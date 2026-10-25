"""Replay case selection and causal risk export for the web demo.

Phase 6.1 (PLAN.md Section 6.1, Phase 6). Selects best/typical/miss/
false_alarm (+ insufficient-data if one exists) examples from the TEST SET
only. Risk values are computed causally offline (Adjustment A3) at each
prediction time using only data up to that time -- the values exported here
are read directly from windows.parquet's already-causal model_risk column
(features.compute_window_features re-filters to Time <= t by construction;
verified generally by tests/test_features.py's causality tests, and
specifically for these exported values by scripts/06b_replay_causality_check.py).

Honest-reframing note (round 3, 2026-10-24): the shipped model is
`b2_alone` (current MAP only, calibrated). "top_features_at_alert" below
therefore has exactly one entry -- MAP -- not config.REPLAY_TOP_FEATURES_N.
Padding it with unused features from a richer model that was tested and
didn't win would misrepresent what's actually driving the alert.

Selection rules (written here, documented in DATA_CARD.md):
- Best: the 2 detected events with the longest lead time (ties broken by
  lower missing_fraction at the alert -- "clean data").
- Typical: the 2 detected events with lead time closest to the median
  detected lead time.
- Miss: up to 2 events with no qualifying alert.
- False alarm: up to 2 alerts with no event in the next H minutes.
- Insufficient: a case where a persistently high share of its windows have
  missing_fraction > config.INSUFFICIENT_DATA_MISSING_FRACTION, if one exists.
Each category prefers a caseid not already used by an earlier category, for
variety; ties/ordering broken by caseid ascending, so selection is
deterministic and reproducible.
"""

from __future__ import annotations

import pandas as pd

from . import alarms, config, metrics


def _lead_time_for_event(event_start_s: float, alerts: list[float], horizon_min: float) -> float | None:
    qualifying = [a for a in alerts if a < event_start_s <= a + horizon_min * 60.0]
    if not qualifying:
        return None
    return event_start_s - min(qualifying)


def classify_events_and_alerts(
    case_events: dict[int, list[float]],
    case_alerts: dict[int, list[float]],
    horizon_min: float = config.HORIZON_MIN_PRIMARY,
) -> dict:
    """Per-case-and-instant classification used to pick replay examples.
    Returns {"detected": [...], "missed": [...], "false_alarms": [...]}."""
    detected, missed, false_alarms = [], [], []
    for caseid in set(case_events) | set(case_alerts):
        events = case_events.get(caseid, [])
        alerts = case_alerts.get(caseid, [])
        for e in sorted(events):
            lead_s = _lead_time_for_event(e, alerts, horizon_min)
            if lead_s is None:
                missed.append({"caseid": caseid, "event_s": e})
            else:
                alert_s = e - lead_s
                detected.append({"caseid": caseid, "event_s": e, "alert_s": alert_s, "lead_s": lead_s})
        for a in sorted(alerts):
            if alarms.alert_is_false(a, events, horizon_min):
                false_alarms.append({"caseid": caseid, "alert_s": a})
    return {"detected": detected, "missed": missed, "false_alarms": false_alarms}


def find_insufficient_data_case(windows_df: pd.DataFrame, min_share: float = 0.5) -> dict | None:
    """A case where at least min_share of its windows have
    missing_fraction > the insufficient-data cutoff, if one exists. If none
    does, falls back to the case with the HIGHEST such share -- "closest
    example" per PLAN.md Phase 6.1 ("if none exist in the test set, say so
    in the UI and docs and show the closest examples") -- with
    is_true_insufficient=False so the caller/UI can say so honestly.
    Returns {"caseid", "share", "is_true_insufficient"} or None if the
    windows_df is empty."""
    cutoff = config.INSUFFICIENT_DATA_MISSING_FRACTION
    share = windows_df.groupby(config.COL_CASEID)["missing_fraction"].apply(lambda s: (s > cutoff).mean())
    if len(share) == 0:
        return None
    qualifying = share[share >= min_share].sort_values(ascending=False)
    if len(qualifying):
        return {"caseid": int(qualifying.index[0]), "share": float(qualifying.iloc[0]), "is_true_insufficient": True}
    closest = share.sort_values(ascending=False)
    return {"caseid": int(closest.index[0]), "share": float(closest.iloc[0]), "is_true_insufficient": False}


def _missing_fraction_near(windows_df: pd.DataFrame, caseid: int, t_s: float) -> float:
    case_rows = windows_df[windows_df[config.COL_CASEID] == caseid]
    if len(case_rows) == 0:
        return float("nan")
    nearest = case_rows.iloc[(case_rows["t_s"] - t_s).abs().argsort()[:1]]
    return float(nearest["missing_fraction"].iloc[0])


def select_replay_cases(
    windows_df: pd.DataFrame,
    case_events: dict[int, list[float]],
    case_alerts: dict[int, list[float]],
    horizon_min: float = config.HORIZON_MIN_PRIMARY,
    per_type_target: int = config.REPLAY_CASES_PER_TYPE_TARGET,
) -> list[dict]:
    """Returns a list of {"caseid", "kind", "anchor_s"} picks, deterministic,
    preferring a not-yet-used caseid per category where possible."""
    classified = classify_events_and_alerts(case_events, case_alerts, horizon_min)
    used_caseids: set[int] = set()
    picks: list[dict] = []

    def _pick(candidates: list[dict], kind: str, anchor_key: str, key):
        nonlocal picks, used_caseids
        ranked = sorted(candidates, key=key)
        chosen, fallback = [], []
        for c in ranked:
            (chosen if c["caseid"] not in used_caseids else fallback).append(c)
        final = (chosen + fallback)[:per_type_target]
        for c in final:
            picks.append({"caseid": c["caseid"], "kind": kind, "anchor_s": c[anchor_key]})
            used_caseids.add(c["caseid"])

    detected = classified["detected"]
    for d in detected:
        d["missing_at_alert"] = _missing_fraction_near(windows_df, d["caseid"], d["alert_s"])
    _pick(detected, "best", "event_s", key=lambda d: (-d["lead_s"], d["missing_at_alert"], d["caseid"]))

    if detected:
        median_lead = pd.Series([d["lead_s"] for d in detected]).median()
        _pick(detected, "typical", "event_s", key=lambda d: (abs(d["lead_s"] - median_lead), d["caseid"]))

    _pick(classified["missed"], "miss", "event_s", key=lambda d: d["caseid"])
    _pick(classified["false_alarms"], "false_alarm", "alert_s", key=lambda d: d["caseid"])

    insufficient = find_insufficient_data_case(windows_df)
    if insufficient is not None:
        case_rows = windows_df[windows_df[config.COL_CASEID] == insufficient["caseid"]]
        anchor_s = float(case_rows["t_s"].median())
        picks.append({
            "caseid": insufficient["caseid"], "kind": "insufficient", "anchor_s": anchor_s,
            "is_true_insufficient": insufficient["is_true_insufficient"], "missing_share": insufficient["share"],
        })

    return picks


def top_features_at_alert(map_value: float) -> list[dict]:
    """The shipped model has exactly one feature (MAP) -- see module
    docstring. Honest, not padded to config.REPLAY_TOP_FEATURES_N."""
    return [{"name": "MAP", "value": round(map_value, 1), "direction": "below 65 mmHg" if map_value < config.EVENT_MAP_THRESHOLD_MMHG else "approaching 65 mmHg"}]


def verdict_text(kind: str, lead_s: float | None, standard_alarm_s: float | None, is_true_insufficient: bool = True) -> str:
    if kind == "miss":
        return f"Missed: the {config.WORDING_ALERT_NAME} gave no warning before this event."
    if kind == "false_alarm":
        return f"False alarm: pressure stayed above 65 for the next {config.HORIZON_MIN_PRIMARY} minutes."
    if kind == "insufficient":
        if is_true_insufficient:
            return "Not enough data to assess for part of this excerpt."
        return "No test case had persistently insufficient data -- this is the closest example, shown for completeness."
    lead_min = lead_s / 60.0 if lead_s is not None else None
    return f"Alert fired {lead_min:.1f} min before the standard alarm." if lead_min is not None else "Alert fired; the standard alarm never triggered in this excerpt."
