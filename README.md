# Drift

Early warning for hidden bleeding — catching the vital-sign drift that happens while blood pressure still looks normal.

**Status: pre-event scaffold (Phase 0).** This README is a stub; the full version (what/why/how to run, pipeline reproduction in ≤5 commands) is written in Phase 7, from real numbers in `artifacts/metrics.json`.

See [PLAN.md](PLAN.md) for the full build plan, [CLAUDE.md](CLAUDE.md) for the working rules, and [ACTIONS.md](ACTIONS.md) for the live checklist.

## What this is

A small, calibrated, interpretable model that watches the dynamics of heart rate, blood pressure, and pulse pressure in surgical patients (VitalDB, Seoul National University Hospital) and compares its warning time against a standard low-pressure alarm. The demo is a static, offline, two-mode web page: a replay of a recorded real patient, and a physiology-grounded simulated bleed.

**What we claim / do not claim:** see PLAN.md Section 0 / CLAUDE.md.

## Repo layout

See PLAN.md Section 4.1. Briefly:
- `src/drift/` — the pipeline (`config.py` holds every constant)
- `scripts/` — numbered pipeline scripts (01_fetch.py ... 07_export_web_data.py)
- `web/` — the static demo (`index.html`, `style.css`, `app.js`, `data/*.js`)
- `tests/` — pytest suite
- `data/` — raw/interim/processed data (gitignored; `data/manual/` holds small pre-approved reference tables)
- `artifacts/` — small committed outputs (`metrics.json`, plots)

## How to run (filled in once the pipeline exists)

TODO Phase 7.

## How to reproduce the pipeline (filled in once the pipeline exists)

TODO Phase 7.

## Limitations

See [LIMITATIONS.md](LIMITATIONS.md).
