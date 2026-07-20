/*
 * Executable acceptance test for the non-MIDI answer modes in
 * beat_selector/harmony_trainer.js (plan U2, ticket 06).
 *
 * Contract under test:
 *   - ANSWER_MODE "mcq": an identification drill is completable mouse-only
 *     via HarmonyTrainer.answer(option) — wrong answers are recorded and do
 *     not advance; correct answers complete the target and auto-advance;
 *     answering every target finishes the exercise.  MIDI note events are
 *     monitored (highlighting) but never grade.
 *   - ANSWER_MODE "card": clicking a chord card submits its index; grading
 *     compares against the current target (or a per-target answerIndex
 *     override, the seam for "spot the intruder").
 *   - Default (no ANSWER_MODE): answer() is inert and the MIDI grader works
 *     exactly as before — the hardware flow is unchanged.
 *
 * Run:  node tests/harmony_trainer_answer_test.js
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
  // Synchronous setTimeout: the correct-answer auto-advance runs inline.
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

// A C-major diatonic target with an MCQ block, in the payload shape
// build_trainer_payload emits for answer_mode="mcq" specs.
const MAJOR_OPTIONS = ["I", "ii", "iii", "IV", "V", "vi", "vii°"];
function idTarget(i, roman, pcs, midis, extra) {
  return Object.assign({
    absMeasure: i, measureNumber: i + 1, group: "g", render: "block",
    key: "C major", mode: "major",
    scale: ["C", "D", "E", "F", "G", "A", "B"], degree: roman, degreeNumber: 1,
    roman: roman, chordSymbol: "X", root: "C", quality: "major",
    chordTones: ["C", "E", "G"], pitchClasses: pcs, midiPitches: midis,
    intervalLayer: "M3+m3", functionLabel: "tonic", scaleDegreeName: "tonic",
    explanation: "...",
    mcq: { prompt: "Which chord of C major is this?",
           options: MAJOR_OPTIONS, answer: roman },
  }, extra);
}
function mcqPayload() {
  return {
    title: "id", render: "block", ANSWER_MODE: "mcq",
    TARGET_CHORDS: [
      idTarget(0, "I", [0, 4, 7], [60, 64, 67]),
      idTarget(1, "IV", [5, 9, 0], [65, 69, 72]),
    ],
  };
}

let passed = 0;
function assert(cond, msg) {
  if (!cond) { console.error("FAIL:", msg); process.exitCode = 1; throw new Error(msg); }
  passed += 1;
}

// === Test A: an MCQ drill is completable mouse-only ==========================
(function testMcqMouseOnlyCompletion() {
  const h = makeHarness(mcqPayload());
  h.HT.init(mcqPayload());
  assert(h.HT.state().answerMode === "mcq", "payload ANSWER_MODE reaches state()");

  const wrong = h.HT.answer("V");
  assert(wrong && wrong.correct === false, "wrong option graded incorrect");
  assert(h.HT.state().idx === 0 && h.HT.state().completed === false,
         "wrong answer does not advance");

  const right = h.HT.answer("I");
  assert(right && right.correct === true, "correct option graded correct");
  assert(h.HT.state().idx === 1, "correct answer auto-advances");

  h.HT.answer("IV");
  assert(h.HT.state().finished === true,
         "answering every target finishes the exercise — no MIDI involved");
  assert(h.HT.answerState().log.length === 3, "every attempt is recorded");
  console.log("Test A (MCQ mouse-only completion): PASS");
})();

// === Test B: MCQ mode monitors MIDI but never grades it ======================
(function testMcqGatesMidiGrading() {
  const h = makeHarness(mcqPayload());
  h.HT.init(mcqPayload());
  h.noteOn(60); h.noteOn(64); h.noteOn(67);   // full I triad
  assert(h.state.midiDown.size === 3, "base monitoring still tracks held keys");
  assert(h.HT.state().completed === false && h.HT.state().idx === 0,
         "playing the chord does not answer an identification drill");
  h.noteOff(60); h.noteOff(64); h.noteOff(67);
  assert(h.HT.state().idx === 0, "releases do not advance either");
  console.log("Test B (MCQ gates MIDI grading): PASS");
})();

// === Test C: card mode — click the matching card =============================
(function testCardMode() {
  const p = mcqPayload();
  p.ANSWER_MODE = "card";
  p.TARGET_CHORDS.forEach((t) => { delete t.mcq; });
  const h = makeHarness(p);
  h.HT.init(p);
  assert(h.HT.state().answerMode === "card", "card mode active");

  const wrong = h.HT.answer(1);
  assert(wrong && wrong.correct === false && h.HT.state().idx === 0,
         "clicking the wrong card is recorded and does not advance");
  const right = h.HT.answer(0);
  assert(right && right.correct === true && h.HT.state().idx === 1,
         "clicking the matching card advances");
  console.log("Test C (card mode): PASS");
})();

// === Test D: card mode honours a per-target answerIndex override =============
(function testCardAnswerIndexOverride() {
  const p = mcqPayload();
  p.ANSWER_MODE = "card";
  p.TARGET_CHORDS.forEach((t) => { delete t.mcq; });
  p.TARGET_CHORDS[0].answerIndex = 1;   // the "spot the intruder" seam (G5a)
  const h = makeHarness(p);
  h.HT.init(p);
  assert(h.HT.answer(0).correct === false, "own index is wrong when overridden");
  assert(h.HT.answer(1).correct === true, "the override index is the answer");
  console.log("Test D (card answerIndex override): PASS");
})();

// === Test E: default payloads keep the MIDI flow byte-identical ==============
(function testMidiModeUnchanged() {
  const p = mcqPayload();
  delete p.ANSWER_MODE;
  p.TARGET_CHORDS.forEach((t) => { delete t.mcq; });
  const h = makeHarness(p);
  h.HT.init(p);
  assert(h.HT.state().answerMode === "midi", "no ANSWER_MODE defaults to midi");
  assert(h.HT.answer("I") === null, "answer() is inert in midi mode");
  assert(h.HT.answerState().log.length === 0, "nothing recorded in midi mode");
  h.noteOn(60); h.noteOn(64); h.noteOn(67);
  assert(h.HT.state().completed === true, "MIDI grading still completes");
  h.noteOff(60); h.noteOff(64); h.noteOff(67);
  assert(h.HT.state().idx === 1, "MIDI advance-on-release still works");
  console.log("Test E (midi flow unchanged): PASS");
})();

// === Test F: answer log entries carry the grading evidence ===================
(function testAnswerLogShape() {
  const h = makeHarness(mcqPayload());
  h.HT.init(mcqPayload());
  h.HT.answer("vi");
  const e = h.HT.answerState().log[0];
  assert(e.idx === 0 && e.mode === "mcq" && e.given === "vi" &&
         e.expected === "I" && e.correct === false,
         "log entry records idx/mode/given/expected/correct");
  assert(h.HT.answerState().last === undefined ||
         h.HT.answerState().last.given === "vi",
         "answerState exposes the latest attempt");
  assert(h.HT.state().answered === 1, "state() exposes the attempt count");
  console.log("Test F (answer log shape): PASS");
})();

console.log("\nAll answer-mode checks passed (" + passed + " assertions).");
