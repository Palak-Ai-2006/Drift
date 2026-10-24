"""Toy-series tests for alarm generation and the operating-point threshold
search (PLAN.md Section 4/7.3/7.4/7.6)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import alarms, config  # noqa: E402


def _case_df(t_s, risk, map_=None, missing_fraction=None):
    n = len(t_s)
    return pd.DataFrame({
        "t_s": t_s,
        "risk": risk,
        "map": map_ if map_ is not None else [90.0] * n,
        "missing_fraction": missing_fraction if missing_fraction is not None else [0.0] * n,
    })


def test_generate_case_alerts_applies_refractory_period():
    # Risk stays high for a long stretch; without refractory suppression
    # every minute would alert.
    t_s = [0, 60, 120, 180, 240, 900, 960]
    risk = [1, 1, 1, 1, 1, 1, 1]
    df = _case_df(t_s, risk)
    alerts = alarms.generate_case_alerts(df, "risk", threshold=0.5, refractory_min=15)
    # 15 min refractory = 900s: alert at t=0, next allowed alert at t>=900.
    assert alerts == [0, 900]


def test_generate_case_alerts_suppressed_by_missing_fraction():
    t_s = [0, 60]
    risk = [1, 1]
    df = _case_df(t_s, risk, missing_fraction=[0.5, 0.0])
    alerts = alarms.generate_case_alerts(df, "risk", threshold=0.5, missing_fraction_cutoff=0.30)
    assert alerts == [60]


def test_generate_case_alerts_suppressed_when_map_already_low():
    t_s = [0, 60]
    risk = [1, 1]
    df = _case_df(t_s, risk, map_=[50.0, 90.0])
    alerts = alarms.generate_case_alerts(df, "risk", threshold=0.5)
    assert alerts == [60]


def test_generate_case_alerts_below_threshold_never_alerts():
    df = _case_df([0, 60], [0.1, 0.2])
    assert alarms.generate_case_alerts(df, "risk", threshold=0.5) == []


def test_alert_is_false_when_no_event_follows_within_horizon():
    assert alarms.alert_is_false(100.0, event_starts_s=[2000.0], horizon_min=15) is True
    assert alarms.alert_is_false(100.0, event_starts_s=[], horizon_min=15) is True


def test_alert_is_true_when_event_follows_within_horizon():
    # Event at t=700, alert at t=100, horizon 15min=900s -> 100 < 700 <= 1000.
    assert alarms.alert_is_false(100.0, event_starts_s=[700.0], horizon_min=15) is False


def test_false_alarm_rate_for_threshold_counts_only_false_alerts():
    # One case, two alerts (15-min refractory apart so both survive), one
    # true (event follows within horizon) and one false (nothing follows).
    t_s = [0, 900, 1800]
    risk = [1, 1, 1]
    df = _case_df(t_s, risk)
    case_dfs = {1: df}
    case_events = {1: [100.0]}  # only the t=0 alert is "true" (100 in (0, 900])
    rate = alarms.false_alarm_rate_for_threshold(case_dfs, case_events, "risk", threshold=0.5, horizon_min=15)
    hours = alarms.monitored_patient_hours(df)
    assert rate == pytest.approx(2 / hours)  # 2 false out of 3 alerts


def test_higher_threshold_never_increases_false_alarm_rate():
    # Risk rises step-wise over 4 hours; no events anywhere, so every
    # alert that survives refractory suppression is false.
    t_s = list(range(0, 4 * 3600, 60))
    risk = [float(i) for i in range(len(t_s))]
    df = _case_df(t_s, risk)
    case_dfs = {1: df}
    case_events = {1: []}
    low_thr_rate = alarms.false_alarm_rate_for_threshold(case_dfs, case_events, "risk", threshold=10, horizon_min=15)
    high_thr_rate = alarms.false_alarm_rate_for_threshold(case_dfs, case_events, "risk", threshold=len(t_s) - 10, horizon_min=15)
    assert high_thr_rate <= low_thr_rate


def test_false_alarm_rate_respects_repeated_caseids_for_bootstrap():
    # One alert, no events -> 1 false alarm. Passing the same caseid twice
    # (as a bootstrap resample would) must double both the false-alarm
    # count and the monitored hours, leaving the rate itself unchanged,
    # NOT collapse to a single occurrence.
    df = _case_df([0, 900], [1, 1])
    case_dfs = {1: df}
    case_events = {1: []}
    rate_once = alarms.false_alarm_rate_for_threshold(case_dfs, case_events, "risk", threshold=0.5, caseids=[1])
    rate_twice = alarms.false_alarm_rate_for_threshold(case_dfs, case_events, "risk", threshold=0.5, caseids=[1, 1])
    assert rate_twice == pytest.approx(rate_once)


def test_find_threshold_for_target_fa_rate_achieves_zero_when_requested():
    # No events, so the only way to hit a target of 0 FA/hour is to never alert.
    t_s = list(range(0, 3600, 60))
    risk = [1.0] * len(t_s)
    df = _case_df(t_s, risk)
    case_dfs = {1: df}
    case_events = {1: []}
    thr, fa_rate = alarms.find_threshold_for_target_fa_rate(
        case_dfs, case_events, "risk", target_fa_per_hour=0.0, horizon_min=15,
    )
    assert fa_rate == pytest.approx(0.0)
    assert thr > max(risk)  # threshold had to exceed every observed risk value
