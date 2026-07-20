/*
 * Executable acceptance test for beat_selector/note_input.js (plan U2,
 * ticket 06): the shared dispatcher for non-hardware note input (on-screen
 * piano pointer presses + QWERTY typing).
 *
 * Contract under test:
 *   - noteOn/noteOff route through window.onMidiNoteOn/onMidiNoteOff *at call
 *     time* (so the HarmonyTrainer wrapper installed later still grades), and
 *     queue a copy for the Python host to poll for sound.
 *   - takeEvents() drains the queue (bounded).
 *   - QWERTY: layout-independent e.code mapping from C4, octave shift Z/X,
 *     guards for repeats, modifiers and editable targets; a held key releases
 *     the pitch it started, even across an octave shift.
 *
 * Run:  node tests/note_input_test.js
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

function makeHarness() {
  const routed = [];      // what reached window.onMidiNoteOn/off
  const listeners = {};   // window.addEventListener captures
  const window = {
    addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
  };
  window.onMidiNoteOn = (pitch, vel, ts) => routed.push({ type: "on", pitch, vel, ts });
  window.onMidiNoteOff = (pitch, ts) => routed.push({ type: "off", pitch, ts });
  const sandbox = { window, console, Date };
  vm.createContext(sandbox);
  vm.runInContext(
    fs.readFileSync(path.join(__dirname, "..", "beat_selector", "note_input.js"), "utf-8"),
    sandbox, { filename: "note_input.js" });
  return { window, routed, listeners, NI: window.NoteInput };
}

let passed = 0;
function assert(cond, msg) {
  if (!cond) { console.error("FAIL:", msg); process.exitCode = 1; throw new Error(msg); }
  passed += 1;
}

// === Test A: noteOn/noteOff route through the live window handlers ==========
(function testRouting() {
  const h = makeHarness();
  h.NI.noteOn(60);
  assert(h.routed.length === 1 && h.routed[0].type === "on" && h.routed[0].pitch === 60,
         "noteOn routes through window.onMidiNoteOn");
  assert(h.routed[0].vel > 0 && h.routed[0].vel <= 127, "default velocity is sane");
  h.NI.noteOff(60);
  assert(h.routed.length === 2 && h.routed[1].type === "off" && h.routed[1].pitch === 60,
         "noteOff routes through window.onMidiNoteOff");
  console.log("Test A (routing): PASS");
})();

// === Test B: the trainer's later wrapping still sees synthetic input ========
(function testLateWrapSeen() {
  const h = makeHarness();
  const wrapped = [];
  const base = h.window.onMidiNoteOn;
  h.window.onMidiNoteOn = function (p, v, t) { wrapped.push(p); base(p, v, t); };
  h.NI.noteOn(64);
  assert(wrapped.length === 1 && wrapped[0] === 64,
         "handlers are resolved at call time, not captured at load");
  console.log("Test B (late wrap): PASS");
})();

// === Test C: double-on / double-off guards ==================================
(function testGuards() {
  const h = makeHarness();
  h.NI.noteOn(60); h.NI.noteOn(60);
  assert(h.routed.length === 1, "second noteOn of a held pitch is ignored");
  h.NI.noteOff(60); h.NI.noteOff(60);
  assert(h.routed.length === 2, "noteOff of a released pitch is ignored");
  console.log("Test C (double on/off guards): PASS");
})();

// === Test D: queue for the Python sound poll ================================
(function testQueue() {
  const h = makeHarness();
  h.NI.noteOn(60, 80); h.NI.noteOff(60);
  const evs = h.NI.takeEvents();
  assert(evs.length === 2, "takeEvents returns queued events");
  assert(evs[0].type === "on" && evs[0].midi === 60 && evs[0].vel === 80,
         "on-event carries midi + velocity");
  assert(evs[1].type === "off" && evs[1].midi === 60, "off-event carries midi");
  assert(h.NI.takeEvents().length === 0, "takeEvents drains the queue");
  console.log("Test D (queue drain): PASS");
})();

// === Test E: queue is bounded ===============================================
(function testQueueBounded() {
  const h = makeHarness();
  for (let i = 0; i < 400; i++) { h.NI.noteOn(30 + (i % 60)); h.NI.noteOff(30 + (i % 60)); }
  assert(h.NI.takeEvents().length <= 256, "unpolled queue stays bounded");
  console.log("Test E (queue bounded): PASS");
})();

// === Test F: QWERTY mapping from C4 =========================================
(function testQwertyBasics() {
  const h = makeHarness();
  h.NI.handleKeyDown({ code: "KeyA" });
  assert(h.routed.length === 1 && h.routed[0].pitch === 60, "KeyA plays C4 (60)");
  h.NI.handleKeyDown({ code: "KeyW" });
  assert(h.routed[1].pitch === 61, "KeyW plays C#4 (61)");
  h.NI.handleKeyDown({ code: "KeyK" });
  assert(h.routed[2].pitch === 72, "KeyK plays C5 (72)");
  h.NI.handleKeyUp({ code: "KeyA" });
  assert(h.routed[3].type === "off" && h.routed[3].pitch === 60, "keyup releases C4");
  console.log("Test F (QWERTY basics): PASS");
})();

// === Test G: QWERTY guards (repeat, modifiers, editable target, unknown) ====
(function testQwertyGuards() {
  const h = makeHarness();
  h.NI.handleKeyDown({ code: "KeyA", repeat: true });
  assert(h.routed.length === 0, "auto-repeat keydown is ignored");
  h.NI.handleKeyDown({ code: "KeyA", ctrlKey: true });
  assert(h.routed.length === 0, "ctrl-chords are ignored (shortcuts stay usable)");
  h.NI.handleKeyDown({ code: "KeyA", target: { tagName: "INPUT" } });
  assert(h.routed.length === 0, "typing into an input field is ignored");
  h.NI.handleKeyDown({ code: "F5" });
  assert(h.routed.length === 0, "unmapped keys are ignored");
  // A held key already down is not re-triggered by a second (missed-repeat) keydown.
  h.NI.handleKeyDown({ code: "KeyA" });
  h.NI.handleKeyDown({ code: "KeyA" });
  assert(h.routed.length === 1, "second keydown of a held key is ignored");
  console.log("Test G (QWERTY guards): PASS");
})();

// === Test H: octave shift, held notes release their original pitch ==========
(function testOctaveShift() {
  const h = makeHarness();
  h.NI.handleKeyDown({ code: "KeyA" });            // C4 = 60
  h.NI.handleKeyDown({ code: "KeyZ" });            // octave down
  h.NI.handleKeyDown({ code: "KeyS" });            // D, now in octave 3 => 50
  assert(h.routed[1].pitch === 50, "after KeyZ the next note is an octave lower");
  h.NI.handleKeyUp({ code: "KeyA" });
  assert(h.routed[2].type === "off" && h.routed[2].pitch === 60,
         "a held key releases the pitch it started, not the shifted one");
  h.NI.handleKeyDown({ code: "KeyX" });            // octave back up
  h.NI.handleKeyDown({ code: "KeyD" });            // E4 = 64
  assert(h.routed[3].pitch === 64, "KeyX restores the octave");
  // Clamp: hammering KeyZ never pushes notes below MIDI range.
  for (let i = 0; i < 12; i++) h.NI.handleKeyDown({ code: "KeyZ" });
  h.NI.handleKeyDown({ code: "KeyF" });
  const last = h.routed[h.routed.length - 1];
  assert(last.type === "on" && last.pitch >= 0, "octave shift clamps inside MIDI range");
  console.log("Test H (octave shift): PASS");
})();

// === Test I: releaseAll frees every held note (blur failsafe) ===============
(function testReleaseAll() {
  const h = makeHarness();
  h.NI.noteOn(60); h.NI.handleKeyDown({ code: "KeyG" });   // G4 = 67
  h.NI.releaseAll();
  const offs = h.routed.filter((e) => e.type === "off").map((e) => e.pitch).sort();
  assert(offs.length === 2 && offs[0] === 60 && offs[1] === 67,
         "releaseAll releases pointer and QWERTY notes alike");
  assert(h.NI.takeEvents().filter((e) => e.type === "off").length === 2,
         "releaseAll events reach the sound queue too");
  console.log("Test I (releaseAll): PASS");
})();

// === Test J: listeners attach when the environment provides them ============
(function testListeners() {
  const h = makeHarness();
  assert((h.listeners.keydown || []).length === 1, "keydown listener attached");
  assert((h.listeners.keyup || []).length === 1, "keyup listener attached");
  assert((h.listeners.blur || []).length === 1, "blur failsafe attached");
  console.log("Test J (listeners attached): PASS");
})();

console.log("\nAll note-input checks passed (" + passed + " assertions).");
