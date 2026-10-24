"""Phase 3 feature/window tests on toy series (no real VitalDB data needed).
The causality tests are the accept criterion PLAN.md/CLAUDE.md call out as
the single most important integrity requirement (Adjustment A3): a feature
computed at time t must never change no matter what the data after t says."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import config, features  # noqa: E402

BASELINE_HR, BASELINE_MAP, BASELINE_SBP, BASELINE_DBP = 70.0, 90.0, 120.0, 70.0


def _toy_case_df(
    duration_s: float = 7200.0,
    interval_s: float = 30.0,
    event_start_s: float = 3000.0,
    event_duration_s: float = 120.0,
):
    """A stable toy case (HR=70, MAP=90, SBP=120, DBP=70 throughout) with
    one MAP<65 event from event_start_s for event_duration_s."""
    times = np.arange(0.0, duration_s, interval_s)
    hr = np.full_like(times, BASELINE_HR)
    sbp = np.full_like(times, BASELINE_SBP)
    dbp = np.full_like(times, BASELINE_DBP)
    map_ = np.full_like(times, BASELINE_MAP)

    in_event = (times >= event_start_s) & (times < event_start_s + event_duration_s)
    map_[in_event] = 55.0
    sbp[in_event] = 85.0  # keep SBP > DBP during the event

    return pd.DataFrame({
        "Time": times,
        config.TRACK_HR: hr,
        config.TRACK_SBP: sbp,
        config.TRACK_DBP: dbp,
        config.TRACK_MAP: map_,
    })


def _toy_case_row(anestart_s=0.0, opstart_s=0.0, opend_s=7200.0, age=55, sex="M", asa=2, emop=0):
    return pd.Series({
        config.COL_CASEID: 999,
        config.COL_ANESTART: anestart_s,
        config.COL_OPSTART: opstart_s,
        config.COL_OPEND: opend_s,
        config.COL_AGE: age,
        config.COL_SEX: sex,
        config.COL_ASA: asa,
        config.COL_EMOP: emop,
    })


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------
def test_compute_patient_baseline_matches_known_constant_values():
    df = _toy_case_df()
    baseline = features.compute_patient_baseline(df, anesthesia_start_s=0.0)
    assert baseline["hr"] == BASELINE_HR
    assert baseline["map"] == BASELINE_MAP
    assert baseline["pp"] == BASELINE_SBP - BASELINE_DBP
    assert baseline["shock_index"] == pytest.approx(BASELINE_HR / BASELINE_SBP)
    # exclusion window (15 min) + baseline window (10 min) = 1500s
    assert baseline["baseline_end_s"] == 1500.0


# ---------------------------------------------------------------------------
# has_recent_map_low
# ---------------------------------------------------------------------------
def test_has_recent_map_low_true_during_and_shortly_after_event():
    df = _toy_case_df()
    assert features.has_recent_map_low(df, t_s=3030.0) is True  # inside the event
    assert features.has_recent_map_low(df, t_s=3150.0) is True  # event just ended (within 5 min)


def test_has_recent_map_low_false_well_before_or_long_after_event():
    df = _toy_case_df()
    assert features.has_recent_map_low(df, t_s=1500.0) is False
    assert features.has_recent_map_low(df, t_s=3000.0 + 120.0 + 301.0) is False


# ---------------------------------------------------------------------------
# compute_window_features: basic correctness on a flat, pre-event window
# ---------------------------------------------------------------------------
def test_compute_window_features_flat_region_has_zero_slopes_and_no_drift():
    df = _toy_case_df()
    baseline = features.compute_patient_baseline(df, anesthesia_start_s=0.0)
    t_s = 2000.0  # after baseline closes (1500s), well before the event (3000s)
    feat = features.compute_window_features(df, t_s, baseline)
    assert feat["hr"] == BASELINE_HR
    assert feat["map"] == BASELINE_MAP
    assert feat["pp"] == BASELINE_SBP - BASELINE_DBP
    for series in ("hr", "map", "pp", "shock_index"):
        for w in config.FEATURE_SLOPE_WINDOWS_MIN:
            assert feat[f"{series}_slope_{w}"] == pytest.approx(0.0, abs=1e-9)
        assert feat[f"{series}_drift"] == pytest.approx(0.0, abs=1e-9)
    assert feat["missing_fraction"] == pytest.approx(0.0)


def test_compute_window_features_returns_none_with_no_data_at_or_before_t():
    df = _toy_case_df()
    baseline = features.compute_patient_baseline(df, anesthesia_start_s=0.0)
    assert features.compute_window_features(df.iloc[0:0], 2000.0, baseline) is None


# ---------------------------------------------------------------------------
# Causality: the accept criterion. Recomputing from data truncated at t (or
# from data with everything after t corrupted) must give the identical
# feature vector as computing from the full case.
# ---------------------------------------------------------------------------
def test_compute_window_features_is_unaffected_by_truncating_future_rows():
    df = _toy_case_df()
    baseline = features.compute_patient_baseline(df, anesthesia_start_s=0.0)
    t_s = 2500.0

    feat_full = features.compute_window_features(df, t_s, baseline)
    truncated = df[df["Time"] <= t_s]
    feat_truncated = features.compute_window_features(truncated, t_s, baseline)

    assert feat_full.keys() == feat_truncated.keys()
    for k in feat_full:
        if pd.isna(feat_full[k]) and pd.isna(feat_truncated[k]):
            continue
        assert feat_full[k] == pytest.approx(feat_truncated[k])


def test_compute_window_features_is_unaffected_by_corrupting_future_rows():
    df = _toy_case_df()
    baseline = features.compute_patient_baseline(df, anesthesia_start_s=0.0)
    t_s = 2500.0

    feat_before = features.compute_window_features(df, t_s, baseline)

    corrupted = df.copy()
    future = corrupted["Time"] > t_s
    corrupted.loc[future, config.TRACK_HR] = 999.0
    corrupted.loc[future, config.TRACK_MAP] = 1.0
    corrupted.loc[future, config.TRACK_SBP] = 999.0
    corrupted.loc[future, config.TRACK_DBP] = 1.0
    feat_after = features.compute_window_features(corrupted, t_s, baseline)

    for k in feat_before:
        if pd.isna(feat_before[k]) and pd.isna(feat_after[k]):
            continue
        assert feat_before[k] == pytest.approx(feat_after[k]), f"feature {k} leaked future data"


def test_has_recent_map_low_is_unaffected_by_future_rows():
    df = _toy_case_df()
    t_s = 1500.0  # well before the event; flipping future MAP must not change this
    before = features.has_recent_map_low(df, t_s)
    corrupted = df.copy()
    corrupted.loc[corrupted["Time"] > t_s, config.TRACK_MAP] = 1.0
    after = features.has_recent_map_low(corrupted, t_s)
    assert before == after == False  # noqa: E712


# ---------------------------------------------------------------------------
# build_case_windows: labeling and exclusion end to end
# ---------------------------------------------------------------------------
def test_build_case_windows_labels_primary_horizon_correctly_before_event():
    df = _toy_case_df()
    row = _toy_case_row()
    windows = features.build_case_windows(df, row)
    assert len(windows) > 0

    # A prediction time exactly one primary-horizon (15 min = 900s) before
    # the event start must be labeled positive for h15.
    t_just_inside = 3000.0 - config.HORIZON_MIN_PRIMARY * 60.0
    row_at_t = windows.loc[np.isclose(windows["t_s"], t_just_inside)]
    assert len(row_at_t) == 1
    assert row_at_t.iloc[0]["label_h15"] == 1.0

    # Far earlier, nothing in the next 15 minutes -> negative.
    t_far_before = 1620.0  # a valid 60s-stride grid point (t_start=1500, stride=60s)
    row_far = windows.loc[np.isclose(windows["t_s"], t_far_before)]
    assert len(row_far) == 1
    assert row_far.iloc[0]["label_h15"] == 0.0


def test_build_case_windows_excludes_recent_map_low_prediction_times():
    df = _toy_case_df()
    row = _toy_case_row()
    windows = features.build_case_windows(df, row)
    # No kept window may have MAP<65 in the 5 minutes before it.
    for t_s in windows["t_s"]:
        assert not features.has_recent_map_low(df, t_s)


def test_build_case_windows_marks_label_unknown_when_horizon_exceeds_case_end():
    df = _toy_case_df(duration_s=2000.0, event_start_s=999999.0)  # no event at all, short case
    row = _toy_case_row(opend_s=2000.0)
    windows = features.build_case_windows(df, row)
    # Any t within HORIZON_MIN_PRIMARY minutes of case end must have label_h15 = NaN.
    near_end = windows[windows["t_s"] > 2000.0 - config.HORIZON_MIN_PRIMARY * 60.0]
    assert len(near_end) > 0
    assert near_end["label_h15"].isna().all()


def test_build_case_windows_empty_when_baseline_unavailable():
    # Case ends before the baseline window even opens.
    df = _toy_case_df(duration_s=500.0)
    row = _toy_case_row(opend_s=500.0)
    windows = features.build_case_windows(df, row)
    assert len(windows) == 0
