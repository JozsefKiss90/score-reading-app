/*
 * Executable MIDI-acceptance test: drives the REAL beat_selector/harmony_trainer.js
 * with Music-Theory-Lab payloads (the shape harmony.lab_musicxml.build_lab_payload
 * emits) and confirms the controller validates them correctly. This is the
 * end-to-end proof for P2/P3/P5 — especially that the optional strict-bass
 * inversion mode actually requires the BASS note first at runtime (the field the
 * controller reads is `pitchClasses`, so the bass must be `pitchClasses[0]`).
 *
 * The lab targets below mirror build_lab_payload's documented output; the Python
 * suite (tests/test_harmony_lab.py) locks the generator to these exact values.
 *
 * Run:  node tests/harmony_lab_midi_test.js
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
function midiToName(m) { return NAMES[((m % 12) + 12) % 12] + (Math.floor(m / 12) - 1); }

// PITCH_MAP: every sounding MIDI of a measure, under beat "1" (the controller
// maps pitch-class -> note ids per measure regardless of beat).
function makePitchMap(payload) {
  const pm = {};
  payload.TARGET_CHORDS.forEach((t) => {
    pm[String(t.absMeasure)] = {
      "1": t.midiPitches.map((m, k) => ({ id: "n" + t.absMeasure + "_" + k, pitch: midiToName(m) })),
    };
  });
  return pm;
}

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
    getElementById(id) { if (!nodes.has(id)) { const n = makeNode(); n.id = id; nodes.set(id, n); } return nodes.get(id); },
    createElement() { return makeNode(); },
    querySelector() { return null; }, head: makeNode(), body: makeNode(),
  };
  const keyStatus = new Map();
  const state = {
    boot: { PITCH_MAP: makePitchMap(payload) },
    selNotesByMidi: new Map(), selNoteIds: new Set(), midiDown: new Set(),
    boxesByAbs: {}, readySvg: true,
  };
  payload.TARGET_CHORDS.forEach((t) => { state.boxesByAbs[t.absMeasure] = {}; });
  const app = {
    state, lastMeasure: -1,
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
  window.onMidiNoteOn = (pitch, vel) => {
    if (Number(vel) <= 0) { window.onMidiNoteOff(pitch); return; }
    state.midiDown.add(pitch); app.refreshMidiHighlights();
  };
  window.onMidiNoteOff = (pitch) => { state.midiDown.delete(pitch); app.refreshMidiHighlights(); };
  const sandbox = { window, document, console, setTimeout: () => {}, clearTimeout: () => {} };
  vm.createContext(sandbox);
  vm.runInContext(
    fs.readFileSync(path.join(__dirname, "..", "beat_selector", "harmony_trainer.js"), "utf-8"),
    sandbox, { filename: "harmony_trainer.js" });
  return { window, app, state, keyStatus,
           noteOn: (p, v) => window.onMidiNoteOn(p, v === undefined ? 100 : v, 0),
           noteOff: (p) => window.onMidiNoteOff(p, 0) };
}

// Lab target builder with the full key set build_lab_payload emits.
function labTarget(o) {
  return Object.assign({
    measureNumber: o.absMeasure + 1, group: "g", key: "C major", mode: "major",
    scale: ["C", "D", "E", "F", "G", "A", "B"], degree: o.roman || "I",
    degreeNumber: 1, chordSymbol: "C", root: "C", quality: "major",
    chordTones: ["C", "E", "G"], intervalLayer: "M3+m3", functionLabel: "tonic",
    scaleDegreeName: "tonic", explanation: "...", labNote: "...",
  }, o);
}

let passed = 0;
function assert(cond, msg) {
  if (!cond) { console.error("FAIL:", msg); process.exitCode = 1; throw new Error(msg); }
  passed += 1;
}

// === Test A: strict-bass inversion requires the BASS note first =============
(function testStrictBass() {
  // First-inversion C major I, strict: pitchClasses bass-first [E,C,G] = [4,0,7].
  const payload = {
    title: "strict inv", render: "arpeggio",
    TARGET_CHORDS: [labTarget({
      absMeasure: 0, render: "arpeggio", pitchClasses: [4, 0, 7],
      midiPitches: [52, 60, 64, 67], bassPitchClass: 4,  // E3 + C4/E4/G4
    })],
  };

  // Pressing the root C (pc 0) first must be REJECTED (red, no advance).
  let h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);
  h.noteOn(60);  // C4
  assert(h.keyStatus.get(60) === "bad", "strict: root C first is red");
  assert(h.window.HarmonyTrainer.state().arpIndex === 0, "strict: root first does not advance");
  h.noteOff(60);

  // Pressing the bass E (pc 4) first must be ACCEPTED (green, advance).
  h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);
  h.noteOn(64);  // E4 (any octave of the bass pc)
  assert(h.keyStatus.get(64) === "ok", "strict: bass E first is green");
  assert(h.window.HarmonyTrainer.state().arpIndex === 1, "strict: bass first advances");
  h.noteOff(64);
  h.noteOn(60); h.noteOff(60);  // then C
  h.noteOn(67); h.noteOff(67);  // then G
  assert(h.window.HarmonyTrainer.state().finished === true, "strict: completes bottom-up");
  console.log("Test A (strict bass-first): PASS");
})();

// === Test B: non-strict inversion block accepts the chord tones in any order =
(function testBlockInversion() {
  const payload = {
    title: "block inv", render: "block",
    TARGET_CHORDS: [labTarget({
      absMeasure: 0, render: "block", pitchClasses: [0, 4, 7],
      midiPitches: [48, 60, 64, 67], bassPitchClass: 0,
    })],
  };
  const h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);
  // Any octave of any chord tone is green; out-of-chord is red.
  h.noteOn(64); assert(h.keyStatus.get(64) === "ok", "block: E green");
  h.noteOn(61); assert(h.keyStatus.get(61) === "bad", "block: C# red");
  h.noteOff(61);
  h.noteOn(60); h.noteOn(67);  // press full triad
  assert(h.window.HarmonyTrainer.state().completed === true, "block: completes on full triad");
  console.log("Test B (block inversion): PASS");
})();

// === Test C: SATB cadence validates the 3 reduced triad pitch classes ========
(function testSatb() {
  // V chord (G-B-D) reported as 3 pcs even though 4 voices sound.
  const payload = {
    title: "satb", render: "block",
    TARGET_CHORDS: [labTarget({
      absMeasure: 0, render: "block", roman: "V", chordSymbol: "G",
      pitchClasses: [7, 11, 2], midiPitches: [55, 59, 62, 67],  // G3 B3 D4 G4
    })],
  };
  const h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);
  h.noteOn(55); h.noteOn(59); h.noteOn(62);  // G B D
  assert(h.window.HarmonyTrainer.state().completed === true, "SATB: completes on G-B-D");
  console.log("Test C (SATB cadence): PASS");
})();

// === Test D: motive melody validates note-by-note in order ==================
(function testMotive() {
  const payload = {
    title: "motive", render: "arpeggio",
    TARGET_CHORDS: [labTarget({
      absMeasure: 0, render: "arpeggio", pitchClasses: [0, 4, 7, 4],
      midiPitches: [60, 64, 67, 64],
    })],
  };
  const h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);
  h.noteOn(64); assert(h.keyStatus.get(64) === "bad", "motive: E before its turn is red");
  h.noteOff(64);
  [60, 64, 67, 64].forEach((m) => { h.noteOn(m); h.noteOff(m); });
  assert(h.window.HarmonyTrainer.state().finished === true, "motive: finishes 1-3-5-3 in order");
  console.log("Test D (motive melody): PASS");
})();

// === Test E: technique phrase walks a multi-measure line in order ============
// Piano-technique ticket 01: the tracer's five-finger measure (revisiting
// pitch classes on the way down) + the rest-padded closing measure, exactly
// the shape harmony.lab_musicxml.build_lab_payload emits for the concept.
(function testTechniquePhrase() {
  const up = [60, 62, 64, 65, 67, 65, 64, 62];      // C D E F G F E D (eighths)
  const payload = {
    title: "technique", render: "arpeggio", concept: "technique",
    TARGET_CHORDS: [
      labTarget({
        absMeasure: 0, render: "arpeggio", concept: "melody",
        pitchClasses: [0, 2, 4, 5, 7, 5, 4, 2], midiPitches: up,
      }),
      labTarget({
        absMeasure: 1, render: "arpeggio", concept: "melody",
        pitchClasses: [0], midiPitches: [60],
      }),
    ],
  };
  const h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);
  // A wrong note is red and does NOT advance the walk (grading honesty).
  h.noteOn(61); assert(h.keyStatus.get(61) === "bad", "technique: C# is red");
  assert(h.window.HarmonyTrainer.state().arpIndex === 0, "technique: wrong note does not advance");
  h.noteOff(61);
  up.forEach((m) => { h.noteOn(m); h.noteOff(m); });
  assert(h.app.lastMeasure === 1, "technique: cursor moved to the final measure");
  // Octave-agnostic close: the final tonic accepted an octave up (C5).
  h.noteOn(72); h.noteOff(72);
  assert(h.window.HarmonyTrainer.state().finished === true,
         "technique: finishes the two-measure phrase in order");
  console.log("Test E (technique phrase): PASS");
})();

console.log("\nAll harmony_lab MIDI-acceptance checks passed (" + passed + " assertions).");
