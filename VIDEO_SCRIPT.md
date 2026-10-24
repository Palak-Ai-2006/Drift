# 3-minute video script (draft — text only, no project code)

Written pre-event per PLAN.md Section 1 and Phase 7 ("Video script (3 min): hook → problem → replay with alert → standard alarm later → simulator (blunted toggle) → numbers vs baselines → limits and next steps"). Draft with placeholders now (Decision 9); fill in real numbers and record around hour 18–22.

**No number is spoken or shown on screen unless it comes from a generated file (`metrics.json` / `proof.js`).**

---

### 0:00–0:15 — Hook
*(on camera or voiceover over a still of a flat blood-pressure line)*

"When a patient is bleeding, blood pressure is the last thing to move. The body compensates — heart rate climbs, pulse pressure narrows — until it suddenly can't anymore. We built something that watches what moves first."

### 0:15–0:40 — Problem
*(show the rubric-mapping framing, or just talk over a simple slide)*

"Hemorrhage is the leading cause of preventable trauma death. Standard monitors alarm when blood pressure itself drops — but by then the patient has already decompensated. We wanted an alert that fires during the compensation phase, while pressure still looks normal."

### 0:40–1:30 — Replay demo (the core proof)
*(screen recording of `web/index.html`, Replay tab, "Best example" case, playing)*

- Point out the banner: "Recorded patient, sped up 30×. Not live."
- Let it play until the Drift alert fires (amber): "Here — heart rate's climbing, pulse pressure is narrowing. Our alert fires here."
- Let playback continue until the standard alarm fires (red, MAP < 65): "The standard low-pressure alarm doesn't fire until here."
- Point at the verdict strip / timeline bar: "[FROM replay_cases.js: Drift alerted ___ minutes before the standard alarm.]"

### 1:30–2:00 — Simulator demo (physiology, made legible)
*(screen recording of the Simulated bleed tab)*

- Drag the "Blood lost" slider or hit Play bleed.
- "This is synthetic — labeled SYNTHETIC throughout, built from standard ATLS blood-loss staging, just to make the physiology visible."
- Toggle "Blunted heart-rate response": "This is what it looks like in a patient on beta-blockers, or an older patient — the compensation itself is blunted, so the warning comes later, or sometimes not at all. We show that honestly instead of hiding it."

### 2:00–2:30 — Numbers vs. baselines
*(show the Proof and method drawer, or a simple results slide generated from `proof.js`)*

"Across the held-out test set — patients the model never saw during training — at the same false-alarm rate as the standard alarm: [FROM proof.js: sensitivity numbers, median lead time, Brier score]. We also show our misses and our false alarms in the case picker — not just the wins."

### 2:30–2:50 — Limits and honesty
"This is surgical data, not prehospital trauma — a real trauma version would need retraining on intermittent, ambulance-cadence vitals. It's not clinically validated, and it's not a device. It's a research prototype."

### 2:50–3:00 — Close
"The engine itself is small enough to run on a phone with no internet connection. The interface is built so a real device feed could someday replace this replay without a redesign. Honest next steps: trauma data, prehospital cadence, clinician input. Thanks for watching."

---

## Shot list (prep before recording)
- [ ] Screen recording, Replay tab, best-example case, full play-through (speed 30×)
- [ ] Screen recording, Replay tab, miss or false-alarm case (optional, if time allows in the longer form / Devpost write-up)
- [ ] Screen recording, Simulated bleed tab, slider drag + blunted toggle
- [ ] Screen recording, Proof and method drawer open
- [ ] Screenshots at 1440×900 and 1280×720 (Phase 6 acceptance criteria — reuse these for Devpost images)
