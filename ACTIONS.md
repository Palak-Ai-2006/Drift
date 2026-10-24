# ACTIONS

A checklist to work through before and during the event.

---

## a. Before the event (me)

- [ ] Ask organizers about pre-downloading data (is this allowed before the event starts?) — **Decision (Oct 24):** until answered, treat as no. Docs and reading only; small reference tables (column dictionary, track names, clinical table) may go in `data/manual/`; bulk case downloads wait for event start.
- [ ] **Organizer's answer, once obtained:** _______________________________ (date asked: _____, date answered: _____)
- [x] Read the VitalDB column dictionary (`clinical_parameters.csv` on PhysioNet) so field names are known in advance — **done 2026-10-24**, downloaded to `data/manual/clinical_parameters.csv` along with `cases.csv` and `track_names.csv`; all expected fields/tracks confirmed exactly, see `DATA_NOTES.md`.
- [ ] Confirm HackPSU 2026 rules and judging criteria (Fall 2026 wording not yet verified — see PLAN.md Section 1). **Specifically also ask:** is any pre-event code or analysis allowed, or must all project code (not just data downloads) be written on site? Our current working assumption (Decision 1) is the strict one — on-site only — until this is confirmed.
- [x] Write the Devpost outline (text only) — **done 2026-10-24**, see [DEVPOST_OUTLINE.md](DEVPOST_OUTLINE.md). Numbers are placeholders; fill from `metrics.json`/`proof.js` only.
- [x] Write the 3-minute video script (text only) — **done 2026-10-24**, see [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md). Numbers are placeholders.
- [ ] Plan sleep (at least one real break during the 24 hours — see PLAN.md Section 11). Draft default below — adjust to your actual arrival/departure times:
  - Hour 0: event starts, Phase 0.
  - Hours ~16–18: once feature freeze hits (Section 10), take the sleep break here rather than during active development — this is after the website works end-to-end and before docs/Devpost, so a gap here costs the least.
  - Do **not** sleep during Phase 4 (hours 6–10, model/metrics) or during the feature-freeze crunch itself (16–18) — these are the two "hard deadline" windows per Decision 6.
  - Target at least a 2–3 hour block; shorter naps during background-job waits (Phase 1 downloads, Phase 4 training) are fine as long as something is still running.
- [ ] Review the two cited papers for pitch accuracy (reading only, PLAN.md Section 14): hemorrhage-as-preventable-death source (pubmed.ncbi.nlm.nih.gov/36551134/) and the VitalDB Scientific Data paper — confirm the exact claims before quoting them in the Devpost/video.
- [ ] Rehearse the 60-second booth routine (PLAN.md Section 9) out loud at least once — it's written as a script but hasn't been practiced.
- [ ] Double check laptop toolchain is present (read-only check, no installs per the hard limits): Python 3.11+, `pip`/`venv` available. Do **not** `pip install` anything yet.
- [ ] Pack/logistics: charger, any snacks/water, something for the sleep block.

---

## b. At event start

### Repo setup
- [ ] `git init`
- [ ] First commit of the docs (PLAN.md, CLAUDE.md, ACTIONS.md, DATA_NOTES.md, .gitignore, empty folders)
- [ ] Create a public GitHub repo
- [ ] Push

### Phase prompts (run one at a time, from PLAN.md Section 13)

**P0 — Repo and guardrails** (target: 0–1 h)
- [ ] Scaffold repo per Section 4.1
- [ ] `config.py` placeholders for every constant, including the Oct 24 decided constants in PLAN.md Section 6B
- [ ] `.gitignore`, `CLAUDE.md` from Section 12
- [ ] Passing pytest
- [ ] Accept: `pytest` passes; no data committed

**P1 — VitalDB access and inventory** (target: 1–3 h)
- [x] `vitaldb_io.py` fetches/caches case table and track list — **done**, reads from `data/manual/` (or `data/raw/` if freshly re-fetched); `download_case_table()` written for a live re-fetch when needed.
- [x] Real column/track names printed and verified (never guessed) — **done**, all 19 expected columns and all 4 expected tracks confirmed present via `scripts/01_fetch.py`.
- [x] Flag cases with invasive-arterial HR, SBP, DBP, MAP — **done** (proxy via `aline1`/`aline2`): 3,463 of 6,388 cases.
- [x] `data/interim/inventory.parquet` written — **done**, 6,388 rows.
- [x] Test on 5 cases: fetch, resample to 30 s grid, print size/time, extrapolate — **done 2026-10-24**, caseids [6269, 757, 6293, 2911, 2349] (sampled deterministically, seed=42, from arterial-line cases). 5/5 succeeded, avg 0.69s/case, avg 10.9 KB/case (lean 4-track 30s tables, not whole raw files) → extrapolates to ~5.7 min / well under 1 GB for 500 cases. Report: `artifacts/phase1_download_test_report.csv`.
- [x] Accept: counts printed (total, with arterial line, with all four tracks, by EBL bucket); one case plotted and plausible — **done**. All 5 test cases have all 4 tracks present with 88–99% coverage. Plot: `artifacts/phase1_case_6269_plot.png` — plausible real surgical trace (HR variability, MAP mostly >65, with expected sensor artifacts at case start/end that Phase 2's artifact-rejection bounds will clean up).
- [ ] **Decision gate (hour ~3), tiers (Oct 24):** cannot be evaluated yet — needs real eligible-case and event counts from Phase 2, not just the raw clinical-table counts above.
  - [ ] ≥300 cases and ≥100 events → proceed as planned
  - [ ] 150–299 cases or 60–99 events → proceed with Section 7 fallback if needed; state wide-CI caveat in Proof drawer and DATA_CARD.md
  - [ ] <150 cases or <60 events → pivot to simulator-first; replay whatever real cases exist; no performance claims

**P2 — Cohort and events** (target: 3–6 h, with P3)
- [x] `cohort.py`, `preprocess.py` (artifact rejection), `labels.py` (event detector) with unit tests on toy series — **done 2026-10-24, per "option 3": written and fully tested on synthetic/toy data, not run against real bulk vitals yet.** 30 new tests, all passing (`test_cohort.py`, `test_labels.py`, `test_preprocess.py`; 48/48 total across the whole suite).
- [x] Inclusion/exclusion funnel with real numbers written into `DATA_CARD.md` — **partially done**: the clinical-table-derivable portion (age≥18, arterial line) ran for real (`scripts/02_build_cohort.py`): 3,419 of 6,388 cases pass both. The ≥60min-usable-monitoring criterion is written and toy-tested (`cohort.usable_monitored_minutes`) but not run at scale — **bulk download for this is now done** (2026-10-24, `scripts/02b_bulk_download.py`: 500/500 cases succeeded, 0 failures, 4.70 MB; selection = 167 high_loss_or_transfused + 333 random_arterial_line, seed=42, deterministic — see `data/interim/bulk_download_selection.csv` and `artifacts/phase2_bulk_download_report.csv`); still need to actually *run* `usable_monitored_minutes`/event detection over these 500 real files to get the real funnel numbers and finalize `cohort.parquet`.
- [x] Cohort B set per Oct 24 decision (RBC transfusion OR EBL ≥500 mL; top-quartile fallback if <60 cases or <10% of eligible); record final choice and counts in `DATA_CARD.md`; never change after seeing results — **rule implemented and tested** (`cohort.assign_cohort_b`); **preliminary** real count against the 3,419 clinical-table-eligible cases: 654 (19.1%) via the primary rule, no fallback needed. Not yet final — must be re-run once vitals-based eligibility narrows the eligible set further.
- [ ] Accept: `cohort.parquet`; funnel documented; event-detector unit tests pass — **event-detector tests pass (10/10, toy series).** `cohort.parquet` itself is NOT final — only `data/interim/cohort_preliminary.parquet` exists (clinical-table criteria only, explicitly marked `is_final=False`). Full funnel + final cohort.parquet need the bulk download.

**P3 — Windows, labels, features** (target: 3–6 h, with P2)
- [ ] `features.py` (strictly causal), window labeling, exclusion rules
- [ ] Causality test; split-disjointness test
- [ ] Positive rates by cohort and horizon printed
- [ ] Accept: `windows.parquet`; causality unit test passes; leakage checklist (Section 8) reviewed

**P4 — Baselines, models, evaluation** (target: 6–10 h; hard deadline — if not done by hour 10, stop P5 and finish this first)
- [ ] Baselines B1–B4; logistic regression; HistGradientBoosting; calibration on validation
- [ ] Alarm logic with refractory period; operating-point selection at 1 FA/patient-hour (also 0.5, 2)
- [ ] Metrics with bootstrap CIs by case; logistic coefficients + scaling saved for the web "why" panel
- [ ] Model choice per Oct 24 decision: ship logistic unless boosted beats it on **validation only** by both (a) bootstrap-by-case AUPRC-difference 95% CI excluding zero, and (b) ≥5 pp more sensitivity at 1 FA/patient-hour
- [ ] Insufficient-data threshold finalized at 30% missing fraction; check it excludes ≤10% of validation windows and report the actual share
- [ ] Leakage checklist (Section 8) run and reported item by item
- [ ] Accept: `metrics.json` and plots regenerate with one command

**P5 — Hemorrhage simulator** (target: 8–11 h; filler during P4/P1 background jobs only, not true parallel work)
- [ ] `simulator.py`: ATLS-inspired curves, per-patient variability, three bleed profiles, blunted-response switch, transparent drift score
- [ ] Tests for monotonic trends
- [ ] `web/data/sim_curves.js` exported (`window.DRIFT_SIM`)
- [ ] Accept: monotonic trends shown; alert point and MAP<65 point printed for both blunted settings; SYNTHETIC wording defined

**P6a — Replay export** (target: 10–11 h)
- [ ] Four example types selected from TEST SET only (best, typical, miss, false alarm; 2 each if available; insufficient-data case if one exists), rules in `config.py` + `DATA_CARD.md`
- [ ] Excerpt export (40 min before → 10 min after, 30 s resolution); causal risk at 1-min stride
- [ ] `web/data/replay_cases.js`, `model_meta.js`, `proof.js` written as `.js` globals (not `.json`)
- [ ] Accept: causality check script passes (20 sampled timepoints, truncated-data match); schema validator passes; `web/data` size < 10 MB
- [ ] **Decision gate (Adjustment A4):** at least one miss and one false alarm present, or UI/docs say so and show closest examples

**P6b — Website, replay mode** (target: 11–16 h)
- [ ] `web/index.html`, `style.css`, `app.js` — static, no libraries, no build step, no network
- [ ] Two tabs, dark bedside-monitor look, controls bar, Drift status banner, scrolling chart, standard monitor strip, verdict strip, timeline bar
- [ ] Heart indicator pulses at current HR; `prefers-reduced-motion` respected
- [ ] `VitalsSource` interface (`ReplaySource`, `SimulatedSource`, documented `DeviceSource` per Oct 24 spec: comment block with method signatures, sample format, cadence, throwing stub, + one README limits line)
- [ ] Accept: every state reachable (alert, standard alarm, miss, false alarm, insufficient data); scrubbing backwards hides future items; space/arrow keys work

**P6c — Website, simulator mode** (target: 11–16 h)
- [ ] "Simulated bleed" mode using `window.DRIFT_SIM`; SYNTHETIC badge/banner
- [ ] Blood-lost slider, Play bleed, bleed-profile selector, blunted checkbox, Reset
- [ ] Transparent rule score labeled as such; verdict strip computed from data
- [ ] Accept: blunted toggle delays alert or shows "No warning before collapse in this setting"

**P6d — Drawer and polish** (target: 11–16 h)
- [ ] "Proof and method" drawer (Esc to close) reading only `window.DRIFT_PROOF` / `window.DRIFT_META`
- [ ] Manual UI QA checklist (PLAN.md Section 9A) run and fixed
- [ ] Accept: zero console errors, zero network requests; screenshots saved at 1440×900 and 1280×720

**Feature freeze: hour 18** (PLAN.md Section 10)

**P7 — Tests, documentation, submission** (target: 18–24 h)
- [ ] **Final test list (Oct 24 decision):** event detector, feature causality, split disjointness, replay-export causality — that's it unless time allows more
- [ ] Manual UI QA checklist complete (Section 9A)
- [ ] **Required docs:** short `README.md`, `LIMITATIONS.md`, Devpost text, video
- [ ] `DATA_CARD.md` and `MODEL_CARD.md` — one page each, generated from `metrics.json`, no hand-typed numbers
- [ ] Devpost text (problem, solution, diagram, honesty section, results table, synthetic disclosure, what's next, GitHub link) — **draft with placeholders around hour 10**, so this slot is just filling numbers + recording
- [ ] 2–3 min video recorded
- [ ] Accept: no number in Devpost/video that isn't in a generated file; submit with ≥ 2 h buffer
- [ ] **If slipping, cut in this order:** (1) boosted model, (2) horizon sweep, (3) insufficient-data example case, (4) `MODEL_CARD.md` as its own file (fold into README)

---

## c. Log

| Date/time | What was done | Result | Next |
|---|---|---|---|
| | | | |
