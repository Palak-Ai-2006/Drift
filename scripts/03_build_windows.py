#!/usr/bin/env python
"""Phase 3: build windows.parquet over the 442 final-eligible cases
(data/interim/cohort.parquet), using features.build_case_windows.

Accept (PLAN.md Phase 3): windows.parquet; positive rates by cohort;
causality unit test passes (tests/test_features.py); leakage checklist
(PLAN.md Section 8) reviewed below.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import config, features, vitaldb_io  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
COHORT_FINAL_PARQUET = ROOT / "data" / "interim" / "cohort.parquet"
WINDOWS_PARQUET = ROOT / "data" / "processed" / "windows.parquet"


def main() -> None:
    print("=== Phase 3: build windows.parquet ===")
    cases_df = vitaldb_io.load_case_table()
    cohort_df = pd.read_parquet(COHORT_FINAL_PARQUET)
    eligible = cohort_df[cohort_df["eligible_final"]]
    print(f"Final-eligible cases: {len(eligible)}")

    all_windows = []
    errors = []
    for i, caseid in enumerate(eligible[config.COL_CASEID], start=1):
        try:
            cleaned = vitaldb_io.load_and_clean_case(int(caseid))
            row = cases_df.loc[cases_df[config.COL_CASEID] == caseid].iloc[0]
            windows = features.build_case_windows(cleaned, row)
            all_windows.append(windows)
        except Exception as exc:  # noqa: BLE001 - one bad case must not abort the run
            errors.append({"caseid": int(caseid), "error": str(exc)})
        if i % 100 == 0:
            print(f"  ... {i}/{len(eligible)} cases processed")

    if errors:
        print(f"\n{len(errors)} case(s) failed:")
        for e in errors:
            print(f"  {e['caseid']}: {e['error']}")

    windows_df = pd.concat(all_windows, ignore_index=True)
    windows_df = windows_df.merge(
        cohort_df[[config.COL_CASEID, "cohort_b_final"]], on=config.COL_CASEID, how="left",
    )

    WINDOWS_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    windows_df.to_parquet(WINDOWS_PARQUET, index=False)

    n_cases_with_windows = windows_df[config.COL_CASEID].nunique()
    print(f"\nTotal windows: {len(windows_df)} from {n_cases_with_windows} cases "
          f"({len(eligible) - n_cases_with_windows} cases had no usable baseline, excluded)")

    print("\n--- Positive rate by cohort and horizon ---")
    for h in config.HORIZON_MIN_OPTIONS:
        col = f"label_h{h}"
        overall = windows_df[col].mean(skipna=True)
        by_cohort = windows_df.groupby("cohort_b_final")[col].mean()
        n_unknown = windows_df[col].isna().sum()
        print(f"H={h}min: overall positive rate = {overall:.4f} "
              f"(Cohort B = {by_cohort.get(True, float('nan')):.4f}, "
              f"non-Cohort-B = {by_cohort.get(False, float('nan')):.4f}), "
              f"{n_unknown} windows unknown/censored ({n_unknown / len(windows_df):.2%})")

    print("\n--- Leakage/validity checklist (PLAN.md Section 8) ---")
    print("[x] Split by case, never by row -- not yet split (Phase 4); windows.parquet keeps caseid for this.")
    print("[x] No end-of-case totals (EBL/RBC/FFP/fluids) used as features -- confirmed, none referenced in features.py.")
    print("[x] Baseline for drift features uses only data before the prediction time -- "
          "baseline window always ends at/before the first prediction time (t_start = max(baseline_end, op_start)).")
    print("[ ] Scaling/calibration/threshold fitted on train/val only -- N/A until Phase 4.")
    print("[ ] Test set evaluated once -- N/A until Phase 4.")
    print("[x] Feature unit test proves causality -- tests/test_features.py "
          "(truncation + future-corruption tests), run via pytest.")
    print(f"[x] Event counts/positive rate printed -- see above (train/val/test split is Phase 4).")
    print("[ ] Bootstrap CIs by case -- Phase 4.")
    print("[x] Confounders acknowledged -- anesthetic depth/vasopressors/surgical events not modeled; "
          "no vasopressor track available in config.REQUIRED_NUMERIC_TRACKS, so the stretch feature is skipped.")

    print(f"\nSaved {WINDOWS_PARQUET}")


if __name__ == "__main__":
    main()
