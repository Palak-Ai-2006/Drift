#!/usr/bin/env python
"""Phase 4 iteration, round 3 (rules locked in ACTIONS.md before this was
written). Two targeted candidates against b2_alone, 5-fold grouped CV on
train+val only, same 3pp/CI-excludes-zero decision rule, time-boxed to
~3 hours:

1. residual_ridge: MAP-only model's logit as a fixed offset, ridge-
   penalized logistic on the extra features (HR, shock index, PP, all
   slopes, all drift-from-baseline) fit on top of it, penalty chosen by
   inner grouped CV (models.fit_offset_ridge_with_inner_cv).
2. interaction_features: MAP plus (65-MAP)*shock_index and
   (65-MAP)*HR-drift, as a small plain logistic.
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
RESULTS_JSON = ROOT / "artifacts" / "phase4_round3_cv_results.json"

PRIMARY_LABEL_COL = f"label_h{config.HORIZON_MIN_PRIMARY}"
PRIMARY_FA_TARGET = config.ALARM_OPERATING_POINT_FA_PER_PATIENT_HOUR
DECISION_MARGIN_PP = 3.0
N_FOLDS = 3  # exact Round 3 plan (ACTIONS.md): 3-fold grouped CV, not 5-fold

EXTRA_FEATURES_FOR_RESIDUAL = (
    "hr", "shock_index", "pp",
    "hr_slope_5", "hr_slope_10", "hr_slope_15",
    "map_slope_5", "map_slope_10", "map_slope_15",
    "pp_slope_5", "pp_slope_10", "pp_slope_15",
    "shock_index_slope_5", "shock_index_slope_10", "shock_index_slope_15",
    "hr_drift", "map_drift", "pp_drift", "shock_index_drift",
)


def build_case_events(caseids, cases_df):
    out = {}
    for caseid in caseids:
        cleaned = vitaldb_io.load_and_clean_case(int(caseid))
        row = cases_df.loc[cases_df[config.COL_CASEID] == caseid].iloc[0]
        op_window = cleaned[(cleaned["Time"] >= row[config.COL_OPSTART]) & (cleaned["Time"] <= row[config.COL_OPEND])]
        events = labels.detect_primary_events(op_window)
        out[caseid] = sorted(e.start_time for e in events)
    return out


def add_interaction_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    closeness = -out["map_minus_65"]  # (65 - MAP): positive & larger when MAP is further below 65
    out["map_closeness_x_shock_index"] = closeness * out["shock_index"]
    out["map_closeness_x_hr_drift"] = closeness * out["hr_drift"]
    return out


def oof_b2_alone(dev_all_df, dev_fit_df, folds) -> pd.Series:
    oof = pd.Series(index=dev_all_df.index, dtype=float)
    for fold_ids in folds:
        fold_set = set(fold_ids)
        train_fit = dev_fit_df[~dev_fit_df[config.COL_CASEID].isin(fold_set)]
        held_out = dev_all_df[dev_all_df[config.COL_CASEID].isin(fold_set)]
        if len(held_out) == 0:
            continue
        model = models.fit_logistic(train_fit[["map"]], train_fit[PRIMARY_LABEL_COL])
        oof.loc[held_out.index] = model.predict_proba(held_out[["map"]])[:, 1]
    return oof


def oof_residual_ridge(dev_all_df, dev_fit_df, folds, extra_cols) -> pd.Series:
    """For each outer fold: fit b2_alone on the outer-train rows to get the
    offset, then fit OffsetRidgeLogistic (with its own inner CV for alpha,
    on the same outer-train rows) on top of it; predict both on the
    held-out fold."""
    oof = pd.Series(index=dev_all_df.index, dtype=float)
    for fold_ids in folds:
        fold_set = set(fold_ids)
        train_fit = dev_fit_df[~dev_fit_df[config.COL_CASEID].isin(fold_set)]
        held_out = dev_all_df[dev_all_df[config.COL_CASEID].isin(fold_set)]
        if len(held_out) == 0:
            continue

        base_model = models.fit_logistic(train_fit[["map"]], train_fit[PRIMARY_LABEL_COL])
        offset_train = base_model.decision_function(train_fit[["map"]])

        X_extra_train = train_fit[list(extra_cols)].fillna(0.0).to_numpy()
        y_train = train_fit[PRIMARY_LABEL_COL].to_numpy()
        groups_train = train_fit[config.COL_CASEID].to_numpy()
        residual_model = models.fit_offset_ridge_with_inner_cv(X_extra_train, y_train, offset_train, groups_train)

        offset_held = base_model.decision_function(held_out[["map"]])
        X_extra_held = held_out[list(extra_cols)].fillna(0.0).to_numpy()
        oof.loc[held_out.index] = residual_model.predict_proba_from_offset(X_extra_held, offset_held)
    return oof


def oof_interaction(dev_all_df, dev_fit_df, folds) -> pd.Series:
    feats = ["map", "map_closeness_x_shock_index", "map_closeness_x_hr_drift"]
    oof = pd.Series(index=dev_all_df.index, dtype=float)
    for fold_ids in folds:
        fold_set = set(fold_ids)
        train_fit = dev_fit_df[~dev_fit_df[config.COL_CASEID].isin(fold_set)]
        held_out = dev_all_df[dev_all_df[config.COL_CASEID].isin(fold_set)]
        if len(held_out) == 0:
            continue
        model = models.fit_logistic(train_fit[feats].fillna(0.0), train_fit[PRIMARY_LABEL_COL])
        oof.loc[held_out.index] = model.predict_proba(held_out[feats].fillna(0.0))[:, 1]
    return oof


def cv_sensitivity(dev_all_df, risk_col, case_events, dev_ids, target_fa=PRIMARY_FA_TARGET):
    case_dfs = {cid: g for cid, g in dev_all_df.groupby(config.COL_CASEID)}
    thr, fa_rate = alarms.find_threshold_for_target_fa_rate(case_dfs, case_events, risk_col, target_fa)
    case_alerts = {cid: alarms.generate_case_alerts(case_dfs[cid], risk_col, thr) for cid in dev_ids if cid in case_dfs}
    sens_result = metrics.event_sensitivity_and_lead_times(case_events, case_alerts, dev_ids, config.HORIZON_MIN_PRIMARY)
    return thr, fa_rate, sens_result["sensitivity"], case_dfs


def main() -> None:
    print("=== Phase 4 iteration round 3: residual/offset model + interaction terms ===")
    cases_df = vitaldb_io.load_case_table()
    windows_df = pd.read_parquet(WINDOWS_PARQUET)
    windows_df = add_interaction_features(windows_df)

    all_caseids = sorted(windows_df[config.COL_CASEID].unique().tolist())
    split = models.split_cases(cases_df, all_caseids)
    dev_ids = [c for c in all_caseids if split[c] in ("train", "val")]
    print(f"Dev (train+val): {len(dev_ids)} cases")

    print("Computing real event lists...")
    case_events = build_case_events(dev_ids, cases_df)

    dev_all_df = windows_df[windows_df[config.COL_CASEID].isin(dev_ids)].copy()
    dev_fit_df = dev_all_df[dev_all_df[PRIMARY_LABEL_COL].notna()]

    folds = models.grouped_kfold_by_subject(cases_df, dev_ids, n_folds=N_FOLDS)
    print(f"Grouped {N_FOLDS}-fold CV: fold sizes = {[len(f) for f in folds]}")

    results = {}

    print("\n--- b2_alone (reference) ---")
    dev_all_df["oof_b2_alone"] = oof_b2_alone(dev_all_df, dev_fit_df, folds)
    thr, fa, sens, _ = cv_sensitivity(dev_all_df, "oof_b2_alone", case_events, dev_ids)
    print(f"  CV sensitivity@1FA/hr={sens:.4f} (thr={thr:.4f}, FA={fa:.3f}/hr)")
    results["b2_alone"] = {"threshold": thr, "fa_rate": fa, "sensitivity": sens}

    print("\n--- residual_ridge (MAP offset + ridge-penalized extras) ---")
    dev_all_df["oof_residual_ridge"] = oof_residual_ridge(dev_all_df, dev_fit_df, folds, EXTRA_FEATURES_FOR_RESIDUAL)
    thr, fa, sens, _ = cv_sensitivity(dev_all_df, "oof_residual_ridge", case_events, dev_ids)
    print(f"  CV sensitivity@1FA/hr={sens:.4f} (thr={thr:.4f}, FA={fa:.3f}/hr)")
    results["residual_ridge"] = {"threshold": thr, "fa_rate": fa, "sensitivity": sens}

    print("\n--- interaction_features (MAP + 2 interaction terms) ---")
    dev_all_df["oof_interaction_features"] = oof_interaction(dev_all_df, dev_fit_df, folds)
    thr, fa, sens, _ = cv_sensitivity(dev_all_df, "oof_interaction_features", case_events, dev_ids)
    print(f"  CV sensitivity@1FA/hr={sens:.4f} (thr={thr:.4f}, FA={fa:.3f}/hr)")
    results["interaction_features"] = {"threshold": thr, "fa_rate": fa, "sensitivity": sens}

    print(f"\n=== Decision rule: beat b2_alone CV sensitivity ({results['b2_alone']['sensitivity']:.4f}) "
          f"by >= {DECISION_MARGIN_PP}pp, CI excludes zero ===")
    case_dfs = {cid: g for cid, g in dev_all_df.groupby(config.COL_CASEID)}
    alerts_b2 = {cid: alarms.generate_case_alerts(case_dfs[cid], "oof_b2_alone", results["b2_alone"]["threshold"]) for cid in case_dfs}

    decisions = {}
    for name in ("residual_ridge", "interaction_features"):
        risk_col = f"oof_{name}"
        alerts_candidate = {cid: alarms.generate_case_alerts(case_dfs[cid], risk_col, results[name]["threshold"]) for cid in case_dfs}

        def diff_fn(sample_ids, alerts_candidate=alerts_candidate):
            sens_c = metrics.event_sensitivity_and_lead_times(case_events, alerts_candidate, sample_ids, config.HORIZON_MIN_PRIMARY)["sensitivity"]
            sens_b2 = metrics.event_sensitivity_and_lead_times(case_events, alerts_b2, sample_ids, config.HORIZON_MIN_PRIMARY)["sensitivity"]
            if np.isnan(sens_c) or np.isnan(sens_b2):
                return float("nan")
            return sens_c - sens_b2

        ci = metrics.bootstrap_ci_by_case(dev_ids, diff_fn, n_resamples=config.BOOTSTRAP_N_RESAMPLES)
        gain_pp = ci["point"] * 100
        adopt = gain_pp >= DECISION_MARGIN_PP and ci["ci_low"] > 0
        decisions[name] = {"gain_pp": gain_pp, "ci": ci, "adopt_eligible": bool(adopt)}
        print(f"  {name}: gain={gain_pp:+.2f}pp, 95% CI=[{ci['ci_low']*100:+.2f}, {ci['ci_high']*100:+.2f}]pp, adopt_eligible={adopt}")

    eligible = {n: d for n, d in decisions.items() if d["adopt_eligible"]}
    winner = max(eligible, key=lambda n: decisions[n]["gain_pp"]) if eligible else None
    print(f"\n=> {'Adopted: ' + winner if winner else 'No candidate cleared the bar. b2_alone stands.'}")

    RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_JSON.write_text(json.dumps({"cv_results": results, "decisions": decisions, "winner": winner}, indent=2, default=lambda x: None))
    print(f"Saved {RESULTS_JSON}")


if __name__ == "__main__":
    main()
