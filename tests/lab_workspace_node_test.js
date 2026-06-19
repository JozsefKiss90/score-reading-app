/*
 * Headless behavioural test for the Music Theory Laboratory workspace web UIs:
 *   - beat_selector/harmony_lab.js      (left panel: concept theory + example explanation + sync)
 *   - beat_selector/lab_cheatsheet.js   (right tab: cheatsheet)
 *   - beat_selector/lab_mapping.js      (right tab: current mapping)
 *   - beat_selector/harmony_circle.js   (right tab: lab-launch affordances)
 *
 * The GUI can't run in CI, so this stubs the browser globals and loads each
 * controller via Node's `vm`, then checks the integration-facing behaviour the
 * Qt host depends on (Part 10.4):
 *   - HarmonyLab renders concept theory from the embedded explanation;
 *   - HarmonyLab renders the example explanation pushed by the host;
 *   - a sync update changes the current "Now playing" explanation;
 *   - the Cheatsheet panel renders the degree patterns / interval layers / functions;
 *   - the Current Mapping panel renders the per-measure mapping rows;
 *   - the Circle (with labLaunch) enqueues "Open ... lab" requests for the host.
 *
 * Run:  node tests/lab_workspace_node_test.js
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

// --- DOM/window stub -------------------------------------------------------
function makeHarness() {
  const ALL = [];
  function makeNode(tag) {
    const node = {
      tag: tag || "div", id: "", className: "", _t: "", _h: "",
      dataset: {}, style: {}, _children: [], _listeners: {},
      classList: {
        _s: new Set(),
        add(c) { this._s.add(c); },
        remove() { for (let i = 0; i < arguments.length; i++) this._s.delete(arguments[i]); },
        contains(c) { return this._s.has(c); },
        toggle(c, o) { o === undefined && (o = !this._s.has(c)); o ? this._s.add(c) : this._s.delete(c); return o; },
      },
      appendChild(c) { this._children.push(c); return c; },
      insertBefore(c) { this._children.unshift(c); return c; },
      addEventListener(ev, fn) { (this._listeners[ev] = this._listeners[ev] || []).push(fn); },
      setAttribute(k, v) { if (k === "class") this.className = v; if (k === "id") this.id = v; this["_a_" + k] = v; },
      getAttribute(k) { return this["_a_" + k]; }, removeAttribute() {}, remove() {},
      fire(ev) { (this._listeners[ev] || []).forEach((fn) => fn({})); },
      querySelector() { return null; }, querySelectorAll() { return []; },
    };
    Object.defineProperty(node, "textContent", { get() { return this._t; }, set(v) { this._t = v; } });
    Object.defineProperty(node, "innerHTML", { get() { return this._h; }, set(v) { this._h = v; this._children = []; } });
    ALL.push(node);
    return node;
  }
  const byId = new Map();
  const listeners = {};
  const document = {
    getElementById(id) { if (!byId.has(id)) { const n = makeNode(); n.id = id; byId.set(id, n); } return byId.get(id); },
    createElement(t) { return makeNode(t); },
    createElementNS(ns, t) { return makeNode(t); },
    createTextNode(t) { const n = makeNode("#text"); n.textContent = t; return n; },
    head: makeNode(), body: makeNode(),
  };
  const window = {
    addEventListener(ev, fn) { (listeners[ev] = listeners[ev] || []).push(fn); },
    removeEventListener(ev, fn) { listeners[ev] = (listeners[ev] || []).filter((f) => f !== fn); },
  };
  return { ALL, document, window, makeNode, byId };
}

function runScript(file, h) {
  const sandbox = { window: h.window, document: h.document, console, Set, Math, Object, Array, String, JSON };
  vm.createContext(sandbox);
  vm.runInContext(
    fs.readFileSync(path.join(__dirname, "..", "beat_selector", file), "utf-8"),
    sandbox, { filename: file });
  return sandbox;
}

// Collect all text rendered anywhere under a node (recursive: _t, _h, children).
function allText(node, acc) {
  acc = acc || [];
  if (!node) return acc.join(" ");
  if (node._t) acc.push(node._t);
  if (node._h) acc.push(node._h);
  (node._children || []).forEach((c) => allText(c, acc));
  return acc.join(" ");
}

let passed = 0;
function assert(cond, msg) {
  if (!cond) { console.error("FAIL:", msg); process.exitCode = 1; throw new Error(msg); }
  passed += 1;
}

// --- fixtures --------------------------------------------------------------
const CONCEPT_EXPL = {
  concept: "inversion", title: "Inversions",
  short_definition: "An inversion changes the bass, not the chord.",
  core_idea: "A chord's identity is its chord tones and root, not its lowest note.",
  what_to_listen_for: ["same harmony as the bass moves"],
  what_to_play: ["play all tones, then bass first"],
  theory_terms: ["root position", "first inversion", "figured bass"],
  atlas_connections: ["same Atlas triad node across inversions"],
  common_misconceptions: ["C/E is not a new chord"],
  next_steps: ["carry inversions into voice leading"],
};

const LAB_DATA = {
  schema: "harmony-lab/v1",
  concepts: [
    { id: "inversion", label: "Inversions", detail: "changing bass", explanation: CONCEPT_EXPL },
    { id: "voice_leading_cadence", label: "Voice-leading cadences", detail: "SATB", explanation: { concept: "voice_leading", title: "Voice-leading cadences", short_definition: "directed motion", core_idea: "voices resolve", what_to_listen_for: ["arrival"], what_to_play: ["connect chords"], theory_terms: ["cadence"], atlas_connections: ["cadence node"], common_misconceptions: ["just two chords"], next_steps: ["add seventh"] } },
    { id: "real_score_analysis", label: "Real score analysis", detail: "reserved", reserved: true },
  ],
  experiments: [
    { experiment_id: "inv_C_I", title: "Inversions of C major I", concept: "inversion", schema: "harmony-lab/v1" },
    { experiment_id: "cad_V_I_C", title: "V–I in C", concept: "cadence", schema: "harmony-lab/v1" },
  ],
};

const EXPERIMENT_EXPL = {
  concept: "inversion", conceptLabel: "Inversions",
  title: "Inversions of C major I", key: "C major", modeWord: "major",
  scale: ["C", "D", "E", "F", "G", "A", "B"],
  summary: "In C major, I is C, built from C-E-G; chord tones stay, the bass changes.",
  facts: [{ label: "Key", value: "C major" }, { label: "Chord tones", value: "C-E-G" }],
  invariants: ["chord tones C-E-G", "root identity C", "tonic function"],
  changes: ["bass C (root position)", "bass E (first inversion)", "bass G (second inversion)"],
  sections: [{ title: "root position - C", lines: ["Bass: C", "Figured bass: 5/3"] }],
  practice: ["Compare the bass positions: C, C/E, C/G."],
};

const INV_TARGET = {
  absMeasure: 1, render: "block", key: "C major", mode: "major",
  roman: "I", chordSymbol: "C", inversionLabel: "first inversion",
  figuredBass: "6", bassNote: "E", chordTones: ["C", "E", "G"], concept: "block",
  labNote: "C in first inversion (6): tones C–E–G invariant; bass changes to E.",
};
const MELODY_TARGET = {
  absMeasure: 0, key: "C major", mode: "major", concept: "melody",
  motiveLabel: "^1–^3–^5–^3", degreeLabels: ["^1", "^3", "^5", "^3"],
  labNote: "Motive ^1–^3–^5–^3 in C major: C–E–G–E.",
};

const MAPPING = {
  concept: "inversion", conceptLabel: "Inversions", experimentTitle: "Inversions of C major I",
  measureNumber: 2, key: "C major", modeWord: "major",
  scale: ["C", "D", "E", "F", "G", "A", "B"], roman: "I", chordSymbol: "C",
  tones: ["C", "E", "G"], function: "tonic", intervalLayer: "M3+m3",
  inversion: { inversion: 1, label: "first inversion", figuredBass: "6", bass: "E", slash: "C/E" },
  cadence: null, motive: null, polyphony: null,
  atlasNodeIds: { scale: "scale:C:major", degree: "degree:major:I", triad: "triad:C:major:0" },
  atlasEdges: [{ source: "triad:C:major:0", target: "scale:C:major", relation: "belongs_to" }],
};

const CHEATSHEET = {
  majorPattern: [
    { degree: "I", quality: "major", intervalLayer: "M3+m3", functionLabel: "tonic", functionClass: "T" },
    { degree: "V", quality: "major", intervalLayer: "M3+m3", functionLabel: "dominant", functionClass: "D" },
  ],
  minorPattern: [
    { degree: "i", quality: "minor", intervalLayer: "m3+M3", functionLabel: "tonic", functionClass: "T" },
  ],
  intervalLayers: [{ quality: "major", intervalLayer: "M3+m3" }, { quality: "minor", intervalLayer: "m3+M3" }],
  functionClasses: [{ class: "T", label: "Tonic" }, { class: "S", label: "Pre/Sub" }, { class: "D", label: "Dominant" }],
};

// === Test 1: HarmonyLab concept theory ======================================
(function testConceptTheory() {
  const h = makeHarness();
  const s = runScript("harmony_lab.js", h);
  s.window.HarmonyLab.init(LAB_DATA);
  const theory = allText(h.document.getElementById("labConceptTheory"));
  assert(theory.indexOf("Inversions") !== -1, "concept theory shows the title");
  assert(theory.indexOf("Core idea") !== -1, "concept theory has a Core idea section");
  assert(theory.indexOf("chord tones and root") !== -1, "concept theory renders the core idea prose");
  assert(theory.indexOf("What to listen for") !== -1, "concept theory has a listen section");
  console.log("Test 1 (concept theory): PASS");
})();

// === Test 2: HarmonyLab example explanation =================================
(function testExampleExplanation() {
  const h = makeHarness();
  const s = runScript("harmony_lab.js", h);
  s.window.HarmonyLab.init(LAB_DATA);
  s.window.HarmonyLab.setExperimentExplanation(EXPERIMENT_EXPL);
  const ex = allText(h.document.getElementById("labExample"));
  assert(ex.indexOf("Inversions of C major I") !== -1, "example shows the experiment title");
  assert(ex.indexOf("C-E-G") !== -1, "example shows derived chord tones");
  assert(ex.indexOf("What stays invariant") !== -1, "example has an invariants section");
  assert(ex.indexOf("What changes") !== -1, "example has a changes section");
  assert(ex.indexOf("How to practise") !== -1, "example has a practice section");
  console.log("Test 2 (example explanation): PASS");
})();

// === Test 3: HarmonyLab sync update changes the live explanation ============
(function testSyncUpdate() {
  const h = makeHarness();
  const s = runScript("harmony_lab.js", h);
  s.window.HarmonyLab.init(LAB_DATA);
  s.window.HarmonyLab.updateExplanation(INV_TARGET);
  let live = h.document.getElementById("labExplain")._h;
  assert(live.indexOf("first inversion") !== -1, "live guide shows the inversion target");

  s.window.HarmonyLab.updateExplanation(MELODY_TARGET);
  live = h.document.getElementById("labExplain")._h;
  assert(live.indexOf("Motive") !== -1, "live guide switches to the motive target");
  assert(live.indexOf("first inversion") === -1, "previous target cleared");

  // setSync renders the Atlas strip.
  s.window.HarmonyLab.setSync({ triad: "triad:C:major:0", degree: "degree:major:I" });
  assert(h.document.getElementById("labAtlas")._h.indexOf("triad") !== -1, "sync strip renders");
  console.log("Test 3 (sync update): PASS");
})();

// === Test 4: Cheatsheet panel ===============================================
(function testCheatsheet() {
  const h = makeHarness();
  const s = runScript("lab_cheatsheet.js", h);
  const r = s.window.LabCheatsheet.init(CHEATSHEET);
  assert(r.ok, "cheatsheet init ok");
  const txt = allText(h.document.getElementById("csRoot"));
  assert(txt.indexOf("Major degree pattern") !== -1, "cheatsheet shows major pattern");
  assert(txt.indexOf("Natural-minor degree pattern") !== -1, "cheatsheet shows minor pattern");
  assert(txt.indexOf("Interval layers") !== -1, "cheatsheet shows interval layers");
  assert(txt.indexOf("M3+m3") !== -1, "cheatsheet shows a layer formula");
  assert(txt.indexOf("Dominant") !== -1, "cheatsheet shows function classes");
  const m = s.window.LabCheatsheet._model(CHEATSHEET);
  assert(m.major.length === 2 && m.functions.length === 3, "cheatsheet model parsed");
  console.log("Test 4 (cheatsheet): PASS");
})();

// === Test 5: Current Mapping panel ==========================================
(function testMapping() {
  const h = makeHarness();
  const s = runScript("lab_mapping.js", h);
  s.window.LabMapping.update(MAPPING);
  const txt = allText(h.document.getElementById("mapRoot"));
  assert(txt.indexOf("Current mapping") !== -1, "mapping title rendered");
  assert(txt.indexOf("first inversion") !== -1, "mapping shows the inversion field");
  assert(txt.indexOf("C/E") !== -1, "mapping shows the slash chord");
  assert(txt.indexOf("triad:C:major:0") !== -1, "mapping shows the Atlas triad node id");
  assert(txt.indexOf("belongs_to") !== -1, "mapping shows a related Atlas edge");

  const rows = s.window.LabMapping._rows(MAPPING);
  const labels = rows.map((r) => r.label);
  assert(labels.indexOf("Roman numeral") !== -1, "mapping rows include the Roman numeral");
  assert(labels.indexOf("Inversion") !== -1, "mapping rows include the inversion");

  // Empty mapping -> placeholder, no throw.
  s.window.LabMapping.update(null);
  assert(allText(h.document.getElementById("mapRoot")).indexOf("Play an experiment") !== -1,
    "empty mapping shows placeholder");
  console.log("Test 5 (current mapping): PASS");
})();

// === Test 6: Circle lab-launch affordances ==================================
function triad(degree, sym, fnClass) {
  return { degree, degreeNumber: 1, chordSymbol: sym, root: degree, quality: "major",
    tones: ["C", "E", "G"], intervalLayer: "M3+m3",
    functionLabel: fnClass === "D" ? "dominant" : "tonic", functionClass: fnClass };
}
const C_TRIADS = [triad("I", "C", "T"), triad("V", "G", "D")];
const CIRCLE_DATA = {
  schema: "harmony-circle/v1", labLaunch: true,
  majorKeys: [{ key: "C", mode: "major", relativeMinor: "A", fifths: 0,
    scale: ["C", "D", "E", "F", "G", "A", "B"], triads: C_TRIADS }],
  minorKeys: [{ key: "A", mode: "natural_minor", relativeMajor: "C", fifths: 0,
    scale: ["A", "B", "C", "D", "E", "F", "G"], triads: C_TRIADS }],
  circleOrderMajor: ["C"], circleOrderMinor: ["A"],
  cheatsheet: CHEATSHEET, relations: [],
};

(function testCircleLabLaunch() {
  const h = makeHarness();
  const s = runScript("harmony_circle.js", h);
  s.window.HarmonyCircle.init(CIRCLE_DATA);
  s.window.HarmonyCircle.selectKey("C", "major");
  // A key is selected -> motive + voice-leading lab buttons exist.
  let motive = h.ALL.filter((n) => n._t === "Motive lab" && n._listeners.click);
  assert(motive.length >= 1, "motive lab button present for a key");
  motive[0].fire("click");
  let req = s.window.HarmonyCircle.takeLabLaunch();
  assert(req && req.labConcept === "motive" && req.key === "C major", "motive lab request enqueued");

  // Select the dominant degree -> inversion + cadence lab buttons appear.
  s.window.HarmonyCircle.selectDegree("V");
  const inv = h.ALL.filter((n) => n._t === "Inversion lab (V)" && n._listeners.click);
  assert(inv.length >= 1, "inversion lab button present for a degree");
  inv[0].fire("click");
  req = s.window.HarmonyCircle.takeLabLaunch();
  assert(req && req.labConcept === "inversion" && req.degree === "V", "inversion lab request enqueued");

  const cad = h.ALL.filter((n) => /^Cadence lab/.test(n._t || "") && n._listeners.click);
  assert(cad.length >= 1, "cadence lab button present for a dominant degree");
  cad[0].fire("click");
  req = s.window.HarmonyCircle.takeLabLaunch();
  assert(req && req.labConcept === "cadence" && req.pattern[0] === "V" && req.pattern[1] === "I",
    "cadence lab request enqueued with V-I pattern");
  console.log("Test 6 (circle lab-launch): PASS");
})();

// === Test 7: Circle WITHOUT labLaunch shows no lab buttons (trainer parity) ==
(function testCircleNoLabLaunch() {
  const h = makeHarness();
  const s = runScript("harmony_circle.js", h);
  const plain = Object.assign({}, CIRCLE_DATA);
  delete plain.labLaunch;
  s.window.HarmonyCircle.init(plain);
  s.window.HarmonyCircle.selectKey("C", "major");
  const motive = h.ALL.filter((n) => n._t === "Motive lab");
  assert(motive.length === 0, "no lab buttons when labLaunch is off (trainer parity)");
  assert(s.window.HarmonyCircle.takeLabLaunch() === null, "lab queue empty when off");
  console.log("Test 7 (circle no-labLaunch parity): PASS");
})();

console.log("\nAll Music Theory Lab workspace checks passed (" + passed + " assertions).");
