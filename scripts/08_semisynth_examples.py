#!/usr/bin/env python
"""Round 4 (SYNTHETIC_PLAN.md): sanity-check plots BEFORE the generator is
frozen. No training. Pulls stable baseline windows from synth-train cases
only, injects one T1, one T3 and one T4 bleed, plus the two non-bleed
confounders, and plots MAP / HR / pulse pressure with onset marked.
Outputs: artifacts/round4_example_{T1,T3,T4,negatives}.png and
artifacts/round4_baseline_pool_report.json. Everything plotted is SYNTHETIC
on top of a real recorded baseline.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import config, semisynth, vitaldb_io  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WINDOWS_PARQUET = ROOT / "data" / "processed" / "windows.parquet"
HOLDOUT_CSV = ROOT / "data" / "interim" / "fresh_holdout_selection.csv"
ART = ROOT / "artifacts"


def find_windows(cases_df, caseids, rng):
    out, n_no_stable = [], 0
    for cid in caseids:
        row = cases_df.loc[cases_df[config.COL_CASEID] == cid].iloc[0]
        w = semisynth.select_baseline_segment(
            vitaldb_io.load_and_clean_case(int(cid)), vitaldb_io.load_drug_tracks(int(cid)),
            float(row[config.COL_OPSTART]), float(row[config.COL_OPEND]), rng,
        )
        if w is None:
            n_no_stable += 1
        else:
            out.append((int(cid), w))
    return out, n_no_stable


def plot_case(ax_col, case, title):
    s = case.stream
    m = case.meta
    t = s["Time"] / 60.0
    pp = s[config.TRACK_SBP] - s[config.TRACK_DBP]
    series = [
        (s[config.TRACK_MAP], "MAP (mmHg)", config.WEB_COLOR_TRACE_MAP),
        (s[config.TRACK_HR], "HR (bpm)", config.WEB_COLOR_TRACE_HR),
        (pp, "Pulse pressure (mmHg)", config.WEB_COLOR_TRACE_PP),
    ]
    for ax, (y, ylabel, color) in zip(ax_col, series):
        ax.plot(t, y, color=color, lw=1.4)
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.25)
        if "t0_min" in m:
            ax.axvline(m["t0_min"], color="k", ls="--", lw=1)
            if m["decompensation_min"] < t.max():
                ax.axvline(m["decompensation_min"], color="#B22222", ls=":", lw=1.2)
            if m["collapse_min"] is not None:
                ax.axvline(m["collapse_min"], color="#B22222", ls="-", lw=1.6, alpha=0.8)
        if "stim_onset_min" in m:
            ax.axvspan(m["stim_onset_min"], m["stim_onset_min"] + m["stim_duration_min"], color="orange", alpha=0.2)
        if "drop_onset_min" in m:
            ax.axvline(m["drop_onset_min"], color="purple", ls="--", lw=1)
        if "artifact_onset_min" in m:
            ax.axvline(m["artifact_onset_min"], color="gray", ls="-.", lw=1)
    ax_col[0].axhline(config.EVENT_MAP_THRESHOLD_MMHG, color="#B22222", lw=0.8, alpha=0.6)
    ax_col[0].set_title(title, fontsize=9)
    ax_col[-1].set_xlabel("Minutes into window")


def describe(case):
    m = case.meta
    keys = ("label", "tier", "source_caseid", "t0_min", "rate_band", "rate_frac_per_min", "g_hr", "f_c",
            "decompensation_min", "fitted_to_window", "expected_collapse_min", "collapse_min",
            "collapses_in_window", "window_len_min", "map_pre_bleed", "pp_pre_bleed",
            "stim_onset_min", "stim_duration_min", "stim_hr_delta",
            "drop_onset_min", "drop_mmhg", "artifact", "artifact_onset_min")
    return {k: (round(m[k], 3) if isinstance(m[k], float) else m[k]) for k in keys if k in m}


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cases_df = vitaldb_io.load_case_table()
    windows_df = pd.read_parquet(WINDOWS_PARQUET, columns=[config.COL_CASEID])
    pool = semisynth.get_baseline_pool_caseids(cases_df, windows_df)
    holdout = set(pd.read_csv(HOLDOUT_CSV)[config.COL_CASEID])
    assert not set(pool) & holdout, "baseline pool must never touch the fresh holdout"
    split = semisynth.split_baseline_cases(cases_df, pool)
    synth_train = [c for c in pool if split[c] == "train"]
    print(f"Baseline pool (Phase 4 train+val): {len(pool)} cases -> synth train/val/test = "
          f"{sum(v == 'train' for v in split.values())}/{sum(v == 'val' for v in split.values())}/"
          f"{sum(v == 'test' for v in split.values())}")

    rng = np.random.RandomState(config.SYNTH_GENERATOR_SEED)
    windows, n_none = find_windows(cases_df, synth_train, rng)
    print(f"synth-train cases with a stable window: {len(windows)}/{len(synth_train)} (no stable window: {n_none})")
    collapse_rates = {}
    tier_bleeds = {}
    for tier in config.SYNTH_TIERS:
        bleeds = [c for c in semisynth.generate_tier_cases(windows, tier) if c.meta["is_bleed"]]
        tier_bleeds[tier] = bleeds
        rate = float(np.mean([c.meta["collapses_in_window"] for c in bleeds]))
        by_band = {}
        for band in config.SYNTH_RATE_BANDS:
            sub = [c.meta["collapses_in_window"] for c in bleeds if c.meta["rate_band"] == band]
            if sub:
                by_band[band] = {"n": len(sub), "collapse_rate": float(np.mean(sub))}
        min_map = float(min(c.stream[config.TRACK_MAP].min() for c in bleeds))
        n_no_collapse = sum(c.meta["label"] == config.SYNTH_LABEL_BLEED_NO_COLLAPSE for c in bleeds)
        n_fitted = sum(c.meta["fitted_to_window"] for c in bleeds)
        lengths = [c.meta["window_len_min"] for c in bleeds]
        collapse_rates[tier] = {"n_bleeds": len(bleeds), "collapse_in_window_rate": rate, "by_rate_band": by_band,
                                "n_bleed_no_collapse": n_no_collapse, "n_fitted_to_window": n_fitted,
                                "window_len_min_range": [float(min(lengths)), float(max(lengths))],
                                "min_map_any_stream": min_map}
        print(f"{tier}: MAP<65 reached in-window for {rate:.0%} of {len(bleeds)} bleeds; by band "
              + ", ".join(f"{b} {v['collapse_rate']:.0%} (n={v['n']})" for b, v in by_band.items())
              + f"; bleed_no_collapse={n_no_collapse}; fitted={n_fitted}; "
              f"window {min(lengths):.0f}-{max(lengths):.0f} min; lowest MAP {min_map:.1f}")

    (ART / "round4_baseline_pool_report.json").write_text(json.dumps({
        "pool_n": len(pool), "synth_split_counts": {s: sum(v == s for v in split.values()) for s in ("train", "val", "test")},
        "synth_train_with_stable_window": len(windows), "synth_train_without_stable_window": n_none,
        "synth_train_collapse_in_window_by_tier": collapse_rates,
        "note": "Sanity-check run only; generator not frozen; no model trained.",
    }, indent=2))

    gen_rng = np.random.RandomState(config.SYNTH_GENERATOR_SEED + 1)
    picks = gen_rng.choice(len(windows), size=5, replace=False)
    examples = {}
    for tier, idx in zip(("T1", "T3", "T4"), picks[:3]):
        cid, w = windows[idx]
        examples[tier] = semisynth.generate_bleed_case(w, tier, gen_rng, source_caseid=cid)

    # bleed_no_collapse example, picked by a fixed rule (first one in T2 generation order), not by eye.
    no_collapse = [c for c in tier_bleeds["T2"] if c.meta["label"] == config.SYNTH_LABEL_BLEED_NO_COLLAPSE]
    if no_collapse:
        examples["bleed_no_collapse"] = no_collapse[0]

    for name, case in examples.items():
        tier = case.meta["tier"]
        fig, axes = plt.subplots(3, 1, figsize=(9, 7), sharex=True)
        m = case.meta
        plot_case(axes, case, (
            f"SYNTHETIC {m['label']} on real VitalDB baseline (case {m['source_caseid']}) | {tier} "
            f"{config.SYNTH_TIER_NAMES[tier]} | rate {m['rate_frac_per_min']*100:.2f}%BV/min ({m['rate_band']}), "
            f"g_hr={m['g_hr']:.2f}, f_c={m['f_c']:.2f}\n"
            "black dashed = bleed onset t0 · red dotted = f reaches f_c · red solid = MAP<65 event"
            + ("" if m["collapses_in_window"] else " (NO collapse in window)")
            + (" · orange = stimulation spike" if "stim_onset_min" in m else "")
            + (f" · gray = {m['artifact']} artifact" if "artifact" in m else "")
        ))
        fig.tight_layout()
        out = ART / f"round4_example_{name}.png"
        fig.savefig(out, dpi=120)
        plt.close(fig)
        print(f"\n{name}: {describe(case)}\n  saved {out}")

    fig, axes = plt.subplots(3, 2, figsize=(13, 7), sharex="col")
    for col, (kind, idx) in enumerate(zip(("non_bleed_hypotension", "stimulation_spike"), picks[3:])):
        cid, w = windows[idx]
        case = semisynth.generate_negative_case(w, kind, gen_rng, tier="T4", source_caseid=cid)
        plot_case(axes[:, col], case, f"SYNTHETIC negative: {kind} (case {cid}, no bleed)\n"
                  "purple dashed = drop onset · orange = spike")
        print(f"\nnegative {kind}: {describe(case)}")
    fig.tight_layout()
    out = ART / "round4_example_negatives.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"  saved {out}")


if __name__ == "__main__":
    main()
