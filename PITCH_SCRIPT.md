# Live demo pitch script (about 4 minutes)

Keep this open beside the demo. Each step says **what to click** and **what to say**. The only numbers to quote are in the generated block below (filled by `scripts/11_docs_numbers.py`) or on screen. For the simulated profiles, read the minutes off the Timing panel rather than from memory.

<!-- NUMBERS:VIDEO:START -->
- Replay, best example: the early alert fires 14.9 min before the standard alarm.
- Real test set: 57.4% of events caught, median 4.3 min early, 0.97 false alarms per patient-hour; a plain MAP cutoff does about the same (60.1%, 4.4 min).
- Simulation: 96.1% of collapses caught at 0.63 false alarms/hr, median 7.9 min warning vs 3.4 min for a MAP cutoff and 5.0 min for a standard monitor.
<!-- NUMBERS:VIDEO:END -->

**Before you start:** open `web/index.html` full-screen. Have these deep links ready in other tabs so you can jump if time runs short:
- `index.html#case=0&t=1300` (replay, just before the alert)
- `index.html#mode=sim&profile=sudden`
- `index.html#mode=sim&profile=slow_ooze`

---

## 1. The problem (about 30 s) · page open on Replay, nothing playing

**Point at:** the "Standard monitor" strip.

**Say:**
> "When someone is bleeding internally, blood pressure is the *last* thing to move. The body hides the blood loss: the heart speeds up and the pulse narrows, and blood pressure looks fine until the body runs out of tricks. Then it collapses fast.
> Every bedside monitor in an ER or operating room alarms on fixed limits, like 'blood pressure below 65'. So the alarm fires at the collapse, not before it. We wanted to see how much earlier you could warn by watching *how the numbers move*, not just where they are."

---

## 2. A real recorded patient (about 60 s) · Replay tab, Best example 1, press **Play** (90×)

**Point at:** the "Recorded patient, sped up 90×. Not live." chip, then the teal "REAL DATA, SURGICAL" badge.
> "This is a real surgical patient from VitalDB, an open dataset from Seoul National University Hospital, replayed at 90× speed. It's recorded, not live, and the page says so everywhere."

**Point at:** the two charts.
> "Top chart: blood pressure (MAP, in red) and pulse pressure (in blue). The dashed red line is where the standard alarm goes off. Bottom chart: heart rate. Big numbers on the right are what a nurse would see."

**When the amber banner appears, pause (space bar).**
> "Here's our **Drift alert**. Look at the Timing panel on the right: it logs exactly when the alert fired. The standard monitor below still says 'not triggered'. Blood pressure hasn't crossed its line yet."

**Press Play again until the red standard alarm fires, then pause.**
> "*Now* the standard alarm fires. Timing panel: **Time saved**." Read the number on screen.
> "The page never shows anything from the future. The charts, the alert, the timing and the verdict only appear once playback reaches them. We test that automatically, down to the pixels on the chart."

**Point at:** the case picker.
> "We also show our failures: misses and false alarms are in this list, picked by fixed rules, not by hand. These are selected examples, not average performance."

---

## 3. Honesty moment (about 30 s) · click the **(i)** next to "Risk of low pressure"

**Say:**
> "Here's the most important thing we found. On real surgical data, the heart-rate and pulse-pressure trends **did not** beat plain blood pressure. We tested that three different ways, with rules written down before we looked, and on a fresh set of patients nobody had touched. So on real data, this alert is honestly a smart blood-pressure alarm, and this tooltip says so.
> Why? In surgery, most blood-pressure drops are caused by anesthesia, not bleeding, and nobody records when bleeding starts. So you can't tell from this data whether the bleeding signal is there."
Then quote the real-data numbers from the block.

---

## 4. Why we built a simulator (about 60 s) · click **Simulated bleed**

**Point at:** the purple "SYNTHETIC PATIENT, NOT REAL DATA" badge.
> "To test the idea fairly, we needed patients where we *know* when the bleeding started. So we took calm stretches of real patients' recordings, with their real heart-rate wobble and sensor noise, and injected a simulated bleed on top. Everything here is labeled synthetic."

**Drag the "Blood lost" slider slowly from 0 to about 20%.**
> "Watch: heart rate climbs and the pulse narrows, while blood pressure barely moves. The Drift alert fires here. That's the hidden phase a normal monitor can't see."

**Keep dragging to the end.**
> "And the standard alarm only fires down here." Read the **Warning margin** from the Timing panel.

**Change Bleed profile to "Sudden", then to "Slow ooze".**
> "Same blood loss, different speeds. A sudden bleed collapses in minutes; a slow ooze takes much longer. Look at the Timing panel: the warning shrinks for a fast bleed. That's exactly why minutes matter more than percentages."

**Tick "Blunted heart-rate response".**
> "Older patients and people on beta-blockers can't raise their heart rate much. The alert comes later, and we show that honestly. This alarm is weakest for exactly those patients."

**Say the simulation numbers** from the block.
> "On those simulated bleeds, the trend-based model warned about twice as early as a blood-pressure cutoff, with fewer false alarms. It did *not* catch more collapses, and we say that too."

---

## 5. Trust (about 20 s) · open **Proof and method** (bottom right)

> "Every number on this page is generated from our results files, never typed by hand. The simulator was frozen before training, and the test set could only be run once; the code refuses a second run. Both tables are here, real and simulated, side by side."

---

## 6. Close (about 20 s)

> "What we built: a way to test early-warning ideas honestly before you have labeled data, and a monitor-style demo that shows the result. What we learned: in simulation, watching the trend buys real minutes. On real surgical data, the evidence isn't there yet. The next step is trauma data where bleeding is actually labeled, and retraining on the cuff readings ambulances and ERs actually use. Thank you."

---

## If a judge asks…

| Question | Honest answer |
|---|---|
| "Does it work on real trauma patients?" | "We don't know yet. Our real data is surgical. That's the next step, and it needs credentialed trauma data." |
| "So the real-data alert is just a blood-pressure threshold?" | "Yes. We tested whether the trends add value on real data, three ways, and they didn't. We label it that way instead of overselling." |
| "Isn't the simulation circular?" | "Partly, yes. It assumes textbook physiology, so it shows the method works *if* real bleeding looks like that. It can't prove that it does. That's why we report both results side by side." |
| "What about false alarms?" | Quote the false-alarm numbers from the block, then point at the False alarm examples in the case picker. |
| "What machine would this run on?" | "It's software on top of an existing bedside monitor (Philips, GE, Mindray, or a ZOLL in ambulances). It reads the numbers the monitor already measures. There's a placeholder in the code for a live feed." |
| "Why 90× speed?" | "So a 50-minute recording fits in under a minute. The chip on screen always states the speed." |
| "Is it accurate?" | "Accuracy is misleading here: most of the time nobody is crashing, so 'never alarm' scores high. We report catch rate, false alarms per hour, and minutes of warning instead." |
