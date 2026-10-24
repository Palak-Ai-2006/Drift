#!/usr/bin/env python
"""Phase 4 iteration round 3, clean holdout step 1-2 (ACTIONS.md, locked
before this was written): the original 87-case test set has now been
looked at three times (original, v2, Experiment 2) -- no longer a clean
holdout. Select 175 never-before-downloaded, clinical-table-eligible
cases, run the 5-case timing test first (same pattern as Phase 1), then
bulk-download them.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import config, vitaldb_io  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
COHORT_PRELIMINARY = ROOT / "data" / "interim" / "cohort_preliminary.parquet"
EXISTING_SELECTION = ROOT / "data" / "interim" / "bulk_download_selection.csv"
HOLDOUT_SELECTION_CSV = ROOT / "data" / "interim" / "fresh_holdout_selection.csv"
HOLDOUT_REPORT_CSV = ROOT / "artifacts" / "phase4_round3_holdout_download_report.csv"

HOLDOUT_TARGET_N = 175  # middle of the requested 150-200


def main() -> None:
    print("=== Round 3 clean holdout: select + download never-before-used cases ===")
    cohort_preliminary = pd.read_parquet(COHORT_PRELIMINARY)
    eligible_pool = cohort_preliminary.loc[cohort_preliminary["clinical_eligible"], config.COL_CASEID]

    already_used = set(pd.read_csv(EXISTING_SELECTION)[config.COL_CASEID])
    already_used |= {6269, 757, 6293, 2911, 2349}  # original Phase 1 5-case timing test
    remaining_pool = eligible_pool[~eligible_pool.isin(already_used)]
    print(f"Clinical-eligible pool: {len(eligible_pool)}; already used (any round): {len(already_used)}; "
          f"never-touched remaining: {len(remaining_pool)}")

    selection = remaining_pool.sample(n=HOLDOUT_TARGET_N, random_state=config.RANDOM_SEED).sort_values()
    assert set(selection).isdisjoint(already_used), "holdout selection must never overlap any previously-used caseid"
    HOLDOUT_SELECTION_CSV.parent.mkdir(parents=True, exist_ok=True)
    selection.to_frame(name=config.COL_CASEID).to_csv(HOLDOUT_SELECTION_CSV, index=False)
    print(f"Selected {len(selection)} never-touched cases. Saved to {HOLDOUT_SELECTION_CSV}")

    print("\n--- 5-case timing test (same pattern as Phase 1) ---")
    test_sample = selection.sample(n=5, random_state=config.RANDOM_SEED).tolist()
    test_report = vitaldb_io.test_download_n_cases(test_sample)
    print(test_report)
    avg_s = test_report.loc[test_report["ok"], "seconds"].mean()
    if avg_s >= 15.0:
        raise SystemExit(f"5-case timing test averaged {avg_s:.2f}s/case (>=15s threshold) -- stopping before bulk download.")
    print(f"Average {avg_s:.2f}s/case, well under the 15s/case threshold -- proceeding to bulk download.")

    print(f"\n--- Bulk downloading all {len(selection)} cases (cached ones, including the 5 just tested, are skipped) ---")
    report = vitaldb_io.bulk_download_numeric_tracks(selection.tolist())
    HOLDOUT_REPORT_CSV.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(HOLDOUT_REPORT_CSV, index=False)
    ok = report[report["ok"]]
    print(f"Succeeded: {len(ok)}/{len(selection)}. Failed: {len(report) - len(ok)}.")
    if len(ok):
        print(f"Total size: {ok['bytes'].sum() / 1e6:.2f} MB")
    print(f"Saved {HOLDOUT_REPORT_CSV}")


if __name__ == "__main__":
    main()
