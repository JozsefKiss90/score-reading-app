/*
 * Headless behavioural test for beat_selector/harmony_lab.js.
 *
 * The GUI can't run in CI, so this stubs the browser globals (window/document),
 * feeds a shape-accurate LAB_DATA fixture (matching run_harmony_lab_demo.build_lab_catalog())
 * and a lab target (matching a harmony.lab_musicxml.build_lab_payload target),
 * loads the controller via Node's `vm`, and verifies the host-facing API:
 *   - init() selects the first real concept and renders without throwing;
 *   - clicking an experiment enqueues its LabExperimentSpec, which the host picks
 *     up via takeLaunch();
 *   - experimentsFor() groups cadence + voice_leading under one selector concept;
 *   - updateExplanation() builds the right guide model (voices, bass motion,
 *     inversion / figured bass);
 *   - setSync() parses Atlas node ids into chips.
 *
 * Run:  node tests/harmony_lab_node_test.js
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

let ALL = [];
function makeNode(tag) {
  const node = {
    tag: tag || "div", id: "", className: "", _text: "", _html: "",
    dataset: {}, style: {}, _children: [], _listeners: {},
    classList: {
      _s: new Set(),
      add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); },
      contains(c) { return this._s.has(c); },
    },
    appendChild(c) { this._children.push(c); return c; },
    insertBefore(c) { this._children.unshift(c); return c; },
    addEventListener(ev, fn) { (this._listeners[ev] = this._listeners[ev] || []).push(fn); },
    setAttribute(k, v) { if (k === "class") this.className = v; this["_attr_" + k] = v; },
    removeAttribute() {}, remove() {},
    fire(ev) { (this._listeners[ev] || []).forEach((fn) => fn({})); },
    querySelector() { return null; }, querySelectorAll() { return []; },
  };
  Object.defineProperty(node, "textContent",
    { get() { return this._text; }, set(v) { this._text = v; } });
  Object.defineProperty(node, "innerHTML",
    { get() { return this._html; }, set(v) { this._html = v; this._children = []; } });
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
    head: makeNode(), body: makeNode(),
  };
  const window = { LAB_DATA: data };
  const sandbox = { window, document, console, Set, Math, Object, Array, String, JSON };
  vm.createContext(sandbox);
  vm.runInContext(
    fs.readFileSync(path.join(__dirname, "..", "beat_selector", "harmony_lab.js"), "utf-8"),
    sandbox, { filename: "harmony_lab.js" });
  return { window, document, ui: window.HarmonyLab };
}

// --- fixture (matches build_lab_catalog() + a build_lab_payload target) ------
const DATA = {
  schema: "harmony-lab/v1",
  concepts: [
    { id: "inversion", label: "Inversions", detail: "changing bass" },
    { id: "voice_leading_cadence", label: "Voice-leading cadences", detail: "SATB" },
    { id: "motive", label: "Motive transposition", detail: "across keys" },
    { id: "polyphonic_harmony", label: "Polyphonic harmony", detail: "two voices" },
    { id: "real_score_analysis", label: "Real score analysis", detail: "reserved", reserved: true },
  ],
  experiments: [
    { experiment_id: "inv_C_I", title: "Inversions of C major I", concept: "inversion", schema: "harmony-lab/v1" },
    { experiment_id: "cad_V_I_C", title: "V–I in C", concept: "cadence", schema: "harmony-lab/v1" },
    { experiment_id: "cad_ii_V_I_C", title: "ii–V–I in C", concept: "voice_leading", schema: "harmony-lab/v1" },
    { experiment_id: "motive_1353", title: "1–3–5–3", concept: "motive", schema: "harmony-lab/v1" },
    { experiment_id: "poly_I_V_I", title: "I–V–I", concept: "polyphonic_harmony", schema: "harmony-lab/v1" },
  ],
};

const SATB_TARGET = {
  absMeasure: 1, render: "block", key: "C major", mode: "major",
  roman: "I", chordSymbol: "C", functionLabel: "tonic", quality: "major",
  chordTones: ["C", "E", "G"], pitchClasses: [0, 4, 7], concept: "voice_leading",
  voices: [["soprano", "G4"], ["alto", "E4"], ["tenor", "C4"], ["bass", "C3"]],
  commonTones: ["G"], bassMotion: "G → C", tendencyTones: ["leading tone B → C"],
  labNote: "I (C, tonic); bass G → C; common tone G; leading tone B → C.",
};

const INV_TARGET = {
  absMeasure: 1, render: "block", key: "C major", mode: "major",
  roman: "I", chordSymbol: "C", inversionLabel: "first inversion",
  figuredBass: "6", bassNote: "E", chordTones: ["C", "E", "G"], concept: "block",
  labNote: "C in first inversion (6): the chord tones C–E–G are invariant; only the bass changes to E.",
};

let passed = 0;
function assert(cond, msg) {
  if (!cond) { console.error("FAIL:", msg); process.exitCode = 1; throw new Error(msg); }
  passed += 1;
}

// === Test A: init ===========================================================
(function testInit() {
  const h = makeHarness(DATA);
  const r = h.ui.init(DATA);
  assert(r.ok, "init ok");
  assert(r.experiments === 5, "reports experiment count");
  console.log("Test A (init): PASS");
})();

// === Test B: concept grouping ===============================================
(function testGrouping() {
  const h = makeHarness(DATA);
  h.ui.init(DATA);
  const vlc = h.ui._experimentsFor("voice_leading_cadence").map((e) => e.experiment_id);
  assert(vlc.length === 2 && vlc.indexOf("cad_V_I_C") !== -1 &&
    vlc.indexOf("cad_ii_V_I_C") !== -1, "cadence + voice_leading grouped together");
  assert(h.ui._experimentsFor("inversion").length === 1, "inversion group");
  assert(h.ui._experimentsFor("real_score_analysis").length === 0, "reserved has none");
  console.log("Test B (grouping): PASS");
})();

// === Test C: click -> takeLaunch ============================================
(function testLaunch() {
  const h = makeHarness(DATA);
  h.ui.init(DATA);                       // first real concept = "inversion" is open
  const cards = findByData("id", "inv_C_I");
  assert(cards.length >= 1, "inversion experiment rendered");
  cards[0].fire("click");
  const spec = h.ui.takeLaunch();
  assert(spec && spec.experiment_id === "inv_C_I", "takeLaunch returns clicked spec");
  assert(h.ui.takeLaunch() === null, "queue drains");

  // Switch concept, then launch a cadence experiment.
  h.ui.showConcept("voice_leading_cadence");
  const cad = findByData("id", "cad_V_I_C");
  assert(cad.length >= 1, "cadence experiment rendered after switch");
  cad[0].fire("click");
  assert(h.ui.takeLaunch().experiment_id === "cad_V_I_C", "cadence launch enqueued");
  console.log("Test C (launch): PASS");
})();

// === Test D: explanation model ==============================================
(function testExplanation() {
  const h = makeHarness(DATA);
  h.ui.init(DATA);
  const m = h.ui._explanationModel(SATB_TARGET);
  const labels = m.rows.map((r) => r.label);
  assert(m.heading.indexOf("C") !== -1, "heading shows the chord");
  assert(labels.indexOf("Voices") !== -1, "voices row present");
  assert(labels.indexOf("Bass motion") !== -1, "bass motion row present");
  const bm = m.rows.find((r) => r.label === "Bass motion");
  assert(bm.value === "G → C", "bass motion value");
  assert(m.note.length > 0, "note present");

  const inv = h.ui._explanationModel(INV_TARGET);
  const invLabels = inv.rows.map((r) => r.label);
  assert(invLabels.indexOf("Inversion") !== -1, "inversion row present");
  const ir = inv.rows.find((r) => r.label === "Inversion");
  assert(ir.value.indexOf("6") !== -1, "figured bass shown");
  // updateExplanation must render without throwing.
  h.ui.updateExplanation(SATB_TARGET);
  assert(h.document.getElementById("labExplain")._html.indexOf("Bass motion") !== -1,
    "updateExplanation writes the guide");
  console.log("Test D (explanation): PASS");
})();

// === Test E: sync chips =====================================================
(function testSync() {
  const h = makeHarness(DATA);
  h.ui.init(DATA);
  const chips = h.ui._syncChips({
    scale: "scale:C:major", degree: "degree:major:I",
    triad: "triad:C:major:0", quality: null,
  });
  assert(chips.length === 3, "null ids dropped");
  const triad = chips.find((c) => c.kind === "triad");
  assert(triad.label === "C major 0", "triad id parsed to a label");
  h.ui.setSync({ triad: "triad:C:major:0" });
  assert(h.document.getElementById("labAtlas")._html.indexOf("triad") !== -1,
    "setSync renders the strip");
  console.log("Test E (sync): PASS");
})();

console.log("\nAll harmony_lab.js behavioural checks passed (" + passed + " assertions).");
