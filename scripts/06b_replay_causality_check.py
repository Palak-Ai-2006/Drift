#!/usr/bin/env python
"""Phase 6.1 accept criterion: re-derive risk at 20 sampled timepoints from
data TRUNCATED to Time <= t and confirm it matches the risk already
exported in web/data/replay_cases.js. Proves the exported risk values
never used information from after their own timestamp (Adjustment A3),
independent of (and in addition to) tests/test_features.py's general
causality tests.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import config, models, vitaldb_io  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPLAY_CASES_JS = ROOT / "web" / "data" / "replay_cases.js"
WINDOWS_PARQUET = ROOT / "data" / "processed" / "windows.parquet"
METRICS_V2_JSON = ROOT / "artifacts" / "metrics_v2.json"
PRIMARY_LABEL_COL = f"label_h{config.HORIZON_MIN_PRIMARY}"
N_CHECK = 20


def load_replay_cases() -> list[dict]:
    text = REPLAY_CASES_JS.read_text()
    json_part = text[len("window.DRIFT_CASES = "):].rstrip().rstrip(";")
    return json.loads(json_part)


def refit_shipped_model(cases_df: pd.DataFrame):
    windows_df = pd.read_parquet(WINDOWS_PARQUET)
    all_caseids = sorted(windows_df[config.COL_CASEID].unique().tolist())
    split = models.split_cases(cases_df, all_caseids)
    train_ids = [c for c in all_caseids if split[c] == "train"]
    val_ids = [c for c in all_caseids if split[c] == "val"]
    train_fit = windows_df[windows_df[config.COL_CASEID].isin(train_ids) & windows_df[PRIMARY_LABEL_COL].notna()]
    val_fit = windows_df[windows_df[config.COL_CASEID].isin(val_ids) & windows_df[PRIMARY_LABEL_COL].notna()]
    fitted = models.fit_logistic(train_fit[["map"]], train_fit[PRIMARY_LABEL_COL])
    return models.calibrate_on_validation(fitted, val_fit[["map"]], val_fit[PRIMARY_LABEL_COL])


def main() -> None:
    print("=== Phase 6.1 causality check: re-derive risk from truncated data ===")
    cases = load_replay_cases()
    cases_df = vitaldb_io.load_case_table()
    calibrated = refit_shipped_model(cases_df)

    rng = np.random.RandomState(config.RANDOM_SEED)
    samples = []
    for c in cases:
        for t, r in zip(c["risk_t"], c["risk"]):
            samples.append((c["caseid"], t, r))
    if len(samples) > N_CHECK:
        idx = rng.choice(len(samples), size=N_CHECK, replace=False)
        samples = [samples[i] for i in idx]
    print(f"Checking {len(samples)} sampled (caseid, t) points...")

    n_ok, n_bad = 0, 0
    for caseid, t, exported_risk in samples:
        cleaned = vitaldb_io.load_and_clean_case(int(caseid))
        truncated = cleaned[cleaned["Time"] <= t]  # the whole point: discard everything after t
        if len(truncated) == 0:
            print(f"  caseid={caseid} t={t}: no data at or before t -- skipping")
            continue
        map_at_t = truncated.sort_values("Time").iloc[-1][config.TRACK_MAP]
        recomputed_risk = float(calibrated.predict_proba(pd.DataFrame({"map": [map_at_t]}))[:, 1][0])
        # web/data/replay_cases.js rounds risk to 4 decimals on export
        # (scripts/06_export_replay.py); match at that precision, not
        # floating-point exactness.
        match = abs(round(recomputed_risk, 4) - exported_risk) < 1e-9
        status = "OK" if match else "MISMATCH"
        if not match:
            n_bad += 1
            print(f"  caseid={caseid} t={t}: exported={exported_risk:.6f} recomputed={recomputed_risk:.6f} -- {status}")
        else:
            n_ok += 1

    print(f"\n{n_ok}/{n_ok + n_bad} matched exactly.")
    if n_bad:
        raise SystemExit(f"Causality check FAILED: {n_bad} mismatches.")
    print("Causality check PASSED.")


if __name__ == "__main__":
    main()
