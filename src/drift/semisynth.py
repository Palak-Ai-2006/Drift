"""Round 4 semi-synthetic bleed-injection generator (SYNTHETIC_PLAN.md Section 3).

Baseline segments are real, stable stretches of VitalDB TRAIN+VAL cases
(never the Round 1-3 test cases, never the fresh 175-case holdout). On top
of them we inject a simulated bleed, or a non-bleed confounder, or an
artifact. Everything injected is SYNTHETIC; the baseline level, variability
and sensor noise underneath are real.

A generated case is a SynthCase: `stream` (Time + the four numeric tracks,
the same shape features.py already consumes) and `meta` (generator
internals: t0, rate, g_hr, f_c, tier, ...). `meta` is for labeling and
error analysis only and must never become a feature (SYNTHETIC_PLAN.md
4.4) -- the stream deliberately carries no column but the five below.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config, labels, models

STREAM_COLUMNS = ("Time",) + config.REQUIRED_NUMERIC_TRACKS


# ---------------------------------------------------------------------------
# 3.1 Baseline segments
# ---------------------------------------------------------------------------
def get_baseline_pool_caseids(cases_df: pd.DataFrame, windows_df: pd.DataFrame) -> list[int]:
    """Train+val caseids of the original Phase 4 split (same call as
    scripts/04_train_eval.py). Excludes the Round 1-3 test split; the fresh
    holdout was drawn from never-downloaded cases, so it is disjoint by
    construction (checked again by the caller)."""
    all_caseids = sorted(windows_df[config.COL_CASEID].unique().tolist())
    split = models.split_cases(cases_df, all_caseids)
    return [c for c in all_caseids if split[c] in ("train", "val")]


def split_baseline_cases(cases_df: pd.DataFrame, pool_caseids: list[int]) -> dict[int, str]:
    """synth-train / synth-val / synth-test by case (grouped by subject,
    via the same models.split_cases), with Round 4's own seed."""
    return models.split_cases(
        cases_df, pool_caseids,
        train_frac=config.SYNTH_SPLIT_TRAIN_FRAC, val_frac=config.SYNTH_SPLIT_VAL_FRAC,
        seed=config.SYNTH_SPLIT_SEED,
    )


def drug_rates_change(drug_df: pd.DataFrame, start_s: float, end_s: float, time_col: str = "Time") -> bool:
    """True if any vasopressor-rate / volatile-anesthetic track changes in
    [start_s, end_s]. Same tracks and NaN->0 convention as Experiment 2
    (vitaldb_io.load_drug_tracks, labels.event_is_bleeding_flavored), but
    over a whole interval rather than one before/after pair."""
    d = drug_df[(drug_df[time_col] >= start_s) & (drug_df[time_col] <= end_s)]
    for track in config.DRUG_TRACKS:
        if track not in d.columns:
            continue
        vals = d[track].dropna()
        if len(vals) and (vals.max() - vals.min()) > config.SYNTH_DRUG_FLAT_TOLERANCE:
            return True
    return False


def flush_jump_times(df: pd.DataFrame, time_col: str = "Time") -> np.ndarray:
    """Times of samples whose MAP or pulse pressure sits more than
    SYNTH_FLUSH_JUMP_REJECT_MMHG from its rolling median -- the transient
    shape of an arterial-line flush (and of the injected flush artifact)."""
    t = df[time_col].to_numpy(dtype=float)
    w = config.SYNTH_RESIDUAL_ROLLING_MEDIAN_MIN
    bad = np.zeros(len(t), dtype=bool)
    for y in (df[config.TRACK_MAP].to_numpy(dtype=float),
              (df[config.TRACK_SBP] - df[config.TRACK_DBP]).to_numpy(dtype=float)):
        resid = np.abs(y - _rolling_median(t, y, w))
        bad |= np.nan_to_num(resid) > config.SYNTH_FLUSH_JUMP_REJECT_MMHG
    return t[bad]


def is_window_stable(
    cleaned_df: pd.DataFrame,
    drug_df: pd.DataFrame,
    start_s: float,
    end_s: float,
    op_start_s: float,
    op_end_s: float,
    time_col: str = "Time",
    flush_times: np.ndarray | None = None,
) -> bool:
    """All SYNTHETIC_PLAN.md 3.1 rules: after incision and >= 15 min before
    case end; no MAP < 65 and no drug-rate change within the window +-10 min;
    missing-data fraction under the existing threshold; plus no real
    flush-type jump inside the window. flush_times (from flush_jump_times
    on the whole case) can be passed in to avoid recomputing per window."""
    if start_s < op_start_s or end_s > op_end_s - config.SYNTH_MIN_BEFORE_CASE_END_MIN * 60.0:
        return False

    pad_s = config.SYNTH_STABLE_LOOKAROUND_MIN * 60.0
    padded = cleaned_df[(cleaned_df[time_col] >= start_s - pad_s) & (cleaned_df[time_col] <= end_s + pad_s)]
    if (padded[config.TRACK_MAP] < config.EVENT_MAP_THRESHOLD_MMHG).any():
        return False
    if drug_rates_change(drug_df, start_s - pad_s, end_s + pad_s, time_col):
        return False

    core = cleaned_df[(cleaned_df[time_col] >= start_s) & (cleaned_df[time_col] < end_s)]
    expected = max(round((end_s - start_s) / 30.0), 1)
    present = int(core[list(config.REQUIRED_NUMERIC_TRACKS)].notna().all(axis=1).sum())
    if (1.0 - present / expected) > config.SYNTH_MISSING_FRACTION_MAX:
        return False

    if flush_times is None:
        flush_times = flush_jump_times(core, time_col)
    return not np.any((flush_times >= start_s) & (flush_times < end_s))


def find_stable_windows(
    cleaned_df: pd.DataFrame,
    drug_df: pd.DataFrame,
    op_start_s: float,
    op_end_s: float,
    window_len_min: float,
    time_col: str = "Time",
) -> list[tuple[float, float]]:
    """Every stable window of the given length, starts scanned every
    SYNTH_WINDOW_SEARCH_STRIDE_MIN from incision onward."""
    length_s = window_len_min * 60.0
    stride_s = config.SYNTH_WINDOW_SEARCH_STRIDE_MIN * 60.0
    last_start = op_end_s - config.SYNTH_MIN_BEFORE_CASE_END_MIN * 60.0 - length_s
    flush_times = flush_jump_times(cleaned_df, time_col)
    out = []
    start = op_start_s
    while start <= last_start:
        if is_window_stable(cleaned_df, drug_df, start, start + length_s, op_start_s, op_end_s, time_col, flush_times):
            out.append((start, start + length_s))
        start += stride_s
    return out


def select_baseline_segment(
    cleaned_df: pd.DataFrame,
    drug_df: pd.DataFrame,
    op_start_s: float,
    op_end_s: float,
    rng: np.random.RandomState,
    time_col: str = "Time",
) -> pd.DataFrame | None:
    """One stable window per case at the LONGEST length available (60 min,
    then shorter in SYNTH_WINDOW_SEARCH_STRIDE_MIN steps down to 40), start
    drawn among stable candidates, rebased so Time starts at 0. The bleed
    generator later trims it to fit the bleed (never below 40 min). None if
    the case has no stable window of at least 40 min."""
    candidates = []
    window_len_min = float(config.SYNTH_WINDOW_MAX_LEN_MIN)
    while window_len_min >= config.SYNTH_WINDOW_MIN_LEN_MIN:
        candidates = find_stable_windows(cleaned_df, drug_df, op_start_s, op_end_s, window_len_min, time_col)
        if candidates:
            break
        window_len_min -= config.SYNTH_WINDOW_SEARCH_STRIDE_MIN
    if not candidates:
        return None
    start_s, end_s = candidates[rng.randint(len(candidates))]
    w = cleaned_df[(cleaned_df[time_col] >= start_s) & (cleaned_df[time_col] < end_s)].copy()
    w = w[[time_col] + list(config.REQUIRED_NUMERIC_TRACKS)].rename(columns={time_col: "Time"})
    w["Time"] = w["Time"] - start_s
    w.attrs["source_start_s"] = start_s
    return w.reset_index(drop=True)


def _rolling_median(times_s: np.ndarray, values: np.ndarray, window_min: float) -> np.ndarray:
    half = window_min * 60.0 / 2.0
    out = np.full(len(values), np.nan)
    for i, t in enumerate(times_s):
        sel = (times_s >= t - half) & (times_s <= t + half) & ~np.isnan(values)
        if sel.any():
            out[i] = np.median(values[sel])
    return out


def _real_signals(window_df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Real HR / MAP / PP of the window, plus each one's residual (signal
    minus a rolling median) -- the real noise the plan says to keep."""
    t = window_df["Time"].to_numpy(dtype=float)
    hr = window_df[config.TRACK_HR].to_numpy(dtype=float)
    map_ = window_df[config.TRACK_MAP].to_numpy(dtype=float)
    pp = (window_df[config.TRACK_SBP] - window_df[config.TRACK_DBP]).to_numpy(dtype=float)
    w = config.SYNTH_RESIDUAL_ROLLING_MEDIAN_MIN
    return {
        "t": t, "hr": hr, "map": map_, "pp": pp,
        "hr_resid": hr - _rolling_median(t, hr, w),
        "map_resid": map_ - _rolling_median(t, map_, w),
        "pp_resid": pp - _rolling_median(t, pp, w),
    }


def _assemble_stream(t: np.ndarray, hr: np.ndarray, map_: np.ndarray, pp: np.ndarray) -> pd.DataFrame:
    """SBP/DBP rebuilt from MAP and PP with the same coefficients as the
    Phase 5 simulator, so SBP - DBP == PP exactly."""
    pp = np.maximum(pp, config.SYNTH_PP_FLOOR_MMHG)
    return pd.DataFrame({
        "Time": t,
        config.TRACK_HR: hr,
        config.TRACK_SBP: map_ + config.SIM_SBP_FROM_MAP_PP_COEF * pp,
        config.TRACK_DBP: map_ - config.SIM_DBP_FROM_MAP_PP_COEF * pp,
        config.TRACK_MAP: map_,
    })


# ---------------------------------------------------------------------------
# 3.2 Bleed injection model
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BleedParams:
    t0_min: float
    rate_band: str
    rate_frac_per_min: float
    g_hr: float
    f_c: float
    fitted_to_window: bool = False
    expected_collapse_min: float | None = None  # only meaningful when fitted_to_window

    @property
    def decompensation_min(self) -> float:
        """Minutes into the window at which f reaches f_c."""
        return self.t0_min + self.f_c / self.rate_frac_per_min


def f_to_cross_map65(map_pre: float, f_c: float) -> float | None:
    """Smallest blood-loss fraction at which map_pre + map_delta drops
    SYNTH_COLLAPSE_TARGET_BELOW_MMHG under 65 (before the floor), or None if
    it never does by SYNTH_F_MAX."""
    if not np.isfinite(map_pre):
        return None
    target = config.EVENT_MAP_THRESHOLD_MMHG - config.SYNTH_COLLAPSE_TARGET_BELOW_MMHG
    f = np.arange(0.0, config.SYNTH_F_MAX + 1e-9, 0.001)
    below = map_pre + map_delta(f, f_c) < target
    return float(f[np.argmax(below)]) if below.any() else None


def sample_bleed_params(
    rng: np.random.RandomState, tier: str, window_len_min: float, shifted: bool = False,
    map_pre: float | None = None,
) -> BleedParams:
    """Sample one bleed. If map_pre (the window's pre-bleed MAP) is given and
    the tier/band is in SYNTH_FIT_COLLAPSE_*, rate and t0 are drawn jointly
    so the expected collapse fits inside window_len_min with
    SYNTH_POST_COLLAPSE_MIN to spare; otherwise t0 and rate are independent.
    If even the band's fastest rate can't fit, the draw falls back to the
    unfitted path (and will likely be labeled bleed_no_collapse)."""
    t0_max_frac = config.SYNTH_SHIFTED_T0_MAX_FRACTION_OF_WINDOW if shifted else config.SYNTH_T0_MAX_FRACTION_OF_WINDOW
    t0_lo = config.SYNTH_T0_MIN_INTO_WINDOW_MIN
    t0_hi_unfitted = max(t0_lo, t0_max_frac * window_len_min)

    bands = list(config.SYNTH_RATE_BANDS)
    if tier == "T1":
        band = str(rng.choice(config.SYNTH_T1_RATE_BANDS))
    elif tier == "T3":
        w = config.SYNTH_T3_RATE_BAND_WEIGHTS
        band = str(rng.choice(bands, p=[w[b] for b in bands]))
    else:
        band = str(rng.choice(bands))
    rate_lo, rate_hi = config.SYNTH_RATE_BANDS[band]
    if shifted:
        m = float(rng.uniform(*config.SYNTH_SHIFTED_RATE_MULTIPLIER_RANGE))
        rate_lo, rate_hi = rate_lo * m, rate_hi * m

    g_hr = float(rng.uniform(*(config.SYNTH_G_HR_RANGE_T1 if tier == "T1" else config.SYNTH_G_HR_RANGE_NORMAL)))
    if tier == "T3":
        g_hr *= float(rng.uniform(*config.SYNTH_G_HR_RANGE_BLUNTED_SCALE))
    if shifted:
        g_hr *= float(rng.uniform(*config.SYNTH_SHIFTED_G_HR_MULTIPLIER_RANGE))

    f_c = float(np.clip(rng.normal(config.SYNTH_F_C_MEAN, config.SYNTH_F_C_STD), config.SYNTH_F_C_MIN, config.SYNTH_F_C_MAX))

    fit = map_pre is not None and tier in config.SYNTH_FIT_COLLAPSE_TIERS and band in config.SYNTH_FIT_COLLAPSE_BANDS
    if fit:
        f_cross = f_to_cross_map65(map_pre, f_c)
        # time from 0 by which collapse must have happened
        budget = window_len_min - config.SYNTH_POST_COLLAPSE_MIN - config.SYNTH_COLLAPSE_SUSTAIN_MARGIN_MIN
        if f_cross is not None and budget > t0_lo:
            rate_needed = f_cross / (budget - t0_lo)
            if rate_needed <= rate_hi:
                rate = float(rng.uniform(max(rate_lo, rate_needed), rate_hi))
                t0_hi = min(t0_hi_unfitted, budget - f_cross / rate)
                t0 = float(rng.uniform(t0_lo, max(t0_lo, t0_hi)))
                expected = t0 + f_cross / rate + config.SYNTH_COLLAPSE_SUSTAIN_MARGIN_MIN
                return BleedParams(t0_min=t0, rate_band=band, rate_frac_per_min=rate, g_hr=g_hr, f_c=f_c,
                                   fitted_to_window=True, expected_collapse_min=expected)

    rate = float(rng.uniform(rate_lo, rate_hi))
    t0 = float(rng.uniform(t0_lo, t0_hi_unfitted))
    return BleedParams(t0_min=t0, rate_band=band, rate_frac_per_min=rate, g_hr=g_hr, f_c=f_c)


def blood_loss_fraction(t_min: np.ndarray, t0_min: float, rate_frac_per_min: float) -> np.ndarray:
    """f(t): 0 up to t0, then linear at `rate`, capped at SYNTH_F_MAX."""
    f = np.where(t_min > t0_min, (t_min - t0_min) * rate_frac_per_min, 0.0)
    return np.clip(f, 0.0, config.SYNTH_F_MAX)


def hr_delta(f: np.ndarray, g_hr: float) -> np.ndarray:
    """Rises with f, scaled by g_hr; saturates (plateaus) at high f."""
    return g_hr * config.SYNTH_HR_GAIN_COEF * (1.0 - np.exp(-config.SYNTH_HR_RISE_RATE * f))


def pp_delta(f: np.ndarray, pp_baseline: float) -> np.ndarray:
    """Narrows as f rises (fastest early), keeps narrowing past f_c; the
    size is a fraction of the case's own pre-bleed pulse pressure."""
    return -config.SYNTH_PP_NARROWING_FRAC * pp_baseline * (1.0 - np.exp(-config.SYNTH_PP_DECAY_RATE * f))


def apply_map_floor(map_: np.ndarray) -> np.ndarray:
    """Smooth floor: ~identity well above SYNTH_MAP_FLOOR_MMHG, levels off at
    it, never below it (softplus, no kink)."""
    floor, s = config.SYNTH_MAP_FLOOR_MMHG, config.SYNTH_MAP_FLOOR_SOFTNESS_MMHG
    with np.errstate(invalid="ignore"):  # missing samples stay NaN
        return floor + s * np.logaddexp(0.0, (map_ - floor) / s)


def map_delta(f: np.ndarray, f_c: float) -> np.ndarray:
    """Small drift before f_c, steep fall after; softplus hinge, no kink."""
    k = config.SYNTH_MAP_HINGE_STEEPNESS
    hinge = np.logaddexp(0.0, k * (f - f_c)) / k
    hinge0 = np.logaddexp(0.0, k * (0.0 - f_c)) / k  # so map_delta(0) == 0 exactly
    return -config.SYNTH_MAP_PRE_FC_SLOPE * f - config.SYNTH_MAP_POST_FC_SLOPE * (hinge - hinge0)


# ---------------------------------------------------------------------------
# 3.3 Confounders and artifacts (each an additive overlay on HR / MAP)
# ---------------------------------------------------------------------------
def stimulation_spike_hr(
    t_min: np.ndarray, rng: np.random.RandomState,
    onset_range: tuple[float, float] | None = None,
) -> tuple[np.ndarray, dict]:
    """Transient HR rise of +15..35 bpm for 2..6 min, 1-min ramps; MAP
    untouched. onset_range defaults to anywhere in the window."""
    dur = float(rng.uniform(*config.SYNTH_STIM_SPIKE_DURATION_MIN_RANGE))
    amp = float(rng.uniform(*config.SYNTH_STIM_SPIKE_HR_DELTA_RANGE))
    lo, hi = onset_range if onset_range is not None else (5.0, t_min.max() - dur - 2.0)
    onset = float(rng.uniform(lo, max(lo, hi)))
    ramp = 1.0
    up = np.clip((t_min - onset) / ramp, 0.0, 1.0)
    down = np.clip((onset + dur - t_min) / ramp, 0.0, 1.0)
    return amp * np.minimum(up, down), {"stim_onset_min": onset, "stim_duration_min": dur, "stim_hr_delta": amp}


def non_bleed_map_drop(t_min: np.ndarray, rng: np.random.RandomState) -> tuple[np.ndarray, dict]:
    """Anesthetic-like MAP drop with no HR rise or PP narrowing before it."""
    onset = float(rng.uniform(*config.SYNTH_NON_BLEED_ONSET_MIN_RANGE))
    onset = min(onset, max(5.0, t_min.max() - config.SYNTH_NON_BLEED_RAMP_MIN - 5.0))
    drop = float(rng.uniform(*config.SYNTH_NON_BLEED_MAP_DROP_RANGE_MMHG))
    ramp = np.clip((t_min - onset) / config.SYNTH_NON_BLEED_RAMP_MIN, 0.0, 1.0)
    return -drop * ramp, {"drop_onset_min": onset, "drop_mmhg": drop}


def inject_artifact(stream: pd.DataFrame, rng: np.random.RandomState, kind: str | None = None) -> tuple[pd.DataFrame, dict]:
    """Flatline (all tracks frozen), dropout (all NaN) or arterial-line
    flush spike (one sample of SBP/DBP/MAP pushed up)."""
    kind = kind or str(rng.choice(config.SYNTH_ARTIFACT_KINDS))
    out = stream.copy()
    t_min = out["Time"].to_numpy(dtype=float) / 60.0
    tracks = list(config.REQUIRED_NUMERIC_TRACKS)
    if kind == "flush_spike":
        i = int(rng.randint(len(out)))
        delta = float(rng.uniform(*config.SYNTH_ARTIFACT_FLUSH_SPIKE_DELTA_RANGE_MMHG))
        for col in (config.TRACK_SBP, config.TRACK_DBP, config.TRACK_MAP):
            out.loc[i, col] += delta
        return out, {"artifact": kind, "artifact_onset_min": float(t_min[i]), "artifact_delta": delta}

    rng_range = config.SYNTH_ARTIFACT_FLATLINE_DURATION_MIN_RANGE if kind == "flatline" else config.SYNTH_ARTIFACT_DROPOUT_DURATION_MIN_RANGE
    dur = float(rng.uniform(*rng_range))
    onset = float(rng.uniform(5.0, max(5.0, t_min.max() - dur - 2.0)))
    mask = (t_min >= onset) & (t_min <= onset + dur)
    if mask.any():
        if kind == "flatline":
            first = out.loc[mask, tracks].iloc[0]
            for col in tracks:
                out.loc[mask, col] = first[col]
        else:
            out.loc[mask, tracks] = np.nan
    return out, {"artifact": kind, "artifact_onset_min": onset, "artifact_duration_min": dur}


# ---------------------------------------------------------------------------
# Case generation (3.2 + 3.3 + 3.4 tiers)
# ---------------------------------------------------------------------------
@dataclass
class SynthCase:
    stream: pd.DataFrame
    meta: dict = field(default_factory=dict)


def generate_bleed_case(
    window_df: pd.DataFrame, tier: str, rng: np.random.RandomState,
    source_caseid: int | None = None, shifted: bool = False,
) -> SynthCase:
    """A bleed injected onto one real baseline window, per tier:
    T1 textbook (strong g_hr, moderate rate, residual x0.3, no confounders);
    T2 realistic (full residual, any rate, maybe one artifact);
    T3 blunted (g_hr cut 50-90%, mostly slow, maybe one artifact);
    T4 confounded (T2 plus an unrelated stimulation spike).
    The window is trimmed to fit a fitted bleed (see sample_bleed_params).
    The label comes from the stream: bleed_collapse if the primary MAP<65
    event occurs in-window, otherwise bleed_no_collapse."""
    if tier not in config.SYNTH_TIERS:
        raise ValueError(f"unknown tier {tier!r}")
    s = _real_signals(window_df)
    available_min = float(s["t"].max()) / 60.0 + 0.5
    pre = s["t"] / 60.0 <= config.SYNTH_PRE_BLEED_MAP_WINDOW_MIN
    map_pre = float(np.nanmedian(s["map"][pre])) if np.isfinite(s["map"][pre]).any() else float("nan")
    params = sample_bleed_params(rng, tier, available_min, shifted=shifted, map_pre=map_pre)

    # Size the window to the bleed: trim to expected collapse + a few minutes
    # of decompensation, never below the plan's 40-min minimum.
    window_len_min = available_min
    if params.fitted_to_window:
        window_len_min = float(np.clip(params.expected_collapse_min + config.SYNTH_POST_COLLAPSE_MIN,
                                       config.SYNTH_WINDOW_MIN_LEN_MIN, available_min))
    keep = s["t"] < window_len_min * 60.0
    s = {k: v[keep] for k, v in s.items()}
    t_min = s["t"] / 60.0

    f = blood_loss_fraction(t_min, params.t0_min, params.rate_frac_per_min)
    pp_pre = float(np.nanmedian(s["pp"][t_min <= params.t0_min]))
    noise_extra = config.SYNTH_TIER_RESIDUAL_SCALE[tier] - 1.0  # T1 damps the real residual
    hr = s["hr"] + noise_extra * np.nan_to_num(s["hr_resid"]) + hr_delta(f, params.g_hr)
    map_ = apply_map_floor(s["map"] + noise_extra * np.nan_to_num(s["map_resid"]) + map_delta(f, params.f_c))
    pp = s["pp"] + noise_extra * np.nan_to_num(s["pp_resid"]) + pp_delta(f, pp_pre)

    meta = {
        "is_bleed": True, "tier": tier, "shifted": shifted, "source_caseid": source_caseid,
        "source_start_s": window_df.attrs.get("source_start_s"),
        "t0_min": params.t0_min, "rate_band": params.rate_band, "rate_frac_per_min": params.rate_frac_per_min,
        "g_hr": params.g_hr, "f_c": params.f_c, "decompensation_min": params.decompensation_min,
        "fitted_to_window": params.fitted_to_window, "expected_collapse_min": params.expected_collapse_min,
        "map_pre_bleed": map_pre, "pp_pre_bleed": pp_pre,
        "window_len_min": window_len_min, "available_window_min": available_min,
    }
    if tier == "T4" and rng.uniform() < config.SYNTH_T4_STIM_SPIKE_PROB:
        dur_max = config.SYNTH_STIM_SPIKE_DURATION_MIN_RANGE[1]
        earliest = config.SYNTH_T4_STIM_EARLIEST_ONSET_MIN
        before_t0 = (earliest, params.t0_min - dur_max)
        after_t0 = (params.t0_min, params.decompensation_min - dur_max - 1.0)
        use_before = rng.uniform() < config.SYNTH_T4_STIM_BEFORE_T0_PROB or after_t0[1] < after_t0[0]
        onset_range = before_t0 if use_before else after_t0
        spike, spike_meta = stimulation_spike_hr(t_min, rng, onset_range=onset_range)
        hr = hr + spike
        meta.update(spike_meta)

    stream = _assemble_stream(s["t"], hr, map_, pp)
    if rng.uniform() < config.SYNTH_TIER_ARTIFACT_PROB[tier]:
        stream, art_meta = inject_artifact(stream, rng)
        meta.update(art_meta)

    collapse_min = first_collapse_min(stream)
    meta["collapse_min"] = collapse_min
    meta["collapses_in_window"] = collapse_min is not None
    meta["label"] = config.SYNTH_LABEL_BLEED_COLLAPSE if collapse_min is not None else config.SYNTH_LABEL_BLEED_NO_COLLAPSE
    return SynthCase(stream=stream, meta=meta)


def scored_cases(cases: list["SynthCase"]) -> list["SynthCase"]:
    """Cases that enter sensitivity / FA-rate / lead-time metrics:
    bleed_collapse positives and the negatives. bleed_no_collapse is
    excluded (no collapse event to compare against) and is reported
    descriptively via descriptive_only_cases()."""
    return [c for c in cases if c.meta["label"] not in config.SYNTH_DESCRIPTIVE_ONLY_LABELS]


def descriptive_only_cases(cases: list["SynthCase"]) -> list["SynthCase"]:
    return [c for c in cases if c.meta["label"] in config.SYNTH_DESCRIPTIVE_ONLY_LABELS]


def first_collapse_min(stream: pd.DataFrame) -> float | None:
    """Minute of the first primary event (MAP < 65 sustained >= 60 s) in the
    generated stream -- the same detector that labels real data -- or None
    if MAP never gets there before the window ends."""
    events = labels.detect_primary_events(stream)
    return events[0].start_time / 60.0 if events else None


def generate_negative_case(
    window_df: pd.DataFrame, kind: str, rng: np.random.RandomState,
    tier: str | None = None, source_caseid: int | None = None,
) -> SynthCase:
    """No bleed. kind: clean | non_bleed_hypotension | stimulation_spike |
    artifact. Same noise level as the tier's bleed streams, and the same
    chance of an artifact overlay, so neither can tell bleed from no-bleed
    ("artifact" forces one)."""
    if kind not in config.SYNTH_NEGATIVE_KINDS:
        raise ValueError(f"unknown negative kind {kind!r}")
    s = _real_signals(window_df)
    t_min = s["t"] / 60.0
    noise_extra = (config.SYNTH_TIER_RESIDUAL_SCALE[tier] - 1.0) if tier is not None else 0.0
    hr = s["hr"] + noise_extra * np.nan_to_num(s["hr_resid"])
    map_ = s["map"] + noise_extra * np.nan_to_num(s["map_resid"])
    pp = s["pp"] + noise_extra * np.nan_to_num(s["pp_resid"])
    meta = {"label": kind, "is_bleed": False, "tier": tier, "source_caseid": source_caseid,
            "source_start_s": window_df.attrs.get("source_start_s")}
    if kind == "non_bleed_hypotension":
        drop, m = non_bleed_map_drop(t_min, rng)
        map_ = map_ + drop
        meta.update(m)
    elif kind == "stimulation_spike":
        spike, m = stimulation_spike_hr(t_min, rng)
        hr = hr + spike
        meta.update(m)
    stream = _assemble_stream(s["t"], hr, map_, pp)
    artifact_prob = config.SYNTH_TIER_ARTIFACT_PROB[tier] if tier is not None else 0.0
    if kind == "artifact" or rng.uniform() < artifact_prob:
        stream, m = inject_artifact(stream, rng)
        meta.update(m)
    return SynthCase(stream=stream, meta=meta)


def generate_tier_cases(
    windows: list[tuple[int, pd.DataFrame]], tier: str, seed: int = config.SYNTH_GENERATOR_SEED,
    shifted: bool = False,
) -> list[SynthCase]:
    """One bleed case and one negative (kind drawn from the tier's pool)
    per baseline window. Deterministic for a given seed and window list."""
    rng = np.random.RandomState(seed)
    out = []
    for caseid, w in windows:
        out.append(generate_bleed_case(w, tier, rng, source_caseid=caseid, shifted=shifted))
        kind = str(rng.choice(config.SYNTH_TIER_NEGATIVE_KINDS[tier]))
        out.append(generate_negative_case(w, kind, rng, tier=tier, source_caseid=caseid))
    return out
