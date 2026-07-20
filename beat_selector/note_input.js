/*
 * NoteInput -- shared dispatcher for non-hardware note input (plan U2).
 *
 * The on-screen piano (keyboard_view.js pointer presses) and the QWERTY
 * fallback both land here.  Every synthetic note is routed through
 * window.onMidiNoteOn / window.onMidiNoteOff -- the SAME entry points the
 * Python host calls for hardware MIDI -- so highlighting and the
 * HarmonyTrainer grader treat all three input paths identically.  The
 * handlers are resolved at call time (never captured), because the trainer
 * wraps them after this file loads.
 *
 * Sound: the page has no synth, so each event is also queued; the Python
 * host polls takeEvents() and forwards them to fluidsynth (view.py).  The
 * queue is bounded so an unpolled page (tests, plain viewer) cannot grow it
 * unboundedly.
 *
 * This is a plain classic script (NOT an ES module): it attaches the single
 * global window.NoteInput and is loadable via Node's vm for tests
 * (tests/note_input_test.js), mirroring harmony_trainer.js.
 */
(function () {
  "use strict";

  if (typeof window === "undefined" || window.NoteInput) return;

  var DEFAULT_VELOCITY = 96;
  var MAX_QUEUE = 256;

  var down = new Set();       // midi numbers currently sounding (any source)
  var queue = [];             // events awaiting the Python sound poll
  var downByCode = {};        // QWERTY: e.code -> midi started (see below)

  function nowTs() {
    return (typeof Date !== "undefined" && Date.now) ? Date.now() / 1000 : 0;
  }

  function push(ev) {
    queue.push(ev);
    if (queue.length > MAX_QUEUE) queue.splice(0, queue.length - MAX_QUEUE);
  }

  // Returns true when the note actually started (false: out of range / held).
  function noteOn(midi, velocity) {
    midi = Math.trunc(Number(midi));
    if (!(midi >= 0 && midi <= 127) || down.has(midi)) return false;
    var vel = Math.max(1, Math.min(Math.trunc(Number(velocity) || DEFAULT_VELOCITY), 127));
    down.add(midi);
    push({ type: "on", midi: midi, vel: vel });
    if (window.onMidiNoteOn) window.onMidiNoteOn(midi, vel, nowTs());
    return true;
  }

  function noteOff(midi) {
    midi = Math.trunc(Number(midi));
    if (!down.has(midi)) return false;
    down.delete(midi);
    push({ type: "off", midi: midi });
    if (window.onMidiNoteOff) window.onMidiNoteOff(midi, nowTs());
    return true;
  }

  function releaseAll() {
    Array.from(down).forEach(function (m) { noteOff(m); });
    downByCode = {};
  }

  function takeEvents() {
    return queue.splice(0, queue.length);
  }

  // ---- QWERTY fallback ---------------------------------------------------
  // Layout-independent physical-position mapping (e.code), the common DAW
  // shape: A-row = white keys from C, W-row = the black keys between them.
  var KEY_OFFSETS = {
    KeyA: 0, KeyW: 1, KeyS: 2, KeyE: 3, KeyD: 4, KeyF: 5, KeyT: 6,
    KeyG: 7, KeyY: 8, KeyH: 9, KeyU: 10, KeyJ: 11, KeyK: 12, KeyO: 13,
    KeyL: 14, KeyP: 15, Semicolon: 16, Quote: 17,
  };
  var OCTAVE_DOWN = "KeyZ";
  var OCTAVE_UP = "KeyX";
  var BASE_MIN = 12;   // C0
  var BASE_MAX = 96;   // C7

  var base = 60;              // C4: the midi note KeyA plays

  function isEditableTarget(t) {
    if (!t) return false;
    var tag = String(t.tagName || "").toUpperCase();
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" ||
           !!t.isContentEditable;
  }

  function handleKeyDown(e) {
    if (!e || e.repeat || e.ctrlKey || e.altKey || e.metaKey) return;
    if (isEditableTarget(e.target)) return;
    var code = e.code;
    if (code === OCTAVE_DOWN || code === OCTAVE_UP) {
      base += (code === OCTAVE_UP) ? 12 : -12;
      base = Math.max(BASE_MIN, Math.min(base, BASE_MAX));
      if (e.preventDefault) e.preventDefault();
      return;
    }
    var off = KEY_OFFSETS[code];
    if (off === undefined || downByCode[code] !== undefined) return;
    var midi = base + off;
    if (noteOn(midi)) downByCode[code] = midi;
    if (e.preventDefault) e.preventDefault();
  }

  function handleKeyUp(e) {
    if (!e) return;
    var midi = downByCode[e.code];
    if (midi === undefined) return;
    delete downByCode[e.code];
    noteOff(midi);
  }

  if (window.addEventListener) {
    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);
    window.addEventListener("blur", releaseAll);   // no stuck notes on focus loss
  }

  window.NoteInput = {
    noteOn: noteOn,
    noteOff: noteOff,
    releaseAll: releaseAll,
    takeEvents: takeEvents,
    handleKeyDown: handleKeyDown,
    handleKeyUp: handleKeyUp,
  };
})();
