"""ATLS-inspired hemorrhage simulator -- reference curves, always SYNTHETIC.

Phase 5 (PLAN.md Section 5, Phase 5).
Exports mean HR/MAP/SBP/DBP/PP at blood-volume-fraction-lost f from
config.SIM_BLOOD_LOSS_FRACTION_MIN to MAX in SIM_BLOOD_LOSS_FRACTION_STEP
steps, for blunted = False and True, to web/data/sim_curves.js as
window.DRIFT_SIM. The drift score here is a transparent rule
(config.SIM_DRIFT_SCORE_*), not the trained VitalDB model -- labeled as such
in the UI, and explicitly as "illustrative of textbook ATLS physiology, not
confirmed in our data" (round 3 user instruction, 2026-10-24): the Phase 4
work found the trained model does not clearly beat a MAP threshold on real
data, so this simulator must never be presented as validating it.

Curve shapes (smooth, monotonic, anchored loosely to the ATLS classes
PLAN.md Section 5 describes -- not a precise clinical model):
- HR(f) = HR0 + HR_RISE_COEF * f^HR_RISE_EXPONENT * (blunted ? 0.35 : 1).
  Power-law rise, coefficient chosen so HR ~ ATLS Class II/III/IV ranges
  near f ~ 0.15/0.30/0.40 (see tests/test_simulator.py).
- PP(f) = PP0 - (PP0 - PP_FLOOR) * (1 - exp(-PP_DECAY_RATE * f)).
  Exponential narrowing -- fastest early, consistent with "narrows early."
- MAP(f) = MAP0 - PRE_COMPENSATION_SLOPE * f
           - POST_COMPENSATION_SLOPE * softplus(STEEPNESS * (f - f_c)) / STEEPNESS.
  A smooth hinge: ~flat (small pre-compensation slope only) for f well below
  f_c, falling at POST_COMPENSATION_SLOPE per unit f beyond it -- softplus
  (log(1+exp(x))) is the standard smooth approximation to max(0, x), so
  there is no sharp kink at f_c.
- SBP = MAP + (2/3)*PP, DBP = MAP - (1/3)*PP (config.SIM_SBP/DBP_FROM_MAP_PP_COEF).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import config

ROOT = Path(__file__).resolve().parents[2]
SIM_CURVES_JS = ROOT / "web" / "data" / "sim_curves.js"

HR0 = 72.0
SBP0 = 120.0
DBP0 = 78.0
PP0 = SBP0 - DBP0  # 42, matches config.SIM_DRIFT_SCORE_PP_BASELINE
MAP0 = DBP0 + PP0 / 3.0  # 92

HR_RISE_COEF = 222.0
HR_RISE_EXPONENT = 1.3

PP_FLOOR = 15.0
PP_DECAY_RATE = 6.0

MAP_FLOOR = 40.0
PRE_COMPENSATION_SLOPE = 5.0
POST_COMPENSATION_SLOPE = 150.0
STEEPNESS = 40.0


def _softplus(x: np.ndarray) -> np.ndarray:
    # Numerically stable: log(1+exp(x)) without overflow for large x.
    return np.logaddexp(0.0, x)


def hr_curve(f: np.ndarray, blunted: bool) -> np.ndarray:
    multiplier = config.SIM_BLUNTED_HR_RESPONSE_MULTIPLIER if blunted else 1.0
    return HR0 + multiplier * HR_RISE_COEF * np.power(f, HR_RISE_EXPONENT)


def pp_curve(f: np.ndarray) -> np.ndarray:
    return PP0 - (PP0 - PP_FLOOR) * (1.0 - np.exp(-PP_DECAY_RATE * f))


def map_curve(f: np.ndarray, f_c: float = config.SIM_COMPENSATION_LIMIT_FRACTION_DEFAULT) -> np.ndarray:
    hinge = _softplus(STEEPNESS * (f - f_c)) / STEEPNESS
    return MAP0 - PRE_COMPENSATION_SLOPE * f - POST_COMPENSATION_SLOPE * hinge


def compute_curves(f: np.ndarray, blunted: bool) -> dict[str, np.ndarray]:
    hr = hr_curve(f, blunted)
    pp = pp_curve(f)
    map_ = map_curve(f)
    sbp = map_ + config.SIM_SBP_FROM_MAP_PP_COEF * pp
    dbp = map_ - config.SIM_DBP_FROM_MAP_PP_COEF * pp
    return {"hr": hr, "map": map_, "sbp": sbp, "dbp": dbp, "pp": pp}


def drift_rule_score(hr: np.ndarray, pp: np.ndarray) -> np.ndarray:
    """The simulator's OWN transparent rule score (config.SIM_DRIFT_SCORE_*)
    -- never the trained VitalDB model. Alert at >= SIM_DRIFT_SCORE_ALERT_THRESHOLD."""
    raw = 100.0 * (
        0.5 * (hr - config.SIM_DRIFT_SCORE_HR_BASELINE) / config.SIM_DRIFT_SCORE_HR_SCALE
        + 0.5 * (config.SIM_DRIFT_SCORE_PP_BASELINE - pp) / config.SIM_DRIFT_SCORE_PP_SCALE
    )
    return np.clip(raw, 0.0, 100.0)


def alert_and_map65_points(f: np.ndarray, curves: dict[str, np.ndarray]) -> dict:
    """First f at which the rule score crosses the alert threshold, and
    first f at which MAP < 65 -- printed for both blunted settings per the
    Phase 5 accept criterion."""
    drift = drift_rule_score(curves["hr"], curves["pp"])
    alert_idx = np.argmax(drift >= config.SIM_DRIFT_SCORE_ALERT_THRESHOLD)
    alert_f = float(f[alert_idx]) if drift[alert_idx] >= config.SIM_DRIFT_SCORE_ALERT_THRESHOLD else None
    below65_idx = np.argmax(curves["map"] < 65.0)
    below65_f = float(f[below65_idx]) if curves["map"][below65_idx] < 65.0 else None
    return {"alert_f": alert_f, "map_below_65_f": below65_f}


def build_sim_export() -> dict:
    f = np.arange(
        config.SIM_BLOOD_LOSS_FRACTION_MIN,
        config.SIM_BLOOD_LOSS_FRACTION_MAX + config.SIM_BLOOD_LOSS_FRACTION_STEP / 2,
        config.SIM_BLOOD_LOSS_FRACTION_STEP,
    )
    curves_false = compute_curves(f, blunted=False)
    curves_true = compute_curves(f, blunted=True)
    return {
        "f": f.tolist(),
        "blunted_false": {k: v.tolist() for k, v in curves_false.items()},
        "blunted_true": {k: v.tolist() for k, v in curves_true.items()},
        "meta": {
            "f_min": config.SIM_BLOOD_LOSS_FRACTION_MIN,
            "f_max": config.SIM_BLOOD_LOSS_FRACTION_MAX,
            "f_step": config.SIM_BLOOD_LOSS_FRACTION_STEP,
            "f_c": config.SIM_COMPENSATION_LIMIT_FRACTION_DEFAULT,
            "atls_class_i_max_fraction": config.SIM_ATLS_CLASS_I_MAX_FRACTION,
            "atls_class_ii_max_fraction": config.SIM_ATLS_CLASS_II_MAX_FRACTION,
            "atls_class_iii_max_fraction": config.SIM_ATLS_CLASS_III_MAX_FRACTION,
            "blunted_hr_multiplier": config.SIM_BLUNTED_HR_RESPONSE_MULTIPLIER,
            "drift_score_hr_baseline": config.SIM_DRIFT_SCORE_HR_BASELINE,
            "drift_score_hr_scale": config.SIM_DRIFT_SCORE_HR_SCALE,
            "drift_score_pp_baseline": config.SIM_DRIFT_SCORE_PP_BASELINE,
            "drift_score_pp_scale": config.SIM_DRIFT_SCORE_PP_SCALE,
            "drift_score_alert_threshold": config.SIM_DRIFT_SCORE_ALERT_THRESHOLD,
            "bleed_profiles": list(config.SIM_BLEED_PROFILES),
            "map_event_threshold_mmhg": config.EVENT_MAP_THRESHOLD_MMHG,
            "disclaimer": (
                "Illustrative of textbook ATLS physiology. Not confirmed in our data: "
                "Phase 4 found the trained model does not clearly outperform a simple MAP "
                "threshold on real surgical cases. This simulator uses a transparent rule "
                "score, not the trained model, and is synthetic throughout."
            ),
        },
    }


def write_sim_curves_js(dest: Path = SIM_CURVES_JS) -> Path:
    data = build_sim_export()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(f"window.DRIFT_SIM = {json.dumps(data, indent=2)};\n")
    return dest
