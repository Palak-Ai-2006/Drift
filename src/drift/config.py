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
