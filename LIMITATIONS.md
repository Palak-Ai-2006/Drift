# LIMITATIONS

**Status: pre-event scaffold (Phase 0).** Required doc (Oct 24 decision); expanded with
real numbers in Phase 7.

## What we do not claim

- That this works in prehospital trauma.
- That it detects hemorrhage specifically — the label is hypotension (low blood
  pressure), enriched for high-blood-loss/transfused cases, not a hemorrhage-specific
  signal.
- That it is clinically validated.
- That it is live. The replay demo plays a recorded excerpt, sped up, clearly
  labeled as such.

This is a research prototype for research and education only, not a medical device.

## Data limitations

- Surgical (intraoperative), not prehospital trauma. Anesthesia and surgical
  stimulation affect blood pressure in ways trauma does not.
- Single hospital (Seoul National University Hospital), single country, 2016–2017.
  No external validation yet.
- Continuous invasive arterial readings — not the intermittent cuff readings typical
  in ambulances. A prehospital version would need retraining and re-validation on
  that cadence.
- EBL and transfusion totals used for cohort selection only, with no timing — never
  model inputs.

## Model limitations

- **The central hypothesis is not supported by this run.** Phase 4 tried five
  feature/model combinations (original 29-feature logistic, that plus
  closeness-to-threshold features, that with boosting, a stacked
  MAP+drift-only model, and MAP alone) under 5-fold cross-validation. The
  winner, by a pre-registered margin, was a single-feature model: current
  MAP alone. A model built specifically to test whether HR/pulse-pressure/
  shock-index drift adds value beyond MAP scored *worse* than MAP alone.
  Neither the original nor the revised (v2) model clearly beats a simple
  tuned MAP threshold (B2) on the held-out test set. Full comparison:
  `MODEL_CARD.md`.
- **Confirmed under a second, cleaner label.** A "bleeding-flavored" label
  (event after incision, Cohort B only, excluding events near a vasopressor
  or anesthetic-depth change) was tried specifically to rule out label noise
  as the explanation. Drift lost there too, by a wider and statistically
  significant margin (-7.67pp vs. MAP alone, 95% CI entirely negative). This
  rules out "the plain MAP<65 label is just too noisy" as the reason drift
  doesn't show a benefit here.
- Vasopressor/anesthetic confounding is now partially addressed (see above)
  but not fully: bolus-only vasopressors (e.g. ephedrine push doses) aren't
  recorded as time-resolved infusion tracks in this dataset and couldn't be
  checked; only continuous-pump administrations are visible.
- Reported honestly and completely, per CLAUDE.md's rule against tuning on
  the test set: for the original MAP<65 task, the test set was touched
  exactly twice (once for the original model, once for the v2 revision
  chosen via cross-validation only), both results kept, not just the better
  one. The bleeding-flavored label is a separate task with its own single
  test touch, disclosed as a post-hoc experiment and never blended with the
  other two.

## Regulatory and deployment

- Software that informs clinical decisions may count as a medical device.
  Prospective validation and clinician oversight would be required before any
  real clinical use. See PLAN.md Section 15 for the full honest deployment
  discussion.
