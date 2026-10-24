#!/usr/bin/env python
"""Phase 4 iteration (post phase4-original, requested by the user after
seeing the honest MODEL_CARD.md result that logistic didn't beat B2).

Protocol (locked in MODEL_CARD.md before this script was written):
- The test set (87 cases) was already evaluated once, for phase4-original.
  Everything in this script's model-selection step uses ONLY the 351
  train+val cases, via 5-fold grouped (by subject) cross-validation --
  the 88-case single validation split phase4-original used is too noisy
  to pick a winner from reliably.
- A decision rule is written BELOW, before any CV numbers are computed:
  adopt a v2 candidate only if its cross-validated sensitivity at 1
  FA/patient-hour beats the CV-reproduced original model by >= 3
  percentage points, with the bootstrap-by-case 95% CI of that
  DIFFERENCE excluding zero.
- If a candidate is adopted, it is refit once on the ORIGINAL train/val
  split (same as phase4-original, for a direct apples-to-apples
  comparison) and evaluated against the TEST SET EXACTLY ONCE. Both the
  original and v2 test results are kept and reported side by side --
  v2 never overwrites artifacts/metrics.json.
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
CV_RESULTS_JSON = ROOT / "artifacts" / "phase4_cv_model_selection.json"
METRICS_V2_JSON = ROOT / "artifacts" / "metrics_v2.json"

PRIMARY_LABEL_COL = f"label_h{config.HORIZON_MIN_PRIMARY}"
PRIMARY_FA_TARGET = config.ALARM_OPERATING_POINT_FA_PER_PATIENT_HOUR
DECISION_MARGIN_PP = 3.0  # pre-registered, see module docstring
N_FOLDS = 5

V2_CLOSENESS_FEATURES = (
    "map_minus_65", "map_below_65_hinge", "map_min_5",
    "projected_min_to_cross_65", "time_since_anesthesia_min", "time_since_opstart_min",
)
STACKED_B2_DRIFT_FEATURES = (
    "map",
    "hr_slope_5", "hr_slope_10", "hr_slope_15",
    "map_slope_5", "map_slope_10", "map_slope_15",
    "pp_slope_5", "pp_slope_10", "pp_slope_15",
    "shock_index", "shock_index_slope_5", "shock_index_slope_10", "shock_index_slope_15",
    "hr_drift", "map_drift", "pp_drift", "shock_index_drift",
)

CANDIDATES = {
    "original_repro": {"features": models.FEATURE_COLUMNS, "sex": True, "model": "logistic"},
    "threshold_features": {"features": models.FEATURE_COLUMNS + V2_CLOSENESS_FEATURES, "sex": True, "model": "logistic"},
    "threshold_features_boosted": {"features": models.FEATURE_COLUMNS + V2_CLOSENESS_FEATURES, "sex": True, "model": "boosted"},
    "stacked_b2_drift": {"features": STACKED_B2_DRIFT_FEATURES, "sex": False, "model": "logistic"},
    "b2_alone": {"features": ("map",), "sex": False, "model": "logistic"},
}


def build_case_events(caseids: list[int], cases_df: pd.DataFrame) -> dict[int, list[float]]:
    out = {}
    for caseid in caseids:
        cleaned = vitaldb_io.load_and_clean_case(int(caseid))
        row = cases_df.loc[cases_df[config.COL_CASEID] == caseid].iloc[0]
        op_window = cleaned[(cleaned["Time"] >= row[config.COL_OPSTART]) & (cleaned["Time"] <= row[config.COL_OPEND])]
        events = labels.detect_primary_events(op_window)
        out[caseid] = sorted(e.start_time for e in events)
    return out


def feature_matrix(df: pd.DataFrame, feature_names: tuple, include_sex: bool) -> pd.DataFrame:
    X = df[list(feature_names)].copy()
    if include_sex:
        X["sex"] = models.encode_sex(df["sex"])
    return X


def fit_candidate(train_df: pd.DataFrame, spec: dict):
    X = feature_matrix(train_df, spec["features"], spec["sex"])
    y = train_df[PRIMARY_LABEL_COL]
    if spec["model"] == "logistic":
        return models.fit_logistic(X, y)
    return models.fit_boosted(X, y)


def predict_risk(fitted, df: pd.DataFrame, spec: dict) -> np.ndarray:
    X = feature_matrix(df, spec["features"], spec["sex"])
    return fitted.predict_proba(X)[:, 1]


def oof_predictions(dev_all_df: pd.DataFrame, dev_fit_df: pd.DataFrame, folds: list[list[int]], spec: dict) -> pd.Series:
    """Out-of-fold risk score for every row of dev_all_df (fit on the other
    folds' labeled rows, predict on this fold's rows, whatever their own
    label status -- the alarm stream needs a score for every monitored
    minute, not just labeled ones; see scripts/04_train_eval.py's same
    reasoning)."""
    oof = pd.Series(index=dev_all_df.index, dtype=float)
    for i, fold_ids in enumerate(folds):
        fold_set = set(fold_ids)
        train_fit = dev_fit_df[~dev_fit_df[config.COL_CASEID].isin(fold_set)]
        held_out_all = dev_all_df[dev_all_df[config.COL_CASEID].isin(fold_set)]
        if len(held_out_all) == 0 or train_fit[PRIMARY_LABEL_COL].nunique() < 2:
            continue
        fitted = fit_candidate(train_fit, spec)
        oof.loc[held_out_all.index] = predict_risk(fitted, held_out_all, spec)
    return oof


def cv_sensitivity_and_fa(dev_all_df: pd.DataFrame, risk_col: str, case_events: dict, dev_ids: list[int], target_fa: float):
    case_dfs = {cid: g for cid, g in dev_all_df.groupby(config.COL_CASEID)}
    thr, fa_rate = alarms.find_threshold_for_target_fa_rate(case_dfs, case_events, risk_col, target_fa)
    case_alerts = {cid: alarms.generate_case_alerts(case_dfs[cid], risk_col, thr) for cid in dev_ids if cid in case_dfs}
    sens_result = metrics.event_sensitivity_and_lead_times(case_events, case_alerts, dev_ids, config.HORIZON_MIN_PRIMARY)
    return thr, fa_rate, sens_result["sensitivity"], case_dfs


def main() -> None:
    print("=== Phase 4 iteration: CV model/feature selection (train+val only) ===")
    cases_df = vitaldb_io.load_case_table()
    cohort_df = pd.read_parquet(COHORT_FINAL_PARQUET)
    windows_df = pd.read_parquet(WINDOWS_PARQUET)
    windows_df = baselines.add_baseline_risk_columns(windows_df)

    all_caseids = sorted(windows_df[config.COL_CASEID].unique().tolist())
    split = models.split_cases(cases_df, all_caseids)  # same seed/logic as phase4-original -> identical split
    dev_ids = [c for c in all_caseids if split[c] in ("train", "val")]
    test_ids = [c for c in all_caseids if split[c] == "test"]
    print(f"Dev (train+val, untouched test held out): {len(dev_ids)} cases; test (locked): {len(test_ids)} cases")

    print("Computing real event lists for dev+test cases...")
    case_events = build_case_events(all_caseids, cases_df)

    dev_all_df = windows_df[windows_df[config.COL_CASEID].isin(dev_ids)].copy()
    dev_fit_df = dev_all_df[dev_all_df[PRIMARY_LABEL_COL].notna()]

    folds = models.grouped_kfold_by_subject(cases_df, dev_ids, n_folds=N_FOLDS)
    print(f"Grouped {N_FOLDS}-fold CV: fold sizes = {[len(f) for f in folds]}")

    cv_results = {}
    for name, spec in CANDIDATES.items():
        print(f"\n--- Candidate: {name} ({spec['model']}, {len(spec['features'])} features{'+sex' if spec['sex'] else ''}) ---")
        oof = oof_predictions(dev_all_df, dev_fit_df, folds, spec)
        risk_col = f"oof_{name}"
        dev_all_df[risk_col] = oof

        oof_fit_mask = dev_all_df[PRIMARY_LABEL_COL].notna() & dev_all_df[risk_col].notna()
        auprc = metrics.auroc_auprc_brier(dev_all_df.loc[oof_fit_mask, PRIMARY_LABEL_COL], dev_all_df.loc[oof_fit_mask, risk_col])

        thr, fa_rate, sens, case_dfs = cv_sensitivity_and_fa(dev_all_df, risk_col, case_events, dev_ids, PRIMARY_FA_TARGET)
        print(f"  OOF AUPRC={auprc['auprc']:.4f}  CV sensitivity@{PRIMARY_FA_TARGET}FA/hr={sens:.4f} (thr={thr:.4f}, actual FA={fa_rate:.3f}/hr)")
        cv_results[name] = {"auprc": auprc, "threshold": thr, "fa_rate": fa_rate, "sensitivity": sens, "risk_col": risk_col}

    # ---- Decision rule (pre-registered above) ----
    baseline_sens = cv_results["original_repro"]["sensitivity"]
    print(f"\n=== Decision rule: beat original_repro CV sensitivity ({baseline_sens:.4f}) by >= {DECISION_MARGIN_PP}pp, CI excludes zero ===")

    def make_diff_fn(risk_col_a, risk_col_b, thr_a, thr_b):
        case_dfs = {cid: g for cid, g in dev_all_df.groupby(config.COL_CASEID)}
        # Alerts per case are fixed given (risk_col, threshold) -- independent
        # of which/how-many times a case is drawn in a given resample, so
        # compute them ONCE here rather than inside every one of the 300
        # resamples (a >100x reduction in alert-generation calls).
        alerts_a = {cid: alarms.generate_case_alerts(case_dfs[cid], risk_col_a, thr_a) for cid in case_dfs}
        alerts_b = {cid: alarms.generate_case_alerts(case_dfs[cid], risk_col_b, thr_b) for cid in case_dfs}

        def fn(sample_ids):
            sens_a = metrics.event_sensitivity_and_lead_times(case_events, alerts_a, sample_ids, config.HORIZON_MIN_PRIMARY)["sensitivity"]
            sens_b = metrics.event_sensitivity_and_lead_times(case_events, alerts_b, sample_ids, config.HORIZON_MIN_PRIMARY)["sensitivity"]
            if np.isnan(sens_a) or np.isnan(sens_b):
                return float("nan")
            return sens_a - sens_b

        return fn

    decisions = {}
    for name in CANDIDATES:
        if name == "original_repro":
            continue
        diff_fn = make_diff_fn(
            cv_results[name]["risk_col"], cv_results["original_repro"]["risk_col"],
            cv_results[name]["threshold"], cv_results["original_repro"]["threshold"],
        )
        ci = metrics.bootstrap_ci_by_case(dev_ids, diff_fn, n_resamples=config.BOOTSTRAP_N_RESAMPLES)
        gain_pp = ci["point"] * 100
        adopt = gain_pp >= DECISION_MARGIN_PP and ci["ci_low"] > 0
        decisions[name] = {"gain_pp": gain_pp, "ci": ci, "adopt_eligible": bool(adopt)}
        print(f"  {name}: gain={gain_pp:+.2f}pp, 95% CI=[{ci['ci_low']*100:+.2f}, {ci['ci_high']*100:+.2f}]pp, adopt_eligible={adopt}")

    eligible = {n: d for n, d in decisions.items() if d["adopt_eligible"]}
    if eligible:
        winner = max(eligible, key=lambda n: decisions[n]["gain_pp"])
        print(f"\n=> v2 candidate ADOPTED: {winner} (gain {decisions[winner]['gain_pp']:+.2f}pp)")
    else:
        winner = None
        print("\n=> No candidate cleared the pre-registered bar. Original model stands; v2 is a no-op.")

    CV_RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    CV_RESULTS_JSON.write_text(json.dumps({
        "cv_results": {n: {k: v for k, v in r.items() if k != "risk_col"} for n, r in cv_results.items()},
        "decisions": decisions, "winner": winner, "decision_margin_pp": DECISION_MARGIN_PP, "n_folds": N_FOLDS,
    }, indent=2, default=lambda x: None))
    print(f"Saved CV results to {CV_RESULTS_JSON}")

    if winner is None:
        print("\nNothing further to run -- phase4-original stands as the shipped model.")
        return

    # ---- Refit winner on the ORIGINAL train/val split, evaluate TEST ONCE ----
    print(f"\n=== Refitting '{winner}' on the original train/val split, evaluating TEST ONCE ===")
    spec = CANDIDATES[winner]
    train_ids = [c for c in all_caseids if split[c] == "train"]
    val_ids = [c for c in all_caseids if split[c] == "val"]
    train_all_df = windows_df[windows_df[config.COL_CASEID].isin(train_ids)]
    val_all_df = windows_df[windows_df[config.COL_CASEID].isin(val_ids)].copy()
    test_all_df = windows_df[windows_df[config.COL_CASEID].isin(test_ids)].copy()
    train_fit = train_all_df[train_all_df[PRIMARY_LABEL_COL].notna()]
    val_fit = val_all_df[val_all_df[PRIMARY_LABEL_COL].notna()]

    fitted = fit_candidate(train_fit, spec)
    calibrated = models.calibrate_on_validation(fitted, feature_matrix(val_fit, spec["features"], spec["sex"]), val_fit[PRIMARY_LABEL_COL])
    val_all_df["model_risk"] = calibrated.predict_proba(feature_matrix(val_all_df, spec["features"], spec["sex"]))[:, 1]
    test_all_df["model_risk"] = calibrated.predict_proba(feature_matrix(test_all_df, spec["features"], spec["sex"]))[:, 1]

    case_dfs_val = {cid: g for cid, g in val_all_df.groupby(config.COL_CASEID)}
    thr, val_fa = alarms.find_threshold_for_target_fa_rate(case_dfs_val, case_events, "model_risk", PRIMARY_FA_TARGET)

    case_dfs_test = {cid: g for cid, g in test_all_df.groupby(config.COL_CASEID)}
    cohort_b_test_ids = [c for c in test_ids if bool(cohort_df.loc[cohort_df[config.COL_CASEID] == c, "cohort_b_final"].iloc[0])]

    results_by_cohort = {}
    for cohort_name, cohort_ids in (("A", test_ids), ("B", cohort_b_test_ids)):
        case_alerts = {cid: alarms.generate_case_alerts(case_dfs_test[cid], "model_risk", thr) for cid in cohort_ids if cid in case_dfs_test}
        sens_result = metrics.event_sensitivity_and_lead_times(case_events, case_alerts, cohort_ids, config.HORIZON_MIN_PRIMARY)
        lead_summary = metrics.lead_time_summary(sens_result["lead_times_s"])
        cohort_case_dfs = {cid: case_dfs_test[cid] for cid in cohort_ids if cid in case_dfs_test}
        fa_rate = alarms.false_alarm_rate_for_threshold(cohort_case_dfs, case_events, "model_risk", thr, horizon_min=config.HORIZON_MIN_PRIMARY)
        results_by_cohort[cohort_name] = {
            "n_events": sens_result["n_events"], "n_detected": sens_result["n_detected"],
            "sensitivity": sens_result["sensitivity"], "lead_time": lead_summary, "fa_rate_per_hour": fa_rate,
        }
        print(f"  Cohort {cohort_name}: sensitivity={sens_result['sensitivity']:.3f}, "
              f"lead_median_min={lead_summary['median_s']/60 if lead_summary['median_s']==lead_summary['median_s'] else float('nan'):.2f}, "
              f"FA/hr={fa_rate:.3f}")

    secondary = metrics.auroc_auprc_brier(test_all_df[PRIMARY_LABEL_COL], test_all_df["model_risk"])
    print(f"  Test AUROC/AUPRC/Brier: {secondary}")

    output = {
        "v2_winner": winner, "v2_feature_spec": {"features": list(spec["features"]), "model": spec["model"]},
        "val_operating_point": {"threshold": thr, "val_fa_rate": val_fa, "target_fa": PRIMARY_FA_TARGET},
        "test_results_by_cohort": results_by_cohort,
        "test_secondary_metrics": secondary,
        "compared_against": "artifacts/metrics.json (phase4-original)",
    }
    METRICS_V2_JSON.write_text(json.dumps(output, indent=2, default=lambda x: None))
    print(f"\nSaved {METRICS_V2_JSON}")


if __name__ == "__main__":
    main()
