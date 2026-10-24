# Hemorrhage Early Warning ("Drift") — Build Plan for Claude Code (v2)

Project working name: **Drift** — catching the vital-sign drift that happens while blood pressure still looks normal.
Event: HackPSU Fall 2026 (24 h, Oct 24). Builder: Palak (solo). Tooling: Claude Code on a Mac.

> **How to use this file.** Put it in the repo root as `PLAN.md` (and copy Sections 0, 6A, 12 into `CLAUDE.md` so Claude Code sees them every session). Run the phase prompts in Section 13 one at a time. Every phase has *acceptance criteria*: do not move on until they pass.

> **What changed in v2 (read this first).** (1) The demo is now **one static website with two modes**, not a four-tab Streamlit app. (2) Four design adjustments (Section 6A) are now explicit requirements. (3) The website's look and behavior are specified in detail (Phase 6 and the prompts). (4) A deployment section (Section 15) explains how this demo relates to ER and ambulance use. (5) Timeline, risks, rules and prompts were updated to match.

---

## 0. One-paragraph summary

Trauma patients can bleed for a long time while blood pressure stays normal, because the body compensates (heart rate rises, pulse pressure narrows). Then pressure collapses suddenly. We build an early-warning engine that watches the *dynamics* of heart rate, blood pressure and pulse pressure and warns minutes before the collapse. The engine is a small, calibrated, interpretable model trained and evaluated on real surgical patients (VitalDB, Seoul National University Hospital) and compared against the standard low-pressure alarm. The demo is a single monitor-style web page with two modes: **(1) replay of a recorded real patient** and **(2) a simulated bleed**. In both, the Drift alert appears first and a "standard monitor" alarm fires later, and the gap is shown. Everything synthetic is labeled synthetic; everything real is labeled "surgical, not prehospital trauma."

**What we will and will not claim**
- WE CLAIM: on real intraoperative data, drift features give earlier warning than a threshold alarm at the same false-alarm rate (if the numbers show it).
- WE DO NOT CLAIM: that it works in prehospital trauma, that it detects hemorrhage specifically (the label is hypotension, enriched for high-blood-loss cases), that it is clinically validated, or that it is live. This is a research prototype.

---

## 1. Hackathon-rule compliance (READ FIRST)

The Fall 2025 HackPSU page says projects must be original works created on site: coming with an idea is fine, working on an existing project is not. All code must be attached to the Devpost submission. I have not confirmed the Fall 2026 wording, so **verify it on the HackPSU site or ask organizers before Saturday.**

Safe interpretation until confirmed:
- **Before the event (allowed):** reading, this plan, choosing the dataset, checking VitalDB is reachable, writing the Devpost outline and video script as text.
- **Before the event (avoid):** writing or committing project code (pipelines, models, web page). Do not start the repo early.
- **At the event:** all code is written on site, with Claude Code, from a clean repo. Commit regularly so the history shows work happening during the event.
- Open datasets and open-source libraries are normally fine. If you want to pre-download data, ask organizers first; otherwise download on site.

**Decision (Oct 24):** still unconfirmed. Until the event officially starts: docs and reading only, no project code. Small reference tables (the clinical column dictionary, track names, the clinical table itself) may sit in `data/manual/` as a pre-event exception — they are reference material, not pipeline output. Bulk case downloads (whole-case `.parquet`/`.vital` files) wait for event start unless organizers say otherwise. The organizers' answer, once obtained, is recorded in `ACTIONS.md`.

---

## 2. Problem, pitch and demo story

**One-liner:** "When a patient is bleeding, blood pressure is the last thing to move. We watch what moves first."

**Why it matters (sourced):** hemorrhage is the leading cause of preventable trauma death, and traditional vital signs are insensitive to early blood loss because of compensatory mechanisms (published abstract, Biosensors 2022).

**Rubric mapping (our own estimate, not predictions):**
| Criterion | How Drift addresses it |
|---|---|
| Implementation | Real data pipeline, calibrated model, proper baselines, working offline web demo |
| Clarity | One-sentence problem; a screen where pressure stays flat while the Drift alert fires |
| Creativity | Dynamics-based early warning with abstention and honest failures, not an LLM wrapper |
| Growth | Clinical time-series, alarm-quality metrics, calibration (state what is new for you) |
| Impact | Preventable trauma death; vital signs are what is available where labs/imaging are not |

**Known competition risk:** predicting intraoperative hypotension from VitalDB is already a published area. Do not pitch "first." Pitch: physiology-grounded framing, interpretable features, honest false-alarm accounting, and a demo anyone can understand.

---

## 3. Data sources

### 3.1 Primary: VitalDB (South Korea) — OPEN, no credentialing
- 6,388 non-cardiac surgical cases, Seoul National University Hospital, 2016–2017. Waveforms at 500 Hz and numerics at 1–7 s intervals. Listed on PhysioNet as open access.
- Pages: https://vitaldb.net/dataset and https://physionet.org/content/vitaldb/1.0.0/
- Clinical fields that exist (confirmed on the dataset page): `intraop_ebl`, `intraop_rbc`, `intraop_ffp`, `intraop_crystalloid`, `intraop_colloid`, `intraop_uo`, `aline1`/`aline2`. Also expected (verify in Phase 1): `caseid`, `age`, `sex`, `weight`, `asa`, `emop`, `opstart`/`opend`, `anestart`/`aneend`.
- Tracks expected (verify names in Phase 1): `Solar8000/HR`, `Solar8000/ART_SBP`, `Solar8000/ART_DBP`, `Solar8000/ART_MBP`, plus `SNUADC/ART` (500 Hz arterial waveform; **not needed for v2**, stretch only).
- **Access (checked 2026-10-23):** public, read-only, no login. License CC BY 4.0. `https://api.vitaldb.net/cases` returns the clinical table as CSV; `https://api.vitaldb.net/{caseid}.parquet` (IDs 1–6388, whole case, needs `pip install vitaldb` 1.7+ to read via `vitaldb.VitalFile`) and `/{caseid}.vital` return raw cases. PhysioNet also hosts `clinical_data.csv` (2.1 MB), `clinical_parameters.csv` (column dictionary), `track_names.csv` and `vital_files/0001.vital`… under `https://physionet.org/files/vitaldb/1.0.0/`. **The full dataset is 95.4 GB: never download all of it.** Whole-case files average roughly 15 MB (my estimate), so ~400 cases is about 6 GB; measure the first 5 before bulk download. Track names look like `Solar8000/HR` (Device/Channel); read the exact list, don't guess. `/trks` and the old per-track endpoints are **not verified**; use `track_names.csv` or the library. Cite: Lee H, Jung C. VitalDB… v1.0.0, PhysioNet, https://doi.org/10.13026/czw8-9p62 and Lee HC et al., Scientific Data 2022, https://doi.org/10.1038/s41597-022-01411-5.

### 3.2 Other countries — what I found
| Dataset | Country | Access | Usable by Saturday? |
|---|---|---|---|
| VitalDB | South Korea | Open | **Yes (primary)** |
| INSPIRE (130k surgeries; vitals coarse, up to 5 min) | South Korea | Credentialed via PhysioNet (verify) | No |
| HiRID (~34k ICU admissions) | Switzerland | PhysioNet credentialing + DUA | No |
| SICdb | Austria | PhysioNet credentialing + DUA | No |
| AmsterdamUMCdb | Netherlands | CITI course + license form countersigned by an intensivist | No |
| MOVER (perioperative, 83k cases) | USA | Access terms not verified | Check, optional |
| Porcine exsanguination (6 pigs) | (IEEE DataPort) | Open, free login | Optional figure only |
| LBNP human volunteer studies | Norway, USA | Papers only; no open download found | No |

Conclusion: **only VitalDB is both open and large enough.** Name the credentialed sets as future external validation.

### 3.3 Optional secondary
IEEE DataPort porcine exsanguination: 6 animals, blood loss at 7/14/21/28%. One illustrative figure only; verify file format first.

---

## 4. Architecture

```
VitalDB API ─► data/raw ─► cohort.py ─► data/interim/cohort.parquet
                                │
                 features.py ◄──┘        labels.py
                       │                    │
                       ▼                    ▼
               data/processed/windows.parquet
                       │
   baselines.py   models.py ──► eval.py ──► artifacts/metrics.json, plots/
                       │
          replay.py (select cases, causal risk, export)
                       │
                       ▼
   web/data/replay_cases.js   web/data/model_meta.js   web/data/sim_curves.js   web/data/proof.js
                       │
                       ▼
   web/index.html + app.js + style.css   (static, no build step, works offline from file://)
```

### 4.1 Repo layout
```
drift/
  README.md  PLAN.md  CLAUDE.md  DATA_CARD.md  MODEL_CARD.md  LIMITATIONS.md
  requirements.txt
  src/drift/
    config.py            # ALL constants: thresholds, windows, horizons, seeds, operating point
    vitaldb_io.py  cohort.py  preprocess.py  features.py  labels.py
    baselines.py  models.py  alarms.py  metrics.py
    simulator.py         # reference ATLS-inspired simulator (exports curves to the web)
    replay.py            # case selection + causal risk export
  scripts/               # 01_fetch.py ... 07_export_web_data.py
  web/
    index.html  style.css  app.js
    data/                # replay_cases.js, sim_curves.js, model_meta.js, proof.js (generated; committed)
  tests/
  data/                  # .gitignored
  artifacts/             # small outputs committed (metrics.json, plots)
```

---

## 5. Environment (Mac)

- Python 3.11+, `python -m venv .venv`.
- Packages: `numpy pandas pyarrow scikit-learn scipy matplotlib vitaldb joblib pytest`. Use scikit-learn's `HistGradientBoostingClassifier` (no OpenMP install problems).
- **The web demo uses no build tools and no libraries** (plain HTML, CSS, JavaScript, canvas). No Node, no npm, no CDN, so it works offline.
- Network: API may be slow on event Wi-Fi. Retry and cache; never re-download a cached case.
- All constants in `config.py`; fixed seed everywhere.

---

## 6. Step-by-step build

### Phase 0 — Repo and guardrails (30 min)
Create repo, folders, `config.py` placeholders, `.gitignore` (data/, .venv), `CLAUDE.md`, a passing pytest.
Accept: `pytest` passes; no data committed.

### Phase 1 — VitalDB access and inventory (1.5 h)
1. `vitaldb_io.py`: fetch the case table from `https://api.vitaldb.net/cases`; get the track list from PhysioNet's `track_names.csv` (or per-case via the library); cache to `data/raw/`. Do not rely on a `/trks` endpoint unless you confirm it works.
2. Print and save the **actual** column and track names. Update `config.py` if my expected names are wrong. Do not guess names.
3. Flag cases with invasive-arterial HR, SBP, DBP, MAP.
4. Write `data/interim/inventory.parquet`: availability flags, duration, EBL, RBC units, age, ASA, emergency flag.
5. Test on 5 cases first: fetch `https://api.vitaldb.net/{caseid}.parquet` (or the library), keep only the numeric tracks, resample to a 30 s grid, and print file size and time per case. Extrapolate disk and time before bulk download (target 300–500 cases; about a third high blood loss or transfused, the rest random arterial-line cases); cache the lean tables and delete raw files if disk is tight.
Accept: counts printed (total, with arterial line, with all four tracks, by EBL bucket); one case plotted and plausible.

**Decision gate (hour ~3) — tiers (decided Oct 24):**
- **300 or more usable cases and 100 or more events:** proceed as planned.
- **150–299 cases or 60–99 events:** proceed, but apply the Section 7 event-definition fallback if needed, expect wide confidence intervals, and state that in the Proof drawer and `DATA_CARD.md`.
- **Under 150 cases or under 60 events:** pivot to simulator-first, replay whatever real cases exist, and make no performance claims.

### Phase 2 — Cohort and events (1.5 h)
- **Eligible case:** age ≥ 18; invasive arterial numerics present; ≥ 60 min usable monitoring after the exclusion window.
- **Exclusion window:** first 15 minutes after anesthesia start (induction hypotension is expected and non-hemorrhagic); anything outside the operation window.
- **Artifact rejection:** MAP 20–250, SBP 30–300, DBP 10–200, HR 20–250; SBP > DBP; no interpolation beyond 60 s.
- **Event (the label):** MAP < 65 mmHg sustained ≥ 60 s; event starts at the first sample of the run. Sensitivity analysis: SBP < 90.
- **Cohort A** (all eligible) for false-alarm estimates; **Cohort B** (high blood loss).
  - **Decision (Oct 24):** Cohort B = any RBC transfusion OR `intraop_ebl` ≥ 500 mL, among eligible adults. Set once from the clinical table's distribution before any model results exist. If that gives fewer than 60 cases or under 10% of eligible cases, use the top quartile of `intraop_ebl` instead. Record the final choice and the resulting counts in `DATA_CARD.md`. Never change the choice after seeing results.
- **Caveat for DATA_CARD.md:** EBL and transfusion are end-of-case totals with no timing. They choose cases; they are **never** model inputs.
Accept: `cohort.parquet`; funnel with real numbers in DATA_CARD.md; event-detector unit tests on toy series.

### Phase 3 — Windows, labels, features (2 h)
- **Prediction times:** every 1 minute.
- **Positive:** an event starts within the next H minutes (primary H = 15; also 5, 10, 30).
- **Exclude:** prediction times with MAP < 65 in the previous 5 minutes.
- **Features (strictly causal):** current HR, SBP, DBP, MAP, PP, PP/SBP, shock index; slopes (5/10/15 min) of HR, MAP, PP, shock index; MAP standard deviation; min MAP; missing fraction; drift from patient baseline (median of first 10 usable minutes after the exclusion window; used only after the baseline period); context at start: age, sex, ASA, emergency flag. No end-of-case totals.
Accept: `windows.parquet`; positive rates by cohort; causality unit test; leakage checklist (Section 8).

### Phase 4 — Baselines, models, evaluation (3 h)
- **Patient-level split** by `caseid` (and subject ID if present): 60/20/20, fixed seed. Test set touched once.
- **Baselines:** B1 MAP < 65 (zero lead; the standard alarm); B2 early MAP threshold (70–75, tuned to the same false-alarm rate); B3 shock index > 0.9 (and tuned); B4 MAP-slope rule.
- **Models:** logistic regression (standardized, class-weighted) then `HistGradientBoostingClassifier`.
  - **Decision (Oct 24):** ship the logistic model unless the boosted model beats it on the **validation set** by BOTH (a) the bootstrap-by-case 95% CI of the AUPRC difference excluding zero, and (b) at least 5 percentage points more sensitivity at 1 false alarm per patient-hour. Decide on validation only; never use the test set to pick the model. The logistic model's coefficients power the "why" panel regardless of which model is shipped for the headline numbers.
- **Calibration** on validation (isotonic or Platt); Brier + reliability plot.
- **Alarm logic:** alert when calibrated risk ≥ threshold; 15-min refractory; suppressed if MAP already < 65 or missing fraction too high ("insufficient data").
- **Operating point:** threshold chosen on validation for a target of **1 false alarm per patient-hour** (also report 0.5 and 2). Store the chosen threshold in `config.py` as the demo's operating point.
- **Metrics (test set, bootstrap 95% CI by case):** event-level sensitivity, median/IQR lead time, false alarms per patient-hour, AUROC/AUPRC (secondary), Brier; for Cohorts A and B; H = 5/10/15/30.
- Report unfavorable results plainly. Never tune on the test set.
Accept: `metrics.json` and plots regenerate with one command.

### Phase 5 — Hemorrhage simulator (2 h, parallel with Phase 4)
Purpose: physiology-grounded, **always labeled synthetic**.
- ATLS-inspired reference: Class I < 15% loss, vitals near normal; Class II 15–30%, heart rate up (~100–120), pulse pressure decreased, pressure still normal; Class III 30–40%, heart rate ~120–140, pressure decreased; Class IV > 40%, heart rate > 140, severely low pressure.
- Smooth curves of blood-volume fraction lost `f` (0–0.45): `HR(f)` rises; `PP(f)` narrows early; `MAP(f)` holds within a few mmHg until compensation limit `f_c` (default ~0.27) then falls; `SBP = MAP + 2/3·PP`, `DBP = MAP − 1/3·PP`.
- Variability: baseline HR0/MAP0, per-patient `f_c`, AR(1) noise, three bleed profiles (slow ooze, steady, sudden), **blunted-response switch** (heart-rate rise × ~0.35; for beta-blockers or elderly).
- **Drift score for the simulator is a transparent rule score**, not the VitalDB model (distribution-shift risk): `drift = clamp(100·(0.5·(HR−72)/60 + 0.5·(42−PP)/28), 0, 100)`; alert at `drift ≥ 45`. Keep these constants in `config.py`; the web page reads them from `sim_curves.js`.
- Export `web/data/sim_curves.js`: mean HR, MAP, SBP, DBP, PP at `f` = 0 to 0.45 in 0.005 steps for blunted = false and true. The web page interpolates these (so Python and web can't disagree) and adds only cosmetic seeded noise.
Accept: tests show monotonic trends (HR up, PP down with f; MAP within tolerance until `f_c`); computed alert point and MAP < 65 point printed for both settings; SYNTHETIC wording defined for the UI.

### Phase 6 — Replay export + the website (4–5 h) — **REWRITTEN IN v2**

**6.1 Replay export (`replay.py`, `scripts/07_export_web_data.py`)**
- Select **four labeled example types** from the *test set only*, using explicit rules written in `config.py` and documented in `DATA_CARD.md`:
  - **Best example:** detected event with the longest lead time and clean data.
  - **Typical:** detected event with lead time nearest the median.
  - **Miss:** an event with no alert in the lookback window.
  - **False alarm:** an alert with no event in the next H minutes.
  Include 2 cases of each type if available (8 total), plus one "insufficient data" example if one exists.
- Excerpt per case: from 40 minutes before the event (or alert, for false alarms) to 10 minutes after, at 30 s resolution. Playback target ≈ 30× so a 50-minute excerpt plays in about 100 seconds.
- **Risk values are computed causally offline** (Adjustment A3) at each prediction time (1-minute stride), using only data up to that time.
- Per case export to `web/data/replay_cases.js` as `window.DRIFT_CASES = [...]`, each with:
  `id, kind (best|typical|miss|false_alarm|insufficient), title, excerpt_start_s, dt_s, t[], hr[], sbp[], dbp[], map[], pp[], si[], missing[], risk_t[] (minute stride), risk[], alert_t (or null), standard_alarm_t (first sustained MAP<65, or null), event_t, top_features_at_alert [{name, value, direction}] (top 3), verdict (computed text input: lead_min or "missed" or "false alarm")`.
- Export `model_meta.js`: operating-point threshold, horizon H, refractory, feature display names and plain-language explanations.
- Export `proof.js`: the Proof table (sensitivity at 0.5/1/2 false alarms per patient-hour for Drift vs baselines, median lead time, Brier, cohort counts) read from `metrics.json`. **No number may be typed by hand into the web files.**
- **Data are `.js` files that assign `window.*` globals, not `.json` files.** Browsers block `fetch()` of local JSON when you open `index.html` by double-click (file://). Using `.js` makes the page work offline with no server.
Accept: a Python check script re-derives risk at 20 sampled timepoints from truncated data and matches the exported risk (causality); schema validator passes; total `web/data` size < 10 MB.

**6.2 The website — what it looks like**

*One static page. Two modes selected by a two-tab control. No framework, no build step, no network calls. Dark "bedside monitor" look, readable from about 2 meters at an expo.*

**Look and feel**
- Dark theme only. Background `#0E1116`; panels `#161B22`; hairline borders `#2A313C`; text `#E6EDF3`; secondary text `#9BA7B4`.
- Trace colors (also labeled in text, never color alone): MAP `#FF6B5E`, heart rate `#4ADE80`, pulse pressure `#38BDF8`.
- State colors: monitoring `#9BA7B4`; Drift alert amber `#F5B84B`; standard alarm / low pressure red `#FF5C5C`; synthetic badge purple `#B79CFF`; real-data badge teal `#2DD4BF`.
- Typography: system sans-serif; numerals tabular; sentence case; big numbers ≥ 48 px, body ≥ 16 px, nothing below 13 px.
- Design target 1440×900 laptop and 1280×720 projector; on narrow screens the side panel stacks under the chart. No horizontal scrolling.
- Respect `prefers-reduced-motion` (stop the pulse animation; keep numbers updating).

**Layout (desktop)**
```
┌──────────────────────────────────────────────────────────────────────────┐
│ DRIFT   early warning for hidden bleeding      [REAL DATA, surgical]  ⓘ  │ <- header; badge changes per mode
├──────────────────────────────────────────────────────────────────────────┤
│ [ Replay of a recorded patient ]  [ Simulated bleed ]                    │ <- the only two tabs
├─────────────────────────────────────────────────┬────────────────────────┤
│ ▶ Play   Speed [30×]  ───●──────── 12:40 / 50:00│  ♥ 78 bpm   (beating)  │
│ Case [ Best example ▾ ]  "Recorded patient,     │  MAP 89 mmHg           │
│   sped up 30×. Not live."                       │  Pulse pressure 41     │
│ ┌─────────────────────────────────────────────┐ │  Shock index 0.7       │
│ │ DRIFT: Monitoring · no alert                │ │ ─────────────────────  │
│ ├─────────────────────────────────────────────┤ │  Risk of low pressure  │
│ │  scrolling 30-min chart                     │ │  in next 15 min        │
│ │  MAP (with 65 line) · HR · pulse pressure   │ │  [ gauge   18% ]       │
│ │  Drift alert marker ▲ (amber)               │ │  Data quality: good    │
│ │                                             │ │ ─────────────────────  │
│ └─────────────────────────────────────────────┘ │  Why (appears on alert)│
│ STANDARD MONITOR (same clock, simple low-       │  • HR 18 above baseline│
│ pressure alarm only)                            │  • Pulse pressure -30% │
│ ┌─────────────────────────────────────────────┐ │  • Shock index 0.8→1.0 │
│ │ MAP 89   Standard alarm: not triggered      │ │                        │
│ └─────────────────────────────────────────────┘ │                        │
│ Verdict strip: (empty until the standard alarm  │                        │
│   fires or the excerpt ends)                    │                        │
├─────────────────────────────────────────────────┴────────────────────────┤
│ Research prototype · not for clinical use · no alert does not mean safe    │ <- always visible
│                                                  [ Proof and method ▸ ]   │ <- opens a drawer
└──────────────────────────────────────────────────────────────────────────┘
```

**Mode 1 — Replay of a recorded patient**
- Controls: Play/Pause (space bar also), Restart, speed selector (10×, 30×, 60×; default 30×), scrubber, case picker.
- Case picker groups: "Best example," "Typical," "Miss," "False alarm," "Insufficient data." Right under it, always visible: **"Selected examples, not average performance. Results across all test cases are in Proof and method."**
- **Banner text must say: "Recorded patient, sped up 30×. Not live."** (the speed updates with the selector).
- The heart indicator pulses at the *current heart rate number* (period = 60 / HR seconds of playback time, scaled by speed so it stays watchable; cap visible pulse rate so it never strobes: maximum ~3 pulses per second on screen). Sound is **off by default**; a speaker toggle is optional.
- **Drift banner states (text + icon, not just color):**
  - Monitoring: "Monitoring · no alert"
  - Alert: "DRIFT ALERT · Vitals drifting toward low pressure. Check the patient." (amber) with the "Why" list filled from `top_features_at_alert`
  - Insufficient data: "Not enough data to assess" (grey)
- **Standard monitor strip** (same clock): shows MAP and "Standard alarm: not triggered" until MAP stays below 65 for 60 s, then red "STANDARD ALARM · MAP below 65".
- **Verdict strip (appears only after the standard alarm fires, or at the end of the excerpt):** computed from exported fields:
  - Detected: "Drift alerted 11 min before the standard alarm."
  - Miss: "Missed: Drift gave no warning in this case."
  - False alarm: "False alarm: pressure stayed above 65 for the next 15 minutes."
  A thin timeline bar under the strip marks the two moments (Drift alert ▲ amber, standard alarm ▲ red) with the gap labeled.
- **Nothing from the future may appear before its time** (Adjustment A3): the chart, risk gauge, "Why" list and verdict all reveal only at the current playback time.

**Mode 2 — Simulated bleed**
- Same layout and same two strips. Header badge: **SYNTHETIC patient, not real data** (purple). Banner text: "Simulated patient. Not real data."
- Controls: "Blood lost" slider 0–45%; Play bleed (auto-advances `f` over about 60 s); bleed profile selector (slow ooze, steady, sudden); checkbox "Blunted heart-rate response (beta-blocker or older patient)"; Reset.
- Chart x-axis can be time (during auto-play) with `f` shown as a readout.
- Drift alert fires at `drift ≥ 45` (rule score, labeled "Transparent rule score, not the trained model"). Standard strip fires when MAP < 65 sustained.
- Verdict strip: "Drift alert at 19% blood lost. Standard alarm at 36%. That is 17 percentage points of blood volume of warning." (values computed from the curves). With the blunted toggle on, the alert should come later; if it never fires before collapse, show "No warning before collapse in this setting."

**Proof and method drawer** (opens over the right side; closes with Esc)
- Table: sensitivity at 0.5 / 1 / 2 false alarms per patient-hour for Drift vs baselines; median lead time; Brier score; calibration plot image; cohort counts. All from `proof.js`.
- Plain-language "How it works" in 5 lines and a "What this is not" block (not trauma data, label is low pressure, single hospital, not validated).

**Footer (always visible):** "Research prototype · not for clinical use · no alert does not mean safe."

**Accessibility and robustness**
- Keyboard: space = play/pause; arrow keys = scrub; Esc = close drawer.
- Contrast WCAG AA on text; alert states always include words.
- All time displays in mm:ss of the excerpt. Numbers rounded to integers (MAP, HR, PP) and one decimal (shock index).
- No console errors; no network requests (check the browser's network tab).
- Works from a double-clicked `index.html` (file://) in Chrome and Safari.

**Defined interface for future data sources (the "adapter seam")**
In `app.js` implement a tiny interface so the page doesn't care where vitals come from:
`class VitalsSource { start(); pause(); seek(t); onSample(callback) }`
with `ReplaySource` (VitalDB excerpt), `SimulatedSource` (simulator curves) and a documented-but-unimplemented `DeviceSource` (a future live feed). This is how we say, truthfully, "a monitor could feed this page," without building it.

**Decision (Oct 24) — what "documented" means for `DeviceSource`:** a comment block above the class with the method signatures, the expected sample format (`timestamp` in seconds, `hr`, `sbp`, `dbp`, `map`, a `quality` flag), the update cadence, and a stub body that throws `"DeviceSource not implemented"`; plus one line about it in the README's limits section. No other implementation is required.

Accept when: (a) opening `web/index.html` from disk shows both tabs working with no console errors and no network requests; (b) every state in the banner/strip tables above can be reached (alert, standard alarm, miss, false alarm, insufficient data, blunted no-warning); (c) nothing future-dependent is visible before its time (scrub backwards and verify the verdict disappears); (d) screenshots saved for Devpost at 1440×900 and 1280×720; (e) a 90-second screen recording exists.

### Phase 7 — Tests, documentation, submission (3 h)
- Tests: event detector, feature causality, split disjointness, simulator monotonicity, alarm refractory logic, metric computations, replay-export causality and schema.
- Manual UI QA checklist (Section 9A).
- Docs: `README.md` (what/why/how to run: "open `web/index.html`"; how to reproduce the pipeline in ≤ 5 commands), `DATA_CARD.md`, `MODEL_CARD.md`, `LIMITATIONS.md`, citations.
- Devpost: problem, solution, one diagram, data and honesty section, results table, what is synthetic, what's next (external validation, trauma data, device integration), GitHub link, 2–3 min video.
- Video script (3 min): hook → problem → replay with alert → standard alarm later → simulator (blunted toggle) → numbers vs baselines → limits and next steps.

**Decision (Oct 24) — docs and test scope, final:**
- **Required:** short `README.md`, `LIMITATIONS.md`, Devpost text, video.
- `DATA_CARD.md` and `MODEL_CARD.md` are one page each, generated from `metrics.json` (no hand-typed numbers).
- **Tests, final list (no more, no less unless time allows):** event detector, feature causality, split disjointness, replay-export causality.
- **Draft the Devpost text and video script with placeholders around hour 10**, so hours 18–22 are only: fill in real numbers, record the video, and take screenshots.
- **If anything slips, cut in this order:** (1) boosted model, (2) horizon sweep, (3) the insufficient-data example case, (4) `MODEL_CARD.md` as a separate file (fold its content into the README instead).

---

## 6A. The four design adjustments (now requirements) — what, why, how, acceptance

**A1. Label the replay honestly as "recorded patient, sped up," not live.**
- *What:* The first mode plays a 40–50 minute excerpt around an event at about 30×. The banner states "Recorded patient, sped up 30×. Not live."
- *Why it matters:* Surgical cases last hours, so a true real-time demo would need hours. More importantly, calling a replay "live" would mislead judges about what was tested. Honest labeling protects your credibility, which is the main thing judges can't verify themselves.
- *How:* Excerpt export in Phase 6.1; banner text and speed selector in Phase 6.2.
- *Accept:* the words "Recorded" and "Not live" are visible at all times in replay mode, and speed is shown.

**A2. Drive the heartbeat indicator from the heart-rate number, not the 500 Hz waveform.**
- *What:* A pulsing heart indicator whose rate follows the `HR` value.
- *Why it matters:* The raw 500 Hz arterial waveform means far larger downloads, more processing and more things that can break in 24 hours, and it doesn't change the alert logic, which uses 30-second numerics. A number-driven pulse gives the "it's a living patient" feel at almost no risk. Waveform rendering is a stretch goal only if everything else is finished.
- *How:* CSS/canvas pulse with period tied to HR; cap on-screen pulse rate; reduced-motion support.
- *Accept:* pulse speed visibly changes when HR changes; no raw waveform data is shipped.

**A3. Compute the alert from data up to each moment only (causal).**
- *What:* The risk score at time *t* is computed using only samples at or before *t*. The page reveals nothing from after the current playback time.
- *Why it matters:* A replay already contains the future. If any feature (baseline, smoothing, scaling) peeks ahead, the "earlier than the standard alarm" claim is inflated and the whole project becomes untrustworthy. This is the single most important integrity requirement.
- *How:* Causal feature code (Phase 3), a test that recomputes risk from truncated data (Phase 6.1 acceptance), and UI that reveals by playback time (Phase 6.2).
- *Accept:* the causality check script passes; scrubbing backwards hides the alert, "Why" list and verdict.

**A4. Keep the miss and the false alarm in the case picker, with a "selected examples" note.**
- *What:* Replay includes best, typical, miss and false-alarm cases, with the visible note "Selected examples, not average performance."
- *Why it matters:* A demo with only wins looks cherry-picked. Showing a failure and saying why builds trust, answers the "what about false alarms?" question visually, and fits the honest-uncertainty story. Cases are chosen by written rules on the test set, not by hand.
- *How:* Selection rules in `config.py` and `DATA_CARD.md`; picker groups in Phase 6.2.
- *Accept:* at least one miss and one false alarm are present (if none exist in the test set, say so in the UI and docs and show the closest examples).

**A5 (also changed): static website instead of Streamlit.**
- *Why:* Replay animation needs smooth client-side updates; Streamlit reruns the script on every interaction. A static page can't fail offline, needs no server, can be double-clicked, and can be hosted free on a static site as a backup.

---

## 6B. Decided constants for `config.py` (Oct 24)

All of these are decisions above, collected here so Phase 0 scaffolds them as named constants instead of leaving them as prose:

- `COHORT_B_MIN_EBL_ML = 500` — Cohort B definition: `intraop_ebl` ≥ this, OR any RBC transfusion.
- `COHORT_B_FALLBACK_MIN_CASES = 60` — if Cohort B has fewer cases than this, fall back to the top-quartile rule.
- `COHORT_B_FALLBACK_MIN_FRACTION = 0.10` — or if Cohort B is under this fraction of eligible cases.
- `MODEL_SELECT_MIN_SENSITIVITY_GAIN_PP = 5` — boosted model must beat logistic by at least this many percentage points of sensitivity at the 1 FA/patient-hour operating point, on validation.
- `MODEL_SELECT_REQUIRE_AUPRC_CI_EXCLUDES_ZERO = True` — AND the bootstrap-by-case 95% CI of the validation AUPRC difference must exclude zero.
- `INSUFFICIENT_DATA_MISSING_FRAC = 0.30` — missing-fraction cutoff in the 10-minute window.
- `INSUFFICIENT_DATA_MAX_EXCLUDED_FRAC = 0.10` — max acceptable share of validation windows this cutoff may exclude; report the actual share.
- `EVENT_MAP_THRESHOLD_MMHG = 65`, `EVENT_DURATION_S = 60` — primary/headline event definition.
- `EVENT_FALLBACK_DURATION_S = 30`, `EVENT_FALLBACK_SBP_THRESHOLD_MMHG = 90` — secondary definitions; only one may become primary, and only via the Section 7 fallback switch, done once, before training.
- `DECISION_GATE_TIER1_MIN_CASES = 300`, `DECISION_GATE_TIER1_MIN_EVENTS = 100` — proceed as planned.
- `DECISION_GATE_TIER2_MIN_CASES = 150`, `DECISION_GATE_TIER2_MIN_EVENTS = 60` — proceed with caveats (wide CIs stated in Proof drawer and DATA_CARD.md).
- `PHASE4_HARD_DEADLINE_HOUR = 10` — if Phase 4 isn't done by this hour, stop Phase 5 and finish Phase 4 first.

---

## 7. Precise definitions (keep consistent everywhere)

7.1 **Event:** first sample of a run with MAP < 65 mmHg lasting ≥ 60 s.
7.2 **Prediction time `t`:** every 1 min; label 1 if an event starts in (t, t + H]; excluded if MAP < 65 in the previous 5 min.
7.3 **Drift alert:** calibrated risk ≥ operating-point threshold; 15-min refractory; suppressed when data insufficient or MAP already < 65.
7.4 **Insufficient data:** missing fraction in the 10-minute window above a configured limit.
  - **Decision (Oct 24):** finalized at 30%, no score shown above that. Check on validation that it excludes at most 10% of windows; report the actual share in `DATA_CARD.md`.
7.5 **True alarm / lead time:** an alert at time a is true if an event starts in (a, a + H]; lead time = event start − first such alert.
7.6 **False alarm rate:** false alarms ÷ monitored patient-hours (monitored time excludes exclusion windows).
7.7 **Standard alarm (demo strip):** MAP < 65 mmHg sustained ≥ 60 s. Real monitors use configurable thresholds and delays; ours is a simple stand-in, and the UI says "simple low-pressure alarm."

**Decision (Oct 24) — event definition, final:** primary and headline = MAP < 65 mmHg sustained for 60 s (7.1, 7.7 as written). Everything else is secondary and reported separately, never in the headline: SBP < 90 for 60 s, and a 30 s duration version. The replay's standard-alarm strip always uses the primary definition. The only exception is the fallback described in Section 6 / Section 10 when events are under about 100: switching to the 30 s version (or SBP < 90) becomes the new primary, and the strip changes with it. That switch happens at most once, before training, is stated in `DATA_CARD.md`, and is not undone later.

---

## 8. Leakage and validity checklist (run before reporting any number)

- [ ] Split by case (and subject if available), never by row.
- [ ] No end-of-case totals (EBL, RBC, FFP, fluids) used as features.
- [ ] Baseline for drift features uses only data before the prediction time.
- [ ] Scaling, calibration and threshold choice fitted on train/validation only.
- [ ] Test set evaluated once; no tuning afterwards; replay cases come from the test set.
- [ ] Feature unit test proves causality; replay export check proves causality.
- [ ] Event counts and positive rate printed for train/val/test.
- [ ] Bootstrap confidence intervals by case.
- [ ] Confounders acknowledged: anesthetic depth, vasopressors, surgical events (stretch: vasopressor-running feature if the track exists).

---

## 9. Demo day script and fallbacks

- Primary: `web/index.html` opened from disk on your laptop, offline.
- Backup 1: a 90-second screen recording of both modes.
- Backup 2: static screenshots in Devpost.
- Optional: host the `web/` folder on a free static host or GitHub Pages as a backup link; never depend on it at the expo.
- 60-second booth routine: (1) "Blood pressure is the last thing to move." (2) Press Play on the best example; point to the beating heart and flat pressure. (3) When the amber alert appears, say "the heart is working harder; that's our alert." (4) Let the red standard alarm fire later; read the verdict. (5) Switch to Simulated bleed, drag the slider, tick the blunted toggle. (6) Show the miss case: "here is where it fails."
- Q&A prep is in the pitch guide.

### 9A. Manual UI QA checklist
- [ ] Opens by double-click in Chrome and Safari; both tabs work; no console errors.
- [ ] Network tab shows zero requests.
- [ ] Banner says "Recorded patient, sped up Nx. Not live." in replay; "Simulated patient. Not real data." in simulator.
- [ ] Alert, standard alarm, verdict states all reachable; scrubbing back hides future items.
- [ ] Miss and false-alarm cases play and show the right verdict text.
- [ ] Heart pulse tracks HR; no strobing; reduced-motion respected.
- [ ] 1280×720 and 1440×900 layouts have no overflow; narrow screen stacks.
- [ ] Footer line and badges always visible.
- [ ] Proof drawer numbers match `metrics.json`.

---

## 10. Risks, kill rules and fallbacks

| Risk | Signal | Response |
|---|---|---|
| VitalDB API slow or down | Phase 1 downloads fail repeatedly | Reduce to ≈ 300 cases; if unreachable by hour 4, build simulator-first and reframe honestly |
| Too few events | < ~100 events after exclusions | Lower sustained duration to 30 s or use SBP < 90; widen to all arterial-line cases |
| Model does not beat baselines | Equal-false-alarm sensitivity not better | Present the honest result; lead with the simulator, causal replay, calibration, abstention and failures |
| No miss or false-alarm case in the test set | Selection finds none | Say so in the UI; show the closest cases (lowest lead time, highest-risk non-event) |
| Time slip | Phase 4 not done by hour 12 | Freeze at logistic regression; skip boosted model and horizon sweep; build the web page with the simulator tab first |
| Web page fragile | Any live call needed | All data in local `.js` files; no network; recording as backup |
| Replay data too large | `web/data` > 10 MB | Fewer cases, 60 s resolution, shorter excerpts |

Hard time gates: data inventory by H3; cohort + features by H6; first model + metrics by H10; replay export by H11; **web page working end-to-end by H16; feature freeze H18**; docs/video from H18; submit with ≥ 2 h buffer.

---

## 11. Hour-by-hour timeline (24 h, solo with Claude Code)

| Hours | Work |
|---|---|
| 0–1 | Phase 0 repo/guardrails |
| 1–3 | Phase 1 inventory + downloads (run in background while writing cohort code) |
| 3–6 | Phase 2 cohort/events; Phase 3 features/labels (decision gate H3) |
| 6–10 | Phase 4 baselines, model, calibration, metrics |
| 8–11 | Phase 5 simulator + `sim_curves.js` (filler during Phase 4/1 background jobs only) |
| 10–11 | Phase 6.1 replay export + causality check |
| 11–16 | Phase 6.2 website: replay mode, simulator mode, proof drawer |
| 16–18 | Polish, UI QA, tests; **feature freeze H18** |
| 18–22 | Docs, Devpost, record video, screenshots |
| 22–24 | Buffer, final checks, submit |

**Decision (Oct 24) — no true multitasking.** Overlap two phases only when one of them is a background job (downloads, training) with nothing to actively watch. Phase 5 (simulator) is the designated filler for those waits — do not treat the 8–11 overlap as working two phases by hand at once. **If Phase 4 is not done by hour 10, stop Phase 5 work and finish Phase 4 first.**

Sleep: schedule at least one real break; don't touch model evaluation during it.

---

## 12. Rules for Claude Code (paste into CLAUDE.md)

- Follow PLAN.md phase by phase; stop at acceptance criteria and report results.
- Never guess dataset column or track names; read them from the downloaded inventory and update `config.py`.
- All constants in `config.py`; fixed seed; deterministic outputs.
- Never use end-of-case totals (EBL/RBC/FFP/fluids) as model features.
- Splits are by case. Test set is evaluated once. Replay cases come from the test set.
- Risk values for replay are computed causally; the UI reveals nothing before its playback time.
- Every synthetic view says SYNTHETIC; every real-data view says "Recorded patient, surgical, VitalDB (Korea). Not live."
- The web demo is static HTML/CSS/JS with no frameworks, no build step, no network; data are local `.js` files assigning `window.*` globals.
- No number is typed by hand into web files; they are generated from `metrics.json` and the pipeline.
- Do not commit raw data. Commit small artifacts and generated `web/data` files only.
- Write tests alongside code; run `pytest` before declaring a phase done.
- Report unfavorable results plainly; no tuning on the test set.
- No clinical claims. Prototype for research and education only.

---

## 13. Phase prompts to paste into Claude Code (in order)

**P0:** "Read PLAN.md. Do Phase 0 only: scaffold the repo per Section 4.1, create config.py with placeholders for every constant in the plan, .gitignore, CLAUDE.md from Section 12, and a passing pytest. Stop and summarize."

**P1:** "Do Phase 1. Implement vitaldb_io.py to fetch and cache the case table and track list. Print the real column and track names and propose updates to config.py. Build the inventory table with counts by availability and EBL bucket, download numeric tracks for candidate cases with retries and caching, and plot one case. Report counts against the decision gate."

**P2:** "Do Phase 2 using the definitions in PLAN.md Sections 6 and 7. Implement cohort.py, preprocess.py (artifact rejection) and the event detector in labels.py with unit tests on toy series. Write the inclusion/exclusion funnel with real numbers into DATA_CARD.md."

**P3:** "Do Phase 3. Implement features.py (strictly causal), window labeling and exclusion rules. Add a test proving causality and one checking no case appears in more than one split. Print positive rates by cohort and horizon."

**P4:** "Do Phase 4. Implement baselines, logistic regression, HistGradientBoosting, calibration on validation, alarm logic with refractory period, operating-point selection at 1 false alarm per patient-hour (also 0.5 and 2), and metrics with bootstrap CIs by case. Save the logistic model's coefficients and feature scaling so the web page can show 'why'. Produce metrics.json and plots. Run the leakage checklist in Section 8 and report each item."

**P5:** "Do Phase 5. Implement simulator.py per PLAN.md: ATLS-inspired curves, per-patient variability, three bleed profiles, blunted-response switch, and the transparent drift score with the constants in config.py. Add tests for monotonic trends. Export web/data/sim_curves.js (mean HR, MAP, SBP, DBP, PP at f = 0 to 0.45 in 0.005 steps, for blunted false and true) as `window.DRIFT_SIM = {...}`. Print the alert point and the MAP-below-65 point for both settings."

**P6a (replay export):** "Do Phase 6.1. In replay.py select four example types (best, typical, miss, false alarm; two each if available, plus an insufficient-data case if one exists) from the TEST SET only, using written selection rules in config.py that you also document in DATA_CARD.md. For each, export a 40-minutes-before to 10-minutes-after excerpt at 30 s resolution with causally computed risk at 1-minute stride, the Drift alert time, the standard alarm time (MAP below 65 for 60 s), the event time, the top three contributing features at the alert, and the verdict inputs. Write web/data/replay_cases.js (window.DRIFT_CASES), model_meta.js (window.DRIFT_META: threshold, horizon, refractory, feature display names with plain-language explanations) and proof.js (window.DRIFT_PROOF) generated from metrics.json. Use .js globals, not .json. Write a check script that recomputes risk at 20 sampled timepoints from truncated data and confirms it matches. Report file sizes."

**P6b (website, replay mode):** "Do Phase 6.2, part 1: build web/index.html, style.css and app.js as a single static page with no libraries, no build step and no network requests, working when opened by double-click. Follow PLAN.md Phase 6.2 exactly. Dark bedside-monitor look: background #0E1116, panels #161B22, borders #2A313C, text #E6EDF3, MAP #FF6B5E, heart rate #4ADE80, pulse pressure #38BDF8, amber alert #F5B84B, red alarm #FF5C5C, teal REAL DATA badge #2DD4BF, purple SYNTHETIC badge #B79CFF. Header with the DRIFT name and a mode badge; exactly two tabs: 'Replay of a recorded patient' and 'Simulated bleed'. Replay layout: left column has the controls bar (play/pause, restart, speed 10x/30x/60x default 30x, scrubber, case picker grouped as Best example, Typical, Miss, False alarm, Insufficient data, with the permanent note 'Selected examples, not average performance'), a banner reading 'Recorded patient, sped up 30x. Not live.', a Drift status banner (Monitoring, DRIFT ALERT with the text 'Vitals drifting toward low pressure. Check the patient.', or Not enough data), a scrolling 30-minute canvas chart with MAP, heart rate and pulse pressure, a 65 mmHg reference line on MAP and an amber alert marker; below it a STANDARD MONITOR strip on the same clock showing MAP and 'Standard alarm: not triggered' until the red 'STANDARD ALARM, MAP below 65'; then a verdict strip and a small timeline bar showing both markers and the gap. Right column: a heart indicator that pulses at the current heart-rate number (cap on-screen pulse rate, respect prefers-reduced-motion, sound off), large numbers for MAP, pulse pressure, shock index, a risk gauge for 'Risk of low pressure in next 15 minutes', a data-quality line, and a 'Why' list filled from top_features_at_alert only after the alert. Footer always visible: 'Research prototype · not for clinical use · no alert does not mean safe.' Implement the VitalsSource interface (ReplaySource, SimulatedSource, and a documented but unimplemented DeviceSource). Nothing from after the current playback time may be visible; scrubbing backwards must hide the alert, the Why list and the verdict. Space toggles play, arrow keys scrub. Test every state: detected, miss, false alarm, insufficient data."

**P6c (website, simulator mode):** "Do Phase 6.2, part 2: add the 'Simulated bleed' mode using window.DRIFT_SIM, interpolating the exported curves and adding only cosmetic seeded noise. Same layout and same two strips; badge 'SYNTHETIC patient, not real data' and banner 'Simulated patient. Not real data.' Controls: 'Blood lost' slider 0 to 45%, a 'Play bleed' button advancing over about 60 seconds, a bleed-profile selector (slow ooze, steady, sudden), a checkbox 'Blunted heart-rate response (beta-blocker or older patient)', and Reset. The Drift status uses the transparent rule score with the constants from window.DRIFT_SIM, and the interface labels it 'Transparent rule score, not the trained model'. The standard strip fires when MAP stays below 65 for 60 s. The verdict reads 'Drift alert at X% blood lost. Standard alarm at Y%. That is Z percentage points of blood volume of warning.' computed from the data; with the blunted box ticked, show the later alert, or 'No warning before collapse in this setting.'"

**P6d (drawer and polish):** "Do Phase 6.2, part 3: add the 'Proof and method' drawer opened from the footer and closed with Esc, reading only window.DRIFT_PROOF and window.DRIFT_META: the sensitivity table at 0.5, 1 and 2 false alarms per patient-hour for Drift versus baselines, median lead time, Brier score, cohort counts, a five-line plain-language 'How it works' and a 'What this is not' block. Then work through the manual UI QA checklist in PLAN.md Section 9A, fix everything, confirm zero console errors and zero network requests, and save screenshots at 1440x900 and 1280x720."

**P7:** "Do Phase 7. Complete README (how to open the demo and reproduce the pipeline), DATA_CARD, MODEL_CARD and LIMITATIONS, run the full test suite, and draft the Devpost text and 3-minute video script using real numbers from metrics.json. Do not state any number that is not in a generated file."

---

## 14. Sources (verified during planning)

- VitalDB dataset page and field/track list: https://vitaldb.net/dataset
- VitalDB on PhysioNet (open access): https://physionet.org/content/vitaldb/1.0.0/
- VitalDB paper (Scientific Data 2022): https://pmc.ncbi.nlm.nih.gov/articles/PMC9178032
- INSPIRE perioperative dataset: https://link.springer.com/10.1038/s41597-024-03517-4
- Comparison of open perioperative datasets: https://synapse.koreamed.org/articles/1516083781
- Open ICU databases overview: https://linkr.interhop.org/en/resources/public-databases-overview
- HiRID on PhysioNet (credentialed): https://www.physionet.org/content/hirid/1.1/
- AmsterdamUMCdb access (DANS): https://dans.knaw.nl/en/?p=8879
- Porcine exsanguination dataset (IEEE DataPort): https://ieee-dataport.org/node/2382
- Intraoperative hypotension prediction on VitalDB (prior work): https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12654517/
- Arterial-pressure dynamics preprint (2026, not peer reviewed): https://www.medrxiv.org/content/10.64898/2026.08.26.26361468.full.pdf
- Hemorrhage as leading cause of preventable trauma death: https://pubmed.ncbi.nlm.nih.gov/36551134/
- HackPSU Fall 2025 rules page (verify Fall 2026): https://ist.psu.edu/events/hackpsu-fall-2025

*Not verified:* exact VitalDB column/track names beyond the dataset page, VitalDB license wording, ATLS numeric ranges (standard teaching; double-check before quoting), HackPSU Fall 2026 rules, and any integration path to real ER or ambulance equipment.

---

## 15. Deployment: website demo versus ER and ambulance use (honest version)

**What we ship at HackPSU:** a website (static page) that replays recorded data and simulates a bleed. It is a *demonstration of the engine and the interface idea*, not a device.

**Why a website is the right choice now:**
- We have no ER monitor and no ambulance equipment, and I haven't verified how any specific device exposes its data or what integration it would need. Claiming otherwise would be guessing.
- A static page runs offline, anywhere, on anything with a browser, so judges can try it.

**What could sit behind the same screen in real settings (design implications, not promises):**
- *The engine is tiny.* A logistic model on a handful of features can run on a phone, tablet or small bedside computer **without internet**. That matters in ambulances, where connectivity is unreliable. The web page's JavaScript already computes everything it shows from exported coefficients, which is the same idea.
- *The interface is a thin layer.* The `VitalsSource` seam means a future device feed replaces the replay without redesigning the screen.
- *Possible form factors:* a secondary display or tablet beside a patient monitor; a software module inside a monitoring system; a paramedic tablet app. Which is feasible depends on the equipment vendor, hospital IT, and regulatory review, none of which we have checked.

**Real gaps to say out loud:**
- **Data cadence:** our data are continuous invasive arterial readings. Ambulances usually have intermittent cuff readings, so a prehospital version would need retraining and re-validation on that cadence.
- **Setting:** surgery is not trauma (anesthesia and surgical stimulation affect pressure).
- **Regulation and validation:** software that informs clinical decisions may count as a medical device; prospective validation and clinician oversight would come before any clinical use.
- **Alarm design:** where and how an alert appears (sound, wording, who sees it) needs clinician input; our wording is a prototype.

**How to say it:** "This is a website because I don't have ER equipment, and I won't pretend otherwise. The engine is small enough to run on a device without internet, and the screen is built so a live feed could replace the replay. The honest next steps are trauma data, prehospital cadence, and clinician input."
