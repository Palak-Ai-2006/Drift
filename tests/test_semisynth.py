"""Round 4 generator tests (SYNTHETIC_PLAN.md Section 6), on toy series --
no real VitalDB data needed."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import config, features, labels, semisynth  # noqa: E402

HR0, MAP0, SBP0, DBP0 = 70.0, 85.0, 120.0, 67.5  # SBP - DBP = 52.5 = PP0


def _flat_window(minutes: float = 60.0, interval_s: float = 30.0) -> pd.DataFrame:
    t = np.arange(0.0, minutes * 60.0, interval_s)
    return pd.DataFrame({
        "Time": t,
        config.TRACK_HR: np.full_like(t, HR0),
        config.TRACK_SBP: np.full_like(t, SBP0),
        config.TRACK_DBP: np.full_like(t, DBP0),
        config.TRACK_MAP: np.full_like(t, MAP0),
    })


def _fixed_params(**kw):
    base = dict(t0_min=15.0, rate_band="moderate", rate_frac_per_min=0.012, g_hr=1.0, f_c=0.30)
    base.update(kw)
    return semisynth.BleedParams(**base)


def _stream_from_params(window, params, tier="T2"):
    """generate_bleed_case with its sampled params replaced by fixed ones."""
    rng = np.random.RandomState(0)
    orig = semisynth.sample_bleed_params
    semisynth.sample_bleed_params = lambda *a, **k: params
    try:
        return semisynth.generate_bleed_case(window, tier, rng)
    finally:
        semisynth.sample_bleed_params = orig


# ---------------------------------------------------------------------------
# f(t)
# ---------------------------------------------------------------------------
def test_blood_loss_fraction_zero_before_t0_and_non_decreasing_after():
    t = np.linspace(0, 60, 601)
    f = semisynth.blood_loss_fraction(t, t0_min=12.0, rate_frac_per_min=0.01)
    assert np.all(f[t <= 12.0] == 0.0)
    assert np.all(np.diff(f) >= 0.0)
    assert f[-1] > 0.0
    assert f.max() <= config.SYNTH_F_MAX


# ---------------------------------------------------------------------------
# Response curves
# ---------------------------------------------------------------------------
def test_map_held_near_baseline_until_f_c_then_falls():
    f_c = 0.30
    f = np.linspace(0, 0.5, 501)
    d = semisynth.map_delta(f, f_c)
    assert d[0] == pytest.approx(0.0, abs=1e-12)
    assert np.all(np.abs(d[f <= f_c - 0.05]) < 3.0)  # "small drift only"
    assert np.all(np.diff(d) <= 1e-12)               # never rises
    assert d[np.argmin(np.abs(f - (f_c + 0.1)))] < -20.0  # "falls steeply"


def test_hr_rises_and_pp_narrows_monotonically():
    f = np.linspace(0, 0.5, 501)
    assert np.all(np.diff(semisynth.hr_delta(f, 1.0)) > 0)
    assert np.all(np.diff(semisynth.pp_delta(f, 50.0)) < 0)


def test_pp_narrowing_is_relative_to_the_case_baseline():
    f = np.array([0.3])
    assert semisynth.pp_delta(f, 80.0)[0] == pytest.approx(2.0 * semisynth.pp_delta(f, 40.0)[0])
    assert -semisynth.pp_delta(np.array([10.0]), 50.0)[0] <= config.SYNTH_PP_NARROWING_FRAC * 50.0 + 1e-9


def test_map_floor_is_smooth_and_never_crossed():
    x = np.linspace(-50, 120, 1000)
    y = semisynth.apply_map_floor(x)
    assert np.all(y > config.SYNTH_MAP_FLOOR_MMHG)
    assert np.all(np.diff(y) > 0)
    assert y[-1] == pytest.approx(x[-1], abs=1e-6)  # identity well above the floor


def test_fast_bleed_collapse_stops_at_the_floor():
    w = _flat_window()
    case = _stream_from_params(w, _fixed_params(t0_min=10.0, rate_frac_per_min=0.025, f_c=0.2))
    assert case.stream[config.TRACK_MAP].min() >= config.SYNTH_MAP_FLOOR_MMHG


def test_blunted_gain_produces_smaller_hr_rise():
    w = _flat_window()
    normal = _stream_from_params(w, _fixed_params(g_hr=1.0))
    blunted = _stream_from_params(w, _fixed_params(g_hr=0.2))
    rise_n = normal.stream[config.TRACK_HR].max() - HR0
    rise_b = blunted.stream[config.TRACK_HR].max() - HR0
    assert rise_b < 0.5 * rise_n


def test_t3_sampled_g_hr_is_blunted_relative_to_t2():
    rng = np.random.RandomState(1)
    t2 = [semisynth.sample_bleed_params(rng, "T2", 50.0).g_hr for _ in range(200)]
    t3 = [semisynth.sample_bleed_params(rng, "T3", 50.0).g_hr for _ in range(200)]
    assert max(t3) <= config.SYNTH_G_HR_RANGE_NORMAL[1] * config.SYNTH_G_HR_RANGE_BLUNTED_SCALE[1]
    assert np.mean(t3) < 0.5 * np.mean(t2)


def test_t0_is_at_least_ten_minutes_into_window():
    rng = np.random.RandomState(2)
    for tier in config.SYNTH_TIERS:
        for _ in range(50):
            assert semisynth.sample_bleed_params(rng, tier, 45.0).t0_min >= config.SYNTH_T0_MIN_INTO_WINDOW_MIN


# ---------------------------------------------------------------------------
# Stream shape and labels
# ---------------------------------------------------------------------------
def test_stream_unchanged_before_t0_and_pp_consistent():
    w = _flat_window()
    case = _stream_from_params(w, _fixed_params(t0_min=15.0))
    s = case.stream
    pre = s[s["Time"] <= 15.0 * 60.0]
    assert np.allclose(pre[config.TRACK_HR], HR0)
    assert np.allclose(pre[config.TRACK_MAP], MAP0)
    assert np.allclose(s[config.TRACK_SBP] - s[config.TRACK_DBP] >= config.SYNTH_PP_FLOOR_MMHG, True)


def test_labels_line_up_with_injected_decompensation_time():
    w = _flat_window()
    params = _fixed_params(t0_min=15.0, rate_frac_per_min=0.012, f_c=0.30)  # decomp at 40 min
    case = _stream_from_params(w, params)
    assert case.meta["decompensation_min"] == pytest.approx(40.0)
    events = labels.detect_primary_events(case.stream)
    assert events, "a decompensating bleed must produce a MAP<65 event"
    first_event_min = events[0].start_time / 60.0
    assert first_event_min >= params.decompensation_min           # never before decompensation
    assert first_event_min <= params.decompensation_min + 10.0    # and soon after it
    assert case.meta["collapse_min"] == pytest.approx(first_event_min)
    assert case.meta["collapses_in_window"] is True
    assert case.meta["label"] == config.SYNTH_LABEL_BLEED_COLLAPSE


def test_collapse_flag_reads_the_stream_not_the_decompensation_time():
    # f reaches f_c at 57 of 60 min: compensation fails "in window", but MAP
    # can't fall from 85 to below 65 in the last 3 minutes.
    w = _flat_window(60.0)
    case = _stream_from_params(w, _fixed_params(t0_min=32.0, rate_frac_per_min=0.012, f_c=0.30))
    assert case.meta["decompensation_min"] < 60.0
    assert case.meta["collapses_in_window"] is False
    assert case.meta["collapse_min"] is None
    assert case.meta["label"] == config.SYNTH_LABEL_BLEED_NO_COLLAPSE
    assert case.meta["is_bleed"] is True


# ---------------------------------------------------------------------------
# Window-to-bleed sizing (SYNTHETIC_PLAN.md 3.4 amendment)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("map_pre", [70.0, 85.0, 105.0])
@pytest.mark.parametrize("tier", config.SYNTH_FIT_COLLAPSE_TIERS)
def test_fitted_bleeds_expect_collapse_inside_the_window(tier, map_pre):
    rng = np.random.RandomState(12)
    n_fitted = 0
    for _ in range(200):
        p = semisynth.sample_bleed_params(rng, tier, 60.0, map_pre=map_pre)
        assert p.t0_min >= config.SYNTH_T0_MIN_INTO_WINDOW_MIN
        lo, hi = config.SYNTH_RATE_BANDS[p.rate_band]
        assert lo - 1e-12 <= p.rate_frac_per_min <= hi + 1e-12  # stays in its band either way
        if p.fitted_to_window:
            assert p.rate_band in config.SYNTH_FIT_COLLAPSE_BANDS
            assert p.expected_collapse_min + config.SYNTH_POST_COLLAPSE_MIN <= 60.0 + 1e-9
            n_fitted += 1
        elif p.rate_band in config.SYNTH_FIT_COLLAPSE_BANDS:
            # only allowed when even the band's fastest rate can't collapse in time
            f_cross = semisynth.f_to_cross_map65(map_pre, p.f_c)
            budget = 60.0 - config.SYNTH_POST_COLLAPSE_MIN - config.SYNTH_COLLAPSE_SUSTAIN_MARGIN_MIN
            assert f_cross is None or f_cross / (budget - config.SYNTH_T0_MIN_INTO_WINDOW_MIN) > hi
    assert n_fitted > 0


def test_slow_bands_and_t3_are_never_fitted():
    rng = np.random.RandomState(13)
    for tier in config.SYNTH_TIERS:
        for _ in range(100):
            p = semisynth.sample_bleed_params(rng, tier, 60.0, map_pre=85.0)
            if p.rate_band == "slow" or tier not in config.SYNTH_FIT_COLLAPSE_TIERS:
                assert not p.fitted_to_window


def test_f_to_cross_map65_matches_map_delta():
    f = semisynth.f_to_cross_map65(85.0, 0.30)
    target = config.EVENT_MAP_THRESHOLD_MMHG - config.SYNTH_COLLAPSE_TARGET_BELOW_MMHG
    assert 85.0 + semisynth.map_delta(np.array([f]), 0.30)[0] < target
    assert 85.0 + semisynth.map_delta(np.array([f - 0.002]), 0.30)[0] >= target
    assert semisynth.f_to_cross_map65(float("nan"), 0.30) is None


def test_t1_bleeds_mostly_collapse_and_windows_stay_40_to_60():
    rng = np.random.RandomState(14)
    cases = [semisynth.generate_bleed_case(_flat_window(60.0), "T1", rng) for _ in range(50)]
    lengths = [c.stream["Time"].iloc[-1] / 60.0 + 0.5 for c in cases]
    assert all(config.SYNTH_WINDOW_MIN_LEN_MIN - 0.5 <= L <= config.SYNTH_WINDOW_MAX_LEN_MIN + 0.5 for L in lengths)
    assert np.mean([c.meta["collapses_in_window"] for c in cases]) >= 0.9
    for c in cases:
        if c.meta["collapses_in_window"]:
            assert c.meta["collapse_min"] >= c.meta["t0_min"]


def test_bleed_no_collapse_is_kept_out_of_scored_metrics():
    rng = np.random.RandomState(15)
    collapse = _stream_from_params(_flat_window(), _fixed_params(t0_min=15.0))
    no_collapse = _stream_from_params(_flat_window(60.0), _fixed_params(t0_min=32.0))
    negative = semisynth.generate_negative_case(_flat_window(), "clean", rng)
    cases = [collapse, no_collapse, negative]
    assert semisynth.scored_cases(cases) == [collapse, negative]
    assert semisynth.descriptive_only_cases(cases) == [no_collapse]


@pytest.mark.parametrize("seed", range(20))
def test_t4_stimulation_spike_lands_before_decompensation(seed):
    case = semisynth.generate_bleed_case(_flat_window(), "T4", np.random.RandomState(seed))
    m = case.meta
    assert m["stim_onset_min"] + m["stim_duration_min"] <= m["decompensation_min"]
    assert m["stim_onset_min"] >= config.SYNTH_T4_STIM_EARLIEST_ONSET_MIN


def test_stream_carries_no_generator_internals():
    w = _flat_window()
    rng = np.random.RandomState(3)
    for tier in config.SYNTH_TIERS:
        case = semisynth.generate_bleed_case(w, tier, rng)
        assert tuple(case.stream.columns) == semisynth.STREAM_COLUMNS
    baseline = features.compute_patient_baseline(case.stream, anesthesia_start_s=-15 * 60.0)
    feat = features.compute_window_features(case.stream, 30 * 60.0, baseline)
    internals = {"f", "t0", "t0_min", "rate", "rate_frac_per_min", "g_hr", "f_c", "tier", "label", "decompensation_min"}
    assert not internals & set(feat)


def test_non_bleed_hypotension_has_no_hr_or_pp_precursor():
    w = _flat_window()
    case = semisynth.generate_negative_case(w, "non_bleed_hypotension", np.random.RandomState(4))
    s = case.stream
    assert np.allclose(s[config.TRACK_HR], HR0)
    assert np.allclose(s[config.TRACK_SBP] - s[config.TRACK_DBP], SBP0 - DBP0)
    assert s[config.TRACK_MAP].min() < MAP0 - config.SYNTH_NON_BLEED_MAP_DROP_RANGE_MMHG[0] + 1e-9


def test_stimulation_spike_raises_hr_transiently_with_map_steady():
    w = _flat_window()
    case = semisynth.generate_negative_case(w, "stimulation_spike", np.random.RandomState(5))
    s = case.stream
    rise = s[config.TRACK_HR].max() - HR0
    lo, hi = config.SYNTH_STIM_SPIKE_HR_DELTA_RANGE
    assert lo - 1e-9 <= rise <= hi + 1e-9
    assert s[config.TRACK_HR].iloc[-1] == pytest.approx(HR0)  # transient
    assert np.allclose(s[config.TRACK_MAP], MAP0)


@pytest.mark.parametrize("kind", config.SYNTH_ARTIFACT_KINDS)
def test_artifacts_change_the_stream(kind):
    w = _flat_window()
    clean = semisynth.generate_negative_case(w, "clean", np.random.RandomState(6)).stream
    art, meta = semisynth.inject_artifact(clean, np.random.RandomState(6), kind=kind)
    assert meta["artifact"] == kind
    if kind == "dropout":
        assert art[config.TRACK_MAP].isna().any()
    elif kind == "flush_spike":
        assert art[config.TRACK_MAP].max() > MAP0 + config.SYNTH_ARTIFACT_FLUSH_SPIKE_DELTA_RANGE_MMHG[0] - 1e-9


def _noisy_window(minutes=60.0, seed=20):
    rng = np.random.RandomState(seed)
    w = _flat_window(minutes)
    for col, sd in ((config.TRACK_HR, 4.0), (config.TRACK_MAP, 3.0), (config.TRACK_SBP, 4.0)):
        w[col] = w[col] + rng.normal(0, sd, len(w))
    return w


@pytest.mark.parametrize("tier", config.SYNTH_TIERS)
def test_bleed_and_negative_streams_share_the_same_noise_level(tier):
    """No shortcut: before bleed onset, a bleed stream and a no-bleed stream
    built on the same real window are identical (same residual scaling)."""
    w = _noisy_window()
    params = _fixed_params(t0_min=20.0)
    orig = semisynth.sample_bleed_params
    semisynth.sample_bleed_params = lambda *a, **k: params
    try:
        orig_prob = dict(config.SYNTH_TIER_ARTIFACT_PROB)
        config.SYNTH_TIER_ARTIFACT_PROB.update({t: 0.0 for t in config.SYNTH_TIERS})
        bleed = semisynth.generate_bleed_case(w, tier, np.random.RandomState(0))
        neg = semisynth.generate_negative_case(w, "clean", np.random.RandomState(0), tier=tier)
    finally:
        semisynth.sample_bleed_params = orig
        config.SYNTH_TIER_ARTIFACT_PROB.update(orig_prob)
    pre_b = bleed.stream[bleed.stream["Time"] < 19 * 60]
    pre_n = neg.stream[neg.stream["Time"] < 19 * 60]
    hr_only = pre_b[config.TRACK_HR].to_numpy()
    if tier == "T4":  # T4 bleeds carry a stimulation spike; compare MAP/PP only
        hr_only = None
    if hr_only is not None:
        assert np.allclose(hr_only, pre_n[config.TRACK_HR].to_numpy())
    assert np.allclose(pre_b[config.TRACK_MAP], pre_n[config.TRACK_MAP])
    assert np.allclose(pre_b[config.TRACK_SBP] - pre_b[config.TRACK_DBP], pre_n[config.TRACK_SBP] - pre_n[config.TRACK_DBP])


def test_artifact_rate_is_the_same_for_bleed_and_no_bleed_streams():
    windows = [(i, _noisy_window(seed=i)) for i in range(150)]
    cases = semisynth.generate_tier_cases(windows, "T2", seed=21)
    bleed_rate = np.mean([("artifact" in c.meta) for c in cases if c.meta["is_bleed"]])
    neg_rate = np.mean([("artifact" in c.meta) for c in cases if not c.meta["is_bleed"]])
    expected = config.SYNTH_TIER_ARTIFACT_PROB["T2"]
    assert abs(bleed_rate - expected) < 0.1 and abs(neg_rate - expected) < 0.1


def test_generate_tier_cases_is_deterministic():
    windows = [(1, _flat_window()), (2, _flat_window(45.0))]
    a = semisynth.generate_tier_cases(windows, "T4", seed=11)
    b = semisynth.generate_tier_cases(windows, "T4", seed=11)
    assert [c.meta for c in a] == [c.meta for c in b]
    for ca, cb in zip(a, b):
        pd.testing.assert_frame_equal(ca.stream, cb.stream)
    assert [c.meta["is_bleed"] for c in a] == [True, False, True, False]


# ---------------------------------------------------------------------------
# 3.1 Stable-window selection
# ---------------------------------------------------------------------------
def _toy_case(minutes=180.0, map_dip_at_min=None, drug_change_at_min=None):
    t = np.arange(0.0, minutes * 60.0, 30.0)
    df = pd.DataFrame({
        "Time": t,
        config.TRACK_HR: np.full_like(t, HR0),
        config.TRACK_SBP: np.full_like(t, SBP0),
        config.TRACK_DBP: np.full_like(t, DBP0),
        config.TRACK_MAP: np.full_like(t, MAP0),
    })
    if map_dip_at_min is not None:
        df.loc[(t >= map_dip_at_min * 60) & (t < map_dip_at_min * 60 + 120), config.TRACK_MAP] = 55.0
    drug = pd.DataFrame({"Time": t, config.VASOPRESSOR_RATE_TRACKS[0]: np.zeros_like(t)})
    if drug_change_at_min is not None:
        drug.loc[t >= drug_change_at_min * 60, config.VASOPRESSOR_RATE_TRACKS[0]] = 5.0
    return df, drug


def test_stable_window_rules():
    df, drug = _toy_case()
    ok = semisynth.is_window_stable
    assert ok(df, drug, 30 * 60, 80 * 60, op_start_s=20 * 60, op_end_s=170 * 60)
    assert not ok(df, drug, 10 * 60, 60 * 60, op_start_s=20 * 60, op_end_s=170 * 60)    # before incision
    assert not ok(df, drug, 110 * 60, 160 * 60, op_start_s=20 * 60, op_end_s=170 * 60)  # <15 min before end

    df_dip, drug0 = _toy_case(map_dip_at_min=88.0)  # 8 min after the window: inside +-10
    assert not ok(df_dip, drug0, 30 * 60, 80 * 60, op_start_s=20 * 60, op_end_s=170 * 60)
    df_dip_far, _ = _toy_case(map_dip_at_min=95.0)  # 15 min after: outside +-10
    assert ok(df_dip_far, drug0, 30 * 60, 80 * 60, op_start_s=20 * 60, op_end_s=170 * 60)

    df1, drug_chg = _toy_case(drug_change_at_min=85.0)
    assert not ok(df1, drug_chg, 30 * 60, 80 * 60, op_start_s=20 * 60, op_end_s=170 * 60)

    df_miss, drug1 = _toy_case()
    sel = (df_miss["Time"] >= 30 * 60) & (df_miss["Time"] < 50 * 60)  # 20 of 50 min missing = 40%
    df_miss.loc[sel, config.TRACK_HR] = np.nan
    assert not ok(df_miss, drug1, 30 * 60, 80 * 60, op_start_s=20 * 60, op_end_s=170 * 60)


def test_window_with_flush_jump_is_rejected():
    df, drug = _toy_case()
    args = dict(op_start_s=20 * 60, op_end_s=170 * 60)
    assert semisynth.is_window_stable(df, drug, 30 * 60, 80 * 60, **args)

    window = df[(df["Time"] >= 30 * 60) & (df["Time"] < 80 * 60)].reset_index(drop=True)
    spiked, meta = semisynth.inject_artifact(window, np.random.RandomState(9), kind="flush_spike")
    df_spiked = df.copy()
    df_spiked.loc[(df["Time"] >= 30 * 60) & (df["Time"] < 80 * 60), list(config.REQUIRED_NUMERIC_TRACKS)] = (
        spiked[list(config.REQUIRED_NUMERIC_TRACKS)].to_numpy()
    )
    assert not semisynth.is_window_stable(df_spiked, drug, 30 * 60, 80 * 60, **args)
    # the precomputed path used by find_stable_windows agrees
    flush = semisynth.flush_jump_times(df_spiked)
    assert not semisynth.is_window_stable(df_spiked, drug, 30 * 60, 80 * 60, flush_times=flush, **args)


def test_select_baseline_segment_returns_rebased_stable_window():
    df, drug = _toy_case(map_dip_at_min=100.0)
    w = semisynth.select_baseline_segment(df, drug, 20 * 60, 170 * 60, np.random.RandomState(7))
    assert w is not None
    assert w["Time"].iloc[0] == 0.0
    length_min = (w["Time"].iloc[-1] + 30.0) / 60.0
    assert config.SYNTH_WINDOW_MIN_LEN_MIN - 0.5 <= length_min <= config.SYNTH_WINDOW_MAX_LEN_MIN + 0.5
    start = w.attrs["source_start_s"]
    assert semisynth.is_window_stable(df, drug, start, start + length_min * 60, 20 * 60, 170 * 60)


def test_select_baseline_segment_none_when_nothing_is_stable():
    df, drug = _toy_case(minutes=50.0)  # a 40-min window would need to end by 35 min (50 - 15)
    assert semisynth.select_baseline_segment(df, drug, 0.0, 50 * 60, np.random.RandomState(0)) is None


def test_select_baseline_segment_prefers_the_longest_stable_window():
    df, drug = _toy_case(minutes=180.0)
    w = semisynth.select_baseline_segment(df, drug, 20 * 60, 170 * 60, np.random.RandomState(0))
    assert (w["Time"].iloc[-1] + 30.0) / 60.0 == pytest.approx(config.SYNTH_WINDOW_MAX_LEN_MIN)


# ---------------------------------------------------------------------------
# Splits
# ---------------------------------------------------------------------------
def test_synth_splits_do_not_overlap_and_keep_subjects_together():
    caseids = list(range(1, 101))
    cases_df = pd.DataFrame({
        config.COL_CASEID: caseids,
        config.COL_SUBJECTID: [c // 2 for c in caseids],  # pairs of cases share a subject
    })
    split = semisynth.split_baseline_cases(cases_df, caseids)
    sets = {s: {c for c, v in split.items() if v == s} for s in ("train", "val", "test")}
    assert sets["train"] and sets["val"] and sets["test"]
    assert not (sets["train"] & sets["val"]) and not (sets["train"] & sets["test"]) and not (sets["val"] & sets["test"])
    assert set().union(*sets.values()) == set(caseids)
    subj = dict(zip(cases_df[config.COL_CASEID], cases_df[config.COL_SUBJECTID]))
    for s1 in sets:
        for s2 in sets:
            if s1 != s2:
                assert not ({subj[c] for c in sets[s1]} & {subj[c] for c in sets[s2]})


def test_baseline_pool_excludes_phase4_test_split():
    from drift import models
    caseids = list(range(1, 51))
    cases_df = pd.DataFrame({config.COL_CASEID: caseids, config.COL_SUBJECTID: caseids})
    windows_df = pd.DataFrame({config.COL_CASEID: caseids})
    pool = semisynth.get_baseline_pool_caseids(cases_df, windows_df)
    phase4 = models.split_cases(cases_df, caseids)
    assert set(pool) == {c for c in caseids if phase4[c] in ("train", "val")}
    assert not {c for c in caseids if phase4[c] == "test"} & set(pool)


# ---------------------------------------------------------------------------
# Causality still holds on synthetic streams (Adjustment A3)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("tier", config.SYNTH_TIERS)
def test_feature_causality_on_synthetic_streams(tier):
    rng = np.random.RandomState(8)
    w = _flat_window()
    w[config.TRACK_HR] += rng.normal(0, 2, len(w))  # some real-looking noise
    w[config.TRACK_MAP] += rng.normal(0, 2, len(w))
    case = semisynth.generate_bleed_case(w, tier, rng)
    s = case.stream
    baseline = features.compute_patient_baseline(s, anesthesia_start_s=-15 * 60.0)
    for t_s in (12 * 60.0, 25 * 60.0, 38 * 60.0):
        full = features.compute_window_features(s, t_s, baseline)
        corrupted = s.copy()
        future = corrupted["Time"] > t_s
        corrupted.loc[future, list(config.REQUIRED_NUMERIC_TRACKS)] = 1.0
        trunc = features.compute_window_features(corrupted, t_s, baseline)
        for k in full:
            if pd.isna(full[k]) and pd.isna(trunc[k]):
                continue
            assert full[k] == pytest.approx(trunc[k]), f"{tier}: feature {k} leaked future data at t={t_s}"
