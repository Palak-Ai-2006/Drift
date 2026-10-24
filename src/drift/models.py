"""Logistic regression and HistGradientBoostingClassifier, with calibration.

Phase 4 (PLAN.md Section 4, Phase 4). Not yet implemented.
Model-selection rule (Oct 24 decision, config.MODEL_SELECT_*): ship the
logistic model unless the boosted model beats it on the VALIDATION set by
both the AUPRC bootstrap-CI bar and the sensitivity-gain bar. Decide on
validation only; never use the test set to pick the model. The logistic
model's coefficients and feature scaling are always saved, since they power
the web demo's "why" panel regardless of which model is shipped for the
headline numbers.
"""
