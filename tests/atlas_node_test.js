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

// Mirror harmony.atlas._keyboard_keys() so highlighted midis land on real keys.
function kbKeys(lo, hi) {
  const BLACK = { 1: 1, 3: 1, 6: 1, 8: 1, 10: 1 };
  const NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
  const whites = [];
  for (let m = lo; m <= hi; m++) if (!BLACK[m % 12]) whites.push(m);
  const ww = 100 / whites.length, bw = ww * 0.62, wi = {};
  whites.forEach((m, i) => { wi[m] = i; });
  const keys = [];
  for (let m = lo; m <= hi; m++) {
    const pc = m % 12, isB = !!BLACK[pc];
    const k = { midi: m, pc: pc, name: NAMES[pc], octave: Math.floor(m / 12) - 1, isBlack: isB };
    if (isB) { k.leftPct = (wi[m - 1] + 1) * ww - bw / 2; k.widthPct = bw; }
    keys.push(k);
  }
  return keys;
}
function kbNote(midi, name, pc) { return { midi: midi, name: name, pc: pc }; }
function kbThird(position, name, quality, from, fromMidi, to, toMidi, step, stepMidi, path, steps) {
  return {
    position: position, name: name, semitones: quality === "major" ? 4 : 3, quality: quality,
    fromName: from, fromMidi: fromMidi, toName: to, toMidi: toMidi,
    stepName: step, stepMidi: stepMidi, scalePath: path, steps: steps,
    flashMidis: [fromMidi, stepMidi, toMidi],
  };
}
const W = { size: 2, name: "W" }, H = { size: 1, name: "H" };

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
      { nodeId: "degree:major:I", roman: "I", quality: "major", intervalLayer: "M3+m3", functionLabel: "tonic", scaleDegreeName: "tonic", spec: spec("deg_I"),
        keyboard: { referenceKey: "C", referenceLabel: "C major", quality: "major", intervalLayer: "M3+m3",
          chord: { root: kbNote(60, "C", 0), third: kbNote(64, "E", 4), fifth: kbNote(67, "G", 7) },
          thirds: [
            kbThird("lower", "M3", "major", "C", 60, "E", 64, "D", 62, ["C", "D", "E"], [W, W]),
            kbThird("upper", "m3", "minor", "E", 64, "G", 67, "F", 65, ["E", "F", "G"], [W, H]),
          ], structure: "Major triad — major third (M3) below, minor third (m3) above." } },
      { nodeId: "degree:major:ii", roman: "ii", quality: "minor", intervalLayer: "m3+M3", functionLabel: "predominant", scaleDegreeName: "supertonic", spec: spec("deg_ii"),
        keyboard: { referenceKey: "C", referenceLabel: "C major", quality: "minor", intervalLayer: "m3+M3",
          chord: { root: kbNote(62, "D", 2), third: kbNote(65, "F", 5), fifth: kbNote(69, "A", 9) },
          thirds: [
            kbThird("lower", "m3", "minor", "D", 62, "F", 65, "E", 64, ["D", "E", "F"], [W, H]),
            kbThird("upper", "M3", "major", "F", 65, "A", 69, "G", 67, ["F", "G", "A"], [W, W]),
          ], structure: "Minor triad — minor third (m3) below, major third (M3) above." } },
    ],
    natural_minor: [
      { nodeId: "degree:natural_minor:i", roman: "i", quality: "minor", intervalLayer: "m3+M3", functionLabel: "tonic", scaleDegreeName: "tonic", spec: spec("deg_i"),
        keyboard: { referenceKey: "A", referenceLabel: "A minor", quality: "minor", intervalLayer: "m3+M3",
          chord: { root: kbNote(69, "A", 9), third: kbNote(72, "C", 0), fifth: kbNote(76, "E", 4) },
          thirds: [
            kbThird("lower", "m3", "minor", "A", 69, "C", 72, "B", 71, ["A", "B", "C"], [W, H]),
            kbThird("upper", "M3", "major", "C", 72, "E", 76, "D", 74, ["C", "D", "E"], [W, W]),
          ], structure: "Minor triad — minor third (m3) below, major third (M3) above." } },
    ],
  },
  keyboardKeys: kbKeys(60, 77),
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

(function testKeyboardRenders() {
  const h = makeHarness(DATA);
  h.ui.init(DATA);                       // global tab is default -> keyboard built
  const card = ALL.filter((n) => n.className &&
    n.className.split(" ").indexOf("kbCard") !== -1)[0];
  assert(card, "keyboard card rendered under the global map");
  assert(h.ui.keyboardKeyCount() === DATA.keyboardKeys.length,
    "every keyboard key node is built (" + DATA.keyboardKeys.length + ")");
  console.log("Test H (keyboard renders): PASS");
})();

(function testKeyboardDefaultIsTonic() {
  const h = makeHarness(DATA);
  h.ui.init(DATA);
  // First row I = C-E-G with D/F passing tones.
  assert(h.ui.keyboardRoleOf(60).indexOf("root") !== -1, "default root C(60)");
  assert(h.ui.keyboardRoleOf(64).indexOf("third") !== -1, "default third E(64)");
  assert(h.ui.keyboardRoleOf(67).indexOf("fifth") !== -1, "default fifth G(67)");
  assert(h.ui.keyboardRoleOf(62).indexOf("stepTone") !== -1, "lower passing D(62)");
  assert(h.ui.keyboardRoleOf(65).indexOf("stepTone") !== -1, "upper passing F(65)");
  console.log("Test I (keyboard default = tonic triad): PASS");
})();

(function testKeyboardRetargetsOnHover() {
  const h = makeHarness(DATA);
  h.ui.init(DATA);
  const iiRow = findByData("node", "degree:major:ii")[0];
  assert(iiRow, "ii row present");
  iiRow.fire("mouseenter");              // hover retargets the shared keyboard
  assert(h.ui.keyboardRoleOf(62).indexOf("root") !== -1, "retarget: D(62) now root");
  assert(h.ui.keyboardRoleOf(60).indexOf("root") === -1, "retarget: old root C(60) cleared");
  assert(h.ui.keyboardRoleOf(69).indexOf("fifth") !== -1, "retarget: A(69) now fifth");
  const kb = h.ui.currentKeyboard();
  assert(kb && kb.intervalLayer === "m3+M3", "retarget: payload updated to ii (m3+M3)");
  console.log("Test J (keyboard retargets on hover): PASS");
})();

(function testRowClickStillLaunchesWithKeyboard() {
  const h = makeHarness(DATA);
  h.ui.init(DATA);
  const row = findByData("node", "degree:major:ii")[0];
  row.fire("click");                     // click contract unchanged by keyboard
  assert(h.ui.takeLaunch().exercise_id === "deg_ii", "row click still launches its spec");
  console.log("Test K (row click unaffected by keyboard): PASS");
})();

console.log("\nAll atlas.js behavioural checks passed (" + passed + " assertions).");
