# scripts/

Numbered pipeline scripts (PLAN.md Section 4.1), each a thin CLI wrapper around
`src/drift/*`. Not yet written (Phase 0 scaffold only) — created as each phase
is implemented, in order:

- `01_fetch.py` — Phase 1: fetch/cache the VitalDB case table, track list, and
  candidate-case numeric tracks.
- `02_build_cohort.py` — Phase 2: cohort assignment, exclusion funnel, event
  detection.
- `03_build_windows.py` — Phase 3: window labeling and feature export.
- `04_train_eval.py` — Phase 4: baselines, models, calibration, metrics.
- `05_simulate.py` — Phase 5: hemorrhage simulator curves export.
- `06_export_replay.py` — Phase 6.1: replay case selection and causal risk export.
- `07_export_web_data.py` — Phase 6.1: writes `web/data/*.js` from
  `artifacts/metrics.json` and the replay export.
