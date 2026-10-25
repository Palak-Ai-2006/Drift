# Round 4 — Semi-synthetic proof of concept

Status: PLAN. Lock this file (commit + tag `round4-plan`) before writing any generator or model code.

---

## 1. What this round claims, and what it doesn't

**Claim (if the numbers support it):**
"In a physiology-grounded simulation where bleeding is the known cause of collapse, Drift detects X% of simulated bleeds a median of Y minutes before a standard threshold alarm, at Z false alarms per patient-hour."

**Does not claim:** performance on real patients. The simulation assumes compensation comes before collapse, as textbook physiology says. It shows the detection method works *when that is true*. It cannot show that it is true in real patients.

Every number from this round is reported with the words "in simulation."

---

## 2. Why we use semi-synthetic data (the logic explanation)

1. **The real label is mixed.** In VitalDB, "MAP < 65" is caused by many things: anesthetic induction, anesthetic depth, vasodilating drugs, surgical stimulation, positioning, and sometimes bleeding. Vital signs alone can't tell us which events are bleeds, and there are no ground-truth bleed timestamps.
2. **That mix hides the signal we care about.** Rounds 2 and 3 showed MAP alone matches or beats the drift features on this label. That fits the idea that non-bleeding causes dominate the events, though it doesn't prove it.
3. **We can't subtract anesthesia out of a recording.** Its effect on HR and BP varies by drug, dose and patient, and isn't additive. Any "cleaning" would just be guessing.
4. **So we build a controlled setting where we know the cause.** We take real, stable stretches of VitalDB data and inject a simulated bleed on top. The patient's baseline, variability and sensor noise stay real. The bleed and its start time are known exactly.
5. **This is standard practice.** Signal injection and simulation studies are common for proof-of-concept work when ground-truth labels are missing.

---

## 3. Generator design

### 3.1 Baseline segments (real)
- Source: VitalDB **train + val cases only**. Never the Round 1–3 test cases, never the fresh 175-case holdout.
- "Stable" window rules (all must hold):
  - no MAP < 65 within the window or within ±10 min
  - no vasopressor or anesthetic infusion-rate change within ±10 min (reuse the Experiment 2 drug-track logic)
  - after incision, at least 15 min before case end
  - missing-data fraction under the existing artifact threshold
- Window length: 40–60 min (enough for a baseline period + bleed + decompensation).
- Keep the residual (signal minus a rolling median) so the real noise can be layered on top of the injected trend.

### 3.2 Bleed injection model
Per injected case, sample:
- `t0`: bleed onset, at least 10 min into the window (so the baseline is established)
- `rate`: blood loss in % of blood volume per minute (slow / moderate / fast bands)
- `g_hr`: heart-rate gain (how strongly HR responds); low values = blunted response
- `f_c`: the blood-loss fraction where compensation fails (around 30%, sampled per case)

Blood-loss fraction `f(t)` rises from `t0` at `rate`. Responses, smoothed with logistic transitions:

| Signal | Before `f_c` (compensated) | After `f_c` (decompensated) |
|---|---|---|
| HR | rises with `f`, scaled by `g_hr` | keeps rising, then may plateau |
| Pulse pressure | narrows as `f` rises (DBP up slightly from vasoconstriction, SBP down slightly) | narrows further |
| MAP | held near baseline (small drift only) | falls steeply |

The shape follows the ATLS classes of hemorrhage: under 15% loss, few changes; 15–30%, HR up and pulse pressure down with normal BP; 30–40%, BP falls; over 40%, BP falls sharply. Older ATLS editions gave HR cutoffs of about 100 / 120 / 140 bpm; the 10th edition (2018) uses arrows instead.

Known limit: Mutschler et al. (Injury, 2014) found real trauma patients often don't follow this table, especially for heart rate. That is the reason for Tier 3.

All ranges live in `config.py` under a `SYNTH` block. No magic numbers in generator code.

### 3.3 Negatives and confounders (these keep it from being trivial)
- **Clean negatives:** stable segments with nothing injected.
- **Non-bleed hypotension:** MAP drops with no preceding HR rise or pulse-pressure narrowing (an anesthetic-like drop). Both systems are scored on these. Drift is not expected to warn early, and we say so.
- **Stimulation spikes:** transient HR rise of +15 to +35 bpm for 2–6 min, with MAP steady or rising, and no bleed. This generates false alarms.
- **Artifacts:** flatline, dropout, and arterial-line flush spikes. These test the "insufficient data" state.

### 3.4 Difficulty tiers
| Tier | Name | What's in it |
|---|---|---|
| T1 | Textbook | strong HR gain, moderate rate, light noise, no confounders |
| T2 | Realistic | full real-baseline noise, slow to fast rates, artifacts |
| T3 | Blunted | `g_hr` reduced 50–90%, more slow bleeds |
| T4 | Confounded | T2 plus stimulation spikes and non-bleed hypotension |

"Harder and harder": training may use a curriculum (T1 to T4). Evaluation is always reported per tier, never only the best tier.

**Amendment (before `round4-generator-frozen`):** For T1/T2/T4 moderate and fast bleeds, `t0` and rate are sampled jointly so the expected collapse fits in the window, and the window is trimmed to fit the bleed while staying within 40–60 min. Any injected bleed that does not reach MAP < 65 in its window is labeled **`bleed_no_collapse`**: this class is reported descriptively (how the risk score behaved as compensation progressed) and is never counted as a positive or a negative in sensitivity, false-alarm-rate or lead-time metrics.

---

## 4. Splits and integrity rules
1. Baseline segments are split **by VitalDB case** into synth-train / synth-val / synth-test. A patient's real baseline never appears in two splits.
2. **Generator frozen first.** Ranges, tier definitions and seeds are committed and tagged `round4-generator-frozen` before any model is trained. After that the generator is not changed. If it has to change, the reason is written in this file and both results are reported.
3. **Separate test seed**, plus a **shifted test set**: some parameters partly outside the training ranges (slower bleeds, lower `g_hr`, longer `t0`). This checks that the model learned physiology, not the generator's quirks.
4. **Features:** the same causal feature code from Phase 3. No generator internals (`f`, `t0`, `rate`, `g_hr`, tier) are ever used as features.
5. The threshold is set on synth-val at 1 false alarm per patient-hour. synth-test is evaluated **once** per tier.
6. **Baselines on the same streams:**
   - B1: MAP < 65 alarm
   - B2: tuned MAP threshold
   - Standard monitor: an OR of typical bedside alarm limits (MAP < 65, SBP < 90, HR > 120). These are typical defaults; confirm and cite before quoting them.
7. The causality test must still pass on synthetic streams.

---

## 5. Metrics (why not "accuracy")
More than 90% of time windows contain no bleed, so a model that never alerts would score around 95% "accuracy." Report instead, **per tier**:
- sensitivity at 0.5 / 1 / 2 false alarms per patient-hour (Drift vs B1, B2, standard monitor)
- median lead time vs B1 and vs the standard monitor
- calibration (Brier score, reliability plot)
- every miss listed with its cause (blunted, fast bleed, artifact, confounder)

**Target, set before running:** ≥ 95% sensitivity at ≤ 1 FA/hr on T1–T2. T3 and T4 are reported whatever they show. If the target isn't met, report that; don't adjust the generator to reach it.

Outputs go to `artifacts/metrics_synth.json`. Web data is generated from that file, never typed by hand.

### 5a. Evaluation details fixed before training (2026-10-24, before any Round 4 model existed)
Constants live in `config.py` (`SYNTH_EVAL_*`, `SYNTH_FEATURE_COLUMNS`, `SYNTH_MODEL_*`, `SYNTH_STANDARD_MONITOR_*`).
1. **Data:** one longest stable window per baseline case in each split. For each window and tier there are 4 replicates, each one bleed stream and one no-bleed stream, using separate seeds for train, val, test and shifted test.
2. **Features:** the Phase 3 causal features computed from the stream only. Demographics and time-since-start features are left out because they don't exist or mean nothing in a synthetic window. No generator internals are used.
3. **Labels and alarms:** exactly as for real data: an event (MAP < 65 for ≥ 60 s) within 15 min, a 15-min refractory period, and the same suppression rules. `bleed_no_collapse` streams are left out of training, threshold setting and scoring.
4. **Model choice (synth-val only):** logistic regression and gradient boosting are trained on pooled synth-train across all tiers. The winner has the higher pooled val sensitivity at 1 FA/hr on collapsing bleeds. If they're within 2 points, the longer median lead time wins; if that's within 0.5 min too, logistic wins. The winner is then calibrated (isotonic) on synth-val.
5. **Thresholds:** for the model and B2 (a MAP cutoff), set on pooled synth-val at 0.5 / 1 / 2 FA/hr. A deployed alarm doesn't know the tier, so there's one threshold for all tiers. B1 is the MAP < 65 event itself, with zero lead. The "standard monitor" is B1 OR HR > 120 OR SBP < 90, fixed and untuned; these are typical settings, not a verified factory default.
6. **False alarm:** an alert counts as false if no event follows within 15 min, the same rule as real data. This is conservative because a correct alert more than 15 min before collapse counts as false. As a secondary measure only, used for no decision, a "bleed-aware" rate also counts as correct any alert at or after bleed onset in a collapsing-bleed stream.
7. **Test:** synth-test and shifted test are each evaluated in one run, per tier, with 95% bootstrap CIs resampled by source VitalDB case.
8. **Target check:** for T1 and T2 separately, sensitivity ≥ 0.95 and FA ≤ 1.0/hr at the 1 FA/hr operating point (point estimates, CIs shown).
9. **Misses:** each miss gets the first cause that applies, in this order: blunted (`g_hr` < 0.5), artifact (one in the 15 min before collapse), confounder (a spike in the 15 min before collapse), fast bleed, otherwise other.
10. **Descriptive only:** detection of non-bleed hypotension events (not expected to be early), and for `bleed_no_collapse`, how the risk score changed as blood loss accumulated.

---

## 6. Tests (write alongside code)
- `f(t)` is zero before `t0` and non-decreasing after
- MAP stays within a small band of baseline until `f_c`, then falls
- labels line up with the injected decompensation time
- blunted cases (low `g_hr`) produce a smaller HR rise
- no generator-internal column reaches the feature matrix
- the synth-train / val / test case-ID sets don't overlap
- the existing causality test passes on synthetic streams
- `pytest` passes before each commit

---

## 7. Time box
| Step | Budget |
|---|---|
| Generator + tests | 2 h |
| Train + evaluate per tier | 1.5 h |
| Write-up (MODEL_CARD section, this file's results section) | 0.5 h |

Hard stop at 4 h total, then move to the interface whatever happens.

Commits and tags: `round4-plan` → `round4-generator-frozen` → `round4-results`.

---

## 8. How real data and simulation fit together (for the pitch)
- **Simulation:** shows the method catches bleeds early when compensation happens, and shows where it breaks (blunted response, confounders).
- **Real VitalDB:** on mixed-cause surgical hypotension, a tuned MAP threshold is as good as the drift features. This is consistent with confounders swamping the bleeding signal.
- **The gap between the two** is the argument for the next step: trauma or ICU data with bleeding-specific labels (for example, transfusion need), which needs credentialed access.

---

## 9. Draft explanation paragraph (Devpost)
> Real surgical data can't tell us which blood-pressure drops are caused by bleeding: anesthesia, drugs and surgical stimulation also lower pressure, and there are no bleed timestamps. So we built a semi-synthetic test bed. We take real, stable stretches of patient data from VitalDB, keeping their real heart-rate variability and sensor noise, and inject simulated bleeds whose effects follow the ATLS classes of hemorrhage: heart rate rises and pulse pressure narrows while blood pressure holds, then pressure collapses. We make it progressively harder with realistic noise, blunted heart-rate responses like those in elderly patients or patients on beta-blockers, and confounders such as pain-driven heart-rate spikes and non-bleeding pressure drops. The simulator rules were frozen before training, and testing uses unseen patients and unseen bleed settings. Results are reported per difficulty level and always labeled as simulation.

---

## Sources
- ATLS classes of hemorrhage (10th ed., arrows; base deficit): WikEM summary of ACS Committee on Trauma, ATLS Student Course Manual, 10th ed., 2018 — https://wikem.org/wiki/Template:Hemorrhagic_shock_classes
- Older numeric version (HR ~100/120/140): European trauma bleeding guideline, Crit Care 2007 — https://pmc.ncbi.nlm.nih.gov/articles/PMC2151863/table/T2
- Real patients often deviate from the ATLS table: Mutschler et al., Injury 2014, doi:10.1016/j.injury.2014.08.015
