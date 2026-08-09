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
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
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

// === Test B2: four-tone accent cell (piano-technique ticket 06) =============
(function testArpeggioAccentCell() {
  // arp_octave_root payload: pitchClasses [r, 3rd, 5th, r], the 4th quarter
  // the root an octave up. The ordered walk accepts the return to the root
  // mod-12 (any octave), with no JS change.
  const payload = {
    title: "C cell", render: "arpeggio",
    TARGET_CHORDS: [
      target(0, "arpeggio", "I", "C", "C", "major", ["C", "E", "G", "C"], [0, 4, 7, 0], [60, 64, 67, 72], "M3+m3", "tonic", "tonic"),
    ],
  };
  const h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);

  h.noteOn(60); h.noteOff(60);
  h.noteOn(64); h.noteOff(64);
  h.noteOn(67); h.noteOff(67);
  assert(h.window.HarmonyTrainer.state().arpIndex === 3, "three tones down, cell not finished");
  assert(h.window.HarmonyTrainer.state().finished !== true, "the 4th tone is still owed");
  // The return to the root is green and finishes the cell — octave-blind.
  h.noteOn(60); assert(h.keyStatus.get(60) === "ok", "root return green in any octave");
  h.noteOff(60);
  assert(h.window.HarmonyTrainer.state().finished === true, "finished after the 4-tone cell");
  console.log("Test B2 (four-tone accent cell): PASS");
})();

// === Test B3: repeated-pc walk lights only walked noteheads =================
(function testSlotAwareSelection() {
  // The arpeggio-run bug (piano-technique ticket 06): a bar whose walk
  // repeats a pitch class (three C's: C4/C5/C6) must NOT light every same-pc
  // notehead at once — only the walked slots plus the current one.  Grading
  // stays octave-blind; this is the display contract.
  const t0 = target(0, "arpeggio", "I", "C", "C", "major",
    ["C", "E", "G", "C", "E", "G", "C", "G"],
    [0, 4, 7, 0, 4, 7, 0, 7],
    [60, 64, 67, 72, 76, 79, 84, 79], "M3+m3", "tonic", "tonic");
  t0.slotsPerMeasure = 8;
  const payload = { title: "run", render: "arpeggio", TARGET_CHORDS: [t0] };
  const h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);

  const idsFor = (midi) => {
    const ids = h.state.selNotesByMidi.get(midi);
    return ids ? [...ids].filter((i) => !i.startsWith("__ht")) : [];
  };

  // At the start only slot 0's C notehead is selectable — not slots 3 and 6.
  assert(idsFor(60).includes("n0_0"), "slot-0 C selected at start");
  assert(!idsFor(60).includes("n0_3"), "future C (slot 3) unlit at start");
  assert(!idsFor(60).includes("n0_6"), "future C (slot 6) unlit at start");
  assert(idsFor(72).includes("n0_0"), "octave-blind: C5 maps to the same slot");

  // Walk C E G: the current step becomes slot 3 (the second C).
  h.noteOn(60); h.noteOff(60);
  h.noteOn(64); h.noteOff(64);
  h.noteOn(67); h.noteOff(67);
  assert(h.window.HarmonyTrainer.state().arpIndex === 3, "walked to slot 3");
  assert(idsFor(60).includes("n0_0"), "played C stays selected");
  assert(idsFor(60).includes("n0_3"), "current C (slot 3) selected");
  assert(!idsFor(60).includes("n0_6"), "future C (slot 6) still unlit");
  assert(!h.state.selNoteIds.has("n0_6"), "slot 6 not in the selection set");
  // The future E (slot 4) is not lit either while slot 3 is current.
  assert(!idsFor(64).includes("n0_4"), "future E (slot 4) unlit");

  console.log("Test B3 (slot-aware repeated-pc selection): PASS");
})();

// === Test B4: trainer cell keeps slot-awareness despite the bass row =======
(function testSlotAwareWithBass() {
  // A trainer measure's PITCH_MAP also carries the notated bass whole note;
  // it is not part of the walk and must not break the slot alignment.
  const t0 = target(0, "arpeggio", "I", "C", "C", "major",
    ["C", "E", "G", "C"], [0, 4, 7, 0], [60, 64, 67, 72],
    "M3+m3", "tonic", "tonic");
  t0.bassMidi = 48;
  const payload = { title: "cell", render: "arpeggio", TARGET_CHORDS: [t0] };
  const h = makeHarness(payload);
  // Hand-build the pitch map with the bass row present.
  h.state.boot.PITCH_MAP = { "0": {
    "1": [{ id: "n0_b", pitch: "C3" }, { id: "n0_0", pitch: "C4" }],
    "2": [{ id: "n0_1", pitch: "E4" }],
    "3": [{ id: "n0_2", pitch: "G4" }],
    "4": [{ id: "n0_3", pitch: "C5" }],
  } };
  h.window.HarmonyTrainer.init(payload);

  const idsFor = (midi) => {
    const ids = h.state.selNotesByMidi.get(midi);
    return ids ? [...ids].filter((i) => !i.startsWith("__ht")) : [];
  };
  assert(idsFor(60).includes("n0_0"), "slot-0 C selected at start (cell)");
  assert(!idsFor(60).includes("n0_3"), "octave-root C unlit until walked");
  assert(!idsFor(60).includes("n0_b"), "bass row never joins the walk");
  console.log("Test B4 (slot-aware with bass row): PASS");
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

// === Test D: re-init does not stack MIDI handlers ===========================
(function testReinitNoStacking() {
  const payload = {
    title: "C arp", render: "arpeggio",
    TARGET_CHORDS: [
      target(0, "arpeggio", "I", "C", "C", "major", ["C", "E", "G"], [0, 4, 7], [60, 64, 67], "M3+m3", "tonic", "tonic"),
    ],
  };
  const h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);
  h.window.HarmonyTrainer.init(payload); // re-init on the SAME window/page
  // One physical root press must advance arpIndex by exactly 1. If init()
  // stacked the wrappers, afterNoteOn would fire twice and jump arpIndex to 2.
  h.noteOn(60);
  assert(h.window.HarmonyTrainer.state().arpIndex === 1,
    "re-init does not stack handlers (single advance per note)");
  h.noteOff(60);
  console.log("Test D (re-init no stacking): PASS");
})();

// === Test E: velocity-0 note-on is treated as a note-off ====================
(function testVelocityZero() {
  const payload = {
    title: "C arp", render: "arpeggio",
    TARGET_CHORDS: [
      target(0, "arpeggio", "I", "C", "C", "major", ["C", "E", "G"], [0, 4, 7], [60, 64, 67], "M3+m3", "tonic", "tonic"),
    ],
  };
  const h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);
  // Many MIDI sources encode note-off as note-on velocity 0.
  h.noteOn(60, 0);
  assert(h.window.HarmonyTrainer.state().arpIndex === 0,
    "velocity-0 does not advance the arpeggio");
  assert(!h.state.midiDown.has(60),
    "velocity-0 routed to note-off (key is not held)");
  console.log("Test E (velocity-0 note-off): PASS");
})();

console.log("\nAll harmony_trainer.js behavioural checks passed (" + passed + " assertions).");
