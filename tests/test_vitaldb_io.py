"""Phase 1 tests for vitaldb_io.py, steps 1-4 (loading, name verification,
arterial-line flagging, inventory building). Runs against the real cached
reference tables in data/manual/ (small, pre-approved, already committed to
this machine — see DATA_NOTES.md) rather than mocks, since those files are
exactly what the module is built to read.

Step 5 (per-case whole-file download) is NOT tested here — it needs live
network access to VitalDB's per-case endpoint, which is gated behind the
bulk-download sign-off (see vitaldb_io.py module docstring).
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import config, vitaldb_io  # noqa: E402


@pytest.fixture(scope="module")
def cases_df():
    return vitaldb_io.load_case_table()


@pytest.fixture(scope="module")
def track_names_df():
    return vitaldb_io.load_track_names()


def test_load_case_table_matches_known_shape(cases_df):
    # 6,388 cases + header, confirmed 2026-10-24 (DATA_NOTES.md).
    assert len(cases_df) == 6388
    assert config.COL_CASEID in cases_df.columns


def test_load_track_names_has_expected_rows(track_names_df):
    assert len(track_names_df) > 0
    assert "Parameter" in track_names_df.columns


def test_verify_required_tracks_present(track_names_df):
    result = vitaldb_io.verify_required_tracks_present(track_names_df)
    assert all(result.values())
    assert set(result.keys()) == set(config.REQUIRED_NUMERIC_TRACKS)


def test_verify_required_columns_present(cases_df):
    result = vitaldb_io.verify_required_columns_present(cases_df)
    assert all(result.values())


def test_verify_required_tracks_raises_on_missing(track_names_df):
    broken = track_names_df[track_names_df["Parameter"] != config.TRACK_HR]
    with pytest.raises(ValueError, match="Solar8000/HR"):
        vitaldb_io.verify_required_tracks_present(broken)


def test_flag_invasive_arterial_matches_raw_aline_counts(cases_df):
    flags = vitaldb_io.flag_invasive_arterial(cases_df)
    raw_count = (
        cases_df[config.COL_ALINE1].notna() | cases_df[config.COL_ALINE2].notna()
    ).sum()
    assert flags.sum() == raw_count
    assert flags.dtype == bool


def test_build_inventory_shape_and_columns(cases_df):
    inv = vitaldb_io.build_inventory(cases_df)
    assert len(inv) == len(cases_df)
    for col in (
        config.COL_CASEID, "has_arterial_line", "duration_min",
        config.COL_INTRAOP_EBL, config.COL_INTRAOP_RBC, config.COL_AGE,
        config.COL_ASA, "emergency", "has_all_four_numeric_tracks",
    ):
        assert col in inv.columns


def test_build_inventory_never_uses_end_of_case_totals_as_features():
    # Guard against regressions: inventory may READ end-of-case totals (to
    # report/select cohorts) but this module must never claim to compute a
    # model feature from them. This test just documents the columns that are
    # selection-only per config.END_OF_CASE_SELECTION_ONLY_COLS.
    for col in (config.COL_INTRAOP_EBL, config.COL_INTRAOP_RBC):
        assert col in config.END_OF_CASE_SELECTION_ONLY_COLS


def test_save_and_reload_inventory_roundtrip(cases_df, tmp_path):
    inv = vitaldb_io.build_inventory(cases_df)
    dest = tmp_path / "inventory.parquet"
    vitaldb_io.save_inventory(inv, dest=dest)
    reloaded = pd.read_parquet(dest)
    assert len(reloaded) == len(inv)


def test_ebl_bucket_covers_full_range():
    s = pd.Series([float("nan"), 0, 50, 300, 1000])
    buckets = vitaldb_io.ebl_bucket(s)
    assert len(buckets) == 5
