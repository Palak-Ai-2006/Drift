#!/usr/bin/env python
"""Phase 4 iteration, part 2: diagnostics for the adopted v2 model
(b2_alone, chosen by scripts/04b_model_iteration.py's pre-registered CV
rule). Cheap to refit (single feature), so this reruns that refit rather
than re-running the expensive CV script, and adds:
  - a calibration reliability plot on the test set (same test predictions
    already used for the one allowed test evaluation -- no second test
    touch, just a different view of the same predictions)
  - sensitivity across all four horizons from the SAME fixed alert stream
    (threshold chosen once, at H=15/1 FA-per-hour)
  - subgroup slices: gradual vs. abrupt MAP decline into each event (split
    at the test set's own median map_slope_15 at event onset -- not a
    guessed clinical cutoff), and early vs. late in the operation (split
    at the median event position within its case's op window)
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import alarms, config, features, labels, metrics, models, vitaldb_io  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
COHORT_FINAL_PARQUET = ROOT / "data" / "interim" / "cohort.parquet"
WINDOWS_PARQUET = ROOT / "data" / "processed" / "windows.parquet"
METRICS_V2_JSON = ROOT / "artifacts" / "metrics_v2.json"

PRIMARY_LABEL_COL = f"label_h{config.HORIZON_MIN_PRIMARY}"


def build_case_events(caseids, cases_df):
    out = {}
    for caseid in caseids:
        cleaned = vitaldb_io.load_and_clean_case(int(caseid))
        row = cases_df.loc[cases_df[config.COL_CASEID] == caseid].iloc[0]
        op_window = cleaned[(cleaned["Time"] >= row[config.COL_OPSTART]) & (cleaned["Time"] <= row[config.COL_OPEND])]
        events = labels.detect_primary_events(op_window)
        out[caseid] = sorted(e.start_time for e in events)
    return out, {caseid: cleaned for caseid, cleaned in ((c, vitaldb_io.load_and_clean_case(int(c))) for c in caseids)}


def plot_reliability(reliability, model_name, brier, out_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    bins = [b for b in reliability["bins"] if b["n"] > 0]
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], "--", color="#9BA7B4", label="perfectly calibrated")
    ax.plot([b["mean_predicted"] for b in bins], [b["observed_fraction"] for b in bins],
             "o-", color=config.WEB_COLOR_TRACE_HR, label=f"{model_name} (Brier={brier:.4f})")
    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Observed positive fraction")
    ax.set_title(f"v2 ({model_name}) calibration reliability, test set")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    print(f"Saved reliability plot to {out_path}")


def main() -> None:
    print("=== v2 (b2_alone) diagnostics: reliability, horizon sweep, subgroup slices ===")
    cases_df = vitaldb_io.load_case_table()
    cohort_df = pd.read_parquet(COHORT_FINAL_PARQUET)
    windows_df = pd.read_parquet(WINDOWS_PARQUET)

    all_caseids = sorted(windows_df[config.COL_CASEID].unique().tolist())
    split = models.split_cases(cases_df, all_caseids)
    train_ids = [c for c in all_caseids if split[c] == "train"]
    val_ids = [c for c in all_caseids if split[c] == "val"]
    test_ids = [c for c in all_caseids if split[c] == "test"]

    train_all = windows_df[windows_df[config.COL_CASEID].isin(train_ids)]
    val_all = windows_df[windows_df[config.COL_CASEID].isin(val_ids)].copy()
    test_all = windows_df[windows_df[config.COL_CASEID].isin(test_ids)].copy()
    train_fit = train_all[train_all[PRIMARY_LABEL_COL].notna()]
    val_fit = val_all[val_all[PRIMARY_LABEL_COL].notna()]

    X_train = train_fit[["map"]]
    y_train = train_fit[PRIMARY_LABEL_COL]
    fitted = models.fit_logistic(X_train, y_train)
    calibrated = models.calibrate_on_validation(fitted, val_fit[["map"]], val_fit[PRIMARY_LABEL_COL])

    val_all["model_risk"] = calibrated.predict_proba(val_all[["map"]])[:, 1]
    test_all["model_risk"] = calibrated.predict_proba(test_all[["map"]])[:, 1]

    print("Computing event lists + cleaned vitals for test cases...")
    case_events, case_vitals = build_case_events(test_ids, cases_df)

    case_dfs_val = {cid: g for cid, g in val_all.groupby(config.COL_CASEID)}
    val_events, _ = build_case_events(val_ids, cases_df)
    thr, val_fa = alarms.find_threshold_for_target_fa_rate(case_dfs_val, val_events, "model_risk", config.ALARM_OPERATING_POINT_FA_PER_PATIENT_HOUR)
    print(f"Operating threshold (from validation): {thr:.4f} (val FA={val_fa:.3f}/hr)")

    case_dfs_test = {cid: g for cid, g in test_all.groupby(config.COL_CASEID)}
    case_alerts_test = {cid: alarms.generate_case_alerts(case_dfs_test[cid], "model_risk", thr) for cid in test_ids if cid in case_dfs_test}

    # ---- Reliability ----
    reliability = metrics.reliability_curve(test_all[PRIMARY_LABEL_COL], test_all["model_risk"])
    secondary = metrics.auroc_auprc_brier(test_all[PRIMARY_LABEL_COL], test_all["model_risk"])
    plot_reliability(reliability, "b2_alone", secondary["brier"], ROOT / "artifacts" / "phase4_v2_reliability_plot.png")

    # ---- Horizon sweep, same fixed alert stream ----
    print("\n--- Sensitivity across horizons (same alert stream, threshold fixed at H=15/1 FA-per-hr) ---")
    horizon_results = {}
    for h in config.HORIZON_MIN_OPTIONS:
        sens_result = metrics.event_sensitivity_and_lead_times(case_events, case_alerts_test, test_ids, h)
        lead_summary = metrics.lead_time_summary(sens_result["lead_times_s"])
        horizon_results[h] = {"sensitivity": sens_result["sensitivity"], "n_events": sens_result["n_events"],
                               "n_detected": sens_result["n_detected"], "lead_time": lead_summary}
        print(f"  H={h}min: sensitivity={sens_result['sensitivity']:.3f} ({sens_result['n_detected']}/{sens_result['n_events']}), "
              f"lead_median_min={lead_summary['median_s']/60:.2f}" if lead_summary["median_s"] == lead_summary["median_s"] else "  n/a")

    # ---- Subgroup: gradual vs abrupt decline into each event ----
    print("\n--- Subgroup: gradual vs. abrupt MAP decline into the event ---")
    event_rows = []
    for caseid, events in case_events.items():
        cleaned = case_vitals[caseid]
        row = cases_df.loc[cases_df[config.COL_CASEID] == caseid].iloc[0]
        baseline = features.compute_patient_baseline(cleaned, float(row[config.COL_ANESTART]), op_start_s=float(row[config.COL_OPSTART]))
        op_start_s, op_end_s = float(row[config.COL_OPSTART]), float(row[config.COL_OPEND])
        for e_start in events:
            feat = features.compute_window_features(cleaned, e_start, baseline)
            if feat is None:
                continue
            qualifying = [a for a in case_alerts_test.get(caseid, []) if a < e_start <= a + config.HORIZON_MIN_PRIMARY * 60.0]
            event_rows.append({
                "caseid": caseid, "event_start_s": e_start,
                "map_slope_15_at_onset": feat["map_slope_15"],
                "position_in_op": (e_start - op_start_s) / (op_end_s - op_start_s) if op_end_s > op_start_s else float("nan"),
                "detected": len(qualifying) > 0,
            })
    events_df = pd.DataFrame(event_rows).dropna(subset=["map_slope_15_at_onset"])

    median_slope = events_df["map_slope_15_at_onset"].median()
    events_df["decline_group"] = np.where(events_df["map_slope_15_at_onset"] <= median_slope, "abrupt(steeper half)", "gradual(shallower half)")
    decline_sens = events_df.groupby("decline_group")["detected"].agg(["mean", "count"])
    print(f"Median map_slope_15 at event onset (split point): {median_slope:.3f} mmHg/min")
    print(decline_sens)

    median_pos = events_df["position_in_op"].median()
    events_df["timing_group"] = np.where(events_df["position_in_op"] <= median_pos, "early(first half)", "late(second half)")
    timing_sens = events_df.groupby("timing_group")["detected"].agg(["mean", "count"])
    print(f"\nMedian event position in op window (split point): {median_pos:.3f}")
    print(timing_sens)

    # ---- Append to metrics_v2.json ----
    v2 = json.loads(METRICS_V2_JSON.read_text())
    v2["reliability_curve"] = reliability
    v2["horizon_sweep"] = {str(k): v for k, v in horizon_results.items()}
    v2["subgroup_decline_steepness"] = {
        "median_split_mmhg_per_min": float(median_slope),
        "groups": decline_sens.reset_index().to_dict(orient="records"),
    }
    v2["subgroup_timing_in_op"] = {
        "median_split_fraction": float(median_pos),
        "groups": timing_sens.reset_index().to_dict(orient="records"),
    }
    METRICS_V2_JSON.write_text(json.dumps(v2, indent=2, default=lambda x: None))
    print(f"\nUpdated {METRICS_V2_JSON}")


if __name__ == "__main__":
    main()
