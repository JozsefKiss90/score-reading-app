/*
 * Executable acceptance test for the "spot the intruder" answer mode and the
 * tritone-resolution highlighting in beat_selector/harmony_trainer.js
 * (ticket 17 / plan G5a).
 *
 * Contract under test:
 *   - ANSWER_MODE "spot": a single-question drill.  Clicking the chord that
 *     is not diatonic to the key (payload SPOT_INDEX) completes AND finishes
 *     the exercise in one step; wrong clicks are recorded and re-askable;
 *     the chromatic noteheads of the intruder measure light up on success.
 *     MIDI events monitor but never grade.
 *   - A midi target carrying `tritoneResolution` lights the resolution
 *     noteheads (toPcs) when the chord completes — the resolve stage's
 *     "tritone flagged green as it resolves".
 *
 * Run:  node tests/harmony_trainer_spot_test.js
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
    dataset: {}, style: {}, firstChild: null, disabled: false,
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
  const state = {
    boot: { PITCH_MAP: makePitchMap(payload) },
    selNotesByMidi: new Map(), selNoteIds: new Set(), midiDown: new Set(),
    boxesByAbs: {}, readySvg: true,
  };
  payload.TARGET_CHORDS.forEach((t) => { state.boxesByAbs[t.absMeasure] = {}; });
  const app = {
    state, lastMeasure: -1,
    jsSetCursorAbs(abs) { this.lastMeasure = abs; },
    refreshMidiHighlights() {},
  };
  const window = { ScoreApp: app };
  window.onMidiNoteOn = (pitch, vel) => {
    if (Number(vel) <= 0) { window.onMidiNoteOff(pitch); return; }
    state.midiDown.add(pitch);
  };
  window.onMidiNoteOff = (pitch) => { state.midiDown.delete(pitch); };
  const sandbox = { window, document, console,
                    setTimeout: (fn) => { fn(); return 0; }, clearTimeout: () => {} };
  vm.createContext(sandbox);
  vm.runInContext(
    fs.readFileSync(path.join(__dirname, "..", "beat_selector", "harmony_trainer.js"), "utf-8"),
    sandbox, { filename: "harmony_trainer.js" });
  return { window, app, state, nodes,
           HT: window.HarmonyTrainer,
           noteOn: (p, v) => window.onMidiNoteOn(p, v === undefined ? 100 : v, 0),
           noteOff: (p) => window.onMidiNoteOff(p, 0) };
}

function target(i, roman, symbol, tones, pcs, midis, extra) {
  return Object.assign({
    absMeasure: i, measureNumber: i + 1, group: "g", render: "block",
    key: "C major", mode: "major",
    scale: ["C", "D", "E", "F", "G", "A", "B"], degree: roman, degreeNumber: 1,
    roman: roman, chordSymbol: symbol, root: tones[0], quality: "major",
    chordTones: tones, pitchClasses: pcs, midiPitches: midis,
    intervalLayer: "M3+m3", functionLabel: "tonic", scaleDegreeName: "tonic",
    explanation: "explains " + roman,
  }, extra);
}

// The flagship spot payload: I–vi–V7/V–V–I in C major, intruder at index 2.
function spotPayload() {
  return {
    title: "Spot the intruder", render: "block",
    ANSWER_MODE: "spot", SPOT_INDEX: 2,
    TARGET_CHORDS: [
      target(0, "I", "C", ["C", "E", "G"], [0, 4, 7], [60, 64, 67]),
      target(1, "vi", "Am", ["A", "C", "E"], [9, 0, 4], [69, 72, 76]),
      target(2, "V7/V", "D7", ["D", "F#", "A", "C"], [2, 6, 9, 0],
             [62, 66, 69, 72],
             { intruder: true, romanHidden: true, chromaticPcs: [6],
               tritonePcs: [6, 0],
               explanation: "F# is the leading tone of G: D7 is V7/V." }),
      target(3, "V", "G", ["G", "B", "D"], [7, 11, 2], [67, 71, 74]),
      target(4, "I", "C", ["C", "E", "G"], [0, 4, 7], [60, 64, 67]),
    ],
  };
}

// The resolve payload: V7/V → V with tritone-resolution metadata.
function resolvePayload() {
  return {
    title: "Resolve the intruder", render: "block",
    TARGET_CHORDS: [
      target(0, "V7/V", "D7", ["D", "F#", "A", "C"], [2, 6, 9, 0],
             [62, 66, 69, 72],
             { intruder: true, chromaticPcs: [6], tritonePcs: [6, 0] }),
      target(1, "V", "G", ["G", "B", "D"], [7, 11, 2], [67, 71, 74],
             { tritoneResolution: { fromPcs: [6, 0], fromMeasure: 0,
                                    toPcs: [7, 11], text: "F#→G, C→B" } }),
    ],
  };
}

let passed = 0;
function assert(cond, msg) {
  if (!cond) { console.error("FAIL:", msg); process.exitCode = 1; throw new Error(msg); }
  passed += 1;
}

// === Test A: spot is a single-question drill =================================
(function testSpotSingleQuestion() {
  const h = makeHarness(spotPayload());
  h.HT.init(spotPayload());
  assert(h.HT.state().answerMode === "spot", "payload ANSWER_MODE spot reaches state()");

  const wrong = h.HT.answer(0);
  assert(wrong && wrong.correct === false, "clicking a diatonic chord is wrong");
  assert(h.HT.state().finished === false, "wrong click does not finish");

  const right = h.HT.answer(2);
  assert(right && right.correct === true, "clicking the intruder is correct");
  assert(h.HT.state().finished === true,
         "one correct click finishes the whole exercise (single question)");
  const log = h.HT.answerState().log;
  assert(log.length === 2 && log[1].mode === "spot" && log[1].expected === 2,
         "spot attempts are logged with the intruder index as expected");
  assert(h.HT.answer(1) === null, "answering after the finish is inert");
  console.log("Test A (spot single question): PASS");
})();

// === Test B: the chromatic notehead lights on success ========================
(function testSpotPulse() {
  const h = makeHarness(spotPayload());
  h.HT.init(spotPayload());
  assert(h.HT.spotActiveIds().length === 0, "nothing lit before the answer");
  h.HT.answer(2);
  // F# (pc 6) is midi 66 = the second note of measure 2 -> id n2_1.
  assert(JSON.stringify(h.HT.spotActiveIds()) === JSON.stringify(["n2_1"]),
         "exactly the chromatic notehead of the intruder measure lights");
  console.log("Test B (chromatic notehead pulse): PASS");
})();

// === Test C: MIDI monitors but never grades a spot drill =====================
(function testSpotGatesMidi() {
  const h = makeHarness(spotPayload());
  h.HT.init(spotPayload());
  h.noteOn(60); h.noteOn(64); h.noteOn(67);   // full I triad
  assert(h.HT.state().completed === false && h.HT.state().finished === false,
         "playing a chord neither answers nor finishes a spot drill");
  h.noteOff(60); h.noteOff(64); h.noteOff(67);
  assert(h.HT.state().idx === 0, "releases do not advance");
  console.log("Test C (spot gates MIDI): PASS");
})();

// === Test D: tritone resolution lights on the resolve stage ==================
(function testTritoneResolution() {
  const h = makeHarness(resolvePayload());
  h.HT.init(resolvePayload());
  // Play the intruder (D7) and release: advance to the resolution target.
  [62, 66, 69, 72].forEach((m) => h.noteOn(m));
  assert(h.HT.state().completed === true, "the intruder chord grades as usual");
  assert(h.HT.tritoneActiveIds().length === 0,
         "no resolution highlight while the tritone still sounds");
  [62, 66, 69, 72].forEach((m) => h.noteOff(m));
  assert(h.HT.state().idx === 1, "release advances to the resolution");
  // Play the resolution (G major): the whole resolution lights green — the
  // origin tritone tones (F# = n0_1, C = n0_3 in the applied measure) AND
  // the landing tones (G = n1_0, B = n1_1).
  [67, 71, 74].forEach((m) => h.noteOn(m));
  assert(h.HT.state().completed === true, "the resolution chord completes");
  assert(JSON.stringify(h.HT.tritoneActiveIds().slice().sort()) ===
         JSON.stringify(["n0_1", "n0_3", "n1_0", "n1_1"]),
         "the origin tritone (fromPcs) and landing tones (toPcs) light");
  console.log("Test D (tritone resolution highlight): PASS");
})();

// === Test E: diatonic payloads are untouched =================================
(function testNoSpotFieldsNoChange() {
  const p = resolvePayload();
  delete p.TARGET_CHORDS[0].tritonePcs;
  delete p.TARGET_CHORDS[1].tritoneResolution;
  const h = makeHarness(p);
  h.HT.init(p);
  [62, 66, 69, 72].forEach((m) => h.noteOn(m));
  assert(h.HT.state().completed === true, "plain MIDI grading unchanged");
  assert(h.HT.tritoneActiveIds().length === 0,
         "no tritone highlight without the payload field");
  console.log("Test E (no spot fields, no change): PASS");
})();

console.log("\nAll spot/tritone checks passed (" + passed + " assertions).");
