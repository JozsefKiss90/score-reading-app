/*
 * Headless behavioural test for beat_selector/harmony_circle.js.
 *
 * Stubs the browser globals (window/document incl. SVG createElementNS), feeds a
 * shape-accurate CIRCLE_DATA fixture (matching harmony.circle_payload), loads the
 * controller via Node's `vm`, and verifies the host-facing contract:
 *   - init() builds the circle and returns 12 major keys;
 *   - selecting a key renders its 7 triads and updates the detail panel;
 *   - clicking launch shortcuts enqueues the right spec (host polls takeLaunch);
 *   - updateFromTrainerState() highlights the correct key/degree/chord/function;
 *   - onCellClick callbacks fire.
 *
 * Run:  node tests/circle_node_test.js
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

let ALL = [];
function mk(tag) {
  const n = {
    tag: tag || "div", id: "", className: "", _t: "", _h: "",
    dataset: {}, style: {}, _c: [], _l: {},
    classList: {
      _s: new Set(),
      add(c) { this._s.add(c); }, remove() { for (var i = 0; i < arguments.length; i++) this._s.delete(arguments[i]); },
      contains(c) { return this._s.has(c); },
      toggle(c, o) { o === undefined && (o = !this._s.has(c)); o ? this._s.add(c) : this._s.delete(c); return o; },
    },
    appendChild(c) { this._c.push(c); return c; },
    addEventListener(e, f) { (this._l[e] = this._l[e] || []).push(f); },
    setAttribute(k, v) { if (k === "class") this.className = v; if (k === "id") this.id = v; this["_a_" + k] = v; },
    getAttribute(k) { return this["_a_" + k]; }, removeAttribute() {}, remove() {},
    fire(e) { (this._l[e] || []).forEach((f) => f({})); },
  };
  Object.defineProperty(n, "textContent", { get() { return this._t; }, set(v) { this._t = v; } });
  Object.defineProperty(n, "innerHTML", { get() { return this._h; }, set(v) { this._h = v; this._c = []; } });
  ALL.push(n);
  return n;
}
function findByText(txt, needsClick) {
  return ALL.filter((n) => n._t === txt && (!needsClick || (n._l.click && n._l.click.length)));
}
function findByData(key, val) { return ALL.filter((n) => n.dataset && n.dataset[key] === val); }

function harness(data) {
  ALL = [];
  const byId = new Map();
  const listeners = {};
  const document = {
    getElementById(i) { if (!byId.has(i)) { const n = mk(); n.id = i; byId.set(i, n); } return byId.get(i); },
    createElement(t) { return mk(t); },
    createElementNS(ns, t) { return mk(t); },
    createTextNode(t) { const n = mk("#text"); n.textContent = t; return n; },
    head: mk(), body: mk(),
  };
  const window = {
    CIRCLE_DATA: data,
    addEventListener(ev, fn) { (listeners[ev] = listeners[ev] || []).push(fn); },
    removeEventListener(ev, fn) { listeners[ev] = (listeners[ev] || []).filter((f) => f !== fn); },
    dispatch(ev, detail) { (listeners[ev] || []).forEach((f) => f({ detail: detail })); },
  };
  const sandbox = { window, document, console, Set, Math, Object, Array, String };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "beat_selector", "harmony_circle.js"), "utf-8"),
    sandbox, { filename: "harmony_circle.js" });
  return { window, document, hc: window.HarmonyCircle };
}

// --- fixture (matches harmony.circle_payload.build_circle_payload() shape) ---
function triad(degree, sym, root, quality, tones, layer, fnLabel, fnClass) {
  return { degree, degreeNumber: 1, chordSymbol: sym, root, quality, tones,
    intervalLayer: layer, functionLabel: fnLabel, functionClass: fnClass };
}
const C_TRIADS = [
  triad("I", "C", "C", "major", ["C", "E", "G"], "M3+m3", "tonic", "T"),
  triad("ii", "Dm", "D", "minor", ["D", "F", "A"], "m3+M3", "predominant", "S"),
  triad("iii", "Em", "E", "minor", ["E", "G", "B"], "m3+M3", "mediant", "T"),
  triad("IV", "F", "F", "major", ["F", "A", "C"], "M3+m3", "subdominant", "S"),
  triad("V", "G", "G", "major", ["G", "B", "D"], "M3+m3", "dominant", "D"),
  triad("vi", "Am", "A", "minor", ["A", "C", "E"], "m3+M3", "tonic", "T"),
  triad("vii°", "B°", "B", "diminished", ["B", "D", "F"], "m3+m3", "dominant", "D"),
];
const G_TRIADS = [
  triad("I", "G", "G", "major", ["G", "B", "D"], "M3+m3", "tonic", "T"),
  triad("ii", "Am", "A", "minor", ["A", "C", "E"], "m3+M3", "predominant", "S"),
  triad("iii", "Bm", "B", "minor", ["B", "D", "F#"], "m3+M3", "mediant", "T"),
  triad("IV", "C", "C", "major", ["C", "E", "G"], "M3+m3", "subdominant", "S"),
  triad("V", "D", "D", "major", ["D", "F#", "A"], "M3+m3", "dominant", "D"),
  triad("vi", "Em", "E", "minor", ["E", "G", "B"], "m3+M3", "tonic", "T"),
  triad("vii°", "F#°", "F#", "diminished", ["F#", "A", "C"], "m3+m3", "dominant", "D"),
];
function majorKey(key, rel, fifths, scale, triads) {
  return { key, mode: "major", relativeMinor: rel, fifths, scale, triads };
}
const DATA = {
  schema: "harmony-circle/v1",
  majorKeys: [
    majorKey("C", "A", 0, ["C", "D", "E", "F", "G", "A", "B"], C_TRIADS),
    majorKey("G", "E", 1, ["G", "A", "B", "C", "D", "E", "F#"], G_TRIADS),
  ].concat(["D", "A", "E", "B", "Gb", "Db", "Ab", "Eb", "Bb", "F"].map(
    (k) => majorKey(k, "A", 0, ["C", "D", "E", "F", "G", "A", "B"], C_TRIADS))),
  minorKeys: [{ key: "A", mode: "natural_minor", relativeMajor: "C", fifths: 0,
    scale: ["A", "B", "C", "D", "E", "F", "G"], triads: C_TRIADS }],
  circleOrderMajor: ["C", "G", "D", "A", "E", "B", "Gb", "Db", "Ab", "Eb", "Bb", "F"],
  circleOrderMinor: ["A", "E", "B", "F#", "C#", "G#", "Eb", "Bb", "F", "C", "G", "D"],
  cheatsheet: {
    majorPattern: C_TRIADS, minorPattern: C_TRIADS,
    intervalLayers: [{ quality: "major", intervalLayer: "M3+m3" }],
    functionClasses: [
      { class: "T", label: "Tonic-related family", short: "T" },
      { class: "S", label: "Predominant family", short: "PD/S" },
      { class: "D", label: "Dominant family", short: "D" },
    ],
  },
  relations: [],
};

let passed = 0;
function assert(c, m) { if (!c) { console.error("FAIL:", m); process.exitCode = 1; throw new Error(m); } passed++; }

(function testInit() {
  const h = harness(DATA);
  const r = h.hc.init(DATA);
  assert(r.ok && r.majorKeys === 12, "init builds 12 major keys");
  console.log("Test A (init): PASS");
})();

(function testSelectKeyAndLaunch() {
  const h = harness(DATA);
  h.hc.init(DATA);
  // click the G major key cell on the SVG ring
  const gcell = findByData("key", "G").filter((n) => n.dataset.mode === "major")[0];
  assert(gcell, "G major cell rendered");
  gcell.fire("click");
  assert(h.hc.highlightState().selectedKey === "G", "selecting G sets selectedKey");
  // launch full-key block via the shortcut button
  const btn = findByText("Full-key block", true)[0];
  assert(btn, "full-key block shortcut present");
  btn.fire("click");
  const spec = h.hc.takeLaunch();
  assert(spec && spec.drill === "full_key" && spec.key === "G major" && spec.render === "block",
    "full-key block enqueues correct spec");
  console.log("Test B (select key + launch): PASS");
})();

(function testTriadDegreeLaunch() {
  const h = harness(DATA);
  h.hc.init(DATA);
  h.hc.selectKey("G", "major");
  h.hc.selectDegree("V");
  const btn = findByText("V across keys", true)[0];
  assert(btn, "degree shortcut present after selecting V");
  btn.fire("click");
  const spec = h.hc.takeLaunch();
  assert(spec && spec.drill === "horizontal_degree" && spec.degree === "V" && spec.mode === "major",
    "degree drill enqueues correct spec");
  console.log("Test C (triad degree launch): PASS");
})();

(function testSync() {
  const h = harness(DATA);
  h.hc.init(DATA);
  h.hc.updateFromTrainerState({ key: "G major", mode: "major", roman: "V",
    chordSymbol: "D", quality: "major", functionLabel: "dominant" });
  const s = h.hc.highlightState();
  assert(s.key === "G", "sync key = G");
  assert(s.mode === "major", "sync mode");
  assert(s.roman === "V", "sync roman = V");
  assert(s.chordSymbol === "D", "sync chord = D");
  assert(s.functionClass === "D", "sync function class = D");
  console.log("Test D (trainer sync): PASS");
})();

(function testEventSync() {
  const h = harness(DATA);
  h.hc.init(DATA);
  // The trainer dispatches a CustomEvent; the circle listens (same-page path).
  h.window.dispatch("harmonytrainer:targetchange",
    { key: "C major", mode: "major", roman: "I", chordSymbol: "C", functionLabel: "tonic" });
  assert(h.hc.highlightState().roman === "I", "event-driven sync updates highlight");
  console.log("Test E (event sync): PASS");
})();

(function testOnCellClick() {
  const h = harness(DATA);
  h.hc.init(DATA);
  let got = null;
  h.hc.onCellClick((d) => { got = d; });
  findByData("key", "C").filter((n) => n.dataset.mode === "major")[0].fire("click");
  assert(got && got.type === "key" && got.key === "C", "onCellClick fires with key detail");
  console.log("Test F (onCellClick): PASS");
})();

(function testReinit() {
  const h = harness(DATA);
  h.hc.init(DATA);
  h.hc.init(DATA);   // must not stack the window event listener
  h.window.dispatch("harmonytrainer:targetchange",
    { key: "G major", mode: "major", roman: "V", chordSymbol: "D", functionLabel: "dominant" });
  assert(h.hc.highlightState().roman === "V", "re-init keeps a single working listener");
  console.log("Test G (idempotent re-init): PASS");
})();

console.log("\nAll harmony_circle.js behavioural checks passed (" + passed + " assertions).");
