"""Toy tests for replay case selection (PLAN.md Section 6.1)."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import config, replay  # noqa: E402


def test_classify_events_and_alerts_separates_detected_missed_and_false():
    case_events = {1: [1000.0], 2: [2000.0]}
    case_alerts = {1: [100.0], 2: [], 3: [500.0]}  # case 1 detected, case 2 missed, case 3 false alarm
    result = replay.classify_events_and_alerts(case_events, case_alerts, horizon_min=15)
    assert len(result["detected"]) == 1
    assert result["detected"][0]["caseid"] == 1
    assert len(result["missed"]) == 1
    assert result["missed"][0]["caseid"] == 2
    assert len(result["false_alarms"]) == 1
    assert result["false_alarms"][0]["caseid"] == 3


def test_find_insufficient_data_case_detects_persistent_gaps():
    df = pd.DataFrame({
        config.COL_CASEID: [1, 1, 1, 2, 2, 2],
        "missing_fraction": [0.5, 0.6, 0.55, 0.0, 0.0, 0.0],
    })
    result = replay.find_insufficient_data_case(df, min_share=0.5)
    assert result["caseid"] == 1
    assert result["is_true_insufficient"] is True


def test_find_insufficient_data_case_falls_back_to_closest_if_none_qualifies():
    df = pd.DataFrame({config.COL_CASEID: [1, 1, 2, 2], "missing_fraction": [0.1, 0.1, 0.05, 0.05]})
    result = replay.find_insufficient_data_case(df)
    assert result["caseid"] == 1  # highest share, even though below min_share
    assert result["is_true_insufficient"] is False


def test_select_replay_cases_prefers_variety_across_categories():
    # Two cases, each with one detected event and one false alarm.
    case_events = {1: [1000.0], 2: [2000.0]}
    case_alerts = {1: [100.0, 2500.0], 2: [1500.0, 5000.0]}  # case1: alert@100 detects; case2: alert@1500 detects
    windows_df = pd.DataFrame({
        config.COL_CASEID: [1, 1, 2, 2], "t_s": [100.0, 2500.0, 1500.0, 5000.0], "missing_fraction": [0.0] * 4,
    })
    picks = replay.select_replay_cases(windows_df, case_events, case_alerts, horizon_min=15, per_type_target=2)
    kinds = {p["kind"] for p in picks}
    assert "best" in kinds
    assert "false_alarm" in kinds


def test_verdict_text_for_each_kind():
    assert "Missed" in replay.verdict_text("miss", None, None)
    assert "False alarm" in replay.verdict_text("false_alarm", None, None)
    assert "Not enough data" in replay.verdict_text("insufficient", None, None)
    assert "before the standard alarm" in replay.verdict_text("best", 300.0, 900.0)


def test_top_features_at_alert_reflects_the_single_feature_model():
    feats = replay.top_features_at_alert(58.0)
    assert len(feats) == 1
    assert feats[0]["name"] == "MAP"
    assert feats[0]["value"] == 58.0
    assert "below 65" in feats[0]["direction"]
