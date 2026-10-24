"""Event-detector unit tests on toy series (PLAN.md Phase 2 accept criterion:
"event-detector unit tests on toy series"). No real VitalDB data needed."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import config, labels  # noqa: E402


def _series(times_s, values, col=config.TRACK_MAP):
    return pd.DataFrame({"Time": times_s, col: values})


def test_sustained_run_detected_with_correct_start_time():
    # MAP drops below 65 at t=60 and stays down through t=150 (90s sustained).
    times = [0, 30, 60, 90, 120, 150, 180]
    values = [80, 75, 60, 55, 58, 62, 80]
    df = _series(times, values)
    events = labels.detect_primary_events(df)
    assert len(events) == 1
    assert events[0].start_time == 60
    assert events[0].end_time == 150
    assert events[0].duration_s == 90


def test_run_shorter_than_threshold_not_detected():
    # Only one sample below 65 (t=60), duration 0s < 60s threshold.
    times = [0, 30, 60, 90, 120]
    values = [80, 75, 60, 75, 80]
    df = _series(times, values)
    events = labels.detect_primary_events(df)
    assert events == []


def test_run_exactly_at_threshold_boundary_is_detected():
    # Two samples, 60s apart, both below 65 -> duration exactly 60s (inclusive).
    times = [0, 30, 60, 90]
    values = [80, 75, 60, 58]
    # last two samples (t=60, t=90) are below 65, duration = 30s < 60 -> no event
    df = _series(times, values)
    events = labels.detect_primary_events(df)
    assert events == []

    # Now make the run span exactly 60s: samples at 60, 90, 120 all below 65.
    times2 = [0, 30, 60, 90, 120, 150]
    values2 = [80, 75, 60, 58, 59, 80]
    df2 = _series(times2, values2)
    events2 = labels.detect_primary_events(df2)
    assert len(events2) == 1
    assert events2[0].duration_s == 60  # inclusive boundary is detected


def test_nan_breaks_a_run_instead_of_extending_or_hiding_it():
    # Below-threshold, then NaN, then below-threshold again: NaN should
    # split this into (at most) two short runs, neither reaching 60s, so no
    # event should be detected overall even though total "bad" time is long.
    times = [0, 30, 60, 90, 120, 150]
    values = [80, 60, np.nan, np.nan, 60, 80]
    df = _series(times, values)
    events = labels.detect_primary_events(df)
    assert events == []


def test_multiple_separate_events_detected_in_order():
    times = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300]
    # Run 1: t=30..90 (60s, below threshold). Above at 120, 150. Run 2: t=180..240 (60s).
    values = [80, 60, 58, 58, 80, 80, 60, 55, 58, 80, 80]
    df = _series(times, values)
    events = labels.detect_primary_events(df)
    assert len(events) == 2
    assert events[0].start_time == 30
    assert events[1].start_time == 180
    assert events[0].start_time < events[1].start_time


def test_irregular_sampling_uses_actual_elapsed_time_not_sample_count():
    # Only 2 samples below threshold, but 70s apart -> should count as
    # sustained (>=60s) even though it's just 2 rows, because duration is
    # measured by elapsed time, not sample count.
    times = [0, 10, 80]
    values = [80, 60, 58]
    df = _series(times, values)
    events = labels.detect_primary_events(df)
    assert len(events) == 1
    assert events[0].duration_s == 70


def test_fallback_short_duration_detects_a_30s_run_primary_does_not():
    times = [0, 30, 60, 90]
    values = [80, 60, 58, 80]  # below-threshold run spans t=30..60, 30s
    df = _series(times, values)
    assert labels.detect_primary_events(df) == []
    fallback_events = labels.detect_fallback_short_duration_events(df)
    assert len(fallback_events) == 1
    assert fallback_events[0].duration_s == 30


def test_fallback_sbp_variant_uses_sbp_column_and_90_threshold():
    times = [0, 30, 60, 90, 120]
    values = [100, 85, 80, 85, 100]
    df = _series(times, values, col=config.TRACK_SBP)
    events = labels.detect_fallback_sbp_events(df)
    assert len(events) == 1
    assert events[0].start_time == 30
    assert events[0].duration_s == 60


def test_first_event_time_returns_earliest_start_or_none():
    assert labels.first_event_time([]) is None
    e1 = labels.Event(start_time=100, end_time=160, duration_s=60)
    e2 = labels.Event(start_time=50, end_time=110, duration_s=60)
    assert labels.first_event_time([e1, e2]) == 50


def _drug_df(times_s, **tracks):
    data = {"Time": times_s}
    for name, vals in tracks.items():
        data[name] = vals
    return pd.DataFrame(data)


def test_event_is_bleeding_flavored_false_when_not_cohort_b():
    drug_df = _drug_df([0, 3600], **{config.DRUG_TRACKS[0]: [0.0, 0.0]})
    assert labels.event_is_bleeding_flavored(1800, op_start_s=0, is_cohort_b=False, drug_df=drug_df) is False


def test_event_is_bleeding_flavored_false_before_incision():
    drug_df = _drug_df([0, 3600], **{config.DRUG_TRACKS[0]: [0.0, 0.0]})
    assert labels.event_is_bleeding_flavored(100, op_start_s=500, is_cohort_b=True, drug_df=drug_df) is False


def test_event_is_bleeding_flavored_true_with_flat_vasopressor():
    track = config.VASOPRESSOR_RATE_TRACKS[0]
    times = list(range(0, 3600, 30))
    drug_df = _drug_df(times, **{track: [5.0] * len(times)})  # constant, no increase
    assert labels.event_is_bleeding_flavored(1800, op_start_s=0, is_cohort_b=True, drug_df=drug_df) is True


def test_event_is_bleeding_flavored_false_with_recent_vasopressor_increase():
    track = config.VASOPRESSOR_RATE_TRACKS[0]
    times = [0, 1500, 1750]  # increase happens inside the 5-min lookback before t=1800
    drug_df = _drug_df(times, **{track: [0.0, 0.0, 8.0]})
    assert labels.event_is_bleeding_flavored(1800, op_start_s=0, is_cohort_b=True, drug_df=drug_df) is False


def test_event_is_bleeding_flavored_true_when_increase_is_outside_lookback():
    track = config.VASOPRESSOR_RATE_TRACKS[0]
    times = [0, 100, 1700]  # increase at t=100, well before the 5-min lookback window for t=1800
    drug_df = _drug_df(times, **{track: [0.0, 8.0, 8.0]})
    assert labels.event_is_bleeding_flavored(1800, op_start_s=0, is_cohort_b=True, drug_df=drug_df) is True


def test_detect_events_is_generic_and_config_driven():
    # Sanity: detect_events with explicit params matches detect_primary_events.
    times = [0, 30, 60, 90, 120, 150]
    values = [80, 75, 60, 55, 58, 80]
    df = _series(times, values)
    generic = labels.detect_events(
        df,
        pressure_col=config.TRACK_MAP,
        threshold_mmhg=config.EVENT_MAP_THRESHOLD_MMHG,
        min_duration_s=config.EVENT_SUSTAINED_DURATION_S,
    )
    assert generic == labels.detect_primary_events(df)
