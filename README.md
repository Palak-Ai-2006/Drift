# Drift

**When a patient is bleeding, blood pressure is the last thing to move. Drift watches what moves first.**

Research prototype · not for clinical use · no alert does not mean safe.

## What this is

Bleeding patients can look stable for a long time: the heart speeds up and the gap between the top and bottom blood-pressure numbers (pulse pressure) narrows, while blood pressure itself holds. Then pressure collapses. Drift is an early-warning engine that watches those trends and warns before the collapse, compared against the standard low-pressure alarm.

It has two parts:
- **A model trained and tested on real surgical patients** (VitalDB, Seoul National University Hospital), plus a semi-synthetic test bed: real patient recordings with simulated bleeds injected on top, so the cause of each collapse is known.
- **A static, offline, two-mode web demo:** a sped-up replay of a recorded patient, and a simulated bleed you can drive with a slider.

## Results

<!-- NUMBERS:RESULTS:START -->
### Real surgical data (VitalDB)
| Method (real surgical data, test set) | Sensitivity | Median lead | False alarms / patient-hour |
|---|---|---|---|
| B1 (standard alarm, MAP<65/60s) | 100.0% | 0.0 min | 0.00 |
| B2 (tuned early-MAP threshold) | 60.1% | 4.4 min | 1.15 |
| Drift alert (shipped model, MAP only) | 57.4% | 4.3 min | 0.97 |
| Drift, fresh never-touched holdout (175 cases) | 52.5% | 5.2 min | 0.77 |

Calibration (shipped model, test set): Brier 0.103, AUROC 0.705.

### Simulation (real baselines + injected bleeds; synthetic)
| Tier (simulation) | Bleeds that collapsed | Sensitivity [95% CI] | False alarms / hr | Lead: model | Lead: MAP cutoff | Lead: standard monitor |
|---|---|---|---|---|---|---|
| T1 textbook | 85 | 97.6% [94.3%–100.0%] | 0.65 | 6.7 min | 3.4 min | 5.3 min |
| T2 realistic | 67 | 95.5% [90.2%–100.0%] | 0.66 | 8.3 min | 3.3 min | 7.1 min |
| T3 blunted | 36 | 94.4% [84.8%–100.0%] | 0.48 | 7.2 min | 4.0 min | 1.0 min |
| T4 confounded | 69 | 95.7% [89.6%–100.0%] | 0.74 | 9.2 min | 3.6 min | 5.9 min |
| All tiers | 257 | 96.1% [93.0%–98.9%] | 0.63 | 7.9 min | 3.4 min | 5.0 min |

Pre-registered target (≥ 95.0% at ≤ 1 false alarm/hr on T1 and T2): T1 97.6% at 0.65/hr, T2 95.5% at 0.66/hr, both met on the point estimate (lower CI bounds are below the target). Unseen bleed settings, all tiers: 95.4% at 0.54/hr.
<!-- NUMBERS:RESULTS:END -->

**How to read this.**
- **Real surgical data:** heart-rate and pulse-pressure trends did not beat blood pressure alone, under a pre-registered protocol across three rounds of testing. The demo calls its alert a *Drift alert*, but on real data it is a MAP-only model, and the page says so. This matches the published debate over whether commercial hypotension predictors add anything beyond MAP itself.
- **Simulation, where bleeding causes textbook compensation:** the trend-based model warns about twice as early as a MAP cutoff. It does not catch more collapses.
- **What the gap means:** the difference between these two results is the argument for testing on trauma data with real bleeding labels. Details: [MODEL_CARD.md](MODEL_CARD.md), [SYNTHETIC_PLAN.md](SYNTHETIC_PLAN.md), [LIMITATIONS.md](LIMITATIONS.md).

## How to run the demo

Open `web/index.html` in Chrome or Safari (double-click works). It needs no server, no internet and no install.

- **Keyboard:** space plays and pauses, the arrow keys scrub, Esc closes the Proof drawer.
- **Deep links for presenting:** `web/index.html#case=0&t=1700` jumps to a replay moment; `web/index.html#mode=sim&f=0.3&blunted=1` jumps to a simulated bleed.

## How to reproduce the pipeline

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```
```bash
.venv/bin/python -m pytest -q
```
```bash
bash scripts/run_pipeline.sh
```

The pipeline script downloads the VitalDB cases on its first run (cached afterwards) and rebuilds every artifact, web data file and generated number in the docs, in order. All seeds are fixed. The Round 4 test set is evaluated only once and the script won't re-run it.

## Repo layout

- `src/drift/`: the pipeline. `config.py` holds every constant; `semisynth.py` is the Round 4 bleed-injection generator.
- `scripts/`: numbered pipeline steps (`01`–`11`) and `run_pipeline.sh`.
- `web/`: the static demo (`index.html`, `style.css`, `app.js`, `data/*.js`, all generated).
- `tests/`: the pytest suite.
- `artifacts/`: small committed outputs: metrics JSON, plots, screenshots.
- `data/`: VitalDB data (gitignored). `data/manual/` holds small reference tables.

Every number in the web demo and in the marked blocks of this README, [DEVPOST.md](DEVPOST.md) and [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md) is generated from `artifacts/` by the scripts, never typed by hand.

## Data and license

VitalDB (Lee HC et al., *Scientific Data* 2022), used under CC BY 4.0. The data is surgical (intraoperative), not prehospital trauma, so the real-data label is low blood pressure, not bleeding specifically. See [DATA_CARD.md](DATA_CARD.md).

## Limitations

See [LIMITATIONS.md](LIMITATIONS.md).
