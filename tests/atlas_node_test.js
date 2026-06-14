/*
 * Headless behavioural test for beat_selector/atlas.js.
 *
 * The GUI can't run in CI, so this stubs the browser globals (window/document),
 * feeds a shape-accurate ATLAS_DATA fixture (matching harmony.atlas.to_json()),
 * loads the Atlas controller via Node's `vm`, and verifies the host-facing API:
 *   - init() builds all tabs and renders without throwing;
 *   - clicking a global-map row / matrix cell enqueues that exercise spec, which
 *     the host picks up via takeLaunch();
 *   - setSync() highlights the active nodes (Part VII);
 *   - hoverRelated() highlights related nodes (Part I);
 *   - tab switching re-renders.
 *
 * Run:  node tests/atlas_node_test.js
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

// --- DOM stub --------------------------------------------------------------
let ALL = [];
function makeNode(tag) {
  const node = {
    tag: tag || "div", id: "", className: "", _text: "", _html: "",
    dataset: {}, style: {}, _children: [], _listeners: {},
    classList: {
      _s: new Set(),
      add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); },
      contains(c) { return this._s.has(c); },
      toggle(c, on) { if (on === undefined) on = !this._s.has(c);
        if (on) this._s.add(c); else this._s.delete(c); return on; },
    },
    appendChild(c) { this._children.push(c); return c; },
    insertBefore(c) { this._children.unshift(c); return c; },
    addEventListener(ev, fn) { (this._listeners[ev] = this._listeners[ev] || []).push(fn); },
    removeAttribute() {}, remove() {},
    setAttribute(k, v) {
      if (k === "class") this.className = v;
      else if (k === "id") this.id = v;
      this["_attr_" + k] = v;
    },
    getAttribute(k) { return this["_attr_" + k]; },
    fire(ev) { (this._listeners[ev] || []).forEach((fn) => fn({})); },
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; },
    querySelectorAll(sel) {
      const cls = sel.replace(/^\./, "").split(/\s|>/)[0].replace(/^\./, "");
      return this._children.filter((c) => c.className &&
        c.className.split(" ").indexOf(cls) !== -1);
    },
  };
  Object.defineProperty(node, "textContent", {
    get() { return this._text; }, set(v) { this._text = v; },
  });
  Object.defineProperty(node, "innerHTML", {
    get() { return this._html; }, set(v) { this._html = v; this._children = []; },
  });
  ALL.push(node);
  return node;
}

function findByData(key, val) {
  return ALL.filter((n) => n.dataset && n.dataset[key] === val);
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
    // intentionally NO createElementNS -> graph view uses its text fallback.
    head: makeNode(), body: makeNode(),
  };
  const window = { ATLAS_DATA: data };
  const sandbox = { window, document, console, Set, Math, Object, Array, String };
  vm.createContext(sandbox);
  vm.runInContext(
    fs.readFileSync(path.join(__dirname, "..", "beat_selector", "atlas.js"), "utf-8"),
    sandbox, { filename: "atlas.js" });
  return { window, document, ui: window.AtlasUI };
}

// --- fixture (matches harmony.atlas.to_json() shape) -----------------------
function spec(id) { return { exercise_id: id, drill: "full_key", title: id }; }

const DATA = {
  schema: "harmony-atlas/v1",
  modes: ["major", "natural_minor"],
  keys: { major: ["C", "G"], natural_minor: ["A", "E"] },
  keySpecs: {
    major: { C: spec("key_C"), G: spec("key_G") },
    natural_minor: { A: spec("key_A"), E: spec("key_E") },
  },
  globalMap: {
    major: [
      { nodeId: "degree:major:I", roman: "I", quality: "major", intervalLayer: "M3+m3", functionLabel: "tonic", scaleDegreeName: "tonic", spec: spec("deg_I") },
      { nodeId: "degree:major:ii", roman: "ii", quality: "minor", intervalLayer: "m3+M3", functionLabel: "predominant", scaleDegreeName: "supertonic", spec: spec("deg_ii") },
    ],
    natural_minor: [
      { nodeId: "degree:natural_minor:i", roman: "i", quality: "minor", intervalLayer: "m3+M3", functionLabel: "tonic", scaleDegreeName: "tonic", spec: spec("deg_i") },
    ],
  },
  transpositionMatrix: {
    major: {
      mode: "major", keys: ["C", "G"], rows: [
        { degreeNodeId: "degree:major:I", roman: "I", rowSpec: spec("row_I"), cells: [
          { nodeId: "triad:C:major:0", key: "C", roman: "I", chordSymbol: "C", chordTones: ["C", "E", "G"], intervalLayer: "M3+m3", spec: spec("cell_C_I") },
          { nodeId: "triad:G:major:0", key: "G", roman: "I", chordSymbol: "G", chordTones: ["G", "B", "D"], intervalLayer: "M3+m3", spec: spec("cell_G_I") },
        ] },
      ],
    },
    natural_minor: { mode: "natural_minor", keys: ["A", "E"], rows: [
      { degreeNodeId: "degree:natural_minor:i", roman: "i", rowSpec: spec("row_i"), cells: [
        { nodeId: "triad:A:natural_minor:0", key: "A", roman: "i", chordSymbol: "Am", chordTones: ["A", "C", "E"], intervalLayer: "m3+M3", spec: spec("cell_A_i") },
      ] },
    ] },
  },
  qualityMatrix: {
    major: [
      { qualityNodeId: "quality:major", quality: "major", intervalLayer: "M3+m3", spec: spec("q_major"), entries: [
        { nodeId: "triad:C:major:0", key: "C", roman: "I", chordSymbol: "C" }] },
    ],
    natural_minor: [
      { qualityNodeId: "quality:minor", quality: "minor", intervalLayer: "m3+M3", spec: spec("q_minor"), entries: [
        { nodeId: "triad:A:natural_minor:0", key: "A", roman: "i", chordSymbol: "Am" }] },
    ],
  },
  functionMap: {
    major: { mode: "major", keys: ["C", "G"], rows: [
      { functionNodeId: "function:major:tonic", functionLabel: "tonic", romans: ["I", "vi", "iii"], cells: [
        { key: "C", chords: [{ chordSymbol: "C" }], spec: spec("fn_C_tonic") },
        { key: "G", chords: [{ chordSymbol: "G" }], spec: spec("fn_G_tonic") }] }] },
    natural_minor: { mode: "natural_minor", keys: ["A", "E"], rows: [
      { functionNodeId: "function:natural_minor:tonic", functionLabel: "tonic", romans: ["i"], cells: [
        { key: "A", chords: [{ chordSymbol: "Am" }], spec: spec("fn_A_tonic") }] }] },
  },
  intervalLayerMap: [
    { layerNodeId: "layer:M3+m3", intervalLayer: "M3+m3", quality: "major", diatonic: true, spec: spec("layer_major") },
    { layerNodeId: "layer:M3+M3", intervalLayer: "M3+M3", quality: "augmented", diatonic: false, spec: null },
  ],
  cadenceMap: [
    { cadenceNodeId: "cadence:ii_v_i_major", label: "ii–V–I", mode: "major", family: "progression", cadenceType: "authentic", tokens: ["ii", "V", "I"], referenceChords: [{ chordSymbol: "Dm" }, { chordSymbol: "G" }, { chordSymbol: "C" }], functionPath: ["predominant", "dominant", "tonic"], keysTable: [{ key: "C", chords: ["Dm", "G", "C"] }], spec: spec("cad_iiVI") },
  ],
  learningPath: [
    { level: 1, id: "scales", title: "Scales", detail: "x" },
    { level: 2, id: "triads", title: "Triads", detail: "x" },
    { level: 3, id: "interval_layers", title: "Interval layers", detail: "x" },
    { level: 4, id: "transposition", title: "Transposition", detail: "x" },
    { level: 5, id: "functions", title: "Functions", detail: "x" },
    { level: 6, id: "cadences", title: "Cadences", detail: "x" },
    { level: 7, id: "real_music", title: "Real music", detail: "x" },
  ],
  progress: { overallPercent: 0, categories: [
    { category: "Scales", total: 2, completed: 0, percent: 0, items: [
      { exerciseId: "key_C", title: "C major", done: false, spec: spec("key_C") }] }] },
  graph: { relations: ["same_quality"], nodes: [
    { id: "degree:major:I", kind: "degree", label: "I", data: {}, spec: spec("g_deg") },
    { id: "quality:major", kind: "quality", label: "major", data: {} }],
    edges: [{ source: "degree:major:I", target: "quality:major", relation: "same_quality" }] },
};

// --- assertions ------------------------------------------------------------
let passed = 0;
function assert(cond, msg) {
  if (!cond) { console.error("FAIL:", msg); process.exitCode = 1; throw new Error(msg); }
  passed += 1;
}

(function testInit() {
  const h = makeHarness(DATA);
  const r = h.ui.init(DATA);
  assert(r.ok, "init ok");
  assert(r.tabs.length === 9, "9 tabs built");
  assert(h.ui.currentTab() === "global", "first tab is global");
  console.log("Test A (init + tabs): PASS");
})();

(function testGlobalClickLaunch() {
  const h = makeHarness(DATA);
  h.ui.init(DATA);
  const row = findByData("node", "degree:major:I")[0];
  assert(row, "global I row rendered");
  row.fire("click");
  const got = h.ui.takeLaunch();
  assert(got && got.exercise_id === "deg_I", "clicking I enqueues its degree spec");
  assert(h.ui.takeLaunch() === null, "queue empty after take");
  console.log("Test B (global click -> launch): PASS");
})();

(function testSyncHighlights() {
  const h = makeHarness(DATA);
  h.ui.init(DATA);
  h.ui.setSync({ degree: "degree:major:I", quality: "quality:major" });
  const s = h.ui.syncState();
  assert(s.indexOf("degree:major:I") !== -1, "sync marks the active degree node");
  console.log("Test C (sync highlight): PASS");
})();

(function testHoverRelated() {
  const h = makeHarness(DATA);
  h.ui.init(DATA);
  // Hover a minor-quality context -> the ii row (minor) lights up.
  h.ui.hoverRelated({ quality: "minor", mode: "major" });
  assert(h.ui.hoverState().indexOf("degree:major:ii") !== -1,
    "hover relates same-quality rows");
  h.ui.clearHover();
  assert(h.ui.hoverState().length === 0, "clearHover clears");
  console.log("Test D (hover related): PASS");
})();

(function testMatrixCellLaunch() {
  const h = makeHarness(DATA);
  h.ui.init(DATA);
  assert(h.ui.showTab("matrix") === "matrix", "switch to matrix");
  const cell = findByData("node", "triad:G:major:0")[0];
  assert(cell, "matrix cell rendered");
  cell.fire("click");
  assert(h.ui.takeLaunch().exercise_id === "cell_G_I", "cell launches its key spec");
  console.log("Test E (matrix cell -> launch): PASS");
})();

(function testAllTabsRender() {
  const h = makeHarness(DATA);
  h.ui.init(DATA);
  h.ui.tabs().forEach((t) => {
    h.ui.showTab(t);
    assert(h.ui.currentTab() === t, "rendered tab " + t + " without throwing");
  });
  console.log("Test F (all tabs render): PASS");
})();

(function testProgressAndCadenceLaunch() {
  const h = makeHarness(DATA);
  h.ui.init(DATA);
  h.ui.showTab("cadences");
  const card = findByData("node", "cadence:ii_v_i_major")[0];
  card.fire("click");
  assert(h.ui.takeLaunch().exercise_id === "cad_iiVI", "cadence card launches its spec");
  console.log("Test G (cadence launch): PASS");
})();

console.log("\nAll atlas.js behavioural checks passed (" + passed + " assertions).");
