/*
 * Headless behavioural test for beat_selector/harmonic_network.js.
 *
 * The GUI can't run in CI, so this stubs the browser globals (window/document),
 * loads the REAL payload from Python (harmony.harmonic_network), runs the
 * controller via Node's `vm`, and verifies the host-facing contract:
 *   - init() indexes the graph and renders without throwing (48 nodes);
 *   - node-class filters hide/show nodes;
 *   - selecting C surfaces its related Am / G7 / B°;
 *   - selecting G7 explains "resolves to C";
 *   - clicking a launch button queues a valid spec, dequeued via takeLaunch();
 *   - a dominant-seventh node's seventh drill is reserved (never launchable);
 *   - trainer/atlas sync highlighting maps onto the right node.
 *
 * Run:  node tests/harmonic_network_node_test.js
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const cp = require("child_process");

const ROOT = path.join(__dirname, "..");

// --- load the real payload from Python --------------------------------------
function loadPayload() {
  const candidates = [
    path.join(ROOT, ".venv", "Scripts", "python.exe"),
    path.join(ROOT, ".venv", "bin", "python"),
    "python", "python3",
  ];
  const code =
    "import json;from harmony.harmonic_network import build_network_payload;" +
    "print(json.dumps(build_network_payload()))";
  for (const py of candidates) {
    try {
      const out = cp.execFileSync(py, ["-c", code],
        { cwd: ROOT, encoding: "utf-8", maxBuffer: 64 * 1024 * 1024 });
      return JSON.parse(out);
    } catch (e) { /* try the next interpreter */ }
  }
  console.error("SKIP: could not run Python to build the network payload.");
  process.exit(0);
}

// --- minimal DOM harness (mirrors curriculum_node_test.js) ------------------
let ALL = [];
function makeNode(tag) {
  const node = {
    tag: tag || "div", id: "", className: "", _text: "", _html: "", value: "",
    checked: false, dataset: {}, style: {}, _children: [], _listeners: {},
    classList: {
      _s: new Set(),
      add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); },
      contains(c) { return this._s.has(c); },
    },
    appendChild(c) { this._children.push(c); return c; },
    addEventListener(ev, fn) { (this._listeners[ev] = this._listeners[ev] || []).push(fn); },
    setAttribute(k, v) { if (k === "class") this.className = v; this["_attr_" + k] = v; },
    getAttribute(k) { return this["_attr_" + k]; },
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
function byClass(cls) { return ALL.filter((n) => n.className &&
  n.className.split(" ").indexOf(cls) !== -1); }
// Recursively collect text from a node tree (textContent + child spans).
function deepText(node) {
  let t = node._text || "";
  (node._children || []).forEach((c) => { t += " " + deepText(c); });
  return t;
}

function makeHarness(data) {
  ALL = [];
  const byId = new Map();
  const document = {
    getElementById(id) {
      if (!byId.has(id)) { const n = makeNode(); n.id = id; byId.set(id, n); }
      return byId.get(id);
    },
    createElement(tag) { return makeNode(tag); },
    // intentionally NO createElementNS -> the SVG view uses its text fallback.
    head: makeNode(), body: makeNode(),
  };
  const window = { HARMONIC_NETWORK_DATA: data };
  const sandbox = { window, document, console, Set, Math, Object, Array, String, JSON };
  vm.createContext(sandbox);
  vm.runInContext(
    fs.readFileSync(path.join(ROOT, "beat_selector", "harmonic_network.js"), "utf-8"),
    sandbox, { filename: "harmonic_network.js" });
  return { window, document, ui: window.HarmonicNetwork, byId };
}

let passed = 0;
function assert(cond, msg) {
  if (!cond) { console.error("FAIL:", msg); process.exitCode = 1; throw new Error(msg); }
  passed += 1;
}

const PAYLOAD = loadPayload();

// === Test A: init renders the graph =========================================
(function testInit() {
  const h = makeHarness(PAYLOAD);
  const r = h.ui.init(PAYLOAD);
  assert(r.ok, "init ok");
  assert(r.nodes === 48, "init reports 48 nodes, got " + r.nodes);
  assert(h.ui.visibleNodeCount() === 48, "all 48 nodes visible by default");
  assert(h.ui.nodeIds().length === 48, "48 node ids indexed");
  const counts = h.ui.counts();
  assert(counts && counts.nodesByKind.dominant_seventh === 12, "12 dominant sevenths");
  console.log("Test A (init): PASS");
})();

// === Test B: node-class filters hide/show ===================================
(function testFilters() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);
  h.ui.setFilter({ kinds: { dominant_seventh: false } });
  assert(h.ui.visibleNodeCount() === 36, "hiding dominant sevenths leaves 36, got " +
    h.ui.visibleNodeCount());
  // an edge into a hidden kind is also hidden
  const before = h.ui.visibleEdgeCount();
  h.ui.setFilter({ kinds: { diminished_triad: false } });
  assert(h.ui.visibleNodeCount() === 24, "hiding two kinds leaves 24");
  assert(h.ui.visibleEdgeCount() < before, "edges into hidden kinds are hidden");
  h.ui.setFilter({ kinds: { dominant_seventh: true, diminished_triad: true } });
  assert(h.ui.visibleNodeCount() === 48, "re-showing restores 48");
  console.log("Test B (filters): PASS");
})();

// === Test C: selecting C surfaces Am / G7 / B° ==============================
(function testSelectC() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);
  const sel = h.ui.selectNode("hn:major:C");
  assert(sel === "hn:major:C", "selected C major");
  const nb = h.ui.neighborsOf("hn:major:C");
  assert(nb.indexOf("hn:minor:A") !== -1, "C connects to A minor (relative)");
  assert(nb.indexOf("hn:dom7:G") !== -1, "C connects to G7 (its dominant 7th)");
  assert(nb.indexOf("hn:dim:B") !== -1, "C connects to B° (its leading-tone dim)");
  // the right panel shows the explanation + connected nodes
  const right = h.byId.get("hnRight");
  const txt = deepText(right);
  assert(/Am/.test(txt) && /G7/.test(txt) && /B°/.test(txt),
    "right panel lists related Am / G7 / B°");
  console.log("Test C (select C -> Am/G7/B°): PASS");
})();

// === Test D: selecting G7 explains "resolves to C" ==========================
(function testSelectG7() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);
  h.ui.selectNode("hn:dom7:G");
  const right = h.byId.get("hnRight");
  const txt = deepText(right);
  assert(/resolves to C/i.test(txt), "G7 explanation says it resolves to C");
  assert(/V7/.test(txt), "G7 explanation names it the V7");
  const nb = h.ui.neighborsOf("hn:dom7:G");
  assert(nb.indexOf("hn:major:C") !== -1, "G7 connects to C major");
  console.log("Test D (select G7 -> resolves to C): PASS");
})();

// === Test E: launch queue returns valid specs for implemented drills only ===
(function testLaunch() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);

  // Click the launch button on C major -> queues a real spec.
  h.ui.selectNode("hn:major:C");
  const btns = byClass("launchBtn");
  assert(btns.length >= 1, "C major renders a launch button");
  btns[0].fire("click");
  assert(h.ui.pendingCount() === 1, "one spec queued after click");
  const spec = h.ui.takeLaunch();
  assert(spec && spec.drill === "full_key", "queued spec is a real full_key drill");
  assert(h.ui.takeLaunch() === null, "queue drains to null");

  // The dominant seventh exposes a RESERVED seventh drill (no launch button),
  // plus a launchable triad surrogate (V->I), which is NOT a seventh chord.
  ALL.length = 0;                            // only inspect the next render
  h.ui.selectNode("hn:dom7:G");
  const g7Node = h.ui.nodeById("hn:dom7:G");
  const reserved = g7Node.trainerSpecs.filter((t) => t.status === "reserved");
  assert(reserved.length === 1 && reserved[0].spec === null,
    "G7 seventh drill is reserved with no spec");
  assert(byClass("reservedBadge").length >= 1, "reserved drill shows a badge");
  const g7Btns = byClass("launchBtn");
  assert(g7Btns.length === 1, "G7 shows exactly one (triad surrogate) launch button");
  g7Btns[0].fire("click");
  const surrogate = h.ui.takeLaunch();
  assert(surrogate && surrogate.drill === "function" && surrogate.drill !== "seventh_chord",
    "G7's launchable is a triad drill, never a seventh chord");

  // launching a malformed spec is a no-op
  assert(h.ui.launch(null) === false, "launching null is refused");
  console.log("Test E (launch queue): PASS");
})();

// === Test F: sync highlighting from trainer + atlas =========================
(function testSync() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);
  // a trainer target on the V chord of C major -> highlights G7
  const sel = h.ui.highlightFromTrainerTarget({ key: "C major", mode: "major", roman: "V" });
  assert(sel === "hn:dom7:G", "trainer V-of-C target highlights G7, got " + sel);
  // an Atlas sync on the Gb-major scale (enharmonic of F#) highlights F# major
  const sel2 = h.ui.highlightFromAtlasSync({ scale: "scale:Gb:major" });
  assert(sel2 === "hn:major:F#", "atlas Gb-major sync highlights F# major, got " + sel2);
  // a vii° target highlights the diminished node
  const sel3 = h.ui.highlightFromTrainerTarget({ key: "C major", mode: "major", roman: "vii°" });
  assert(sel3 === "hn:dim:B", "trainer vii°-of-C target highlights B°, got " + sel3);
  console.log("Test F (sync highlighting): PASS");
})();

// === Test G: search + exportState ==========================================
(function testSearchExport() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);
  h.ui.setFilter({ search: "7" });          // all dominant sevenths carry "7"
  const st = h.ui.exportState();
  assert(st.searchHits === 12, "12 nodes match '7', got " + st.searchHits);
  assert(st.visibleNodes === 12, "search narrows visible nodes to the 12 matches");
  h.ui.setFilter({ search: "" });
  assert(h.ui.exportState().visibleNodes === 48, "clearing search restores 48");
  // clearSelection resets selection
  h.ui.selectNode("hn:major:C");
  h.ui.clearSelection();
  assert(h.ui.exportState().selectedNode === null, "clearSelection clears node");
  console.log("Test G (search + exportState): PASS");
})();

console.log("\nAll harmonic_network.js behavioural checks passed (" + passed + " assertions).");
