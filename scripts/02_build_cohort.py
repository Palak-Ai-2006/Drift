#!/usr/bin/env python
"""Phase 2, clinical-table-derivable portion: eligibility (age + arterial
line), the funnel, and a preliminary Cohort B check using that partial
eligibility as a stand-in.

NOT the final cohort.parquet -- the real eligibility definition also needs
>=60min usable monitoring after the exclusion window, which needs real
per-case vitals (bulk download, still gated per Decision 1). See
cohort.py's module docstring and HANDOFF.md.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import cohort, vitaldb_io  # noqa: E402


def main() -> None:
    print("=== Phase 2 (clinical-table-derivable portion only) ===")
    cases_df = vitaldb_io.load_case_table()
    print(f"Loaded {len(cases_df)} cases.")

    elig = cohort.clinical_table_eligibility(cases_df)
    funnel = cohort.clinical_eligibility_funnel(elig)
    print("\n--- Clinical-table eligibility funnel ---")
    for k, v in funnel.items():
        print(f"  {k}: {v}")

    table = cohort.build_cohort_table(cases_df, elig)
    print(f"\nCohort A (clinical_eligible proxy): {int(table['cohort_a'].sum())}")
    print(f"Cohort B: {int(table['cohort_b'].sum())} (rule used: {table['cohort_b_rule_used'].iloc[0]})")
    print(f"\nFinal: {table.attrs['is_final']}")
    print(f"Pending: {table.attrs['pending']}")

    out = Path(__file__).resolve().parents[1] / "data" / "interim" / "cohort_preliminary.parquet"
    table.to_parquet(out, index=False)
    print(f"\nSaved preliminary cohort table to {out}")


if __name__ == "__main__":
    main()
