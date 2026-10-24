#!/usr/bin/env python
"""Phase 5: export web/data/sim_curves.js from the hemorrhage simulator.
Prints the accept-criterion alert/MAP<65 points for both blunted settings.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import config, simulator  # noqa: E402


def main() -> None:
    print("=== Phase 5: hemorrhage simulator export ===")
    f = np.arange(
        config.SIM_BLOOD_LOSS_FRACTION_MIN,
        config.SIM_BLOOD_LOSS_FRACTION_MAX + config.SIM_BLOOD_LOSS_FRACTION_STEP / 2,
        config.SIM_BLOOD_LOSS_FRACTION_STEP,
    )
    for blunted in (False, True):
        curves = simulator.compute_curves(f, blunted)
        pts = simulator.alert_and_map65_points(f, curves)
        print(f"blunted={blunted}: alert_f={pts['alert_f']}, map_below_65_f={pts['map_below_65_f']}")

    dest = simulator.write_sim_curves_js()
    size_kb = dest.stat().st_size / 1024
    print(f"\nSaved {dest} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
