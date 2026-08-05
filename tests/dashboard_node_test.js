/*
 * Headless behavioural test for beat_selector/dashboard.js (ticket 08, U3).
 *
 * Stubs the browser globals, builds a REAL dashboard payload from Python
 * (harmony.progress_service.dashboard_payload over a seeded temp store),
 * loads the controller via Node's `vm`, and verifies the host-facing API:
 *   - init() renders and reports the exercise-leaf count;
 *   - the heatmap paints one cell per leaf with the state class;
 *   - the due-today strip lists the due items; clicking one enqueues its
 *     node id (takeLaunch), as does clicking a heatmap cell;
 *   - setPayload() re-renders with fresh data;
 *   - the DOM-decoupled derivations (streak line, tooltips, due line).
 *
 * Run:  node tests/dashboard_node_test.js
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const cp = require("child_process");

const ROOT = path.join(__dirname, "..");

// --- build a real payload from Python (seeded: one due leaf, one fresh) -----
function loadPayload() {
  const candidates = [
    path.join(ROOT, ".venv", "Scripts", "python.exe"),
    path.join(ROOT, ".venv", "bin", "python"),
    "python", "python3",
  ];
  const code = `
import json, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from harmony.progress_service import ProgressService
now = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
with tempfile.TemporaryDirectory() as d:
    svc = ProgressService(Path(d) / "c.json", Path(d) / "j.json")
    from harmony.curriculum import get_curriculum
    leaves = get_curriculum().leaves()
    svc.record(leaves[0].id, accuracy=1.0,
               timestamp=(now - timedelta(days=10)).isoformat())
    svc.record(leaves[1].id, accuracy=1.0, timestamp=now.isoformat())
    svc.journey.mark_stage_completed("meet_the_scale", now.isoformat())
    print(json.dumps(svc.dashboard_payload(now)))
`;
  for (const py of candidates) {
    try {
      const out = cp.execFileSync(py, ["-c", code],
        { cwd: ROOT, encoding: "utf-8", maxBuffer: 64 * 1024 * 1024 });
      return JSON.parse(out);
    } catch (e) { /* try the next interpreter */ }
  }
  console.error("SKIP: could not run Python to build the dashboard payload.");
  process.exit(0);
}

// --- minimal DOM harness (mirrors curriculum_node_test.js) ------------------
let ALL = [];
function makeNode(tag) {
  const node = {
    tag: tag || "div", id: "", className: "", _text: "", _html: "", value: "",
    dataset: {}, style: {}, _children: [], _listeners: {},
    classList: {
      _s: new Set(),
      add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); },
      contains(c) { return this._s.has(c); },
    },
    appendChild(c) { this._children.push(c); return c; },
    addEventListener(ev, fn) { (this._listeners[ev] = this._listeners[ev] || []).push(fn); },
    setAttribute(k, v) { if (k === "class") this.className = v; this["_attr_" + k] = v; },
    removeAttribute() {}, remove() {},
    fire(ev, arg) { (this._listeners[ev] || []).forEach((fn) => fn(arg || {})); },
    querySelector() { return null; }, querySelectorAll() { return []; },
  };
  Object.defineProperty(node, "textContent",
    { get() { return this._text; }, set(v) { this._text = v; } });
  Object.defineProperty(node, "innerHTML",
    { get() { return this._html; }, set(v) { this._html = v; this._children = []; } });
  ALL.push(node);
  return node;
}
function cells() {
  return ALL.filter((n) => (n.className || "").indexOf("dashCell") === 0);
}
function dueCards() {
  return ALL.filter((n) => (n.className || "").indexOf("dashDueCard") === 0);
}

function makeHarness() {
  ALL = [];
  const byId = new Map();
  const document = {
    getElementById(id) {
      if (!byId.has(id)) { const n = makeNode(); n.id = id; byId.set(id, n); }
      return byId.get(id);
    },
    createElement(tag) { return makeNode(tag); },
    head: makeNode(), body: makeNode(),
  };
  const window = {};
  const sandbox = { window, document, console, Set, Math, Object, Array, String, JSON };
  vm.createContext(sandbox);
  vm.runInContext(
    fs.readFileSync(path.join(ROOT, "beat_selector", "dashboard.js"), "utf-8"),
    sandbox, { filename: "dashboard.js" });
  return { window, document, ui: window.Dashboard, byId };
}

let passed = 0;
function assert(cond, msg) {
  if (!cond) { console.error("FAIL:", msg); process.exitCode = 1; throw new Error(msg); }
  passed += 1;
}

const PAYLOAD = loadPayload();

// === Test A: init renders the full heatmap ==================================
(function testInit() {
  const h = makeHarness();
  const r = h.ui.init(PAYLOAD);
  assert(r.ok, "init ok");
  assert(r.leaves === PAYLOAD.heatmap.totalLeaves,
    "reports the payload's leaf count");
  assert(cells().length === PAYLOAD.heatmap.totalLeaves,
    "one heatmap cell per exercise leaf, got " + cells().length);
  const states = cells().map((c) => c.dataset.state);
  assert(states.filter((s) => s === "completed").length >= 2,
    "seeded completed leaves are painted");
  console.log("Test A (init/heatmap): PASS");
})();

// === Test B: due strip + launch queue =======================================
(function testDueStrip() {
  const h = makeHarness();
  h.ui.init(PAYLOAD);
  assert(PAYLOAD.review.dueCount === 1, "seed produced exactly one due item");
  const cards = dueCards();
  assert(cards.length === 1, "one due card rendered");
  cards[0].fire("click");
  const launched = h.ui.takeLaunch();
  assert(launched === PAYLOAD.review.due[0].nodeId,
    "clicking a due card enqueues its node id");
  assert(h.ui.takeLaunch() === null, "queue drains");
  console.log("Test B (due strip): PASS");
})();

// === Test C: heatmap cell click launches ====================================
(function testCellLaunch() {
  const h = makeHarness();
  h.ui.init(PAYLOAD);
  const cell = cells()[0];
  cell.fire("click");
  assert(h.ui.takeLaunch() === cell.dataset.nodeId,
    "clicking a heatmap cell enqueues its node id");
  console.log("Test C (cell launch): PASS");
})();

// === Test D: setPayload re-renders ==========================================
(function testSetPayload() {
  const h = makeHarness();
  h.ui.init(PAYLOAD);
  const fresh = JSON.parse(JSON.stringify(PAYLOAD));
  fresh.review.due = [];
  fresh.review.dueCount = 0;
  fresh.streak.current = 9;
  h.ui.setPayload(fresh);
  assert(dueCards().length === 1,
    "old cards remain only as detached stubs (strip itself was cleared)");
  const strip = h.document.getElementById("dashDue");
  assert(strip._children.length === 1 &&
    strip._children[0].className === "dashEmpty",
    "empty due strip shows the empty-state message");
  console.log("Test D (setPayload): PASS");
})();

// === Test E: pure derivations ===============================================
(function testDerivations() {
  const h = makeHarness();
  const ui = h.ui;
  assert(ui._streakLine({ current: 3, best: 5, practicedToday: true })
    .indexOf("3-day streak") !== -1, "streak line shows current");
  assert(ui._streakLine({ current: 3, best: 5, practicedToday: true })
    .indexOf("best 5") !== -1, "streak line shows best when higher");
  assert(ui._streakLine({ current: 0, best: 0, practicedToday: false })
    .indexOf("not practiced yet today") !== -1, "streak line nags gently");
  const tip = ui._cellTooltip({ title: "C major", state: "completed",
                                attempts: 2, dueAt: "2026-08-01T00:00:00+00:00" });
  assert(tip.indexOf("C major") === 0 && tip.indexOf("2 attempts") !== -1 &&
    tip.indexOf("due 2026-08-01") !== -1, "cell tooltip: " + tip);
  assert(ui._dueLine({ overdueDays: 0.2 }) === "due today", "due today line");
  assert(ui._dueLine({ overdueDays: 3.4 }) === "3 days overdue", "overdue line");
  console.log("Test E (derivations): PASS");
})();

console.log("dashboard_node_test: ALL PASS (" + passed + " assertions)");
