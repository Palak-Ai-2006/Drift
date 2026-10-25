#!/usr/bin/env bash
# Rebuild everything from VitalDB in order. Downloads ~500 + 175 cases on
# the first run (cached under data/raw/ afterwards). Every step is
# deterministic (fixed seeds), so a re-run reproduces the committed artifacts.
# The Round 4 test stage runs only if it has never run: it refuses a second
# evaluation by design (artifacts/round4_test_evaluated.json).
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python

$PY scripts/01_fetch.py                         # case table, track names, inventory
$PY scripts/02_build_cohort.py                  # clinical eligibility, Cohort B
$PY scripts/02b_bulk_download.py                # numeric vitals for the selected sample
$PY scripts/02c_finalize_cohort.py              # vitals-based eligibility, events
$PY scripts/03_build_windows.py                 # causal features + labels
$PY scripts/04_train_eval.py                    # Phase 4 original model + baselines
$PY scripts/04b_model_iteration.py              # v2 model selection (CV)
$PY scripts/04c_v2_diagnostics.py
$PY scripts/04d_event_aligned_traces.py
$PY scripts/04e_bleeding_label_experiment.py    # Experiment 2
$PY scripts/04f_round3_residual_interaction.py  # round 3
$PY scripts/04g_round3_secondary_shock_index.py
$PY scripts/04h_fresh_holdout_download.py       # 175-case clean holdout
$PY scripts/04i_fresh_holdout_eval.py
$PY scripts/05_simulate.py                      # web/data/sim_curves.js
$PY scripts/06_export_replay.py                 # web/data/replay_cases.js, model_meta.js
$PY scripts/06b_replay_causality_check.py
$PY scripts/08_semisynth_examples.py            # Round 4 example plots
$PY scripts/09_round4_train_eval.py --stage dev
if [ -f artifacts/round4_test_evaluated.json ]; then
  echo "Round 4 test set already evaluated once -- keeping artifacts/metrics_synth.json."
else
  $PY scripts/09_round4_train_eval.py --stage test
fi
$PY scripts/10_round4_report.py                 # results sections in MODEL_CARD.md, SYNTHETIC_PLAN.md
$PY scripts/07_export_web_data.py               # web/data/proof.js
$PY scripts/11_docs_numbers.py                  # numbers in README.md, DEVPOST.md, VIDEO_SCRIPT.md
