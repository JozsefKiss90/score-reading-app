/*
 * Headless behavioural test for beat_selector/score_soul.js (window.ScoreSoul).
 *
 * The GUI can't run in CI, so this loads the REAL score-soul payload from
 * Python (harmony.score_import + harmony.score_graph) and drives the controller
 * via Node's `vm` with NO document present -- exercising the host-facing data
 * contract that the launcher relies on (it is DOM-guarded, so rendering is a
 * no-op headless and all data/state logic still runs):
 *   - init() indexes 34 measures and the 148-node mandala;
 *   - setCurrentMeasure() tracks the live measure + exposes its slice;
 *   - selectMeasure() queues a selection drained once by takeSelection();
 *   - activeNodesFor() returns a measure's atlas/network constellation;
 *   - a chromatic measure's slice is marked honestly.
 *
 * Run:  node tests/score_soul_node_test.js
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const cp = require("child_process");

const ROOT = path.join(__dirname, "..");

function loadPayload() {
  const candidates = [
    path.join(ROOT, ".venv", "Scripts", "python.exe"),
    path.join(ROOT, ".venv", "bin", "python"),
    "python", "python3",
  ];
  const code =
    "import json;" +
    "from harmony.score_import import load_bwv846_analysis;" +
    "from harmony.score_graph import build_score_graph;" +
    "from harmony.harmonic_network import build_network;" +
    "from harmony.network_template import get_template;" +
    "r=load_bwv846_analysis();g=build_score_graph(r);" +
    "net=build_network(get_template('dominant_diminished_relative_network_v1')).to_payload();" +
    "cases=[{'measure':m,'target':r.slice_for_measure(m).network_target()," +
    "'refs':r.slice_for_measure(m).network_refs} for m in [1,3,6,11,14]];" +
    "print(json.dumps({'analysis':r.to_dict(),'graph':g.to_payload()," +
    "'network':net,'parity':cases}))";
  for (const py of candidates) {
    try {
      const out = cp.execFileSync(py, ["-c", code],
        { cwd: ROOT, encoding: "utf-8", maxBuffer: 64 * 1024 * 1024 });
      return JSON.parse(out);
    } catch (e) { /* try the next interpreter */ }
  }
  console.error("SKIP: could not run Python to build the score-soul payload.");
  process.exit(0);
}

let failures = 0;
function ok(cond, msg) {
  if (cond) { console.log("  ok  - " + msg); }
  else { failures++; console.log("FAIL  - " + msg); }
}
function eq(a, b, msg) { ok(a === b, msg + "  (got " + JSON.stringify(a) + ")"); }

// --- load the controller into a headless sandbox (no document) --------------
const src = fs.readFileSync(
  path.join(ROOT, "beat_selector", "score_soul.js"), "utf-8");
const sandbox = { window: {}, console: console };
vm.runInNewContext(src, sandbox, { filename: "score_soul.js" });
const Soul = sandbox.window.ScoreSoul;
ok(!!Soul, "window.ScoreSoul is exported");

const payload = loadPayload();

// --- init ------------------------------------------------------------------
const res = Soul.init(payload);
ok(res && res.ok, "init() returns ok");
eq(Soul.measureCount(), 34, "init indexes 34 measures");
eq(Soul.measures().length, 34, "measures() lists 34 entries");
eq(Soul.nodeCount(), payload.graph.counts.nodes, "nodeCount matches payload");
ok(Soul.nodeCount() > 100, "mandala has >100 nodes (got " + Soul.nodeCount() + ")");
ok(Soul.nodeIds().indexOf("score:bwv846_prelude_c_major") !== -1,
   "node ids include the central score node");

// init auto-selects the first measure
eq(Soul.currentMeasure(), 1, "init auto-selects measure 1");

// --- setCurrentMeasure ------------------------------------------------------
eq(Soul.setCurrentMeasure(6), 6, "setCurrentMeasure(6) returns 6");
eq(Soul.currentMeasure(), 6, "currentMeasure() tracks the live measure");
const s6 = Soul.sliceForMeasure(6);
ok(s6 && s6.status === "unsupported_chromatic",
   "measure 6 slice is marked unsupported_chromatic (honest)");
const s1 = Soul.sliceForMeasure(1);
ok(s1 && s1.roman === "I", "measure 1 slice roman is I");

// --- selection queue (host poll contract) ----------------------------------
ok(Soul.takeSelection() === null, "no pending selection before a click");
Soul.selectMeasure(3);
eq(Soul.currentMeasure(), 3, "selectMeasure updates the local current measure");
const sel = Soul.takeSelection();
ok(sel && sel.measure === 3, "takeSelection() drains the clicked measure");
ok(Soul.takeSelection() === null, "takeSelection() is a drain (empty after read)");

// --- active constellation ---------------------------------------------------
const active = Soul.activeNodesFor(1);
ok(active.indexOf("measure:1") !== -1, "activeNodesFor(1) includes its measure node");
ok(active.indexOf("slice:1") !== -1, "activeNodesFor(1) includes its harmony-slice node");
ok(active.some((id) => id.indexOf("atlas_ref:") === 0),
   "activeNodesFor(1) reaches an Atlas-ref node");
ok(active.some((id) => id.indexOf("network_ref:") === 0),
   "activeNodesFor(1) reaches a Network-ref node");

// --- counts -----------------------------------------------------------------
const gc = Soul.graphCounts();
ok(gc && gc.nodesByType.measure === 34, "graphCounts reports 34 measure nodes");
ok(gc.edgesByRelation.follows === 33, "graphCounts reports 33 follows edges");
const st = Soul.exportState();
eq(st.currentMeasure, 3, "exportState reflects the live current measure");
eq(st.measureCount, 34, "exportState reports the measure count");

// --- cross-language parity: Python network_refs_for == JS highlight set -----
// The Python network_refs_for() (score_analysis.py) is a documented hand-mirror
// of the JS highlightFromTrainerTarget() (harmonic_network.js).  Drive the REAL
// JS on the REAL network payload (with the proven minimal DOM stub) and assert
// it lights EXACTLY the Python-computed refs -- the guard against silent drift.
(function networkParity() {
  function makeNode(tag) {
    const n = { tag: tag || "div", id: "", className: "", _text: "", _html: "",
      dataset: {}, style: {}, _children: [], _listeners: {},
      classList: { _s: new Set(), add(c) { this._s.add(c); },
        remove(c) { this._s.delete(c); }, contains(c) { return this._s.has(c); },
        toggle(c, on) { if (on) this._s.add(c); else this._s.delete(c); } },
      appendChild(c) { this._children.push(c); return c; },
      addEventListener() {}, setAttribute(k, v) { if (k === "class") this.className = v; },
      getAttribute() { return null; }, removeAttribute() {}, remove() {},
      querySelector() { return null; }, querySelectorAll() { return []; } };
    Object.defineProperty(n, "textContent",
      { get() { return this._text; }, set(v) { this._text = v; } });
    Object.defineProperty(n, "innerHTML",
      { get() { return this._html; }, set(v) { this._html = v; this._children = []; } });
    return n;
  }
  const byId = new Map();
  const document = {
    getElementById(id) {
      if (!byId.has(id)) { const n = makeNode(); n.id = id; byId.set(id, n); }
      return byId.get(id);
    },
    createElement(tag) { return makeNode(tag); },   // no createElementNS -> SVG text fallback
    head: makeNode(), body: makeNode(),
  };
  const hnSandbox = { window: {}, document: document, console: console,
    Set: Set, Math: Math, Object: Object, Array: Array, String: String, JSON: JSON };
  vm.createContext(hnSandbox);
  vm.runInContext(
    fs.readFileSync(path.join(ROOT, "beat_selector", "harmonic_network.js"), "utf-8"),
    hnSandbox, { filename: "harmonic_network.js" });
  const HN = hnSandbox.window.HarmonicNetwork;
  ok(!!(HN && HN.highlightFromTrainerTarget && HN.syncNodes),
     "harmonic_network.js loaded headless for parity");
  HN.init(payload.network);
  function sortedEq(a, b) {
    if (a.length !== b.length) return false;
    const x = a.slice().sort(), y = b.slice().sort();
    return x.every((v, i) => v === y[i]);
  }
  (payload.parity || []).forEach((c) => {
    HN.highlightFromTrainerTarget(c.target);
    const live = HN.syncNodes();
    ok(sortedEq(live, c.refs),
       "m" + c.measure + " JS highlight == Python network_refs " +
       JSON.stringify(c.refs) + " (JS got " + JSON.stringify(live) + ")");
  });
})();

console.log(failures === 0
  ? "\nALL SCORE-SOUL TESTS PASSED"
  : "\n" + failures + " SCORE-SOUL TEST(S) FAILED");
process.exit(failures === 0 ? 0 : 1);
