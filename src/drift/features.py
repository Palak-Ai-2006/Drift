"""Strictly causal feature computation and window labeling.

Phase 3 (PLAN.md Section 3, Section 7, Section 6B). Every feature at
prediction time t uses only samples at or before t (Adjustment A3 -- the
single most important integrity requirement). Enforced by construction:
compute_window_features() re-filters its input to Time <= t itself, so
passing it extra future rows changes nothing -- which is exactly what
tests/test_features.py's causality test checks.

Design choices PLAN.md Section 3 leaves unspecified, made explicit here
(not dataset facts -- model-design decisions, unlike column/track names,
which are never guessed):
- MAP std/min and the missing-fraction feature use the longest slope
  window (config.FEATURE_SLOPE_WINDOWS_MIN[-1] = 15 min) rather than a new
  undocumented window length.
- "Drift from patient baseline" is computed for HR, MAP, PP and shock
  index (the same four series the slope features use), as
  current_value - baseline_value.
- A window's label for horizon H is NaN (unknown, not "no event") when
  the case's monitored window ends before t + H -- the recording simply
  doesn't cover that horizon, so labeling it 0 would be wrong (right
  censoring), not an observed negative.
- Prediction times start only once the baseline window has closed (the
  baseline needs `exclusion_window_min` then `baseline_window_min` of
  data) and run to opend; the per-PLAN.md-7.2 exclusion (MAP < 65 in the
  previous 5 min) drops the row entirely rather than keeping it flagged,
  matching the plan's literal "excluded".
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config, labels


def _pulse_pressure(sbp: pd.Series, dbp: pd.Series) -> pd.Series:
    return sbp - dbp


def _shock_index(hr: pd.Series, sbp: pd.Series) -> pd.Series:
    return hr / sbp


def _derived_series(df: pd.DataFrame) -> pd.DataFrame:
    """HR, MAP, PP, shock_index as a tidy frame alongside Time -- the four
    series slopes/drift/std are computed over."""
    out = pd.DataFrame({"Time": df["Time"]})
    out["hr"] = df[config.TRACK_HR]
    out["map"] = df[config.TRACK_MAP]
    out["pp"] = _pulse_pressure(df[config.TRACK_SBP], df[config.TRACK_DBP])
    out["shock_index"] = _shock_index(df[config.TRACK_HR], df[config.TRACK_SBP])
    return out


def compute_patient_baseline(
    cleaned_df: pd.DataFrame,
    anesthesia_start_s: float,
    op_start_s: float = 0.0,
    exclusion_window_min: float = config.EXCLUSION_WINDOW_AFTER_ANESTHESIA_START_MIN,
    baseline_window_min: float = config.FEATURE_BASELINE_WINDOW_MIN,
    time_col: str = "Time",
) -> dict[str, float]:
    """Median of hr/map/pp/shock_index over the baseline window (the
    `baseline_window_min` minutes right after the exclusion window ends).
    This window always ends before any valid prediction time, so it never
    leaks future information into the drift features that use it.

    anestart is "from casestart" and can be negative (the arterial line --
    and so our four required tracks -- is often placed after anesthesia
    induction, so the recording frequently starts after anesthesia_start_s
    already). anesthesia_start_s + exclusion_window_min can then land before
    the recording even begins; clamping to max(..., op_start_s, 0) mirrors
    cohort.usable_monitored_minutes()'s own bounds (never start the window
    before the recording or the operation itself begins) instead of
    silently losing the case to an empty baseline window.
    """
    baseline_start_s = max(anesthesia_start_s + exclusion_window_min * 60.0, op_start_s, 0.0)
    baseline_end_s = baseline_start_s + baseline_window_min * 60.0
    window = cleaned_df[(cleaned_df[time_col] >= baseline_start_s) & (cleaned_df[time_col] < baseline_end_s)]
    derived = _derived_series(window)
    return {
        "hr": derived["hr"].median(),
        "map": derived["map"].median(),
        "pp": derived["pp"].median(),
        "shock_index": derived["shock_index"].median(),
        "baseline_end_s": baseline_end_s,
    }


def _slope_per_min(times_s: np.ndarray, values: np.ndarray) -> float:
    """Least-squares slope (value per minute) over non-NaN points. NaN if
    fewer than 2 usable points."""
    mask = ~np.isnan(values)
    if mask.sum() < 2:
        return float("nan")
    t_min = times_s[mask] / 60.0
    v = values[mask]
    if t_min.max() == t_min.min():
        return float("nan")
    slope, _ = np.polyfit(t_min, v, 1)
    return float(slope)


def has_recent_map_low(
    df_upto_t: pd.DataFrame,
    t_s: float,
    lookback_min: float = config.EXCLUDE_IF_RECENT_MAP_LOW_LOOKBACK_MIN,
    time_col: str = "Time",
) -> bool:
    """PLAN.md 7.2: exclude prediction times with MAP < 65 in the previous
    lookback_min minutes. Only ever looks at samples at or before t."""
    d = df_upto_t[df_upto_t[time_col] <= t_s]
    window = d[d[time_col] > t_s - lookback_min * 60.0]
    return bool((window[config.TRACK_MAP] < config.EVENT_MAP_THRESHOLD_MMHG).any())


def compute_window_features(
    df_upto_t: pd.DataFrame,
    t_s: float,
    baseline: dict[str, float],
    slope_windows_min: tuple[float, ...] = config.FEATURE_SLOPE_WINDOWS_MIN,
    current_window_min: float = config.FEATURE_SLOPE_WINDOWS_MIN[-1],
    time_col: str = "Time",
) -> dict | None:
    """The causal feature vector at one prediction time t. df_upto_t may
    contain rows after t -- this function always re-filters to Time <= t
    itself, so it is safe to pass it a case's whole cleaned table.

    Returns None if there is no sample at or before t (nothing to predict
    from yet).
    """
    d = df_upto_t[df_upto_t[time_col] <= t_s].sort_values(time_col)
    if len(d) == 0:
        return None

    current = d.iloc[-1]
    hr, sbp, dbp, map_ = (
        current[config.TRACK_HR], current[config.TRACK_SBP],
        current[config.TRACK_DBP], current[config.TRACK_MAP],
    )
    pp = sbp - dbp if pd.notna(sbp) and pd.notna(dbp) else float("nan")
    pp_over_sbp = pp / sbp if pd.notna(pp) and pd.notna(sbp) and sbp != 0 else float("nan")
    shock_index = hr / sbp if pd.notna(hr) and pd.notna(sbp) and sbp != 0 else float("nan")

    current_window = d[d[time_col] > t_s - current_window_min * 60.0]
    derived_current_window = _derived_series(current_window)
    times = current_window[time_col].to_numpy(dtype=float)

    feat: dict = {
        "hr": hr, "sbp": sbp, "dbp": dbp, "map": map_,
        "pp": pp, "pp_over_sbp": pp_over_sbp, "shock_index": shock_index,
        "map_std": derived_current_window["map"].std(),
        "map_min": derived_current_window["map"].min(),
    }

    expected_slots = max(round(current_window_min * 60.0 / 30.0), 1)
    all_four_present = current_window[list(config.REQUIRED_NUMERIC_TRACKS)].notna().all(axis=1)
    feat["missing_fraction"] = 1.0 - (all_four_present.sum() / expected_slots)

    for series_name in ("hr", "map", "pp", "shock_index"):
        values_full = derived_current_window[series_name].to_numpy(dtype=float)
        for w in slope_windows_min:
            window_mask = times > t_s - w * 60.0
            feat[f"{series_name}_slope_{int(w)}"] = _slope_per_min(times[window_mask], values_full[window_mask])
        feat[f"{series_name}_drift"] = (
            {"hr": hr, "map": map_, "pp": pp, "shock_index": shock_index}[series_name] - baseline[series_name]
            if t_s >= baseline["baseline_end_s"] else float("nan")
        )

    return feat


def build_case_windows(
    cleaned_df: pd.DataFrame,
    case_row: pd.Series,
    time_col: str = "Time",
) -> pd.DataFrame:
    """All labeled, causal feature rows for one case. Empty DataFrame if
    the case has no usable baseline (too little data right after the
    exclusion window to establish one)."""
    anesthesia_start_s = float(case_row[config.COL_ANESTART])
    op_start_s = float(case_row[config.COL_OPSTART])
    op_end_s = float(case_row[config.COL_OPEND])

    baseline = compute_patient_baseline(cleaned_df, anesthesia_start_s, op_start_s=op_start_s)
    if any(pd.isna(v) for k, v in baseline.items() if k != "baseline_end_s"):
        return pd.DataFrame()

    op_window = cleaned_df[(cleaned_df[time_col] >= op_start_s) & (cleaned_df[time_col] <= op_end_s)]
    events = labels.detect_primary_events(op_window, time_col=time_col)
    event_starts = sorted(e.start_time for e in events)

    t_start = max(baseline["baseline_end_s"], op_start_s)
    prediction_times = np.arange(t_start, op_end_s, config.PREDICTION_STRIDE_MIN * 60.0)

    rows = []
    for t_s in prediction_times:
        df_upto_t = cleaned_df[cleaned_df[time_col] <= t_s]
        if has_recent_map_low(df_upto_t, t_s):
            continue  # PLAN.md 7.2: excluded, not kept-and-flagged

        feat = compute_window_features(df_upto_t, t_s, baseline)
        if feat is None:
            continue

        feat["caseid"] = int(case_row[config.COL_CASEID])
        feat["t_s"] = t_s
        feat["age"] = case_row[config.COL_AGE]
        feat["sex"] = case_row[config.COL_SEX]
        feat["asa"] = case_row[config.COL_ASA]
        feat["emergency"] = case_row[config.COL_EMOP]

        for h in config.HORIZON_MIN_OPTIONS:
            horizon_end_s = t_s + h * 60.0
            if op_end_s < horizon_end_s:
                feat[f"label_h{h}"] = np.nan  # recording ends before the horizon closes -- unknown, not negative
            else:
                feat[f"label_h{h}"] = float(any(t_s < e_start <= horizon_end_s for e_start in event_starts))

        rows.append(feat)

    return pd.DataFrame(rows)
