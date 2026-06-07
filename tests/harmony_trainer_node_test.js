/*
 * Headless behavioural test for beat_selector/harmony_trainer.js.
 *
 * The GUI can't run in CI, so this harness stubs the browser globals
 * (window/document/setTimeout) and the existing ScoreApp + MIDI bridge, loads
 * the trainer controller via Node's `vm`, and drives MIDI note-on/off events to
 * verify:
 *   - the current target chord is "ok" (green) and other pitches are "bad" (red),
 *     octave-agnostically;
 *   - block mode advances only after all tones were pressed AND released;
 *   - arpeggio mode enforces tone order and advances per tone.
 *
 * Run:  node tests/harmony_trainer_node_test.js
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
function midiToName(m) { return NAMES[((m % 12) + 12) % 12] + (Math.floor(m / 12) - 1); }

function makePitchMap(payload) {
  const pm = {};
  payload.TARGET_CHORDS.forEach((t) => {
    pm[String(t.absMeasure)] = {
      "1": t.midiPitches.map((m, k) => ({ id: "n" + t.absMeasure + "_" + k, pitch: midiToName(m) })),
    };
  });
  return pm;
}

function target(absMeasure, render, roman, sym, root, quality, tones, pcs, midis, layer, fn, deg) {
  return {
    absMeasure, render, key: "C major", mode: "major",
    scale: ["C", "D", "E", "F", "G", "A", "B"],
    roman, degree: roman, degreeNumber: 1, chordSymbol: sym, root, quality,
    chordTones: tones, pitchClasses: pcs, midiPitches: midis,
    intervalLayer: layer, functionLabel: fn, scaleDegreeName: deg, explanation: "...",
  };
}

// --- DOM/host stubs ---------------------------------------------------------
function makeNode() {
  return {
    id: "", className: "", textContent: "", _innerHTML: "",
    dataset: {}, style: {}, firstChild: null,
    set innerHTML(v) { this._innerHTML = v; }, get innerHTML() { return this._innerHTML; },
    appendChild() {}, insertBefore() {}, addEventListener() {},
    remove() {}, querySelector() { return null; }, querySelectorAll() { return []; },
  };
}

function makeHarness(payload) {
  const nodes = new Map();
  const document = {
    getElementById(id) {
      if (!nodes.has(id)) { const n = makeNode(); n.id = id; nodes.set(id, n); }
      return nodes.get(id);
    },
    createElement() { return makeNode(); },
    querySelector() { return null; },
    head: makeNode(),
    body: makeNode(),
  };

  const keyStatus = new Map();
  const state = {
    boot: { PITCH_MAP: makePitchMap(payload) },
    selNotesByMidi: new Map(),
    selNoteIds: new Set(),
    midiDown: new Set(),
    boxesByAbs: {},
    readySvg: true,
  };
  payload.TARGET_CHORDS.forEach((t) => { state.boxesByAbs[t.absMeasure] = {}; });

  const app = {
    state,
    lastMeasure: -1,
    jsSetCursorAbs(abs) { this.lastMeasure = abs; },
    refreshMidiHighlights() {
      keyStatus.clear();
      for (const m of state.midiDown) {
        const ids = state.selNotesByMidi.get(m);
        keyStatus.set(m, (ids && ids.size > 0) ? "ok" : "bad");
      }
    },
  };

  const window = { ScoreApp: app };
  // Base MIDI bridge (what beatpage.html installs), wrapped by the controller.
  window.onMidiNoteOn = (pitch, vel) => {
    if (Number(vel) <= 0) { window.onMidiNoteOff(pitch); return; }
    state.midiDown.add(pitch);
    app.refreshMidiHighlights();
  };
  window.onMidiNoteOff = (pitch) => {
    state.midiDown.delete(pitch);
    app.refreshMidiHighlights();
  };

  const sandbox = {
    window, document, console,
    setTimeout: () => {}, clearTimeout: () => {},
  };
  vm.createContext(sandbox);
  const code = fs.readFileSync(
    path.join(__dirname, "..", "beat_selector", "harmony_trainer.js"), "utf-8");
  vm.runInContext(code, sandbox, { filename: "harmony_trainer.js" });

  return { window, app, state, keyStatus,
           noteOn: (p, v) => window.onMidiNoteOn(p, v === undefined ? 100 : v, 0),
           noteOff: (p) => window.onMidiNoteOff(p, 0) };
}

// --- assertions -------------------------------------------------------------
let passed = 0;
function assert(cond, msg) {
  if (!cond) { console.error("FAIL:", msg); process.exitCode = 1; throw new Error(msg); }
  passed += 1;
}

// === Test A: block mode =====================================================
(function testBlock() {
  const payload = {
    title: "C major", render: "block",
    TARGET_CHORDS: [
      target(0, "block", "I", "C", "C", "major", ["C", "E", "G"], [0, 4, 7], [60, 64, 67], "M3+m3", "tonic", "tonic"),
      target(1, "block", "ii", "Dm", "D", "minor", ["D", "F", "A"], [2, 5, 9], [62, 65, 69], "m3+M3", "predominant", "supertonic"),
    ],
  };
  const h = makeHarness(payload);
  const r = h.window.HarmonyTrainer.init(payload);
  assert(r.ok, "block init ok");
  assert(h.app.lastMeasure === 0, "highlight starts on measure 0");

  // Correct pitch (any octave) = green; out-of-chord = red.
  h.noteOn(60); assert(h.keyStatus.get(60) === "ok", "C4 is green for I");
  h.noteOff(60);
  h.noteOn(48); assert(h.keyStatus.get(48) === "ok", "C3 (other octave) green");
  h.noteOff(48);
  h.noteOn(61); assert(h.keyStatus.get(61) === "bad", "C#4 is red for I");
  h.noteOff(61);

  // Press the whole triad: still on chord 0 until released.
  h.noteOn(60); h.noteOn(64); h.noteOn(67);
  assert(h.window.HarmonyTrainer.state().idx === 0, "no advance while held");
  assert(h.window.HarmonyTrainer.state().completed === true, "marked completed");
  // Release all -> advance to chord 1.
  h.noteOff(60); h.noteOff(64);
  assert(h.window.HarmonyTrainer.state().idx === 0, "no advance until fully released");
  h.noteOff(67);
  assert(h.window.HarmonyTrainer.state().idx === 1, "advanced after full release");
  assert(h.app.lastMeasure === 1, "highlight moved to measure 1");

  // Now target is ii (D-F-A): D green, C red.
  h.noteOn(62); assert(h.keyStatus.get(62) === "ok", "D green for ii");
  h.noteOn(60); assert(h.keyStatus.get(60) === "bad", "C red for ii");
  h.noteOff(62); h.noteOff(60);

  // Partial chord must NOT advance.
  h.noteOn(62); h.noteOn(65); h.noteOff(62); h.noteOff(65);
  assert(h.window.HarmonyTrainer.state().idx === 1, "partial chord does not advance");

  console.log("Test A (block): PASS");
})();

// === Test B: arpeggio mode ==================================================
(function testArpeggio() {
  const payload = {
    title: "C arp", render: "arpeggio",
    TARGET_CHORDS: [
      target(0, "arpeggio", "I", "C", "C", "major", ["C", "E", "G"], [0, 4, 7], [60, 64, 67], "M3+m3", "tonic", "tonic"),
    ],
  };
  const h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);

  // Initially only the root (C) is expected; E pressed early is wrong/red.
  h.noteOn(64); assert(h.keyStatus.get(64) === "bad", "E red before its turn");
  h.noteOff(64);
  assert(h.window.HarmonyTrainer.state().arpIndex === 0, "out-of-order does not advance");

  // Correct order: C -> E -> G.
  h.noteOn(60); assert(h.keyStatus.get(60) === "ok", "C green (root first)");
  h.noteOff(60);
  assert(h.window.HarmonyTrainer.state().arpIndex === 1, "advance after root");
  h.noteOn(64); assert(h.keyStatus.get(64) === "ok", "E green (its turn)");
  h.noteOff(64);
  assert(h.window.HarmonyTrainer.state().arpIndex === 2, "advance after third");
  h.noteOn(67); assert(h.keyStatus.get(67) === "ok", "G green (last)");
  h.noteOff(67);
  assert(h.window.HarmonyTrainer.state().finished === true, "finished after last tone");

  console.log("Test B (arpeggio): PASS");
})();

// === Test C: navigation =====================================================
(function testNav() {
  const payload = {
    title: "C major", render: "block",
    TARGET_CHORDS: [
      target(0, "block", "I", "C", "C", "major", ["C", "E", "G"], [0, 4, 7], [60, 64, 67], "M3+m3", "tonic", "tonic"),
      target(1, "block", "ii", "Dm", "D", "minor", ["D", "F", "A"], [2, 5, 9], [62, 65, 69], "m3+M3", "predominant", "supertonic"),
    ],
  };
  const h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);
  h.window.HarmonyTrainer.goTo(1);
  assert(h.window.HarmonyTrainer.state().idx === 1, "goTo(1)");
  assert(h.app.lastMeasure === 1, "goTo moves highlight");
  // Selection followed: D green, C red on chord ii.
  h.noteOn(62); assert(h.keyStatus.get(62) === "ok", "nav selection applied");
  h.noteOff(62);
  h.window.HarmonyTrainer.goTo(99); // clamps
  assert(h.window.HarmonyTrainer.state().idx === 1, "goTo clamps to last");
  console.log("Test C (navigation): PASS");
})();

console.log("\nAll harmony_trainer.js behavioural checks passed (" + passed + " assertions).");
