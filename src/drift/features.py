"""Strictly causal feature computation and window labeling.

Phase 3 (PLAN.md Section 3, Section 6 Phase 3). Not yet implemented.
Every feature at prediction time t must use only samples at or before t
(Adjustment A3 — the single most important integrity requirement). This is
verified by a dedicated causality unit test (recompute from truncated data,
confirm the result matches) before any phase that depends on this module is
marked done.
"""
