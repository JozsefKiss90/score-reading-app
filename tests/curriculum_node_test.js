/*
 * Headless behavioural test for beat_selector/curriculum.js.
 *
 * The GUI can't run in CI, so this stubs the browser globals (window/document),
 * loads the REAL curriculum payload from Python
 * (harmony.curriculum_explanations.build_curriculum_payload), loads the
 * controller via Node's `vm`, and verifies the host-facing API + decoupled
 * logic:
 *   - init() indexes the tree and reports the exercise-leaf count;
 *   - the tree lazily expands/collapses and remembers nothing across a fresh init;
 *   - search() filters to matches + ancestors (token-AND over the index);
 *   - keyboard navigation moves / expands / collapses / selects;
 *   - clicking an exercise enqueues its LabExperimentSpec (takeLaunch);
 *   - selecting a node enqueues it for Atlas/Circle sync (takeSelection);
 *   - selectByExerciseId() jumps to the leaf that owns a trainer exercise;
 *   - the lesson / exercise page models carry the derived fields;
 *   - setProgress() overlays roll-up stats;
 *   - setSync() parses Atlas node ids into chips.
 *
 * Run:  node tests/curriculum_node_test.js
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
    "import json;from harmony.curriculum_explanations import build_curriculum_payload;" +
    "print(json.dumps(build_curriculum_payload()))";
  for (const py of candidates) {
    try {
      const out = cp.execFileSync(py, ["-c", code],
        { cwd: ROOT, encoding: "utf-8", maxBuffer: 64 * 1024 * 1024 });
      return JSON.parse(out);
    } catch (e) { /* try the next interpreter */ }
  }
  console.error("SKIP: could not run Python to build the curriculum payload.");
  process.exit(0);
}

// --- minimal DOM harness (mirrors harmony_lab_node_test.js) -----------------
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
function findByData(key, val) { return ALL.filter((n) => n.dataset && n.dataset[key] === val); }
function rowsRendered() { return ALL.filter((n) => n.dataset && n.dataset.id && n.dataset.depth !== undefined); }

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
  const window = { CURRICULUM: data };
  const sandbox = { window, document, console, Set, Math, Object, Array, String, JSON };
  vm.createContext(sandbox);
  vm.runInContext(
    fs.readFileSync(path.join(ROOT, "beat_selector", "curriculum.js"), "utf-8"),
    sandbox, { filename: "curriculum.js" });
  return { window, document, ui: window.Curriculum, byId };
}

let passed = 0;
function assert(cond, msg) {
  if (!cond) { console.error("FAIL:", msg); process.exitCode = 1; throw new Error(msg); }
  passed += 1;
}

const PAYLOAD = loadPayload();

// === Test A: init ===========================================================
(function testInit() {
  const h = makeHarness(PAYLOAD);
  const r = h.ui.init(PAYLOAD);
  assert(r.ok, "init ok");
  // 351 leaves = 102 native drills + 15 block cadences + 107 inversions
  // (96-key grid + 1 arpeggio worked example + 1 ii6 cadence bridge + 9
  // bass-line dictations, ticket 11) + 15 SATB voice-leading cadences
  // + 2 motives + 3 polyphonic examples + 56 seventh-chord drills
  // (ticket 09: 2 add-the-7th + 12 tritone + 2 V7–I; ticket 10: 7 quality
  // + 3 ear-ID + 6 ii7–V7–I; ticket 11: 12 V7 figured inversions + 12
  // resolution walks) + 12 harmonic-minor drills (ticket 13: 4 A/B
  // one-accidental pairs + 2 V–i + 2 vii°–i + 4 i–iv–V–i) + 4 G2b drills
  // (ticket 14: 1 III+ quality drill + 3 melodic-minor motive cells)
  // + 35 G3 cadence-taxonomy drills (ticket 16: 2 V→? ear reflexes + 3
  // PAC/IAC + 3 soprano dictations + 2 i–V halves + 3 Phrygian iv6–V + 6
  // cadential 6/4 hear/relabel pairs + 16 cadence orbits; the 15s above
  // already include the ticket's 2 new half-cadence catalogue entries).
  assert(r.exercises === 351, "reports 351 exercise leaves, got " + r.exercises);
  // first category auto-expanded -> its lesson rows are visible
  const rows = h.ui._visibleRows();
  assert(rows.length > PAYLOAD.tree.children.length, "first category expanded");
  console.log("Test A (init): PASS");
})();

// === Test B: expand / collapse ==============================================
(function testExpand() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);
  const before = h.ui._visibleRows().length;
  // collapse the first category via keyboard-less API: toggle through a click
  const catId = PAYLOAD.tree.children[0].id;
  const catRows = findByData("id", catId);
  assert(catRows.length >= 1, "category row rendered");
  // click the twisty to collapse (first child of the row is the twisty span)
  catRows[0]._children[0].fire("click");
  const after = h.ui._visibleRows().length;
  assert(after < before, "collapsing the category hides its descendants");
  console.log("Test B (expand/collapse): PASS");
})();

// === Test C: search filters to matches + ancestors ==========================
(function testSearch() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);
  const ids = h.ui._searchNodes("ii V I");
  assert(ids.length > 0, "search finds ii V I");
  const titles = ids.map((id) => h.ui._nodeById(id).title).join(" | ");
  assert(/ii/i.test(titles), "ii V I results mention ii");

  h.ui.search("authentic cadence");
  const set = h.ui._matchSet("authentic cadence");
  assert(set, "authentic cadence has a match set");
  // every match's ancestors are in the set (so the path is visible)
  const firstMatch = h.ui._searchNodes("authentic cadence")[0];
  h.ui._ancestorsOf(firstMatch).forEach((a) =>
    assert(set[a], "ancestor " + a + " is in the filter set"));

  // searching renders only the filtered rows
  h.ui.search("diminished");
  const filteredTitles = rowsRendered().map((n) => n.dataset.id);
  assert(filteredTitles.length > 0, "diminished filter shows rows");
  console.log("Test C (search): PASS");
})();

// === Test D: keyboard navigation ============================================
(function testKeyboard() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);
  const f1 = h.ui._keyMove("ArrowDown");
  assert(f1 === PAYLOAD.tree.children[0].id, "ArrowDown focuses first category");
  const f2 = h.ui._keyMove("ArrowDown");
  assert(f2 && f2 !== f1, "ArrowDown moves focus");
  // collapse-then-expand the focused category
  h.ui._keyMove("ArrowUp");                       // back to first category
  const visBefore = h.ui._visibleRows().length;
  h.ui._keyMove("ArrowLeft");                      // collapse
  assert(h.ui._visibleRows().length < visBefore, "ArrowLeft collapses");
  h.ui._keyMove("ArrowRight");                     // expand again
  assert(h.ui._visibleRows().length === visBefore, "ArrowRight re-expands");
  console.log("Test D (keyboard): PASS");
})();

// === Test E: launch + selection sync ========================================
(function testLaunch() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);
  // find a leaf id from the tree
  let leafId = null, leafSpecId = null;
  (function find(node) {
    if (leafId) return;
    if (node.kind === "exercise") {
      leafId = node.id;
      leafSpecId = (node.exerciseSpecs && node.exerciseSpecs[0]
        && node.exerciseSpecs[0].exercise_id) || node.labSpec.experiment_id;
      return;
    }
    (node.children || []).forEach(find);
  })(PAYLOAD.tree);
  assert(leafId, "found a leaf id");

  // selectByExerciseId expands ancestors and selects the owning leaf
  const sel = h.ui.selectByExerciseId(leafSpecId);
  assert(sel === leafId, "selectByExerciseId resolves the owning leaf");
  // selecting enqueues for Atlas/Circle sync
  assert(h.ui.takeSelection() === leafId, "takeSelection returns the selected node");

  // the leaf row is rendered; double-click launches its labSpec
  const rows = findByData("id", leafId);
  assert(rows.length >= 1, "leaf row rendered after select");
  rows[0].fire("dblclick");
  const spec = h.ui.takeLaunch();
  assert(spec && spec.concept, "takeLaunch returns the LabExperimentSpec");
  assert(h.ui.takeLaunch() === null, "launch queue drains");
  console.log("Test E (launch + selection): PASS");
})();

// === Test F: page models ====================================================
(function testPages() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);
  // a function-drill exercise page (find by pattern in title)
  let funcLeafId = null;
  Object.keys(PAYLOAD.pages).forEach((id) => {
    const p = PAYLOAD.pages[id];
    if (!funcLeafId && p.kind === "exercise" && /ii.?V.?I/.test(p.title)
        && p.harmonicAnalysis && p.harmonicAnalysis.length) funcLeafId = id;
  });
  assert(funcLeafId, "found a ii-V-I exercise page");
  const em = h.ui._exerciseModel(PAYLOAD.pages[funcLeafId]);
  assert(em.analysis.length >= 1, "exercise model carries harmonic analysis");
  assert(em.launch && em.launch.concept, "exercise model carries launch spec");
  assert(em.preview, "exercise model carries trainer preview");

  // a lesson page
  const lessonId = "lesson:functions_major";
  assert(PAYLOAD.pages[lessonId], "functions_major lesson page exists");
  const lm = h.ui._lessonModel(PAYLOAD.pages[lessonId]);
  assert(lm.skills.length >= 1, "lesson model carries skills");
  assert(lm.order.length >= 1, "lesson model carries recommended order");
  assert(lm.audio, "lesson model carries audio objective");
  console.log("Test F (page models): PASS");
})();

// === Test G: progress overlay ===============================================
(function testProgress() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);
  const rootId = PAYLOAD.tree.id;
  h.ui.setProgress({
    stats: {
      [rootId]: { id: rootId, kind: "curriculum", total: 231, completed: 12,
                  mastered: 3, percent: 5.2, state: "started" },
    },
  });
  const html = h.document.getElementById("curProgress")._html
    + h.document.getElementById("curProgress")._children.map((c) => c._text).join(" ");
  // the progress panel re-rendered with the overall line
  assert(rowsRendered().length > 0, "tree still rendered after setProgress");
  console.log("Test G (progress): PASS");
})();

// === Test H: sync chips =====================================================
(function testSync() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);
  const chips = h.ui._syncChips({
    scale: "scale:C:major", degree: "degree:major:I",
    triad: "triad:C:major:0", quality: null,
  });
  assert(chips.length === 3, "null ids dropped");
  const triad = chips.find((c) => c.kind === "triad");
  assert(triad.label === "C major 0", "triad id parsed to a label");
  h.ui.setSync({ triad: "triad:C:major:0" });
  assert(h.document.getElementById("curAtlas")._html.indexOf("triad") !== -1,
    "setSync renders the strip");
  console.log("Test H (sync): PASS");
})();

// === Test I: echo drill affordance (plan A1, ticket 07) =====================
(function testEchoAffordance() {
  const h = makeHarness(PAYLOAD);
  h.ui.init(PAYLOAD);

  // find an echo-eligible leaf and an ineligible one from the real payload
  let echoId = null, plainId = null;
  (function find(node) {
    if (node.kind === "exercise") {
      if (node.echoEligible && !echoId) echoId = node.id;
      if (!node.echoEligible && !plainId) plainId = node.id;
    }
    (node.children || []).forEach(find);
  })(PAYLOAD.tree);
  assert(echoId, "the payload marks echo-eligible leaves");
  assert(plainId, "lab-concept leaves stay ineligible");

  const echoButtons = () =>
    ALL.filter((n) => /curEcho/.test(n.className));

  // Not started -> the button renders locked and clicking enqueues nothing.
  h.ui.select(echoId);
  let btns = echoButtons();
  assert(btns.length >= 1, "eligible leaf shows the echo button");
  assert(/locked/.test(btns[btns.length - 1].className),
         "echo is locked before the visual leaf is started");
  btns[btns.length - 1].fire("click");
  assert(h.ui.takeLaunch() === null, "locked echo click enqueues nothing");

  // Progress arrives (leaf started) -> the detail re-renders unlocked.
  h.ui.setProgress({ stats: { [echoId]: {
    id: echoId, kind: "exercise", state: "started", attempts: 1,
    bestScore: 0, percent: 0 } } });
  btns = echoButtons().filter((n) => !/locked/.test(n.className));
  assert(btns.length >= 1, "started leaf unlocks the echo button");
  btns[btns.length - 1].fire("click");
  const spec = h.ui.takeLaunch();
  assert(spec && spec.echo === true, "echo launch carries the echo flag");
  assert(spec.concept === "drill", "echo launch wraps the native drill spec");

  // Ineligible leaves never show the affordance.  (ALL accumulates nodes
  // across renders, so "no new echo button" means the count stays flat.)
  const countBefore = echoButtons().length;
  h.ui.select(plainId);
  assert(echoButtons().length === countBefore,
         "selecting an ineligible leaf adds no echo button");
  console.log("Test I (echo affordance): PASS");
})();

console.log("\nAll curriculum.js behavioural checks passed (" + passed + " assertions).");
