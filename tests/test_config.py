"""Phase 0 smoke test: config.py imports and the fixed decisions hold together.

This is intentionally small — it exists to satisfy the Phase 0 acceptance
criterion ("pytest passes; no data committed") before any pipeline logic
exists. Later phases add their own tests (event detector, feature causality,
split disjointness, replay-export causality — the Phase 7 required list).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import config  # noqa: E402


def test_config_imports():
    assert config.RANDOM_SEED == 42


def test_required_numeric_tracks_are_the_confirmed_names():
    assert config.REQUIRED_NUMERIC_TRACKS == (
        config.TRACK_HR,
        config.TRACK_SBP,
        config.TRACK_DBP,
        config.TRACK_MAP,
    )
    assert config.TRACK_HR == "Solar8000/HR"


def test_split_fractions_sum_to_one():
    total = config.SPLIT_TRAIN_FRAC + config.SPLIT_VAL_FRAC + config.SPLIT_TEST_FRAC
    assert abs(total - 1.0) < 1e-9


def test_event_definition_is_the_decided_primary():
    assert config.EVENT_MAP_THRESHOLD_MMHG == 65
    assert config.EVENT_SUSTAINED_DURATION_S == 60
    # Fallback switch must not be silently pre-applied.
    assert config.EVENT_DEFINITION_FALLBACK_APPLIED is False


def test_cohort_b_rule_matches_oct_24_decision():
    assert config.COHORT_B_MIN_EBL_ML == 500
    assert config.COHORT_B_FALLBACK_MIN_CASES == 60
    assert config.COHORT_B_FALLBACK_MIN_FRACTION_OF_ELIGIBLE == 0.10


def test_insufficient_data_threshold_is_finalized_at_30_percent():
    assert config.INSUFFICIENT_DATA_MISSING_FRACTION == 0.30
    assert config.INSUFFICIENT_DATA_MAX_EXCLUDED_WINDOW_FRACTION == 0.10


def test_end_of_case_totals_are_never_listed_as_features():
    # This test only guards the config-level list; Phase 3's feature module
    # must itself also never reference these columns as model inputs.
    assert "intraop_ebl" in config.END_OF_CASE_SELECTION_ONLY_COLS
    assert "intraop_rbc" in config.END_OF_CASE_SELECTION_ONLY_COLS


def test_decision_gate_tiers_are_ordered():
    assert config.DECISION_GATE_TIER1_MIN_CASES > config.DECISION_GATE_TIER2_MIN_CASES
    assert config.DECISION_GATE_TIER1_MIN_EVENTS > config.DECISION_GATE_TIER2_MIN_EVENTS
