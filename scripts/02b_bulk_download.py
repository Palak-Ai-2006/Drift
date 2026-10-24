#!/usr/bin/env python
"""Phase 2 bulk download: fetch numeric-track vitals for the selected
300-500 case sample (cohort.select_bulk_download_sample), so Phase 2's
vitals-based eligibility and Phase 2/3's real event counts can finally be
computed. Authorized at event start (2026-10-24) -- see CLAUDE.md.

Caches each case under data/raw/{caseid}_numeric_30s.parquet and never
re-downloads a cached case. Safe to re-run: already-cached cases are
skipped, so this can resume a partial run.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import cohort, config, vitaldb_io  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
COHORT_PRELIMINARY = ROOT / "data" / "interim" / "cohort_preliminary.parquet"
SELECTION_CSV = ROOT / "data" / "interim" / "bulk_download_selection.csv"
REPORT_CSV = ROOT / "artifacts" / "phase2_bulk_download_report.csv"


def main() -> None:
    print("=== Phase 2 bulk download ===")
    cohort_df = pd.read_parquet(COHORT_PRELIMINARY)
    print(f"Loaded preliminary cohort table: {len(cohort_df)} rows.")

    selection = cohort.select_bulk_download_sample(cohort_df)
    n_high_loss = int((selection["selection_group"] == "high_loss_or_transfused").sum())
    n_random = int((selection["selection_group"] == "random_arterial_line").sum())
    print(f"\nSelected {len(selection)} cases:")
    print(f"  high_loss_or_transfused: {n_high_loss}")
    print(f"  random_arterial_line:    {n_random}")

    SELECTION_CSV.parent.mkdir(parents=True, exist_ok=True)
    selection.to_csv(SELECTION_CSV, index=False)
    print(f"Saved selection to {SELECTION_CSV}")

    caseids = selection[config.COL_CASEID].tolist()
    print(f"\nDownloading/verifying {len(caseids)} cases (cached ones are skipped)...")
    report = vitaldb_io.bulk_download_numeric_tracks(caseids)

    REPORT_CSV.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(REPORT_CSV, index=False)

    ok = report[report["ok"]] if "ok" in report.columns and report["ok"].any() else report.iloc[0:0]
    failed = report[~report["ok"]] if "ok" in report.columns else report
    n_newly_downloaded = int((~ok["cached"]).sum()) if len(ok) else 0
    n_already_cached = int(ok["cached"].sum()) if len(ok) else 0
    total_bytes = int(ok["bytes"].sum()) if len(ok) else 0

    print(f"\n--- Bulk download report ---")
    print(f"Requested: {len(caseids)}")
    print(f"Succeeded: {len(ok)} ({n_already_cached} already cached, {n_newly_downloaded} newly downloaded)")
    print(f"Failed:    {len(failed)}")
    if len(failed):
        print("Failed caseids:", failed["caseid"].tolist())
    print(f"Total size on disk (succeeded cases): {total_bytes / 1e6:.2f} MB")
    print(f"\nSaved report to {REPORT_CSV}")
    print(
        "\nNext: run per-case preprocess.reject_artifacts + cohort.usable_monitored_minutes "
        "over these cached files to finalize vitals-based eligibility and real event counts."
    )


if __name__ == "__main__":
    main()
