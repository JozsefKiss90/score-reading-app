/*
 * Executable acceptance test for the echo-play presentation in
 * beat_selector/harmony_trainer.js (plan A1 level 1, ticket 07).
 *
 * Contract under test:
 *   - PRESENTATION "echo": the notation is veiled during the listen phase —
 *     an "ht-veil" class (plus a hiding style) goes on the SVG root, the
 *     guide panel redacts every chord-identifying field, and the chord-card
 *     list is not rendered.  currentTarget() (the external-sync feed) is
 *     redacted the same way.
 *   - Grading is EXACTLY the visual drill's: the same MIDI note events
 *     complete and advance targets (pitch-class validator untouched).
 *   - Finishing the drill lifts the veil (sound-before-symbol: the notation
 *     is revealed for review); navigating again re-veils for the next pass.
 *   - Payloads without PRESENTATION (or "visual") change nothing.
 *
 * Run:  node tests/harmony_trainer_echo_test.js
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
function midiToName(m) { return NAMES[((m % 12) + 12) % 12] + (Math.floor(m / 12) - 1); }

function makeClassList(owner) {
  const set = new Set();
  return {
    add(...cs) { cs.forEach((c) => set.add(c)); },
    remove(...cs) { cs.forEach((c) => set.delete(c)); },
    toggle(c, force) {
      const on = force === undefined ? !set.has(c) : !!force;
      if (on) set.add(c); else set.delete(c);
      return on;
    },
    contains(c) { return set.has(c); },
    _set: set,
  };
}

function makeNode(tag) {
  const n = {
    tagName: tag || "div",
    id: "", textContent: "", _innerHTML: "",
    dataset: {}, style: {}, firstChild: null, disabled: false,
    children: [],
    set innerHTML(v) { this._innerHTML = v; if (!v) this.children = []; },
    get innerHTML() { return this._innerHTML; },
    appendChild(c) { this.children.push(c); return c; },
    insertBefore(c) { this.children.unshift(c); return c; },
    addEventListener() {}, remove() {},
    querySelector() { return null; }, querySelectorAll() { return []; },
    setAttribute(k, v) { if (k === "id") this.id = v; },
  };
  n.classList = makeClassList(n);
  return n;
}

function makePitchMap(payload) {
  const pm = {};
  payload.TARGET_CHORDS.forEach((t) => {
    pm[String(t.absMeasure)] = {
      "1": t.midiPitches.map((m, k) => ({ id: "n" + t.absMeasure + "_" + k, pitch: midiToName(m) })),
    };
  });
  return pm;
}

function makeHarness(payload) {
  const nodes = new Map();
  const svgRoot = makeNode("svg");
  svgRoot.ownerDocument = {
    createElementNS(ns, tag) { return makeNode(tag); },
    getElementById(id) {
      return svgRoot.children.find((c) => c.id === id) || null;
    },
  };
  const document = {
    getElementById(id) { if (!nodes.has(id)) { const n = makeNode(); n.id = id; nodes.set(id, n); } return nodes.get(id); },
    createElement(tag) { return makeNode(tag); },
    createElementNS(ns, tag) { return makeNode(tag); },
    querySelector() { return null; }, head: makeNode(), body: makeNode("body"),
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
    _svgRoot() { return svgRoot; },
    _svgGetById() { return null; },
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
  return { window, app, state, nodes, svgRoot, document,
           HT: window.HarmonyTrainer,
           noteOn: (p, v) => window.onMidiNoteOn(p, v === undefined ? 100 : v, 0),
           noteOff: (p) => window.onMidiNoteOff(p, 0) };
}

// Two C-major targets with distinctive giveaway strings, in the payload shape
// build_trainer_payload emits for presentation="echo" specs.
function echoTarget(i, roman, pcs, midis) {
  return {
    absMeasure: i, measureNumber: i + 1, group: "C major", render: "block",
    key: "C major", mode: "major",
    scale: ["C", "D", "E", "F", "G", "A", "B"], degree: roman, degreeNumber: 1,
    roman: roman, chordSymbol: "SYM_SECRET_" + i, root: "C", quality: "major",
    chordTones: ["TONE_SECRET_" + i], pitchClasses: pcs, midiPitches: midis,
    intervalLayer: "M3+m3", functionLabel: "tonic", scaleDegreeName: "tonic",
    explanation: "EXPLAIN_SECRET_" + i,
  };
}
function echoPayload(extra) {
  return Object.assign({
    // A deliberately leaky title: cadence/progression titles spell the
    // Roman sequence, so the veiled header must not print it.
    title: "Echo: V–I cadence", render: "block",
    ANSWER_MODE: "midi", PRESENTATION: "echo",
    TARGET_CHORDS: [
      echoTarget(0, "I", [0, 4, 7], [60, 64, 67]),
      echoTarget(1, "IV", [5, 9, 0], [65, 69, 72]),
    ],
  }, extra || {});
}

let passed = 0;
function assert(cond, msg) {
  if (!cond) { console.error("FAIL:", msg); process.exitCode = 1; throw new Error(msg); }
  passed += 1;
}

// === Test A: echo payloads veil the notation ================================
(function testEchoVeilsNotation() {
  const h = makeHarness(echoPayload());
  h.HT.init(echoPayload());
  assert(h.HT.state().presentation === "echo", "payload PRESENTATION reaches state()");
  assert(h.HT.state().veiled === true, "the listen phase starts veiled");
  assert(h.svgRoot.classList.contains("ht-veil"), "SVG root carries the veil class");
  assert(h.document.body.classList.contains("ht-echo"), "body carries the echo flag");
  const style = h.svgRoot.children.find((c) => c.id === "ht-veil-style");
  assert(!!style, "a veil style is injected into the SVG");
  assert(/visibility:\s*hidden/.test(style.textContent), "the veil hides via visibility");
  ["g.note", "g.harm", "g.ledgerLines"].forEach((sel) => {
    assert(style.textContent.indexOf(sel) !== -1, "veil covers " + sel);
  });
  console.log("Test A (echo veils the notation): PASS");
})();

// === Test B: the guide panel redacts every chord-identifying field ==========
(function testPanelRedaction() {
  const h = makeHarness(echoPayload());
  h.HT.init(echoPayload());
  const cur = h.nodes.get("htCurrent")._innerHTML;
  assert(cur.indexOf("C major") !== -1, "the key context stays visible");
  ["SYM_SECRET_0", "TONE_SECRET_0", "EXPLAIN_SECRET_0"].forEach((secret) => {
    assert(cur.indexOf(secret) === -1, "panel must not leak " + secret);
  });
  assert(h.nodes.get("htList").children.length === 0,
         "the chord-card list (roman + symbol per card) is not rendered");
  const title = h.nodes.get("htTitle").textContent;
  assert(title.indexOf("V–I") === -1,
         "the header must not spell the progression while veiled");
  assert(title.indexOf("Echo drill") !== -1, "the header stays a neutral prompt");
  console.log("Test B (panel redaction): PASS");
})();

// === Test C: grading is exactly the visual drill's ==========================
(function testGradingParity() {
  const h = makeHarness(echoPayload());
  h.HT.init(echoPayload());
  h.noteOn(61);                                  // wrong note: monitored only
  assert(h.HT.state().completed === false, "a wrong note does not complete");
  h.noteOff(61);
  h.noteOn(60); h.noteOn(64); h.noteOn(67);      // the full I triad
  assert(h.HT.state().completed === true, "the pitch-class validator completes");
  h.noteOff(60); h.noteOff(64); h.noteOff(67);
  assert(h.HT.state().idx === 1, "advance-on-release works exactly as visual");
  console.log("Test C (grading parity): PASS");
})();

// === Test D: currentTarget() is redacted while veiled =======================
(function testCurrentTargetRedaction() {
  const h = makeHarness(echoPayload());
  h.HT.init(echoPayload());
  const t = h.HT.currentTarget();
  assert(t && t.echoVeiled === true, "redacted target is flagged echoVeiled");
  assert(t.key === "C major" && t.measureNumber === 1,
         "key + position survive (Atlas key sync, cursor prose)");
  ["roman", "chordSymbol", "chordTones", "pitchClasses", "midiPitches",
   "functionLabel", "explanation"].forEach((f) => {
    assert(!(f in t), "redacted target must not carry " + f);
  });
  console.log("Test D (currentTarget redaction): PASS");
})();

// === Test E: finishing lifts the veil (sound-before-symbol reveal) ==========
(function testRevealOnFinish() {
  const h = makeHarness(echoPayload());
  h.HT.init(echoPayload());
  [[60, 64, 67], [65, 69, 72]].forEach((chord) => {
    chord.forEach((m) => h.noteOn(m));
    chord.forEach((m) => h.noteOff(m));
  });
  assert(h.HT.state().finished === true, "both targets echoed finishes the drill");
  assert(h.HT.state().veiled === false, "finishing lifts the veil");
  assert(!h.svgRoot.classList.contains("ht-veil"), "SVG veil class removed");
  assert(!h.document.body.classList.contains("ht-echo"), "body flag removed");
  const t = h.HT.currentTarget();
  assert(t && t.roman === "IV" && !t.echoVeiled,
         "currentTarget() is the full chord after the reveal");
  assert(h.nodes.get("htList").children.length > 0,
         "the chord cards appear for post-drill review");
  assert(h.nodes.get("htCurrent")._innerHTML.indexOf("SYM_SECRET_1") !== -1,
         "the guide panel shows the full detail after the reveal");
  assert(h.nodes.get("htTitle").textContent.indexOf("V–I cadence") !== -1,
         "the full title returns with the reveal");
  console.log("Test E (reveal on finish): PASS");
})();

// === Test F: navigating after the reveal re-veils the next pass =============
(function testReveilOnNavigation() {
  const h = makeHarness(echoPayload());
  h.HT.init(echoPayload());
  [[60, 64, 67], [65, 69, 72]].forEach((chord) => {
    chord.forEach((m) => h.noteOn(m));
    chord.forEach((m) => h.noteOff(m));
  });
  assert(h.HT.state().veiled === false, "revealed after the first pass");
  h.HT.reset();
  assert(h.HT.state().veiled === true, "a fresh pass hides the notation again");
  assert(h.svgRoot.classList.contains("ht-veil"), "SVG veil back on");
  console.log("Test F (re-veil on navigation): PASS");
})();

// === Test G: visual payloads are untouched ==================================
(function testVisualUnchanged() {
  const p = echoPayload();
  delete p.PRESENTATION;
  const h = makeHarness(p);
  h.HT.init(p);
  assert(h.HT.state().presentation === "visual", "no PRESENTATION defaults visual");
  assert(h.HT.state().veiled === false, "visual drills are never veiled");
  assert(!h.svgRoot.classList.contains("ht-veil"), "no veil class on visual");
  const t = h.HT.currentTarget();
  assert(t && t.roman === "I" && t.chordSymbol === "SYM_SECRET_0",
         "currentTarget() stays the full chord");
  assert(h.nodes.get("htCurrent")._innerHTML.indexOf("SYM_SECRET_0") !== -1,
         "the guide panel keeps its full detail");
  console.log("Test G (visual flow unchanged): PASS");
})();

// === Test H: playback flashes stay display-only under the veil ==============
(function testPlaybackFlashUnderVeil() {
  const h = makeHarness(echoPayload());
  h.HT.init(echoPayload());
  const lit = h.HT.playbackFlash(0, [60, 64, 67], 0);
  assert(lit === 3, "transport flashes still resolve note ids while veiled");
  assert(h.HT.state().veiled === true, "flashing does not lift the veil");
  console.log("Test H (playback flash under veil): PASS");
})();

// === Test I: echo + mcq — the aural quality-ID drill (ticket 10) ============
(function testEchoMcqQualityId() {
  const p = echoPayload({ ANSWER_MODE: "mcq" });
  p.TARGET_CHORDS.forEach((t, i) => {
    t.mcq = { prompt: "Which seventh-chord quality do you hear?",
              options: ["Mm7", "mm7", "MM7", "ø7", "°7"],
              answer: i === 0 ? "Mm7" : "ø7" };
  });
  const h = makeHarness(p);
  h.HT.init(p);
  assert(h.HT.state().veiled === true, "echo+mcq starts veiled");
  assert(h.HT.state().answerMode === "mcq", "answer mode reaches state()");
  const cur = h.nodes.get("htCurrent")._innerHTML;
  ["SYM_SECRET_0", "TONE_SECRET_0", "EXPLAIN_SECRET_0"].forEach((secret) => {
    assert(cur.indexOf(secret) === -1, "veiled mcq panel must not leak " + secret);
  });
  assert(cur.indexOf("answer strip") !== -1,
         "the veiled prompt says to answer from the strip, not the keyboard");
  assert(h.nodes.get("htTitle").textContent.indexOf("identify") !== -1,
         "the veiled header says listen-then-identify");
  assert(h.nodes.get("htList").children.length === 0,
         "no chord-card list in mcq mode (it would hand out answers)");
  const strip = h.nodes.get("htAnswer");
  const opts = strip.children.find((c) => c.className === "opts");
  assert(opts && opts.children.length === 5, "five quality options render");
  const wrong = h.HT.answer("MM7");
  assert(wrong && wrong.correct === false, "a wrong quality is rejected");
  assert(h.HT.state().idx === 0, "wrong answers do not advance");
  const right = h.HT.answer("Mm7");
  assert(right && right.correct === true, "the right quality is accepted");
  assert(h.HT.state().idx === 1, "a correct answer advances");
  assert(h.HT.state().veiled === true, "still veiled mid-drill");
  h.HT.answer("ø7");
  assert(h.HT.state().finished === true, "answering every target finishes");
  assert(h.HT.state().veiled === false, "finishing lifts the veil (reveal)");
  console.log("Test I (echo + mcq quality ID): PASS");
})();

// === Test J: bass-line dictation (ticket 11 / plan A1 level 5) ==============
(function testBassLineDictation() {
  // The lab payload shape for dictation: full-chord midiPitches (playback
  // sounds the whole progression) but a single graded pitch class per
  // measure — the bass — plus DICTATION: "bass" for the prompt.
  const p = echoPayload({ DICTATION: "bass" });
  p.TARGET_CHORDS = [
    Object.assign(echoTarget(0, "ii6", [5], [62, 65, 69, 53]),
                  { strictBass: true, bassPitchClass: 5, bassNote: "F",
                    figuredBass: "6", bassMidi: 53 }),
    Object.assign(echoTarget(1, "V", [7], [67, 71, 74, 55]),
                  { strictBass: true, bassPitchClass: 7, bassNote: "G",
                    bassMidi: 55 }),
  ];
  const h = makeHarness(p);
  h.HT.init(p);
  assert(h.HT.state().veiled === true, "dictation starts veiled (echo)");
  assert(h.HT.state().dictation === "bass", "DICTATION reaches state()");
  const title = h.nodes.get("htTitle").textContent;
  assert(/dictation/i.test(title), "the veiled header names dictation");
  const cur = h.nodes.get("htCurrent")._innerHTML;
  assert(/bass line/i.test(cur), "the veiled prompt asks for the bass line");
  assert(cur.indexOf("play it back on the keyboard") === -1,
         "the generic echo-the-chord prompt is replaced");
  ["SYM_SECRET_0", "TONE_SECRET_0", "EXPLAIN_SECRET_0"].forEach((secret) => {
    assert(cur.indexOf(secret) === -1, "dictation panel must not leak " + secret);
  });
  // A note held BELOW the demanded bass is the answer's bass — and wrong.
  // (Ordinary drills keep stray notes advisory; dictation answers with the
  // lowest sounding note, so it must fail here.)
  h.noteOn(52);                                    // E3 — below any F
  h.noteOn(65);                                    // F4 — the target pc
  assert(h.HT.state().completed === false,
         "a stray note below the demanded bass must not pass dictation");
  h.noteOff(52); h.noteOff(65);
  assert(h.HT.state().idx === 0, "the failed attempt does not advance");
  // Grading: the bass note alone completes the measure (any octave).
  h.noteOn(65);                                    // F4
  assert(h.HT.state().completed === true, "the bass pitch class completes");
  h.noteOff(65);
  assert(h.HT.state().idx === 1, "release advances to the next measure");
  h.noteOn(43); h.noteOff(43);                     // G2 — a different octave
  assert(h.HT.state().finished === true, "the bass line finishes the drill");
  assert(h.HT.state().veiled === false, "the reveal shows the full chords");
  console.log("Test J (bass-line dictation): PASS");
})();

// === Test K: soprano dictation (ticket 16 / plan G3, the PAC-vs-IAC ear) ====
(function testSopranoDictation() {
  // Mirror of Test J on the other edge of the texture: full-chord playback,
  // but the graded pitch class per measure is the SOPRANO, and a stray note
  // held ABOVE the demanded soprano must fail (the top line IS the answer).
  const p = echoPayload({ DICTATION: "soprano" });
  p.TARGET_CHORDS = [
    echoTarget(0, "V", [11], [50, 55, 59, 43]),      // soprano B (B4 = 71)
    echoTarget(1, "I", [0], [52, 55, 60, 48]),       // soprano C (C5 = 72)
  ];
  const h = makeHarness(p);
  h.HT.init(p);
  assert(h.HT.state().veiled === true, "soprano dictation starts veiled");
  assert(h.HT.state().dictation === "soprano", "DICTATION reaches state()");
  assert(/soprano/i.test(h.nodes.get("htTitle").textContent),
         "the veiled header names soprano dictation");
  const cur = h.nodes.get("htCurrent")._innerHTML;
  assert(/top line/i.test(cur), "the veiled prompt asks for the top line");
  assert(cur.indexOf("play it back on the keyboard") === -1,
         "the generic echo-the-chord prompt is replaced");
  // A note held ABOVE the demanded soprano is the answer's top — and wrong.
  h.noteOn(74);                                    // D5 — above the soprano
  h.noteOn(71);                                    // B4 — the target pc
  assert(h.HT.state().completed === false,
         "a stray note above the demanded soprano must not pass");
  h.noteOff(74); h.noteOff(71);
  assert(h.HT.state().idx === 0, "the failed attempt does not advance");
  // The soprano alone completes the measure (any octave).
  h.noteOn(59);                                    // B3 — a different octave
  assert(h.HT.state().completed === true, "the soprano pitch class completes");
  h.noteOff(59);
  assert(h.HT.state().idx === 1, "release advances to the next measure");
  h.noteOn(60); h.noteOff(60);                     // C4
  assert(h.HT.state().finished === true, "the top line finishes the drill");
  assert(h.HT.state().veiled === false, "the reveal shows the full chords");
  console.log("Test K (soprano dictation): PASS");
})();

console.log("\nAll echo-presentation checks passed (" + passed + " assertions).");
