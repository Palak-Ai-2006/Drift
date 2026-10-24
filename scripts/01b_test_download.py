#!/usr/bin/env python
"""Phase 1, step 5: test on 5 cases — fetch, keep numeric tracks, resample to
30s, print size/time per case, extrapolate before any bulk download.

Case ids are sampled deterministically (config.RANDOM_SEED) from the
arterial-line subset of data/interim/inventory.parquet, built in
scripts/01_fetch.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from drift import config, vitaldb_io  # noqa: E402


def main() -> None:
    inv = pd.read_parquet(vitaldb_io.INVENTORY_PARQUET)
    arterial = inv[inv["has_arterial_line"] == True]  # noqa: E712
    sample = arterial.sample(n=config.PHASE1_TEST_CASE_COUNT, random_state=config.RANDOM_SEED)
    caseids = sample[config.COL_CASEID].tolist()
    print(f"Testing download on {len(caseids)} cases (seed={config.RANDOM_SEED}): {caseids}")

    report = vitaldb_io.test_download_n_cases(caseids)
    print("\nPer-case report:")
    print(report.to_string(index=False))

    out = Path(__file__).resolve().parents[1] / "artifacts" / "phase1_download_test_report.csv"
    report.to_csv(out, index=False)
    print(f"\nSaved report to {out}")


if __name__ == "__main__":
    main()
