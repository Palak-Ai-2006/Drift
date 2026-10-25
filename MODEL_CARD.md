# MODEL_CARD

**Status: Phase 4 original complete (2026-10-24), tagged `phase4-original`.**
Generated from `artifacts/metrics.json` (`scripts/04_train_eval.py`). Numbers
below are real, not placeholders.

**Test-evaluation protocol:** the test set was evaluated once, here, on this
original model. Any revision (v2) is selected using only validation /
cross-validation on train+val; the test set is then evaluated exactly one
more time for the chosen v2, and that result is reported **next to** this one
below, never replacing it (see "Phase 4 revision (v2)" below, added only
after this original section was committed and tagged).

## Model

- **Shipped model: logistic regression.** The boosted model
  (`HistGradientBoostingClassifier`) did NOT clear either selection bar on
  validation (Oct 24 decision, `config.MODEL_SELECT_*`): sensitivity gain was
  **-0.86pp** (boosted was slightly *worse*, need ≥+5pp) and the bootstrap-by-case
  95% CI of the AUPRC difference was **[-0.096, +0.085]** (includes zero). Both
  bars must pass to ship boosted; neither did.
- **Features:** strictly causal — current HR/SBP/DBP/MAP/PP/PP-over-SBP/shock
  index; 5/10/15-min slopes of HR/MAP/PP/shock index; 15-min MAP std/min;
  15-min missing fraction; drift-from-baseline for HR/MAP/PP/shock index;
  age/sex/ASA/emergency context. Never end-of-case totals. See `src/drift/features.py`.
- **Calibration:** isotonic, fit on validation only (`sklearn.frozen.FrozenEstimator`
  + `CalibratedClassifierCV`). Test Brier score (H=15): **0.1037**. Reliability
  plot: `artifacts/phase4_reliability_plot.png` — well calibrated through ~0.3
  predicted probability (bins of 1,400-6,600 test rows), but the top of the
  range (predicted >0.5) has only 3-95 test rows per bin, too few to assess
  calibration reliably there — reported, not hidden.
- **Operating points** (threshold chosen on validation; actual test-set FA rate
  differs, expected from val/test variation, not tuning):

  | Target FA/hr | Threshold | Val FA/hr |
  |---|---|---|
  | 0.5 | 0.3144 | 0.290 |
  | 1.0 (primary) | 0.2946 | 0.880 |
  | 2.0 | 0.1791 | 1.414 |

## Evaluation (test set, touched once; 87 cases, 263/88/87 train/val/test split by subject)

**Headline comparison at the primary operating point (1 FA/patient-hour target, H=15min), with bootstrap 95% CIs by case:**

| Method | Sensitivity (Cohort A) | Lead time (median) | FA/hr (Cohort A) |
|---|---|---|---|
| B1 (standard alarm, MAP<65/60s) | 100% (by construction, lead=0) | 0 min | 0 |
| **Drift (logistic)** | **46.4% [38.3%, 54.6%]** | **5.6 min** | **1.17 [0.93, 1.43]** |
| B2 (tuned early-MAP threshold) | 60.1% | 4.4 min | 1.15 |
| B3 (tuned shock-index threshold) | 33.0% | 5.8 min | 1.31 |
| B4 (tuned MAP-slope rule) | 22.7% | 7.0 min | 1.08 |

**WE DO NOT CLAIM a win here.** At every false-alarm budget tested (0.5/1.0/2.0
per patient-hour), the simple tuned early-MAP-threshold baseline (B2) matched
or beat the logistic model's sensitivity (e.g. at 0.5 FA/hr: B2 52.6% vs. model
18.6%). Full table across all methods/targets/cohorts/horizons is in
`artifacts/metrics.json`. This is reported plainly per CLAUDE.md Section 12
("report unfavorable results plainly; no tuning on the test set") — no
retuning was done after seeing this.
- Secondary (test, H=15): AUROC **0.736**, AUPRC **0.260** (base rate ~10.8%),
  Brier **0.104**, n=11,570 labeled rows.
- Logistic coefficients (standardized scale) are saved in `metrics.json` under
  `logistic_coefficients_for_why_panel` for the web demo's "why" panel. Top by
  magnitude: `pp_over_sbp` (+1.00), `shock_index` (+0.77), `map_min` (-0.54),
  `hr` (-0.44), `pp` (-0.41), `map` (-0.37). Caveat: several features are
  correlated (map, map_min, map_drift; hr and shock_index), so individual
  coefficient signs should be read cautiously — `hr`'s negative sign, for
  example, is likely a partialling-out artifact against shock_index, not a
  claim that higher heart rate lowers risk.

## Leakage checklist (PLAN.md Section 8)

- [x] Split by case (and subject), never by row.
- [x] No end-of-case totals used as features — confirmed, none referenced in `features.py`.
- [x] Baseline/drift features use only data before the prediction time — enforced by construction, verified by `tests/test_features.py`'s causality tests.
- [x] Scaling, calibration, threshold chosen on train/validation only — `Pipeline` fit on train, calibrator and operating points fit on validation, test touched only for final metrics.
- [x] Test set evaluated once; no tuning afterward.
- [x] Causality unit tests pass (`tests/test_features.py`, 12 tests).
- [x] Event counts / positive rate printed for train/val/test — 1,398 real events across 438 cases; positive rates by horizon/cohort in `DATA_CARD.md`.
- [x] Bootstrap CIs by case — headline sensitivity/FA-rate and the model-selection AUPRC diff both bootstrapped (1,000 resamples, by case).
- [x] Confounders (anesthetic depth, vasopressors, surgical events) acknowledged — not modeled; no vasopressor track in the dataset's numeric tracks, so that stretch feature was skipped.

## Phase 4 revision (v2) — 2026-10-24

Done in response to the original's honest-but-weak result above, following a
pre-registered protocol (locked in this file, committed and tagged
`phase4-original`, *before* any of this section was written): candidate
models/features were selected using **5-fold grouped (by subject)
cross-validation on the 351 train+val cases only** — the single 88-case
validation split the original used is too noisy to pick a winner from
reliably. The test set was touched exactly one more time, for the winning
candidate only. Full CV numbers: `artifacts/phase4_cv_model_selection.json`;
full v2 test numbers: `artifacts/metrics_v2.json`.

**Candidates tried in CV** (all logistic unless noted; CV sensitivity @ 1
FA/patient-hour, decision rule = beat `original_repro`'s CV sensitivity
(50.6%) by ≥3pp with the bootstrap-by-case 95% CI of the difference excluding
zero):

| Candidate | What it adds | CV sensitivity | CV AUPRC | Gain vs. original | Adopt? |
|---|---|---|---|---|---|
| `original_repro` | (original's 29 features + sex, reproduced in CV) | 50.6% | 0.305 | — | baseline |
| `threshold_features` | + MAP−65, projected min-to-cross-65, 5-min MAP min, time-since-anesthesia/opstart | 52.2% | 0.322 | +1.6pp, CI [-0.2, +3.7] | No |
| `threshold_features_boosted` | same features, HistGradientBoosting | 52.3% | 0.306 | +1.7pp, CI [-1.0, +4.7] | No |
| `stacked_b2_drift` | MAP + HR/MAP/PP/shock-index slopes + drift only (tests whether drift adds to MAP alone) | 46.1% | 0.259 | **-4.5pp**, CI [-8.4, -1.0] | No (worse) |
| **`b2_alone`** | **MAP only, single feature** | **56.9%** | 0.294 | **+6.3pp, CI [+3.0, +9.6]** | **Yes** |

**v2 = `b2_alone`: a single-feature (current MAP) logistic model, calibrated
the same way as the original.** This is the only candidate that cleared the
pre-registered bar.

**The honest reading of this result, stated plainly:** this is not a case
where smarter features found a signal the raw threshold missed. It is the
opposite — the stacked model built specifically to test "does drift add
value beyond MAP" scored *worse* than MAP alone (-4.5pp), and every
multi-feature variant (including the new closeness-to-threshold features)
underperformed the single-feature model at this operating point. Note also
that `b2_alone` has the *lowest* AUROC/AUPRC of the logistic candidates
(0.742/0.294 vs. the original's 0.785/0.305) — it is not a better classifier
overall, its ROC/PR curve simply crosses the others' favorably right at the
~1-FA/hour operating region this project targets. **Across every feature set
and model tried (original, closeness-to-threshold, stacked drift-only,
boosted), none added measurable predictive value beyond current MAP itself,
within this feature-engineering approach, on this dataset, at this horizon.**
That is a real, if deflating, finding about this project's central hypothesis
(that drift dynamics predict hypotension earlier than a threshold) — not yet
supported by the data as currently featurized.

**v2 test-set result (touched once), vs. the original, side by side:**

| | Original (29 features, logistic) | v2 (`b2_alone`, 1 feature) |
|---|---|---|
| Threshold (from validation) | 0.2946 | 0.3539 |
| Val FA/hr | 0.880 | 0.732 |
| **Test sensitivity, Cohort A** | 46.4% [38.3%, 54.6%] | **57.4%** |
| Test sensitivity, Cohort B | 44.7% | 54.0% |
| Test lead time (median) | 5.6 min | 4.4 min |
| Test FA/hr, Cohort A | 1.17 [0.93, 1.43] | 0.97 |
| Test FA/hr, Cohort B | 1.38 | 1.00 |
| Test AUROC / AUPRC / Brier | 0.736 / 0.260 / 0.1037 | 0.705 / 0.288 / 0.1035 |

v2 does meaningfully better on the test set too (57.4% vs. 46.4% sensitivity,
at a *lower* false-alarm rate), confirming the CV result wasn't a fluke of
the fold split. **v2 still does not clearly beat B2 from the original
comparison table (60.1% sensitivity)** — it is close (57.4% vs 60.1%), in the
same range, and the honest conclusion stands: nothing tried here demonstrates
that the "drift" features add value over a well-calibrated MAP threshold.

**Horizon sweep (v2, same fixed alert stream, no retuning per horizon):**

| H (min) | Sensitivity | Lead time (median) |
|---|---|---|
| 5 | 30.2% | 1.8 min |
| 10 | 45.4% | 2.9 min |
| 15 (primary) | 57.4% | 4.4 min |
| 30 | 73.5% | 16.0 min |

**Subgroup slices (test set, v2, split at the test set's own median — not a
guessed clinical cutoff):**
- **Decline steepness** (MAP slope in the 15 min before event onset): events
  in the steeper/more-abrupt half were detected **66.2%** of the time vs.
  **49.0%** for the shallower/more-gradual half. This is the opposite of
  what "drift helps most with slow bleeds" would predict — plausible reading:
  a raw-MAP model catches abrupt, deep drops more reliably because they cross
  the threshold with more margin, while gradual declines hover closer to the
  boundary and are more often missed by a few points.
- **Timing in the operation** (event position within its case's op window):
  early-half events detected 55.2% of the time vs. 60.0% for late-half —
  only a modest difference, no strong story either way.
- **B1 comparison still holds**: v2's median lead time (4.4 min) is still
  strictly positive and well ahead of B1's zero-by-construction lead — "earlier
  than the standard alarm" is true for both the original and v2, even though
  "beats a tuned threshold" is not.

**What remains deliberately NOT done, for honesty's sake:** a dedicated model
refit at H=5/H=10 (rather than reusing the H=15-tuned alert stream) was not
done. The bleeding-flavored label suggested here *was* subsequently built and
tested — see "Experiment 2" below.

## Experiment 1: event-aligned traces (2026-10-24, descriptive, train+val only)

For every real event in the 351 train+val cases, HR/MAP/PP/shock-index were
extracted at 1-minute marks for the 30 minutes before onset (1,107 events
with a usable trace), and plotted as median + bootstrap-by-case band, split
two ways. No model, no tuning, no test-set touch — purely descriptive.
`artifacts/phase4_event_aligned_traces_cohort.png`,
`..._decline.png`.

- **Cohort B vs. not:** Cohort B cases run a **persistently elevated** HR
  (~86 vs ~70 bpm) and shock index (~0.83 vs ~0.65) across the *entire*
  30-minute window — not a late-breaking rise right before the event. This
  looks like a chronic compensating state specific to these patients, not an
  acute dynamic signal in the minutes before collapse.
- **Abrupt vs. gradual decline** (split at the dev event set's own median MAP
  slope at onset, -0.237 mmHg/min — not a guessed clinical cutoff): gradual
  events show the same persistently-elevated-shock-index pattern throughout;
  abrupt events look comparatively unremarkable (lower, flatter shock index)
  until a late, sharp MAP crash in the final ~10-15 minutes.
- **Why this matters for the CV result above:** a slope/drift feature is
  built to catch a *late, dynamic* change. If the real signal (where present)
  is an *already-elevated, flat* baseline rather than a last-minute rise,
  slope features have little to find — current-value features (shock index,
  MAP) would see it instead, and they're already in the original/stacked
  models. This is a plausible, not proven, explanation for why nothing beat
  MAP alone in CV.

## Experiment 2: bleeding-flavored label (2026-10-24, post-hoc, test touched once for this new task)

Rules locked in `ACTIONS.md` *before* this was run (full definition there).
Summary: a real primary event qualifies as "bleeding-flavored" only if it
occurs after incision, in a Cohort B case, with no vasopressor-infusion-rate
or volatile-anesthetic increase in the preceding 5 minutes (drug track names
read from `track_names.csv`, not guessed; bolus-only pressors like ephedrine
aren't time-resolved in these tracks and can't be checked — documented
limitation). The label never references HR/PP/shock index, so those features
can't trivially predict it. A disqualified event in a window's horizon makes
that window's label unknown (excluded), not negative.

Of 1,107 real dev-set events, **665 qualified, 442 were disqualified**
(mostly: not Cohort B, or a vasopressor/anesthetic change nearby) — positive
rate on this label is 5.9% (vs. 10.8% for the plain MAP<65 label).

**CV result (5-fold, train+val, same protocol as the v2 screening):**

| Candidate | CV sensitivity @ 1 FA/hr | CV AUPRC |
|---|---|---|
| `original_repro` | 46.3% | 0.256 |
| **`b2_alone`** | **49.3%** | 0.204 |
| `stacked_b2_drift` | 41.7% | 0.200 |

**stacked_b2_drift vs. b2_alone: -7.67pp, 95% CI [-12.84, -2.56]pp — drift is
not just "doesn't help," it is *significantly worse*, with the CI entirely on
the negative side.** Per the pre-registered rule, this is a clear loss, not a
marginal miss: **we stop here, no further feature engineering**, and report
it plainly. `b2_alone` is the winner by default.

**Test set, touched once for this new task, disclosed as a post-hoc
experiment (kept separate from `metrics.json`/`metrics_v2.json`):**
sensitivity **53.8%** (70/130 qualifying events — a noticeably smaller test
sample than the original's 291, so this number carries more uncertainty than
it looks), median lead time **5.0 min**, FA/hr **1.33**, AUROC/AUPRC/Brier
**0.678 / 0.132 / 0.055**. Full numbers: `artifacts/metrics_exp2_bleeding_label.json`.

**Overall reading across both experiments and both labels:** drift/slope
features have now been tested against the plain MAP<65 label (v2 screening)
and this cleaner, more hemorrhage-specific label (Experiment 2), under two
independently-built CV protocols. In both, a model restricted to current MAP
alone beat every richer alternative tried, and the stacked drift-only model
was consistently the weakest performer. This project's central hypothesis —
that HR/pulse-pressure/shock-index dynamics predict hypotension earlier than
a MAP threshold — is not supported by this dataset, this feature
engineering, at this horizon. That is reported here as the honest result,
not reframed as a near-win.

## Phase 4 iteration, round 3 (2026-10-24, tagged `round3-start`/`round3-end`)

Rules locked in `ACTIONS.md` before any code (see there for the full plan):
3-fold grouped CV on train+val for two targeted primary-task candidates
against `b2_alone`, a separate secondary compensation-flag task, and a
fresh never-touched holdout to replace the now three-times-looked-at test
set. Time-boxed to ~3 hours.

### Primary task: residual/offset model + interaction terms

| Candidate | What it is | CV sensitivity @ 1 FA/hr | Gain vs. b2_alone | Adopt? |
|---|---|---|---|---|
| `b2_alone` | MAP only (reference) | 56.5% | — | baseline |
| `residual_ridge` | MAP-only logit as a fixed offset + ridge-penalized logistic on HR/shock-index/PP/all-slopes/all-drift, penalty chosen by inner CV | 47.9% | **-8.58pp, 95% CI [-12.23, -5.02]pp** | No — decisively worse |
| `interaction_features` | MAP + `(65-MAP)×shock_index` + `(65-MAP)×HR-drift` | 55.0% | -1.45pp, 95% CI [-3.55, +0.30] | No — CI includes zero |

**Neither candidate cleared the pre-registered bar (≥3pp, CI excludes
zero). Stopped here, per the rule, with no further feature engineering.**
`residual_ridge`'s own toy tests (`tests/test_models.py`) confirm the
implementation is correct — it recovers real injected signal and shrinks
pure noise toward zero on synthetic data — so this is a real result about
this dataset, not an implementation bug: even letting the extra features
compete against MAP with a tunable penalty (rather than a flat, uniform
one as in the original 29-feature model), they still don't help.
`interaction_features` came closest of anything tried in this whole
iteration (-1.45pp, nearly flat) but still didn't win.

### Secondary task: sustained elevated shock index (compensation-state flag — NOT a hemorrhage detector)

Label: the first time a trailing 5-minute rolling median of shock index
(HR/SBP) reaches ≥0.9 within the operation window (492 episodes across
351 dev cases, positive rate 7.5% of windows). Predicted from age, height,
weight, sex, MAP, and pulse pressure **only** — no HR, SBP, or
shock-index-derived feature, so the label can't be predicted from a
disguised copy of itself.

**CV ROC AUC: 0.650 (95% CI [0.595, 0.702]).** A real, if modest, signal:
MAP/pulse-pressure dynamics and patient demographics predict an *upcoming
compensatory state* better than chance, even with HR/shock-index itself
excluded from the inputs. This is reported as a compensation-state flag — a
possible second row for the demo — never as evidence of bleeding or as
validation of the hemorrhage-detection hypothesis above.

### Clean holdout: 175 never-before-downloaded cases

The original 87-case test set had been looked at three times by this point
(original, v2, Experiment 2) and could no longer support a trustworthy
"how well does this generalize" claim. 175 cases were sampled from the
2,914 clinical-table-eligible cases never touched by any prior round or
test/val/train split (5-case timing test first: 0.67s/case, well under the
15s/case stop threshold), bulk-downloaded (175/175 succeeded), and run
through the full eligibility/Cohort-B/windows pipeline (156/175 eligible;
Cohort B fell to the top-quartile fallback rule here — expected at this
smaller scale, not a bug, since the fixed fallback-trigger thresholds in
`config.py` apply the same way regardless of sample size).

The standing model (`b2_alone`, undefeated through v2, Experiment 2, and
this round's primary task) — using its **already-fitted weights and
already-chosen threshold from v2, with no refitting or re-tuning on this
holdout** — was evaluated on it exactly once:

| | Original v2 test (87 cases, looked at 3x) | Fresh holdout (175 cases, looked at once) |
|---|---|---|
| Sensitivity, Cohort A | 57.4% | **52.5%** (187/356 events) |
| Sensitivity, Cohort B | 54.0% | **48.2%** (79/164 events) |
| FA/hr, Cohort A | 0.97 | **0.77** |
| AUROC / AUPRC | 0.705 / 0.288 | 0.733 / 0.219 |

Performance holds up on genuinely unseen data — sensitivity is a few points
lower but the false-alarm rate is also lower (0.77 vs. target 1.0/hr, vs.
0.97 on the old test set), so the two move together rather than one
masking a collapse in the other. This is the most trustworthy number in the
whole project so far, precisely because nothing was tuned against it.

## Leakage checklist (PLAN.md Section 8, original model — v2 follows the identical pipeline)

- [x] Split by case (and subject), never by row.
- [x] No end-of-case totals used as features — confirmed, none referenced in `features.py`.
- [x] Baseline/drift features use only data before the prediction time — enforced by construction, verified by `tests/test_features.py`'s causality tests.
- [x] Scaling, calibration, threshold chosen on train/validation only — `Pipeline` fit on train, calibrator and operating points fit on validation, test touched only for final metrics.
- [x] Test set evaluated once for the original; evaluated exactly once more for v2, per the pre-registered protocol above — no tuning after either look.
- [x] Causality unit tests pass (`tests/test_features.py`, 15 tests, including the new v2 features).
- [x] Event counts / positive rate printed for train/val/test — 1,398 real events across 438 cases; positive rates by horizon/cohort in `DATA_CARD.md`.
- [x] Bootstrap CIs by case — headline sensitivity/FA-rate, the original's model-selection AUPRC diff, and v2's CV decision-rule diff all bootstrapped (1,000 resamples, by case).
- [x] Confounders (anesthetic depth, vasopressors, surgical events) acknowledged — not modeled; no vasopressor track in the dataset's numeric tracks, so that stretch feature was skipped.

<!-- ROUND4_RESULTS:START -->
## Round 4: semi-synthetic results (SIMULATION, generated by `scripts/10_round4_report.py`)

**Every number in this section is from a simulation.** Real, stable VitalDB baselines have simulated bleeds injected on top. The simulation assumes that compensation (heart rate up, pulse pressure down) comes before collapse, so these results show the method works *when that is true*. They cannot show that it *is* true in real patients. Design: [SYNTHETIC_PLAN.md](SYNTHETIC_PLAN.md) §3–5a. Generator frozen by fingerprint (`artifacts/round4_generator_freeze.json`) before training. The test set was evaluated once.

**Model:** logistic regression on the Phase 3 causal features, trained on synth-train across all tiers and chosen on synth-val (tied on sensitivity and lead -> simpler model). It was calibrated (isotonic) on synth-val, and one 1 FA/hr threshold from synth-val is used for every tier. **B2** at the same target alarms when MAP < 77.8 mmHg. **Standard monitor** = MAP < 65 OR HR > 120 OR SBP < 90 (typical settings, not a verified default). **B1** = MAP < 65 itself (zero lead).

**Pre-registered target (≥ 95% sensitivity at ≤ 1 FA/hr on T1 and T2):**
- **T1:** sensitivity 97.6% [94.3–100.0], 0.65 false alarms/hr → target **met** (point estimate)
- **T2:** sensitivity 95.5% [90.2–100.0], 0.66 false alarms/hr → target **met** (point estimate)

### Synth-test, per tier, at the 1 FA/hr operating point
| Tier | Collapses | Drift model sensitivity [95% CI] | Model FA/hr [95% CI] | Model lead, median (IQR) min | B2 (MAP cutoff) sens / FA/hr / lead | Standard monitor FA/hr / lead | Model − standard monitor lead (median, min) |
|---|---|---|---|---|---|---|---|
| T1 textbook | 85 | 97.6% [94.3–100.0] | 0.65 [0.57–0.74] | 6.7 (3.9–10.9) | 100.0% / 0.80 / 3.4 | 0.35 / 5.3 | 2.0 |
| T2 realistic | 67 | 95.5% [90.2–100.0] | 0.66 [0.47–0.84] | 8.3 (4.4–12.6) | 98.5% / 1.12 / 3.3 | 0.21 / 7.1 | 2.5 |
| T3 blunted | 36 | 94.4% [84.8–100.0] | 0.48 [0.28–0.68] | 7.2 (5.0–10.1) | 94.4% / 1.18 / 4.0 | 0.12 / 1.0 | 6.0 |
| T4 confounded | 69 | 95.7% [89.6–100.0] | 0.74 [0.56–0.93] | 9.2 (5.4–12.2) | 97.1% / 1.11 / 3.6 | 0.33 / 5.9 | 2.0 |
| All tiers | 257 | 96.1% [93.0–98.9] | 0.63 [0.50–0.76] | 7.9 (4.8–11.7) | 98.1% / 1.04 / 3.4 | 0.26 / 5.0 | 2.0 |

Lead time is capped at 15 min by the horizon. False alarm means no MAP < 65 event within 15 min; this is conservative, because a correct alert 20 min before collapse counts as false. Under the secondary "bleed-aware" count (alerts after bleed onset are not false), all-tier FA/hr is: model 0.19, B2 0.93, standard monitor 0.06.

At 0.5 FA/hr (val threshold) the model's test sensitivity over all tiers is 95.3% vs B2 95.3%. At 2 FA/hr it's 96.1% vs B2 98.4%.

### Shifted test (slower bleeds, lower HR gain, later onset than training)
| Tier | Collapses | Drift model sensitivity [95% CI] | Model FA/hr [95% CI] | Model lead, median (IQR) min | B2 (MAP cutoff) sens / FA/hr / lead | Standard monitor FA/hr / lead | Model − standard monitor lead (median, min) |
|---|---|---|---|---|---|---|---|
| T1 textbook | 59 | 100.0% [100.0–100.0] | 0.51 [0.38–0.61] | 7.0 (3.3–11.4) | 100.0% / 0.85 / 4.0 | 0.17 / 3.1 | 3.0 |
| T2 realistic | 53 | 92.5% [82.7–100.0] | 0.61 [0.43–0.80] | 9.8 (5.7–13.0) | 100.0% / 1.07 / 3.5 | 0.22 / 1.9 | 6.3 |
| T3 blunted | 13 | 100.0% [100.0–100.0] | 0.35 [0.15–0.57] | 7.7 (4.0–10.9) | 100.0% / 1.19 / 3.9 | 0.09 / 0.0 | 5.9 |
| T4 confounded | 50 | 92.0% [84.9–98.1] | 0.68 [0.45–0.91] | 7.8 (3.7–12.4) | 96.0% / 1.40 / 3.7 | 0.23 / 3.0 | 5.0 |
| All tiers | 175 | 95.4% [91.6–98.7] | 0.54 [0.40–0.69] | 7.7 (3.9–11.8) | 98.9% / 1.11 / 3.8 | 0.18 / 2.2 | 5.0 |

### Misses, other classes, calibration
- **Misses (synth-test, model at 1 FA/hr): 10.** By cause: other 5, artifact 2, blunted 2, fast 1. B2 caught 8 of them. 3 come from a single real baseline patient (VitalDB case 4475). Full list: `artifacts/round4_test_misses.csv`.
- **`bleed_no_collapse` (descriptive, not scored), 159 streams:** median calibrated risk by blood lost: before onset 0.01, 0-10% lost 0.02, 10-20% lost 0.19, >20% lost 0.42. Alerted after bleed onset: 89.9%; before onset (a false alert): 1.9%.
- **Non-bleed hypotension (T4 no-bleed streams whose MAP fell below 65):** 3 of 20 warned early. This is expected: by design there is no heart-rate or pulse-pressure precursor.
- **Calibration (Brier, synth-test):** T1 0.041, T2 0.049, T3 0.037, T4 0.092, ALL 0.054. Reliability plot: `artifacts/round4_reliability_plot.png`.

### What this does and doesn't show
- **Does:** when bleeding produces textbook compensation, a simple calibrated model on heart-rate, pulse-pressure and MAP trends warns about twice as early as a MAP cutoff (7.9 vs 3.4 min median) with fewer false alarms (0.63 vs 1.04/hr). It warns a median 2.0 min earlier than a standard HR/SBP/MAP monitor, which raises fewer false alarms (0.26/hr).
- **Doesn't:** it doesn't catch *more* collapses than a well-tuned MAP cutoff (both are near the ceiling), and it says nothing about real patients. On real surgical data (Rounds 1–3) MAP alone matched these features, consistent with the published debate over whether the Hypotension Prediction Index adds anything beyond MAP. The simulation can't settle which world real trauma patients live in; that needs data with real bleed labels.
<!-- ROUND4_RESULTS:END -->

## Alert naming (2026-10-25)

In the web demo, both tabs now call their alert a **"Drift alert"**: a product name chosen for consistency, by the user's decision during the UI polish pass. It replaces the earlier label "Early MAP-based alert". **The model behind the real-data alert is unchanged:** it is still the MAP-only, calibrated logistic model (`b2_alone`), and heart-rate, pulse-pressure and shock-index trends are still not shown to add value on real data. To keep that visible, the alert's detail text ("Mean arterial pressure trending low"), the header tagline ("MAP-based early warning"), the Proof drawer's honesty note and its table label ("shipped model, MAP only") all still say it is MAP-based. In the Simulated tab, the "Drift alert" is the transparent heart-rate / pulse-pressure rule score.

## What this is not

Not clinically validated. Not a device. A research prototype trained on surgical
(intraoperative) data — not prehospital trauma. Neither the original nor v2
clearly outperforms a simple MAP-threshold rule — see Evaluation and Phase 4
revision above. See [LIMITATIONS.md](LIMITATIONS.md).
