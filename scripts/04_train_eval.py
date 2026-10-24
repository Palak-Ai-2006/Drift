#!/usr/bin/env python
"""Phase 4: patient-level split, baselines B1-B4, logistic + boosted models,
calibration, alarm logic, operating-point selection, and test-set metrics
with bootstrap CIs by case. Writes artifacts/metrics.json -- the single
source of truth every later number (web demo, DATA_CARD, MODEL_CARD,
Devpost, video) must be read from, never hand-typed (CLAUDE.md Section 12).

Accept (PLAN.md Phase 4): metrics.json and plots regenerate with one command.
Test set is evaluated once; no tuning on it (model selection and operating
points are chosen on validation only).
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
METRICS_JSON = ROOT / "artifacts" / "metrics.json"

PRIMARY_LABEL_COL = f"label_h{config.HORIZON_MIN_PRIMARY}"
FA_TARGETS = (config.ALARM_OPERATING_POINT_FA_PER_PATIENT_HOUR, *config.ALARM_OPERATING_POINT_FA_ALTERNATES_PER_PATIENT_HOUR)


def build_case_events(caseids: list[int], cases_df: pd.DataFrame) -> dict[int, list[float]]:
    """Real primary-event start times per case, within the operation
    window -- same definition scripts/02c_finalize_cohort.py and
    features.build_case_windows already use, recomputed here once so
    Phase 4 doesn't need to re-plumb it through windows.parquet."""
    out = {}
    for caseid in caseids:
        cleaned = vitaldb_io.load_and_clean_case(int(caseid))
        row = cases_df.loc[cases_df[config.COL_CASEID] == caseid].iloc[0]
        op_window = cleaned[(cleaned["Time"] >= row[config.COL_OPSTART]) & (cleaned["Time"] <= row[config.COL_OPEND])]
        events = labels.detect_primary_events(op_window)
        out[caseid] = sorted(e.start_time for e in events)
    return out


def to_case_dfs(windows_df: pd.DataFrame, caseids: list[int]) -> dict[int, pd.DataFrame]:
    sub = windows_df[windows_df[config.COL_CASEID].isin(caseids)]
    return {cid: g for cid, g in sub.groupby(config.COL_CASEID)}


def auprc_diff_metric_fn(val_df: pd.DataFrame, logistic_col: str, boosted_col: str, label_col: str):
    def fn(caseid_sample: list[int]) -> float:
        rows = pd.concat([val_df[val_df[config.COL_CASEID] == cid] for cid in set(caseid_sample)], ignore_index=True)
        # Repeat rows for caseids drawn more than once, matching case-level bootstrap semantics.
        counts = pd.Series(caseid_sample).value_counts()
        rows = pd.concat([rows[rows[config.COL_CASEID] == cid] for cid in counts.index for _ in range(counts[cid])], ignore_index=True)
        y = rows[label_col]
        if y.notna().sum() == 0 or y.dropna().nunique() < 2:
            return float("nan")
        m_log = metrics.auroc_auprc_brier(y, rows[logistic_col])
        m_boost = metrics.auroc_auprc_brier(y, rows[boosted_col])
        if np.isnan(m_log["auprc"]) or np.isnan(m_boost["auprc"]):
            return float("nan")
        return m_boost["auprc"] - m_log["auprc"]
    return fn


def sensitivity_at_threshold(case_dfs: dict, case_events: dict, caseids: list, risk_col: str, threshold: float, horizon_min: float) -> float:
    case_alerts = {cid: alarms.generate_case_alerts(case_dfs[cid], risk_col, threshold) for cid in caseids if cid in case_dfs}
    result = metrics.event_sensitivity_and_lead_times(case_events, case_alerts, caseids, horizon_min)
    return result["sensitivity"]


def plot_reliability_curve(reliability: dict, model_name: str, brier: float) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    bins = [b for b in reliability["bins"] if b["n"] > 0]
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], "--", color="#9BA7B4", label="perfectly calibrated")
    ax.plot([b["mean_predicted"] for b in bins], [b["observed_fraction"] for b in bins],
             "o-", color=config.WEB_COLOR_TRACE_MAP, label=f"{model_name} (Brier={brier:.4f})")
    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Observed positive fraction")
    ax.set_title(f"Calibration reliability, test set (H={config.HORIZON_MIN_PRIMARY}min)")
    ax.legend(loc="upper left")
    fig.tight_layout()
    out = ROOT / "artifacts" / "phase4_reliability_plot.png"
    fig.savefig(out, dpi=120)
    print(f"Saved reliability plot to {out}")


def main() -> None:
    print("=== Phase 4: baselines, models, evaluation ===")
    cases_df = vitaldb_io.load_case_table()
    cohort_df = pd.read_parquet(COHORT_FINAL_PARQUET)
    windows_df = pd.read_parquet(WINDOWS_PARQUET)
    windows_df = baselines.add_baseline_risk_columns(windows_df)

    all_caseids = sorted(windows_df[config.COL_CASEID].unique().tolist())
    split = models.split_cases(cases_df, all_caseids)
    windows_df["split"] = windows_df[config.COL_CASEID].map(split)
    train_ids = [c for c in all_caseids if split[c] == "train"]
    val_ids = [c for c in all_caseids if split[c] == "val"]
    test_ids = [c for c in all_caseids if split[c] == "test"]
    print(f"Split: {len(train_ids)} train / {len(val_ids)} val / {len(test_ids)} test cases")

    print("Computing real event lists for all cases (for sensitivity/lead-time/FA metrics)...")
    case_events = build_case_events(all_caseids, cases_df)
    print(f"  total events across {len(all_caseids)} cases: {sum(len(v) for v in case_events.values())}")

    # windows_df "_all" (every row for that split, whatever labels it has)
    # is what the alarm stream, operating-point search, sensitivity and
    # false-alarm-rate denominator all run on -- the system is live for
    # every monitored minute, not just ones where label_h15 happens to be
    # known. Only fitting/calibration/AUPRC comparison (which need y
    # itself) restrict to rows with a known primary-horizon label.
    train_all_df = windows_df[windows_df["split"] == "train"]
    val_all_df = windows_df[windows_df["split"] == "val"].copy()
    test_all_df = windows_df[windows_df["split"] == "test"].copy()
    train_fit_df = train_all_df[train_all_df[PRIMARY_LABEL_COL].notna()]
    val_fit_df = val_all_df[val_all_df[PRIMARY_LABEL_COL].notna()]
    print(f"Rows with known label_h{config.HORIZON_MIN_PRIMARY} (for fitting/calibration): "
          f"{len(train_fit_df)} train / {len(val_fit_df)} val, out of {len(train_all_df)} / {len(val_all_df)} total")

    X_train = models.prepare_feature_matrix(train_fit_df)
    y_train = train_fit_df[PRIMARY_LABEL_COL]
    X_val_fit = models.prepare_feature_matrix(val_fit_df)
    y_val_fit = val_fit_df[PRIMARY_LABEL_COL]
    X_val_all = models.prepare_feature_matrix(val_all_df)
    X_test_all = models.prepare_feature_matrix(test_all_df)

    print("Fitting logistic regression...")
    logistic_pipeline = models.fit_logistic(X_train, y_train)
    print("Fitting HistGradientBoostingClassifier...")
    boosted_model = models.fit_boosted(X_train, y_train)

    val_all_df["logistic_raw"] = logistic_pipeline.predict_proba(X_val_all)[:, 1]
    val_all_df["boosted_raw"] = boosted_model.predict_proba(X_val_all)[:, 1]
    val_fit_df = val_all_df[val_all_df[PRIMARY_LABEL_COL].notna()]  # refresh with the *_raw columns attached

    # ---- Model selection on VALIDATION ONLY ----
    case_dfs_val_all = to_case_dfs(val_all_df, val_ids)
    thr_log, fa_log = alarms.find_threshold_for_target_fa_rate(
        case_dfs_val_all, case_events, "logistic_raw", config.ALARM_OPERATING_POINT_FA_PER_PATIENT_HOUR,
    )
    thr_boost, fa_boost = alarms.find_threshold_for_target_fa_rate(
        case_dfs_val_all, case_events, "boosted_raw", config.ALARM_OPERATING_POINT_FA_PER_PATIENT_HOUR,
    )
    sens_log = sensitivity_at_threshold(case_dfs_val_all, case_events, val_ids, "logistic_raw", thr_log, config.HORIZON_MIN_PRIMARY)
    sens_boost = sensitivity_at_threshold(case_dfs_val_all, case_events, val_ids, "boosted_raw", thr_boost, config.HORIZON_MIN_PRIMARY)
    sens_gain_pp = (sens_boost - sens_log) * 100

    auprc_fn = auprc_diff_metric_fn(val_fit_df, "logistic_raw", "boosted_raw", PRIMARY_LABEL_COL)
    auprc_diff_ci = metrics.bootstrap_ci_by_case(val_ids, auprc_fn, n_resamples=config.BOOTSTRAP_N_RESAMPLES)
    auprc_ci_excludes_zero = auprc_diff_ci["ci_low"] > 0

    ship_boosted = (
        config.MODEL_SELECT_REQUIRE_AUPRC_CI_EXCLUDES_ZERO and auprc_ci_excludes_zero
        and sens_gain_pp >= config.MODEL_SELECT_MIN_SENSITIVITY_GAIN_PP
    )
    chosen_model_name = "boosted" if ship_boosted else "logistic"
    print(f"\n--- Model selection (validation only) ---")
    print(f"Logistic: val sensitivity@1FA/hr = {sens_log:.4f} (threshold={thr_log:.4f}, actual FA={fa_log:.3f}/hr)")
    print(f"Boosted:  val sensitivity@1FA/hr = {sens_boost:.4f} (threshold={thr_boost:.4f}, actual FA={fa_boost:.3f}/hr)")
    print(f"Sensitivity gain (boosted - logistic): {sens_gain_pp:.2f}pp (need >= {config.MODEL_SELECT_MIN_SENSITIVITY_GAIN_PP}pp)")
    print(f"AUPRC diff bootstrap 95% CI: [{auprc_diff_ci['ci_low']:.4f}, {auprc_diff_ci['ci_high']:.4f}] "
          f"(point={auprc_diff_ci['point']:.4f}), excludes zero: {auprc_ci_excludes_zero}")
    print(f"=> Shipping: {chosen_model_name}")

    # ---- Calibrate the CHOSEN model on validation (label-known rows only) ----
    chosen_raw_model = boosted_model if ship_boosted else logistic_pipeline
    X_val_fit = models.prepare_feature_matrix(val_fit_df)
    calibrated = models.calibrate_on_validation(chosen_raw_model, X_val_fit, y_val_fit)

    val_all_df["model_risk"] = calibrated.predict_proba(X_val_all)[:, 1]
    test_all_df["model_risk"] = calibrated.predict_proba(X_test_all)[:, 1]

    # ---- Operating points on VALIDATION, for the model and every baseline ----
    case_dfs_val = to_case_dfs(val_all_df, val_ids)
    methods = {"model": "model_risk", "b2": "b2_risk", "b3": "b3_risk", "b4": "b4_risk"}
    operating_points = {}
    for method, risk_col in methods.items():
        operating_points[method] = {}
        for target in FA_TARGETS:
            thr, fa_rate = alarms.find_threshold_for_target_fa_rate(case_dfs_val, case_events, risk_col, target)
            operating_points[method][target] = {"threshold": thr, "val_fa_rate": fa_rate}
            print(f"Operating point: {method} @ target {target} FA/hr -> threshold={thr:.4f}, val FA rate={fa_rate:.3f}/hr")

    # ---- TEST SET evaluation (touched once) ----
    print("\n=== TEST SET evaluation (evaluated once) ===")
    case_dfs_test = to_case_dfs(test_all_df, test_ids)
    cohort_b_test_ids = [c for c in test_ids if bool(cohort_df.loc[cohort_df[config.COL_CASEID] == c, "cohort_b_final"].iloc[0])]

    results = {"methods": {}}
    for method, risk_col in list(methods.items()) + [("b1", None)]:
        results["methods"][method] = {}
        targets = FA_TARGETS if method != "b1" else (None,)
        for target in targets:
            if method == "b1":
                case_alerts = {cid: baselines.b1_alert_times(case_events.get(cid, [])) for cid in test_ids}
                key = "zero_lead"
            else:
                thr = operating_points[method][target]["threshold"]
                case_alerts = {cid: alarms.generate_case_alerts(case_dfs_test[cid], risk_col, thr) for cid in test_ids if cid in case_dfs_test}
                key = str(target)

            per_horizon = {}
            for h in config.HORIZON_MIN_OPTIONS:
                for cohort_name, cohort_ids in (("A", test_ids), ("B", cohort_b_test_ids)):
                    if method == "b1":
                        # B1's alert IS each event's own start time by construction
                        # (zero lead) -- the generic matcher requires alert < event
                        # strictly, which a lead of exactly 0 can never satisfy, so
                        # this is a documented special case, not run through it.
                        n_events = sum(len(case_events.get(cid, [])) for cid in cohort_ids)
                        per_horizon[f"H{h}_cohort{cohort_name}"] = {
                            "n_events": n_events, "n_detected": n_events,
                            "sensitivity": 1.0 if n_events > 0 else float("nan"),
                            "lead_time": {"median_s": 0.0, "iqr_low_s": 0.0, "iqr_high_s": 0.0, "n": n_events},
                        }
                        continue
                    sens_result = metrics.event_sensitivity_and_lead_times(case_events, case_alerts, cohort_ids, h)
                    lead_summary = metrics.lead_time_summary(sens_result["lead_times_s"])
                    per_horizon[f"H{h}_cohort{cohort_name}"] = {
                        "n_events": sens_result["n_events"], "n_detected": sens_result["n_detected"],
                        "sensitivity": sens_result["sensitivity"], "lead_time": lead_summary,
                    }

            # False-alarm rate uses the primary horizon's true/false definition
            # (the alarm stream itself doesn't change across horizons -- only
            # which events count as "covered" does), reported per cohort.
            fa_rate_by_cohort = {}
            for cohort_name, cohort_ids in (("A", test_ids), ("B", cohort_b_test_ids)):
                if method == "b1":
                    fa_rate_by_cohort[cohort_name] = 0.0  # zero-lead alarm == the event itself; never "false"
                else:
                    cohort_case_dfs = {cid: case_dfs_test[cid] for cid in cohort_ids if cid in case_dfs_test}
                    fa_rate_by_cohort[cohort_name] = alarms.false_alarm_rate_for_threshold(
                        cohort_case_dfs, case_events, risk_col, operating_points[method][target]["threshold"],
                        horizon_min=config.HORIZON_MIN_PRIMARY,
                    )

            results["methods"][method][key] = {"per_horizon": per_horizon, "fa_rate_per_hour_by_cohort": fa_rate_by_cohort}

    # Secondary metrics (AUROC/AUPRC/Brier) on test, primary horizon and model risk only.
    secondary = metrics.auroc_auprc_brier(test_all_df[PRIMARY_LABEL_COL], test_all_df["model_risk"])
    print(f"Test AUROC/AUPRC/Brier (H={config.HORIZON_MIN_PRIMARY}, model={chosen_model_name}): {secondary}")

    reliability = metrics.reliability_curve(test_all_df[PRIMARY_LABEL_COL], test_all_df["model_risk"])
    plot_reliability_curve(reliability, chosen_model_name, secondary["brier"])

    # Bootstrap 95% CIs by case for the headline comparison (model vs. B1,
    # the standard alarm) at the primary horizon, both cohorts -- PLAN.md
    # Phase 4 accept criterion: "bootstrap 95% CI by case."
    print("\nBootstrapping 95% CIs for headline sensitivity/FA-rate numbers...")
    model_thr = operating_points["model"][config.ALARM_OPERATING_POINT_FA_PER_PATIENT_HOUR]["threshold"]
    headline_cis = {}
    for cohort_name, cohort_ids in (("A", test_ids), ("B", cohort_b_test_ids)):
        def sens_fn(sample, _ids=cohort_ids):
            return sensitivity_at_threshold(case_dfs_test, case_events, sample, "model_risk", model_thr, config.HORIZON_MIN_PRIMARY)

        def fa_fn(sample):
            return alarms.false_alarm_rate_for_threshold(
                case_dfs_test, case_events, "model_risk", model_thr,
                horizon_min=config.HORIZON_MIN_PRIMARY, caseids=sample,
            )

        headline_cis[cohort_name] = {
            "sensitivity_ci": metrics.bootstrap_ci_by_case(cohort_ids, sens_fn, n_resamples=config.BOOTSTRAP_N_RESAMPLES),
            "fa_rate_ci": metrics.bootstrap_ci_by_case(cohort_ids, fa_fn, n_resamples=config.BOOTSTRAP_N_RESAMPLES),
        }
        print(f"  Cohort {cohort_name}: sensitivity {headline_cis[cohort_name]['sensitivity_ci']['point']:.3f} "
              f"[{headline_cis[cohort_name]['sensitivity_ci']['ci_low']:.3f}, {headline_cis[cohort_name]['sensitivity_ci']['ci_high']:.3f}], "
              f"FA/hr {headline_cis[cohort_name]['fa_rate_ci']['point']:.3f} "
              f"[{headline_cis[cohort_name]['fa_rate_ci']['ci_low']:.3f}, {headline_cis[cohort_name]['fa_rate_ci']['ci_high']:.3f}]")

    feature_names = list(models.FEATURE_COLUMNS) + ["sex"]
    logistic_meta = models.logistic_coefficients(logistic_pipeline, feature_names)

    output = {
        "chosen_model": chosen_model_name,
        "model_selection": {
            "sensitivity_logistic": sens_log, "sensitivity_boosted": sens_boost,
            "sensitivity_gain_pp": sens_gain_pp, "auprc_diff_ci": auprc_diff_ci,
            "auprc_ci_excludes_zero": bool(auprc_ci_excludes_zero),
        },
        "operating_points": operating_points,
        "test_results": results,
        "test_secondary_metrics": secondary,
        "test_reliability_curve": reliability,
        "headline_bootstrap_cis": headline_cis,
        "split_sizes": {"train": len(train_ids), "val": len(val_ids), "test": len(test_ids)},
        "logistic_coefficients_for_why_panel": logistic_meta,
        "primary_horizon_min": config.HORIZON_MIN_PRIMARY,
    }
    METRICS_JSON.parent.mkdir(parents=True, exist_ok=True)
    METRICS_JSON.write_text(json.dumps(output, indent=2, default=lambda x: None))
    print(f"\nSaved {METRICS_JSON}")


if __name__ == "__main__":
    main()
