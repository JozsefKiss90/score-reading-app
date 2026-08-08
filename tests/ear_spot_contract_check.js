/*
 * Cross-language contract checker (ticket 19 / plan G5c): loads a REAL
 * Python-emitted *ear stage* payload (path in argv[2]) into the REAL
 * beat_selector/harmony_trainer.js and completes it mouse-only and ear-only —
 * click the bar the chromatic chord sounded in, then name the degree it
 * tonicised — asserting the veil never lifts between the two answers.
 *
 * Driven by tests/test_applied_ramps.py (CrossLanguageEarStageContract), which
 * builds the payload with build_trainer_payload and asserts this script prints
 * CONTRACT OK.  Not a standalone test: run the Python side.
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

function must(cond, why) { if (!cond) throw new Error(why); }

const HT = window.HarmonyTrainer;
const r = HT.init(payload);
must(r.ok, "init failed: " + r.why);
must(HT.state().answerMode === "spot", "payload did not select spot mode");
must(HT.state().veiled === true, "the ear stage must start veiled");
must(HT.currentTarget().echoVeiled === true,
     "the veiled target must be redacted for external panes");

const spot = Math.trunc(Number(payload.SPOT_INDEX));
const followup = payload.SPOT_FOLLOWUP;
must(followup && followup.answer, "the ear payload carries no SPOT_FOLLOWUP");

// A wrong bar, then the right one.
const wrongBar = payload.TARGET_CHORDS.findIndex((_, i) => i !== spot);
must(HT.answer(wrongBar).correct === false, "a diatonic bar graded correct");
must(HT.state().veiled === true, "a wrong guess lifted the veil");

must(HT.answer(spot).correct === true, "the intruder's bar graded wrong");
must(HT.state().finished === false, "the position answer alone finished the drill");
must(HT.state().followupPending === true, "no follow-up question was raised");
must(HT.state().veiled === true, "the veil lifted before the follow-up was answered");

// A wrong degree, then the right one.
const wrongDeg = followup.options.find((o) => o !== followup.answer);
must(HT.answer(wrongDeg).correct === false, "a wrong degree graded correct");
must(HT.state().finished === false, "a wrong degree finished the drill");

must(HT.answer(followup.answer).correct === true, "the right degree graded wrong");
must(HT.state().finished === true, "both answers did not finish the drill");
must(HT.state().veiled === false, "finishing did not reveal the notation");
must(HT.answerState().log.length === 4, "attempt log " + HT.answerState().log.length + " != 4");

console.log("CONTRACT OK: ear stage completed by ear — bar " + (spot + 1) +
            " then " + followup.answer + ", 4 attempts logged");
