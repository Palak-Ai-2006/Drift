# HANDOFF — read this first in a new chat

Written 2026-10-24, updated same day after Phase 2 (option 3) to hand this project
off to a fresh Claude Code session. Paste this file (or just say "read
HANDOFF.md") at the start of the new chat. Everything below is accurate as of
right now; if things drift, PLAN.md + CLAUDE.md + ACTIONS.md are the sources of
truth (this file is a snapshot/index, not a new rule set).

---

## 1. What this project is

**Drift** — a hemorrhage early-warning engine for HackPSU Fall 2026 (24h, Oct 24
event date in the plan, solo builder, Claude Code). Full spec: [PLAN.md](PLAN.md).
One-paragraph summary and claims: top of [CLAUDE.md](CLAUDE.md).

## 2. What mode we're in right now (read CLAUDE.md for the authoritative version)

This is **pre-event prep**, not the actual 24h build yet. The rules have been
loosened step by step today as the user explicitly authorized each one:

1. Docs/reading only, no code — **original rule**.
2. → Code files (`.py`/`.js`/`.html`) **allowed** (Oct 24, user said so explicitly).
3. → Still **no git**: no `git init`, no commit (not even local-only), no remote,
   no push. **This restriction is still active right now.** Folder is confirmed
   NOT a git repo as of the last check.
4. → `pip install` / a local `.venv` **allowed** (Oct 24, user said so explicitly) —
   used to actually install and run the pipeline's dependencies.
5. → Small reference-table downloads (the VitalDB clinical case table, track
   names, clinical parameter dictionary) **allowed and done** — see `data/manual/`.
6. → The Phase 1 "5-case test download" of real per-case `.parquet` files
   **allowed and done** (Oct 24, user said so explicitly) — see `data/raw/`.
7. → **Bulk download (the real 300–500 case pipeline input) is still NOT
   approved.** Decision 1 (PLAN.md Section 1 / CLAUDE.md) reserves this for
   event start or explicit organizer sign-off. **Do not do a bulk download
   without asking the user first**, even though the 5-case test went fine.
8. → **"Option 3" (Oct 24):** when asked whether to start Phase 2 early too,
   the user chose a middle path instead of a blanket yes/no: write and test
   Phase 2's code (`cohort.py`, `preprocess.py`, `labels.py`) now, but only
   against synthetic/toy data — hold off running it against real bulk vitals
   until the event or organizer sign-off. **This is the model to default to
   for later phases too** if a similar "can we start X early" question comes
   up: writing + toy-testing logic is lower rule-risk than running it against
   real data at scale, and the user has shown they'll pick that split when
   offered it. Don't assume it automatically extends to Phase 3+ though —
   ask again the same way, the same way this was asked for Phase 2.

**Open and unresolved:** HackPSU Fall 2026's actual "must be created on site"
rule has never been confirmed with organizers. Writing code before the event
technically may violate that rule regardless of git status — this was discussed
at length with the user, who chose to proceed anyway, eyes open. See
`ACTIONS.md` section (a) for the organizer-question checklist item, still open.

**If starting a new chat:** don't assume today's permissions silently extend to
things not yet explicitly asked for (e.g., bulk downloads, git init). Ask the user
the same way this session did, especially for anything that touches git or
downloads more real case data.

## 3. Everything decided so far (the "Oct 24 Decisions")

These are layered into PLAN.md (as inline "Decision (Oct 24)" blocks) and
`src/drift/config.py` (as actual constants), not just chat history. The short
version:

1. **Cohort B** (high blood loss): RBC transfusion OR `intraop_ebl` ≥ 500 mL;
   falls back to top-quartile EBL if that's under 60 cases or under 10% of
   eligible cases. Locked before any model results exist.
2. **Model selection**: ship logistic regression unless boosted model beats it on
   **validation only** by both an AUPRC-CI bar and a +5pp sensitivity bar.
3. **Insufficient-data cutoff**: 30% missing fraction, finalized; check it
   excludes ≤10% of validation windows.
4. **Event definition**: MAP < 65 mmHg for 60s is the permanent headline. SBP<90
   and the 30s version are secondary, reported separately. One allowed fallback
   switch (if case/event counts are low), done once, before training, logged in
   DATA_CARD.md, never reversed.
5. **Phase 1 decision-gate tiers**: ≥300 cases & ≥100 events = proceed; 150–299 /
   60–99 = proceed with caveats; below that = pivot to simulator-first, no
   performance claims.
6. **No true multitasking**: Phase 5 (simulator) is filler during Phase 1/4
   background waits only. If Phase 4 isn't done by hour 10, stop Phase 5 and
   finish Phase 4.
7. **`DeviceSource`** counts as "documented" with a specific comment-block format
   (see PLAN.md Phase 6.2 adapter-seam section).
8. **Docs/test scope trimmed**: required = short README, LIMITATIONS.md, Devpost
   text, video. DATA_CARD.md/MODEL_CARD.md = one page each, generated. Tests =
   only event detector, feature causality, split disjointness, replay-export
   causality. Draft Devpost/video with placeholders by hour 10. Cut order if
   slipping: boosted model → horizon sweep → insufficient-data case → MODEL_CARD
   as separate file.
9. **Local-only git plan**: when git does start, no GitHub/push — matches "keep
   on this computer only" per the user. (Note: this contradicts ACTIONS.md's
   original "create a public GitHub repo, push" step under section b — **this
   conflict is still unresolved and flagged in ACTIONS.md**, not yet fixed.)

All of #1–8's actual numbers live in `src/drift/config.py` under the "Decided
constants for config.py (Oct 24)" section (also mirrored as PLAN.md Section 6B).

## 4. File-by-file: what exists and what it does right now

### Root docs
| File | What it is |
|---|---|
| [PLAN.md](PLAN.md) | The full build plan. Source of truth for scope/requirements. Has been edited today to splice in the Oct 24 decisions inline — don't re-ask about things already resolved there. |
| [CLAUDE.md](CLAUDE.md) | Working rules for Claude Code in this repo: PRE-EVENT MODE hard limits (see section 2 above) + Sections 0, 6A, 12 copied from PLAN.md. **A new session reads this automatically.** |
| [ACTIONS.md](ACTIONS.md) | The live checklist — before-event tasks, phase-by-phase at-event checklist (with real status checked off for Phase 0/1), and an empty log table. **Check this first to see exactly what's done vs. pending.** |
| [DATA_NOTES.md](DATA_NOTES.md) | VitalDB access facts, what's confirmed vs. UNVERIFIED, citations, and (now) the specifics of the reference-table downloads done 2026-10-24. |
| [DATA_CARD.md](DATA_CARD.md) | Stub that's being filled in as phases complete. Currently has real Phase 1 inventory counts (total/arterial-line/EBL-bucket) and an early (non-final) Cohort B signal. Phase 2 will add the real eligibility funnel. |
| [MODEL_CARD.md](MODEL_CARD.md) | Stub, one page, TODO markers for Phase 4 results. |
| [LIMITATIONS.md](LIMITATIONS.md) | Stub with the "what we don't claim" content already written; model-specific limitations TODO after Phase 4. |
| [README.md](README.md) | Stub pointing to PLAN.md/CLAUDE.md/ACTIONS.md; "how to run" sections TODO until Phase 7. |
| [DEVPOST_OUTLINE.md](DEVPOST_OUTLINE.md) | Draft Devpost text with placeholders for every number (pulled from `metrics.json`/`proof.js` later, never hand-typed). Ready to fill in during Phase 7. |
| [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md) | Timed 3-minute video script draft, same placeholder rule, plus a shot list. |
| [HANDOFF.md](HANDOFF.md) | This file. |

### Code (`src/drift/`)
| File | Status |
|---|---|
| `__init__.py` | Package docstring only. |
| `config.py` | **The important one.** Every constant for the whole project — thresholds, windows, horizons, seeds, colors, wording, the Oct 24 decisions. Read this before writing any other module; don't hardcode a number anywhere else that belongs here. |
| `vitaldb_io.py` | **Implemented and tested (Phase 1).** Loads/caches the case table and track list (cache-first from `data/manual/` or `data/raw/`), verifies column/track names against `config.py` (raises if anything's missing — never guesses), flags arterial-line cases, builds the inventory table, and has working (tested) functions to download a single case's numeric tracks and run the "test N cases" report. The actual bulk-download loop (300–500 cases) hasn't been run — see section 2. |
| `cohort.py` | **Implemented and tested (Phase 2, "option 3").** `clinical_table_eligibility()` + `clinical_eligibility_funnel()` run for real against the cached clinical table (age≥18 + arterial line → 3,419/6,388). `usable_monitored_minutes()` / `is_usable_monitoring_sufficient()` (the ≥60min-after-exclusion criterion) and `assign_cohort_b()` (the fixed Cohort B rule + top-quartile fallback) are implemented and toy-tested, with `assign_cohort_b` also run for real against the 3,419 proxy-eligible cases (654 cases, 19.1%, primary rule, no fallback needed — **preliminary, not final**, see DATA_CARD.md). `build_cohort_table()` assembles a `cohort_preliminary.parquet`, explicitly marked `attrs["is_final"] = False`. The real `cohort.parquet` (needs the vitals-based eligibility criterion at scale) still needs the bulk download. |
| `preprocess.py` | **Implemented and tested (Phase 2, "option 3").** `reject_artifacts()` (MAP/SBP/DBP/HR bounds + SBP>DBP rule) and `interpolate_short_gaps()` (gap measured bracket-to-bracket, not missing-sample count) both implemented and unit-tested on toy series. Not yet run against real downloaded case data (that's a trivial next step once wanted — the 5 real files in `data/raw/` could be run through this today without touching the bulk-download gate, if useful). |
| `labels.py` | **Implemented and tested (Phase 2, "option 3").** `detect_events()` (generic, config-driven) + `detect_primary_events()` / `detect_fallback_short_duration_events()` / `detect_fallback_sbp_events()` wrappers. Handles irregular sampling (elapsed-time based, not sample-count based) and treats NaN as breaking a run (never extends or fabricates an event). 10 toy-series tests, all passing — matches the plan's own "event-detector unit tests on toy series" acceptance line. Not yet run against real vitals. |
| `features.py` | **Stub only.** Phase 3: causal feature computation + window labeling. Not implemented. |
| `baselines.py` | **Stub only.** Phase 4: threshold baselines B1-B4. Not implemented. |
| `models.py` | **Stub only.** Phase 4: logistic + boosted model, calibration. Not implemented. |
| `alarms.py` | **Stub only.** Phase 4: alarm/refractory logic. Not implemented. |
| `metrics.py` | **Stub only.** Phase 4: evaluation metrics, bootstrap CIs, writes `artifacts/metrics.json`. Not implemented. |
| `simulator.py` | **Stub only.** Phase 5: ATLS-inspired hemorrhage simulator. Not implemented. |
| `replay.py` | **Stub only.** Phase 6.1: replay case selection + causal risk export to `web/data/*.js`. Not implemented. |

### Scripts (`scripts/`)
| File | Status |
|---|---|
| `README.md` | Lists the planned 01–07 numbered scripts (most not written yet). |
| `01_fetch.py` | **Working.** Runs Phase 1 steps 1–4 against the cached clinical table: loads data, verifies names, builds `data/interim/inventory.parquet`, prints accept-criteria counts. |
| `01b_test_download.py` | **Working, already run once.** Samples 5 arterial-line caseids deterministically (seed=42) and downloads/tests them via `vitaldb_io`. Produced `artifacts/phase1_download_test_report.csv`. Re-running it will re-download the same 5 cases (deterministic sample) unless the inventory changes. |
| `01c_plot_one_case.py` | **Working, already run once.** Plots case 6269's HR/MAP/SBP/DBP to `artifacts/phase1_case_6269_plot.png`. |
| `02_build_cohort.py` | **Working, already run once.** Runs the clinical-table-derivable portion of Phase 2 for real (eligibility funnel, preliminary Cohort B count), writes `data/interim/cohort_preliminary.parquet`. Explicitly NOT the final cohort — see `cohort.py` notes above. |
| `03_*` through `07_*` | Not written yet — next phases. |

### Tests (`tests/`)
| File | Status |
|---|---|
| `test_config.py` | 8 tests, all passing. Sanity-checks the config constants (split fractions, event definition, Cohort B rule, etc.) — not pipeline logic. |
| `test_vitaldb_io.py` | 10 tests, all passing, run against the real cached data (no mocks). Covers loading, name verification, arterial-line flagging, inventory building. |
| `test_cohort.py` | 13 tests, all passing. Toy-data tests for `usable_monitored_minutes`/`is_usable_monitoring_sufficient`/`assign_cohort_b`, plus integration tests against the real cached clinical table (reuses `data/manual/cases.csv`, no new downloads) for `clinical_table_eligibility`/`clinical_eligibility_funnel`/`build_cohort_table`. |
| `test_labels.py` | 10 tests, all passing, all on toy series (boundary cases, NaN-breaks-a-run, irregular sampling, multiple events, both fallback variants). |
| `test_preprocess.py` | 7 tests, all passing, all on toy series (artifact bounds, SBP≤DBP rule, gap interpolation with its bracket-distance semantics made explicit). |
| **Total: 48/48 passing.** Run with `source .venv/bin/activate && python -m pytest -v` from the repo root. |

### Data (`data/`)
| Path | Contents |
|---|---|
| `data/manual/` | Pre-approved small reference tables, downloaded 2026-10-24: `cases.csv` (6,388-row clinical table), `track_names.csv` (196 tracks), `clinical_parameters.csv` (column dictionary). These are the canonical source `vitaldb_io.py` reads from. |
| `data/raw/` | 5 downloaded-and-resampled case files from the Phase 1 step-5 test (`{caseid}_numeric_30s.parquet` for 6269, 757, 6293, 2911, 2349). Small (7–17 KB each — lean 4-track, 30s-resolution tables, not whole raw files). |
| `data/interim/` | `inventory.parquet` — the Phase 1 output, 6,388 rows (one per case in the clinical table), with arterial-line flag, duration, EBL, RBC, age, ASA, emergency flag. |
| `data/processed/` | Empty — Phase 3 output (`windows.parquet`) goes here. |
| All of `data/` is gitignored (`.gitignore`), so none of this is meant to be committed even once git starts — it's either re-derivable from the API or regenerated by scripts. |

### Artifacts (`artifacts/`)
| File | What it is |
|---|---|
| `phase1_download_test_report.csv` | Per-case size/time report from the 5-case test. |
| `phase1_case_6269_plot.png` | The Phase 1 accept-criterion plot (also sent to the user). |
| Phase 4+ will add `metrics.json` here — the single source of truth every other number (web demo, DATA_CARD, Devpost, video) must be read from, never hand-typed. |

### `web/`
Empty except `web/data/` folder. Nothing built yet — Phase 6.

### Environment
- `.venv/` — local virtualenv (gitignored), with `numpy`, `pandas`, `pyarrow`,
  `scikit-learn` 1.9.1, `scipy`, `matplotlib`, `vitaldb` 1.7.2, `joblib`,
  `pytest` 9.1.1, `requests` all installed. Activate with
  `source .venv/bin/activate` before running anything.
- `requirements.txt` — the package list above.

## 5. Immediate next step

**Phase 2's code is written and tested (see table above) — what's left of
Phase 2 is entirely blocked on real data, not on more code:**
- Running `cohort.usable_monitored_minutes` / `is_usable_monitoring_sufficient`
  at scale (needs real per-case vitals for every candidate case).
- Finalizing the real eligible-case count and the real Cohort B count (the
  654/3,419 preliminary number must be rechecked once the vitals-based filter
  narrows the eligible set).
- Finally answering the Section 6/10 decision-gate tiers (currently
  un-evaluatable — only clinical-table counts exist, not real eligible-case /
  event counts).
- Running `labels.py`'s event detector against real per-case vitals to get
  real event counts.

**All of the above needs the bulk download (300–500 cases), still not
approved** (see section 2, item 7). **Ask the user before running it.**

**What CAN still be done without the bulk download, following the "option 3"
pattern (section 2, item 8) — ask the user first, same as Phase 2 was asked:**
- Write and toy-test Phase 3 (`features.py` — causal feature computation,
  window labeling). The causality unit test the plan calls for doesn't need
  real bulk data either.
- Optionally: run `preprocess.py` / `labels.py` against the 5 real case files
  already in `data/raw/` as a richer-than-toy sanity check — this doesn't
  need a new bulk download, just reuses data already approved and downloaded.

## 6. Things a new session should NOT re-litigate

All of these were discussed and decided today — don't re-ask, just follow
`config.py` / PLAN.md's inline decisions:
- Cohort B definition and fallback.
- Model-selection criteria (logistic vs boosted).
- Insufficient-data threshold (30%).
- Event definition (MAP<65/60s primary, with its one-time fallback rule).
- Decision-gate tiers.
- Docs/test scope for Phase 7.
- That code files are allowed, packages are installed, and the 5-case test
  download already happened.
- That Phase 2's `cohort.py`/`preprocess.py`/`labels.py` are already written
  and toy-tested (48/48 tests passing) — don't rewrite them from scratch,
  extend/use them.

## 7. Things a new session SHOULD check with the user before acting

- Any **bulk download** (anything beyond the 5 already-downloaded test cases).
- **`git init` / any commit**, even local-only — still explicitly forbidden
  until the user says otherwise.
- The **HackPSU rules confirmation** — still unresolved; if the user says
  they've since confirmed the rules, update PLAN.md Section 1 / `ACTIONS.md`
  accordingly.
- The **GitHub vs. local-only conflict** in `ACTIONS.md` section (b) — it still
  says "create a public GitHub repo, push," which conflicts with the user's
  later "keep on this computer only" instruction. Resolve this explicitly with
  the user before the event-start git steps run.
