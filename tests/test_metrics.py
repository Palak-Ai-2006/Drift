"""Toy tests for event-level sensitivity/lead-time and bootstrap CIs
(PLAN.md Section 4/7.5/8)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import metrics  # noqa: E402


def test_event_sensitivity_detects_event_with_qualifying_alert():
    case_events = {1: [900.0]}  # event at t=900
    case_alerts = {1: [100.0]}  # alert at t=100; 100 < 900 <= 100+900 -> true
    result = metrics.event_sensitivity_and_lead_times(case_events, case_alerts, [1], horizon_min=15)
    assert result["n_events"] == 1
    assert result["n_detected"] == 1
    assert result["sensitivity"] == 1.0
    assert result["lead_times_s"] == [800.0]


def test_event_sensitivity_misses_event_with_no_qualifying_alert():
    case_events = {1: [900.0]}
    case_alerts = {1: [50.0]}  # 50 + 900 = 950 >= 900, so this DOES qualify; use a too-early alert instead
    case_alerts = {1: [-100.0]}  # -100 + 900 = 800 < 900 -> does not qualify (too early for horizon)
    result = metrics.event_sensitivity_and_lead_times(case_events, case_alerts, [1], horizon_min=15)
    assert result["n_detected"] == 0
    assert result["sensitivity"] == 0.0
    assert result["lead_times_s"] == []


def test_event_sensitivity_uses_earliest_qualifying_alert_for_max_lead_time():
    case_events = {1: [900.0]}
    case_alerts = {1: [500.0, 800.0]}  # both qualify (within 900s before event); earliest gives longest lead
    result = metrics.event_sensitivity_and_lead_times(case_events, case_alerts, [1], horizon_min=15)
    assert result["lead_times_s"] == [400.0]  # 900 - 500


def test_event_sensitivity_aggregates_across_cases():
    case_events = {1: [900.0], 2: [900.0]}
    case_alerts = {1: [100.0], 2: []}  # case 1 detected, case 2 missed
    result = metrics.event_sensitivity_and_lead_times(case_events, case_alerts, [1, 2], horizon_min=15)
    assert result["n_events"] == 2
    assert result["n_detected"] == 1
    assert result["sensitivity"] == 0.5


def test_lead_time_summary_on_known_values():
    summary = metrics.lead_time_summary([100.0, 200.0, 300.0, 400.0, 500.0])
    assert summary["median_s"] == 300.0
    assert summary["n"] == 5


def test_lead_time_summary_empty():
    summary = metrics.lead_time_summary([])
    assert summary["n"] == 0
    assert np.isnan(summary["median_s"])


def test_auroc_auprc_brier_excludes_nan_labels():
    y_true = pd.Series([1.0, 0.0, np.nan, 1.0, 0.0])
    y_prob = pd.Series([0.9, 0.1, 0.5, 0.8, 0.2])
    result = metrics.auroc_auprc_brier(y_true, y_prob)
    assert result["n"] == 4
    assert result["auroc"] == 1.0  # perfect separation among the labeled rows


def test_reliability_curve_bins_known_values_correctly():
    y_true = pd.Series([0.0, 0.0, 1.0, 1.0])
    y_prob = pd.Series([0.03, 0.08, 0.92, 0.97])
    result = metrics.reliability_curve(y_true, y_prob, n_bins=10)
    low_bin = result["bins"][0]
    high_bin = result["bins"][9]
    assert low_bin["n"] == 2
    assert low_bin["observed_fraction"] == 0.0
    assert high_bin["n"] == 2
    assert high_bin["observed_fraction"] == 1.0


def test_reliability_curve_excludes_nan_labels():
    y_true = pd.Series([0.0, np.nan, 1.0])
    y_prob = pd.Series([0.05, 0.5, 0.95])
    result = metrics.reliability_curve(y_true, y_prob, n_bins=10)
    total_n = sum(b["n"] for b in result["bins"])
    assert total_n == 2


def test_bootstrap_ci_by_case_point_estimate_uses_full_unresampled_set():
    caseids = [1, 2, 3, 4]
    values = {1: 1.0, 2: 2.0, 3: 3.0, 4: 4.0}

    def metric_fn(sample):
        return float(np.mean([values[c] for c in sample]))

    result = metrics.bootstrap_ci_by_case(caseids, metric_fn, n_resamples=200)
    assert result["point"] == pytest.approx(2.5)
    assert result["ci_low"] <= result["point"] <= result["ci_high"]


def test_bootstrap_ci_by_case_handles_nan_resamples():
    caseids = [1, 2]

    def metric_fn(sample):
        return float("nan") if len(set(sample)) == 1 else 1.0

    result = metrics.bootstrap_ci_by_case(caseids, metric_fn, n_resamples=50)
    assert result["n_valid_resamples"] <= 50
