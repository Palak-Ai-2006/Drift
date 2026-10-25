"""Round 4 evaluation helpers (SYNTHETIC_PLAN.md Sections 4-5, 5a).

Turns generated SynthCases into the same causal feature rows and event
lists the real-data pipeline uses, so the model, B2 and the alarm logic
run unchanged. Generator internals (meta) are used ONLY to label, score
and explain results -- never as model inputs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config, features, labels, semisynth


def generator_fingerprint() -> dict:
    """SHA-256 of semisynth.py and of every SYNTH_* config value. Recorded
    before training (artifacts/round4_generator_freeze.json); the training
    script refuses to run if it no longer matches."""
    import hashlib
    import json
    from pathlib import Path

    code = Path(semisynth.__file__).read_bytes()
    synth_cfg = {k: getattr(config, k) for k in sorted(dir(config)) if k.startswith("SYNTH_")}
    cfg_json = json.dumps(synth_cfg, sort_keys=True, default=list)
    return {
        "semisynth_py_sha256": hashlib.sha256(code).hexdigest(),
        "synth_config_sha256": hashlib.sha256(cfg_json.encode()).hexdigest(),
    }


def synth_case_row(stream: pd.DataFrame, synth_id: int) -> pd.Series:
    """A case_row that makes features.build_case_windows treat the window
    start as the end of the exclusion period: baseline = first 10 min,
    predictions every minute from 10 min to the window end."""
    return pd.Series({
        config.COL_CASEID: synth_id,
        config.COL_ANESTART: -config.EXCLUSION_WINDOW_AFTER_ANESTHESIA_START_MIN * 60.0,
        config.COL_OPSTART: 0.0,
        config.COL_OPEND: float(stream["Time"].max()),
        config.COL_AGE: np.nan, config.COL_SEX: np.nan, config.COL_ASA: np.nan, config.COL_EMOP: np.nan,
    })


def standard_monitor_risk(df: pd.DataFrame) -> pd.Series:
    """1.0 where HR > 120 or SBP < 90 (the non-MAP part of the standard
    monitor; its MAP < 65 part is B1, handled at the event itself)."""
    hit = (df["hr"] > config.SYNTH_STANDARD_MONITOR_HR_HIGH) | (df["sbp"] < config.SYNTH_STANDARD_MONITOR_SBP_LOW)
    return hit.astype(float)


def case_feature_rows(case: semisynth.SynthCase, synth_id: int) -> pd.DataFrame:
    """Causal feature rows for one synthetic case, plus bookkeeping columns
    (synth_id, source_caseid, tier, label) that are NOT model features."""
    rows = features.build_case_windows(case.stream, synth_case_row(case.stream, synth_id))
    if rows.empty:
        return rows
    rows["synth_id"] = synth_id
    rows["source_caseid"] = case.meta["source_caseid"]
    rows["tier"] = case.meta["tier"]
    rows["label"] = case.meta["label"]
    rows["b2_risk"] = -rows["map"]
    rows["std_risk"] = standard_monitor_risk(rows)
    return rows


def case_event_starts(case: semisynth.SynthCase) -> list[float]:
    return sorted(e.start_time for e in labels.detect_primary_events(case.stream))


def featurize_one(args: tuple) -> tuple:
    """(case, synth_id) -> (synth_id, feature rows, event starts); top-level
    so worker processes can import it."""
    case, sid = args
    return sid, case_feature_rows(case, sid), case_event_starts(case)


def feature_matrix(rows: pd.DataFrame) -> pd.DataFrame:
    return rows[list(config.SYNTH_FEATURE_COLUMNS)].copy()


def build_cases(
    windows: list[tuple[int, pd.DataFrame]], seed_base: int, replicates: int = config.SYNTH_EVAL_REPLICATES,
    shifted: bool = False,
) -> list[semisynth.SynthCase]:
    """All tiers x replicates for one split. Seed per (tier, replicate) is
    seed_base + 1000 * tier_index + replicate."""
    out = []
    for ti, tier in enumerate(config.SYNTH_TIERS):
        for rep in range(replicates):
            seed = seed_base + 1000 * ti + rep
            for c in semisynth.generate_tier_cases(windows, tier, seed=seed, shifted=shifted):
                c.meta["replicate"] = rep
                out.append(c)
    return out


def bleed_aware_false_alarms(alerts_s: list[float], event_starts_s: list[float], bleed_onset_s: float | None,
                             horizon_min: float = config.SYNTH_EVAL_HORIZON_MIN) -> int:
    """Secondary FA count: like the primary rule (no event within H after
    the alert), except an alert at or after bleed onset in a bleed stream is
    never false -- the bleed really is happening."""
    n = 0
    for a in alerts_s:
        if bleed_onset_s is not None and a >= bleed_onset_s:
            continue
        if not any(a < e <= a + horizon_min * 60.0 for e in event_starts_s):
            n += 1
    return n


def classify_miss(meta: dict, collapse_s: float, horizon_min: float = config.SYNTH_EVAL_HORIZON_MIN) -> str:
    """First cause that applies, in the pre-registered order: blunted,
    artifact, confounder, fast, other."""
    lo_min, hi_min = collapse_s / 60.0 - horizon_min, collapse_s / 60.0
    if meta.get("g_hr", 1.0) < config.SYNTH_MISS_BLUNTED_G_HR:
        return "blunted"
    if "artifact_onset_min" in meta:
        a0 = meta["artifact_onset_min"]
        a1 = a0 + meta.get("artifact_duration_min", 0.0)
        if a1 >= lo_min and a0 <= hi_min:
            return "artifact"
    if "stim_onset_min" in meta:
        s0, s1 = meta["stim_onset_min"], meta["stim_onset_min"] + meta["stim_duration_min"]
        if s1 >= lo_min and s0 <= hi_min:
            return "confounder"
    if meta.get("rate_band") == "fast":
        return "fast"
    return "other"


# ---------------------------------------------------------------------------
# Fast alarm evaluation: the SAME rules as alarms.generate_case_alerts /
# alarms.find_threshold_for_target_fa_rate (tested equal), on precomputed
# numpy arrays so threshold searches over ~1000 cases take seconds.
# ---------------------------------------------------------------------------
def case_arrays(rows: pd.DataFrame, risk_col: str) -> dict[int, tuple]:
    out = {}
    for sid, g in rows.groupby("synth_id"):
        g = g.sort_values("t_s")
        out[sid] = (
            g["t_s"].to_numpy(dtype=float), g[risk_col].to_numpy(dtype=float),
            g["missing_fraction"].to_numpy(dtype=float), g["map"].to_numpy(dtype=float),
        )
    return out


def fast_alerts(arr: tuple, threshold: float, refractory_min: float = config.ALARM_REFRACTORY_MIN) -> list[float]:
    t, risk, mf, map_ = arr
    with np.errstate(invalid="ignore"):
        eligible = (~np.isnan(risk)) & (risk >= threshold) & (mf <= config.INSUFFICIENT_DATA_MISSING_FRACTION) \
            & (map_ >= config.EVENT_MAP_THRESHOLD_MMHG)
    alerts: list[float] = []
    last = None
    for ts in t[eligible]:
        if last is None or ts - last >= refractory_min * 60.0:
            alerts.append(float(ts))
            last = ts
    return alerts


def n_false(alerts: list[float], events: list[float], horizon_min: float = config.SYNTH_EVAL_HORIZON_MIN) -> int:
    return sum(not any(a < e <= a + horizon_min * 60.0 for e in events) for a in alerts)


def fa_rate(arrays: dict, events: dict, threshold: float) -> float:
    falses = sum(n_false(fast_alerts(a, threshold), events.get(sid, [])) for sid, a in arrays.items())
    hours = sum(len(a[0]) for a in arrays.values()) * config.PREDICTION_STRIDE_MIN / 60.0
    return falses / hours if hours > 0 else float("inf")


def threshold_for_fa(arrays: dict, events: dict, target: float, n_candidates: int = 200) -> tuple[float, float]:
    """Lowest threshold with FA rate <= target; same candidate grid and walk
    as alarms.find_threshold_for_target_fa_rate."""
    all_risk = np.concatenate([a[1] for a in arrays.values()])
    all_risk = all_risk[~np.isnan(all_risk)]
    cands = np.unique(np.quantile(all_risk, np.linspace(0.0, 1.0, n_candidates)))
    cands = np.sort(np.append(cands, cands.max() + 1.0))
    best = (float(cands[-1]), float("inf"))
    for thr in cands:
        r = fa_rate(arrays, events, thr)
        best = (float(thr), r)
        if r <= target:
            return float(thr), float(r)
    return best


def detection(alerts: list[float], event_s: float, horizon_min: float = config.SYNTH_EVAL_HORIZON_MIN) -> float | None:
    """Lead time (s) of the earliest alert in [event - H, event), or None."""
    q = [a for a in alerts if a < event_s <= a + horizon_min * 60.0]
    return event_s - min(q) if q else None


def check_split_disjoint(split_windows: dict[str, list[tuple[int, pd.DataFrame]]], forbidden: set[int]) -> None:
    """Raise if any source VitalDB case appears in two splits or in the
    forbidden set (Phase 4 test cases, fresh holdout)."""
    seen: dict[int, str] = {}
    for split, windows in split_windows.items():
        for cid, _ in windows:
            if cid in forbidden:
                raise AssertionError(f"case {cid} in {split} is forbidden (Phase 4 test or fresh holdout)")
            if cid in seen and seen[cid] != split:
                raise AssertionError(f"case {cid} appears in both {seen[cid]} and {split}")
            seen[cid] = split
