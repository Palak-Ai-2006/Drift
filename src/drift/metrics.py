"""Evaluation metrics: sensitivity, lead time, false-alarm rate, AUROC/AUPRC,
Brier score, bootstrap confidence intervals by case.

Phase 4 (PLAN.md Section 4, Section 7.5-7.6, Section 8). Not yet implemented.
Test set is evaluated once; never tuned on afterwards (CLAUDE.md Section 12).
Bootstrap resampling is by case (config.BOOTSTRAP_RESAMPLE_BY), not by row.
Writes artifacts/metrics.json, the single source of truth for every number
that later appears in the web demo, DATA_CARD.md, MODEL_CARD.md, Devpost text,
and the video script.
"""
