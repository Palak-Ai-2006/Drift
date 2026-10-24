#!/usr/bin/env python
"""Phase 2 finalization: run the vitals-based eligibility criterion and the
primary event detector over the real downloaded 500-case sample
(data/raw/, selected by scripts/02b_bulk_download.py), to get real
eligible-case / event counts, build the final cohort.parquet, and evaluate
the Phase 1 decision-gate tier (PLAN.md Section 6, "Decision gate hour ~3").

Scope: cohort.parquet here covers ONLY the 500 selected+downloaded cases,
not all 3,419 clinically-eligible cases in the full clinical table -- we
only have real vitals for the sample, and the sample IS the dataset Phase
3/4 train and evaluate on (PLAN.md Phase 1 step 5: "target 300-500 cases").

Time alignment: cases.csv's anestart/opstart/opend are "seconds from
casestart", and clinical_parameters.csv defines casestart as "Recording
Start Time; Set to 0 for anonymization" -- i.e. casestart IS the first
sample of the downloaded vitals file. So Time - Time.min() in each
downloaded parquet is on the exact same clock as anestart/opstart/opend.
Never assumed without checking data/manual/clinical_parameters.csv.

Event-counting window: restricted to [opstart, opend] (the operation
window), same bound usable_monitored_minutes() applies -- a case's
recording can extend before/after the operation itself, and the project's
claims are about intraoperative monitoring. The induction-hypotension
exclusion window (first 15 min after anesthesia start) is NOT applied to
raw event counting here; it's an eligibility/baseline-period concept
(PLAN.md Phase 2 "exclusion window"), and Phase 3 is where per-prediction
exclusions near the event boundary happen. Counting here is deliberately
the plain MAP<65-for-60s detector over the full monitored op window.
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import cohort, config, labels, vitaldb_io  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
COHORT_PRELIMINARY = ROOT / "data" / "interim" / "cohort_preliminary.parquet"
SELECTION_CSV = ROOT / "data" / "interim" / "bulk_download_selection.csv"
COHORT_FINAL_PARQUET = ROOT / "data" / "interim" / "cohort.parquet"
FUNNEL_JSON = ROOT / "artifacts" / "phase2_final_funnel.json"


def _case_row(cases_df: pd.DataFrame, caseid: int) -> pd.Series:
    rows = cases_df.loc[cases_df[config.COL_CASEID] == caseid]
    if len(rows) != 1:
        raise ValueError(f"Expected exactly one clinical-table row for caseid {caseid}, found {len(rows)}")
    return rows.iloc[0]


def process_one_case(caseid: int, cases_df: pd.DataFrame) -> dict:
    cleaned = vitaldb_io.load_and_clean_case(caseid, dest_dir=DATA_RAW)

    row = _case_row(cases_df, caseid)
    anestart_s = float(row[config.COL_ANESTART])
    opstart_s = float(row[config.COL_OPSTART])
    opend_s = float(row[config.COL_OPEND])

    usable_min = cohort.usable_monitored_minutes(
        cleaned, anesthesia_start_s=anestart_s, op_start_s=opstart_s, op_end_s=opend_s,
    )
    eligible_vitals = usable_min >= config.ELIGIBLE_MIN_MONITORED_MIN_AFTER_EXCLUSION

    op_window = cleaned[(cleaned["Time"] >= opstart_s) & (cleaned["Time"] <= opend_s)]
    events = labels.detect_primary_events(op_window)

    return {
        "caseid": caseid,
        "usable_monitored_min": usable_min,
        "eligible_vitals": eligible_vitals,
        "n_primary_events": len(events),
    }


def main() -> None:
    print("=== Phase 2 finalization: vitals-based eligibility + real event counts ===")
    cases_df = vitaldb_io.load_case_table()
    cohort_preliminary = pd.read_parquet(COHORT_PRELIMINARY)
    selection = pd.read_csv(SELECTION_CSV)
    caseids = selection[config.COL_CASEID].tolist()
    print(f"Processing {len(caseids)} cases from the bulk-download sample...")

    rows = []
    errors = []
    for i, cid in enumerate(caseids, start=1):
        try:
            rows.append(process_one_case(cid, cases_df))
        except Exception as exc:  # noqa: BLE001 - one bad case must not abort the run
            errors.append({"caseid": cid, "error": str(exc)})
        if i % 100 == 0:
            print(f"  ... {i}/{len(caseids)} processed")

    if errors:
        print(f"\n{len(errors)} case(s) failed to process:")
        for e in errors:
            print(f"  {e['caseid']}: {e['error']}")

    per_case = pd.DataFrame(rows)
    final = cohort_preliminary.merge(per_case, on=config.COL_CASEID, how="inner")
    final = final.merge(selection, on=config.COL_CASEID, how="left")

    final["eligible_final"] = final["clinical_eligible"] & final["eligible_vitals"]

    # Recompute Cohort B against the FINAL eligible mask, scoped to this sample.
    eligible_mask_full = pd.Series(False, index=cases_df.index)
    sampled_idx = cases_df.index[cases_df[config.COL_CASEID].isin(final.loc[final["eligible_final"], config.COL_CASEID])]
    eligible_mask_full.loc[sampled_idx] = True
    cohort_b_result = cohort.assign_cohort_b(cases_df, eligible_mask_full)

    final_caseid_to_cohort_b = dict(zip(
        cases_df.loc[cohort_b_result.membership, config.COL_CASEID], [True] * int(cohort_b_result.membership.sum()),
    ))
    final["cohort_b_final"] = final[config.COL_CASEID].map(lambda c: final_caseid_to_cohort_b.get(c, False))

    final.attrs["is_final"] = True
    final.attrs["scope"] = (
        f"Only the {len(caseids)}-case bulk-download sample (data/interim/bulk_download_selection.csv), "
        "not all 3,419 clinically-eligible cases in the full clinical table."
    )

    COHORT_FINAL_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    final.to_parquet(COHORT_FINAL_PARQUET, index=False)

    n_sampled = len(final)
    n_clinical_eligible = int(final["clinical_eligible"].sum())
    n_vitals_eligible = int(final["eligible_vitals"].sum())
    n_final_eligible = int(final["eligible_final"].sum())
    n_cohort_b_final = int(cohort_b_result.n_cohort_b)
    total_events_final_eligible = int(final.loc[final["eligible_final"], "n_primary_events"].sum())
    total_events_all_sampled = int(final["n_primary_events"].sum())

    if n_final_eligible >= config.DECISION_GATE_TIER1_MIN_CASES and total_events_final_eligible >= config.DECISION_GATE_TIER1_MIN_EVENTS:
        tier = "Tier 1: proceed as planned"
    elif n_final_eligible >= config.DECISION_GATE_TIER2_MIN_CASES or total_events_final_eligible >= config.DECISION_GATE_TIER2_MIN_EVENTS:
        tier = "Tier 2: proceed with fallback/caveats, wide-CI warning"
    else:
        tier = "Tier 3: pivot to simulator-first, no performance claims"

    print("\n--- Final Phase 2 funnel (scope: 500-case sample only) ---")
    print(f"Sampled (downloaded):               {n_sampled}")
    print(f"Clinical-eligible (age+arterial):   {n_clinical_eligible}")
    print(f"Vitals-eligible (>=60min usable):   {n_vitals_eligible}")
    print(f"FINAL eligible (both):              {n_final_eligible}")
    print(f"Cohort B (final):                   {n_cohort_b_final}")
    print(f"Primary events (MAP<65/60s), final-eligible cases only: {total_events_final_eligible}")
    print(f"Primary events, all {n_sampled} sampled cases (for reference): {total_events_all_sampled}")
    print(f"\nDecision gate (hour ~3): {tier}")

    summary = {
        "n_sampled": n_sampled,
        "n_clinical_eligible": n_clinical_eligible,
        "n_vitals_eligible": n_vitals_eligible,
        "n_final_eligible": n_final_eligible,
        "n_cohort_b_final": n_cohort_b_final,
        "cohort_b_rule_used": cohort_b_result.rule_used,
        "total_primary_events_final_eligible": total_events_final_eligible,
        "total_primary_events_all_sampled": total_events_all_sampled,
        "decision_gate_tier": tier,
        "n_processing_errors": len(errors),
        "scope_note": final.attrs["scope"],
    }
    FUNNEL_JSON.parent.mkdir(parents=True, exist_ok=True)
    FUNNEL_JSON.write_text(json.dumps(summary, indent=2))
    print(f"\nSaved funnel summary to {FUNNEL_JSON}")
    print(f"Saved final cohort table to {COHORT_FINAL_PARQUET}")


if __name__ == "__main__":
    main()
