"""Fetch and cache VitalDB case table, track list, and per-case numeric tracks.

Phase 1 (PLAN.md Section 6, Phase 1):
  1. fetch the case table + track list, cache to data/raw/
  2. print/save the actual column and track names (never guessed)
  3. flag cases with invasive-arterial HR, SBP, DBP, MAP
  4. write data/interim/inventory.parquet
  5. test on 5 cases: fetch whole-case files, keep numeric tracks, resample,
     measure size/time, extrapolate before any bulk download

Rules (CLAUDE.md Section 12):
- Never guess dataset column or track names — read them from the downloaded
  inventory (data/manual/track_names.csv, data/manual/clinical_parameters.csv)
  and config.py, which already hold the confirmed names (verified 2026-10-24).
- Cache downloads; never re-download a cached case (download_case_numeric_tracks
  skips any caseid already on disk under dest_dir).
- Never download the full 95.4 GB dataset — see config.DOWNLOAD_TARGET_CASES_MIN/MAX.
- The event has started (2026-10-24): the Phase 2 bulk download (the full
  300-500 case sample selected by cohort.select_bulk_download_sample) is
  authorized. None of the functions below run on import — a caller
  (scripts/02b_bulk_download.py) invokes them explicitly.
"""

from __future__ import annotations

import gzip
import io
import time
from pathlib import Path

import pandas as pd
import requests

from . import config, preprocess

ROOT = Path(__file__).resolve().parents[2]
DATA_MANUAL = ROOT / "data" / "manual"
DATA_RAW = ROOT / "data" / "raw"
DATA_INTERIM = ROOT / "data" / "interim"

CASES_CSV_MANUAL = DATA_MANUAL / "cases.csv"
TRACK_NAMES_CSV_MANUAL = DATA_MANUAL / "track_names.csv"
CLINICAL_PARAMETERS_CSV_MANUAL = DATA_MANUAL / "clinical_parameters.csv"

CASES_CSV_RAW = DATA_RAW / "cases.csv"
TRACK_NAMES_CSV_RAW = DATA_RAW / "track_names.csv"

INVENTORY_PARQUET = DATA_INTERIM / "inventory.parquet"


# ---------------------------------------------------------------------------
# Step 1: fetch / cache the case table and track list
# ---------------------------------------------------------------------------
def download_case_table(dest: Path = CASES_CSV_RAW, timeout_s: int = 60) -> Path:
    """Download the clinical case table from the VitalDB API and cache it.

    The endpoint serves gzip-compressed CSV without a Content-Encoding header,
    so requests' automatic decompression doesn't kick in — decompress by hand.
    This is a network call; see the module docstring's rule about when it's
    appropriate to call this versus load_case_table()'s cache-first default.
    """
    resp = requests.get(config.VITALDB_CASES_URL, timeout=timeout_s)
    resp.raise_for_status()
    raw = resp.content
    try:
        raw = gzip.decompress(raw)
    except OSError:
        pass  # already plain text
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    return dest


def load_case_table(prefer_cache: bool = True) -> pd.DataFrame:
    """Load the clinical case table, preferring the already-approved cache.

    Load order: data/raw/cases.csv (if previously fetched this session) ->
    data/manual/cases.csv (the pre-event reference copy, confirmed 2026-10-24)
    -> error. Does NOT hit the network — call download_case_table() first if
    a fresh copy is wanted.
    """
    candidates = [CASES_CSV_RAW, CASES_CSV_MANUAL] if prefer_cache else [CASES_CSV_MANUAL, CASES_CSV_RAW]
    for path in candidates:
        if path.exists():
            df = pd.read_csv(path)
            return df
    raise FileNotFoundError(
        f"No cached case table found at {CASES_CSV_RAW} or {CASES_CSV_MANUAL}. "
        "Run download_case_table() or restore data/manual/cases.csv."
    )


def load_track_names() -> pd.DataFrame:
    """Load the track-name dictionary (Parameter, Description, Type/Hz, Unit)."""
    for path in (TRACK_NAMES_CSV_RAW, TRACK_NAMES_CSV_MANUAL):
        if path.exists():
            return pd.read_csv(path)
    raise FileNotFoundError(
        f"No cached track-name dictionary found at {TRACK_NAMES_CSV_RAW} or "
        f"{TRACK_NAMES_CSV_MANUAL}."
    )


def load_clinical_parameters() -> pd.DataFrame:
    """Load the clinical column dictionary (Parameter, Data Source, Description, Unit)."""
    if CLINICAL_PARAMETERS_CSV_MANUAL.exists():
        return pd.read_csv(CLINICAL_PARAMETERS_CSV_MANUAL)
    raise FileNotFoundError(f"No cached clinical parameter dictionary at {CLINICAL_PARAMETERS_CSV_MANUAL}.")


# ---------------------------------------------------------------------------
# Step 2: print/verify the actual column and track names (never guessed)
# ---------------------------------------------------------------------------
def verify_required_tracks_present(track_names_df: pd.DataFrame) -> dict:
    """Confirm config.REQUIRED_NUMERIC_TRACKS exist exactly as named.

    Returns a dict {track_name: bool_present}. Raises if any are missing —
    the whole point of this step is to never guess.
    """
    present_names = set(track_names_df["Parameter"])
    result = {t: (t in present_names) for t in config.REQUIRED_NUMERIC_TRACKS}
    missing = [t for t, ok in result.items() if not ok]
    if missing:
        raise ValueError(
            f"Expected numeric tracks not found in track_names.csv: {missing}. "
            "Do not guess — update config.py only after checking the real file."
        )
    return result


def verify_required_columns_present(cases_df: pd.DataFrame) -> dict:
    """Confirm every column config.py expects actually exists in cases.csv."""
    expected = [
        config.COL_CASEID, config.COL_SUBJECTID, config.COL_AGE, config.COL_SEX,
        config.COL_WEIGHT, config.COL_ASA, config.COL_EMOP, config.COL_OPSTART,
        config.COL_OPEND, config.COL_ANESTART, config.COL_ANEEND,
        config.COL_ALINE1, config.COL_ALINE2, config.COL_INTRAOP_EBL,
        config.COL_INTRAOP_RBC, config.COL_INTRAOP_FFP,
        config.COL_INTRAOP_CRYSTALLOID, config.COL_INTRAOP_COLLOID,
        config.COL_INTRAOP_UO,
    ]
    present_cols = set(cases_df.columns)
    result = {c: (c in present_cols) for c in expected}
    missing = [c for c, ok in result.items() if not ok]
    if missing:
        raise ValueError(
            f"Expected clinical columns not found in cases.csv: {missing}. "
            "Do not guess — update config.py only after checking the real file."
        )
    return result


# ---------------------------------------------------------------------------
# Step 3: flag cases with invasive-arterial HR, SBP, DBP, MAP
# ---------------------------------------------------------------------------
def flag_invasive_arterial(cases_df: pd.DataFrame) -> pd.Series:
    """True where an arterial line (aline1 or aline2) was recorded.

    aline1/aline2 presence is the clinical-table proxy for "this case has an
    invasive arterial line, so the numeric tracks Solar8000/ART_SBP,
    ART_DBP, ART_MBP (and HR) are expected to be recorded." Whether the four
    numeric tracks are *actually* present per case still needs a per-case
    track-list check (Phase 1 step 5 / the 5-case test), which is a network
    call per case and is gated the same way whole-case downloads are.
    """
    a1 = cases_df[config.COL_ALINE1].notna() & (cases_df[config.COL_ALINE1].astype(str).str.strip() != "")
    a2 = cases_df[config.COL_ALINE2].notna() & (cases_df[config.COL_ALINE2].astype(str).str.strip() != "")
    return a1 | a2


# ---------------------------------------------------------------------------
# Step 4: build data/interim/inventory.parquet
# ---------------------------------------------------------------------------
def build_inventory(cases_df: pd.DataFrame) -> pd.DataFrame:
    """Build the inventory table: availability flags, duration, EBL, RBC
    units, age, ASA, emergency flag — per PLAN.md Phase 1 step 4.

    casestart/caseend are both "set to 0 for anonymization" per
    clinical_parameters.csv, so case duration is computed from
    opstart/opend (seconds, relative to casestart) instead.
    """
    inv = pd.DataFrame()
    inv[config.COL_CASEID] = cases_df[config.COL_CASEID]
    inv["has_arterial_line"] = flag_invasive_arterial(cases_df)
    inv["duration_min"] = (cases_df[config.COL_OPEND] - cases_df[config.COL_OPSTART]) / 60.0
    inv[config.COL_INTRAOP_EBL] = cases_df[config.COL_INTRAOP_EBL]
    inv[config.COL_INTRAOP_RBC] = cases_df[config.COL_INTRAOP_RBC]
    inv[config.COL_AGE] = cases_df[config.COL_AGE]
    inv[config.COL_ASA] = cases_df[config.COL_ASA]
    inv["emergency"] = cases_df[config.COL_EMOP]
    # "with all four tracks" (actual per-case numeric-track presence) cannot
    # be filled in from the clinical table alone — see flag_invasive_arterial
    # docstring. Left as a column of NA until the Phase 1 step-5 per-case
    # check runs (pending network-access sign-off; see vitaldb_io.py module
    # docstring and the Oct 24 decisions).
    inv["has_all_four_numeric_tracks"] = pd.NA
    return inv


def save_inventory(inventory_df: pd.DataFrame, dest: Path = INVENTORY_PARQUET) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    inventory_df.to_parquet(dest, index=False)
    return dest


def ebl_bucket(ebl_ml: pd.Series) -> pd.Series:
    """Bucket intraop_ebl for the Phase 1 accept-criteria printout.

    Bucket edges are for *reporting* only (none of this is a model feature,
    and the Cohort B rule in config.py is separate and fixed).
    """
    bins = [-float("inf"), 0, 100, 500, float("inf")]
    labels = ["0 (none recorded)", "1-100 mL", "101-500 mL", ">500 mL"]
    return pd.cut(ebl_ml, bins=bins, labels=labels)


def print_inventory_counts(cases_df: pd.DataFrame, inventory_df: pd.DataFrame) -> None:
    """Phase 1 accept criterion: counts printed (total, with arterial line,
    with all four tracks, by EBL bucket)."""
    total = len(inventory_df)
    with_arterial = int(inventory_df["has_arterial_line"].sum())
    print(f"Total cases in clinical table: {total}")
    print(f"With invasive arterial line (aline1/aline2 recorded): {with_arterial}")
    print(
        "With all four numeric tracks confirmed present: PENDING "
        "(requires a per-case track-list check — gated the same as bulk "
        "whole-case downloads; see vitaldb_io.py module docstring)."
    )
    print("By EBL bucket:")
    buckets = ebl_bucket(inventory_df[config.COL_INTRAOP_EBL])
    print(buckets.value_counts(dropna=False).sort_index().to_string())


# ---------------------------------------------------------------------------
# Step 5: per-case download / resample test (NOT auto-run on import).
# Gated: whole-case downloads wait for event start / organizer sign-off
# (PLAN.md Section 1, Oct 24 Decision 1). Written here so it's ready to run
# the moment that sign-off exists, without needing to write it under time
# pressure during the event.
# ---------------------------------------------------------------------------
def download_case_numeric_tracks(
    caseid: int,
    tracks: tuple[str, ...] = config.REQUIRED_NUMERIC_TRACKS,
    dest_dir: Path = DATA_RAW,
    timeout_s: int = 60,
    skip_existing: bool = True,
    file_suffix: str = "numeric_30s",
) -> tuple[Path, float, int, bool]:
    """Fetch one whole case via the vitaldb library, keep only `tracks`,
    cache the lean table, and return (path, seconds_elapsed, bytes_written,
    was_cached).

    This is the "test on 5 cases" step (Phase 1, step 5) and the function
    the Phase 2 bulk download (vitaldb_io.bulk_download_numeric_tracks)
    calls per case. skip_existing=True (the default) never re-downloads a
    case already cached under dest_dir, per CLAUDE.md Section 12 /
    DATA_NOTES.md: "cache downloads; never re-download a cached case."

    file_suffix lets a caller fetch a DIFFERENT track set for the same
    caseid into its own cache file (e.g. "drugs_30s" for the Experiment 2
    vasopressor/anesthetic tracks) without colliding with or re-fetching
    the core numeric tracks.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{caseid}_{file_suffix}.parquet"
    if skip_existing and dest.exists():
        return dest, 0.0, dest.stat().st_size, True

    import vitaldb  # imported here so the rest of this module works without it

    t0 = time.monotonic()
    vf = vitaldb.VitalFile(caseid, tracks)
    df = vf.to_pandas(tracks, interval=30, return_timestamp=True)
    elapsed = time.monotonic() - t0

    df.to_parquet(dest, index=False)
    size_bytes = dest.stat().st_size
    return dest, elapsed, size_bytes, False


def test_download_n_cases(caseids: list[int], dest_dir: Path = DATA_RAW) -> pd.DataFrame:
    """Run download_case_numeric_tracks over a small list of case ids and
    report size/time per case, for extrapolating disk and time before any
    bulk download (Phase 1, step 5, accept criterion)."""
    rows = []
    for cid in caseids:
        try:
            path, elapsed_s, size_bytes, cached = download_case_numeric_tracks(cid, dest_dir=dest_dir)
            rows.append({
                "caseid": cid, "ok": True, "seconds": elapsed_s,
                "bytes": size_bytes, "path": str(path), "cached": cached,
            })
        except Exception as exc:  # noqa: BLE001 - report failures, don't crash the test
            rows.append({"caseid": cid, "ok": False, "error": str(exc)})
    report = pd.DataFrame(rows)
    if report["ok"].any():
        ok = report[report["ok"]]
        avg_s = ok["seconds"].mean()
        avg_bytes = ok["bytes"].mean()
        print(f"Tested {len(ok)}/{len(caseids)} cases successfully.")
        print(f"Avg time/case: {avg_s:.2f}s -> est. for {config.DOWNLOAD_TARGET_CASES_MAX} cases: {avg_s * config.DOWNLOAD_TARGET_CASES_MAX / 60:.1f} min")
        print(f"Avg size/case: {avg_bytes / 1e6:.2f} MB -> est. for {config.DOWNLOAD_TARGET_CASES_MAX} cases: {avg_bytes * config.DOWNLOAD_TARGET_CASES_MAX / 1e9:.2f} GB")
    return report


def load_drug_tracks(caseid: int, dest_dir: Path = DATA_RAW) -> pd.DataFrame:
    """Load the cached vasopressor/anesthetic tracks (config.DRUG_TRACKS,
    downloaded via bulk_download_numeric_tracks(..., tracks=config.DRUG_TRACKS,
    file_suffix="drugs_30s")) and align Time the same way load_and_clean_case
    does.

    NaN -> 0 for every drug/anesthetic column: empirically verified (case
    17: Orchestra/NEPI_RATE is NaN for ~280 minutes, then jumps straight to
    4.8 when the infusion starts -- no intermediate "0.0 but recorded"
    period) that these pump/gas tracks simply aren't recorded while a drug
    isn't running, not "recorded as missing while running." Treating NaN as
    0 is what lets Experiment 2 detect an infusion *starting* (0 -> nonzero)
    as the "increase" it is, and is harmless for a track a case never uses
    at all (stays 0 throughout either way). No artifact-range rejection
    here -- rate/concentration tracks don't share HR/BP's physiological
    bounds.
    """
    path = dest_dir / f"{caseid}_drugs_30s.parquet"
    df = pd.read_parquet(path)
    df = df.sort_values("Time").reset_index(drop=True)
    df["Time"] = df["Time"] - df["Time"].min()
    drug_cols = [c for c in df.columns if c in config.DRUG_TRACKS]
    df[drug_cols] = df[drug_cols].fillna(0.0)
    return df


def load_and_clean_case(caseid: int, dest_dir: Path = DATA_RAW) -> pd.DataFrame:
    """Load a cached numeric-tracks parquet, align Time to the casestart=0
    clock, and apply the same cleaning used everywhere else in this project
    (preprocess.reject_artifacts then interpolate_short_gaps).

    Time alignment: clinical_parameters.csv defines casestart as "Recording
    Start Time; Set to 0 for anonymization" -- i.e. casestart IS the first
    sample of the downloaded file, so Time - Time.min() lands on the exact
    same clock as cases.csv's anestart/opstart/opend (verified against a
    real case in scripts/02c_finalize_cohort.py's development). Used by
    both scripts/02c_finalize_cohort.py and features.py so the two phases
    never silently diverge on cleaning.
    """
    path = dest_dir / f"{caseid}_numeric_30s.parquet"
    df = pd.read_parquet(path)
    df = df.sort_values("Time").reset_index(drop=True)
    df["Time"] = df["Time"] - df["Time"].min()
    cleaned = preprocess.reject_artifacts(df)
    cleaned = preprocess.interpolate_short_gaps(cleaned, value_cols=list(config.REQUIRED_NUMERIC_TRACKS))
    return cleaned


# ---------------------------------------------------------------------------
# Phase 2 bulk download: the full selected sample (300-500 cases), not just
# the 5-case test. Authorized at event start (2026-10-24) -- see CLAUDE.md.
# ---------------------------------------------------------------------------
def bulk_download_numeric_tracks(
    caseids: list[int],
    dest_dir: Path = DATA_RAW,
    progress_every: int = 25,
    tracks: tuple[str, ...] = config.REQUIRED_NUMERIC_TRACKS,
    file_suffix: str = "numeric_30s",
) -> pd.DataFrame:
    """Download (or reuse cached) numeric tracks for every caseid in the
    list. Never raises on a single case's failure -- records it and moves
    on, so one bad caseid can't abort an hours-long run. Returns a report
    DataFrame (caseid, ok, seconds, bytes, cached, path/error); callers
    should persist it (e.g. artifacts/phase2_bulk_download_report.csv).

    tracks/file_suffix let this fetch a different track set into its own
    cache file (see download_case_numeric_tracks)."""
    rows = []
    for i, cid in enumerate(caseids, start=1):
        try:
            path, elapsed_s, size_bytes, cached = download_case_numeric_tracks(
                cid, tracks=tracks, dest_dir=dest_dir, file_suffix=file_suffix,
            )
            rows.append({
                "caseid": cid, "ok": True, "seconds": elapsed_s,
                "bytes": size_bytes, "cached": cached, "path": str(path),
            })
        except Exception as exc:  # noqa: BLE001 - one bad case must not abort the run
            rows.append({"caseid": cid, "ok": False, "error": str(exc)})
        if progress_every and i % progress_every == 0:
            print(f"  ... {i}/{len(caseids)} cases processed")
    report = pd.DataFrame(rows)
    return report
