"""Alarm logic: threshold + refractory period + suppression rules, and the
operating-point threshold search used by both the model and the tuned
baselines (B2-B4).

Phase 4 (PLAN.md Section 4, Section 7.3-7.4, Section 7.6).
Alert when risk >= the operating-point threshold; refractory period
config.ALARM_REFRACTORY_MIN; suppressed if MAP already < 65 or missing
fraction exceeds config.INSUFFICIENT_DATA_MISSING_FRACTION. Operates on
one case's rows at a time, each already a window from features.py, so
"MAP already < 65" and "missing fraction" are read straight off that
window's own feature columns (map, missing_fraction) -- no new network or
recomputation. The same function generates alerts for the model's
calibrated risk AND for every tuned baseline, since a baseline's "risk" is
just whatever scalar features.py/baselines.py produced for that row.

Monitored patient-hours (the false-alarm-rate denominator, PLAN.md 7.6)
is operationalized as (number of window rows) * PREDICTION_STRIDE_MIN/60:
windows.parquet's rows are already the 1-per-minute prediction times left
after the exclusion rule (PLAN.md 7.2), i.e. exactly "monitored time,
exclusion windows excluded" at the row level.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def generate_case_alerts(
    case_df: pd.DataFrame,
    risk_col: str,
    threshold: float,
    refractory_min: float = config.ALARM_REFRACTORY_MIN,
    missing_fraction_cutoff: float = config.INSUFFICIENT_DATA_MISSING_FRACTION,
    time_col: str = "t_s",
) -> list[float]:
    """Alert times (seconds) for one case, in time order. A row alerts if
    risk >= threshold, missing_fraction <= cutoff, map >= EVENT_MAP_THRESHOLD_MMHG
    (defensive -- windows.parquet should already exclude MAP<65 rows), and
    no alert fired within the last refractory_min minutes for this case.
    """
    d = case_df.sort_values(time_col)
    t = d[time_col].to_numpy(dtype=float)
    risk = d[risk_col].to_numpy(dtype=float)
    missing_fraction = d["missing_fraction"].to_numpy(dtype=float) if "missing_fraction" in d.columns else np.zeros(len(d))
    map_ = d["map"].to_numpy(dtype=float) if "map" in d.columns else np.full(len(d), np.inf)

    eligible = (
        ~np.isnan(risk) & (risk >= threshold)
        & (missing_fraction <= missing_fraction_cutoff)
        & (map_ >= config.EVENT_MAP_THRESHOLD_MMHG)
    )

    alerts: list[float] = []
    last_alert_s: float | None = None
    refractory_s = refractory_min * 60.0
    for t_s, ok in zip(t, eligible):
        if not ok:
            continue
        if last_alert_s is not None and (t_s - last_alert_s) < refractory_s:
            continue
        alerts.append(t_s)
        last_alert_s = t_s
    return alerts


def monitored_patient_hours(windows_df: pd.DataFrame) -> float:
    return len(windows_df) * config.PREDICTION_STRIDE_MIN / 60.0


def alert_is_false(alert_s: float, event_starts_s: list[float], horizon_min: float) -> bool:
    """PLAN.md 7.5: an alert is true if an event starts in (alert, alert+H]."""
    horizon_end_s = alert_s + horizon_min * 60.0
    return not any(alert_s < e <= horizon_end_s for e in event_starts_s)


def false_alarm_rate_for_threshold(
    case_dfs: dict[int, pd.DataFrame],
    case_events: dict[int, list[float]],
    risk_col: str,
    threshold: float,
    horizon_min: float = config.HORIZON_MIN_PRIMARY,
    refractory_min: float = config.ALARM_REFRACTORY_MIN,
    time_col: str = "t_s",
    caseids: list[int] | None = None,
) -> float:
    """False alarms / monitored patient-hours, at one candidate threshold.

    caseids defaults to every key in case_dfs (each counted once). Pass an
    explicit list -- e.g. a bootstrap resample, which may repeat a caseid
    several times -- to have each occurrence contribute its own alerts and
    monitored hours; a dict can't represent that repetition, so building
    one from a resampled list first would silently under-count it.
    """
    if caseids is None:
        caseids = list(case_dfs.keys())
    total_false = 0
    total_hours = 0.0
    for caseid in caseids:
        if caseid not in case_dfs:
            continue
        df = case_dfs[caseid]
        alerts = generate_case_alerts(df, risk_col, threshold, refractory_min=refractory_min, time_col=time_col)
        events = case_events.get(caseid, [])
        total_false += sum(alert_is_false(a, events, horizon_min) for a in alerts)
        total_hours += monitored_patient_hours(df)
    return total_false / total_hours if total_hours > 0 else float("inf")


def find_threshold_for_target_fa_rate(
    case_dfs: dict[int, pd.DataFrame],
    case_events: dict[int, list[float]],
    risk_col: str,
    target_fa_per_hour: float,
    horizon_min: float = config.HORIZON_MIN_PRIMARY,
    refractory_min: float = config.ALARM_REFRACTORY_MIN,
    time_col: str = "t_s",
    n_candidates: int = 200,
) -> tuple[float, float]:
    """Search candidate thresholds (quantiles of the observed risk
    distribution, so the search always covers the achievable range) for
    the lowest threshold whose false-alarm rate is <= target_fa_per_hour.
    Returns (threshold, actual_fa_rate_at_that_threshold). If no threshold
    achieves the target (even the highest observed value exceeds it),
    returns the highest candidate and its (still too high) FA rate.
    """
    all_risk = pd.concat([df[risk_col] for df in case_dfs.values()]).dropna()
    candidates = np.unique(np.quantile(all_risk, np.linspace(0.0, 1.0, n_candidates)))
    # Append a threshold strictly above every observed value, so "never
    # alert" (FA rate 0) is always a reachable candidate.
    candidates = np.append(candidates, candidates.max() + 1.0)
    candidates = np.sort(candidates)  # lowest threshold (most alerts, highest FA rate) first

    # FA rate is non-increasing as the threshold rises; walk up from the most
    # sensitive threshold and take the first one that already meets the
    # target -- the lowest threshold (most sensitive) satisfying the FA cap.
    best = (candidates[-1], float("inf"))
    for thr in candidates:
        fa_rate = false_alarm_rate_for_threshold(
            case_dfs, case_events, risk_col, thr, horizon_min=horizon_min, refractory_min=refractory_min, time_col=time_col,
        )
        best = (thr, fa_rate)
        if fa_rate <= target_fa_per_hour:
            return float(thr), float(fa_rate)
    return float(best[0]), float(best[1])
