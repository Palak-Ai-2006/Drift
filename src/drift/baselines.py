"""Threshold baselines B1-B4 (PLAN.md Section 4, Phase 4). Not yet implemented.

B1: MAP < 65 (zero lead; the standard alarm).
B2: early MAP threshold, tuned within config.BASELINE_B2_EARLY_MAP_THRESHOLD_RANGE_MMHG.
B3: shock index > config.BASELINE_B3_SHOCK_INDEX_THRESHOLD, tuned.
B4: MAP-slope rule (threshold TODO, set and tuned in Phase 4).
All tuned to match the operating-point false-alarm rate, same as the model.
"""
