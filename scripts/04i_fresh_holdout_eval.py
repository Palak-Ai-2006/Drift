#!/usr/bin/env python
"""Phase 4 iteration round 3, clean holdout steps 3-5 (ACTIONS.md): build
the same eligibility/cohort/windows pipeline for the 175 never-before-used
cases, then evaluate the standing model (b2_alone, the undefeated champion
of v2/Experiment 2/round 3's primary task -- nothing beat it) EXACTLY ONCE.

Uses the EXACT already-fitted v2 model (same train/val cases, same
threshold chosen on the original validation set) -- no refitting, no new
tuning, so this is a genuinely clean generalization check, not a second
chance to pick a better threshold.
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import alarms, cohort, config, features, labels, metrics, models, vitaldb_io  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
HOLDOUT_SELECTION_CSV = ROOT / "data" / "interim" / "fresh_holdout_selection.csv"
HOLDOUT_COHORT_PARQUET = ROOT / "data" / "interim" / "fresh_holdout_cohort.parquet"
HOLDOUT_WINDOWS_PARQUET = ROOT / "data" / "processed" / "fresh_holdout_windows.parquet"
RESULTS_JSON = ROOT / "artifacts" / "phase4_round3_fresh_holdout_results.json"
WINDOWS_PARQUET = ROOT / "data" / "processed" / "windows.parquet"
METRICS_V2_JSON = ROOT / "artifacts" / "metrics_v2.json"

PRIMARY_LABEL_COL = f"label_h{config.HORIZON_MIN_PRIMARY}"


def build_holdout_cohort(caseids: list[int], cases_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for i, caseid in enumerate(caseids, start=1):
        cleaned = vitaldb_io.load_and_clean_case(int(caseid))
        row = cases_df.loc[cases_df[config.COL_CASEID] == caseid].iloc[0]
        anestart_s, opstart_s, opend_s = float(row[config.COL_ANESTART]), float(row[config.COL_OPSTART]), float(row[config.COL_OPEND])
        usable_min = cohort.usable_monitored_minutes(cleaned, anesthesia_start_s=anestart_s, op_start_s=opstart_s, op_end_s=opend_s)
        eligible_vitals = usable_min >= config.ELIGIBLE_MIN_MONITORED_MIN_AFTER_EXCLUSION
        rows.append({config.COL_CASEID: caseid, "usable_monitored_min": usable_min, "eligible_final": eligible_vitals})
        if i % 50 == 0:
            print(f"  ... {i}/{len(caseids)} eligibility computed")
    df = pd.DataFrame(rows)

    eligible_mask_full = pd.Series(False, index=cases_df.index)
    eligible_caseids = set(df.loc[df["eligible_final"], config.COL_CASEID])
    eligible_mask_full.loc[cases_df[config.COL_CASEID].isin(eligible_caseids).to_numpy()] = True
    cohort_b_result = cohort.assign_cohort_b(cases_df, eligible_mask_full)
    cohort_b_ids = set(cases_df.loc[cohort_b_result.membership, config.COL_CASEID])
    df["cohort_b_final"] = df[config.COL_CASEID].isin(cohort_b_ids)
    print(f"  Eligible: {df['eligible_final'].sum()}/{len(df)}; Cohort B: {df['cohort_b_final'].sum()} "
          f"(rule: {cohort_b_result.rule_used})")
    return df


def build_holdout_windows(eligible_caseids: list[int], cases_df: pd.DataFrame) -> pd.DataFrame:
    all_windows = []
    for i, caseid in enumerate(eligible_caseids, start=1):
        cleaned = vitaldb_io.load_and_clean_case(int(caseid))
        row = cases_df.loc[cases_df[config.COL_CASEID] == caseid].iloc[0]
        windows = features.build_case_windows(cleaned, row)
        all_windows.append(windows)
        if i % 50 == 0:
            print(f"  ... {i}/{len(eligible_caseids)} cases windowed")
    return pd.concat(all_windows, ignore_index=True) if all_windows else pd.DataFrame()


def build_case_events(caseids, cases_df):
    out = {}
    for caseid in caseids:
        cleaned = vitaldb_io.load_and_clean_case(int(caseid))
        row = cases_df.loc[cases_df[config.COL_CASEID] == caseid].iloc[0]
        op_window = cleaned[(cleaned["Time"] >= row[config.COL_OPSTART]) & (cleaned["Time"] <= row[config.COL_OPEND])]
        events = labels.detect_primary_events(op_window)
        out[caseid] = sorted(e.start_time for e in events)
    return out


def main() -> None:
    print("=== Round 3 clean holdout: build pipeline + evaluate the standing model (b2_alone) once ===")
    cases_df = vitaldb_io.load_case_table()
    holdout_ids = pd.read_csv(HOLDOUT_SELECTION_CSV)[config.COL_CASEID].tolist()
    print(f"Holdout cases: {len(holdout_ids)}")

    print("\nBuilding eligibility + Cohort B for the holdout...")
    holdout_cohort = build_holdout_cohort(holdout_ids, cases_df)
    HOLDOUT_COHORT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    holdout_cohort.to_parquet(HOLDOUT_COHORT_PARQUET, index=False)

    eligible_ids = holdout_cohort.loc[holdout_cohort["eligible_final"], config.COL_CASEID].tolist()
    cohort_b_ids = set(holdout_cohort.loc[holdout_cohort["cohort_b_final"], config.COL_CASEID])

    print(f"\nBuilding windows for {len(eligible_ids)} eligible holdout cases...")
    holdout_windows = build_holdout_windows(eligible_ids, cases_df)
    HOLDOUT_WINDOWS_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    holdout_windows.to_parquet(HOLDOUT_WINDOWS_PARQUET, index=False)
    print(f"Total holdout windows: {len(holdout_windows)} from {holdout_windows[config.COL_CASEID].nunique()} cases")

    print("\nComputing real events for the holdout cases...")
    case_events = build_case_events(eligible_ids, cases_df)
    n_events = sum(len(v) for v in case_events.values())
    print(f"Total primary events in holdout: {n_events}")

    print("\n--- Refitting the EXACT v2 recipe (b2_alone: MAP-only logistic, same train/val, same threshold) ---")
    all_original_caseids = sorted(pd.read_parquet(WINDOWS_PARQUET)[config.COL_CASEID].unique().tolist())
    split = models.split_cases(cases_df, all_original_caseids)
    train_ids = [c for c in all_original_caseids if split[c] == "train"]
    original_windows = pd.read_parquet(WINDOWS_PARQUET)
    train_fit = original_windows[original_windows[config.COL_CASEID].isin(train_ids) & original_windows[PRIMARY_LABEL_COL].notna()]
    fitted = models.fit_logistic(train_fit[["map"]], train_fit[PRIMARY_LABEL_COL])

    v2_meta = json.loads(METRICS_V2_JSON.read_text())
    threshold = v2_meta["val_operating_point"]["threshold"]
    print(f"Using v2's already-chosen operating threshold (no new tuning): {threshold}")

    val_ids = [c for c in all_original_caseids if split[c] == "val"]
    val_fit = original_windows[original_windows[config.COL_CASEID].isin(val_ids) & original_windows[PRIMARY_LABEL_COL].notna()]
    calibrated = models.calibrate_on_validation(fitted, val_fit[["map"]], val_fit[PRIMARY_LABEL_COL])

    holdout_windows = holdout_windows.copy()
    holdout_windows["model_risk"] = calibrated.predict_proba(holdout_windows[["map"]])[:, 1]

    case_dfs = {cid: g for cid, g in holdout_windows.groupby(config.COL_CASEID)}
    case_alerts = {cid: alarms.generate_case_alerts(case_dfs[cid], "model_risk", threshold) for cid in eligible_ids if cid in case_dfs}

    results_by_cohort = {}
    for cohort_name, cohort_ids in (("A", eligible_ids), ("B", [c for c in eligible_ids if c in cohort_b_ids])):
        sens_result = metrics.event_sensitivity_and_lead_times(case_events, case_alerts, cohort_ids, config.HORIZON_MIN_PRIMARY)
        lead_summary = metrics.lead_time_summary(sens_result["lead_times_s"])
        cohort_case_dfs = {cid: case_dfs[cid] for cid in cohort_ids if cid in case_dfs}
        fa_rate = alarms.false_alarm_rate_for_threshold(cohort_case_dfs, case_events, "model_risk", threshold, horizon_min=config.HORIZON_MIN_PRIMARY)
        results_by_cohort[cohort_name] = {
            "n_events": sens_result["n_events"], "n_detected": sens_result["n_detected"],
            "sensitivity": sens_result["sensitivity"], "lead_time": lead_summary, "fa_rate_per_hour": fa_rate,
        }
        print(f"  Cohort {cohort_name}: sensitivity={sens_result['sensitivity']:.3f} "
              f"({sens_result['n_detected']}/{sens_result['n_events']}), FA/hr={fa_rate:.3f}")

    secondary = metrics.auroc_auprc_brier(holdout_windows[PRIMARY_LABEL_COL], holdout_windows["model_risk"])
    print(f"  AUROC/AUPRC/Brier: {secondary}")

    RESULTS_JSON.write_text(json.dumps({
        "model": "b2_alone (exact v2 recipe, no refitting/re-tuning on this holdout)",
        "threshold_used": threshold,
        "n_holdout_cases_selected": len(holdout_ids),
        "n_holdout_cases_eligible": len(eligible_ids),
        "n_holdout_cases_cohort_b": len(cohort_b_ids),
        "n_holdout_events": n_events,
        "results_by_cohort": results_by_cohort,
        "secondary_metrics": secondary,
    }, indent=2, default=lambda x: None))
    print(f"\nSaved {RESULTS_JSON}")


if __name__ == "__main__":
    main()
