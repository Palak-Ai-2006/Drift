#!/usr/bin/env python
"""Phase 1, steps 1-4 (PLAN.md): load the cached case table + track list,
verify names, flag arterial-line cases, build and save the inventory, print
accept-criteria counts.

Step 5 (the 5-case download/resample test) is intentionally NOT run by this
script — it downloads real per-case files, which is gated behind the
bulk-download sign-off described in vitaldb_io.py's module docstring and the
Oct 24 Decision 1. Run it separately, explicitly, once that sign-off exists.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import vitaldb_io  # noqa: E402


def main() -> None:
    print("=== Phase 1, steps 1-4: inventory from the cached clinical table ===")
    print(f"Loading case table from cache (data/manual or data/raw)...")
    cases_df = vitaldb_io.load_case_table()
    print(f"Loaded {len(cases_df)} rows, {len(cases_df.columns)} columns.")

    print("\nLoading track-name dictionary...")
    track_names_df = vitaldb_io.load_track_names()
    print(f"Loaded {len(track_names_df)} track definitions.")

    print("\n--- Step 2: verify actual column and track names (never guessed) ---")
    col_result = vitaldb_io.verify_required_columns_present(cases_df)
    print(f"All {len(col_result)} expected clinical columns confirmed present.")
    track_result = vitaldb_io.verify_required_tracks_present(track_names_df)
    print(f"All {len(track_result)} expected numeric tracks confirmed present:")
    for name, ok in track_result.items():
        print(f"  {name}: {'OK' if ok else 'MISSING'}")

    print("\n--- Step 3/4: flag arterial-line cases, build inventory ---")
    inventory_df = vitaldb_io.build_inventory(cases_df)
    dest = vitaldb_io.save_inventory(inventory_df)
    print(f"Saved inventory to {dest} ({len(inventory_df)} rows).")

    print("\n--- Accept criteria: counts ---")
    vitaldb_io.print_inventory_counts(cases_df, inventory_df)

    print(
        "\nNOTE: 'with all four tracks' and 'one case plotted' from the "
        "accept criteria both require downloading at least one real "
        "whole-case file (Phase 1 step 5), which is gated per Decision 1 "
        "until the event starts or organizers approve bulk downloads."
    )


if __name__ == "__main__":
    main()
