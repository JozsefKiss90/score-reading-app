/*
 * Cross-language contract checker (plan U2, ticket 06): loads a REAL
 * Python-emitted trainer payload (path in argv[2]) into the REAL
 * beat_selector/harmony_trainer.js and completes the identification drill
 * mouse-only — one wrong answer then the right one per target.
 *
 * Driven by tests/test_answer_modes.py (CrossLanguageMcqContract), which
 * builds the payload with build_trainer_payload and asserts this script
 * prints CONTRACT OK.  Not a standalone test: run the Python side.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));

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
const nodes = new Map();
const document = {
  getElementById(id) { if (!nodes.has(id)) { const n = makeNode(); n.id = id; nodes.set(id, n); } return nodes.get(id); },
  createElement() { return makeNode(); },
  querySelector() { return null; }, head: makeNode(), body: makeNode(),
};
const state = {
  boot: { PITCH_MAP: {} },
  selNotesByMidi: new Map(), selNoteIds: new Set(), midiDown: new Set(),
  boxesByAbs: {}, readySvg: true,
};
payload.TARGET_CHORDS.forEach((t) => { state.boxesByAbs[t.absMeasure] = {}; });
const app = { state, jsSetCursorAbs() {}, refreshMidiHighlights() {} };
const window = { ScoreApp: app, onMidiNoteOn() {}, onMidiNoteOff() {} };
const sandbox = { window, document, console,
                  setTimeout: (fn) => { fn(); return 0; }, clearTimeout: () => {} };
vm.createContext(sandbox);
vm.runInContext(
  fs.readFileSync(path.join(__dirname, "..", "beat_selector", "harmony_trainer.js"), "utf-8"),
  sandbox, { filename: "harmony_trainer.js" });

const HT = window.HarmonyTrainer;
const r = HT.init(payload);
if (!r.ok) throw new Error("init failed: " + r.why);
if (HT.state().answerMode !== "mcq") throw new Error("payload did not select mcq mode");

payload.TARGET_CHORDS.forEach((t) => {
  const wrongOpt = t.mcq.options.find((o) => o !== t.mcq.answer);
  const w = HT.answer(wrongOpt);
  if (!w || w.correct !== false) throw new Error("wrong option graded correct at " + t.roman);
  const c = HT.answer(t.mcq.answer);
  if (!c || c.correct !== true) throw new Error("right option graded wrong at " + t.roman);
});
if (!HT.state().finished) throw new Error("drill not finished: " + JSON.stringify(HT.state()));
const expectAttempts = payload.TARGET_CHORDS.length * 2;
if (HT.answerState().log.length !== expectAttempts) {
  throw new Error("attempt log " + HT.answerState().log.length + " != " + expectAttempts);
}
console.log("CONTRACT OK: " + payload.TARGET_CHORDS.length +
            " targets completed mouse-only, " + expectAttempts + " attempts logged");
