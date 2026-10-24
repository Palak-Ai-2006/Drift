"""Event detector (the label) -- PLAN.md Section 7.1, Phase 2.

Primary/headline event: pressure < threshold sustained for >= min_duration_s;
event starts at the first sample of the run (not the midpoint, not when it's
confirmed sustained). Also supports the two secondary/sensitivity variants
(SBP<90, 30s duration) via the same generic function, per the Oct 24 decision
that these are reported separately and only become primary via the one-time
documented fallback switch in config.py.

NaN samples are treated as "condition not met" (they neither extend nor
satisfy a run) -- missing data should never manufacture or hide an event.
Duration is measured as actual elapsed time between the first and last
sample of a run, so irregular sampling is handled correctly (no assumption
of a fixed interval).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import config


@dataclass(frozen=True)
class Event:
    start_time: float
    end_time: float
    duration_s: float


def detect_events(
    df: pd.DataFrame,
    pressure_col: str,
    threshold_mmhg: float,
    min_duration_s: float,
    time_col: str = "Time",
) -> list[Event]:
    """Detect runs where df[pressure_col] < threshold_mmhg, sustained for at
    least min_duration_s (elapsed time between the run's first and last
    sample). Returns one Event per qualifying run, event.start_time = the
    first sample's time.
    """
    d = df.sort_values(time_col).reset_index(drop=True)
    times = d[time_col].to_numpy(dtype=float)
    values = d[pressure_col].to_numpy(dtype=float)
    below = values < threshold_mmhg  # NaN < x is always False -- NaN breaks runs

    events: list[Event] = []
    n = len(d)
    i = 0
    while i < n:
        if not below[i]:
            i += 1
            continue
        j = i
        while j < n and below[j]:
            j += 1
        # run is [i, j)
        run_start_t = times[i]
        run_end_t = times[j - 1]
        duration = run_end_t - run_start_t
        if duration >= min_duration_s:
            events.append(Event(start_time=run_start_t, end_time=run_end_t, duration_s=duration))
        i = j
    return events


def detect_primary_events(df: pd.DataFrame, time_col: str = "Time") -> list[Event]:
    """Primary/headline definition: MAP < 65 mmHg sustained >= 60s."""
    return detect_events(
        df,
        pressure_col=config.TRACK_MAP,
        threshold_mmhg=config.EVENT_MAP_THRESHOLD_MMHG,
        min_duration_s=config.EVENT_SUSTAINED_DURATION_S,
        time_col=time_col,
    )


def detect_fallback_short_duration_events(df: pd.DataFrame, time_col: str = "Time") -> list[Event]:
    """Secondary/sensitivity: MAP < 65 mmHg sustained >= 30s. Never the
    headline unless config.EVENT_DEFINITION_FALLBACK_APPLIED is set True as
    the one-time, pre-training switch (Oct 24 decision)."""
    return detect_events(
        df,
        pressure_col=config.TRACK_MAP,
        threshold_mmhg=config.EVENT_MAP_THRESHOLD_MMHG,
        min_duration_s=config.EVENT_FALLBACK_DURATION_S,
        time_col=time_col,
    )


def detect_fallback_sbp_events(df: pd.DataFrame, time_col: str = "Time") -> list[Event]:
    """Secondary/sensitivity: SBP < 90 mmHg sustained >= 60s. Never the
    headline unless explicitly switched per the Oct 24 decision."""
    return detect_events(
        df,
        pressure_col=config.TRACK_SBP,
        threshold_mmhg=config.EVENT_FALLBACK_SBP_THRESHOLD_MMHG,
        min_duration_s=config.EVENT_SUSTAINED_DURATION_S,
        time_col=time_col,
    )


def first_event_time(events: list[Event]) -> float | None:
    if not events:
        return None
    return min(e.start_time for e in events)


# ---------------------------------------------------------------------------
# Phase 4 Experiment 2: "bleeding-flavored" event qualification. Rules
# locked in ACTIONS.md (2026-10-24) BEFORE this was written. A real primary
# event additionally qualifies as bleeding-flavored if it occurs after
# incision, in a Cohort B case, with no vasopressor-rate or volatile-
# anesthetic increase in the preceding lookback_min minutes. Deliberately
# never references HR/PP/shock_index -- only MAP (the event itself),
# timing, cohort membership, and drug tracks -- so HR-based features can't
# trivially predict this label.
# ---------------------------------------------------------------------------
def _value_at_or_before(df: pd.DataFrame, value_col: str, t_s: float, time_col: str = "Time") -> float:
    d = df[df[time_col] <= t_s]
    if len(d) == 0:
        return float("nan")
    return float(d.sort_values(time_col).iloc[-1][value_col])


def event_is_bleeding_flavored(
    event_start_s: float,
    op_start_s: float,
    is_cohort_b: bool,
    drug_df: pd.DataFrame,
    drug_tracks: tuple[str, ...] = config.DRUG_TRACKS,
    lookback_min: float = config.EXCLUDE_IF_RECENT_MAP_LOW_LOOKBACK_MIN,
    time_col: str = "Time",
) -> bool:
    """True if a real primary event qualifies as bleeding-flavored per the
    ACTIONS.md Experiment 2 rules. drug_df is vitaldb_io.load_drug_tracks()'s
    output (NaN already filled with 0 -- "not currently running")."""
    if not is_cohort_b:
        return False
    if event_start_s <= op_start_s:
        return False
    for track in drug_tracks:
        if track not in drug_df.columns:
            continue
        now = _value_at_or_before(drug_df, track, event_start_s, time_col)
        before = _value_at_or_before(drug_df, track, event_start_s - lookback_min * 60.0, time_col)
        if pd.notna(now) and pd.notna(before) and now > before:
            return False  # a vasopressor/anesthetic increase in the lookback window disqualifies it
    return True
