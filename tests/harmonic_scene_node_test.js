/*
 * Headless behavioural test for the SCENE-mode API of harmonic_network.js
 * (setScene / updateOccurrenceState / requestSceneSeek / clearScene).
 *
 * Loads REAL GraphScene payloads from Python (harmony.graph_scene_router) and
 * verifies the host-facing contract without a browser (the DOM harness has no
 * createElementNS, so the scene graph uses its text-summary fallback):
 *   - setScene renders the C-major diatonic field (11 nodes / 7 occurrences);
 *   - the occurrence timeline shows 7 chips; the header names the scene;
 *   - updateOccurrenceState moves the current index + lights the right chip;
 *   - a scene replacement drops the previous scene's nodes (no stale ids);
 *   - requestSceneSeek enqueues a host seek request (dequeued via takeHostRequest);
 *   - an unsupported scene shows the honest "no graph" view (0 nodes).
 *
 * Run:  node tests/harmonic_scene_node_test.js
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const cp = require("child_process");

const ROOT = path.join(__dirname, "..");

function loadScenes() {
  const candidates = [
    path.join(ROOT, ".venv", "Scripts", "python.exe"),
    path.join(ROOT, ".venv", "bin", "python"),
    "python", "python3",
  ];
  const code = [
    "import json",
    "from harmony.atlas import full_key_spec, degree_spec",
    "from harmony.graph_scene_router import GraphSceneRequest, build_graph_scene",
    "from harmony.graph_scene_generators import build_unsupported",
    "def scene(spec): return build_graph_scene(GraphSceneRequest(exercise_spec=spec)).to_dict()",
    "out = {",
    "  'field': scene(full_key_spec('C','major')),",
    "  'fieldG': scene(full_key_spec('G','major')),",
    "  'degree': scene(degree_spec('V','major')),",
    "  'unsupported': build_unsupported(source_kind='lab', source_id='mot',"
      + " reason='melodic motive has no harmonic graph yet').to_dict(),",
    "}",
    "print(json.dumps(out))",
  ].join("\n");
  for (const py of candidates) {
    try {
      const out = cp.execFileSync(py, ["-c", code],
        { cwd: ROOT, encoding: "utf-8", maxBuffer: 64 * 1024 * 1024 });
      return JSON.parse(out);
    } catch (e) { /* try next */ }
  }
  console.error("SKIP: could not run Python to build scene payloads.");
  process.exit(0);
}

// --- minimal DOM harness (no createElementNS -> scene graph uses text summary) ---
let ALL = [];
function makeNode(tag) {
  const node = {
    tag: tag || "div", id: "", className: "", _text: "", _html: "", value: "",
    checked: false, dataset: {}, style: {}, _children: [], _listeners: {},
    appendChild(c) { this._children.push(c); return c; },
    addEventListener(ev, fn) { (this._listeners[ev] = this._listeners[ev] || []).push(fn); },
    setAttribute(k, v) { if (k === "class") this.className = v; this["_attr_" + k] = v; },
    getAttribute(k) { return this["_attr_" + k]; },
    removeAttribute() {}, remove() {},
    fire(ev, arg) { (this._listeners[ev] || []).forEach((fn) => fn(arg || {})); },
  };
  Object.defineProperty(node, "textContent",
    { get() { return this._text; }, set(v) { this._text = v; } });
  Object.defineProperty(node, "innerHTML",
    { get() { return this._html; }, set(v) { this._html = v; this._children = []; } });
  ALL.push(node);
  return node;
}
function deepText(node) {
  let t = node._text || "";
  (node._children || []).forEach((c) => { t += " " + deepText(c); });
  return t;
}
function byClass(cls) {
  return ALL.filter((n) => n.className && n.className.split(" ").indexOf(cls) !== -1);
}

function makeHarness() {
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
  const window = {};
  const sandbox = { window, document, console, Set, Math, Object, Array, String, JSON };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(ROOT, "beat_selector", "harmonic_network.js"),
    "utf-8"), sandbox, { filename: "harmonic_network.js" });
  return { HN: window.HarmonicNetwork, doc: document };
}

let failures = 0;
function ok(cond, msg) {
  if (!cond) { console.error("  FAIL: " + msg); failures++; }
  return cond;
}

const S = loadScenes();
const { HN, doc } = makeHarness();

// --- Test A: setScene renders the C-major diatonic field --------------------
let st = HN.setScene(S.field);
ok(st.sceneType === "diatonic_key_field", "A: sceneType diatonic_key_field (got " + st.sceneType + ")");
ok(st.nodes === 11, "A: 11 nodes (got " + st.nodes + ")");
ok(st.occurrences === 7, "A: 7 occurrences (got " + st.occurrences + ")");
ok(st.currentIndex === null, "A: no current index before play");
ok(st.nextIndex === 0, "A: next index starts at 0");
ok(HN.sceneNodeIds().indexOf("hn:triad:C:major:1") !== -1, "A: Dm triad node present");
ok(HN.sceneNodeIds().indexOf("hn:key:C") !== -1, "A: C key anchor present");
ok(deepText(doc.getElementById("hnTitle")).indexOf("C major") !== -1, "A: header names C major");
ok(byClass("occChip").length === 7, "A: 7 timeline chips (got " + byClass("occChip").length + ")");
console.log("Test A (setScene C-major field): " + (failures ? "FAIL" : "PASS"));

// --- Test B: updateOccurrenceState drives the running position --------------
let before = failures;
HN.updateOccurrenceState({ sequenceIndex: 4 });
let st2 = HN.sceneState();
ok(st2.currentIndex === 4, "B: current index 4 (got " + st2.currentIndex + ")");
ok(st2.nextIndex === 5, "B: next index 5");
ok(byClass("is-current").length >= 1, "B: a chip/node is current");
HN.updateOccurrenceState({ sequenceIndex: 5, correct: true });
ok(HN.sceneState().visited === 1, "B: one visited after advancing");
console.log("Test B (updateOccurrenceState): " + (failures > before ? "FAIL" : "PASS"));

// --- Test C: scene replacement drops stale nodes ----------------------------
before = failures;
HN.setScene(S.degree);
let st3 = HN.sceneState();
ok(st3.sceneType === "degree_transposition", "C: switched to degree_transposition");
ok(HN.sceneNodeIds().indexOf("hn:key:C") === -1, "C: previous scene's C key node is GONE (no stale ids)");
ok(HN.sceneNodeIds().indexOf("hn:degree:major:V") !== -1, "C: degree node present");
ok(st3.occurrences === 12, "C: 12 degree instances (got " + st3.occurrences + ")");
ok(st3.currentIndex === null, "C: running position reset on scene switch");
console.log("Test C (scene replacement, no stale nodes): " + (failures > before ? "FAIL" : "PASS"));

// --- Test D: requestSceneSeek enqueues a host request -----------------------
before = failures;
HN.setScene(S.field);
HN.requestSceneSeek(2);
let req = HN.takeHostRequest();
ok(req && req.type === "seek" && req.sequenceIndex === 2, "D: seek host request for index 2");
console.log("Test D (requestSceneSeek): " + (failures > before ? "FAIL" : "PASS"));

// --- Test E: unsupported scene shows the honest fail-closed view -------------
before = failures;
let stU = HN.setScene(S.unsupported);
ok(stU.sceneType === "unsupported", "E: unsupported scene type");
ok(stU.nodes === 0, "E: no nodes");
ok(deepText(doc.getElementById("hnCenter")).indexOf("No suitable harmonic graph") !== -1,
   "E: honest message shown");
console.log("Test E (unsupported fail-closed view): " + (failures > before ? "FAIL" : "PASS"));

// --- Test F: clearScene ------------------------------------------------------
before = failures;
HN.setScene(S.field);
HN.clearScene("switching exercise");
ok(HN.sceneState().sceneType == null, "F: scene cleared");
ok(deepText(doc.getElementById("hnCenter")).indexOf("No suitable harmonic graph") !== -1,
   "F: cleared view shown");
console.log("Test F (clearScene): " + (failures > before ? "FAIL" : "PASS"));

if (failures) { console.error("\n" + failures + " scene assertion(s) FAILED."); process.exit(1); }
console.log("\nAll harmonic_network.js SCENE-mode checks passed.");
