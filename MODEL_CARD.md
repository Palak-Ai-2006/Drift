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

**What was tried from the suggested checklist and deliberately NOT done, for
honesty's sake:** a second "bleeding-flavored" composite label (MAP<65 +
rising HR or high-EBL case) was not implemented — it would need its own
leakage review and was judged lower-value than the CV protocol itself, given
time spent. A dedicated model refit at H=5/H=10 (rather than reusing the
H=15-tuned alert stream) was not done either. Both are reasonable next steps,
not completed here.

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

## What this is not

Not clinically validated. Not a device. A research prototype trained on surgical
(intraoperative) data — not prehospital trauma. Neither the original nor v2
clearly outperforms a simple MAP-threshold rule — see Evaluation and Phase 4
revision above. See [LIMITATIONS.md](LIMITATIONS.md).
