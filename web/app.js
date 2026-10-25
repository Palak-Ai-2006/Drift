/* Drift web demo (PLAN.md Phase 6.2). Static, no framework, no network.
 * Every number shown comes from the generated data files
 * (window.DRIFT_CASES / DRIFT_SIM / DRIFT_META / DRIFT_PROOF).
 * Causality (Adjustment A3): replay views reveal only samples at or before
 * the current playback time. */
(function () {
  "use strict";

  const CASES = window.DRIFT_CASES || [];
  const SIM = window.DRIFT_SIM;
  const META = window.DRIFT_META;
  const PROOF = window.DRIFT_PROOF;
  const W = META.wording;
  const HORIZON_S = META.horizon_min * 60;
  const REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const MAX_PULSE_HZ = 3; // on-screen heartbeat never faster than this
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const $ = (id) => document.getElementById(id);

  // -------------------------------------------------------------------------
  // Adapter seam: the page only talks to a VitalsSource.
  // -------------------------------------------------------------------------
  class VitalsSource {
    start() {}
    pause() {}
    seek(_pos) {}
    onSample(cb) { this._cb = cb; }
    _emit(sample) { if (this._cb) this._cb(sample); }
  }

  /** Replays a recorded excerpt at `speed`x. Position = seconds into the excerpt. */
  class ReplaySource extends VitalsSource {
    constructor(caseData, getSpeed) {
      super();
      this.c = caseData;
      this.getSpeed = getSpeed;
      this.duration = caseData.t[caseData.t.length - 1] - caseData.t[0];
      this.pos = 0;
      this.playing = false;
      this._last = null;
      this._tick = this._tick.bind(this);
    }
    start() {
      if (this.pos >= this.duration) this.pos = 0;
      this.playing = true;
      this._last = null;
      requestAnimationFrame(this._tick);
    }
    pause() { this.playing = false; }
    seek(pos) { this.pos = Math.max(0, Math.min(this.duration, pos)); this._emit(this.sample()); }
    _tick(now) {
      if (!this.playing) return;
      if (this._last !== null) this.pos += ((now - this._last) / 1000) * this.getSpeed();
      this._last = now;
      if (this.pos >= this.duration) { this.pos = this.duration; this.playing = false; }
      this._emit(this.sample());
      if (this.playing) requestAnimationFrame(this._tick);
    }
    /** Latest recorded sample at or before the current position -- never later. */
    sample() {
      const c = this.c, tAbs = c.t[0] + this.pos;
      let i = 0;
      while (i + 1 < c.t.length && c.t[i + 1] <= tAbs) i++;
      return { pos: this.pos, tAbs, i, hr: c.hr[i], sbp: c.sbp[i], dbp: c.dbp[i], map: c.map[i], pp: c.pp[i], si: c.si[i], missing: c.missing[i] };
    }
  }

  /** Walks the simulator curves. Position = blood-volume fraction lost. */
  class SimulatedSource extends VitalsSource {
    constructor(curves) {
      super();
      this.curves = curves;
      this.fMax = curves.meta.f_max;
      this.pos = 0;
      this.blunted = false;
      this.durationS = 60;
      this.playing = false;
      this._last = null;
      this._tick = this._tick.bind(this);
    }
    start() {
      if (this.pos >= this.fMax) this.pos = 0;
      this.playing = true;
      this._last = null;
      requestAnimationFrame(this._tick);
    }
    pause() { this.playing = false; }
    seek(f) { this.pos = Math.max(0, Math.min(this.fMax, f)); this._emit(this.sample()); }
    _tick(now) {
      if (!this.playing) return;
      if (this._last !== null) this.pos += ((now - this._last) / 1000) * (this.fMax / this.durationS);
      this._last = now;
      if (this.pos >= this.fMax) { this.pos = this.fMax; this.playing = false; }
      this._emit(this.sample());
      if (this.playing) requestAnimationFrame(this._tick);
    }
    series() { return this.blunted ? this.curves.blunted_true : this.curves.blunted_false; }
    sample() {
      const f = this.curves.f, s = this.series();
      let i = 0;
      while (i + 1 < f.length && f[i + 1] <= this.pos + 1e-9) i++;
      return { pos: this.pos, i, hr: s.hr[i], sbp: s.sbp[i], dbp: s.dbp[i], map: s.map[i], pp: s.pp[i], si: s.hr[i] / s.sbp[i] };
    }
  }

  /**
   * DeviceSource -- documented, NOT implemented (PLAN.md 6.2 decision).
   * A future live feed from a bedside monitor would implement:
   *   start()            begin streaming
   *   pause()            stop emitting (device keeps recording)
   *   seek(t)            not supported for live data; throws
   *   onSample(cb)       cb({ timestamp, hr, sbp, dbp, map, quality })
   * Sample format: timestamp in seconds; hr in bpm; sbp/dbp/map in mmHg;
   * quality = "good" | "artifact" | "missing". Cadence: one sample every
   * 30 s (the numeric resolution the model was trained on).
   */
  class DeviceSource extends VitalsSource {
    start() { throw new Error("DeviceSource not implemented"); }
  }
  void DeviceSource;

  // -------------------------------------------------------------------------
  // Shared helpers
  // -------------------------------------------------------------------------
  const mmss = (s) => {
    s = Math.max(0, Math.round(s));
    return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
  };
  const fmtInt = (v) => (v === null || v === undefined || Number.isNaN(v) ? "—" : String(Math.round(v)));
  const fmt1 = (v) => (v === null || v === undefined || Number.isNaN(v) ? "—" : v.toFixed(1));

  function setBanner(el, state, text) {
    el.className = "status-banner status-" + state;
    el.textContent = text;
  }

  function setGauge(fillEl, textEl, frac, label, alerting, unit) {
    if (frac === null) { fillEl.style.width = "0%"; textEl.textContent = "—"; return; }
    fillEl.style.width = Math.max(0, Math.min(100, frac * 100)) + "%";
    fillEl.style.backgroundColor = alerting ? css("--state-alert") : css("--trace-map");
    setValue(textEl, label, unit);
  }

  /** Heartbeat paced by the HR number (Adjustment A2), at the real heart rate, capped. */
  function makeHeart(el) {
    let hr = null, timer = null;
    const beat = () => {
      if (!REDUCED_MOTION) { el.classList.remove("beat"); void el.offsetWidth; el.classList.add("beat"); }
      schedule();
    };
    const schedule = () => {
      clearTimeout(timer);
      if (!hr || hr <= 0 || REDUCED_MOTION) return;
      const hz = Math.min(hr / 60, MAX_PULSE_HZ);
      timer = setTimeout(beat, 1000 / hz);
    };
    return { set(v) { const was = hr; hr = v; if (!was && v) schedule(); }, stop() { hr = null; clearTimeout(timer); } };
  }

  function prepCanvas(canvas) {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    return { ctx, w, h };
  }

  /**
   * Draws MAP / HR / pulse pressure against x. `upto` is the last index to
   * draw (inclusive) -- nothing beyond it is ever drawn.
   */
  function drawPanel(canvas, opt) {
    const { ctx, w, h } = prepCanvas(canvas);
    const pad = { l: 44, r: 12, t: 24, b: opt.xTicks ? 26 : 10 };
    const X = (x) => pad.l + ((x - opt.x0) / (opt.x1 - opt.x0)) * (w - pad.l - pad.r);
    const Y = (y) => pad.t + (1 - (Math.min(Math.max(y, opt.yMin), opt.yMax) - opt.yMin) / (opt.yMax - opt.yMin)) * (h - pad.t - pad.b);

    ctx.font = "12px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
    ctx.strokeStyle = css("--border");
    ctx.fillStyle = css("--text-secondary");
    ctx.lineWidth = 1;
    for (let y = opt.yMin; y <= opt.yMax; y += opt.yStep) {
      ctx.beginPath(); ctx.moveTo(pad.l, Y(y)); ctx.lineTo(w - pad.r, Y(y)); ctx.stroke();
      ctx.fillText(String(y), 8, Y(y) + 4);
    }
    (opt.xTicks || []).forEach(([x, label]) => ctx.fillText(label, Math.min(X(x) - 14, w - pad.r - ctx.measureText(label).width), h - 6));

    if (opt.ref65) {
      ctx.setLineDash([5, 4]);
      ctx.strokeStyle = css("--state-alarm");
      ctx.beginPath(); ctx.moveTo(pad.l, Y(65)); ctx.lineTo(w - pad.r, Y(65)); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = css("--state-alarm");
      ctx.fillText("MAP 65", w - pad.r - 52, Y(65) - 5);
    }

    // Each trace is drawn only up to index `upto` -- nothing after "now".
    opt.series.forEach((s) => {
      ctx.strokeStyle = css(s.color); ctx.lineWidth = 2; ctx.beginPath();
      let pen = false;
      for (let i = 0; i <= opt.upto && i < s.ys.length; i++) {
        const v = s.ys[i];
        if (v === null || v === undefined || Number.isNaN(v)) { pen = false; continue; }
        if (!pen) { ctx.moveTo(X(opt.xs[i]), Y(v)); pen = true; } else ctx.lineTo(X(opt.xs[i]), Y(v));
      }
      ctx.stroke();
    });

    // Legend in words, not color alone
    let lx = pad.l;
    opt.series.forEach((s) => {
      ctx.fillStyle = css(s.color); ctx.fillRect(lx, 8, 14, 3);
      ctx.fillStyle = css("--text"); ctx.fillText(s.label, lx + 18, 13);
      lx += ctx.measureText(s.label).width + 36;
    });

    // Event markers (callers only pass markers whose moment has been reached)
    (opt.markers || []).forEach((m) => {
      const x = X(m.x);
      ctx.strokeStyle = m.color; ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(x, pad.t); ctx.lineTo(x, h - pad.b); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = m.color;
      ctx.beginPath(); ctx.moveTo(x, h - pad.b - 10); ctx.lineTo(x - 6, h - pad.b); ctx.lineTo(x + 6, h - pad.b); ctx.closePath(); ctx.fill();
      if (opt.markerLabels) ctx.fillText(m.label, Math.min(x + 6, w - pad.r - ctx.measureText(m.label).width), pad.t + 14 + (m.row || 0) * 15);
    });

    if (opt.now !== undefined) {
      ctx.strokeStyle = css("--text-secondary");
      ctx.beginPath(); ctx.moveTo(X(opt.now), pad.t); ctx.lineTo(X(opt.now), h - pad.b); ctx.stroke();
    }
  }

  /** Top panel: MAP + pulse pressure (mmHg, MAP 65 line). Bottom panel: heart rate. */
  function drawChart(topCanvas, hrCanvas, opt) {
    const common = { xs: opt.xs, x0: opt.x0, x1: opt.x1, upto: opt.upto, markers: opt.markers, now: opt.now };
    drawPanel(topCanvas, {
      ...common, yMin: 0, yMax: 160, yStep: 40, ref65: true, markerLabels: true,
      series: [{ ys: opt.map, color: "--trace-map", label: "MAP (mmHg)" }, { ys: opt.pp, color: "--trace-pp", label: "Pulse pressure (mmHg)" }],
    });
    drawPanel(hrCanvas, {
      ...common, yMin: 40, yMax: 160, yStep: 40, xTicks: opt.xTicks,
      series: [{ ys: opt.hr, color: "--trace-hr", label: "Heart rate (bpm)" }],
    });
  }

  /** Big number with a small unit, built without innerHTML. */
  function setValue(el, text, unit) {
    el.textContent = text;
    if (unit && text !== "—") {
      const u = document.createElement("span");
      u.className = "unit";
      u.textContent = unit;
      el.appendChild(u);
    }
  }

  // -------------------------------------------------------------------------
  // Mode 1: replay
  // -------------------------------------------------------------------------
  const replay = (() => {
    const els = {
      play: $("replay-play"), restart: $("replay-restart"), speed: $("replay-speed"), scrub: $("replay-scrubber"),
      time: $("replay-time"), picker: $("case-picker"), banner: $("replay-banner"), note: $("selected-examples-note"),
      drift: $("drift-banner"), chart: $("replay-chart"), chartHr: $("replay-chart-hr"), noteBtn: $("replay-note-btn"), stdMap: $("standard-map"), stdState: $("standard-alarm-state"),
      verdictPanel: $("verdict-panel"), verdict: $("verdict-text"), tAlert: $("timeline-alert-marker"), tStd: $("timeline-standard-marker"),
      hr: $("hr-value"), map: $("map-value"), pp: $("pp-value"), si: $("si-value"),
      gaugeFill: $("risk-gauge-fill"), gaugeText: $("risk-gauge-text"), quality: $("data-quality"), why: $("why-list"),
      timingAlert: $("timing-alert"), timingStd: $("timing-std"), timingSaved: $("timing-saved"),
    };
    const heart = makeHeart($("heart-icon"));
    let src = null, caseData = null;

    const GROUPS = [["best", "Best example"], ["typical", "Typical"], ["miss", "Miss"], ["false_alarm", "False alarm"], ["insufficient", "Insufficient data"]];
    GROUPS.forEach(([kind, label]) => {
      const idx = CASES.map((c, i) => [c, i]).filter(([c]) => c.kind === kind);
      if (!idx.length) return;
      const og = document.createElement("optgroup");
      og.label = label;
      idx.forEach(([c, i], k) => {
        const o = document.createElement("option");
        o.value = String(i);
        o.textContent = `${label} ${k + 1} (VitalDB case ${c.caseid})`;
        og.appendChild(o);
      });
      els.picker.appendChild(og);
    });
    els.note.textContent = `${W.real_data_full} ${W.selected_examples_note}`;
    els.noteBtn.addEventListener("click", () => {
      els.note.hidden = !els.note.hidden;
      els.noteBtn.setAttribute("aria-expanded", String(!els.note.hidden));
    });
    $("horizon-min").textContent = String(META.horizon_min);

    const speed = () => Number(els.speed.value);
    const updateBannerText = () => { els.banner.textContent = W.replay_banner_tmpl.replace("{speed}", String(speed())); };

    /** When the exported verdict becomes knowable -- never earlier. */
    function verdictRevealT(c) {
      const end = c.t[c.t.length - 1];
      if (c.kind === "false_alarm" && c.alert_t !== null) return Math.min(c.alert_t + HORIZON_S, end);
      if ((c.kind === "best" || c.kind === "typical" || c.kind === "miss") && c.standard_alarm_t !== null) return c.standard_alarm_t;
      return end;
    }

    function riskAt(c, tAbs) {
      let r = null;
      for (let i = 0; i < c.risk_t.length && c.risk_t[i] <= tAbs; i++) r = c.risk[i];
      return r;
    }

    function missingFraction(c, i) {
      const n = Math.round(HORIZON_S / c.dt_s);
      let miss = 0, cnt = 0;
      for (let k = Math.max(0, i - n + 1); k <= i; k++) { cnt++; if (c.missing[k]) miss++; }
      return cnt ? miss / cnt : 0;
    }

    function render(s) {
      const c = caseData, t = s.tAbs, t0 = c.t[0];
      els.time.textContent = `${mmss(s.pos)} / ${mmss(src.duration)}`;
      els.scrub.value = String(Math.round((s.pos / src.duration) * 1000));

      setValue(els.hr, fmtInt(s.hr), "bpm");
      setValue(els.map, fmtInt(s.map), "mmHg");
      setValue(els.pp, fmtInt(s.pp), "mmHg");
      setValue(els.si, fmt1(s.si));
      heart.set(s.hr);

      const mf = missingFraction(c, s.i);
      const insufficient = mf > META.insufficient_data_missing_fraction;
      const risk = riskAt(c, t);
      els.quality.textContent = insufficient ? `Data quality: poor (${Math.round(mf * 100)}% missing, last ${META.horizon_min} min)`
        : risk === null ? "Data quality: good · no risk score yet at this point" : "Data quality: good";

      const alertOn = c.alert_t !== null && t >= c.alert_t && t < c.alert_t + HORIZON_S;
      if (insufficient || risk === null) setBanner(els.drift, "insufficient", W.insufficient_data_banner);
      else if (alertOn) setBanner(els.drift, "alert", W.alert_banner);
      else setBanner(els.drift, "monitoring", W.monitoring_banner);
      setGauge(els.gaugeFill, els.gaugeText, risk, risk === null ? "—" : `${Math.round(risk * 100)}%`, alertOn);

      els.why.innerHTML = "";
      if (alertOn) {
        c.top_features_at_alert.forEach((f) => {
          const li = document.createElement("li");
          li.textContent = `• ${f.name} ${fmtInt(f.value)}, ${f.direction}`;
          els.why.appendChild(li);
        });
      }

      const stdOn = c.standard_alarm_t !== null && t >= c.standard_alarm_t;

      // Timing panel: same timestamps as the chart markers, each revealed
      // only once playback has reached it (nothing from the future).
      const alertSeen = c.alert_t !== null && t >= c.alert_t;
      els.timingAlert.textContent = alertSeen ? mmss(c.alert_t - t0) : "—";
      els.timingStd.textContent = stdOn ? mmss(c.standard_alarm_t - t0) : "—";
      if (!stdOn) els.timingSaved.textContent = "—";
      else if (alertSeen && c.alert_t < c.standard_alarm_t) els.timingSaved.textContent = `${((c.standard_alarm_t - c.alert_t) / 60).toFixed(1)} min`;
      else els.timingSaved.textContent = "None";

      els.stdMap.textContent = `MAP ${fmtInt(s.map)} mmHg`;
      els.stdState.textContent = stdOn ? W.standard_alarm_triggered : W.standard_alarm_not_triggered;
      els.stdState.classList.toggle("triggered", stdOn);

      const showVerdict = t >= verdictRevealT(c);
      els.verdictPanel.hidden = !showVerdict;
      if (showVerdict) {
        els.verdict.textContent = c.verdict;
        const span = c.t[c.t.length - 1] - t0;
        const place = (el, at) => { el.hidden = at === null || at > t; if (!el.hidden) el.style.left = `${((at - t0) / span) * 100}%`; };
        place(els.tAlert, c.alert_t);
        place(els.tStd, c.standard_alarm_t);
      }

      const markers = [];
      if (c.alert_t !== null && t >= c.alert_t) markers.push({ x: c.alert_t, color: css("--state-alert"), label: META.alert_name, row: 0 });
      if (stdOn) markers.push({ x: c.standard_alarm_t, color: css("--state-alarm"), label: "Standard alarm", row: 1 });
      const ticks = [];
      for (let m = 0; m * 60 <= src.duration; m += 10) ticks.push([t0 + m * 60, `${m} min`]);
      drawChart(els.chart, els.chartHr, { xs: c.t, x0: t0, x1: c.t[c.t.length - 1], upto: s.i, map: c.map, hr: c.hr, pp: c.pp, markers, xTicks: ticks, now: t });
    }

    function load(i) {
      if (src) src.pause();
      caseData = CASES[i];
      src = new ReplaySource(caseData, speed);
      src.onSample(render);
      els.play.innerHTML = "&#9654; Play";
      src.seek(0);
    }

    function toggle() {
      if (src.playing) { src.pause(); els.play.innerHTML = "&#9654; Play"; }
      else { src.start(); els.play.innerHTML = "&#10074;&#10074; Pause"; watchEnd(); }
    }
    function watchEnd() {
      const check = () => { if (!src.playing) { els.play.innerHTML = "&#9654; Play"; return; } requestAnimationFrame(check); };
      requestAnimationFrame(check);
    }

    els.play.addEventListener("click", toggle);
    els.restart.addEventListener("click", () => { src.pause(); els.play.innerHTML = "&#9654; Play"; src.seek(0); });
    els.speed.addEventListener("change", updateBannerText);
    els.scrub.addEventListener("input", () => src.seek((Number(els.scrub.value) / 1000) * src.duration));
    els.picker.addEventListener("change", () => load(Number(els.picker.value)));
    updateBannerText();
    if (CASES.length) load(Number(els.picker.value || 0));

    return {
      toggle,
      select: (i, pos) => { els.picker.value = String(i); load(i); src.seek(pos); },
      scrubBy: (sec) => src.seek(src.pos + sec),
      redraw: () => render(src.sample()),
      pause: () => { if (src.playing) toggle(); },
      heart,
    };
  })();

  // -------------------------------------------------------------------------
  // Mode 2: simulated bleed (always SYNTHETIC; transparent rule score)
  // -------------------------------------------------------------------------
  const sim = (() => {
    const m = SIM.meta;
    const els = {
      slider: $("sim-f-slider"), fOut: $("sim-f-readout"), play: $("sim-play"), profile: $("sim-profile"), blunted: $("sim-blunted"),
      reset: $("sim-reset"), disclaimer: $("sim-disclaimer"), drift: $("sim-drift-banner"), chart: $("sim-chart"), chartHr: $("sim-chart-hr"),
      stdMap: $("sim-standard-map"), stdState: $("sim-standard-alarm-state"), verdict: $("sim-verdict-text"),
      hr: $("sim-hr-value"), map: $("sim-map-value"), pp: $("sim-pp-value"), si: $("sim-si-value"),
      gaugeFill: $("sim-gauge-fill"), gaugeText: $("sim-gauge-text"),
      timingAlert: $("sim-timing-alert"), timingStd: $("sim-timing-std"), timingSaved: $("sim-timing-saved"),
    };
    const heart = makeHeart($("sim-heart-icon"));
    const src = new SimulatedSource(SIM);
    // Seconds of on-screen play for the full 0..f_max range, per bleed profile.
    const PROFILE_SECONDS = { slow_ooze: 90, steady: 60, sudden: 25 };
    els.disclaimer.textContent = `${W.synthetic_banner} ${W.simulator_disclaimer} The alert here is a transparent rule score, not the trained model.`;
    els.slider.max = String(m.f_max * 100);

    const score = (hr, pp) => Math.max(0, Math.min(100, 100 * (
      0.5 * (hr - m.drift_score_hr_baseline) / m.drift_score_hr_scale +
      0.5 * (m.drift_score_pp_baseline - pp) / m.drift_score_pp_scale)));

    function keyPoints() {
      const s = src.series(), f = SIM.f;
      let alertF = null, map65F = null;
      for (let i = 0; i < f.length; i++) {
        if (alertF === null && score(s.hr[i], s.pp[i]) >= m.drift_score_alert_threshold) alertF = f[i];
        if (map65F === null && s.map[i] < m.map_event_threshold_mmhg) map65F = f[i];
      }
      return { alertF, map65F };
    }

    function render(sm) {
      const f = sm.pos, pct = (x) => `${Math.round(x * 100)}%`;
      els.fOut.textContent = pct(f);
      els.slider.value = String(f * 100);
      setValue(els.hr, fmtInt(sm.hr), "bpm");
      setValue(els.map, fmtInt(sm.map), "mmHg");
      setValue(els.pp, fmtInt(sm.pp), "mmHg");
      setValue(els.si, fmt1(sm.si));
      heart.set(sm.hr);

      const sc = score(sm.hr, sm.pp);
      const kp = keyPoints();
      const alertOn = kp.alertF !== null && f >= kp.alertF;
      const stdOn = kp.map65F !== null && f >= kp.map65F;
      setBanner(els.drift, alertOn ? "alert" : "monitoring",
        alertOn ? "DRIFT ALERT (rule score) · Heart rate rising, pulse pressure narrowing. Check the patient." : W.monitoring_banner);
      setGauge(els.gaugeFill, els.gaugeText, sc / 100, String(Math.round(sc)), alertOn, `/ 100 · alert at ${m.drift_score_alert_threshold}`);

      els.stdMap.textContent = `MAP ${fmtInt(sm.map)} mmHg`;
      els.stdState.textContent = stdOn ? W.standard_alarm_triggered : W.standard_alarm_not_triggered;
      els.stdState.classList.toggle("triggered", stdOn);

      // Timing panel: the verdict sentence's own numbers, each shown only once
      // the slider has reached that point.
      const warnedFirst = kp.alertF !== null && kp.map65F !== null && kp.alertF < kp.map65F;
      const marginPts = () => Math.round((kp.map65F - kp.alertF) * 100);
      els.timingAlert.textContent = alertOn ? pct(kp.alertF) : "—";
      els.timingStd.textContent = stdOn ? pct(kp.map65F) : "—";
      els.timingSaved.textContent = !stdOn ? "—" : warnedFirst ? `${marginPts()} pts` : "None";

      if (stdOn || f >= m.f_max - 1e-9) {
        if (warnedFirst) {
          els.verdict.textContent = `Drift alert at ${pct(kp.alertF)} blood lost. Standard alarm at ${pct(kp.map65F)}. ` +
            `That is ${marginPts()} percentage points of blood volume of warning.`;
        } else if (kp.map65F !== null) {
          els.verdict.textContent = "No warning before collapse in this setting.";
        } else {
          els.verdict.textContent = "Pressure never fell below 65 in this range.";
        }
      } else if (f > 0) {
        els.verdict.textContent = alertOn ? "Drift alert raised. Waiting to see when the standard alarm fires…" : "Watching…";
      } else {
        els.verdict.textContent = "Move the slider or press Play bleed.";
      }

      const markers = [];
      if (alertOn) markers.push({ x: kp.alertF * 100, color: css("--state-alert"), label: "Drift alert", row: 0 });
      if (stdOn) markers.push({ x: kp.map65F * 100, color: css("--state-alarm"), label: "Standard alarm", row: 1 });
      const s = src.series();
      const ticks = [];
      for (let p = 0; p <= m.f_max * 100 + 1e-9; p += 5) ticks.push([p, `${p}%`]);
      drawChart(els.chart, els.chartHr, { xs: SIM.f.map((x) => x * 100), x0: 0, x1: m.f_max * 100, upto: sm.i, map: s.map, hr: s.hr, pp: s.pp, markers, xTicks: ticks, now: f * 100 });
    }

    src.onSample(render);
    const setPlayLabel = () => { els.play.innerHTML = src.playing ? "&#10074;&#10074; Pause" : "&#9654; Play bleed"; };
    function toggle() {
      if (src.playing) src.pause();
      else {
        src.durationS = PROFILE_SECONDS[els.profile.value] || 60;
        src.start();
        const check = () => { setPlayLabel(); if (src.playing) requestAnimationFrame(check); };
        requestAnimationFrame(check);
      }
      setPlayLabel();
    }
    els.play.addEventListener("click", toggle);
    els.slider.addEventListener("input", () => { src.pause(); setPlayLabel(); src.seek(Number(els.slider.value) / 100); });
    els.blunted.addEventListener("change", () => { src.blunted = els.blunted.checked; src.seek(src.pos); });
    els.reset.addEventListener("click", () => { src.pause(); setPlayLabel(); src.seek(0); });
    src.seek(0);

    return { toggle, seek: (f, blunted) => { els.blunted.checked = blunted; src.blunted = blunted; src.seek(f); }, redraw: () => render(src.sample()), scrubBy: (d) => { src.pause(); setPlayLabel(); src.seek(src.pos + d); }, pause: () => { if (src.playing) toggle(); }, heart };
  })();

  // -------------------------------------------------------------------------
  // Tabs, drawer, keyboard
  // -------------------------------------------------------------------------
  let mode = "replay";
  function setMode(next) {
    mode = next;
    const isReplay = next === "replay";
    $("panel-replay").hidden = !isReplay;
    $("panel-sim").hidden = isReplay;
    $("tab-replay").classList.toggle("active", isReplay);
    $("tab-sim").classList.toggle("active", !isReplay);
    $("tab-replay").setAttribute("aria-selected", String(isReplay));
    $("tab-sim").setAttribute("aria-selected", String(!isReplay));
    const badge = $("mode-badge");
    badge.className = "badge " + (isReplay ? "badge-real" : "badge-synthetic");
    badge.textContent = isReplay ? W.real_data_badge : W.synthetic_badge;
    (isReplay ? sim : replay).pause();
    (isReplay ? replay : sim).redraw();
  }
  $("tab-replay").addEventListener("click", () => setMode("replay"));
  $("tab-sim").addEventListener("click", () => setMode("sim"));

  const pctS = (x) => (x === null || x === undefined ? "—" : `${(x * 100).toFixed(1)}%`);
  function simulationSection(s) {
    if (!s) return "";
    const rows = s.rows.map((r) =>
      `<tr><td>${r.tier}</td><td>${pctS(r.model_sensitivity)}</td><td>${r.model_fa_per_hour.toFixed(2)}</td><td>${r.model_lead_median_min.toFixed(1)}</td>` +
      `<td>${r.b2_lead_median_min.toFixed(1)}</td><td>${r.standard_monitor_lead_median_min.toFixed(1)}</td></tr>`).join("");
    const target = Object.entries(s.target_check).map(([t, v]) =>
      `${t}: ${pctS(v.sensitivity)} at ${v.fa_per_hour.toFixed(2)} false alarms/hr (${v.target_met ? "met" : "not met"})`).join(" · ");
    return `
      <h3><span class="badge badge-synthetic">Simulation</span> Injected bleeds on real baselines</h3>
      <p class="muted">${s.label}. Pre-registered target ≥ ${pctS(s.target_sensitivity)} at ≤ 1 false alarm/hr on T1–T2: ${target}.</p>
      <table><thead><tr><th>Tier</th><th>Sensitivity</th><th>FA/hr</th><th>Lead, model (min)</th><th>Lead, MAP cutoff</th><th>Lead, standard monitor</th></tr></thead><tbody>${rows}</tbody></table>
      <p class="muted">Unseen bleed settings (shifted test), all tiers: ${pctS(s.shifted_all.sensitivity)} at ${s.shifted_all.fa_per_hour.toFixed(2)} FA/hr, median lead ${s.shifted_all.lead_median_min.toFixed(1)} min. ${s.note}</p>`;
  }
  function renderProof() {
    const rows = PROOF.operating_points_table.map((r) =>
      `<tr><td>${r.method}</td><td>${pctS(r.sensitivity)}</td><td>${(r.lead_time_median_s / 60).toFixed(1)} min</td><td>${r.fa_per_hour.toFixed(2)}</td></tr>
       <tr><td colspan="4" class="muted">${r.note}</td></tr>`).join("");
    const cc = PROOF.cohort_counts, sp = PROOF.split_sizes;
    $("drawer-body").innerHTML = `
      <p>${PROOF.honesty_note}</p>
      <h3>Real surgical data (VitalDB), test set, 15-min horizon</h3>
      <table><thead><tr><th>Method</th><th>Sensitivity</th><th>Median lead</th><th>False alarms / patient-hour</th></tr></thead><tbody>${rows}</tbody></table>
      <h3>Calibration and ranking (shipped model, test set)</h3>
      <p>Brier score ${PROOF.brier_score.toFixed(3)} · AUROC ${PROOF.auroc.toFixed(3)} · AUPRC ${PROOF.auprc.toFixed(3)}</p>
      <h3>Cohorts</h3>
      <p>Split by patient: ${sp.train} train / ${sp.val} validation / ${sp.test} test cases. Eligible sample ${cc.n_eligible_sample} (high blood loss: ${cc.n_cohort_b}); fresh never-touched holdout ${cc.n_eligible_fresh_holdout} (high blood loss: ${cc.n_cohort_b_fresh_holdout}).</p>
      ${simulationSection(PROOF.simulation_round4)}
      <h3>How it works</h3>
      <ul>
        <li>Every 30 seconds the monitor's numbers (heart rate, blood pressure) are summarized from the recent past only.</li>
        <li>A small, calibrated model turns them into a risk that pressure falls below 65 in the next ${META.horizon_min} minutes.</li>
        <li>An alert fires when that risk passes a threshold chosen on separate data for about one false alarm per patient-hour.</li>
        <li>After an alert, it stays quiet for ${META.refractory_min} minutes so it doesn't nag.</li>
        <li>If too much data is missing, it says so instead of guessing.</li>
      </ul>
      <h3>What this is not</h3>
      <ul>${PROOF.what_this_is_not.map((x) => `<li>${x}</li>`).join("")}</ul>`;
  }
  const drawer = $("proof-drawer"), backdrop = $("drawer-backdrop");
  const openDrawer = () => { renderProof(); drawer.hidden = false; backdrop.hidden = false; $("drawer-close").focus(); };
  const closeDrawer = () => { drawer.hidden = true; backdrop.hidden = true; };
  $("proof-btn").addEventListener("click", openDrawer);
  $("info-btn").addEventListener("click", openDrawer);
  $("drawer-close").addEventListener("click", closeDrawer);
  backdrop.addEventListener("click", closeDrawer);

  // Metric tooltips: CSS shows them on hover/focus; a tap toggles them on touch screens.
  const closeTips = (except) => document.querySelectorAll(".tip-btn.open").forEach((b) => { if (b !== except) b.classList.remove("open"); });
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".tip-btn");
    closeTips(btn);
    if (btn) btn.classList.toggle("open");
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { closeDrawer(); closeTips(null); return; }
    const tag = (e.target.tagName || "").toLowerCase();
    if (tag === "select" || tag === "input" || tag === "button" || !drawer.hidden) return;
    const active = mode === "replay" ? replay : sim;
    if (e.key === " ") { e.preventDefault(); active.toggle(); }
    else if (e.key === "ArrowRight") { e.preventDefault(); active.scrubBy(mode === "replay" ? 60 : 0.01); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); active.scrubBy(mode === "replay" ? -60 : -0.01); }
  });
  window.addEventListener("resize", () => (mode === "replay" ? replay : sim).redraw());
  setMode("replay");

  // Optional deep link for presenting / screenshots, e.g. #case=0&t=1800 or #mode=sim&f=0.3&blunted=1
  const h = new URLSearchParams(location.hash.slice(1));
  if (h.get("mode") === "sim") {
    setMode("sim");
    sim.seek(Number(h.get("f") || 0), h.get("blunted") === "1");
  } else if (h.has("case") && CASES[Number(h.get("case"))]) {
    replay.select(Number(h.get("case")), Number(h.get("t") || 0));
  }
})();
