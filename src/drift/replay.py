"""Replay case selection and causal risk export for the web demo.

Phase 6.1 (PLAN.md Section 6.1, Phase 6). Not yet implemented.
Selects best/typical/miss/false_alarm (+ insufficient-data if one exists)
examples from the TEST SET only, by written rules (to be added to this module
and documented in DATA_CARD.md). Risk values are computed causally at each
prediction time using only data up to that time (Adjustment A3) — verified by
a check script that recomputes risk at sampled timepoints from truncated data
and confirms a match. Writes web/data/replay_cases.js, model_meta.js, proof.js
as window.* globals (not .json), with every number read from
artifacts/metrics.json — never hand-typed (CLAUDE.md Section 12).
"""
