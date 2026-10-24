# DATA_CARD

**Status: pre-event scaffold (Phase 0).** This card is filled in progressively: the
inclusion/exclusion funnel and Cohort A/B counts in Phase 2, the causality/selection
rules for replay cases in Phase 6.1, and finalized as a one-page generated summary in
Phase 7 (Oct 24 decision — one page, numbers from `artifacts/metrics.json`, nothing
hand-typed).

## Source

VitalDB — 6,388 non-cardiac surgical cases, Seoul National University Hospital,
2016–2017. Open access, CC BY 4.0, no credentialing. See [DATA_NOTES.md](DATA_NOTES.md)
for the full access details and citations.

## Eligibility (Phase 2) — partial (clinical-table criteria done; vitals-based criterion pending)

- Eligible case definition, exclusion window, artifact-rejection bounds: see
  `src/drift/config.py` and PLAN.md Section 2.
- **Clinical-table-derivable eligibility funnel, run for real 2026-10-24
  (`scripts/02_build_cohort.py`, `src/drift/cohort.py`):**
  - Total cases in clinical table: **6,388**
  - Age ≥ 18: **6,331** (57 pediatric cases, age range 0.3–94 years, excluded per
    `config.ELIGIBLE_MIN_AGE_YEARS`)
  - With an invasive arterial line recorded (`aline1` and/or `aline2` non-null,
    proxy for the four numeric tracks being available): **3,463**
  - **Age ≥18 AND arterial line present: 3,419** — this is the clinical-table
    portion of eligibility, i.e. a necessary-but-not-sufficient proxy for the
    full definition.
  - **Still pending, needs real per-case vitals (bulk download, gated per
    Decision 1):** the ≥60-minute-usable-monitoring-after-exclusion-window
    criterion. Until that runs, "3,419" is *not* the final eligible-case count
    — it's an upper bound (every truly eligible case must pass this filter
    too, but not every case that passes this filter is eligible).
  - With all four numeric tracks *confirmed* present per-case: **confirmed on a
    5-case test sample 2026-10-24** (caseids 6269, 757, 6293, 2911, 2349, sampled
    deterministically from the arterial-line subset, seed=42) — all 5 have all 4
    tracks present, 88–99% coverage per track. Full per-case confirmation across
    all ~300–500 cases happens in the bulk download, deferred per Decision 1.
  - By `intraop_ebl` bucket (all 6,388 cases, not yet filtered to eligible):
    0 mL: 11 · 1–100 mL: 1,899 · 101–500 mL: 1,547 · >500 mL: 530 · not recorded
    (NaN): 2,401.

## Cohorts (Phase 2) — TODO

## Cohorts (Phase 2) — TODO

- **Cohort A** (all eligible): count TODO.
- **Cohort B** (high blood loss): rule fixed Oct 24 — RBC transfusion OR
  `intraop_ebl` ≥ 500 mL; falls back to the top quartile of `intraop_ebl` if that
  gives fewer than 60 cases or under 10% of eligible cases. **Final choice and
  resulting counts: TODO, recorded here once decided from the actual distribution
  and never changed afterwards.**
  - *Updated 2026-10-24, refined signal (still not final — see the "pending"
    note under Eligibility above): applying the fixed Cohort B rule to the
    3,419 clinical-table-eligible cases (age≥18 + arterial line, not yet
    vitals-filtered) gives* **654 cases (19.1%) via the primary rule** — no
    fallback needed. This comfortably clears both the 60-case and 10% fallback
    bars. (Earlier, cruder signal computed on all 6,388 cases before any
    eligibility filtering: 740 cases / 11.6% — superseded by the number above,
    kept here only for the record.) Still must be re-run once the vitals-based
    eligibility criterion is added, since the true eligible set is a subset of
    these 3,419.

## Event definition (Phase 2/7.1) — status

- Primary/headline: MAP < 65 mmHg sustained ≥ 60 s (PLAN.md Section 7.1, Oct 24
  decision). **Fallback switch applied: No** (see `config.EVENT_DEFINITION_FALLBACK_APPLIED`).
  If this changes, it is recorded here, once, before training, and not reversed.
- Secondary (reported separately, never as the headline): SBP < 90 mmHg sustained
  ≥ 60 s; 30 s duration version.

## Replay case selection (Phase 6.1) — TODO

Selection rules (best / typical / miss / false-alarm / insufficient-data, from the
test set only) are written in `src/drift/config.py` / `src/drift/replay.py` and
documented here once Phase 6.1 runs. Includes the A4 "selected examples, not
average performance" note and, if no miss or false-alarm case exists in the test
set, a statement to that effect plus the closest examples shown instead.

## Known caveats

- EBL and transfusion totals are end-of-case, with no timing — they only select
  which cases go in Cohort B; they are never model input features.
- This is surgical (intraoperative) data, not prehospital trauma data. The label
  is low blood pressure, not hemorrhage specifically.
- Single hospital, single country, 2016–2017. Not validated for generalization.
