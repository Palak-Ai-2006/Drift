"""ATLS-inspired hemorrhage simulator — reference curves, always SYNTHETIC.

Phase 5 (PLAN.md Section 5, Phase 5). Not yet implemented.
Exports mean HR/MAP/SBP/DBP/PP at blood-volume-fraction-lost f from
config.SIM_BLOOD_LOSS_FRACTION_MIN to MAX in SIM_BLOOD_LOSS_FRACTION_STEP
steps, for blunted = False and True, to web/data/sim_curves.js as
window.DRIFT_SIM. The drift score here is a transparent rule
(config.SIM_DRIFT_SCORE_*), not the trained VitalDB model — label it as such
in the UI.
"""
