# EVENT MODE

Hackathon has started (2026-10-24). Pre-event restrictions removed.

Current git state: `git init` + remote attach to `Palak-Ai-2006/Drift` done. **No `git add` / `git commit` / `git push` until told otherwise** — files stay uncommitted, added later on explicit instruction.

---

## 0. One-paragraph summary

Trauma patients can bleed for a long time while blood pressure stays normal, because the body compensates (heart rate rises, pulse pressure narrows). Then pressure collapses suddenly. We build an early-warning engine that watches the *dynamics* of heart rate, blood pressure and pulse pressure and warns minutes before the collapse. The engine is a small, calibrated, interpretable model trained and evaluated on real surgical patients (VitalDB, Seoul National University Hospital) and compared against the standard low-pressure alarm. The demo is a single monitor-style web page with two modes: **(1) replay of a recorded real patient** and **(2) a simulated bleed**. In both, the Drift alert appears first and a "standard monitor" alarm fires later, and the gap is shown. Everything synthetic is labeled synthetic; everything real is labeled "surgical, not prehospital trauma."

**What we will and will not claim**
- WE CLAIM: on real intraoperative data, drift features give earlier warning than a threshold alarm at the same false-alarm rate (if the numbers show it).
- WE DO NOT CLAIM: that it works in prehospital trauma, that it detects hemorrhage specifically (the label is hypotension, enriched for high-blood-loss cases), that it is clinically validated, or that it is live. This is a research prototype.

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
