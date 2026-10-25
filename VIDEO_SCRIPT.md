# 3-minute video script

Every number you say comes from the generated block below (filled by `scripts/11_docs_numbers.py`). Don't say a number that isn't in it.

<!-- NUMBERS:VIDEO:START -->
- Replay, best example: the early alert fires 14.9 min before the standard alarm.
- Real test set: 57.4% of events caught, median 4.3 min early, 0.97 false alarms per patient-hour; a plain MAP cutoff does about the same (60.1%, 4.4 min).
- Simulation: 96.1% of collapses caught at 0.63 false alarms/hr, median 7.9 min warning vs 3.4 min for a MAP cutoff and 5.0 min for a standard monitor.
<!-- NUMBERS:VIDEO:END -->

---

### 0:00–0:15 · Hook
*(Over the replay chart, paused on a flat blood-pressure line.)*
"When someone is bleeding, blood pressure is the last thing to move. The heart speeds up and the pulse narrows while pressure looks fine. Then it collapses. We wanted to watch what moves first."

### 0:15–0:40 · Problem
"Bleeding is the leading cause of preventable death after trauma. Monitors alarm when blood pressure itself drops, which is the collapse, not the warning. And real hospital data can't tell you which pressure drops were bleeding, because nobody records when bleeding started."

### 0:40–1:20 · Replay of a real patient
*(Replay tab, Best example 1, 90× (the default). Open with `web/index.html#case=0&t=1400` and press space.)*
- Point at the banner: "This is a recorded surgical patient, sped up. Not live."
- When the amber banner appears: "Our early alert fires here."
- When the standard alarm turns red: "The standard alarm fires here." Read the verdict line.
- Be honest: "On real surgical data, this early alert is essentially a smart blood-pressure threshold. Heart-rate trends didn't add anything, and we tested that three ways."

### 1:20–2:00 · Why we built a simulator, and what it showed
*(Simulated bleed tab: drag the slider, then tick "Blunted".)*
"Real surgical pressure drops are mostly anesthesia, not bleeding. So we took real patients' recordings and injected simulated bleeds, so we know exactly when each bleed starts. It's labeled synthetic everywhere."
- Drag the slider: heart rate climbs and pulse pressure narrows while MAP holds, then the alert fires well before the standard alarm.
- Tick blunted: "In older patients or patients on beta-blockers, the warning comes later."
- Say the simulation numbers from the block.

### 2:00–2:30 · Proof and method
*(Open the drawer.)* "Every number here is generated from the results files. We show misses and false alarms in the case picker, not just wins. The simulator was frozen before training, and the test set was used once."

### 2:30–2:50 · Limits
"This is surgical data, not trauma. The simulation assumes textbook physiology, and real trauma patients don't always follow it. It isn't validated, and it isn't a device."

### 2:50–3:00 · Close
"The gap between our real and simulated results is exactly what to test next: trauma data with real bleeding labels. Thanks for watching."

---

## Shot list
- [ ] Replay: Best example 1, full play-through at 90×
- [ ] Replay: Miss or False alarm example (optional)
- [ ] Simulated bleed: slider drag, then blunted toggle
- [ ] Proof drawer, scrolled through both tables
- [ ] Stills: already in `artifacts/web_screenshots/`
