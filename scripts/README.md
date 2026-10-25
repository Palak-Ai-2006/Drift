# scripts/

Numbered pipeline steps, each a thin wrapper around `src/drift/*`. `run_pipeline.sh` runs them all in order.

| Step | What it does |
|---|---|
| `01_fetch.py` | Case table, track names, inventory (`01b`/`01c`: 5-case download test, one plotted case) |
| `02_build_cohort.py`, `02b_bulk_download.py`, `02c_finalize_cohort.py` | Eligibility, Cohort B, bulk vitals download, events |
| `03_build_windows.py` | Causal features and labels → `data/processed/windows.parquet` |
| `04_train_eval.py` | Phase 4 baselines, models, calibration, test metrics → `artifacts/metrics.json` |
| `04b`–`04g` | Model iteration rounds and experiments (each pre-registered in ACTIONS.md) |
| `04h`, `04i` | Fresh 175-case holdout: download, evaluate once |
| `05_simulate.py` | Phase 5 simulator curves → `web/data/sim_curves.js` |
| `06_export_replay.py`, `06b_replay_causality_check.py` | Replay examples → `web/data/replay_cases.js`, `model_meta.js`; causality check |
| `07_export_web_data.py` | Proof drawer data → `web/data/proof.js` |
| `08_semisynth_examples.py` | Round 4 example traces (before the generator freeze) |
| `09_round4_train_eval.py` | Round 4 train/val (`--stage dev`) and one-time test (`--stage test`) → `artifacts/metrics_synth.json` |
| `10_round4_report.py` | Round 4 results sections in MODEL_CARD.md and SYNTHETIC_PLAN.md |
| `11_docs_numbers.py` | Generated number blocks in README.md, DEVPOST.md, VIDEO_SCRIPT.md |
