/*
 * Executable MIDI-acceptance test for strict-bass (lowest-note) grading in
 * beat_selector/harmony_trainer.js (ticket 04 / plan G4/F4).
 *
 * A block target carrying `strictBass: true` + `bassPitchClass` demands the
 * named chord member as the LOWEST sounding note: the right pitch-class set
 * with the wrong bass does not complete, and the feedback names the expected
 * bass.  Targets without the flag keep the octave-agnostic set check.
 *
 * Run:  node tests/harmony_trainer_bass_test.js
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
  return { window, app, state, keyStatus, nodes,
           noteOn: (p, v) => window.onMidiNoteOn(p, v === undefined ? 100 : v, 0),
           noteOff: (p) => window.onMidiNoteOff(p, 0) };
}

// First-inversion C major (C/E): root-position pcs, bass must be E (pc 4).
function invTarget(extra) {
  return Object.assign({
    absMeasure: 0, measureNumber: 1, group: "g", render: "block",
    key: "C major", mode: "major",
    scale: ["C", "D", "E", "F", "G", "A", "B"], degree: "I", degreeNumber: 1,
    roman: "I", chordSymbol: "C", root: "C", quality: "major",
    chordTones: ["C", "E", "G"], pitchClasses: [0, 4, 7],
    midiPitches: [52, 60, 64, 67],
    intervalLayer: "M3+m3", functionLabel: "tonic", scaleDegreeName: "tonic",
    explanation: "...",
    inversion: 1, figuredBass: "6", inversionLabel: "first inversion",
    bassNote: "E", bassPitchClass: 4,
  }, extra);
}

let passed = 0;
function assert(cond, msg) {
  if (!cond) { console.error("FAIL:", msg); process.exitCode = 1; throw new Error(msg); }
  passed += 1;
}

// === Test A: wrong bass fails; feedback names the expected bass ==============
(function testWrongBassFails() {
  const payload = { title: "inv", render: "block",
                    TARGET_CHORDS: [invTarget({ strictBass: true })] };
  const h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);
  // Full pitch-class set with C in the bass (C4-E4-G4): must NOT complete.
  h.noteOn(60); h.noteOn(64); h.noteOn(67);
  assert(h.window.HarmonyTrainer.state().completed === false,
         "strictBass: right tones + wrong bass does not complete");
  const msg = h.nodes.get("htBassMsg");
  assert(msg && /E/.test(msg._innerHTML || msg.textContent),
         "strictBass: feedback names the expected bass (E)");
  console.log("Test A (wrong bass fails, feedback names bass): PASS");
})();

// === Test B: correct bass (any octave, lowest) completes =====================
(function testCorrectBassCompletes() {
  const payload = { title: "inv", render: "block",
                    TARGET_CHORDS: [invTarget({ strictBass: true })] };
  const h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);
  h.noteOn(52); h.noteOn(60); h.noteOn(67);   // E3 + C4 + G4
  assert(h.window.HarmonyTrainer.state().completed === true,
         "strictBass: E lowest completes");
  console.log("Test B (correct bass completes): PASS");
})();

// === Test C: retry after release; then recovery by adding a lower bass ======
(function testRetryAndRecovery() {
  const payload = { title: "inv", render: "block",
                    TARGET_CHORDS: [invTarget({ strictBass: true })] };
  // Wrong attempt, release everything, then a clean correct attempt.
  let h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);
  h.noteOn(60); h.noteOn(64); h.noteOn(67);
  assert(h.window.HarmonyTrainer.state().completed === false, "retry: wrong attempt fails");
  h.noteOff(60); h.noteOff(64); h.noteOff(67);   // all released -> attempt resets
  h.noteOn(52); h.noteOn(60); h.noteOn(67);
  assert(h.window.HarmonyTrainer.state().completed === true, "retry: clean attempt completes");

  // Recovery: after a wrong-bass chord, adding the demanded bass BELOW fixes it.
  h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);
  h.noteOn(60); h.noteOn(64); h.noteOn(67);
  assert(h.window.HarmonyTrainer.state().completed === false, "recovery: wrong at first");
  h.noteOn(52);                                   // add E3 below everything
  assert(h.window.HarmonyTrainer.state().completed === true, "recovery: low E completes");
  console.log("Test C (retry + recovery): PASS");
})();

// === Test D: without strictBass the check is octave-agnostic (regression) ====
(function testNonStrictUnchanged() {
  const payload = { title: "inv", render: "block",
                    TARGET_CHORDS: [invTarget({})] };   // bassPitchClass present, NO flag
  const h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);
  h.noteOn(60); h.noteOn(64); h.noteOn(67);   // C in the bass
  assert(h.window.HarmonyTrainer.state().completed === true,
         "non-strict: octave-agnostic set check still completes");
  console.log("Test D (non-strict unchanged): PASS");
})();

// === Test E: strict target advances only after release, like any block ======
(function testAdvanceAfterRelease() {
  const payload = { title: "inv", render: "block",
                    TARGET_CHORDS: [
                      invTarget({ strictBass: true }),
                      invTarget({ absMeasure: 1, measureNumber: 2 }),
                    ] };
  const h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);
  h.noteOn(52); h.noteOn(60); h.noteOn(67);
  assert(h.window.HarmonyTrainer.state().completed === true, "advance: completes held");
  assert(h.window.HarmonyTrainer.state().idx === 0, "advance: not yet advanced");
  h.noteOff(52); h.noteOff(60); h.noteOff(67);
  assert(h.window.HarmonyTrainer.state().idx === 1, "advance: moves on after release");
  console.log("Test E (advance after release): PASS");
})();

// === Test F: a released bass tap does not count — the bass must SOUND ========
(function testReleasedBassDoesNotCount() {
  const payload = { title: "inv", render: "block",
                    TARGET_CHORDS: [invTarget({ strictBass: true })] };
  const h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);
  h.noteOn(52); h.noteOff(52);                 // tap E3, let it go
  h.noteOn(60); h.noteOn(64); h.noteOn(67);    // C4-E4-G4: E no longer sounds below
  assert(h.window.HarmonyTrainer.state().completed === false,
         "released bass: C lowest sounding must not complete");
  h.noteOn(52);                                // hold the real bass under it
  assert(h.window.HarmonyTrainer.state().completed === true,
         "released bass: sounding E3 completes");
  console.log("Test F (released bass does not count): PASS");
})();

// === Test G: a stray released low tap does not poison the attempt ===========
(function testStrayReleasedTapForgiven() {
  const payload = { title: "inv", render: "block",
                    TARGET_CHORDS: [invTarget({ strictBass: true })] };
  const h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);
  h.noteOn(48); h.noteOff(48);                 // brush C3, release it
  h.noteOn(52); h.noteOn(60); h.noteOn(67);    // then voice the chord correctly
  assert(h.window.HarmonyTrainer.state().completed === true,
         "stray tap: correct sounding voicing completes despite earlier C3 tap");
  console.log("Test G (stray released tap forgiven): PASS");
})();

console.log("\nAll strict-bass grading checks passed (" + passed + " assertions).");
