#!/usr/bin/env python
"""Phase 4 Experiment 2: bleeding-flavored label (rules locked in
ACTIONS.md 2026-10-24, BEFORE this script was written).

Builds a new label (qualifying events only: after incision, Cohort B, no
vasopressor-rate/volatile-anesthetic increase in the preceding 5 min --
see labels.event_is_bleeding_flavored), runs the SAME 5-fold grouped CV
screening as scripts/04b_model_iteration.py (b2_alone vs stacked_b2_drift,
original_repro as a third reference point), and evaluates the test set
EXACTLY ONCE for this new task, disclosed as a post-hoc experiment,
reported separately from metrics.json / metrics_v2.json.

Decision rule: adopt stacked_b2_drift only if it beats b2_alone's CV
sensitivity by >=3pp at 1 FA/patient-hour, bootstrap-by-case 95% CI
excluding zero. If it doesn't: stop, no further feature engineering, and
report that result plainly.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import alarms, baselines, config, labels, metrics, models, vitaldb_io  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
COHORT_FINAL_PARQUET = ROOT / "data" / "interim" / "cohort.parquet"
WINDOWS_PARQUET = ROOT / "data" / "processed" / "windows.parquet"
METRICS_EXP2_JSON = ROOT / "artifacts" / "metrics_exp2_bleeding_label.json"

DECISION_MARGIN_PP = 3.0
N_FOLDS = 5
HORIZON_MIN = config.HORIZON_MIN_PRIMARY
PRIMARY_FA_TARGET = config.ALARM_OPERATING_POINT_FA_PER_PATIENT_HOUR

STACKED_B2_DRIFT_FEATURES = (
    "map",
    "hr_slope_5", "hr_slope_10", "hr_slope_15",
    "map_slope_5", "map_slope_10", "map_slope_15",
    "pp_slope_5", "pp_slope_10", "pp_slope_15",
    "shock_index", "shock_index_slope_5", "shock_index_slope_10", "shock_index_slope_15",
    "hr_drift", "map_drift", "pp_drift", "shock_index_drift",
)
CANDIDATES = {
    "original_repro": {"features": models.FEATURE_COLUMNS, "sex": True},
    "b2_alone": {"features": ("map",), "sex": False},
    "stacked_b2_drift": {"features": STACKED_B2_DRIFT_FEATURES, "sex": False},
}
LABEL_COL = "bleeding_label"


def classify_case_events(caseid: int, cases_df: pd.DataFrame, cohort_df: pd.DataFrame):
    cleaned = vitaldb_io.load_and_clean_case(int(caseid))
    drug_df = vitaldb_io.load_drug_tracks(int(caseid))
    row = cases_df.loc[cases_df[config.COL_CASEID] == caseid].iloc[0]
    op_start_s, op_end_s = float(row[config.COL_OPSTART]), float(row[config.COL_OPEND])
    op_window = cleaned[(cleaned["Time"] >= op_start_s) & (cleaned["Time"] <= op_end_s)]
    events = labels.detect_primary_events(op_window)
    is_cohort_b = bool(cohort_df.loc[cohort_df[config.COL_CASEID] == caseid, "cohort_b_final"].iloc[0])

    qualifying, disqualified = [], []
    for e in events:
        if labels.event_is_bleeding_flavored(e.start_time, op_start_s, is_cohort_b, drug_df):
            qualifying.append(e.start_time)
        else:
            disqualified.append(e.start_time)
    return qualifying, disqualified, op_end_s


def bleeding_label_for_t(t_s: float, op_end_s: float, qualifying: list, disqualified: list, horizon_min: float = HORIZON_MIN) -> float:
    horizon_end = t_s + horizon_min * 60.0
    if any(t_s < e <= horizon_end for e in qualifying):
        return 1.0
    if any(t_s < e <= horizon_end for e in disqualified):
        return float("nan")  # a disqualified (possibly confounded) event -- indeterminate, not negative
    if op_end_s - t_s < horizon_min * 60.0:
        return float("nan")  # right-censored, same as the original label's handling
    return 0.0


def build_bleeding_labels(windows_df: pd.DataFrame, caseids: list[int], cases_df: pd.DataFrame, cohort_df: pd.DataFrame) -> pd.Series:
    label = pd.Series(index=windows_df.index, dtype=float)
    event_counts = {"qualifying": 0, "disqualified": 0}
    for i, caseid in enumerate(caseids, start=1):
        qualifying, disqualified, op_end_s = classify_case_events(caseid, cases_df, cohort_df)
        event_counts["qualifying"] += len(qualifying)
        event_counts["disqualified"] += len(disqualified)
        case_mask = windows_df[config.COL_CASEID] == caseid
        label.loc[case_mask] = windows_df.loc[case_mask, "t_s"].apply(
            lambda t: bleeding_label_for_t(t, op_end_s, qualifying, disqualified)
        )
        if i % 100 == 0:
            print(f"  ... {i}/{len(caseids)} cases classified")
    print(f"  Qualifying events: {event_counts['qualifying']}, disqualified events: {event_counts['disqualified']}")
    return label


def feature_matrix(df: pd.DataFrame, feature_names: tuple, include_sex: bool) -> pd.DataFrame:
    X = df[list(feature_names)].copy()
    if include_sex:
        X["sex"] = models.encode_sex(df["sex"])
    return X


def fit_logistic_candidate(train_df: pd.DataFrame, spec: dict):
    X = feature_matrix(train_df, spec["features"], spec["sex"])
    y = train_df[LABEL_COL]
    return models.fit_logistic(X, y)


def oof_predictions(dev_all_df: pd.DataFrame, dev_fit_df: pd.DataFrame, folds: list[list[int]], spec: dict) -> pd.Series:
    oof = pd.Series(index=dev_all_df.index, dtype=float)
    for fold_ids in folds:
        fold_set = set(fold_ids)
        train_fit = dev_fit_df[~dev_fit_df[config.COL_CASEID].isin(fold_set)]
        held_out_all = dev_all_df[dev_all_df[config.COL_CASEID].isin(fold_set)]
        if len(held_out_all) == 0 or train_fit[LABEL_COL].nunique() < 2:
            continue
        fitted = fit_logistic_candidate(train_fit, spec)
        X_held = feature_matrix(held_out_all, spec["features"], spec["sex"])
        oof.loc[held_out_all.index] = fitted.predict_proba(X_held)[:, 1]
    return oof


def main() -> None:
    print("=== Phase 4 Experiment 2: bleeding-flavored label ===")
    cases_df = vitaldb_io.load_case_table()
    cohort_df = pd.read_parquet(COHORT_FINAL_PARQUET)
    windows_df = pd.read_parquet(WINDOWS_PARQUET)

    all_caseids = sorted(windows_df[config.COL_CASEID].unique().tolist())
    split = models.split_cases(cases_df, all_caseids)
    dev_ids = [c for c in all_caseids if split[c] in ("train", "val")]
    test_ids = [c for c in all_caseids if split[c] == "test"]
    print(f"Dev: {len(dev_ids)} cases, test (locked, touched once below): {len(test_ids)} cases")

    print("\nClassifying events (qualifying vs. disqualified) and building the new label, dev set...")
    dev_all_df = windows_df[windows_df[config.COL_CASEID].isin(dev_ids)].copy()
    dev_all_df[LABEL_COL] = build_bleeding_labels(dev_all_df, dev_ids, cases_df, cohort_df)
    dev_fit_df = dev_all_df[dev_all_df[LABEL_COL].notna()]
    print(f"Dev windows with a known bleeding label: {len(dev_fit_df)} / {len(dev_all_df)} "
          f"(positive rate {dev_fit_df[LABEL_COL].mean():.4f})")

    print("\nComputing real event lists (ALL primary events, for alert scoring) for dev cases...")
    case_events = {}
    for caseid in dev_ids:
        cleaned = vitaldb_io.load_and_clean_case(int(caseid))
        row = cases_df.loc[cases_df[config.COL_CASEID] == caseid].iloc[0]
        op_window = cleaned[(cleaned["Time"] >= row[config.COL_OPSTART]) & (cleaned["Time"] <= row[config.COL_OPEND])]
        case_events[caseid] = sorted(e.start_time for e in labels.detect_primary_events(op_window))
    # Sensitivity here is measured against QUALIFYING events only (what the label targets).
    qualifying_events = {}
    for caseid in dev_ids:
        q, _, _ = classify_case_events(caseid, cases_df, cohort_df)
        qualifying_events[caseid] = q

    folds = models.grouped_kfold_by_subject(cases_df, dev_ids, n_folds=N_FOLDS)
    print(f"\nGrouped {N_FOLDS}-fold CV: fold sizes = {[len(f) for f in folds]}")

    cv_results = {}
    for name, spec in CANDIDATES.items():
        print(f"\n--- Candidate: {name} ({len(spec['features'])} features{'+sex' if spec['sex'] else ''}) ---")
        oof = oof_predictions(dev_all_df, dev_fit_df, folds, spec)
        risk_col = f"oof_{name}"
        dev_all_df[risk_col] = oof

        oof_fit_mask = dev_all_df[LABEL_COL].notna() & dev_all_df[risk_col].notna()
        auprc = metrics.auroc_auprc_brier(dev_all_df.loc[oof_fit_mask, LABEL_COL], dev_all_df.loc[oof_fit_mask, risk_col])

        case_dfs = {cid: g for cid, g in dev_all_df.groupby(config.COL_CASEID)}
        thr, fa_rate = alarms.find_threshold_for_target_fa_rate(case_dfs, qualifying_events, risk_col, PRIMARY_FA_TARGET, horizon_min=HORIZON_MIN)
        case_alerts = {cid: alarms.generate_case_alerts(case_dfs[cid], risk_col, thr) for cid in dev_ids if cid in case_dfs}
        sens_result = metrics.event_sensitivity_and_lead_times(qualifying_events, case_alerts, dev_ids, HORIZON_MIN)
        sens = sens_result["sensitivity"]
        print(f"  OOF AUPRC={auprc['auprc']:.4f}  CV sensitivity@{PRIMARY_FA_TARGET}FA/hr={sens:.4f} "
              f"(thr={thr:.4f}, actual FA={fa_rate:.3f}/hr, n_qualifying_events={sens_result['n_events']})")
        cv_results[name] = {"auprc": auprc, "threshold": thr, "fa_rate": fa_rate, "sensitivity": sens, "risk_col": risk_col}

    print(f"\n=== Decision rule: stacked_b2_drift must beat b2_alone's CV sensitivity ({cv_results['b2_alone']['sensitivity']:.4f}) "
          f"by >= {DECISION_MARGIN_PP}pp, CI excludes zero ===")
    case_dfs = {cid: g for cid, g in dev_all_df.groupby(config.COL_CASEID)}
    alerts_stacked = {cid: alarms.generate_case_alerts(case_dfs[cid], cv_results["stacked_b2_drift"]["risk_col"], cv_results["stacked_b2_drift"]["threshold"]) for cid in case_dfs}
    alerts_b2 = {cid: alarms.generate_case_alerts(case_dfs[cid], cv_results["b2_alone"]["risk_col"], cv_results["b2_alone"]["threshold"]) for cid in case_dfs}

    def diff_fn(sample_ids):
        sens_stacked = metrics.event_sensitivity_and_lead_times(qualifying_events, alerts_stacked, sample_ids, HORIZON_MIN)["sensitivity"]
        sens_b2 = metrics.event_sensitivity_and_lead_times(qualifying_events, alerts_b2, sample_ids, HORIZON_MIN)["sensitivity"]
        if np.isnan(sens_stacked) or np.isnan(sens_b2):
            return float("nan")
        return sens_stacked - sens_b2

    ci = metrics.bootstrap_ci_by_case(dev_ids, diff_fn, n_resamples=config.BOOTSTRAP_N_RESAMPLES)
    gain_pp = ci["point"] * 100
    drift_wins = gain_pp >= DECISION_MARGIN_PP and ci["ci_low"] > 0
    print(f"  stacked_b2_drift vs b2_alone: gain={gain_pp:+.2f}pp, 95% CI=[{ci['ci_low']*100:+.2f}, {ci['ci_high']*100:+.2f}]pp")
    print(f"\n=> Drift {'WINS' if drift_wins else 'DOES NOT WIN'}. "
          f"{'Adopting stacked_b2_drift for this task.' if drift_wins else 'Stopping here, per the pre-registered rule -- no further feature engineering.'}")

    output = {
        "cv_results": {n: {k: v for k, v in r.items() if k != "risk_col"} for n, r in cv_results.items()},
        "decision": {"gain_pp": gain_pp, "ci": ci, "drift_wins": bool(drift_wins)},
        "dev_label_positive_rate": float(dev_fit_df[LABEL_COL].mean()),
        "dev_n_qualifying_events": sum(len(v) for v in qualifying_events.values()),
        "dev_n_disqualified_events": sum(len(case_events[c]) for c in dev_ids) - sum(len(v) for v in qualifying_events.values()),
    }

    if drift_wins:
        winner_name, winner_spec = "stacked_b2_drift", CANDIDATES["stacked_b2_drift"]
    else:
        winner_name, winner_spec = "b2_alone", CANDIDATES["b2_alone"]

    print(f"\n=== Evaluating '{winner_name}' against the TEST SET, EXACTLY ONCE, for this new task ===")
    train_ids = [c for c in all_caseids if split[c] == "train"]
    val_ids = [c for c in all_caseids if split[c] == "val"]
    train_all_df = windows_df[windows_df[config.COL_CASEID].isin(train_ids)].copy()
    val_all_df = windows_df[windows_df[config.COL_CASEID].isin(val_ids)].copy()
    test_all_df = windows_df[windows_df[config.COL_CASEID].isin(test_ids)].copy()

    print("Building bleeding labels for train/val/test...")
    train_all_df[LABEL_COL] = build_bleeding_labels(train_all_df, train_ids, cases_df, cohort_df)
    val_all_df[LABEL_COL] = build_bleeding_labels(val_all_df, val_ids, cases_df, cohort_df)
    test_all_df[LABEL_COL] = build_bleeding_labels(test_all_df, test_ids, cases_df, cohort_df)

    train_fit = train_all_df[train_all_df[LABEL_COL].notna()]
    val_fit = val_all_df[val_all_df[LABEL_COL].notna()]
    if train_fit[LABEL_COL].nunique() < 2:
        print("Not enough positive examples in train to fit a final model for this label -- reporting CV result only.")
        METRICS_EXP2_JSON.write_text(json.dumps(output, indent=2, default=lambda x: None))
        print(f"Saved {METRICS_EXP2_JSON}")
        return

    fitted = fit_logistic_candidate(train_fit, winner_spec)
    calibrated = models.calibrate_on_validation(fitted, feature_matrix(val_fit, winner_spec["features"], winner_spec["sex"]), val_fit[LABEL_COL])
    val_all_df["model_risk"] = calibrated.predict_proba(feature_matrix(val_all_df, winner_spec["features"], winner_spec["sex"]))[:, 1]
    test_all_df["model_risk"] = calibrated.predict_proba(feature_matrix(test_all_df, winner_spec["features"], winner_spec["sex"]))[:, 1]

    test_qualifying_events = {}
    for caseid in test_ids:
        q, _, _ = classify_case_events(caseid, cases_df, cohort_df)
        test_qualifying_events[caseid] = q
    val_qualifying_events = {}
    for caseid in val_ids:
        q, _, _ = classify_case_events(caseid, cases_df, cohort_df)
        val_qualifying_events[caseid] = q

    case_dfs_val = {cid: g for cid, g in val_all_df.groupby(config.COL_CASEID)}
    thr, val_fa = alarms.find_threshold_for_target_fa_rate(case_dfs_val, val_qualifying_events, "model_risk", PRIMARY_FA_TARGET, horizon_min=HORIZON_MIN)

    case_dfs_test = {cid: g for cid, g in test_all_df.groupby(config.COL_CASEID)}
    case_alerts_test = {cid: alarms.generate_case_alerts(case_dfs_test[cid], "model_risk", thr) for cid in test_ids if cid in case_dfs_test}
    sens_result = metrics.event_sensitivity_and_lead_times(test_qualifying_events, case_alerts_test, test_ids, HORIZON_MIN)
    lead_summary = metrics.lead_time_summary(sens_result["lead_times_s"])
    fa_rate = alarms.false_alarm_rate_for_threshold(case_dfs_test, test_qualifying_events, "model_risk", thr, horizon_min=HORIZON_MIN)
    secondary = metrics.auroc_auprc_brier(test_all_df[LABEL_COL], test_all_df["model_risk"])

    print(f"Test (winner={winner_name}): sensitivity={sens_result['sensitivity']:.3f} "
          f"({sens_result['n_detected']}/{sens_result['n_events']} qualifying events), "
          f"lead_median_min={lead_summary['median_s']/60:.2f}, FA/hr={fa_rate:.3f}")
    print(f"Test AUROC/AUPRC/Brier: {secondary}")

    output["winner"] = winner_name
    output["test_results"] = {
        "threshold": thr, "val_fa_rate": val_fa,
        "sensitivity": sens_result["sensitivity"], "n_events": sens_result["n_events"], "n_detected": sens_result["n_detected"],
        "lead_time": lead_summary, "fa_rate_per_hour": fa_rate, "secondary_metrics": secondary,
    }
    METRICS_EXP2_JSON.write_text(json.dumps(output, indent=2, default=lambda x: None))
    print(f"\nSaved {METRICS_EXP2_JSON}")


if __name__ == "__main__":
    main()
