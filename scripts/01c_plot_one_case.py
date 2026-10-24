#!/usr/bin/env python
"""Phase 1 accept criterion: plot one downloaded case and eyeball plausibility."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from drift import config  # noqa: E402

CASEID = 6269  # first of the Phase 1 step-5 test sample


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    df = pd.read_parquet(root / "data" / "raw" / f"{CASEID}_numeric_30s.parquet")
    t_min = (df["Time"] - df["Time"].min()) / 60.0

    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    axes[0].plot(t_min, df[config.TRACK_HR], color="#4ADE80", label="HR")
    axes[0].set_ylabel("HR (bpm)")
    axes[0].legend(loc="upper right")
    axes[0].set_title(f"VitalDB case {CASEID} — numeric tracks, 30s resolution")

    axes[1].plot(t_min, df[config.TRACK_MAP], color="#FF6B5E", label="MAP")
    axes[1].plot(t_min, df[config.TRACK_SBP], color="#9BA7B4", alpha=0.6, label="SBP")
    axes[1].plot(t_min, df[config.TRACK_DBP], color="#38BDF8", alpha=0.6, label="DBP")
    axes[1].axhline(config.EVENT_MAP_THRESHOLD_MMHG, color="red", linestyle="--", linewidth=1, label="MAP=65")
    axes[1].set_ylabel("mmHg")
    axes[1].set_xlabel("Time (min)")
    axes[1].legend(loc="upper right")

    fig.tight_layout()
    out = root / "artifacts" / f"phase1_case_{CASEID}_plot.png"
    fig.savefig(out, dpi=120)
    print(f"Saved plot to {out}")


if __name__ == "__main__":
    main()
