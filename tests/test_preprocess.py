"""Artifact rejection and gap-interpolation unit tests on toy series."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import config, preprocess  # noqa: E402


def test_reject_artifacts_nulls_out_of_range_values():
    df = pd.DataFrame({
        config.TRACK_HR: [60, 5, 260, 80],       # 5 and 260 out of [20,250]
        config.TRACK_SBP: [120, 310, 25, 110],   # 310 and 25 out of [30,300]
        config.TRACK_DBP: [70, 80, 15, 5],       # 5 out of [10,200]
        config.TRACK_MAP: [90, 10, 260, 85],     # 10 and 260 out of [20,250]
    })
    out = preprocess.reject_artifacts(df)
    assert np.isnan(out[config.TRACK_HR].iloc[1])  # 5 rejected
    assert np.isnan(out[config.TRACK_HR].iloc[2])  # 260 rejected
    assert out[config.TRACK_HR].iloc[0] == 60
    assert np.isnan(out[config.TRACK_SBP].iloc[1])  # 310 rejected
    assert np.isnan(out[config.TRACK_MAP].iloc[1])  # 10 rejected
    assert np.isnan(out[config.TRACK_MAP].iloc[2])  # 260 rejected
    assert np.isnan(out[config.TRACK_DBP].iloc[3])  # 5 rejected


def test_reject_artifacts_nulls_sbp_leq_dbp_rows():
    df = pd.DataFrame({
        config.TRACK_SBP: [120, 70, 110],
        config.TRACK_DBP: [70, 75, 60],  # row 1: SBP(70) <= DBP(75) -> violates
    })
    out = preprocess.reject_artifacts(df)
    assert np.isnan(out[config.TRACK_SBP].iloc[1])
    assert np.isnan(out[config.TRACK_DBP].iloc[1])
    assert out[config.TRACK_SBP].iloc[0] == 120
    assert out[config.TRACK_SBP].iloc[2] == 110


def test_reject_artifacts_does_not_mutate_input():
    df = pd.DataFrame({config.TRACK_HR: [5, 60]})
    original = df.copy()
    preprocess.reject_artifacts(df)
    pd.testing.assert_frame_equal(df, original)


def test_interpolate_short_gaps_fills_gap_within_limit():
    # One missing sample at t=30; bracketing valid points are t=0 and t=60,
    # 60s apart (<=60 limit, inclusive) -> interpolated.
    df = pd.DataFrame({"Time": [0, 30, 60, 90], "val": [10.0, np.nan, 30.0, 40.0]})
    out = preprocess.interpolate_short_gaps(df, value_cols=["val"], max_gap_s=60)
    assert out["val"].iloc[1] == pytest.approx(20.0)


def test_interpolate_short_gaps_bracket_distance_not_missing_sample_count():
    # Two consecutive missing samples at 30s spacing -> bracketing valid
    # points are 90s apart, which exceeds the 60s limit even though each
    # individual missing slot is only 30s. "No interpolation beyond 60s" is
    # measured as the gap between the surrounding valid samples.
    df = pd.DataFrame({"Time": [0, 30, 60, 90], "val": [10.0, np.nan, np.nan, 40.0]})
    out = preprocess.interpolate_short_gaps(df, value_cols=["val"], max_gap_s=60)
    assert np.isnan(out["val"].iloc[1])
    assert np.isnan(out["val"].iloc[2])


def test_interpolate_short_gaps_leaves_long_gap_as_nan():
    df = pd.DataFrame({"Time": [0, 200, 400], "val": [10.0, np.nan, 40.0]})
    out = preprocess.interpolate_short_gaps(df, value_cols=["val"], max_gap_s=60)
    assert np.isnan(out["val"].iloc[1])  # gap is 400s, way over the 60s limit


def test_interpolate_short_gaps_leaves_edge_nan_untouched():
    # No valid sample before the leading NaN -> can't interpolate it.
    df = pd.DataFrame({"Time": [0, 30, 60], "val": [np.nan, 20.0, 30.0]})
    out = preprocess.interpolate_short_gaps(df, value_cols=["val"], max_gap_s=60)
    assert np.isnan(out["val"].iloc[0])
