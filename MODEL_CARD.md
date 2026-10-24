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

## What this is not

Not clinically validated. Not a device. A research prototype trained on surgical
(intraoperative) data — not prehospital trauma. On this test set, it does not
clearly outperform a simple MAP-threshold rule — see Evaluation above. See
[LIMITATIONS.md](LIMITATIONS.md).
