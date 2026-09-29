// Headless smoke test for the dashboard using jsdom (not part of the runtime).
// Usage: node scripts/dashboard_smoke.js http://127.0.0.1:8000
// Requires: npm install jsdom (dev-only). Canvas drawing is stubbed, so this
// checks that the JavaScript runs and builds the right DOM, NOT how it looks.
const { JSDOM, VirtualConsole } = require("jsdom");
const base = process.argv[2] || "http://127.0.0.1:8000";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const problems = [];
const check = (cond, msg) => { console.log((cond ? "PASS  " : "FAIL  ") + msg); if (!cond) problems.push(msg); };

(async () => {
  const vc = new VirtualConsole();
  vc.on("jsdomError", (e) => problems.push("jsdomError: " + e.message));
  vc.on("error", (...a) => problems.push("console.error: " + a.join(" ")));
  const html = await (await fetch(base + "/")).text();
  const dom = new JSDOM(html, {
    url: base + "/", runScripts: "dangerously", resources: "usable", pretendToBeVisual: true, virtualConsole: vc,
    beforeParse(w) {
      w.fetch = (u, o) => fetch(new URL(u, base), o);
      const noop = () => {};
      const ctx = new Proxy({}, { get: (t, k) => (k in t ? t[k] : noop), set: (t, k, v) => { t[k] = v; return true; } });
      w.HTMLCanvasElement.prototype.getContext = () => ctx;
      Object.defineProperty(w.HTMLElement.prototype, "clientWidth", { get() { return 600; } });
      Object.defineProperty(w.HTMLElement.prototype, "clientHeight", { get() { return 70; } });
    },
  });
  const d = dom.window.document;
  const q = (s) => d.querySelector(s), qa = (s) => [...d.querySelectorAll(s)];

  // Wait until the simulator (run fast by the caller) has sealed an incident.
  for (let i = 0; i < 40 && qa("#incident-list li").length === 0; i++) await sleep(500);

  check(qa("#tape .lane").length === 6, "live view renders 6 channel lanes");
  check(!/Connecting|unreachable/.test(q("#status-text").textContent), "status text: " + q("#status-text").textContent);
  check(q("#machine-name").textContent.length > 0, "machine name shown");
  check(!q("#mode-badge").hidden, "mode badge visible: " + q("#mode-badge").textContent);
  check(qa("#inject-buttons button").length === 5, "5 fault-injection buttons");
  check(qa("#incident-list li").length >= 1, "incident list has entries: " + qa("#incident-list li").length);

  qa("#incident-list button")[qa("#incident-list li").length - 1].click();
  await sleep(800);
  check(!q("#incident-view").hidden && q("#live-view").hidden, "incident view replaces live view");
  check(qa("#incident-view .rowline").length === 6, "incident board has 6 rows");
  check(qa("#incident-view .rowline:not(.still)").length >= 2, "moved channels listed before still ones");
  check(/Sealed, chain intact/.test(q("#seal-pill").textContent), "seal pill: " + q("#seal-pill").textContent);
  check(q("#incident-view .narrative").textContent.length > 80, "narrative rendered");
  check(qa("#incident-view .hyp").length === 4, "4 hypothesis rows");
  check(q('#incident-view a[download]').getAttribute("href").endsWith("/bundle"), "bundle download link");

  const before = q("#scrub").value;
  q("#scrub").value = "0"; q("#scrub").dispatchEvent(new dom.window.Event("input"));
  check(/^-/.test(q("#scrub-time").textContent), "scrubbing to start shows negative time: " + q("#scrub-time").textContent);
  q("#play-btn").click();
  check(q("#play-btn").textContent === "Pause", "play toggles to Pause");
  await sleep(600);
  check(Number(q("#scrub").value) > 0, "replay advances the cursor: " + q("#scrub").value);
  q("#play-btn").click();
  check(q("#play-btn").textContent === "Play replay", "pause toggles back");

  qa("#incident-view button").find((b) => b.textContent === "Back to live").click();
  check(q("#incident-view").hidden && !q("#live-view").hidden, "back to live works");

  q("#verify-btn").click();
  await sleep(500);
  check(/Chain intact/.test(q("#chain-status").textContent), "verify chain: " + q("#chain-status").textContent);

  qa("#inject-buttons button")[2].click();
  await sleep(500);
  check(/Injected/.test(q("#toast").textContent), "inject toast: " + q("#toast").textContent);

  check(problems.filter((p) => /error|Error/.test(p)).length === 0, "no JS errors: " + JSON.stringify(problems.filter((p) => /rror/.test(p))));
  dom.window.close();
  process.exit(problems.length ? 1 : 0);
})().catch((e) => { console.error("smoke test crashed:", e); process.exit(2); });
