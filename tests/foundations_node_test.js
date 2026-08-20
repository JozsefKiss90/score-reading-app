/*
 * Headless behavioural test for beat_selector/foundations.js — the Chord
 * Progression Foundations (C/G/F) lesson page controller.
 *
 * Stubs the browser globals, loads the REAL lesson payload from Python
 * (harmony.progression_foundations.build_foundations_payload), loads the
 * controller via Node's `vm`, and verifies the host-facing API + the
 * decoupled models:
 *   - init() renders four groups and reports 12 examples;
 *   - selecting an example enqueues its LabExperimentSpec (takeLaunch) and
 *     C/G/F switching changes both the launch and the derived table;
 *   - the reveal toggle flips aria-expanded and adds the analysis columns;
 *   - setCurrent() highlights the matching table row (and ignores targets
 *     belonging to another drill);
 *   - Atlas chips enqueue node-id lists (takeAtlasSelection);
 *   - missing optional display fields fall back to the canonical ASCII ones;
 *   - keyboard row navigation clamps and roves the tabindex.
 *
 * Run:  node tests/foundations_node_test.js
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
    "import json;from harmony.progression_foundations import build_foundations_payload;" +
    "print(json.dumps(build_foundations_payload()))";
  for (const py of candidates) {
    try {
      const out = cp.execFileSync(py, ["-c", code],
        { cwd: ROOT, encoding: "utf-8", maxBuffer: 64 * 1024 * 1024 });
      return JSON.parse(out);
    } catch (e) { /* try the next interpreter */ }
  }
  console.error("SKIP: could not run Python to build the foundations payload.");
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
    removeAttribute() {}, remove() {}, focus() {},
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
function findByData(key, val) {
  return ALL.filter((n) => n.dataset && n.dataset[key] === val);
}
function allWithData(key) {
  return ALL.filter((n) => n.dataset && n.dataset[key] !== undefined);
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
  const window = { FOUNDATIONS: data };
  const sandbox = { window, document, console, Set, Math, Object, Array, String, JSON };
  vm.createContext(sandbox);
  vm.runInContext(
    fs.readFileSync(path.join(ROOT, "beat_selector", "foundations.js"), "utf-8"),
    sandbox, { filename: "foundations.js" });
  return { window, document, ui: window.Foundations, byId };
}

let passed = 0;
function assert(cond, msg) {
  if (!cond) { console.error("FAIL:", msg); process.exitCode = 1; throw new Error(msg); }
  passed += 1;
}

const PAYLOAD = loadPayload();

function exampleIds(payload) {
  const out = [];
  (payload.groups || []).forEach((g) =>
    (g.examples || []).forEach((ex) => out.push(ex.exampleId)));
  return out;
}

// === Test A: init — four groups, 12 examples ================================
(function testInit() {
  const h = makeHarness(PAYLOAD);
  const r = h.ui.init(PAYLOAD);
  assert(r.ok, "init ok");
  assert(r.groups === 4, "four groups, got " + r.groups);
  assert(r.examples === 12, "twelve examples, got " + r.examples);
  // every example rendered a selection button
  const ids = exampleIds(PAYLOAD);
  ids.forEach((id) => {
    assert(findByData("id", id).length === 1, "button rendered for " + id);
  });
  // the transposition strip makes the same-pattern claim visible per group:
  // three key rows per group table
  const strips = PAYLOAD.groups.map((g) => h.ui._transpositionStrip(g));
  strips.forEach((s, i) => {
    assert(s.length === 3, "strip has three keys for group " + i);
    assert(new Set(s.map((r2) => r2.chords)).size === 3,
      "chord rows differ across keys (group " + i + ")");
  });
  console.log("Test A (init): PASS");
})();

// === Test B: selection + launch, C/G/F switching ============================
(function testSelectLaunch() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);
  const groupC = PAYLOAD.groups.find((g) => g.familyId === "ii_V_I");
  const [exC, exG, exF] = groupC.examples;
  assert(h.ui.selectExample(exC.exampleId), "select C example");
  let launch = h.ui.takeLaunch();
  assert(launch && launch.experiment_id === exC.labSpec.experiment_id,
    "launch queued for C");
  assert(h.ui.takeLaunch() === null, "queue drained");
  const modelC = h.ui._tableModel(exC, true);
  // switch C -> G: new launch + a different table
  h.ui.selectExample(exG.exampleId);
  launch = h.ui.takeLaunch();
  assert(launch && launch.experiment_id === exG.labSpec.experiment_id,
    "launch queued for G");
  const modelG = h.ui._tableModel(exG, true);
  assert(JSON.stringify(modelC.rows) !== JSON.stringify(modelG.rows),
    "table changes with the key");
  assert(modelC.columns.join() === modelG.columns.join(),
    "columns are key-invariant");
  // aria-pressed follows the selection (ALL accumulates re-renders, so the
  // LAST match is the current DOM)
  const btnG = findByData("id", exG.exampleId).slice(-1)[0];
  assert(btnG["_attr_aria-pressed"] === "true", "selected button pressed");
  const btnF = findByData("id", exF.exampleId).slice(-1)[0];
  assert(btnF["_attr_aria-pressed"] === "false", "unselected button unpressed");
  console.log("Test B (selection + launch): PASS");
})();

// === Test C: reveal / hide ==================================================
(function testReveal() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);
  const ex = PAYLOAD.groups[0].examples[0];
  h.ui.selectExample(ex.exampleId);
  const base = h.ui._visibleColumns(false).map((c) => c.label);
  assert(base.length === 3, "three base columns, got " + base.length);
  assert(base.indexOf("Roman numeral") === -1, "Roman hidden before reveal");
  assert(h.ui.toggleReveal() === true, "reveal on");
  const full = h.ui._visibleColumns(true).map((c) => c.label);
  ["Roman numeral", "Scale", "Degree", "Quality", "Function", "Chord size",
   "Atlas mapping", "Related lesson"].forEach((label) => {
    assert(full.indexOf(label) !== -1, label + " revealed");
  });
  const revealBtn = () => ALL.filter(
    (n) => n["_attr_aria-controls"] === "fnTableWrap").slice(-1)[0];
  assert(revealBtn() && revealBtn()["_attr_aria-expanded"] === "true",
    "aria-expanded true");
  assert(h.ui.toggleReveal() === false, "reveal off again");
  assert(revealBtn()["_attr_aria-expanded"] === "false", "aria-expanded false");
  console.log("Test C (reveal): PASS");
})();

// === Test D: live measure highlight =========================================
(function testActiveRow() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);
  const ex = PAYLOAD.groups[0].examples[0];        // full field: 7 measures
  h.ui.selectExample(ex.exampleId);
  h.ui.setCurrent(ex.curriculumNodeId, { absMeasure: 3 });
  assert(h.ui._activeAbs() === 3, "active measure tracked");
  const active = ALL.filter((n) => n.className &&
    n.className.indexOf("fnRowActive") !== -1);
  assert(active.length === 1, "exactly one active row");
  assert(active[0].dataset.abs === "3", "the matching row is active");
  assert(active[0]["_attr_aria-current"] === "true", "aria-current set");
  // a target from a DIFFERENT drill must not move the highlight
  h.ui.setCurrent("ex:drill_something_else", { absMeasure: 5 });
  assert(h.ui._activeAbs() === 3, "foreign target ignored");
  console.log("Test D (active row): PASS");
})();

// === Test E: Atlas chips use the selection queue ============================
(function testAtlasChips() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);
  const ex = PAYLOAD.groups[0].examples[0];
  h.ui.selectExample(ex.exampleId);
  h.ui.toggleReveal();                              // atlas column is revealed
  const chips = allWithData("atlas");
  assert(chips.length > 0, "atlas chips rendered");
  chips[0].fire("click");
  const sel = h.ui.takeAtlasSelection();
  assert(Array.isArray(sel) && sel.length > 0, "atlas selection queued");
  assert(sel.indexOf(chips[0].dataset.atlas) !== -1,
    "clicked node id is in the selection");
  assert(h.ui.takeAtlasSelection() === null, "atlas queue drained");
  console.log("Test E (atlas chips): PASS");
})();

// === Test F: optional display fields may be absent ==========================
(function testOptionalData() {
  const minimal = {
    schema: "progression-foundations/v1",
    title: "t", intro: [], transposition: {}, keys: ["C"],
    groups: [{
      letter: "A", familyId: "fam", title: "g", romanLabel: "I", blurb: "",
      examples: [{
        exampleId: "x1", familyId: "fam", groupLetter: "A", label: "A1",
        key: "C", reused: false, curriculumNodeId: "ex:drill_x1",
        exerciseId: "x1", labSpec: { concept: "drill", experiment_id: "drill_x1" },
        chordSymbols: ["C"],
        table: [{ position: 1, measureNumber: 1, key: "C major",
                  chordSymbol: "C", chordNotes: ["C", "E", "G"],
                  scale: ["C"], degree: 1, roman: "I", quality: "major",
                  function: "tonic", chordSize: "triad", pitchClasses: [0] }],
      }],
    }],
  };
  const h = makeHarness(minimal);
  const r = h.ui.init(minimal);
  assert(r.ok && r.examples === 1, "minimal payload initialises");
  h.ui.selectExample("x1");
  const m = h.ui._tableModel(minimal.groups[0].examples[0], true);
  const flat = m.rows[0].join("|");
  assert(flat.indexOf("C") !== -1, "falls back to ASCII chord symbol");
  assert(flat.indexOf("undefined") === -1, "no undefined cells");
  assert(flat.indexOf("tonic") !== -1, "function shown without gloss");
  console.log("Test F (optional data): PASS");
})();

// === Test G: keyboard row navigation ========================================
(function testKeyboard() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);
  const ex = PAYLOAD.groups[0].examples[0];        // 7 rows
  h.ui.selectExample(ex.exampleId);
  assert(h.ui._focusRow() === 0, "focus starts at row 0");
  assert(h.ui._keyMove(1) === 1, "ArrowDown moves to row 1");
  assert(h.ui._keyMove(-1) === 0, "ArrowUp moves back");
  assert(h.ui._keyMove(-1) === 0, "clamped at the top");
  for (let i = 0; i < 20; i += 1) h.ui._keyMove(1);
  assert(h.ui._focusRow() === ex.table.length - 1, "clamped at the bottom");
  // the keydown handler is wired on the rendered rows (roving tabindex)
  const rows = allWithData("abs");
  assert(rows.length >= ex.table.length, "table rows rendered");
  const tab0 = rows.filter((r) => r["_attr_tabindex"] === "0");
  assert(tab0.length >= 1, "one row carries tabindex 0");
  console.log("Test G (keyboard): PASS");
})();

console.log("\nAll foundations.js behavioural checks passed ("
  + passed + " assertions).");
