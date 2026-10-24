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

- TODO (Phase 4/7): fill in once real performance numbers exist. If the model does
  not beat the baselines at matched false-alarm rates, that result is reported
  plainly here, not hidden.
- Confounders not fully accounted for: anesthetic depth, vasopressor use, specific
  surgical events.

## Regulatory and deployment

- Software that informs clinical decisions may count as a medical device.
  Prospective validation and clinician oversight would be required before any
  real clinical use. See PLAN.md Section 15 for the full honest deployment
  discussion.
