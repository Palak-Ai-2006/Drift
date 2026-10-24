# Devpost outline (draft — text only, no project code)

Written pre-event per PLAN.md Section 1 ("writing the Devpost outline... as text" is explicitly allowed before the event) and Phase 7 / Decision 9 ("draft the Devpost text... with placeholders around hour 10, so hours 18–22 only fill numbers").

**Rule for filling this in later: no number goes in here unless it's read out of a generated file (`metrics.json`, `proof.js`). Placeholders below are marked `[FROM metrics.json: ...]`.**

---

## Title
Drift — catching the vital-sign drift that happens while blood pressure still looks normal.

## Tagline / one-liner
"When a patient is bleeding, blood pressure is the last thing to move. We watch what moves first."

## The problem
- Hemorrhage is the leading cause of preventable trauma death (cite: pubmed.ncbi.nlm.nih.gov/36551134/).
- Traditional vital signs are insensitive to early blood loss because the body compensates — heart rate rises, pulse pressure narrows, and blood pressure holds until compensation fails, then collapses fast.
- Standard monitors alarm on low blood pressure itself — by the time that fires, the patient has already decompensated.

## The solution
- An early-warning engine that watches the *dynamics* of heart rate, blood pressure, and pulse pressure — not just their current values — and estimates risk of an imminent low-pressure event, computed causally (using only data available up to that moment).
- Trained and calibrated on real surgical patients (VitalDB, Seoul National University Hospital, 6,388 cases, CC BY 4.0).
- Compared head-to-head against the standard low-pressure alarm at matched false-alarm rates.
- A static, offline, two-mode web demo: replay of a real recorded patient, and a physiology-grounded simulated bleed.

## One diagram
[Pipeline diagram from PLAN.md Section 4 — VitalDB → cohort → features/labels → model → calibration → alarm logic → replay export → web demo. Build this once Phase 4–6 numbers exist; don't hand-draw numbers into it now.]

## Data and honesty section
- Real data: VitalDB, surgical (non-cardiac), Seoul National University Hospital 2016–2017. **Surgical, not prehospital trauma** — the label is intraoperative low blood pressure (MAP < 65 mmHg sustained ≥ 60s), enriched for high-blood-loss/transfused cases, not a hemorrhage-specific label.
- Synthetic data: an ATLS-inspired simulator, always labeled SYNTHETIC, used only to illustrate the physiology and the interface — never used to compute the headline claim.
- Splits by patient case; test set evaluated once; no tuning on the test set.
- Replay risk scores are computed causally — verified by a script that recomputes risk from truncated data and confirms it matches what's shown.

## What we claim / do not claim
- **WE CLAIM:** [FROM metrics.json: on the real intraoperative test set, Drift gives earlier warning than the standard low-pressure alarm at the same false-alarm rate — state the actual median lead-time gap and sensitivity numbers once they exist. If the numbers don't support this, say so plainly instead.]
- **WE DO NOT CLAIM:** that it works in prehospital trauma, that it detects hemorrhage specifically, that it is clinically validated, or that it is live. Research prototype only.

## Results table
[FROM proof.js — sensitivity at 0.5 / 1 / 2 false alarms per patient-hour, Drift vs. baselines B1–B4; median lead time; Brier score; cohort counts (Cohort A / Cohort B). Table is generated, not hand-typed.]

## What is synthetic
Everything under "Simulated bleed" mode: ATLS-inspired curves (Class I–IV blood loss), per-patient variability, three bleed profiles, a blunted heart-rate-response toggle. Labeled SYNTHETIC throughout; drift score there is a transparent rule, not the trained model.

## What's next
- External validation on a second, credentialed dataset (e.g. INSPIRE, HiRID — named as candidates, not yet accessed).
- Prehospital-cadence retraining (intermittent cuff readings, not continuous arterial lines).
- Trauma-specific data, if it becomes available.
- Clinician input on alarm wording, placement, and thresholds before any real device integration.
- See PLAN.md Section 15 for the full honest deployment discussion (what a device integration would and wouldn't require).

## Links
- GitHub: [added once the repo exists — event-start only, kept local-only per current decision; update this line if that changes]
- Video: [2–3 min, linked once recorded]

## Team
Palak (solo), built with Claude Code.
