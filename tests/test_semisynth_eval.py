"""Round 4 evaluation-helper tests (SYNTHETIC_PLAN.md 5a), toy data only."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import config, semisynth, semisynth_eval  # noqa: E402


def _window(minutes=55.0, seed=0):
    rng = np.random.RandomState(seed)
    t = np.arange(0.0, minutes * 60.0, 30.0)
    return pd.DataFrame({
        "Time": t,
        config.TRACK_HR: 70 + rng.normal(0, 3, len(t)),
        config.TRACK_SBP: 120 + rng.normal(0, 3, len(t)),
        config.TRACK_DBP: 67.5 + rng.normal(0, 2, len(t)),
        config.TRACK_MAP: 85 + rng.normal(0, 2, len(t)),
    })


def test_feature_matrix_has_exactly_the_registered_features_and_no_internals():
    case = semisynth.generate_bleed_case(_window(), "T2", np.random.RandomState(1))
    rows = semisynth_eval.case_feature_rows(case, synth_id=7)
    X = semisynth_eval.feature_matrix(rows)
    assert tuple(X.columns) == config.SYNTH_FEATURE_COLUMNS
    internals = set(case.meta) | {"f", "tier", "label", "synth_id", "source_caseid", "time_since_anesthesia_min",
                                  "time_since_opstart_min", "age", "sex", "asa", "emergency"}
    assert not internals & set(X.columns)


def test_predictions_start_after_the_10_minute_baseline():
    case = semisynth.generate_negative_case(_window(), "clean", np.random.RandomState(2), tier="T2")
    rows = semisynth_eval.case_feature_rows(case, synth_id=1)
    assert rows["t_s"].min() == pytest.approx(config.FEATURE_BASELINE_WINDOW_MIN * 60.0)
    assert (rows["synth_id"] == 1).all()


def test_standard_monitor_risk_rule():
    df = pd.DataFrame({"hr": [100, 121, 100, 130], "sbp": [120, 120, 89, 85]})
    assert semisynth_eval.standard_monitor_risk(df).tolist() == [0.0, 1.0, 1.0, 1.0]


def test_bleed_aware_false_alarms():
    events = [3000.0]
    alerts = [600.0, 1500.0, 2400.0]  # 600: false; 1500: false (event 25 min later); 2400: true (10 min before)
    assert semisynth_eval.bleed_aware_false_alarms(alerts, events, bleed_onset_s=None) == 2
    assert semisynth_eval.bleed_aware_false_alarms(alerts, events, bleed_onset_s=1200.0) == 1  # 1500 is after onset


def test_classify_miss_precedence():
    base = {"g_hr": 1.0, "rate_band": "moderate"}
    collapse_s = 40 * 60.0
    assert semisynth_eval.classify_miss({**base, "g_hr": 0.3, "rate_band": "fast"}, collapse_s) == "blunted"
    assert semisynth_eval.classify_miss({**base, "artifact_onset_min": 30.0, "artifact_duration_min": 2.0}, collapse_s) == "artifact"
    assert semisynth_eval.classify_miss({**base, "artifact_onset_min": 5.0, "artifact_duration_min": 2.0}, collapse_s) == "other"
    assert semisynth_eval.classify_miss({**base, "stim_onset_min": 28.0, "stim_duration_min": 3.0}, collapse_s) == "confounder"
    assert semisynth_eval.classify_miss({**base, "rate_band": "fast"}, collapse_s) == "fast"


def test_build_cases_is_deterministic_and_covers_all_tiers_and_replicates():
    windows = [(11, _window(seed=3)), (12, _window(seed=4))]
    a = semisynth_eval.build_cases(windows, seed_base=100, replicates=2)
    b = semisynth_eval.build_cases(windows, seed_base=100, replicates=2)
    assert len(a) == len(config.SYNTH_TIERS) * 2 * len(windows) * 2
    assert [c.meta for c in a] == [c.meta for c in b]
    assert {c.meta["tier"] for c in a} == set(config.SYNTH_TIERS)


def _random_rows(n_cases=12, seed=5):
    rng = np.random.RandomState(seed)
    frames = []
    for sid in range(n_cases):
        n = rng.randint(20, 60)
        frames.append(pd.DataFrame({
            "synth_id": sid, "t_s": 600.0 + 60.0 * np.arange(n),
            "risk": np.where(rng.uniform(size=n) < 0.1, np.nan, rng.uniform(size=n)),
            "missing_fraction": rng.choice([0.0, 0.1, 0.5], size=n, p=[0.8, 0.1, 0.1]),
            "map": rng.choice([60.0, 80.0], size=n, p=[0.1, 0.9]),
        }))
    return pd.concat(frames, ignore_index=True)


def test_fast_alerts_match_alarms_module_exactly():
    from drift import alarms
    rows = _random_rows()
    arrays = semisynth_eval.case_arrays(rows, "risk")
    for thr in (0.2, 0.5, 0.8, 0.95):
        for sid, g in rows.groupby("synth_id"):
            assert semisynth_eval.fast_alerts(arrays[sid], thr) == alarms.generate_case_alerts(g, "risk", thr)


def test_fast_threshold_search_matches_alarms_module():
    from drift import alarms
    rows = _random_rows(seed=6)
    events = {sid: [600.0 + 60.0 * 25] for sid in range(0, 12, 3)}
    arrays = semisynth_eval.case_arrays(rows, "risk")
    case_dfs = {sid: g for sid, g in rows.groupby("synth_id")}
    for target in (0.5, 1.0, 2.0):
        fast = semisynth_eval.threshold_for_fa(arrays, events, target)
        slow = alarms.find_threshold_for_target_fa_rate(case_dfs, events, "risk", target)
        assert fast[0] == pytest.approx(slow[0]) and fast[1] == pytest.approx(slow[1])


def test_detection_lead_time():
    assert semisynth_eval.detection([100.0, 900.0], event_s=1200.0) == 300.0   # 100 is 18 min early: only 900 counts
    assert semisynth_eval.detection([400.0, 900.0], event_s=1200.0) == 800.0   # earliest alert within 15 min wins
    assert semisynth_eval.detection([100.0], event_s=1200.0) is None           # 18 min early: outside H
    assert semisynth_eval.detection([1200.0], event_s=1200.0) is None          # not strictly before


def test_check_split_disjoint():
    w = _window()
    ok = {"train": [(1, w), (2, w)], "val": [(3, w)], "test": [(4, w)]}
    semisynth_eval.check_split_disjoint(ok, forbidden={99})
    with pytest.raises(AssertionError):
        semisynth_eval.check_split_disjoint({"train": [(1, w)], "test": [(1, w)]}, forbidden=set())
    with pytest.raises(AssertionError):
        semisynth_eval.check_split_disjoint(ok, forbidden={4})
