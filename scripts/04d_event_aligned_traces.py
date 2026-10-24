#!/usr/bin/env python
"""Phase 4 iteration, Experiment 1: event-aligned traces (descriptive only
-- no model, no tuning, no test set touched; train+val cases only).

For every real primary event in the 351 train+val cases, extract HR, MAP,
PP and shock index at 1-minute marks for the 30 minutes before event
onset (the most recent sample at or before each mark -- same "current
value" logic features.py uses, so this is directly comparable to what the
model sees). Aggregate by median trace, with a bootstrap-by-case band,
split two ways: Cohort B vs. not, and abrupt vs. gradual decline (same
median-slope split methodology as scripts/04c_v2_diagnostics.py, but
computed here on train+val events only, not reusing the test-set split).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import config, features, labels, models, vitaldb_io  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
COHORT_FINAL_PARQUET = ROOT / "data" / "interim" / "cohort.parquet"
MINUTES_BEFORE = 30


def trace_for_event(cleaned: pd.DataFrame, event_start_s: float) -> dict[int, dict]:
    """{minutes_before: {hr, map, pp, shock_index}} for m=0..MINUTES_BEFORE,
    each the most recent sample at or before (event_start - m*60s)."""
    out = {}
    for m in range(MINUTES_BEFORE + 1):
        t_s = event_start_s - m * 60.0
        d = cleaned[cleaned["Time"] <= t_s]
        if len(d) == 0:
            continue
        row = d.sort_values("Time").iloc[-1]
        hr, sbp, dbp, map_ = row[config.TRACK_HR], row[config.TRACK_SBP], row[config.TRACK_DBP], row[config.TRACK_MAP]
        pp = sbp - dbp if pd.notna(sbp) and pd.notna(dbp) else float("nan")
        shock_index = hr / sbp if pd.notna(hr) and pd.notna(sbp) and sbp != 0 else float("nan")
        out[m] = {"hr": hr, "map": map_, "pp": pp, "shock_index": shock_index}
    return out


def bootstrap_median_band(event_df: pd.DataFrame, value_col: str, case_col: str = "caseid", n_resamples: int = 500, seed: int = config.RANDOM_SEED):
    """Median trace + a bootstrap-by-case 95% band, per minutes_before bin.

    Avoids per-resample pd.concat (slow at this scale): precompute each
    case's row-index positions once, then each resample is just an index
    lookup + a single groupby-median over the gathered rows.
    """
    rng = np.random.RandomState(seed)
    caseids = event_df[case_col].unique()
    minutes = sorted(event_df["minutes_before"].unique())
    point = event_df.groupby("minutes_before")[value_col].median().reindex(minutes)

    case_to_positions = {c: np.asarray(idx) for c, idx in event_df.groupby(case_col).indices.items()}
    minutes_arr = event_df["minutes_before"].to_numpy()
    values_arr = event_df[value_col].to_numpy(dtype=float)

    boot = {m: [] for m in minutes}
    for _ in range(n_resamples):
        sample_cases = rng.choice(caseids, size=len(caseids), replace=True)
        positions = np.concatenate([case_to_positions[c] for c in sample_cases if c in case_to_positions])
        sample_minutes = minutes_arr[positions]
        sample_values = values_arr[positions]
        for m in minutes:
            vals = sample_values[sample_minutes == m]
            vals = vals[~np.isnan(vals)]
            if len(vals):
                boot[m].append(np.median(vals))

    lo = pd.Series({m: (np.percentile(v, 2.5) if v else np.nan) for m, v in boot.items()}).reindex(minutes)
    hi = pd.Series({m: (np.percentile(v, 97.5) if v else np.nan) for m, v in boot.items()}).reindex(minutes)
    return point, lo, hi


def plot_traces(event_df: pd.DataFrame, group_col: str, group_labels: dict, out_path: Path, title: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    variables = [("map", "MAP (mmHg)"), ("hr", "HR (bpm)"), ("pp", "Pulse pressure (mmHg)"), ("shock_index", "Shock index (HR/SBP)")]
    colors = {list(group_labels)[0]: config.WEB_COLOR_TRACE_MAP, list(group_labels)[1]: config.WEB_COLOR_TRACE_PP}

    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    for ax, (col, ylabel) in zip(axes.flat, variables):
        for group_val, label in group_labels.items():
            sub = event_df[event_df[group_col] == group_val]
            if sub.empty:
                continue
            point, lo, hi = bootstrap_median_band(sub, col)
            x = -point.index.to_numpy()  # minutes before event, negative so time flows left->right into 0
            ax.plot(x, point.to_numpy(), color=colors[group_val], label=f"{label} (n={sub['event_id'].nunique()})")
            ax.fill_between(x, lo.to_numpy(), hi.to_numpy(), color=colors[group_val], alpha=0.15)
        ax.axvline(0, color="#9BA7B4", linestyle="--", linewidth=1)
        ax.set_xlabel("Minutes before event onset")
        ax.set_ylabel(ylabel)
        ax.legend(loc="best", fontsize=8)
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    print(f"Saved {out_path}")


def main() -> None:
    print("=== Experiment 1: event-aligned traces (train+val only, descriptive) ===")
    cases_df = vitaldb_io.load_case_table()
    cohort_df = pd.read_parquet(COHORT_FINAL_PARQUET)
    windows_df_caseids = pd.read_parquet(ROOT / "data" / "processed" / "windows.parquet")[config.COL_CASEID].unique()
    all_caseids = sorted(windows_df_caseids.tolist())
    split = models.split_cases(cases_df, all_caseids)
    dev_ids = [c for c in all_caseids if split[c] in ("train", "val")]
    print(f"Dev cases (train+val, descriptive only): {len(dev_ids)}")

    rows = []
    event_id = 0
    for i, caseid in enumerate(dev_ids, start=1):
        cleaned = vitaldb_io.load_and_clean_case(int(caseid))
        row = cases_df.loc[cases_df[config.COL_CASEID] == caseid].iloc[0]
        op_start_s, op_end_s = float(row[config.COL_OPSTART]), float(row[config.COL_OPEND])
        op_window = cleaned[(cleaned["Time"] >= op_start_s) & (cleaned["Time"] <= op_end_s)]
        events = labels.detect_primary_events(op_window)
        is_cohort_b = bool(cohort_df.loc[cohort_df[config.COL_CASEID] == caseid, "cohort_b_final"].iloc[0])

        baseline = None
        for e in events:
            feat = features.compute_window_features(
                cleaned, e.start_time,
                features.compute_patient_baseline(cleaned, float(row[config.COL_ANESTART]), op_start_s=op_start_s),
            )
            if feat is None or pd.isna(feat.get("map_slope_15")):
                continue
            trace = trace_for_event(cleaned, e.start_time)
            event_id += 1
            for m, vals in trace.items():
                rows.append({"event_id": event_id, "caseid": caseid, "minutes_before": m,
                             "cohort_b": is_cohort_b, "map_slope_15_at_onset": feat["map_slope_15"], **vals})
        if i % 100 == 0:
            print(f"  ... {i}/{len(dev_ids)} cases processed")

    event_df = pd.DataFrame(rows)
    n_events = event_df["event_id"].nunique()
    print(f"\nTotal events with a usable trace: {n_events}")

    # Cohort B vs. not
    plot_traces(
        event_df, "cohort_b", {True: "Cohort B (high blood loss)", False: "Not Cohort B"},
        ROOT / "artifacts" / "phase4_event_aligned_traces_cohort.png",
        "Event-aligned vitals, 30 min before onset -- Cohort B vs. not (train+val, median + bootstrap band by case)",
    )

    # Abrupt vs. gradual (median split on this dev event set's own map_slope_15 at onset)
    median_slope = event_df.drop_duplicates("event_id")["map_slope_15_at_onset"].median()
    event_df["decline_group"] = event_df["map_slope_15_at_onset"] <= median_slope
    print(f"Median map_slope_15 at onset (dev events): {median_slope:.3f} mmHg/min")
    plot_traces(
        event_df, "decline_group", {True: "Abrupt (steeper half)", False: "Gradual (shallower half)"},
        ROOT / "artifacts" / "phase4_event_aligned_traces_decline.png",
        "Event-aligned vitals, 30 min before onset -- abrupt vs. gradual decline (train+val, median + bootstrap band by case)",
    )


if __name__ == "__main__":
    main()
