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
 *   - a dominant-seventh node launches its real V7->I drill (ticket 12);
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

  // The dominant seventh launches its REAL V7->I drill (ticket 12): no
  // reserved placeholder, no badge, exactly one launch button.
  ALL.length = 0;                            // only inspect the next render
  h.ui.selectNode("hn:dom7:G");
  const g7Node = h.ui.nodeById("hn:dom7:G");
  const reserved = g7Node.trainerSpecs.filter((t) => t.status === "reserved");
  assert(reserved.length === 0, "G7 carries no reserved entry any more");
  assert(byClass("reservedBadge").length === 0, "no reserved badge rendered");
  const g7Btns = byClass("launchBtn");
  assert(g7Btns.length === 1, "G7 shows exactly one (V7 drill) launch button");
  g7Btns[0].fire("click");
  const v7spec = h.ui.takeLaunch();
  assert(v7spec && v7spec.drill === "function", "G7's launchable is a function drill");
  assert(Array.isArray(v7spec.pattern) && v7spec.pattern[0] === "V7",
    "G7's queued drill is the real V7 resolution, got " + JSON.stringify(v7spec.pattern));

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

// === Test H: launch hardening + debug state (PATCH 1) =======================
(function testLaunchHardening() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);

  // A launchable click queues exactly one spec and records it in lastLaunch.
  h.ui.selectNode("hn:major:C");
  byClass("launchBtn")[0].fire("click");
  assert(h.ui.pendingCount() === 1, "launchable click queues one spec");
  let ll = h.ui.lastLaunch();
  assert(ll && ll.queued === true && ll.drill === "full_key",
    "lastLaunch records the queued full_key drill");
  assert(h.ui.exportState().lastLaunch.queued === true, "exportState surfaces lastLaunch");
  const drained = h.ui.takeLaunch();
  assert(drained && drained.drill === "full_key", "takeLaunch drains exactly the queued spec");
  assert(h.ui.takeLaunch() === null, "queue holds exactly one -> second drain is null");

  // Malformed specs are refused with a reason.
  assert(h.ui.launch({}) === false, "spec without a drill is refused");
  assert(h.ui.launch(null) === false, "null spec is refused");
  assert(h.ui.lastLaunch().reason === "missing-or-malformed-spec", "reason recorded");

  // The G7 node's launch button queues the real V7 drill (ticket 12).
  ALL.length = 0;
  h.ui.selectNode("hn:dom7:G");
  const g7 = h.ui.nodeById("hn:dom7:G");
  assert(g7.trainerSpecs.every((t) => t.status === "launchable" && t.spec),
    "every G7 trainer entry is launchable with a real spec");
  assert(byClass("reservedBadge").length === 0, "no reserved badge anywhere");
  assert(byClass("launchBtn").length === 1, "G7 exposes exactly one launch button");
  byClass("launchBtn")[0].fire("click");
  ll = h.ui.lastLaunch();
  assert(ll.queued === true && ll.drill === "function",
    "lastLaunch records the queued V7 function drill");
  const queued = h.ui.takeLaunch();
  assert(queued && queued.pattern && queued.pattern[0] === "V7",
    "the queued spec carries the V7 pattern");
  console.log("Test H (launch hardening + debug state): PASS");
})();

// === Test I: edge styles solid/dashed/dotted + markers (PATCH 2) ============
(function testEdgeStyles() {
  const h = makeHarness(PAYLOAD);
  h.document.createElementNS = function (ns, tag) { return makeNode(tag); };  // SVG path
  h.ui.init(PAYLOAD);

  // The dash style mapping is the shared source of truth.
  assert(h.ui.edgeStyleOf("fifth") === "solid", "fifth_relation -> solid");
  assert(h.ui.edgeStyleOf("relative") === "dashed", "relative_minor_of -> dashed");
  assert(h.ui.edgeStyleOf("resolve") === "solid", "resolves_to -> solid");
  assert(h.ui.edgeStyleOf("leading") === "solid", "leading_tone_to -> solid");
  assert(h.ui.edgeStyleOf("function") === "dotted", "same_function -> dotted");
  assert(h.ui.edgeStyleOf("shared") === "dashed", "shares_scale_with -> dashed");

  // Rendered SVG paths carry both the visual-class and the relation classes.
  const relEdges = byClass("edge--relative").filter(
    (n) => n.className.indexOf("relation--relative_minor_of") !== -1);
  assert(relEdges.length >= 1, "relative_minor_of renders with the dashed edge--relative class");
  assert(byClass("edge--fifth").length >= 1, "fifth_relation renders with the solid edge--fifth class");

  // A directed resolves_to edge keeps its arrow marker.
  const resolveEdges = byClass("relation--resolves_to");
  assert(resolveEdges.length >= 1, "resolves_to edges are rendered");
  assert(resolveEdges.some((p) => /url\(#arw-/.test(p.getAttribute("marker-end") || "")),
    "a resolves_to edge has a directed marker-end");

  // Toggling a relation's visibility does not strip the style class: hide then
  // re-show same_function and confirm a specific edge returns with its classes.
  const fnEdgeId = PAYLOAD.edges.filter((e) => e.relation === "same_function")[0].id;
  ALL.length = 0;
  h.ui.setFilter({ relations: { same_function: false } });
  assert(byClass("edge--function").length === 0, "same_function off -> its edges are hidden");
  ALL.length = 0;
  h.ui.setFilter({ relations: { same_function: true } });
  const reshown = byClass("relation--same_function");
  assert(reshown.length >= 1, "same_function back on -> its edges render again");
  assert(reshown.every((p) => p.className.indexOf("edge--function") !== -1),
    "re-shown same_function edges still carry the edge--function style class");
  console.log("Test I (edge styles + markers + toggle preserves class): PASS, fnEdge=" + fnEdgeId);
})();

// === Test J: trainer-target sync highlight (PATCH 4) ========================
(function testSyncHighlight() {
  const h = makeHarness(PAYLOAD);
  h.document.createElementNS = function (ns, tag) { return makeNode(tag); };
  h.ui.init(PAYLOAD);
  function gById(id) {
    return ALL.filter((n) => n.getAttribute && n.getAttribute("data-id") === id);
  }

  // C major I -> sync-highlight the C-major node (primary gets node--flash).
  ALL.length = 0;
  let p = h.ui.highlightFromTrainerTarget(
    { key: "C major", mode: "major", roman: "I", root: "C", quality: "major" });
  assert(p === "hn:major:C", "C major I highlights hn:major:C, got " + p);
  let g = gById("hn:major:C");
  assert(g.length === 1 && g[0].className.indexOf("node--sync") !== -1, "C node has node--sync");
  assert(g[0].className.indexOf("node--flash") !== -1, "C node (primary) has node--flash");

  // A natural minor i -> hn:minor:A.
  assert(h.ui.highlightFromTrainerTarget(
    { key: "A", mode: "natural_minor", roman: "i", root: "A", quality: "minor" }) === "hn:minor:A",
    "A natural minor i highlights hn:minor:A");

  // C major vii° (B° diminished) -> hn:dim:B.
  assert(h.ui.highlightFromTrainerTarget(
    { key: "C", mode: "major", roman: "vii°", root: "B", quality: "diminished" }) === "hn:dim:B",
    "C major vii° highlights hn:dim:B");

  // C major V -> primary G7 + the C-major key as context; the G7->C edge syncs.
  ALL.length = 0;
  let pv = h.ui.highlightFromTrainerTarget(
    { key: "C", mode: "major", roman: "V", root: "G", quality: "major" });
  assert(pv === "hn:dom7:G", "C major V primary is hn:dom7:G, got " + pv);
  const sn = h.ui.syncNodes();
  assert(sn.indexOf("hn:dom7:G") !== -1 && sn.indexOf("hn:major:C") !== -1,
    "V syncs both G7 and the C-major key context");
  assert(byClass("edge--sync").length >= 1, "the edge joining the two synced nodes is lit");

  // D major V / A7 -> hn:dom7:A.
  assert(h.ui.highlightFromTrainerTarget(
    { key: "D", mode: "major", roman: "V", root: "A", quality: "major" }) === "hn:dom7:A",
    "D major V highlights hn:dom7:A");
  // Natural-minor VII is a MAJOR subtonic, not a diminished -> falls back to key node.
  assert(h.ui.highlightFromTrainerTarget(
    { key: "A", mode: "natural_minor", roman: "VII", root: "G", quality: "major" }) === "hn:minor:A",
    "Am VII (major subtonic) is not mistaken for a diminished node");

  // Selection and sync highlight coexist.
  h.ui.selectNode("hn:major:C");
  ALL.length = 0;
  h.ui.highlightFromTrainerTarget({ key: "C", mode: "major", roman: "V", root: "G", quality: "major" });
  const st = h.ui.exportState();
  assert(st.selectedNode === "hn:major:C", "selection persists beneath the sync highlight");
  assert(st.syncNodes.indexOf("hn:dom7:G") !== -1, "sync coexists with the active selection");
  const cg = gById("hn:major:C"), gg = gById("hn:dom7:G");
  assert(cg.length === 1 && cg[0].className.indexOf("sel") !== -1, "C keeps its selection (sel) class");
  assert(gg.length === 1 && gg[0].className.indexOf("node--sync") !== -1, "G7 is synced while C stays selected");
  console.log("Test J (trainer-target sync highlight + coexistence): PASS");
})();

// === Test K: CSS dash styles match the JS EDGE_STYLE map (PATCH 2 drift guard) ===
// The dashed/solid/dotted distinction is the PRIMARY visual signal (e.g. fifth and
// same_pitch_class share a grey colour and are told apart ONLY by the dash). That
// style lives in two hand-maintained copies -- JS EDGE_STYLE (edgeStyleOf) and the
// CSS .edge--<vc> stroke-dasharray. This asserts they cannot silently diverge.
(function testDashConsistency() {
  const css = fs.readFileSync(
    path.join(ROOT, "beat_selector", "harmonic_network.css"), "utf-8");
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);
  const VCS = ["fifth", "relative", "dominant", "resolve", "leading", "shared",
    "samepc", "function", "trainer", "atlas", "reserved"];
  function cssCategory(vc) {
    const m = new RegExp("\\.edge\\.edge--" + vc + "\\s*\\{([^}]*)\\}").exec(css);
    assert(m, "CSS defines a .edge.edge--" + vc + " rule");
    const da = /stroke-dasharray\s*:\s*([^;]+)/.exec(m[1]);
    assert(da, "edge--" + vc + " sets stroke-dasharray");
    const val = da[1].trim();
    if (val === "none") return "solid";
    return parseFloat(val.split(/[\s,]+/)[0]) <= 2 ? "dotted" : "dashed";
  }
  VCS.forEach(function (vc) {
    const cssCat = cssCategory(vc), jsCat = h.ui.edgeStyleOf(vc);
    assert(cssCat === jsCat,
      "edge--" + vc + ": CSS dash (" + cssCat + ") matches edgeStyleOf (" + jsCat + ")");
  });
  console.log("Test K (CSS<->JS dash-style consistency): PASS");
})();

// --- load a real Drill->Graph projection from Python ------------------------
function loadProjection() {
  const candidates = [
    path.join(ROOT, ".venv", "Scripts", "python.exe"),
    path.join(ROOT, ".venv", "bin", "python"),
    "python", "python3",
  ];
  const code =
    "import json;from harmony.harmonic_network import build_network;" +
    "from harmony.network_template import get_template;" +
    "from harmony.network_projection import project_harmony_exercise;" +
    "from harmony.atlas import full_key_spec;" +
    "net=build_network(get_template());" +
    "print(json.dumps(project_harmony_exercise(full_key_spec('C','major'),net).to_dict()))";
  for (const py of candidates) {
    try {
      const out = cp.execFileSync(py, ["-c", code],
        { cwd: ROOT, encoding: "utf-8", maxBuffer: 64 * 1024 * 1024 });
      return JSON.parse(out);
    } catch (e) { /* next */ }
  }
  console.error("SKIP: could not build projection payload.");
  process.exit(0);
}

const PROJECTION = loadProjection();

// timeline / summary container helpers (the stub's global ALL accumulates across
// re-renders, so we inspect the actual container's live children instead).
function timelineChips(h) { return h.byId.get("hnTimeline")._children; }
function summaryChildren(h) { return h.byId.get("hnSummary")._children; }
function hasClass(n, c) { return n.className && n.className.split(" ").indexOf(c) !== -1; }

// === Test L: projection ingestion + timeline ================================
(function testProjectionIngestion() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);
  const st = h.ui.setProjection(PROJECTION);
  assert(st.mode === "drill_to_graph", "setProjection enters drill_to_graph mode");
  assert(st.projection && st.projection.steps === 7, "projection has 7 steps");
  assert(st.nextOccurrence === PROJECTION.steps[0].occurrenceId,
    "next starts at the first occurrence");
  // occurrence timeline chips (el()-built -> visible headlessly)
  assert(timelineChips(h).length === 7, "timeline shows 7 occurrence chips, got " +
    timelineChips(h).length);
  assert(timelineChips(h).every((c) => hasClass(c, "occChip")), "each timeline item is a chip");
  // projection summary rendered
  assert(summaryChildren(h).some((c) => hasClass(c, "sumTitle")),
    "projection summary title rendered");
  console.log("Test L (projection ingestion + timeline): PASS");
})();

// === Test M: flow-state advances current/visited/next =======================
(function testFlowState() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);
  h.ui.setProjection(PROJECTION);
  const occ0 = PROJECTION.steps[0].occurrenceId;
  const occ1 = PROJECTION.steps[1].occurrenceId;
  const occ2 = PROJECTION.steps[2].occurrenceId;
  let st = h.ui.updateFlowState({ sequenceIndex: 0 });
  assert(st.currentOccurrence === occ0, "current is occurrence 0");
  assert(st.nextOccurrence === occ1, "next is occurrence 1");
  st = h.ui.updateFlowState({ sequenceIndex: 1 });
  assert(st.currentOccurrence === occ1, "current advances to occurrence 1");
  assert(st.nextOccurrence === occ2, "next advances to occurrence 2");
  assert(st.visited === 1, "occurrence 0 is now visited");
  // exactly one chip in the LIVE timeline is current, and it is occ1's chip
  const chips = timelineChips(h);
  const cur = chips.filter((c) => hasClass(c, "is-current"));
  assert(cur.length === 1, "exactly one chip is current, got " + cur.length);
  assert(cur[0].dataset.occ === occ1, "the current chip is occurrence 1");
  console.log("Test M (flow state current/next/visited): PASS");
})();

// === Test N: timeline click + graph seek enqueue a host request =============
(function testSeekRequests() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);
  h.ui.setProjection(PROJECTION);
  // clicking a timeline chip requests a seek to that occurrence
  timelineChips(h)[3].fire("click");
  const req = h.ui.takeHostRequest();
  assert(req && req.type === "seek", "timeline click enqueues a seek request");
  assert(req.sequenceIndex === 3, "seek targets sequence index 3, got " + req.sequenceIndex);
  assert(h.ui.takeHostRequest() === null, "the queue drains to null");
  // requestSeek API also enqueues
  h.ui.requestSeek(PROJECTION.steps[5].occurrenceId);
  assert(h.ui.takeHostRequest().sequenceIndex === 5, "requestSeek enqueues by occurrence");
  console.log("Test N (seek host requests): PASS");
})();

// === Test O: clearProjection resets to explore ==============================
(function testClearProjection() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);
  h.ui.setProjection(PROJECTION);
  const st = h.ui.clearProjection();
  assert(st.mode === "explore", "clearProjection returns to explore mode");
  assert(st.projection === null, "projection is cleared");
  assert(timelineChips(h).length === 0, "timeline is empty after clear");
  console.log("Test O (clear projection): PASS");
})();

// === Test P: v1 payload compatibility (no projection) =======================
(function testV1Compat() {
  const h = makeHarness(PAYLOAD);
  const r = h.ui.init(PAYLOAD);
  assert(r.nodes === 48, "legacy v1 payload still inits 48 nodes");
  const st = h.ui.exportState();
  assert(st.mode === "explore", "no projection -> explore mode");
  assert(st.projection === null, "no projection by default");
  // legacy trainer-target sync still works alongside the new layer
  h.ui.highlightFromTrainerTarget({ key: "C major", mode: "major", roman: "V" });
  assert(h.ui.exportState().syncNodes.length >= 1, "highlightFromTrainerTarget still syncs");
  console.log("Test P (v1 payload compatibility): PASS");
})();

// === Test Q: proxy nodes + overlay edges render under SVG ====================
(function testProxyRendering() {
  const h = makeHarness(PAYLOAD);
  h.document.createElementNS = function (ns, tag) {
    const n = makeNode(tag); n._ns = ns; return n;
  };
  h.ui.init(PAYLOAD);
  h.ui.setProjection(PROJECTION);
  // proxy triad nodes (I, ii, iii, IV, vi) render as SVG <g> with data-id + is-proxy
  const proxies = byClass("is-proxy");
  assert(proxies.length === PROJECTION.projectionNodes.length,
    "all proxy nodes render, got " + proxies.length);
  assert(proxies.every((p) => p.getAttribute("data-id")),
    "each proxy carries a data-id (host/tests locate it)");
  // overlay sequence edges render
  assert(byClass("overlay-seq").length >= 1, "sequence overlay edges render");
  // the exact-diminished step marks its canonical node in-projection
  h.ui.updateFlowState({ sequenceIndex: 6 });  // vii° -> hn:dim:B
  const cur = byClass("is-current");
  assert(cur.length >= 1, "the current canonical/proxy node is lit");
  console.log("Test Q (proxy + overlay rendering): PASS");
})();

console.log("\nAll harmonic_network.js behavioural checks passed (" + passed + " assertions).");
