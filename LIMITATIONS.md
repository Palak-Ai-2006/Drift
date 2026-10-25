# LIMITATIONS

Every number below is generated in [MODEL_CARD.md](MODEL_CARD.md) or [SYNTHETIC_PLAN.md](SYNTHETIC_PLAN.md); this file explains what the results can and can't support.

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
- **Confirmed a third way, with a different modeling approach.** A
  ridge-penalized offset/residual model (MAP's own prediction as a fixed
  baseline, extra features only allowed to adjust it under a tunable
  penalty) and MAP/shock-index interaction terms were both tried. Neither
  beat MAP alone; the residual model was decisively worse. This rules out
  "a flat, uniform penalty across 29 correlated features was unfairly
  burying the signal" as the explanation too.
- **Generalization checked on a genuinely clean holdout.** 175 cases never
  used in any prior split or round were downloaded and evaluated exactly
  once, with the existing model's exact fitted weights and threshold (no
  refitting). Performance held up (52.5% sensitivity at 0.77 FA/hour,
  vs. 57.4%/0.97 on the original, by-then-reused test set) — the original
  result was not an artifact of a lucky test split.
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

## Simulation limitations (Round 4)

- **Circular by design.** The simulator assumes bleeding causes textbook compensation (heart rate up, pulse pressure down, then collapse). A model that reads heart rate and pulse pressure will do well when that's true. The simulation shows the method works *if* real bleeding looks like this; it cannot show that it does. Studies of real trauma patients (Mutschler et al., *Critical Care* 2013; *Emergency Medicine Journal* 2014) found many don't follow the textbook classes, especially for heart rate.
- **A simple two-number rule nearly matches the model in simulation** (checked on validation data). That's expected for the same reason, and it means the simulation can't tell a clever model from a simple one.
- **It doesn't catch more collapses than a tuned MAP cutoff.** Both are near the ceiling. The model's gains are earlier warning and fewer false alarms.
- **Small source population.** The test baselines come from a few dozen real patients, so the confidence intervals are wide. For T2 and T4, the lower bound sits below the 95% target. Several misses trace back to a single baseline patient.
- **Baselines aren't flat.** "Stable" windows exclude drug changes and low pressure but not slow drift, and real baseline MAP wanders noticeably within a window. That's realistic, but it means only the injected part holds MAP steady during compensation.
- **Conservative scoring.** An alert more than 15 minutes before collapse counts as a false alarm, and lead time is capped at 15 minutes.
- **The simulated-bleed mode in the web demo uses the earlier Phase 5 curves and a transparent rule score,** not the Round 4 model. It's illustrative only. Its alert threshold assumes a textbook baseline (HR 72, pulse pressure 42) and is too strict for real anesthetized patients, whose pulse pressure is typically wider.

## Web demo limitations

- **Replays are recorded and sped up, and labeled so.** Nothing is live.
- **The examples are selected by written rules, not random.** The page says so.
- **The two "Miss" examples are weak demonstrations.** They come from one case where the model produced almost no risk scores before the event, so they mostly display "Not enough data to assess" rather than showing a confident-but-wrong model.
- **There is no live device input.** The page has a documented `DeviceSource` interface for a future bedside-monitor feed, but it is not implemented and throws if called.

## Regulatory and deployment

- Software that informs clinical decisions may count as a medical device.
  Prospective validation and clinician oversight would be required before any
  real clinical use. See PLAN.md Section 15 for the full honest deployment
  discussion.
