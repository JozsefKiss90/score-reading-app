/*
 * Headless behavioural test for the progressive-journey additions to
 * beat_selector/harmonic_network.js (the Functional Degree Network layer).
 *
 * Loads the REAL functional payload from Python
 * (harmony.functional_network.build_functional_network_payload) plus the
 * legacy v1 payload (harmony.harmonic_network) and verifies the host-facing
 * contract of the three additive APIs:
 *   - setVisibleNodes(ids|null) whitelists nodes AND their edges on top of
 *     the kind/relation filters (stage reveal without re-init);
 *   - markCompleted(ids)/completedIds() persist across re-renders and render
 *     the node--done class; unlit-by-default applies to progressive payloads;
 *   - highlightFromDegreeTarget(t) resolves the EXACT degree node by id
 *     (fnet:deg:<tonic>:<degreeNumber-1>), adds the function group, lights
 *     the exercised edge when the next chord is passed, and falls back to
 *     the legacy pitch-class highlight on non-fnet payloads;
 *   - degree-node clicks queue real launchable specs (no reserved drills
 *     exist anywhere in this graph).
 *
 * Run:  node tests/functional_network_node_test.js
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const cp = require("child_process");

const ROOT = path.join(__dirname, "..");

// --- load the real payloads from Python -------------------------------------
function loadPayload(code) {
  const candidates = [
    path.join(ROOT, ".venv", "Scripts", "python.exe"),
    path.join(ROOT, ".venv", "bin", "python"),
    "python", "python3",
  ];
  for (const py of candidates) {
    try {
      const out = cp.execFileSync(py, ["-c", code],
        { cwd: ROOT, encoding: "utf-8", maxBuffer: 64 * 1024 * 1024 });
      return JSON.parse(out);
    } catch (e) { /* try the next interpreter */ }
  }
  console.error("SKIP: could not run Python to build the payload.");
  process.exit(0);
}

const PAYLOAD = loadPayload(
  "import json;from harmony.functional_network import build_functional_network_payload;" +
  "print(json.dumps(build_functional_network_payload()))");
const LEGACY = loadPayload(
  "import json;from harmony.harmonic_network import build_network_payload;" +
  "print(json.dumps(build_network_payload()))");

// --- minimal DOM harness (mirrors harmonic_network_node_test.js) ------------
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

function makeHarness(data, withSvg) {
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
  if (withSvg) document.createElementNS = function (ns, tag) { return makeNode(tag); };
  const window = { HARMONIC_NETWORK_DATA: data };
  const sandbox = { window, document, console, Set, Math, Object, Array, String, JSON,
    parseInt, Infinity };
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

const C_DEGREES = [0, 1, 2, 3, 4, 5, 6].map((i) => "fnet:deg:C:" + i);

// === Test A: init indexes the functional payload =============================
(function testInit() {
  const h = makeHarness(PAYLOAD);
  const r = h.ui.init(PAYLOAD);
  assert(r.ok, "init ok");
  assert(r.nodes === 44, "init reports 44 nodes, got " + r.nodes);
  assert(h.ui.visibleNodeCount() === 44, "all 44 nodes visible by default");
  const counts = h.ui.counts();
  assert(counts.nodesByKind.degree_triad === 28, "28 degree triads");
  assert(counts.nodesByKind.function_group === 12, "12 function groups");
  assert(counts.nodesByKind.key_hub === 4, "4 key hubs");
  assert(counts.reservedDrills === 0, "no reserved drills anywhere");
  console.log("Test A (init): PASS");
})();

// === Test B: setVisibleNodes whitelist (the stage reveal) ====================
(function testWhitelist() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);
  const st = h.ui.setVisibleNodes(C_DEGREES);
  assert(st.visibleWhitelist === 7, "whitelist size is exported");
  assert(h.ui.visibleNodeCount() === 7, "whitelist narrows to the 7 C degrees");
  // edges into whitelisted-out nodes are hidden; intra-whitelist edges remain
  assert(h.ui.visibleEdgeCount() > 0, "intra-whitelist edges stay visible");
  h.ui.setFilter({ relations: { resolves_to: false, prepares: false,
    tonic_substitute: false, deceptive_to: false, function_member: false,
    shared_triad: false, fifth_relation: false, in_key: false } });
  assert(h.ui.visibleEdgeCount() === 0, "all relations off -> no edges");
  h.ui.setFilter({ relations: { resolves_to: true } });
  assert(h.ui.visibleEdgeCount() === 2,
    "resolves_to inside the C panel is V->I and vii°->I, got " + h.ui.visibleEdgeCount());
  // widen the whitelist: stage transitions grow the graph without re-init
  h.ui.setVisibleNodes(C_DEGREES.concat(["fnet:fn:C:tonic"]));
  assert(h.ui.visibleNodeCount() === 8, "whitelist grows to 8");
  // unknown ids are ignored rather than ghost-counted
  h.ui.setVisibleNodes(["fnet:deg:C:0", "fnet:deg:C:99"]);
  assert(h.ui.visibleNodeCount() === 1, "unknown whitelist ids are dropped");
  // null clears the whitelist entirely
  const st2 = h.ui.setVisibleNodes(null);
  assert(st2.visibleWhitelist === null, "null clears the whitelist");
  assert(h.ui.visibleNodeCount() === 44, "clearing restores all 44");
  // selection survives the whole staging dance
  h.ui.selectNode("fnet:deg:C:4");
  h.ui.setVisibleNodes(C_DEGREES);
  assert(h.ui.exportState().selectedNode === "fnet:deg:C:4",
    "selection survives setVisibleNodes");
  // the info panel's "Connected nodes" pills are gated by the whitelist too:
  // no not-yet-revealed (cross-panel / function / hub) neighbours leak.
  ALL.length = 0;
  h.ui.selectNode("fnet:deg:C:0");
  const gated = byClass("ctxPill").length;
  h.ui.setVisibleNodes(null);
  ALL.length = 0;
  h.ui.selectNode("fnet:deg:C:0");
  const open = byClass("ctxPill").length;
  assert(gated < open,
    "whitelist hides off-stage neighbour pills (" + gated + " < " + open + ")");
  console.log("Test B (setVisibleNodes whitelist): PASS");
})();

// === Test C: markCompleted + unlit default (SVG classes) =====================
(function testCompleted() {
  const h = makeHarness(PAYLOAD, true);
  h.ui.init(PAYLOAD);
  function gById(id) {
    return ALL.filter((n) => n.getAttribute && n.getAttribute("data-id") === id);
  }
  // progressive payload -> every node starts unlit
  ALL.length = 0;
  h.ui.setFilter({});                       // force a render we can inspect
  let c0 = gById("fnet:deg:C:0");
  assert(c0.length === 1 && c0[0].className.indexOf("node--unlit") !== -1,
    "progressive payload renders unlit nodes by default");
  // marking lights it (node--done) and drops the unlit class
  ALL.length = 0;
  const size = h.ui.markCompleted(["fnet:deg:C:0", "fnet:deg:C:4", "nope"]);
  assert(size === 2, "markCompleted counts only known ids, got " + size);
  c0 = gById("fnet:deg:C:0");
  assert(c0[0].className.indexOf("node--done") !== -1, "completed node is node--done");
  assert(c0[0].className.indexOf("node--unlit") === -1, "done node is no longer unlit");
  // survives re-renders (filter changes, whitelist changes)
  h.ui.setVisibleNodes(C_DEGREES);
  h.ui.setFilter({ relations: { in_key: true } });
  ALL.length = 0;
  h.ui.setFilter({});                       // final render to inspect
  c0 = gById("fnet:deg:C:0");
  assert(c0.length === 1 && c0[0].className.indexOf("node--done") !== -1,
    "node--done survives re-render");
  assert(h.ui.completedIds().sort().join(",") === "fnet:deg:C:0,fnet:deg:C:4",
    "completedIds reports the set");
  assert(h.ui.exportState().completed === 2, "exportState surfaces the count");
  // a fresh init clears the session set (host re-applies persisted progress)
  h.ui.init(PAYLOAD);
  assert(h.ui.completedIds().length === 0, "init clears the completed set");
  console.log("Test C (markCompleted + unlit): PASS");
})();

// === Test D: sublabels render for functional nodes ===========================
(function testSublabels() {
  const h = makeHarness(PAYLOAD, true);
  h.ui.init(PAYLOAD);
  const subs = byClass("sub");
  assert(subs.length >= 44, "every functional node renders a sublabel, got " + subs.length);
  assert(subs.some((n) => n._text === "G"), "V-of-C sublabel shows the concrete G triad");
  console.log("Test D (sublabels): PASS");
})();

// === Test E: exact-id degree highlight + exercised edge ======================
(function testDegreeHighlight() {
  const h = makeHarness(PAYLOAD, true);
  h.ui.init(PAYLOAD);
  // the acceptance example from the plan: degreeNumber 5 in C -> fnet:deg:C:4
  let p = h.ui.highlightFromDegreeTarget({ key: "C major", degreeNumber: 5 });
  assert(p === "fnet:deg:C:4", "C major degree 5 -> fnet:deg:C:4, got " + p);
  let sn = h.ui.syncNodes();
  assert(sn.indexOf("fnet:fn:C:dominant") !== -1,
    "the V highlight includes its function group (D)");
  // with the NEXT chord passed, the exercised V->I edge lights up
  ALL.length = 0;
  p = h.ui.highlightFromDegreeTarget(
    { key: "C major", degreeNumber: 5, nextKey: "C major", nextDegreeNumber: 1 });
  assert(p === "fnet:deg:C:4", "primary stays the current degree");
  sn = h.ui.syncNodes();
  assert(sn.indexOf("fnet:deg:C:0") !== -1, "next chord joins the sync set");
  const litEdges = byClass("edge--sync");
  assert(litEdges.length >= 1, "the exercised edge is lit");
  assert(litEdges.some((e) => e.className.indexOf("relation--resolves_to") !== -1),
    "the lit edge is the V->I resolves_to arrow");
  // a key outside the journey clears the sync rather than guessing
  assert(h.ui.highlightFromDegreeTarget({ key: "Ab major", degreeNumber: 2 }) === null,
    "unknown journey key clears the sync (null primary)");
  assert(h.ui.syncNodes().length === 0, "no stale sync nodes remain");
  // the graph is major-only: a minor-mode target clears rather than landing
  // on the same-tonic MAJOR panel node
  assert(h.ui.highlightFromDegreeTarget(
    { key: "C", mode: "natural_minor", degreeNumber: 1 }) === null,
    "minor-mode target clears the sync");
  assert(h.ui.syncNodes().length === 0, "minor target leaves no sync nodes");
  // selection coexists with the degree sync (same contract as the v1 sync)
  h.ui.selectNode("fnet:deg:C:0");
  h.ui.highlightFromDegreeTarget({ key: "G major", degreeNumber: 5, roman: "V" });
  const st = h.ui.exportState();
  assert(st.selectedNode === "fnet:deg:C:0", "selection persists under sync");
  assert(st.syncPrimary === "fnet:deg:G:4", "G major V syncs fnet:deg:G:4");
  console.log("Test E (highlightFromDegreeTarget): PASS");
})();

// === Test F: legacy payloads fall back to the pitch-class highlight ==========
(function testLegacyFallback() {
  const h = makeHarness(LEGACY);
  h.ui.init(LEGACY);
  const p = h.ui.highlightFromDegreeTarget(
    { key: "C major", mode: "major", roman: "V", degreeNumber: 5 });
  assert(p === "hn:dom7:G",
    "legacy payload routes through highlightFromTrainerTarget, got " + p);
  // and the legacy payload renders nothing unlit (not progressive)
  const h2 = makeHarness(LEGACY, true);
  h2.ui.init(LEGACY);
  assert(byClass("node--unlit").length === 0, "legacy nodes are never unlit");
  console.log("Test F (legacy fallback): PASS");
})();

// === Test G: degree-node clicks queue real launchable specs ==================
(function testLaunch() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);
  h.ui.selectNode("fnet:deg:C:4");
  const btns = byClass("launchBtn");
  assert(btns.length === 1, "the V degree renders exactly one launch button");
  assert(byClass("reservedBadge").length === 0, "no reserved badge anywhere");
  btns[0].fire("click");
  const spec = h.ui.takeLaunch();
  assert(spec && spec.drill === "function", "queued spec is a function drill");
  assert(JSON.stringify(spec.pattern) === JSON.stringify(["V", "I"]),
    "V node drills V–I");
  assert(h.ui.takeLaunch() === null, "queue drains");
  // key hub launches the full-key drill
  h.ui.selectNode("fnet:key:G");
  byClass("launchBtn").slice(-1)[0].fire("click");
  const hub = h.ui.takeLaunch();
  assert(hub && hub.drill === "full_key" && hub.key === "G major",
    "key hub drills the full key");
  console.log("Test G (launch queue): PASS");
})();

console.log("\nAll functional_network journey checks passed (" + passed + " assertions).");
