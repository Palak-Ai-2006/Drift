#!/usr/bin/env python
"""Phase 4 iteration, round 3, secondary task (rules locked in ACTIONS.md
before this was written). NOT a hemorrhage detector -- a compensation-state
flag, reported as such.

Label: sustained elevated shock index, operationalized as the first time a
trailing 5-minute rolling median of shock index (HR/SBP) reaches >= 0.9
(config.BASELINE_B3_SHOCK_INDEX_THRESHOLD) within the operation window.
Windows are labeled 1 if such an episode starts within the next 15 minutes,
0 if none does (and the case extends far enough to know), NaN if
right-censored (case ends before the horizon closes) -- same convention as
every other label in this project.

Predictors: age, height, weight, sex, MAP, pulse pressure ONLY -- no HR,
SBP, or shock-index-derived feature of any kind, so the model can't predict
the label from (thinly disguised) copies of itself.

3-fold grouped CV on train+val; reports ROC AUC +/- bootstrap-by-case 95% CI.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import config, labels, metrics, models, vitaldb_io  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WINDOWS_PARQUET = ROOT / "data" / "processed" / "windows.parquet"
RESULTS_JSON = ROOT / "artifacts" / "phase4_round3_secondary_shock_index.json"

HORIZON_MIN = config.HORIZON_MIN_PRIMARY
ROLLING_WINDOW_MIN = 5
SHOCK_INDEX_THRESHOLD = config.BASELINE_B3_SHOCK_INDEX_THRESHOLD
N_FOLDS = 3
LABEL_COL = "shock_index_flag"
FEATURES = (config.COL_AGE, config.COL_HEIGHT, config.COL_WEIGHT, "sex_encoded", "map", "pp")


def detect_rolling_shock_index_episodes(cleaned: pd.DataFrame, op_start_s: float, op_end_s: float) -> list[float]:
    """Start times of episodes where the trailing 5-min rolling median of
    shock index first reaches >= threshold, within the operation window."""
    op_window = cleaned[(cleaned["Time"] >= op_start_s) & (cleaned["Time"] <= op_end_s)].sort_values("Time")
    if len(op_window) == 0:
        return []
    shock_index = op_window[config.TRACK_HR] / op_window[config.TRACK_SBP]
    d = pd.DataFrame({"Time": op_window["Time"].to_numpy(), "shock_index": shock_index.to_numpy()})
    d["t_td"] = pd.to_timedelta(d["Time"], unit="s")
    d = d.set_index("t_td")
    rolling_median = d["shock_index"].rolling(f"{ROLLING_WINDOW_MIN}min").median()

    above = (rolling_median >= SHOCK_INDEX_THRESHOLD).to_numpy()
    times = d["Time"].to_numpy()
    episodes = []
    i, n = 0, len(above)
    while i < n:
        if not above[i]:
            i += 1
            continue
        episodes.append(times[i])
        while i < n and above[i]:  # skip the rest of this contiguous run
            i += 1
    return episodes


def label_for_t(t_s: float, op_end_s: float, episodes: list[float], horizon_min: float = HORIZON_MIN) -> float:
    horizon_end = t_s + horizon_min * 60.0
    if any(t_s < e <= horizon_end for e in episodes):
        return 1.0
    if op_end_s - t_s < horizon_min * 60.0:
        return float("nan")
    return 0.0


def build_labels(windows_df: pd.DataFrame, caseids: list[int], cases_df: pd.DataFrame) -> pd.Series:
    label = pd.Series(index=windows_df.index, dtype=float)
    n_episodes = 0
    for i, caseid in enumerate(caseids, start=1):
        cleaned = vitaldb_io.load_and_clean_case(int(caseid))
        row = cases_df.loc[cases_df[config.COL_CASEID] == caseid].iloc[0]
        op_start_s, op_end_s = float(row[config.COL_OPSTART]), float(row[config.COL_OPEND])
        episodes = detect_rolling_shock_index_episodes(cleaned, op_start_s, op_end_s)
        n_episodes += len(episodes)
        case_mask = windows_df[config.COL_CASEID] == caseid
        label.loc[case_mask] = windows_df.loc[case_mask, "t_s"].apply(lambda t: label_for_t(t, op_end_s, episodes))
        if i % 100 == 0:
            print(f"  ... {i}/{len(caseids)} cases labeled")
    print(f"  Total episodes: {n_episodes}")
    return label


def oof_predictions(dev_all_df: pd.DataFrame, dev_fit_df: pd.DataFrame, folds: list[list[int]]) -> pd.Series:
    oof = pd.Series(index=dev_all_df.index, dtype=float)
    for fold_ids in folds:
        fold_set = set(fold_ids)
        train_fit = dev_fit_df[~dev_fit_df[config.COL_CASEID].isin(fold_set)]
        held_out = dev_all_df[dev_all_df[config.COL_CASEID].isin(fold_set)]
        if len(held_out) == 0 or train_fit[LABEL_COL].nunique() < 2:
            continue
        model = models.fit_logistic(train_fit[list(FEATURES)], train_fit[LABEL_COL])
        oof.loc[held_out.index] = model.predict_proba(held_out[list(FEATURES)])[:, 1]
    return oof


def main() -> None:
    print("=== Phase 4 round 3, secondary task: sustained elevated shock index (compensation flag) ===")
    cases_df = vitaldb_io.load_case_table()
    windows_df = pd.read_parquet(WINDOWS_PARQUET)
    windows_df["sex_encoded"] = models.encode_sex(windows_df["sex"])
    windows_df = windows_df.merge(
        cases_df[[config.COL_CASEID, config.COL_HEIGHT, config.COL_WEIGHT]], on=config.COL_CASEID, how="left",
    )

    all_caseids = sorted(windows_df[config.COL_CASEID].unique().tolist())
    split = models.split_cases(cases_df, all_caseids)
    dev_ids = [c for c in all_caseids if split[c] in ("train", "val")]
    print(f"Dev (train+val): {len(dev_ids)} cases")

    dev_all_df = windows_df[windows_df[config.COL_CASEID].isin(dev_ids)].copy()
    print("\nBuilding labels (rolling 5-min median shock index >= 0.9)...")
    dev_all_df[LABEL_COL] = build_labels(dev_all_df, dev_ids, cases_df)
    dev_fit_df = dev_all_df[dev_all_df[LABEL_COL].notna()]
    print(f"Dev windows with known label: {len(dev_fit_df)} / {len(dev_all_df)} "
          f"(positive rate {dev_fit_df[LABEL_COL].mean():.4f})")

    folds = models.grouped_kfold_by_subject(cases_df, dev_ids, n_folds=N_FOLDS)
    print(f"\nGrouped {N_FOLDS}-fold CV: fold sizes = {[len(f) for f in folds]}")

    print("\nFitting (features: age, height, weight, sex, MAP, pulse pressure -- no HR/SBP/shock-index)...")
    dev_all_df["oof_risk"] = oof_predictions(dev_all_df, dev_fit_df, folds)
    scored = dev_all_df[dev_all_df[LABEL_COL].notna() & dev_all_df["oof_risk"].notna()]

    point_auc = roc_auc_score(scored[LABEL_COL], scored["oof_risk"])

    def auc_fn(sample_ids):
        rows = scored[scored[config.COL_CASEID].isin(set(sample_ids))]
        counts = pd.Series(sample_ids).value_counts()
        rows = pd.concat([rows[rows[config.COL_CASEID] == cid] for cid in counts.index for _ in range(counts[cid])], ignore_index=True)
        if rows[LABEL_COL].nunique() < 2:
            return float("nan")
        return roc_auc_score(rows[LABEL_COL], rows["oof_risk"])

    ci = metrics.bootstrap_ci_by_case(dev_ids, auc_fn, n_resamples=config.BOOTSTRAP_N_RESAMPLES)
    print(f"\nCV ROC AUC: {point_auc:.4f} (95% CI [{ci['ci_low']:.4f}, {ci['ci_high']:.4f}])")

    RESULTS_JSON.write_text(json.dumps({
        "label": "rolling_5min_median_shock_index_ge_0.9",
        "features": list(FEATURES),
        "dev_positive_rate": float(dev_fit_df[LABEL_COL].mean()),
        "n_dev_windows_scored": int(len(scored)),
        "cv_roc_auc": point_auc, "cv_roc_auc_ci": ci,
        "note": "Compensation-state flag, NOT a hemorrhage/bleeding detector -- never to be presented as evidence of bleeding.",
    }, indent=2, default=lambda x: None))
    print(f"Saved {RESULTS_JSON}")


if __name__ == "__main__":
    main()
