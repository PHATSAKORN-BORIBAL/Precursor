"use strict";
/* Precursor dashboard. Plain JavaScript, no build step, no external requests.
   All server text is inserted with textContent, never innerHTML. */

const MAX_POINTS = 420;
const POLL_MS = 500;

const state = {
  config: null, seq: 0, series: {}, baselines: {}, lanes: {}, live: null,
  incidents: [], liveIncidentCount: -1, selected: null, detail: null,
  rows: [], cursor: 0, playTimer: null, polling: false, sealOk: null,
};

const $ = (id) => document.getElementById(id);

function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v === false || v == null) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid != null) el.append(kid);
  return el;
}

const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const pad2 = (n) => String(n).padStart(2, "0");

function fmtT(t) {
  if (t > 1e9) return new Date(t * 1000).toISOString().replace("T", " ").slice(0, 19) + "Z";
  const s = Math.round(t);
  return `T+${pad2(Math.floor(s / 3600))}:${pad2(Math.floor((s % 3600) / 60))}:${pad2(s % 60)}`;
}
function fmtDur(sec) {
  const s = Math.abs(Math.round(sec));
  return s < 120 ? `${s} s` : `${Math.floor(s / 60)} min ${pad2(s % 60)} s`;
}
function fmtRel(sec) { return (sec < 0 ? "-" : "+") + fmtDur(sec); }
function fmtVal(v) {
  const a = Math.abs(v);
  return a >= 100 ? v.toFixed(1) : a >= 10 ? v.toFixed(2) : v.toFixed(3);
}
const humanize = (s) => s.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
const labelOf = (name) => (state.config.channels.find((c) => c.name === name) || { label: name }).label;

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  let body = null;
  try { body = await res.json(); } catch (_) { /* non-JSON error body */ }
  if (!res.ok) {
    const d = body && body.detail;
    throw new Error(typeof d === "string" ? d : d ? JSON.stringify(d) : `HTTP ${res.status}`);
  }
  return body;
}

function toast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { el.hidden = true; }, 3500);
}

function fit(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const w = Math.max(1, Math.round(canvas.clientWidth * dpr));
  const hh = Math.max(1, Math.round(canvas.clientHeight * dpr));
  if (canvas.width !== w || canvas.height !== hh) { canvas.width = w; canvas.height = hh; }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w: canvas.clientWidth, h: canvas.clientHeight };
}

/* ------------------------------------------------------------- live view */

function buildLanes() {
  const tape = $("tape");
  tape.replaceChildren();
  for (const ch of state.config.channels) {
    const canvas = h("canvas", { "aria-label": `${ch.label} trace` });
    const valueEl = h("div", { class: "lane-value" });
    const zEl = h("div", { class: "lane-z" });
    tape.append(h("div", { class: "lane" },
      h("div", { class: "lane-info" }, h("span", { class: "lane-name", text: ch.label }), valueEl, zEl),
      canvas));
    state.lanes[ch.name] = { canvas, valueEl, zEl, unit: ch.unit };
    state.series[ch.name] = [];
  }
}

function resetSeries() {
  for (const name of Object.keys(state.series)) state.series[name] = [];
}

function pushSample(s) {
  for (const name of Object.keys(state.series)) {
    const v = s.values[name];
    if (v == null) continue;
    const arr = state.series[name];
    arr.push({ t: s.t, v, z: s.z ? s.z[name] || 0 : 0 });
    if (arr.length > MAX_POINTS) arr.splice(0, arr.length - MAX_POINTS);
  }
}

function zColor(z) {
  const a = Math.abs(z);
  return a >= 4 ? cssVar("--orange") : a >= 2 ? cssVar("--amber") : cssVar("--teal");
}

function drawLane(name) {
  const lane = state.lanes[name];
  const pts = state.series[name];
  const { ctx, w, h: ht } = fit(lane.canvas);
  ctx.clearRect(0, 0, w, ht);
  if (!pts.length) return;

  const base = state.baselines[name];
  let lo = Infinity, hi = -Infinity;
  for (const p of pts) { if (p.v < lo) lo = p.v; if (p.v > hi) hi = p.v; }
  if (base) { lo = Math.min(lo, base.mean - 5 * base.sigma); hi = Math.max(hi, base.mean + 5 * base.sigma); }
  const padv = (hi - lo) * 0.08 || 1;
  lo -= padv; hi += padv;
  const y = (v) => ht - 4 - ((v - lo) / (hi - lo)) * (ht - 8);
  const n = pts.length;
  const x = (i) => w - ((n - 1 - i) / (MAX_POINTS - 1)) * w;

  if (base) {
    ctx.fillStyle = "rgba(95,208,197,0.10)";
    ctx.fillRect(0, y(base.mean + 2 * base.sigma), w, y(base.mean - 2 * base.sigma) - y(base.mean + 2 * base.sigma));
    ctx.strokeStyle = "rgba(255,106,43,0.45)";
    ctx.setLineDash([4, 4]);
    for (const k of [4, -4]) {
      const yy = y(base.mean + k * base.sigma);
      ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(w, yy); ctx.stroke();
    }
    ctx.setLineDash([]);
  }

  const capT = state.live && state.live.capture_trigger_t;
  if (capT != null) {
    const start = capT - state.config.detection.pre_roll_s;
    let i0 = pts.findIndex((p) => p.t >= start);
    if (i0 < 0) i0 = n - 1;
    ctx.fillStyle = "rgba(255,106,43,0.09)";
    ctx.fillRect(x(i0), 0, w - x(i0), ht);
  }
  ctx.strokeStyle = "rgba(255,106,43,0.8)";
  ctx.setLineDash([3, 3]);
  for (const inc of state.incidents) {
    const i = pts.findIndex((p) => p.t >= inc.trigger_time);
    if (i > 0 && pts[i].t - inc.trigger_time < 2) {
      ctx.beginPath(); ctx.moveTo(x(i), 0); ctx.lineTo(x(i), ht); ctx.stroke();
    }
  }
  ctx.setLineDash([]);

  ctx.lineWidth = 1.6;
  ctx.lineJoin = "round";
  for (let i = 1; i < n; i++) {
    ctx.strokeStyle = zColor(pts[i].z);
    ctx.beginPath();
    ctx.moveTo(x(i - 1), y(pts[i - 1].v));
    ctx.lineTo(x(i), y(pts[i].v));
    ctx.stroke();
  }

  const last = pts[n - 1];
  lane.valueEl.textContent = "";
  lane.valueEl.append(fmtVal(last.v), h("small", { text: lane.unit }));
  const a = Math.abs(last.z);
  lane.zEl.textContent = base ? `${last.z >= 0 ? "+" : ""}${last.z.toFixed(1)} from normal` : "learning normal range…";
  lane.zEl.className = "lane-z" + (a >= 4 ? " bad" : a >= 2 ? " warn" : "");
}

function drawTape() { for (const name of Object.keys(state.lanes)) drawLane(name); }

function renderState(st) {
  state.live = st;
  state.baselines = st.baselines || {};
  let cls = "armed", text = "Recording. All channels are inside their normal range.";
  if (st.phase === "warming_up") {
    cls = "warming"; text = `Learning the normal range of each channel… ${Math.round(st.warmup_progress * 100)}%`;
  } else if (st.phase === "capturing") {
    cls = "capturing"; text = `Incident triggered. Recording the aftermath… ${Math.round(st.capture_progress * 100)}%`;
  } else if (st.phase === "alarm") {
    cls = "alarm";
    text = `Incident sealed. Waiting for ${st.latched.map(labelOf).join(", ")} to settle.`;
  }
  $("status-dot").className = "dot " + cls;
  $("status-text").textContent = text;

  const hv = $("health-value");
  hv.textContent = st.phase === "warming_up" ? "--" : Math.round(st.health);
  hv.className = st.health >= 80 ? "ok" : st.health >= 40 ? "warn" : "bad";

  const cap = st.ring_capacity_s;
  $("buf-fill").style.width = `${Math.min(100, (st.buffered_s / cap) * 100)}%`;
  $("buf-preroll").style.width = `${(state.config.detection.pre_roll_s / cap) * 100}%`;
  $("buf-text").textContent =
    `${Math.round(st.buffered_s)} s of ${cap} s buffered. The last ${state.config.detection.pre_roll_s} s (orange) are sealed when something goes wrong.`;
}

async function pollLive() {
  if (state.polling) return;
  state.polling = true;
  try {
    const data = await fetchJSON(`/api/live?since=${state.seq}`);
    if (data.seq < state.seq) { state.seq = 0; resetSeries(); state.polling = false; return; }
    for (const s of data.samples) pushSample(s);
    state.seq = data.seq;
    renderState(data.state);
    if (data.state.incidents !== state.liveIncidentCount) {
      state.liveIncidentCount = data.state.incidents;
      await loadIncidents();
    }
    if (!state.selected) drawTape();
  } catch (err) {
    $("status-dot").className = "dot offline";
    $("status-text").textContent = `Recorder unreachable (${err.message}). Retrying…`;
  } finally {
    state.polling = false;
  }
}

/* ---------------------------------------------------------- incident list */

async function loadIncidents() {
  const data = await fetchJSON("/api/incidents");
  state.incidents = data.incidents;
  renderIncidentList();
}

function renderIncidentList() {
  const list = $("incident-list");
  list.replaceChildren();
  $("incident-empty").hidden = state.incidents.length > 0;
  for (const inc of state.incidents) {
    const unknown = inc.verdict === "unknown_pattern" || inc.verdict === "no_deviation";
    const btn = h("button", {
      class: "incident", type: "button", "aria-current": String(inc.id === state.selected),
      onclick: () => selectIncident(inc.id),
    },
      h("div", { class: "row" },
        h("span", { class: "verdict" + (unknown ? " unknown" : ""), text: humanize(inc.verdict) }),
        h("span", { class: "id", text: inc.id })),
      h("div", { class: "meta", text: `${fmtT(inc.trigger_time)}, triggered on ${labelOf(inc.trigger_channel)}` }),
      h("div", { class: "meta", text: `match score ${inc.score.toFixed(2)}` }));
    list.append(h("li", {}, btn));
  }
}

async function verifyChain(showToast) {
  try {
    const r = await fetchJSON("/api/vault/verify");
    const el = $("chain-status");
    el.className = "chain-status " + (r.ok ? "ok" : "bad");
    el.textContent = r.ok ? `Chain intact (${r.count} sealed)` : `Broken at ${r.broken_at}: ${r.reason}`;
    state.sealOk = r.ok;
    if (showToast) toast(r.ok ? "Hash chain verified." : "Hash chain is broken.");
    return r;
  } catch (err) {
    toast(`Verification failed: ${err.message}`);
    return null;
  }
}

/* ---------------------------------------------------------- incident view */

async function selectIncident(id) {
  try {
    const detail = await fetchJSON(`/api/incidents/${encodeURIComponent(id)}`);
    stopPlayback();
    state.selected = id;
    state.detail = detail;
    $("live-view").hidden = true;
    $("incident-view").hidden = false;
    buildIncidentView();
    renderIncidentList();
    const r = await verifyChain(false);
    const pill = $("seal-pill");
    if (pill && r) {
      pill.textContent = r.ok ? `Sealed, chain intact (sha256 ${detail.seal.hash.slice(0, 10)}…)` : "Seal check failed";
      pill.className = "pill " + (r.ok ? "sealed" : "");
    }
  } catch (err) {
    toast(`Could not open ${id}: ${err.message}`);
  }
}

function closeIncident() {
  stopPlayback();
  state.selected = null; state.detail = null; state.rows = [];
  $("incident-view").hidden = true;
  $("live-view").hidden = false;
  renderIncidentList();
  drawTape();
}

function buildIncidentView() {
  const p = state.detail.payload;
  const an = p.analysis;
  const verdict = an.verdict;
  const t = p.t, n = t.length, trig = p.trigger.t;
  const top = an.hypotheses.find((x) => x.fault === verdict.label);
  const headline = verdict.confident && top ? top.title : "Unknown pattern";
  const view = $("incident-view");
  view.replaceChildren();

  view.append(h("div", { class: "inc-head" },
    h("div", {},
      h("h2", { text: headline }),
      h("p", { class: "inc-sub",
        text: `${p.id}, triggered at ${fmtT(trig)} on ${labelOf(p.trigger.channel)}. ${p.window.sample_count} samples sealed.` }),
      h("p", { class: "inc-sub" },
        h("span", { class: "pill " + (p.provenance.source === "live" ? "" : "sim"),
          text: p.provenance.source === "live" ? "Live data" : `${humanize(p.provenance.source)} data` }),
        h("span", { id: "seal-pill", class: "pill", text: "Checking seal…" }))),
    h("button", { class: "btn", type: "button", onclick: closeIncident, text: "Back to live" })));

  // Board: one row per channel, movers first, in onset order.
  const findings = Object.fromEntries(an.chain.map((f) => [f.channel, f]));
  const order = [...an.chain.map((f) => f.channel),
                 ...p.channels.map((c) => c.name).filter((c) => !findings[c])];
  const board = h("div", { class: "board" });
  const axis = h("div", { class: "axis" });
  const pct = (tt) => `${((tt - t[0]) / (t[n - 1] - t[0])) * 100}%`;
  const tick = (tt, text, cls) => { const s = h("span", { text, class: cls }); s.style.left = pct(tt); return s; };
  axis.append(tick(t[0], fmtRel(t[0] - trig)), tick(trig, "trigger", "trig"), tick(t[n - 1], fmtRel(t[n - 1] - trig)));
  board.append(axis);

  state.rows = [];
  for (const name of order) {
    const f = findings[name];
    const chan = p.channels.find((c) => c.name === name);
    const valEl = h("div", { class: "val" });
    let note = "No clear change";
    if (f) {
      note = f.lead_s > 0 ? `Left normal ${fmtDur(f.lead_s)} before the trigger`
                          : `Moved ${fmtDur(f.lead_s)} after the trigger`;
      if (f.clipped) note += " (or earlier)";
    }
    const canvas = h("canvas", { "aria-label": `${chan.label} replay` });
    board.append(h("div", { class: "rowline" + (f ? "" : " still") },
      h("div", { class: "info" },
        h("b", { text: chan.label + (f ? (f.direction === "up" ? "  ↑" : "  ↓") : "") }),
        valEl, h("span", { class: "note" + (f && f.lead_s > 0 ? " lead" : ""), text: note })),
      canvas));
    state.rows.push({ name, canvas, valEl, finding: f, unit: chan.unit });
  }
  view.append(board);

  state.cursor = Math.max(0, t.findIndex((tt) => tt >= trig));
  const range = h("input", { type: "range", min: "0", max: String(n - 1), value: String(state.cursor),
    id: "scrub", "aria-label": "Replay position" });
  range.addEventListener("input", () => { state.cursor = Number(range.value); drawIncident(); });
  const timeEl = h("span", { id: "scrub-time", class: "time" });
  const playBtn = h("button", { id: "play-btn", class: "btn primary", type: "button", text: "Play replay", onclick: togglePlayback });
  view.append(h("div", { class: "scrub" }, playBtn, range, timeEl));

  // Conclusions and evidence.
  const hyps = h("div", {});
  an.hypotheses.slice(0, 4).forEach((x, i) => hyps.append(h("div", { class: "hyp" + (i === 0 && verdict.confident ? " top" : "") },
    h("span", { text: humanize(x.fault) }),
    h("span", { class: "bar" }, (() => { const b = h("i"); b.style.width = `${Math.round(x.score * 100)}%`; return b; })()),
    h("span", { text: x.score.toFixed(2) }))));
  const concl = h("div", { class: "panel" },
    h("h3", { class: "section-title", text: "What the recorder concluded" }),
    h("p", { class: "narrative", text: p.narrative }),
    h("h3", { class: "section-title", text: "Pattern matches" }), hyps);
  if (verdict.confident && top) {
    concl.append(
      h("p", { class: "kv", text: `Matched: ${top.matched.map(labelOf).join(", ") || "none"}.` +
        (top.missing.length ? ` Not seen: ${top.missing.map(labelOf).join(", ")}.` : "") +
        (top.unexpected.length ? ` Also moved: ${top.unexpected.join(", ")}.` : "") }),
      h("h3", { class: "section-title", text: "Suggested checks" }),
      h("ul", { class: "checks" }, top.checks.map((c) => h("li", { text: c }))));
  }
  concl.append(h("p", { class: "caveat", text: "Scores come from a hand-written heuristic. Onset order shows sequence, not proof of cause." }));

  const seal = state.detail.seal;
  const missing = Object.entries(p.data_quality.missing_samples).filter(([, v]) => v > 0);
  const evidence = h("div", { class: "panel" },
    h("h3", { class: "section-title", text: "Evidence" }),
    h("p", { class: "kv", text: `Sealed ${p.sealed_at_utc} by ${p.provenance.software}.` }),
    h("p", { class: "kv", text: "Seal (SHA-256):" }), h("p", { class: "mono", text: seal.hash }),
    h("p", { class: "kv", text: "Previous incident's seal:" }), h("p", { class: "mono", text: seal.prev_hash }),
    h("p", { class: "kv", text: missing.length ? `Missing readings: ${missing.map(([k, v]) => `${labelOf(k)} ${v}`).join(", ")}.` : "No missing readings in this window." }),
    h("p", { class: "kv" }, h("a", { class: "btn", href: `/api/incidents/${encodeURIComponent(p.id)}/bundle`, download: `${p.id}.json`, text: "Download evidence bundle" })),
    h("p", { class: "caveat", text: `Check offline: python -m precursor verify --file ${p.id}.json` }));
  view.append(h("div", { class: "cols" }, concl, evidence));

  drawIncident();
}

function drawIncident() {
  if (!state.detail) return;
  const p = state.detail.payload;
  const t = p.t, n = t.length, t0 = t[0], t1 = t[n - 1], trig = p.trigger.t;
  const orange = cssVar("--orange"), amber = cssVar("--amber"), teal = cssVar("--teal");

  for (const row of state.rows) {
    const { ctx, w, h: ht } = fit(row.canvas);
    ctx.clearRect(0, 0, w, ht);
    const vals = p.values[row.name], zs = p.z[row.name], base = p.baselines[row.name];
    let lo = Math.min(...vals, base.mean - 5 * base.sigma);
    let hi = Math.max(...vals, base.mean + 5 * base.sigma);
    const padv = (hi - lo) * 0.08 || 1; lo -= padv; hi += padv;
    const x = (tt) => ((tt - t0) / (t1 - t0)) * w;
    const y = (v) => ht - 3 - ((v - lo) / (hi - lo)) * (ht - 6);

    ctx.fillStyle = "rgba(95,208,197,0.10)";
    ctx.fillRect(0, y(base.mean + 2 * base.sigma), w, y(base.mean - 2 * base.sigma) - y(base.mean + 2 * base.sigma));

    const f = row.finding;
    const onsetIdx = f ? Math.max(0, t.findIndex((tt) => tt >= f.onset_t)) : n;
    const after = f && f.role === "follower" ? amber : orange;
    ctx.lineWidth = 1.6; ctx.lineJoin = "round";
    const stroke = (from, to, col) => {
      if (to - from < 1) return;
      ctx.strokeStyle = col; ctx.beginPath();
      for (let i = from; i <= to; i++) { i === from ? ctx.moveTo(x(t[i]), y(vals[i])) : ctx.lineTo(x(t[i]), y(vals[i])); }
      ctx.stroke();
    };
    stroke(0, Math.min(onsetIdx, n - 1), teal);
    if (f) stroke(onsetIdx, n - 1, after);

    ctx.strokeStyle = orange; ctx.setLineDash([5, 4]); ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.moveTo(x(trig), 0); ctx.lineTo(x(trig), ht); ctx.stroke(); ctx.setLineDash([]);

    if (f) {
      ctx.strokeStyle = after; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(x(f.onset_t), ht - 3); ctx.lineTo(x(trig), ht - 3); ctx.stroke();
      ctx.fillStyle = after; ctx.strokeStyle = cssVar("--panel"); ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(x(f.onset_t), y(vals[onsetIdx]), 5, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    }
    const cx = x(t[state.cursor]);
    ctx.strokeStyle = "rgba(231,238,242,0.85)"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(cx, 0); ctx.lineTo(cx, ht); ctx.stroke();

    const z = zs[state.cursor];
    row.valEl.textContent = `${fmtVal(vals[state.cursor])} ${row.unit}  (${z >= 0 ? "+" : ""}${z.toFixed(1)} from normal)`;
    row.valEl.style.color = Math.abs(z) >= 4 ? orange : Math.abs(z) >= 2 ? amber : "";
  }
  const timeEl = $("scrub-time");
  if (timeEl) timeEl.textContent = t[state.cursor] === trig ? "trigger" : fmtRel(t[state.cursor] - trig);
}

function stopPlayback() {
  if (state.playTimer) { clearInterval(state.playTimer); state.playTimer = null; }
  const btn = $("play-btn");
  if (btn) btn.textContent = "Play replay";
}

function togglePlayback() {
  if (state.playTimer) { stopPlayback(); return; }
  const n = state.detail.payload.t.length;
  if (state.cursor >= n - 1) state.cursor = 0;
  $("play-btn").textContent = "Pause";
  state.playTimer = setInterval(() => {
    state.cursor = Math.min(n - 1, state.cursor + 2);
    $("scrub").value = String(state.cursor);
    drawIncident();
    if (state.cursor >= n - 1) stopPlayback();
  }, 33);
}

/* ------------------------------------------------------------------- init */

async function inject(fault) {
  try {
    const r = await fetchJSON("/api/sim/inject", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fault, severity: 1.0 }),
    });
    toast(`Injected ${humanize(r.fault)} at ${fmtT(r.start_t)}.`);
  } catch (err) {
    toast(`Could not inject: ${err.message}`);
  }
}

async function init() {
  try {
    state.config = await fetchJSON("/api/config");
  } catch (err) {
    $("status-text").textContent = `Cannot reach the recorder API (${err.message}).`;
    $("status-dot").className = "dot offline";
    return;
  }
  $("machine-name").textContent = state.config.machine.name;
  const badge = $("mode-badge");
  badge.hidden = false;
  badge.textContent = state.config.mode === "simulate"
    ? `Simulation data, ${state.config.sim_speed}x speed` : "Live ingest";
  if (state.config.mode === "simulate") {
    $("inject-panel").hidden = false;
    const box = $("inject-buttons");
    for (const f of state.config.faults) {
      box.append(h("button", { class: "btn", type: "button", onclick: () => inject(f.name) },
        humanize(f.name), h("span", { text: f.description })));
    }
  }
  $("verify-btn").addEventListener("click", () => verifyChain(true));
  buildLanes();
  window.addEventListener("resize", () => { state.selected ? drawIncident() : drawTape(); });
  await pollLive();
  setInterval(pollLive, POLL_MS);
}

init();
