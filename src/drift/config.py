"""All constants for the Drift pipeline live here (PLAN.md Section 5, Section 6B;
CLAUDE.md Section 12: "All constants in config.py; fixed seed; deterministic outputs.").

Status: Phase 0 scaffold. Values below are either (a) fixed decisions already made
(PLAN.md Section 6B and the Oct 24 decisions), or (b) placeholders marked TODO that
get set/verified in the phase named in their comment. Never guess a dataset column
or track name — the ones below were read from the downloaded inventory
(data/manual/track_names.csv, data/manual/clinical_parameters.csv, confirmed
2026-10-24; see DATA_NOTES.md) before being written here.
"""

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
RANDOM_SEED = 42

# ---------------------------------------------------------------------------
# VitalDB access (Phase 1) — names confirmed 2026-10-24 against
# data/manual/track_names.csv and data/manual/clinical_parameters.csv.
# ---------------------------------------------------------------------------
VITALDB_CASES_URL = "https://api.vitaldb.net/cases"
VITALDB_CASE_PARQUET_URL_TMPL = "https://api.vitaldb.net/{caseid}.parquet"
VITALDB_MIN_CASEID = 1
VITALDB_MAX_CASEID = 6388
VITALDB_FULL_DATASET_SIZE_GB = 95.4  # never download in full

# Confirmed numeric tracks (Type "N" in track_names.csv), Device/Channel format.
TRACK_HR = "Solar8000/HR"
TRACK_SBP = "Solar8000/ART_SBP"
TRACK_DBP = "Solar8000/ART_DBP"
TRACK_MAP = "Solar8000/ART_MBP"
# 500 Hz arterial waveform — confirmed present (Type "W/500") but NOT used in v2
# (Adjustment A2: heartbeat indicator is driven by the HR number, not this track).
TRACK_ART_WAVEFORM = "SNUADC/ART"

REQUIRED_NUMERIC_TRACKS = (TRACK_HR, TRACK_SBP, TRACK_DBP, TRACK_MAP)

# Phase 4 Experiment 2 (bleeding-flavored label) -- vasopressor/anesthetic
# tracks, confirmed present in data/manual/track_names.csv 2026-10-24 (never
# guessed). Continuous-infusion rate tracks only: bolus-only pressors
# (e.g. ephedrine, cases.csv's intraop_eph) are not time-resolved in
# VitalDB's numeric tracks and can't be checked this way -- documented
# limitation, not fixable with the tracks this project downloads.
VASOPRESSOR_RATE_TRACKS = (
    "Orchestra/NEPI_RATE",  # norepinephrine
    "Orchestra/EPI_RATE",  # epinephrine
    "Orchestra/PHEN_RATE",  # phenylephrine
    "Orchestra/VASO_RATE",  # vasopressin
    "Orchestra/DOPA_RATE",  # dopamine
)
# Expired volatile anesthetic concentration -- whichever a case actually
# uses (sevoflurane or desflurane); not every case has non-null data for
# both, since agent choice varies by case.
VOLATILE_ANESTHETIC_TRACKS = ("Primus/EXP_SEVO", "Primus/EXP_DES")
DRUG_TRACKS = VASOPRESSOR_RATE_TRACKS + VOLATILE_ANESTHETIC_TRACKS

# Confirmed clinical columns (cases.csv header, 2026-10-24).
COL_CASEID = "caseid"
COL_SUBJECTID = "subjectid"
COL_AGE = "age"
COL_SEX = "sex"
COL_WEIGHT = "weight"
COL_HEIGHT = "height"  # confirmed present in data/manual/cases.csv header, 2026-10-24
COL_ASA = "asa"
COL_EMOP = "emop"
COL_OPSTART = "opstart"
COL_OPEND = "opend"
COL_ANESTART = "anestart"
COL_ANEEND = "aneend"
COL_ALINE1 = "aline1"
COL_ALINE2 = "aline2"
COL_INTRAOP_EBL = "intraop_ebl"
COL_INTRAOP_RBC = "intraop_rbc"
COL_INTRAOP_FFP = "intraop_ffp"
COL_INTRAOP_CRYSTALLOID = "intraop_crystalloid"
COL_INTRAOP_COLLOID = "intraop_colloid"
COL_INTRAOP_UO = "intraop_uo"

# End-of-case totals: selection-only fields. CLAUDE.md Section 12 /
# PLAN.md Section 2 caveat: these choose which cases go in Cohort B; they are
# NEVER used as model input features.
END_OF_CASE_SELECTION_ONLY_COLS = (
    COL_INTRAOP_EBL,
    COL_INTRAOP_RBC,
    COL_INTRAOP_FFP,
    COL_INTRAOP_CRYSTALLOID,
    COL_INTRAOP_COLLOID,
    COL_INTRAOP_UO,
)

# Download sizing (Phase 1) — TODO: measure on the first 5 cases, update if needed.
DOWNLOAD_TARGET_CASES_MIN = 300
DOWNLOAD_TARGET_CASES_MAX = 500
DOWNLOAD_HIGH_LOSS_OR_TRANSFUSED_FRACTION_TARGET = 1 / 3  # "about a third"
PHASE1_TEST_CASE_COUNT = 5  # measure size/time on this many before bulk download

# ---------------------------------------------------------------------------
# Phase 1 decision-gate tiers (Oct 24 decision; PLAN.md Section 6/10)
# ---------------------------------------------------------------------------
DECISION_GATE_TIER1_MIN_CASES = 300
DECISION_GATE_TIER1_MIN_EVENTS = 100
DECISION_GATE_TIER2_MIN_CASES = 150
DECISION_GATE_TIER2_MIN_EVENTS = 60
# Below DECISION_GATE_TIER2_MIN_CASES/EVENTS: pivot to simulator-first,
# no performance claims (PLAN.md Section 6/10, tier 3).

# ---------------------------------------------------------------------------
# Phase 2: cohort and artifact rejection (PLAN.md Section 2)
# ---------------------------------------------------------------------------
ELIGIBLE_MIN_AGE_YEARS = 18
ELIGIBLE_MIN_MONITORED_MIN_AFTER_EXCLUSION = 60
EXCLUSION_WINDOW_AFTER_ANESTHESIA_START_MIN = 15  # induction hypotension expected

ARTIFACT_MAP_MIN, ARTIFACT_MAP_MAX = 20, 250
ARTIFACT_SBP_MIN, ARTIFACT_SBP_MAX = 30, 300
ARTIFACT_DBP_MIN, ARTIFACT_DBP_MAX = 10, 200
ARTIFACT_HR_MIN, ARTIFACT_HR_MAX = 20, 250
MAX_INTERPOLATION_GAP_S = 60  # no interpolation beyond this

# Cohort B (high blood loss) — Oct 24 decision, locked before any model results.
COHORT_B_MIN_EBL_ML = 500  # intraop_ebl >= this, OR any RBC transfusion
COHORT_B_FALLBACK_MIN_CASES = 60
COHORT_B_FALLBACK_MIN_FRACTION_OF_ELIGIBLE = 0.10
# If Cohort B (as defined above) has fewer than COHORT_B_FALLBACK_MIN_CASES cases,
# or fewer than COHORT_B_FALLBACK_MIN_FRACTION_OF_ELIGIBLE of eligible cases,
# fall back to: top quartile of intraop_ebl among eligible cases.
# Record the final choice + counts in DATA_CARD.md; never change after seeing results.

# ---------------------------------------------------------------------------
# Event definition (PLAN.md Section 7, Oct 24 decision — final)
# ---------------------------------------------------------------------------
# PRIMARY / HEADLINE definition. Never change after training starts, except via
# the one-time fallback switch below.
EVENT_MAP_THRESHOLD_MMHG = 65
EVENT_SUSTAINED_DURATION_S = 60

# SECONDARY definitions — reported separately, never in the headline.
EVENT_FALLBACK_DURATION_S = 30
EVENT_FALLBACK_SBP_THRESHOLD_MMHG = 90

# One-time fallback switch: if Phase 1's event count is in the
# DECISION_GATE_TIER2_* band (or below tier 1), EVENT_SUSTAINED_DURATION_S may be
# dropped to EVENT_FALLBACK_DURATION_S (or the definition changed to the SBP
# version) ONCE, before training. If used, set this flag and state it in
# DATA_CARD.md. Do not flip it back afterwards.
EVENT_DEFINITION_FALLBACK_APPLIED = False  # TODO: set in Phase 1/2 if triggered

# ---------------------------------------------------------------------------
# Phase 3: windows, labels, features (PLAN.md Section 3, Section 7)
# ---------------------------------------------------------------------------
PREDICTION_STRIDE_MIN = 1
HORIZON_MIN_PRIMARY = 15
HORIZON_MIN_OPTIONS = (5, 10, 15, 30)
EXCLUDE_IF_RECENT_MAP_LOW_LOOKBACK_MIN = 5  # exclude t if MAP<65 in previous 5 min

FEATURE_SLOPE_WINDOWS_MIN = (5, 10, 15)
FEATURE_BASELINE_WINDOW_MIN = 10  # median of first 10 usable min after exclusion

# Missing-data / insufficient-data cutoff (Oct 24 decision — finalized).
INSUFFICIENT_DATA_MISSING_FRACTION = 0.30
INSUFFICIENT_DATA_MAX_EXCLUDED_WINDOW_FRACTION = 0.10  # check on validation

# ---------------------------------------------------------------------------
# Phase 4: baselines, models, evaluation (PLAN.md Section 4)
# ---------------------------------------------------------------------------
SPLIT_TRAIN_FRAC, SPLIT_VAL_FRAC, SPLIT_TEST_FRAC = 0.6, 0.2, 0.2

BASELINE_B2_EARLY_MAP_THRESHOLD_RANGE_MMHG = (70, 75)  # tuned to match FA rate
BASELINE_B3_SHOCK_INDEX_THRESHOLD = 0.9  # also tuned
# BASELINE_B4 (MAP-slope rule): threshold TODO, set and tuned in Phase 4.

ALARM_REFRACTORY_MIN = 15
ALARM_OPERATING_POINT_FA_PER_PATIENT_HOUR = 1.0  # primary operating point
ALARM_OPERATING_POINT_FA_ALTERNATES_PER_PATIENT_HOUR = (0.5, 2.0)  # also reported

# Model-selection rule (Oct 24 decision): ship logistic unless boosted model
# clears BOTH bars below, decided on the VALIDATION set only (never test).
MODEL_SELECT_MIN_SENSITIVITY_GAIN_PP = 5
MODEL_SELECT_REQUIRE_AUPRC_CI_EXCLUDES_ZERO = True

BOOTSTRAP_N_RESAMPLES = 1000  # TODO: confirm compute budget allows this in Phase 4
BOOTSTRAP_CI_LEVEL = 0.95
BOOTSTRAP_RESAMPLE_BY = "caseid"  # bootstrap by case, not by row

# ---------------------------------------------------------------------------
# Phase 4 timeline guard (Oct 24 decision, Section 11)
# ---------------------------------------------------------------------------
PHASE4_HARD_DEADLINE_HOUR = 10  # if not done by this hour, stop Phase 5 work

# ---------------------------------------------------------------------------
# Phase 4.5 / Round 4: semi-synthetic bleed-injection generator
# (SYNTHETIC_PLAN.md Section 3 — the source of truth for design and
# rationale; this is just the constants). Baseline segments are real,
# stable stretches of VitalDB TRAIN+VAL cases only (never the Round 1-3
# test cases, never the fresh 175-case holdout); the bleed trend and every
# confounder/artifact below are injected on top and are SYNTHETIC
# throughout. Frozen (no further edits) once tagged round4-generator-frozen.
# ---------------------------------------------------------------------------
SYNTH_GENERATOR_SEED = 4040  # separate from RANDOM_SEED so Round 4 work never silently shares draws with Phase 1-4

# 3.1 Baseline segment selection
SYNTH_WINDOW_MIN_LEN_MIN = 40
SYNTH_WINDOW_MAX_LEN_MIN = 60
SYNTH_WINDOW_SEARCH_STRIDE_MIN = 5  # candidate window starts, scanned at this stride
SYNTH_MIN_BEFORE_CASE_END_MIN = 15  # window end must be >= this long before op end
SYNTH_STABLE_LOOKAROUND_MIN = 10  # "within +-10 min" for the MAP-event / drug-change checks
SYNTH_MISSING_FRACTION_MAX = INSUFFICIENT_DATA_MISSING_FRACTION  # reuse the existing artifact threshold
SYNTH_DRUG_FLAT_TOLERANCE = 1e-6  # max allowed change in a drug-rate track across a "stable" window
SYNTH_RESIDUAL_ROLLING_MEDIAN_MIN = 5.0  # slow component removed to get the real noise residual
# Reject windows holding a real flush-type jump: any sample whose MAP or
# pulse pressure departs from its 5-min rolling median by more than this.
# Below the injected flush artifact's smallest size (30 mmHg), so a window
# carrying the injected shape is always caught.
SYNTH_FLUSH_JUMP_REJECT_MMHG = 25.0

# 3.2 Bleed injection model
SYNTH_T0_MIN_INTO_WINDOW_MIN = 10  # bleed onset at least this far into the window
SYNTH_T0_MAX_FRACTION_OF_WINDOW = 0.4  # onset no later than this fraction of the window
# Fraction of blood volume lost per minute (x100 = %BV/min). Chosen so that
# reaching f_c ~0.30 takes ~12-50 min, i.e. collapse usually lands inside a
# 40-60 min window; cases that don't collapse in-window are flagged in meta.
SYNTH_RATE_BAND_SLOW = (0.006, 0.009)
SYNTH_RATE_BAND_MODERATE = (0.009, 0.014)
SYNTH_RATE_BAND_FAST = (0.014, 0.025)
SYNTH_RATE_BANDS = {
    "slow": SYNTH_RATE_BAND_SLOW,
    "moderate": SYNTH_RATE_BAND_MODERATE,
    "fast": SYNTH_RATE_BAND_FAST,
}
SYNTH_F_MAX = 0.55  # cap on injected blood-loss fraction

# Window-to-bleed sizing (SYNTHETIC_PLAN.md 3.4 amendment, pre-freeze): the
# window LENGTH stays within 40-60 min. For these tiers and rate bands, rate
# and t0 are sampled jointly so the expected collapse (f reaches the level
# that takes MAP below 65, plus a sustain margin) lands inside the
# longest stable window available; the window is then trimmed to collapse +
# SYNTH_POST_COLLAPSE_MIN (never below 40). Slow bleeds are not fitted.
SYNTH_FIT_COLLAPSE_TIERS = ("T1", "T2", "T4")
SYNTH_FIT_COLLAPSE_BANDS = ("moderate", "fast")
SYNTH_COLLAPSE_TARGET_BELOW_MMHG = 2.0   # aim this far under 65 so real noise doesn't break the 60-s run
SYNTH_COLLAPSE_SUSTAIN_MARGIN_MIN = 2.0  # 60-s sustain requirement plus slack
SYNTH_POST_COLLAPSE_MIN = 5.0            # decompensation shown after the expected collapse
SYNTH_PRE_BLEED_MAP_WINDOW_MIN = SYNTH_T0_MIN_INTO_WINDOW_MIN  # baseline MAP = median of the first 10 min

# Labels. The stream decides: an injected bleed whose MAP reaches the
# primary event (MAP < 65 for >= 60 s) inside the window is bleed_collapse;
# one that never does is bleed_no_collapse -- reported descriptively, never
# a positive or a negative in sensitivity / FA-rate / lead-time metrics.
SYNTH_LABEL_BLEED_COLLAPSE = "bleed_collapse"
SYNTH_LABEL_BLEED_NO_COLLAPSE = "bleed_no_collapse"
SYNTH_DESCRIPTIVE_ONLY_LABELS = (SYNTH_LABEL_BLEED_NO_COLLAPSE,)

SYNTH_G_HR_RANGE_NORMAL = (0.8, 1.2)         # heart-rate-gain multiplier, T2/T4
SYNTH_G_HR_RANGE_T1 = (1.0, 1.2)             # T1: "strong HR gain"
SYNTH_G_HR_RANGE_BLUNTED_SCALE = (0.1, 0.5)  # T3: g_hr further scaled by this (50-90% reduction)
SYNTH_F_C_MEAN = 0.30  # compensation-failure fraction, sampled per case
SYNTH_F_C_STD = 0.04
SYNTH_F_C_MIN, SYNTH_F_C_MAX = 0.18, 0.42

# Injected-trend curve shape -- this is the Round 4 generator's own design
# (independent of Phase 5's simulator.py curves, which are a separate,
# already-shipped artifact; never reused or changed here).
# HR delta = g_hr * GAIN * (1 - exp(-RATE * f)): at g_hr=1, about +34 / +52 /
# +60 bpm at f = 0.15 / 0.30 / 0.40 -- from a ~70 bpm anesthetized baseline
# that lands near the older ATLS ~100 / 120 / 130-140 cutoffs.
SYNTH_HR_GAIN_COEF = 75.0        # bpm, saturating limit at g_hr=1
SYNTH_HR_RISE_RATE = 4.0         # per unit f
SYNTH_PP_NARROWING_FRAC = 0.45   # fraction of the case's own pre-bleed PP lost at f -> infinity (saturating)
SYNTH_PP_DECAY_RATE = 5.0
SYNTH_PP_FLOOR_MMHG = 5.0        # PP must stay positive
SYNTH_MAP_PRE_FC_SLOPE = 4.0       # mmHg drift per unit f, before f_c ("small drift only")
SYNTH_MAP_POST_FC_SLOPE = 250.0    # mmHg drop per unit f beyond f_c ("falls steeply")
SYNTH_MAP_HINGE_STEEPNESS = 60.0   # softplus sharpness: ~0.2 mmHg extra drop at f_c - 0.05, ~2.9 at f_c
SYNTH_MAP_FLOOR_MMHG = 30.0        # injected collapse levels off here (smooth floor), never below
SYNTH_MAP_FLOOR_SOFTNESS_MMHG = 3.0

# 3.3 Negatives and confounders
SYNTH_STIM_SPIKE_HR_DELTA_RANGE = (15.0, 35.0)
SYNTH_STIM_SPIKE_DURATION_MIN_RANGE = (2.0, 6.0)
SYNTH_NON_BLEED_MAP_DROP_RANGE_MMHG = (10.0, 25.0)  # anesthetic-like drop, no HR/PP precursor
SYNTH_NON_BLEED_ONSET_MIN_RANGE = (10.0, 35.0)
SYNTH_NON_BLEED_RAMP_MIN = 5.0  # minutes over which the drop ramps in

SYNTH_ARTIFACT_FLATLINE_DURATION_MIN_RANGE = (1.0, 4.0)
SYNTH_ARTIFACT_DROPOUT_DURATION_MIN_RANGE = (0.5, 3.0)
SYNTH_ARTIFACT_FLUSH_SPIKE_DELTA_RANGE_MMHG = (30.0, 60.0)
SYNTH_ARTIFACT_KINDS = ("flatline", "dropout", "flush_spike")
SYNTH_NEGATIVE_KINDS = ("clean", "non_bleed_hypotension", "stimulation_spike", "artifact")

# 3.4 Difficulty tiers
SYNTH_TIERS = ("T1", "T2", "T3", "T4")
SYNTH_TIER_NAMES = {"T1": "textbook", "T2": "realistic", "T3": "blunted", "T4": "confounded"}
SYNTH_TIER_RESIDUAL_SCALE = {"T1": 0.3, "T2": 1.0, "T3": 1.0, "T4": 1.0}  # T1 = "light noise"
SYNTH_T1_RATE_BANDS = ("moderate",)  # T1: "moderate rate", restricted band
SYNTH_T3_RATE_BAND_WEIGHTS = {"slow": 0.6, "moderate": 0.3, "fast": 0.1}  # T3: "more slow bleeds"
# Chance that ANY stream (bleed or not) gets one artifact overlay. Same rate
# for every label within a tier, so artifacts can't hint at the label.
SYNTH_TIER_ARTIFACT_PROB = {"T1": 0.0, "T2": 0.3, "T3": 0.3, "T4": 0.3}
SYNTH_T4_STIM_SPIKE_PROB = 1.0  # T4 bleed streams always carry an unrelated stimulation spike
# ...placed before decompensation so it can actually confound, and mostly before t0.
SYNTH_T4_STIM_BEFORE_T0_PROB = 0.7
SYNTH_T4_STIM_EARLIEST_ONSET_MIN = 2.0
# Which negative kinds each tier's negative pool draws from (T1 has no
# confounders). Artifacts are an overlay on every stream at
# SYNTH_TIER_ARTIFACT_PROB, not a separate negative kind.
SYNTH_TIER_NEGATIVE_KINDS = {
    "T1": ("clean",),
    "T2": ("clean",),
    "T3": ("clean",),
    "T4": ("clean", "stimulation_spike", "non_bleed_hypotension"),
}

# Shifted test set (SYNTHETIC_PLAN.md 4.3): parameters partly outside training ranges.
SYNTH_SHIFTED_RATE_MULTIPLIER_RANGE = (0.6, 0.9)   # slower bleeds
SYNTH_SHIFTED_G_HR_MULTIPLIER_RANGE = (0.6, 0.9)   # lower g_hr
SYNTH_SHIFTED_T0_MAX_FRACTION_OF_WINDOW = 0.5      # later onset

# 4. Splits (own seed; baseline segments drawn from the Phase 4 train+val
# pool only -- see semisynth.get_baseline_pool_caseids)
SYNTH_SPLIT_SEED = 4042
SYNTH_SPLIT_TRAIN_FRAC, SYNTH_SPLIT_VAL_FRAC, SYNTH_SPLIT_TEST_FRAC = 0.6, 0.2, 0.2
SYNTH_SHIFTED_TEST_SEED = 4043  # separate seed for the robustness ("shifted") test set

# Round 4 evaluation rules -- fixed 2026-10-24 BEFORE any Round 4 model was
# trained (SYNTHETIC_PLAN.md Section 5a). Changing any of these after
# results exist must be written down and both results reported.
SYNTH_EVAL_WINDOW_SEEDS = {"train": 5100, "val": 5200, "test": 5300}  # baseline-window draw per split
SYNTH_EVAL_CASE_SEEDS = {"train": 6100, "val": 6200, "test": 7300, "test_shifted": SYNTH_SHIFTED_TEST_SEED}
SYNTH_EVAL_REPLICATES = 4  # per window per tier: each replicate = 1 bleed + 1 no-bleed stream
SYNTH_EVAL_HORIZON_MIN = HORIZON_MIN_PRIMARY  # 15 min, same label and alarm rules as real data
SYNTH_EVAL_FA_TARGETS = (0.5, 1.0, 2.0)
SYNTH_EVAL_PRIMARY_FA = 1.0
SYNTH_EVAL_TARGET_SENSITIVITY = 0.95  # SYNTHETIC_PLAN.md Section 5 target ...
SYNTH_EVAL_TARGET_TIERS = ("T1", "T2")  # ... on these tiers, at <= SYNTH_EVAL_PRIMARY_FA
# Phase 3 causal features minus demographics (absent in synthetic windows)
# and time-since-start features (meaningless on a re-based window).
SYNTH_FEATURE_COLUMNS = (
    "hr", "sbp", "dbp", "map", "pp", "pp_over_sbp", "shock_index",
    "map_std", "map_min", "missing_fraction",
    "hr_slope_5", "hr_slope_10", "hr_slope_15",
    "map_slope_5", "map_slope_10", "map_slope_15",
    "pp_slope_5", "pp_slope_10", "pp_slope_15",
    "shock_index_slope_5", "shock_index_slope_10", "shock_index_slope_15",
    "hr_drift", "map_drift", "pp_drift", "shock_index_drift",
)
SYNTH_MODEL_CANDIDATES = ("logistic", "boosted")
SYNTH_MODEL_SELECT_TIE_PP = 2.0        # within this many points of val sensitivity -> compare lead time
SYNTH_MODEL_SELECT_LEAD_TIE_MIN = 0.5  # within this -> logistic (simpler)
# "Standard monitor" comparator: MAP < 65 (= B1, fires at the event) OR
# HR > 120 OR SBP < 90. Typical bedside settings, NOT verified as any
# specific monitor's factory default -- label as such wherever quoted.
SYNTH_STANDARD_MONITOR_HR_HIGH = 120.0
SYNTH_STANDARD_MONITOR_SBP_LOW = 90.0
SYNTH_MISS_BLUNTED_G_HR = 0.5  # miss attributed to a blunted response below this g_hr

# ---------------------------------------------------------------------------
# Phase 5: hemorrhage simulator (PLAN.md Section 5) — ATLS-inspired, SYNTHETIC
# ---------------------------------------------------------------------------
SIM_BLOOD_LOSS_FRACTION_MIN = 0.0
SIM_BLOOD_LOSS_FRACTION_MAX = 0.45
SIM_BLOOD_LOSS_FRACTION_STEP = 0.005

# ATLS-inspired class boundaries (blood volume fraction lost), for reference/UI text.
# TODO (Phase 5): double-check these against a cited source before quoting in UI —
# DATA_NOTES.md / PLAN.md Section 14 flags ATLS ranges as standard teaching, UNVERIFIED.
SIM_ATLS_CLASS_I_MAX_FRACTION = 0.15
SIM_ATLS_CLASS_II_MAX_FRACTION = 0.30
SIM_ATLS_CLASS_III_MAX_FRACTION = 0.40
# Class IV: > 0.40, up to SIM_BLOOD_LOSS_FRACTION_MAX.

SIM_COMPENSATION_LIMIT_FRACTION_DEFAULT = 0.27  # f_c: MAP holds until this point
SIM_BLUNTED_HR_RESPONSE_MULTIPLIER = 0.35  # beta-blocker / elderly switch

SIM_SBP_FROM_MAP_PP_COEF = 2 / 3  # SBP = MAP + (2/3)*PP
SIM_DBP_FROM_MAP_PP_COEF = 1 / 3  # DBP = MAP - (1/3)*PP

# Transparent rule score for the SIMULATOR ONLY (not the trained model):
# drift = clamp(100*(0.5*(HR-HR0)/HR_SCALE + 0.5*(PP0-PP)/PP_SCALE), 0, 100)
SIM_DRIFT_SCORE_HR_BASELINE = 72
SIM_DRIFT_SCORE_HR_SCALE = 60
SIM_DRIFT_SCORE_PP_BASELINE = 42
SIM_DRIFT_SCORE_PP_SCALE = 28
SIM_DRIFT_SCORE_ALERT_THRESHOLD = 45

SIM_BLEED_PROFILES = ("slow_ooze", "steady", "sudden")
# Web demo time axis (2026-10-25): each profile bleeds at the midpoint of a
# Round 4 rate band (fraction of blood volume per minute), so the demo's
# "slow / steady / sudden" match the rates the Round 4 evaluation used. The
# Phase 5 curves themselves are unchanged -- they depend on blood lost only;
# the rate decides how many MINUTES that takes.
SIM_PROFILE_RATE_BANDS = {
    "slow_ooze": SYNTH_RATE_BAND_SLOW,
    "steady": SYNTH_RATE_BAND_MODERATE,
    "sudden": SYNTH_RATE_BAND_FAST,
}
SIM_WEB_PLAYBACK_SPEED_X = 90  # simulated minutes shown per real minute when "Play bleed" runs

# ---------------------------------------------------------------------------
# Phase 6.1: replay export (PLAN.md Section 6.1)
# ---------------------------------------------------------------------------
REPLAY_EXCERPT_BEFORE_EVENT_MIN = 40
REPLAY_EXCERPT_AFTER_EVENT_MIN = 10
REPLAY_EXPORT_RESOLUTION_S = 30
REPLAY_RISK_STRIDE_MIN = 1  # matches PREDICTION_STRIDE_MIN
REPLAY_CASES_PER_TYPE_TARGET = 2  # best, typical, miss, false_alarm; 2 each if available
REPLAY_TOP_FEATURES_N = 3
REPLAY_WEB_DATA_MAX_SIZE_MB = 10

# ---------------------------------------------------------------------------
# Phase 6.2: website (PLAN.md Section 6.2) — colors, speeds, thresholds the
# web demo reads from generated .js files, not hand-typed.
# ---------------------------------------------------------------------------
WEB_PLAYBACK_SPEED_OPTIONS_X = (10, 30, 60)
WEB_PLAYBACK_SPEED_DEFAULT_X = 30
WEB_HEART_PULSE_MAX_RATE_HZ = 3  # cap on-screen pulse rate so it never strobes

WEB_COLOR_BG = "#0E1116"
WEB_COLOR_PANEL = "#161B22"
WEB_COLOR_BORDER = "#2A313C"
WEB_COLOR_TEXT = "#E6EDF3"
WEB_COLOR_TEXT_SECONDARY = "#9BA7B4"
WEB_COLOR_TRACE_MAP = "#FF6B5E"
WEB_COLOR_TRACE_HR = "#4ADE80"
WEB_COLOR_TRACE_PP = "#38BDF8"
WEB_COLOR_STATE_MONITORING = "#9BA7B4"
WEB_COLOR_STATE_DRIFT_ALERT = "#F5B84B"
WEB_COLOR_STATE_STANDARD_ALARM = "#FF5C5C"
WEB_COLOR_BADGE_SYNTHETIC = "#B79CFF"
WEB_COLOR_BADGE_REAL_DATA = "#2DD4BF"

# ---------------------------------------------------------------------------
# Required UI/doc wording (CLAUDE.md Section 12 — exact strings, not paraphrased)
# ---------------------------------------------------------------------------
WORDING_SYNTHETIC_BADGE = "SYNTHETIC patient, not real data"
WORDING_SYNTHETIC_BANNER = "Simulated patient. Not real data."
WORDING_REAL_DATA_BADGE = "REAL DATA, surgical"
WORDING_REAL_DATA_FULL = "Recorded patient, surgical, VitalDB (Korea). Not live."
WORDING_REPLAY_BANNER_TMPL = "Recorded patient, sped up {speed}x. Not live."
WORDING_FOOTER = (
    "Research prototype · not for clinical use · "
    "no alert does not mean safe."
)
WORDING_SELECTED_EXAMPLES_NOTE = (
    "Selected examples, not average performance. "
    "Results across all test cases are in Proof and method."
)

# Alert naming. Round 3 (2026-10-24) labeled the shipped real-data alert
# "Early MAP-based alert" because nothing beat a plain MAP-only model.
# User decision 2026-10-25 (UI polish, Group 2): both demo tabs use the
# product name "Drift alert". The real-data model is UNCHANGED -- still
# MAP-only -- and the honesty note below, the banner detail text, the
# header tagline and MODEL_CARD.md all say so. See MODEL_CARD.md.
WORDING_ALERT_NAME = "Drift alert"
WORDING_MONITORING_BANNER = "Monitoring · no alert"
WORDING_ALERT_BANNER = (
    "DRIFT ALERT · Mean arterial pressure trending low. Check the patient."
)
WORDING_INSUFFICIENT_DATA_BANNER = "Not enough data to assess"
WORDING_STANDARD_ALARM_NOT_TRIGGERED = "Standard alarm: not triggered"
WORDING_STANDARD_ALARM_TRIGGERED = "STANDARD ALARM · MAP below 65"
WORDING_METHOD_HONESTY_NOTE = (
    "Both tabs call their alert a ‘Drift alert’ for consistency. On real "
    "surgical data, it is a calibrated, early MAP-based threshold, not a "
    "distinct ‘drift’ signal. We tested whether heart-rate, pulse-pressure and "
    "shock-index dynamics add value beyond MAP alone, under a pre-registered "
    "protocol with cross-validation and a held-out test set, across three "
    "rounds of iteration. They did not. A simple tuned MAP-only threshold "
    "(B2) performs similarly on our test data. Full methodology and results: "
    "Proof and method, and MODEL_CARD.md in the project repository."
)
WORDING_SIMULATOR_DISCLAIMER = (
    "Illustrative of textbook ATLS physiology. Not confirmed in our data."
)

# ---------------------------------------------------------------------------
# Phase 7: docs/test scope (Oct 24 decision — final; PLAN.md Phase 7)
# ---------------------------------------------------------------------------
PHASE7_REQUIRED_DOCS = ("README.md", "LIMITATIONS.md", "DEVPOST", "VIDEO")
PHASE7_ONE_PAGE_GENERATED_DOCS = ("DATA_CARD.md", "MODEL_CARD.md")
PHASE7_REQUIRED_TESTS = (
    "event_detector",
    "feature_causality",
    "split_disjointness",
    "replay_export_causality",
)
PHASE7_DRAFT_PLACEHOLDERS_BY_HOUR = 10
# If time slips, cut in this order:
PHASE7_CUT_ORDER = (
    "boosted_model",
    "horizon_sweep",
    "insufficient_data_example_case",
    "model_card_as_separate_file",
)
