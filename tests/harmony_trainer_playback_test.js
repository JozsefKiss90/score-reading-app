/*
 * Headless test for the target-playback visuals in
 * beat_selector/harmony_trainer.js (ticket 05 / plan U1).
 *
 * Stubs the browser globals + ScoreApp (same pattern as
 * harmony_trainer_node_test.js) with two additions: a controllable setTimeout
 * queue and tracked SVG nodes, so the test can advance "time" and observe the
 * pb-live class toggling.  Verifies:
 *   - playbackFlash lights exactly the noteheads of the sounded midis
 *     (octave-exact against PITCH_MAP, pc fallback otherwise);
 *   - overlapping flashes (held bass + per-beat tones) expire independently;
 *   - playbackClear un-lights everything and re-parks the cursor on the
 *     current grading target;
 *   - playback never touches grading state (midiDown / selNotesByMidi / idx).
 *
 * Run:  node tests/harmony_trainer_playback_test.js
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
function midiToName(m) { return NAMES[((m % 12) + 12) % 12] + (Math.floor(m / 12) - 1); }

function target(absMeasure, render, pcs, midis, bassMidi) {
  return {
    absMeasure, render, key: "C major", mode: "major",
    scale: ["C", "D", "E", "F", "G", "A", "B"],
    roman: "I", degree: "I", degreeNumber: 1, chordSymbol: "C", root: "C",
    quality: "major", chordTones: ["C", "E", "G"],
    pitchClasses: pcs, midiPitches: midis, bassMidi,
    intervalLayer: "M3+m3", functionLabel: "tonic", scaleDegreeName: "tonic",
    explanation: "...",
  };
}

// PITCH_MAP with distinct ids per notehead: treble tones + the bass note.
function makePitchMap(payload) {
  const pm = {};
  payload.TARGET_CHORDS.forEach((t) => {
    const rows = t.midiPitches.map((m, k) => (
      { id: "n" + t.absMeasure + "_t" + k, pitch: midiToName(m) }));
    if (t.bassMidi != null) {
      rows.push({ id: "n" + t.absMeasure + "_bass", pitch: midiToName(t.bassMidi) });
    }
    pm[String(t.absMeasure)] = { "1": rows };
  });
  return pm;
}

function makeNode() {
  const classes = new Set();
  return {
    id: "", className: "", textContent: "", _innerHTML: "",
    dataset: {}, style: {}, firstChild: null,
    classList: {
      add(c) { classes.add(c); },
      remove(c) { classes.delete(c); },
      toggle(c, on) { if (on) classes.add(c); else classes.delete(c); },
      contains(c) { return classes.has(c); },
    },
    set innerHTML(v) { this._innerHTML = v; }, get innerHTML() { return this._innerHTML; },
    appendChild() {}, insertBefore() {}, addEventListener() {},
    remove() {}, querySelector() { return null; }, querySelectorAll() { return []; },
    setAttribute() {},
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

  // SVG note nodes, resolvable through app._svgGetById.
  const svgNodes = new Map();
  function svgNode(id) {
    if (!svgNodes.has(id)) { const n = makeNode(); n.id = id; svgNodes.set(id, n); }
    return svgNodes.get(id);
  }

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
    refreshMidiHighlights() {},
    _svgGetById(id) { return svgNode(id); },
  };

  const window = { ScoreApp: app };
  window.onMidiNoteOn = () => {};
  window.onMidiNoteOff = () => {};

  // Controllable timer queue: advance(ms) fires due callbacks in order.
  let now = 0;
  const timers = [];
  const sandbox = {
    window, document, console,
    setTimeout: (fn, ms) => { timers.push({ at: now + (ms || 0), fn }); return timers.length; },
    clearTimeout: () => {},
  };
  function advance(ms) {
    now += ms;
    timers.sort((a, b) => a.at - b.at);
    while (timers.length && timers[0].at <= now) timers.shift().fn();
  }

  vm.createContext(sandbox);
  const code = fs.readFileSync(
    path.join(__dirname, "..", "beat_selector", "harmony_trainer.js"), "utf-8");
  vm.runInContext(code, sandbox, { filename: "harmony_trainer.js" });

  return { window, app, state, advance, svgNode, HT: () => window.HarmonyTrainer };
}

let passed = 0;
function assert(cond, msg) {
  if (!cond) { console.error("FAIL:", msg); process.exitCode = 1; throw new Error(msg); }
  passed += 1;
}

// === Test A: flash lights exactly the sounded noteheads =====================
(function testFlashExact() {
  const payload = {
    title: "C", render: "block",
    TARGET_CHORDS: [target(0, "block", [0, 4, 7], [60, 64, 67], 48)],
  };
  const h = makeHarness(payload);
  h.HT().init(payload);

  const n = h.HT().playbackFlash(0, [60, 64, 67, 48], 3000);
  assert(n === 4, "four noteheads flashed, got " + n);
  assert(h.svgNode("n0_t0").classList.contains("pb-live"), "treble root lit");
  assert(h.svgNode("n0_bass").classList.contains("pb-live"), "bass lit");

  // Octave-exactness: C3 (48) must NOT light the treble C4 head alone.
  const h2 = makeHarness(payload);
  h2.HT().init(payload);
  h2.HT().playbackFlash(0, [48], 3000);
  assert(h2.svgNode("n0_bass").classList.contains("pb-live"), "bass lit for 48");
  assert(!h2.svgNode("n0_t0").classList.contains("pb-live"),
         "treble C4 stays dark when only C3 sounds");

  // pc fallback: a midi with no notated octave match lights the pc's heads.
  const h3 = makeHarness(payload);
  h3.HT().init(payload);
  h3.HT().playbackFlash(0, [72], 3000);   // C5: no exact head, pc==0 matches
  assert(h3.svgNode("n0_t0").classList.contains("pb-live"), "pc fallback lights C heads");

  console.log("Test A (flash exact): PASS");
})();

// === Test B: overlapping flashes expire independently =======================
(function testOverlap() {
  const payload = {
    title: "C arp", render: "arpeggio",
    TARGET_CHORDS: [target(0, "arpeggio", [0, 4, 7], [60, 64, 67], 48)],
  };
  const h = makeHarness(payload);
  h.HT().init(payload);

  h.HT().playbackFlash(0, [48], 3000);    // held bass, whole measure
  h.HT().playbackFlash(0, [60], 750);     // beat-1 tone
  assert(h.svgNode("n0_bass").classList.contains("pb-live"), "bass lit");
  assert(h.svgNode("n0_t0").classList.contains("pb-live"), "tone lit");

  h.advance(800);                          // past the tone, before the bass
  assert(!h.svgNode("n0_t0").classList.contains("pb-live"), "tone expired");
  assert(h.svgNode("n0_bass").classList.contains("pb-live"), "bass still lit");

  h.advance(2500);                         // past the bass
  assert(!h.svgNode("n0_bass").classList.contains("pb-live"), "bass expired");
  assert(h.HT().playbackActiveIds().length === 0, "no ids left");

  // Re-flash keeps the id lit through the older timer's expiry.
  h.HT().playbackFlash(0, [60], 1000);
  h.HT().playbackFlash(0, [60], 5000);
  h.advance(1200);                         // older timer fires, newer stamp wins
  assert(h.svgNode("n0_t0").classList.contains("pb-live"), "re-flash survives old timer");

  console.log("Test B (overlap): PASS");
})();

// === Test C: playbackClear + grading state untouched ========================
(function testClearAndIsolation() {
  const payload = {
    title: "C", render: "block",
    TARGET_CHORDS: [
      target(0, "block", [0, 4, 7], [60, 64, 67], 48),
      target(1, "block", [2, 5, 9], [62, 65, 69], 50),
    ],
  };
  const h = makeHarness(payload);
  h.HT().init(payload);
  h.HT().goTo(1);                          // learner is on chord 1
  assert(h.app.lastMeasure === 1, "cursor parked on grading target");

  const selBefore = h.state.selNotesByMidi;
  const idxBefore = h.HT().state().idx;

  h.HT().playbackFlash(0, [60, 64, 67, 48], 3000);   // playback on measure 0
  assert(h.HT().state().idx === idxBefore, "flash does not move grading idx");
  assert(h.state.selNotesByMidi === selBefore, "flash does not rebuild selection");
  assert(h.state.midiDown.size === 0, "flash does not press keys");

  h.HT().playbackClear();
  assert(h.HT().playbackActiveIds().length === 0, "clear empties bookkeeping");
  assert(!h.svgNode("n0_t0").classList.contains("pb-live"), "clear un-lights");
  assert(h.app.lastMeasure === 1, "clear re-parks cursor on grading target");

  console.log("Test C (clear + isolation): PASS");
})();

console.log("ALL PLAYBACK TESTS PASS (" + passed + " assertions)");
