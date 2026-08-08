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
  return { window, app, state, keyStatus, nodes,
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

// === Test F: dyad steps demand concurrent keys (ticket 03) ===================
// steps: [{pcs, minDistinct}] — the ordered simultaneity walk.  Out-of-order
// arrival within a step is fine (E before C), releasing between the halves
// just leaves the step unsatisfied (no error state), and finger-legato
// overlap into the NEXT dyad passes.
(function testDyadSteps() {
  const payload = {
    title: "thirds", render: "arpeggio", concept: "technique",
    TARGET_CHORDS: [labTarget({
      absMeasure: 0, render: "arpeggio", concept: "melody",
      pitchClasses: [0, 4, 2, 5], midiPitches: [60, 64, 62, 65],
      steps: [{ pcs: [0, 4], minDistinct: 2 },
              { pcs: [2, 5], minDistinct: 2 }],
    })],
  };

  // Near-miss forgiveness: C alone, released, then E alone never satisfies.
  let h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);
  h.noteOn(60); h.noteOff(60); h.noteOn(64);
  assert(h.window.HarmonyTrainer.state().arpIndex === 0,
         "dyad: sequential C-then-E with a release between never satisfies");
  h.noteOff(64);

  // Out-of-order arrival: E struck first, C joining second, still passes.
  h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);
  h.noteOn(64);  // E4 first (both halves are lit as the current step)
  assert(h.keyStatus.get(64) === "ok", "dyad: either half is green");
  assert(h.window.HarmonyTrainer.state().arpIndex === 0,
         "dyad: half a dyad does not advance");
  h.noteOn(60);  // C4 joins — both down
  assert(h.window.HarmonyTrainer.state().arpIndex === 1,
         "dyad: C+E concurrently held satisfies the step in any order");

  // Finger legato: keep C+E held while striking D, then F.
  h.noteOn(62);
  assert(h.window.HarmonyTrainer.state().arpIndex === 1,
         "dyad: half of the next dyad does not advance");
  h.noteOn(65);
  assert(h.window.HarmonyTrainer.state().finished === true,
         "dyad: D+F over the held first dyad finishes the walk");
  console.log("Test F (dyad steps): PASS");
})();

// === Test G: the re-attack rule makes repeated dyads gradable ================
// Holding the sixth C+E through the second identical step must NOT satisfy
// it for free — at least one constituent must be struck anew.  A wrong note
// while holding gives no free ride either.
(function testRepeatedDyadReattack() {
  const payload = {
    title: "same sixth twice", render: "arpeggio", concept: "technique",
    TARGET_CHORDS: [labTarget({
      absMeasure: 0, render: "arpeggio", concept: "melody",
      pitchClasses: [0, 4, 0, 4], midiPitches: [60, 64, 60, 64],
      steps: [{ pcs: [0, 4], minDistinct: 2 },
              { pcs: [0, 4], minDistinct: 2 }],
    })],
  };
  const h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);
  h.noteOn(60); h.noteOn(64);
  assert(h.window.HarmonyTrainer.state().arpIndex === 1,
         "re-attack: the first sixth satisfies step 1");
  // Still holding both: a stray G must not hand step 2 to the held chord.
  h.noteOn(67);
  assert(h.window.HarmonyTrainer.state().arpIndex === 1,
         "re-attack: holding through the barline of the step is not playing it");
  h.noteOff(67);
  // Re-striking ONE constituent (E) while C stays down completes step 2.
  h.noteOff(64); h.noteOn(64);
  assert(h.window.HarmonyTrainer.state().finished === true,
         "re-attack: one freshly struck constituent over a held C suffices");
  console.log("Test G (repeated dyad re-attack): PASS");
})();

// === Test H: octave doubling needs two DISTINCT keys on one pitch class =====
(function testOctaveDoubling() {
  const payload = {
    title: "octaves", render: "arpeggio", concept: "technique",
    TARGET_CHORDS: [labTarget({
      absMeasure: 0, render: "arpeggio", concept: "melody",
      pitchClasses: [0], midiPitches: [60, 72],
      steps: [{ pcs: [0], minDistinct: 2 }],
    })],
  };
  const h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);
  h.noteOn(60);
  assert(h.window.HarmonyTrainer.state().arpIndex === 0,
         "octaves: one C key is not a doubling");
  h.noteOn(60);  // the same key again is still one key
  assert(h.window.HarmonyTrainer.state().arpIndex === 0,
         "octaves: the same key twice is still one key");
  h.noteOn(64);  // a wrong pitch class does not count toward the doubling
  assert(h.keyStatus.get(64) === "bad", "octaves: E is red");
  assert(h.window.HarmonyTrainer.state().arpIndex === 0,
         "octaves: a second key on the WRONG pc does not count");
  h.noteOff(64);
  h.noteOn(72);  // C5 joins C4: two distinct keys, one pitch class
  assert(h.window.HarmonyTrainer.state().finished === true,
         "octaves: C4+C5 held together completes the step");
  console.log("Test H (octave doubling): PASS");
})();

// === Test I: hold enforcement gates the scalar ordered walk (ticket 04 v2) ===
// target.hold = {pc} — a moving note counts only while some active key maps
// mod-12 to the hold pc.  Dropping the hold never resets progress; the walk
// simply refuses until the hold is re-pressed (hold-release-repress cycle).
(function testHoldGateScalarWalk() {
  const payload = {
    title: "rotation", render: "arpeggio", concept: "technique",
    TARGET_CHORDS: [labTarget({
      absMeasure: 0, render: "arpeggio", concept: "melody",
      pitchClasses: [4, 7, 9], midiPitches: [48, 64, 67, 69],
      hold: { pc: 0 },                       // hold C (engraved C3)
    })],
  };
  const h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);
  // Without the hold down, the correct moving note is refused.
  h.noteOn(64);
  assert(h.window.HarmonyTrainer.state().arpIndex === 0,
         "hold: E without the C held is refused");
  h.noteOff(64);
  // Press the hold, then the walk proceeds.
  h.noteOn(48);
  h.noteOn(64);
  assert(h.window.HarmonyTrainer.state().arpIndex === 1,
         "hold: E over the held C advances");
  h.noteOff(64);
  // Drop the hold mid-phrase: progress is kept, the hint appears at once
  // (on the release itself, before any refused note), the next step refuses.
  h.noteOff(48);
  assert(/held/.test(h.nodes.get("htHoldMsg").textContent),
         "hold: releasing the hold shows the keep-held hint immediately");
  h.noteOn(67);
  assert(h.window.HarmonyTrainer.state().arpIndex === 1,
         "hold: dropping the hold does not reset progress");
  h.noteOff(67);
  // Re-press the hold and re-strike: the walk continues to the end.
  h.noteOn(48);
  assert(h.nodes.get("htHoldMsg").textContent === "",
         "hold: re-pressing the hold clears the hint");
  h.noteOn(67);
  assert(h.window.HarmonyTrainer.state().arpIndex === 2,
         "hold: re-pressed hold lets G through");
  h.noteOn(69);
  assert(h.window.HarmonyTrainer.state().finished === true,
         "hold: the moving line finishes over the re-pressed hold");
  console.log("Test I (hold gate, scalar walk): PASS");
})();

// === Test J: hold enforcement composes with dyad steps (tickets 03+04) ======
(function testHoldGateDyadSteps() {
  const payload = {
    title: "hold + dyads", render: "arpeggio", concept: "technique",
    TARGET_CHORDS: [labTarget({
      absMeasure: 0, render: "arpeggio", concept: "melody",
      pitchClasses: [4, 7, 5, 9], midiPitches: [48, 64, 65, 67, 69],
      steps: [{ pcs: [4, 7], minDistinct: 2 },
              { pcs: [5, 9], minDistinct: 2 }],
      hold: { pc: 0 },
    })],
  };
  const h = makeHarness(payload);
  h.window.HarmonyTrainer.init(payload);
  // A complete dyad without the hold is refused.
  h.noteOn(64); h.noteOn(67);
  assert(h.window.HarmonyTrainer.state().arpIndex === 0,
         "hold+dyad: E+G without the hold is refused");
  // Pressing the hold re-evaluates: the held fresh dyad now satisfies.
  h.noteOn(48);
  assert(h.window.HarmonyTrainer.state().arpIndex === 1,
         "hold+dyad: pressing the hold accepts the already-held fresh dyad");
  h.noteOff(64); h.noteOff(67);
  // The hold key itself is never a fresh constituent for the next step.
  h.noteOff(48); h.noteOn(48);
  assert(h.window.HarmonyTrainer.state().arpIndex === 1,
         "hold+dyad: re-pressing the hold alone satisfies nothing");
  h.noteOn(65); h.noteOn(69);
  assert(h.window.HarmonyTrainer.state().finished === true,
         "hold+dyad: the second dyad over the hold finishes the walk");
  console.log("Test J (hold gate, dyad steps): PASS");
})();

console.log("\nAll harmony_lab MIDI-acceptance checks passed (" + passed + " assertions).");
