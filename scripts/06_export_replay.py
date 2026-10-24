#!/usr/bin/env python
"""Phase 6.1: select replay examples from the TEST SET, export causal risk
and raw-vitals excerpts to web/data/replay_cases.js and web/data/model_meta.js.

Uses the shipped model (b2_alone: MAP only, the v2 recipe) with its
already-fitted weights and already-chosen threshold -- the same model and
threshold used throughout Phase 4 round 3's holdout evaluation, no new
fitting or tuning here.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import alarms, config, labels, models, replay, vitaldb_io  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
COHORT_FINAL_PARQUET = ROOT / "data" / "interim" / "cohort.parquet"
WINDOWS_PARQUET = ROOT / "data" / "processed" / "windows.parquet"
METRICS_V2_JSON = ROOT / "artifacts" / "metrics_v2.json"
REPLAY_CASES_JS = ROOT / "web" / "data" / "replay_cases.js"
MODEL_META_JS = ROOT / "web" / "data" / "model_meta.js"

PRIMARY_LABEL_COL = f"label_h{config.HORIZON_MIN_PRIMARY}"
KIND_TITLES = {
    "best": "Best example", "typical": "Typical example", "miss": "Miss",
    "false_alarm": "False alarm", "insufficient": "Insufficient data",
}


def build_case_events(caseids, cases_df):
    out = {}
    for caseid in caseids:
        cleaned = vitaldb_io.load_and_clean_case(int(caseid))
        row = cases_df.loc[cases_df[config.COL_CASEID] == caseid].iloc[0]
        op_window = cleaned[(cleaned["Time"] >= row[config.COL_OPSTART]) & (cleaned["Time"] <= row[config.COL_OPEND])]
        events = labels.detect_primary_events(op_window)
        out[caseid] = sorted(e.start_time for e in events)
    return out


def _nearest_to_anchor(values: list[float], start_s: float, end_s: float, anchor_s: float) -> float | None:
    """The in-range value closest to anchor_s -- NOT the earliest in range.
    An excerpt can contain more than one real event/alert (events cluster);
    picking "earliest in window" would silently substitute an unrelated
    nearby event for the one this example was actually selected to show."""
    in_range = [v for v in values if start_s <= v <= end_s]
    if not in_range:
        return None
    return min(in_range, key=lambda v: abs(v - anchor_s))


def event_in_window(events: list[float], start_s: float, end_s: float, anchor_s: float) -> float | None:
    return _nearest_to_anchor(events, start_s, end_s, anchor_s)


def alert_in_window(alerts: list[float], start_s: float, end_s: float, anchor_s: float) -> float | None:
    return _nearest_to_anchor(alerts, start_s, end_s, anchor_s)


def export_case(pick: dict, cases_df, case_events, case_alerts, windows_by_case, dest_dir) -> dict:
    caseid, kind, anchor_s = pick["caseid"], pick["kind"], pick["anchor_s"]
    cleaned = vitaldb_io.load_and_clean_case(int(caseid))

    excerpt_start_s = anchor_s - config.REPLAY_EXCERPT_BEFORE_EVENT_MIN * 60.0
    excerpt_end_s = anchor_s + config.REPLAY_EXCERPT_AFTER_EVENT_MIN * 60.0
    excerpt = cleaned[(cleaned["Time"] >= excerpt_start_s) & (cleaned["Time"] <= excerpt_end_s)].sort_values("Time")

    t = excerpt["Time"].to_numpy()
    hr, sbp, dbp, map_ = (excerpt[config.TRACK_HR].to_numpy(), excerpt[config.TRACK_SBP].to_numpy(),
                           excerpt[config.TRACK_DBP].to_numpy(), excerpt[config.TRACK_MAP].to_numpy())
    pp = sbp - dbp
    si = hr / sbp
    present = excerpt[list(config.REQUIRED_NUMERIC_TRACKS)].notna().all(axis=1).to_numpy()
    missing = (~present).astype(int)

    wdf = windows_by_case.get(caseid)
    if wdf is not None:
        in_excerpt = wdf[(wdf["t_s"] >= excerpt_start_s) & (wdf["t_s"] <= excerpt_end_s)].sort_values("t_s")
        risk_t = in_excerpt["t_s"].to_numpy()
        risk = in_excerpt["model_risk"].to_numpy()
    else:
        risk_t, risk = np.array([]), np.array([])

    events, alerts = case_events.get(caseid, []), case_alerts.get(caseid, [])

    if kind in ("best", "typical"):
        # Must match replay._lead_time_for_event's exact definition (earliest
        # qualifying alert -> max lead time) -- the same rule that ranked
        # this pick as best/typical in the first place. Using "nearest
        # alert in the excerpt" here could silently pick a different,
        # later-but-still-qualifying alert and misstate the lead time.
        event_t = anchor_s
        qualifying = [a for a in alerts if a < event_t <= a + config.HORIZON_MIN_PRIMARY * 60.0]
        alert_t = min(qualifying) if qualifying else None
    elif kind == "miss":
        event_t = anchor_s
        alert_t = None  # by definition no qualifying alert exists; don't show an unrelated nearby one
    elif kind == "false_alarm":
        alert_t = anchor_s
        event_t = event_in_window(events, excerpt_start_s, excerpt_end_s, anchor_s)
    else:  # insufficient -- anchor_s is not a real event/alert, just informational context
        event_t = event_in_window(events, excerpt_start_s, excerpt_end_s, anchor_s)
        alert_t = alert_in_window(alerts, excerpt_start_s, excerpt_end_s, anchor_s)

    lead_s = (event_t - alert_t) if (event_t is not None and alert_t is not None and alert_t < event_t) else None

    map_at_alert = None
    if alert_t is not None:
        idx = (np.abs(t - alert_t)).argmin()
        map_at_alert = float(map_[idx])

    def _clean(arr):
        return [None if (v != v) else round(float(v), 1) for v in arr]  # v != v is the NaN check

    return {
        "id": f"{caseid}_{kind}",
        "caseid": int(caseid),
        "kind": kind,
        "title": KIND_TITLES[kind],
        "excerpt_start_s": float(excerpt_start_s),
        "dt_s": config.REPLAY_EXPORT_RESOLUTION_S,
        "t": [float(x) for x in t],
        "hr": _clean(hr), "sbp": _clean(sbp), "dbp": _clean(dbp), "map": _clean(map_), "pp": _clean(pp), "si": _clean(si),
        "missing": [int(x) for x in missing],
        "risk_t": [float(x) for x in risk_t],
        "risk": [round(float(x), 4) for x in risk],
        "alert_t": alert_t,
        "standard_alarm_t": event_t,
        "event_t": event_t,
        "top_features_at_alert": replay.top_features_at_alert(map_at_alert) if map_at_alert is not None else [],
        "verdict": replay.verdict_text(kind, lead_s, event_t, pick.get("is_true_insufficient", True)),
        "is_true_insufficient": pick.get("is_true_insufficient"),
    }


def main() -> None:
    print("=== Phase 6.1: replay export ===")
    cases_df = vitaldb_io.load_case_table()
    cohort_df = pd.read_parquet(COHORT_FINAL_PARQUET)
    windows_df = pd.read_parquet(WINDOWS_PARQUET)

    all_caseids = sorted(windows_df[config.COL_CASEID].unique().tolist())
    split = models.split_cases(cases_df, all_caseids)
    test_ids = [c for c in all_caseids if split[c] == "test"]
    train_ids = [c for c in all_caseids if split[c] == "train"]
    val_ids = [c for c in all_caseids if split[c] == "val"]
    print(f"Test set: {len(test_ids)} cases")

    train_fit = windows_df[windows_df[config.COL_CASEID].isin(train_ids) & windows_df[PRIMARY_LABEL_COL].notna()]
    val_fit = windows_df[windows_df[config.COL_CASEID].isin(val_ids) & windows_df[PRIMARY_LABEL_COL].notna()]
    fitted = models.fit_logistic(train_fit[["map"]], train_fit[PRIMARY_LABEL_COL])
    calibrated = models.calibrate_on_validation(fitted, val_fit[["map"]], val_fit[PRIMARY_LABEL_COL])

    v2_meta = json.loads(METRICS_V2_JSON.read_text())
    threshold = v2_meta["val_operating_point"]["threshold"]

    test_all_df = windows_df[windows_df[config.COL_CASEID].isin(test_ids)].copy()
    test_all_df["model_risk"] = calibrated.predict_proba(test_all_df[["map"]])[:, 1]
    windows_by_case = {cid: g for cid, g in test_all_df.groupby(config.COL_CASEID)}

    print("Computing real events for test cases...")
    case_events = build_case_events(test_ids, cases_df)
    case_alerts = {cid: alarms.generate_case_alerts(windows_by_case[cid], "model_risk", threshold)
                   for cid in test_ids if cid in windows_by_case}

    print("Selecting replay cases...")
    picks = replay.select_replay_cases(test_all_df, case_events, case_alerts)
    for p in picks:
        print(f"  {p['kind']:12s} caseid={p['caseid']} anchor_s={p['anchor_s']:.0f}")

    print("\nExporting excerpts...")
    cases_export = [export_case(p, cases_df, case_events, case_alerts, windows_by_case, ROOT) for p in picks]

    REPLAY_CASES_JS.parent.mkdir(parents=True, exist_ok=True)
    REPLAY_CASES_JS.write_text(f"window.DRIFT_CASES = {json.dumps(cases_export, indent=2)};\n")
    size_mb = REPLAY_CASES_JS.stat().st_size / 1e6
    print(f"Saved {REPLAY_CASES_JS} ({size_mb:.2f} MB)")

    model_meta = {
        "alert_name": config.WORDING_ALERT_NAME,
        "threshold": threshold,
        "horizon_min": config.HORIZON_MIN_PRIMARY,
        "refractory_min": config.ALARM_REFRACTORY_MIN,
        "insufficient_data_missing_fraction": config.INSUFFICIENT_DATA_MISSING_FRACTION,
        "features": [{"name": "MAP", "display_name": "Mean arterial pressure", "explanation": "Current MAP, calibrated into a risk score. No other feature is used by the shipped model."}],
        "honesty_note": config.WORDING_METHOD_HONESTY_NOTE,
        "wording": {
            "monitoring_banner": config.WORDING_MONITORING_BANNER,
            "alert_banner": config.WORDING_ALERT_BANNER,
            "insufficient_data_banner": config.WORDING_INSUFFICIENT_DATA_BANNER,
            "standard_alarm_not_triggered": config.WORDING_STANDARD_ALARM_NOT_TRIGGERED,
            "standard_alarm_triggered": config.WORDING_STANDARD_ALARM_TRIGGERED,
            "selected_examples_note": config.WORDING_SELECTED_EXAMPLES_NOTE,
            "real_data_badge": config.WORDING_REAL_DATA_BADGE,
            "real_data_full": config.WORDING_REAL_DATA_FULL,
            "replay_banner_tmpl": config.WORDING_REPLAY_BANNER_TMPL,
            "footer": config.WORDING_FOOTER,
            "synthetic_badge": config.WORDING_SYNTHETIC_BADGE,
            "synthetic_banner": config.WORDING_SYNTHETIC_BANNER,
            "simulator_disclaimer": config.WORDING_SIMULATOR_DISCLAIMER,
        },
    }
    MODEL_META_JS.write_text(f"window.DRIFT_META = {json.dumps(model_meta, indent=2)};\n")
    print(f"Saved {MODEL_META_JS}")


if __name__ == "__main__":
    main()
