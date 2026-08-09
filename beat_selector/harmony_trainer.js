/*
 * Diatonic Harmony Trainer -- runtime controller + guide panel.
 *
 * This file is *injected* into the existing ScoreViewBeats page at runtime
 * (see run_harmony_trainer_demo.py).  It is a plain classic script (NOT an ES
 * module) so it can be evaluated via QWebEngine's runJavaScript and attach a
 * single global: window.HarmonyTrainer.
 *
 * It deliberately reuses the existing MIDI machinery instead of replacing it:
 *
 *   - It sets app.state.selNotesByMidi to the *current target chord's* tones
 *     (mapped octave-agnostically), so the existing app.refreshMidiHighlights()
 *     paints the keyboard green (pitch belongs to the target) / red (it does
 *     not) and greens the on-staff noteheads -- with zero changes to app.js.
 *   - It wraps window.onMidiNoteOn / onMidiNoteOff to drive target
 *     advancement (block: all tones; arpeggio: tones in order).
 *   - Non-MIDI answer modes (plan U2): payloads carrying ANSWER_MODE "mcq"
 *     render a multiple-choice strip (identification drills), "card" turns
 *     the chord-card list into the answer surface.  Both grade via
 *     submitAnswer(); MIDI events then only monitor, never grade.
 *
 * The shared viewer (app.js, sidebar.js, keyboard_view.js, beatpage.html) is
 * never modified, so existing behaviour cannot regress.
 */
(function () {
  "use strict";

  // ---- module state ------------------------------------------------------
  var app = null;
  var data = null;          // the trainer payload
  var idx = 0;              // current target index
  var satisfied = null;     // Set<pc> pressed correctly (block mode)
  var arpIndex = 0;         // next expected tone index (arpeggio mode)
  var completed = false;    // current target fully played?
  var finished = false;     // whole exercise done?
  var bassMiss = false;     // full set played but with the wrong lowest note
  var bassMissText = "";    // feedback naming the expected bass
  var holdMissText = "";    // "keep the X held" hint (ticket 04 v2)

  // ---- simultaneity steps (piano-technique ticket 03) --------------------
  // activeNotes mirrors the physically held keys as RAW midi numbers (add on
  // note-on, remove on note-off / velocity-0).  Navigation never clears it —
  // it is physical reality, and ticket 04's hold enforcement reuses it.
  // freshNotes is the grading half: the held keys struck since the previous
  // step completed (or since the attempt started).  Demanding one fresh
  // constituent per step is the re-attack rule — "play the same sixth four
  // times" stays gradable, while finger-legato overlap between DIFFERENT
  // consecutive steps still passes.
  var activeNotes = new Set();
  var freshNotes = new Set();

  // ---- answer modes (plan U2, ticket 06; "spot" ticket 17) ---------------
  // "midi" is the classic play-the-chord flow.  "mcq" renders an answer
  // strip for identification drills; "card" turns the chord-card list into
  // the answer surface; "spot" is the single-question intruder hunt (plan
  // G5a) — clicking the chord that is not diatonic to the key (payload
  // SPOT_INDEX) finishes the whole exercise.  In every non-midi mode MIDI
  // events keep their monitoring visuals but never grade.
  var ANSWER_ADVANCE_MS = 600;
  var answerMode = "midi";  // "midi" | "mcq" | "card" | "spot"
  var answerLog = [];       // {idx, mode, given, expected, correct}
  var lastAnswer = null;    // latest entry (feedback for the current target)
  var answeredCorrect = new Set();   // target indexes answered correctly
  var cardOrder = null;     // card mode: shuffled DISPLAY order (once per
                            // exercise) so the list doesn't mirror the
                            // question sequence — indexes/grading unchanged

  // ---- echo presentation (plan A1 level 1, ticket 07) --------------------
  // "echo" payloads (PRESENTATION) are aural twins: the target is *heard*
  // (host transport) and played back by ear, so while the drill is
  // unfinished the notation is veiled (SVG class + hiding style), the guide
  // panel redacts every chord-identifying field, and the chord-card list is
  // withheld.  Grading is untouched — the same pitch-class validator runs.
  // Finishing lifts the veil (sound-before-symbol: the notation is revealed
  // for review); navigating again re-veils the next pass.
  var presentation = "visual";  // "visual" | "echo"

  // ---- line dictation (plan A1 level 5, tickets 11 + 16) ------------------
  // DICTATION "bass" payloads are echo drills whose graded target per measure
  // is the single bass pitch class (the notation + playback keep the full
  // chords).  Grading needs nothing new — pitchClasses already carries the
  // bass alone — but the veiled prompt must ask for the bass line, not for
  // echoing a chord.  DICTATION "soprano" (ticket 16, the PAC-vs-IAC ear) is
  // the mirror image: the target is the top line, and a stray note held
  // ABOVE the demanded soprano must fail.
  var dictation = null;         // null | "bass" | "soprano"

  // ---- applied-chord highlights (ticket 17, plan G5a) --------------------
  // spotIds: the intruder's chromatic noteheads, lit (amber pulse) when the
  // learner spots it.  tritoneIds: the resolution noteheads (payload
  // tritoneResolution.toPcs), lit green when the resolve stage's resolution
  // chord completes.  Both are display-only and never touch grading state.
  var spotIds = [];             // note ids currently pulsing amber
  var tritoneIds = [];          // note ids currently lit green
  var resolveMsg = "";          // "✓ Tritone resolved: F#→G, C→B"

  // ---- the applied ear stage (ticket 19, plan G5c) -----------------------
  // A veiled spot payload (PRESENTATION "echo" + ANSWER_MODE "spot") asks the
  // hunt by ear: the answer surface is a strip of BAR POSITIONS (the card list
  // names chords and stays withheld), and payload SPOT_FOLLOWUP adds the
  // second question — which degree did that chord tonicise?  The drill is not
  // finished (and the veil does not lift) until both are answered, so the
  // notation can never reveal the follow-up's answer.
  var spotFound = false;        // the position question is answered
  var followupDone = false;     // the tonicisation question is answered

  // ---- pitch helpers -----------------------------------------------------
  var STEP_PC = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };

  function mod12(n) { return ((n % 12) + 12) % 12; }

  function pitchToMidi(pitch) {
    if (!pitch) return null;
    var t = String(pitch).trim().replace(/♯/g, "#").replace(/♭/g, "b");
    var m = /^([A-Ga-g])([#b]{0,2})(-?\d+)$/.exec(t);
    if (!m) return null;
    var base = STEP_PC[m[1].toUpperCase()];
    if (base === undefined) return null;
    var acc = m[2] || "";
    var delta = (acc.match(/#/g) || []).length - (acc.match(/b/g) || []).length;
    return (parseInt(m[3], 10) + 1) * 12 + base + delta;
  }

  // ---- target accessors --------------------------------------------------
  function targets() { return (data && data.TARGET_CHORDS) || []; }
  function cur() { return targets()[idx] || null; }
  function isArpeggio() {
    var t = cur();
    return !!(t && t.render === "arpeggio");
  }

  // Ordered simultaneity steps (ticket 03): an arpeggio-walk target may
  // demand more than one concurrent key per step — steps like
  // {pcs: [0, 4], minDistinct: 2} (a dyad) or {pcs: [0], minDistinct: 2}
  // (octave doubling).  Null for scalar targets (the classic walk).
  function stepsFor(t) {
    return (t && t.render === "arpeggio" && t.steps && t.steps.length)
      ? t.steps : null;
  }

  // Hold enforcement (ticket 04 v2): target.hold = {pc} names the pitch
  // class that must stay sounding (any octave) for the measure's ordered
  // steps to be accepted.  Null for every target without a graded hold, so
  // holdDown() is vacuously true and pre-04 drills grade unchanged.
  function holdPc(t) {
    return (t && t.hold && t.hold.pc !== null && t.hold.pc !== undefined)
      ? mod12(t.hold.pc) : null;
  }
  function holdDown(t) {
    var pc = holdPc(t);
    if (pc === null) return true;
    var ok = false;
    activeNotes.forEach(function (m) { if (mod12(m) === pc) ok = true; });
    return ok;
  }

  // Strict-bass grading (plan G4/F4): a block target with `strictBass: true`
  // demands `bassPitchClass` as the LOWEST sounding chord tone.  Returns the
  // demanded pitch class, or null when the target grades octave-agnostically.
  function strictBassPc(t) {
    return (t && t.strictBass && t.bassPitchClass !== null &&
            t.bassPitchClass !== undefined) ? mod12(t.bassPitchClass) : null;
  }

  var PC_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

  // Spell a pitch class with the target's own chord-tone spelling when it has
  // one (Eb stays Eb, not D#); fall back to the sharp names.
  function toneName(t, pc) {
    pc = mod12(pc);
    if (t && t.pitchClasses && t.chordTones) {
      var i = t.pitchClasses.map(mod12).indexOf(pc);
      if (i !== -1 && t.chordTones[i]) return t.chordTones[i];
    }
    return PC_NAMES[pc];
  }

  // The lowest *currently sounding* chord tone (stray non-chord notes are
  // already shown red and stay advisory).  Null when none is held.
  function lowestHeldChordTone(t) {
    var pcs = t.pitchClasses.map(mod12);
    var low = null;
    app.state.midiDown.forEach(function (m) {
      m = Math.trunc(Number(m));
      if (pcs.indexOf(mod12(m)) === -1) return;
      if (low === null || m < low) low = m;
    });
    return low;
  }

  // Dictation answers with the BASS LINE, so the lowest sounding note — chord
  // tone or not — IS the answer: a stray note held below the demanded bass
  // must fail, where ordinary drills would keep it advisory.
  function lowestHeldNote() {
    var low = null;
    app.state.midiDown.forEach(function (m) {
      m = Math.trunc(Number(m));
      if (low === null || m < low) low = m;
    });
    return low;
  }

  // Soprano dictation answers with the TOP LINE (ticket 16): the highest
  // sounding note IS the answer, so a stray note above the soprano must fail.
  function highestHeldNote() {
    var high = null;
    app.state.midiDown.forEach(function (m) {
      m = Math.trunc(Number(m));
      if (high === null || m > high) high = m;
    });
    return high;
  }

  function resetAttempt() {
    satisfied = new Set();
    arpIndex = 0;
    completed = false;
    bassMiss = false;
    bassMissText = "";
    holdMissText = "";
    // A fresh attempt demands fresh attacks; keys already held stay in
    // activeNotes (physical reality) but no longer count as struck.
    freshNotes = new Set();
  }

  // Map: keyOf(midi) -> Set(noteId) for a given measure, from boot.PITCH_MAP.
  function idsForMeasure(absMeasure, keyOf) {
    var out = new Map();
    var pm = app && app.state && app.state.boot && app.state.boot.PITCH_MAP;
    if (!pm) return out;
    var beats = pm[String(absMeasure)] || pm[absMeasure];
    if (!beats) return out;
    Object.keys(beats).forEach(function (b) {
      (beats[b] || []).forEach(function (r) {
        if (!r || !r.id || !r.pitch) return;
        var mm = pitchToMidi(r.pitch);
        if (mm === null) return;
        var k = keyOf(mm);
        if (!out.has(k)) out.set(k, new Set());
        out.get(k).add(String(r.id));
      });
    });
    return out;
  }

  // Octave-agnostic (grading) and octave-exact (playback flash) views.
  function idsByPcForMeasure(absMeasure) {
    return idsForMeasure(absMeasure, mod12);
  }
  function idsByMidiForMeasure(absMeasure) {
    return idsForMeasure(absMeasure, function (m) { return m; });
  }

  // Build selNotesByMidi for a set of expected pitch classes.  Every octave of
  // each expected pc maps to that pc's note ids in the current measure, plus a
  // sentinel id so the "ok" status survives even if the measure is off-page.
  function buildSelection(expectedPcs, absMeasure) {
    var S = app.state;
    var idsByPc = idsByPcForMeasure(absMeasure);
    var byMidi = new Map();
    var allIds = new Set();

    expectedPcs.forEach(function (pc) {
      pc = mod12(pc);
      var ids = new Set(idsByPc.get(pc) || []);
      ids.add("__ht_target_" + pc);
      ids.forEach(function (i) { allIds.add(i); });
      for (var m = pc; m <= 127; m += 12) byMidi.set(m, ids);
    });

    S.selNotesByMidi = byMidi;
    S.selNoteIds = allIds;
  }

  // --- Slot-aware selection for scalar ordered walks (piano-technique 06).
  // A measure whose walk repeats a pitch class (the arpeggio runs: three C's
  // per bar) must not light FUTURE same-pc noteheads when an earlier step is
  // played — pc-level selection would green them all at once and read as
  // premature progress.  PITCH_MAP rows carry enough order (numeric beat
  // buckets, then Verovio's own note times for sub-beat notes) to recover
  // the notation order, so each walked slot selects only its own notehead.
  // Grading is untouched (the walk stays octave-blind).
  function orderedRowsForMeasure(absMeasure) {
    var pm = app && app.state && app.state.boot && app.state.boot.PITCH_MAP;
    if (!pm) return null;
    var beats = pm[String(absMeasure)] || pm[absMeasure];
    if (!beats) return null;
    var rows = [];
    Object.keys(beats)
      .sort(function (a, b) { return Number(a) - Number(b); })
      .forEach(function (b) {
        (beats[b] || []).forEach(function (r) {
          if (!r || !r.id || !r.pitch) return;
          var mm = pitchToMidi(r.pitch);
          if (mm === null) return;
          rows.push({ id: String(r.id), midi: mm,
                      t: (typeof r.t_rel === "number") ? r.t_rel : null });
        });
      });
    // Two eighths share a quarter bucket; when every row is timed, the note
    // times restore their order (Array.prototype.sort is stable, so ties
    // keep the beat-bucket order).
    if (rows.length && rows.every(function (r) { return r.t !== null; })) {
      rows.sort(function (a, b) { return a.t - b.t; });
    }
    return rows;
  }

  // The measure's notehead ids in walk order, or null when the rows do not
  // mirror the walk (chord stacks, second voices, unpitched rows) — callers
  // then fall back to pc-level selection, the pre-existing behaviour.
  function walkSlotIds(t) {
    var rows = orderedRowsForMeasure(t.absMeasure);
    if (!rows || !rows.length) return null;
    // Trainer measures also notate a held bass note that is not part of the
    // walk; lab melody measures (marked by slotsPerMeasure) put every row on
    // the walked line, and their bassMidi IS the line's lowest note.
    if (!t.slotsPerMeasure && t.bassMidi !== null && t.bassMidi !== undefined) {
      var bass = Math.trunc(Number(t.bassMidi));
      for (var i = 0; i < rows.length; i++) {
        if (rows[i].midi === bass) { rows.splice(i, 1); break; }
      }
    }
    if (rows.length !== t.pitchClasses.length) return null;
    for (var k = 0; k < rows.length; k++) {
      if (mod12(rows[k].midi) !== mod12(t.pitchClasses[k])) return null;
    }
    return rows.map(function (r) { return r.id; });
  }

  // Selection for a slot-aligned scalar walk: slots 0..arpIndex (played plus
  // current) select their own noteheads; later same-pc slots stay unlit.
  // Returns false when the measure's rows cannot be slot-aligned.
  function buildWalkSelection(t) {
    var slots = walkSlotIds(t);
    if (!slots) return false;
    var idsByPc = new Map();
    var last = Math.min(arpIndex, t.pitchClasses.length - 1);
    for (var i = 0; i <= last; i++) {
      var pc = mod12(t.pitchClasses[i]);
      if (!idsByPc.has(pc)) {
        var seed = new Set();
        seed.add("__ht_target_" + pc);   // survives off-page measures
        idsByPc.set(pc, seed);
      }
      idsByPc.get(pc).add(slots[i]);
    }
    var byMidi = new Map();
    var allIds = new Set();
    idsByPc.forEach(function (ids, pc) {
      ids.forEach(function (id) { allIds.add(id); });
      for (var m = pc; m <= 127; m += 12) byMidi.set(m, ids);
    });
    app.state.selNotesByMidi = byMidi;
    app.state.selNoteIds = allIds;
    return true;
  }

  function expectedPcsForCurrent() {
    var t = cur();
    if (!t) return [];
    if (isArpeggio()) {
      var steps = stepsFor(t);
      if (steps) {
        // Completed steps stay green, the current step's pcs light up next.
        var out = [];
        var last = Math.min(arpIndex, steps.length - 1);
        for (var i = 0; i <= last; i++) {
          ((steps[i] && steps[i].pcs) || []).forEach(function (pc) {
            pc = mod12(pc);
            if (out.indexOf(pc) === -1) out.push(pc);
          });
        }
        return out;
      }
      return t.pitchClasses.slice(0, Math.min(arpIndex + 1, t.pitchClasses.length));
    }
    return t.pitchClasses.slice();
  }

  function applySelection() {
    var t = cur();
    if (!t) return;
    if (!(isArpeggio() && !stepsFor(t) && buildWalkSelection(t))) {
      buildSelection(expectedPcsForCurrent(), t.absMeasure);
    }
    if (app.refreshMidiHighlights) app.refreshMidiHighlights();
  }

  function coversAll(set, pcs) {
    for (var i = 0; i < pcs.length; i++) {
      if (!set.has(mod12(pcs[i]))) return false;
    }
    return true;
  }

  // ---- bar highlight on the score ---------------------------------------
  function placeHighlight(absMeasure, attempts) {
    attempts = attempts || 0;
    var S = app.state;
    if (!S.readySvg || !S.boxesByAbs || !S.boxesByAbs[absMeasure]) {
      if (attempts < 40) {
        setTimeout(function () { placeHighlight(absMeasure, attempts + 1); }, 60);
      }
      return;
    }
    try { app.jsSetCursorAbs(absMeasure, 0, 1); } catch (e) { /* ignore */ }
  }

  // Broadcast the current target so external views (e.g. the Circle of Fifths /
  // Harmony Atlas) can sync their highlight. Guarded so it is a safe no-op in
  // headless test contexts that stub window without CustomEvent.
  function emitTargetChange(detail) {
    try {
      if (typeof window !== "undefined" &&
          typeof window.dispatchEvent === "function" &&
          typeof CustomEvent === "function") {
        window.dispatchEvent(new CustomEvent("harmonytrainer:targetchange",
          { detail: detail === undefined ? publicTarget() : detail }));
      }
    } catch (e) { /* ignore */ }
  }

  // ---- target playback visuals (transport, plan U1) ----------------------
  // The Python transport (audio/target_playback.py) sequences the target
  // chords through the synth and mirrors each noteon here so the notated
  // noteheads flash while they sound.  This path is display-only: it never
  // touches midiDown / selNotesByMidi / grading state, so the learner's own
  // MIDI monitoring keeps working during and after playback.
  var pbStamp = new Map();   // note id -> stamp of the latest flash holding it
  var pbSeq = 0;

  function pbEnsureStyle() {
    try {
      var root = app && app._svgRoot ? app._svgRoot() : null;
      if (!root) return;
      var doc = root.ownerDocument;
      if (!doc || (doc.getElementById && doc.getElementById("ht-pb-style"))) return;
      var style = doc.createElementNS(
        "http://www.w3.org/2000/svg", "style");
      style.setAttribute("id", "ht-pb-style");
      style.textContent = [
        ".pb-live .notehead use,",
        ".pb-live .notehead path,",
        ".pb-live .notehead ellipse,",
        ".pb-live .notehead polygon,",
        ".pb-live .notehead rect {",
        "  fill: #d97706 !important;",
        "  stroke: #d97706 !important;",
        "}",
      ].join("\n");
      root.appendChild(style);
    } catch (e) { /* ignore */ }
  }

  function pbSetClass(id, on) {
    var node = app && app._svgGetById ? app._svgGetById(id) : null;
    if (!node) return;
    try { node.classList.toggle("pb-live", !!on); } catch (e) { /* ignore */ }
  }

  // Flash the noteheads for `midis` in `absMeasure` for `durMs` — octave-
  // exact (idsByMidiForMeasure), so only heads that sound light.  Overlapping
  // flashes (a held bass under per-beat tones) expire independently: each id
  // remembers its latest stamp and only that flash's timer un-lights it.
  function playbackFlash(absMeasure, midis, durMs) {
    if (!app) return 0;
    pbEnsureStyle();
    // Re-assert the echo veil: flashes fire throughout the auto-played
    // listen phase, so a late-rendered SVG gets veiled here even after
    // updateVeil's own retry window lapsed.  (attempts=100 -> no new
    // retry timers pile up from this call.)
    updateVeil(100);
    var byMidi = idsByMidiForMeasure(absMeasure);
    var byPc = idsByPcForMeasure(absMeasure);
    var ids = [];
    (midis || []).forEach(function (m) {
      m = Math.trunc(Number(m));
      var exact = byMidi.get(m);
      var set = (exact && exact.size) ? exact : byPc.get(mod12(m));
      if (set) set.forEach(function (id) { ids.push(id); });
    });
    var stamp = ++pbSeq;
    ids.forEach(function (id) {
      pbStamp.set(id, stamp);
      pbSetClass(id, true);
    });
    if (ids.length && durMs > 0) {
      setTimeout(function () {
        ids.forEach(function (id) {
          if (pbStamp.get(id) === stamp) {
            pbStamp.delete(id);
            pbSetClass(id, false);
          }
        });
      }, durMs);
    }
    return ids.length;
  }

  // Un-light everything and re-park the cursor on the learner's current
  // grading target (playback moved it).  Grading state is untouched.
  function playbackClear() {
    pbStamp.forEach(function (_stamp, id) { pbSetClass(id, false); });
    pbStamp = new Map();
    var t = cur();
    if (t) placeHighlight(t.absMeasure);
    return true;
  }

  // ---- applied-chord highlights (ticket 17, plan G5a) --------------------
  // Style injected into the SVG like the playback style: the intruder's
  // chromatic noteheads pulse amber, the tritone's landing tones go green.
  function appliedEnsureStyle() {
    try {
      var root = app && app._svgRoot ? app._svgRoot() : null;
      if (!root) return;
      var doc = root.ownerDocument;
      if (!doc || (doc.getElementById && doc.getElementById("ht-applied-style"))) return;
      var style = doc.createElementNS(
        "http://www.w3.org/2000/svg", "style");
      style.setAttribute("id", "ht-applied-style");
      style.textContent = [
        "@keyframes htIntruderPulse {",
        "  0%, 100% { opacity: 1; }",
        "  50% { opacity: 0.25; }",
        "}",
        ".ht-intruder { animation: htIntruderPulse 0.9s ease-in-out 4; }",
        ".ht-intruder .notehead use, .ht-intruder .notehead path,",
        ".ht-intruder .notehead ellipse, .ht-intruder .notehead polygon,",
        ".ht-intruder .notehead rect {",
        "  fill: #d97706 !important;",
        "  stroke: #d97706 !important;",
        "}",
        ".ht-tritone-ok .notehead use, .ht-tritone-ok .notehead path,",
        ".ht-tritone-ok .notehead ellipse, .ht-tritone-ok .notehead polygon,",
        ".ht-tritone-ok .notehead rect {",
        "  fill: #16a34a !important;",
        "  stroke: #16a34a !important;",
        "}",
      ].join("\n");
      root.appendChild(style);
    } catch (e) { /* ignore */ }
  }

  function svgSetClass(id, cls, on) {
    var node = app && app._svgGetById ? app._svgGetById(id) : null;
    if (!node) return;
    try { node.classList.toggle(cls, !!on); } catch (e) { /* ignore */ }
  }

  // Note ids of `pcs` in `absMeasure` (octave-agnostic, like grading).
  function idsForPcs(absMeasure, pcs) {
    var byPc = idsByPcForMeasure(absMeasure);
    var ids = [];
    (pcs || []).forEach(function (pc) {
      var set = byPc.get(mod12(pc));
      if (set) set.forEach(function (id) { ids.push(id); });
    });
    return ids;
  }

  // Light the intruder's chromatic noteheads (spot success feedback).
  function spotPulse() {
    var s = targets()[spotIndex()];
    if (!s) return;
    appliedEnsureStyle();
    spotIds = idsForPcs(s.absMeasure, s.chromaticPcs);
    spotIds.forEach(function (id) { svgSetClass(id, "ht-intruder", true); });
  }

  // Light the whole resolution as the tritone resolves (resolve stage): the
  // origin tritone tones (fromPcs, in the applied chord's measure) AND the
  // landing tones (toPcs) — the plan's "F#+C → G+B flagged green".
  function tritoneFlash(t) {
    var res = t && t.tritoneResolution;
    if (!res) return;
    appliedEnsureStyle();
    tritoneIds = idsForPcs(t.absMeasure, res.toPcs);
    if (res.fromMeasure !== undefined && res.fromMeasure !== null) {
      tritoneIds = tritoneIds.concat(idsForPcs(res.fromMeasure, res.fromPcs));
    }
    tritoneIds.forEach(function (id) { svgSetClass(id, "ht-tritone-ok", true); });
    resolveMsg = "✓ Tritone resolved: " + (res.text || "");
  }

  function clearAppliedHighlights() {
    spotIds.forEach(function (id) { svgSetClass(id, "ht-intruder", false); });
    tritoneIds.forEach(function (id) { svgSetClass(id, "ht-tritone-ok", false); });
    spotIds = [];
    tritoneIds = [];
    resolveMsg = "";
  }

  function spotIndex() {
    return data ? Math.trunc(Number(data.SPOT_INDEX)) : -1;
  }

  // The ear stage's second question (null when the payload asks only "where").
  function spotFollowup() {
    return (answerMode === "spot" && data && data.SPOT_FOLLOWUP)
      ? data.SPOT_FOLLOWUP : null;
  }

  // Between the two questions: the position is found, the degree is not.
  function followupPending() {
    return !!(spotFollowup() && spotFound && !followupDone);
  }

  // ---- echo veil (plan A1, ticket 07) ------------------------------------
  function isVeiled() { return presentation === "echo" && !finished; }

  // The hiding style lives inside the SVG (like the playback style) so it
  // survives the page's own stylesheets.  Everything pitch-identifying is
  // hidden — noteheads (g.note covers stem + accidental), beamed groups,
  // rests, ledger lines, and the chord-symbol / Roman-numeral labels
  // (g.harm) — while staff, clefs, key/time signatures and the cursor stay,
  // so the learner still sees *where* they are, just not *what* sounds.
  function veilEnsureStyle(root) {
    try {
      var doc = root.ownerDocument;
      if (!doc || (doc.getElementById && doc.getElementById("ht-veil-style"))) return;
      var style = doc.createElementNS("http://www.w3.org/2000/svg", "style");
      style.setAttribute("id", "ht-veil-style");
      style.textContent = [
        ".ht-veil g.note, .ht-veil g.chord, .ht-veil g.beam,",
        ".ht-veil g.rest, .ht-veil g.accid, .ht-veil g.dots,",
        ".ht-veil g.ledgerLines, .ht-veil g.harm {",
        "  visibility: hidden;",
        "}",
      ].join("\n");
      root.appendChild(style);
    } catch (e) { /* ignore */ }
  }

  // Sync the veil with the current phase.  The SVG renders asynchronously
  // after init, so keep retrying while it should be veiled but isn't yet.
  function updateVeil(attempts) {
    var on = isVeiled();
    try {
      if (document.body) document.body.classList.toggle("ht-echo", on);
    } catch (e) { /* headless stub */ }
    var root = app && app._svgRoot ? app._svgRoot() : null;
    if (!root) {
      if (on && (attempts || 0) < 100) {
        setTimeout(function () { updateVeil((attempts || 0) + 1); }, 100);
      }
      return;
    }
    veilEnsureStyle(root);
    try { root.classList.toggle("ht-veil", on); } catch (e) { /* ignore */ }
  }

  // The external-sync view of the current target (Atlas / Circle / guide
  // panes poll this).  While veiled it is redacted to what the learner may
  // know — key, mode, and position — so no consumer can leak the answer.
  function publicTarget() {
    var t = cur();
    if (!t || !isVeiled()) return t;
    return { echoVeiled: true, key: t.key, mode: t.mode, render: t.render,
             absMeasure: t.absMeasure, measureNumber: t.measureNumber };
  }

  // ---- navigation --------------------------------------------------------
  function goTo(i) {
    var N = targets().length;
    if (N === 0) return;
    if (i < 0) i = 0;
    if (i > N - 1) i = N - 1;
    idx = i;
    resetAttempt();
    lastAnswer = null;               // feedback belongs to the left target
    finished = false;
    spotFound = false;               // a fresh pass re-asks both ear questions
    followupDone = false;
    clearAppliedHighlights();        // fresh pass: no stale intruder/tritone
    updateVeil();                    // a fresh echo pass re-hides the notation
    applySelection();
    placeHighlight(cur().absMeasure);
    renderPanel();
    emitTargetChange();
  }

  function advance() {
    var N = targets().length;
    if (idx + 1 < N) {
      goTo(idx + 1);
    } else {
      finished = true;
      completed = false;
      satisfied = new Set();
      arpIndex = 0;
      updateVeil();                  // echo reveal: sound before symbol
      renderPanel();
      emitTargetChange();            // consumers may now see the full target
    }
  }

  // ---- MIDI event hooks (run after the base app handlers) ----------------
  // A simultaneity step is satisfied at a note-on when (a) every demanded
  // pitch class is held, (b) at least minDistinct DISTINCT keys land in
  // those classes (octave doubling: two C keys), and (c) one of those keys
  // was struck after the previous step completed — the re-attack rule.
  // This grades CONCURRENCY at note-on time, not attack synchrony: notes
  // struck apart but overlapping still pass (true togetherness would need
  // the discarded timestamps; the concept explanation says so).
  function stepSatisfied(step) {
    var pcs = ((step && step.pcs) || []).map(mod12);
    if (!pcs.length) return false;
    var held = [];                    // distinct held keys landing in pcs
    var fresh = false;
    activeNotes.forEach(function (m) {
      if (pcs.indexOf(mod12(m)) === -1) return;
      held.push(m);
      if (freshNotes.has(m)) fresh = true;
    });
    if (!fresh) return false;                                    // (c)
    var need = Math.trunc(Number(step.minDistinct)) || pcs.length;
    if (held.length < need) return false;                        // (b)
    for (var i = 0; i < pcs.length; i++) {                       // (a)
      var ok = false;
      for (var j = 0; j < held.length; j++) {
        if (mod12(held[j]) === pcs[i]) { ok = true; break; }
      }
      if (!ok) return false;
    }
    return true;
  }

  // A correct step arrived while the graded hold was up: refuse it without
  // touching progress and tell the player what to re-press.  The hint stays
  // until the hold sounds again (cleared at the top of the ordered branch).
  function reportHoldMiss(t) {
    holdMissText = "Keep the " + toneName(t, holdPc(t)) +
      " held — press it again, then replay the note.";
    renderProgress();
  }

  function afterNoteOn(pitch, velocity) {
    var midi = Math.trunc(Number(pitch));
    if (Number(velocity) <= 0) {             // velocity-0 is a note-off
      activeNotes.delete(midi);
      freshNotes.delete(midi);
      return;
    }
    activeNotes.add(midi);
    freshNotes.add(midi);
    if (answerMode !== "midi") return;       // ID drills grade via answer()
    var t = cur();
    if (!t || finished) return;
    var pc = mod12(midi);

    if (isArpeggio()) {
      var steps = stepsFor(t);
      // Hold enforcement (ticket 04 v2): re-pressing the hold clears the
      // hint; the step evaluation below then runs with the hold satisfied
      // (in steps mode the already-held fresh keys can advance right away).
      if (holdMissText && holdDown(t)) {
        holdMissText = "";
        renderProgress();
      }
      if (steps) {
        // Wrong notes stay ignored, and an incomplete dyad is simply not
        // yet satisfied — releasing between its halves carries no error
        // state (near-miss forgiveness).
        if (arpIndex < steps.length && stepSatisfied(steps[arpIndex])) {
          if (!holdDown(t)) {
            reportHoldMiss(t);       // refuse, keep progress (no reset)
            return;
          }
          freshNotes.clear();        // the next step demands its own attack
          arpIndex += 1;
          if (arpIndex >= steps.length) {
            completed = true;
            tritoneFlash(t);         // resolve stage: light the landing tones
            advance();
          } else {
            applySelection();      // keep played tones green, light next step
            renderProgress();
          }
        }
      } else if (pc === mod12(t.pitchClasses[arpIndex])) {
        if (!holdDown(t)) {
          reportHoldMiss(t);         // refuse, keep progress (no reset)
          return;
        }
        arpIndex += 1;
        if (arpIndex >= t.pitchClasses.length) {
          completed = true;
          tritoneFlash(t);           // resolve stage: light the landing tones
          advance();
        } else {
          applySelection();        // keep played tones green, light next tone
          renderProgress();
        }
      }
    } else {
      if (t.pitchClasses.map(mod12).indexOf(pc) !== -1) satisfied.add(pc);
      if (!completed && coversAll(satisfied, t.pitchClasses)) {
        var wantBass = strictBassPc(t);
        var wantTop = dictation === "soprano" ? mod12(t.pitchClasses[0]) : null;
        var low = wantBass === null ? null
          : dictation === "bass" ? lowestHeldNote() : lowestHeldChordTone(t);
        var high = wantTop === null ? null : highestHeldNote();
        var bassOk = wantBass === null ||
          (low !== null && mod12(low) === wantBass);
        var topOk = wantTop === null ||
          (high !== null && mod12(high) === wantTop);
        if (bassOk && topOk) {
          completed = true;
          bassMiss = false;
          bassMissText = "";
          tritoneFlash(t);           // resolve stage: light the landing tones
          renderProgress();
        } else if (!bassOk && low !== null) {
          // Right pitch classes, wrong sounding bass: fail with feedback naming
          // the demanded bass.  Recoverable by adding it below (no release) or
          // by releasing everything for a fresh attempt.
          bassMiss = true;
          bassMissText = "✗ Right chord, wrong bass: " + toneName(t, wantBass) +
            " must be the lowest sounding note" +
            (t.figuredBass ? " (" + t.figuredBass + ")" : "") +
            " — you have " + toneName(t, low) + " in the bass.";
          renderProgress();
        } else if (!topOk && high !== null) {
          // Soprano dictation with a stray note on top: the top line IS the
          // answer, so name the demanded soprano (same recovery as bassMiss).
          bassMiss = true;
          bassMissText = "✗ Right note, wrong top: " + toneName(t, wantTop) +
            " must be the highest sounding note — you have " +
            toneName(t, high) + " on top.";
          renderProgress();
        }
      }
    }
  }

  function afterNoteOff(pitch) {
    var off = Math.trunc(Number(pitch));
    activeNotes.delete(off);
    freshNotes.delete(off);
    if (answerMode !== "midi") return;       // ID drills grade via answer()
    if (finished) return;
    if (isArpeggio()) {
      // Releasing the graded hold shows the keep-held hint right away —
      // not only once a moving note gets refused (ticket 04 v2).
      var t = cur();
      if (t && !completed && holdPc(t) !== null &&
          mod12(off) === holdPc(t) && !holdDown(t) && !holdMissText) {
        reportHoldMiss(t);
      }
      return;                                // arpeggio advances on note-on
    }
    if (completed && app.state.midiDown.size === 0) {
      advance();
      return;
    }
    // A flagged bass miss resets to a clean attempt once every key is up (the
    // feedback stays visible until the next attempt succeeds or the target
    // changes).  Non-strict targets keep accumulating across releases.
    if (bassMiss && app.state.midiDown.size === 0) {
      var keepText = bassMissText;
      resetAttempt();
      bassMissText = keepText;
      applySelection();
    }
  }

  function wrapMidiHandlers() {
    // Save the base (app-bound) handlers exactly once.
    if (!window.__HT_BASE_ON__) window.__HT_BASE_ON__ = window.onMidiNoteOn;
    if (!window.__HT_BASE_OFF__) window.__HT_BASE_OFF__ = window.onMidiNoteOff;

    var baseOn = window.__HT_BASE_ON__;
    var baseOff = window.__HT_BASE_OFF__;

    window.onMidiNoteOn = function (pitch, velocity, ts) {
      if (baseOn) baseOn(pitch, velocity, ts);
      try { afterNoteOn(pitch, velocity, ts); }
      catch (e) { console.error("[HarmonyTrainer] noteOn", e); }
    };
    window.onMidiNoteOff = function (pitch, ts) {
      if (baseOff) baseOff(pitch, ts);
      try { afterNoteOff(pitch, ts); }
      catch (e) { console.error("[HarmonyTrainer] noteOff", e); }
    };
  }

  // ---- non-MIDI answering (plan U2) --------------------------------------
  // MCQ: `given` is an option string, graded against the target's mcq.answer.
  // Card: `given` is a card index, graded against the current target index —
  // or a per-target `answerIndex` override.  Spot (ticket 17): `given` is a
  // card index graded against the payload's SPOT_INDEX — one correct click
  // finishes the whole exercise (a single question, not one per chord).
  // Returns the recorded log entry, or null when answering is not available.
  function submitAnswer(given) {
    var t = cur();
    if (!t) return null;
    // The ear stage's follow-up (ticket 19): the position is already found —
    // `completed` is set — so this branch runs before the usual guard.
    if (followupPending()) return submitFollowup(given);
    if (finished || completed) return null;
    var entry;
    if (answerMode === "mcq") {
      entry = { idx: idx, mode: "mcq", given: given,
                expected: (t.mcq || {}).answer };
    } else if (answerMode === "card") {
      var want = (t.answerIndex === undefined || t.answerIndex === null)
        ? idx : Math.trunc(Number(t.answerIndex));
      entry = { idx: idx, mode: "card", given: Math.trunc(Number(given)),
                expected: want };
    } else if (answerMode === "spot") {
      entry = { idx: idx, mode: "spot", given: Math.trunc(Number(given)),
                expected: spotIndex() };
    } else {
      return null;                    // midi mode: cards navigate, not answer
    }
    entry.correct = entry.given === entry.expected;
    answerLog.push(entry);
    lastAnswer = entry;
    if (entry.correct) {
      completed = true;
      answeredCorrect.add(entry.idx);
      if (answerMode === "spot") {
        // The position question is answered.  Visually that is the whole
        // drill; by ear (SPOT_FOLLOWUP) the degree question comes next and
        // the veil must stay until it is answered — finishing here would
        // reveal the notation the follow-up is asked about.
        spotFound = true;
        if (followupPending()) {
          renderPanel();
          return entry;
        }
        // The full re-render reveals the hidden roman, marks the intruder
        // card amber, and pulses its chromatic noteheads.
        finished = true;
        spotPulse();
        renderPanel();
        emitTargetChange();
        return entry;
      }
      if (answerMode === "card") markCardDone(entry.expected);
      renderProgress();
      renderAnswerUI();
      setTimeout(function () {
        // Only auto-advance the question that was answered (the learner may
        // have navigated away during the feedback beat).
        if (idx === entry.idx && completed && !finished) advance();
      }, ANSWER_ADVANCE_MS);
    } else {
      renderProgress();
      renderAnswerUI();
    }
    return entry;
  }

  // The ear stage's second question (ticket 19): `given` is one of
  // SPOT_FOLLOWUP.options — the degree the intruder tonicised.  Answering it
  // correctly is what finishes the drill and lifts the veil.
  function submitFollowup(given) {
    var f = spotFollowup();
    var entry = { idx: idx, mode: "spot_followup", given: String(given),
                  expected: f.answer };
    entry.correct = entry.given === entry.expected;
    answerLog.push(entry);
    lastAnswer = entry;
    if (entry.correct) {
      followupDone = true;
      finished = true;
      spotPulse();
      renderPanel();
      emitTargetChange();
    } else {
      renderProgress();
      renderAnswerUI();
    }
    return entry;
  }

  function markCardDone(i) {
    try {
      var el = document.querySelector('.htCard[data-index="' + i + '"]');
      if (el) el.classList.add("done");
    } catch (e) { /* headless stub */ }
  }

  // ---- sidebar panel -----------------------------------------------------
  function ensureStyles() {
    if (document.getElementById("htStyle")) return;
    var st = document.createElement("style");
    st.id = "htStyle";
    st.textContent = [
      "#trainerPanel{padding:6px 8px;border-bottom:2px solid #e5e7eb;font:13px/1.35 system-ui;}",
      "#trainerPanel h3{margin:4px 0 6px;color:#0b3a53;font:600 14px system-ui;}",
      "#htTitle{font-weight:600;margin-bottom:4px;}",
      "#htControls{display:flex;gap:6px;align-items:center;margin:6px 0;flex-wrap:wrap;}",
      "#htControls button{cursor:pointer;border:1px solid #cbd5e1;background:#f8fafc;border-radius:5px;padding:3px 8px;font:12px system-ui;}",
      "#htControls button:hover{background:#e2e8f0;}",
      "#htProgress{color:#64748b;font-size:12px;margin-left:auto;}",
      "#htCurrent{background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;padding:8px;margin:6px 0;}",
      "#htCurrent .row{margin:2px 0;}",
      "#htCurrent .lbl{color:#64748b;display:inline-block;min-width:64px;}",
      "#htCurrent .big{font-size:15px;font-weight:700;color:#0b3a53;}",
      "#htCurrent .exp{margin-top:6px;color:#334155;font-size:12px;font-style:italic;}",
      "#htCurrent.done{background:#dcfce7;border-color:#86efac;}",
      "#htBassMsg{display:none;margin:6px 0;padding:6px 8px;background:#fef2f2;border:1px solid #fca5a5;border-radius:6px;color:#991b1b;font-size:12px;}",
      "#htBassMsg.show{display:block;}",
      /* the "keep the hold down" hint (ticket 04 v2): amber, not red — the
         refused note is not an error, the walk resumes once the hold sounds */
      "#htHoldMsg{display:none;margin:6px 0;padding:6px 8px;background:#fffbeb;border:1px solid #fcd34d;border-radius:6px;color:#92400e;font-size:12px;}",
      "#htHoldMsg.show{display:block;}",
      "#htResMsg{display:none;margin:6px 0;padding:6px 8px;background:#dcfce7;border:1px solid #86efac;border-radius:6px;color:#166534;font-size:12px;font-weight:600;}",
      "#htResMsg.show{display:block;}",
      "#htList{max-height:34vh;overflow:auto;margin-top:4px;}",
      "#htList .htGroup{font-weight:600;color:#475569;margin:8px 2px 2px;font-size:12px;}",
      "#htCard{}",
      ".htCard{display:flex;gap:6px;align-items:baseline;padding:4px 6px;margin:2px 0;border:1px solid #e5e7eb;border-radius:5px;cursor:pointer;}",
      ".htCard:hover{background:#f1f5f9;}",
      ".htCard .rn{font-weight:700;min-width:34px;}",
      ".htCard .sym{min-width:38px;}",
      ".htCard .meta{color:#64748b;font-size:11px;}",
      ".htCard.active{border-color:#2563eb;background:#dbeafe;}",
      ".htCard.done{border-color:#16a34a;}",
      ".htCard.done .rn{color:#16a34a;}",
      /* the found intruder (ticket 17): amber card, amber roman */
      ".htCard.intruder{border-color:#d97706;background:#fef3c7;}",
      ".htCard.intruder .rn{color:#b45309;}",
      "#htDone{display:none;margin:6px 0;padding:6px 8px;background:#dcfce7;border:1px solid #16a34a;border-radius:6px;color:#14532d;font-weight:600;}",
      "#htDone.show{display:block;}",
      /* answer strip (plan U2) */
      "#htAnswer{margin:6px 0;}",
      "#htAnswer .prompt{font-weight:600;margin:4px 0;color:#0b3a53;}",
      "#htAnswer .opts{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0;}",
      "#htAnswer button.htOpt{cursor:pointer;border:1px solid #cbd5e1;background:#f8fafc;border-radius:5px;padding:4px 10px;font:13px system-ui;}",
      "#htAnswer button.htOpt:hover{background:#e2e8f0;}",
      "#htAnswer button.htOpt:disabled{opacity:.55;cursor:default;}",
      "#htAnsMsg{margin:4px 0;font-size:12px;font-weight:600;}",
      "#htAnsMsg.ok{color:#166534;}",
      "#htAnsMsg.bad{color:#991b1b;}",
      /* dark mode */
      ".dark-score #trainerPanel{border-bottom-color:#222;}",
      ".dark-score #trainerPanel h3{color:#93c5fd;}",
      ".dark-score #htControls button{background:#1f2937;border-color:#374151;color:#e5e7eb;}",
      ".dark-score #htCurrent{background:#0b1220;border-color:#1e3a8a;color:#e5e7eb;}",
      ".dark-score #htBassMsg{background:#2b0b0b;border-color:#7f1d1d;color:#fca5a5;}",
      ".dark-score #htHoldMsg{background:#292008;border-color:#92400e;color:#fcd34d;}",
      ".dark-score #htCurrent .big{color:#93c5fd;}",
      ".dark-score #htCurrent .exp{color:#cbd5e1;}",
      ".dark-score .htCard{background:#0b0b0b;border-color:#1f2933;color:#e5e7eb;}",
      ".dark-score .htCard.active{background:#1e3a8a;border-color:#60a5fa;}",
      ".dark-score .htCard.intruder{background:#451a03;border-color:#d97706;}",
      ".dark-score .htCard.intruder .rn{color:#fbbf24;}",
      ".dark-score #htResMsg{background:#052e16;border-color:#166534;color:#86efac;}",
      ".dark-score #htAnswer .prompt{color:#93c5fd;}",
      ".dark-score #htAnswer button.htOpt{background:#1f2937;border-color:#374151;color:#e5e7eb;}",
      ".dark-score #htAnsMsg.ok{color:#86efac;}",
      ".dark-score #htAnsMsg.bad{color:#fca5a5;}",
      /* hide the dormant native beat-selector UI while the trainer owns the panel */
      "body.ht-active #side > h3, body.ht-active #side > #beatList{display:none;}",
    ].join("\n");
    document.head.appendChild(st);
  }

  function buildPanelSkeleton() {
    var side = document.getElementById("side");
    if (!side) return;
    var existing = document.getElementById("trainerPanel");
    if (existing) existing.remove();

    var panel = document.createElement("div");
    panel.id = "trainerPanel";
    panel.innerHTML =
      '<h3>Harmony Trainer</h3>' +
      '<div id="htTitle"></div>' +
      '<div id="htControls">' +
      '  <button id="htPrev">◀ Prev</button>' +
      '  <button id="htNext">Next ▶</button>' +
      '  <button id="htReset">Reset</button>' +
      '  <span id="htProgress"></span>' +
      '</div>' +
      '<div id="htDone">✓ Exercise complete!</div>' +
      '<div id="htBassMsg"></div>' +
      '<div id="htHoldMsg"></div>' +
      '<div id="htResMsg"></div>' +
      '<div id="htCurrent"></div>' +
      '<div id="htAnswer"></div>' +
      '<div id="htList"></div>';
    side.insertBefore(panel, side.firstChild);

    document.getElementById("htPrev").addEventListener("click", function () { goTo(idx - 1); });
    document.getElementById("htNext").addEventListener("click", function () { goTo(idx + 1); });
    document.getElementById("htReset").addEventListener("click", function () { goTo(0); });
  }

  function renderCurrent() {
    var el = document.getElementById("htCurrent");
    if (!el) return;
    var t = cur();
    if (!t) { el.textContent = ""; return; }
    var modeWord = t.mode === "natural_minor" ? "natural minor"
      : t.mode === "harmonic_minor" ? "harmonic minor"
      : t.mode === "melodic_minor" ? "melodic minor" : "major";
    var wantBass = strictBassPc(t);
    el.className = completed ? "done" : "";
    // Echo listen phase: everything that names the chord IS the answer —
    // show only the key context, the position, and how to listen.
    if (isVeiled()) {
      // The ear stage's second phase (ticket 19): the bar is found, so the
      // panel stops asking for it and points at the degree question.
      if (followupPending()) {
        var found = targets()[spotIndex()];
        el.innerHTML =
          '<div class="row big">' + esc(t.key) + " — bar " +
          esc(found ? found.measureNumber : "?") + " left the key</div>" +
          '<div class="exp">Now name the degree that chord tonicised, in ' +
          "the answer strip below. The notation stays hidden until you do — " +
          "it would give the answer away.</div>";
        return;
      }
      // Echo + mcq (ticket 10): the learner IDENTIFIES what they hear from
      // the answer strip instead of playing it back.
      var listenHow = answerMode === "spot"
        ? "hear the progression, then click the bar where the harmony left " +
          "the key — one chord is borrowed from elsewhere"
        : answerMode === "mcq"
        ? "hear the chord, then name it from the answer strip below."
        : dictation === "bass"
          ? "hear the progression, then play only its bass line — one " +
            "bass note per measure (any octave)"
          : dictation === "soprano"
            ? "hear the cadence, then play only its top line — one " +
              "soprano note per measure (nothing above it)"
            : "hear the target, then play it back on the keyboard. It is " +
              "graded exactly like the visual drill";
      el.innerHTML =
        '<div class="row big">' + esc(t.key) + " — echo by ear</div>" +
        '<div class="row"><span class="lbl">Mode</span>' + esc(modeWord) + "</div>" +
        '<div class="row"><span class="lbl">Where</span>bar ' +
        esc(t.measureNumber) + " (highlighted)</div>" +
        '<div class="exp">🎧 Notation is hidden. Press ▶ Play to ' +
        listenHow + "; finishing reveals the notation.</div>";
      return;
    }
    // Identification (MCQ): the Roman numeral, function, tones etc. ARE the
    // answer — show only the key context and point at the highlighted bar.
    if (answerMode === "mcq") {
      el.innerHTML =
        '<div class="row big">' + esc(t.key) + "</div>" +
        '<div class="row"><span class="lbl">Mode</span>' + esc(modeWord) + "</div>" +
        '<div class="row"><span class="lbl">Where</span>bar ' +
        esc(t.measureNumber) + " (highlighted)</div>";
      return;
    }
    // Spot the intruder (ticket 17): the question is about the whole
    // progression, not the current chord.  After the find, the panel owns
    // the reveal — the intruder's name and its one-liner explanation.
    if (answerMode === "spot") {
      var s = targets()[spotIndex()];
      if (finished && s) {
        el.className = "done";
        el.innerHTML =
          '<div class="row big">' + esc(s.chordSymbol) + " is " +
          esc(s.roman) + "</div>" +
          '<div class="exp">' + esc(s.explanation) + "</div>";
      } else {
        el.className = "";
        el.innerHTML =
          '<div class="row big">' + esc(t.key) + " — spot the intruder</div>" +
          '<div class="row"><span class="lbl">Mode</span>' + esc(modeWord) + "</div>" +
          '<div class="row"><span class="lbl">Scale</span>' + esc(t.scale.join(" ")) + "</div>";
      }
      return;
    }
    // Card matching: the card labels carry the Roman/symbol, so the prompt
    // describes the chord without naming it.
    if (answerMode === "card") {
      el.innerHTML =
        '<div class="row big">' + esc(t.key) + " — which chord is this?</div>" +
        '<div class="row"><span class="lbl">Mode</span>' + esc(modeWord) + "</div>" +
        '<div class="row"><span class="lbl">Tones</span>' + esc(t.chordTones.join("–")) + "</div>" +
        '<div class="row"><span class="lbl">Function</span>' + esc(t.functionLabel) +
        " (" + esc(t.scaleDegreeName) + ")</div>";
      return;
    }
    el.innerHTML =
      '<div class="row big">' + esc(t.key) + " — " + esc(t.roman) +
      " (" + esc(t.functionLabel) + ")</div>" +
      (wantBass === null ? "" :
        '<div class="row"><span class="lbl">Bass</span>' +
        esc(t.bassNote || toneName(t, wantBass)) + " — lowest note" +
        (t.figuredBass ? " (" + esc(t.figuredBass) + ")" : "") + "</div>") +
      '<div class="row"><span class="lbl">Mode</span>' + esc(modeWord) + "</div>" +
      '<div class="row"><span class="lbl">Scale</span>' + esc(t.scale.join(" ")) + "</div>" +
      '<div class="row"><span class="lbl">Chord</span>' + esc(t.chordSymbol) +
      "  (" + esc(t.quality) + ")</div>" +
      '<div class="row"><span class="lbl">Tones</span>' + esc(t.chordTones.join("–")) + "</div>" +
      '<div class="row"><span class="lbl">Layer</span>' + esc(t.intervalLayer) + "</div>" +
      '<div class="row"><span class="lbl">Function</span>' + esc(t.functionLabel) +
      " (" + esc(t.scaleDegreeName) + ")</div>" +
      '<div class="exp">' + esc(t.explanation) + "</div>";
  }

  function renderProgress() {
    var p = document.getElementById("htProgress");
    if (p) p.textContent = "Chord " + (idx + 1) + " / " + targets().length;
    var done = document.getElementById("htDone");
    if (done) done.className = finished ? "show" : "";
    var bm = document.getElementById("htBassMsg");
    if (bm) {
      bm.textContent = bassMissText;
      bm.className = bassMissText ? "show" : "";
    }
    var hm = document.getElementById("htHoldMsg");
    if (hm) {
      hm.textContent = holdMissText;
      hm.className = holdMissText ? "show" : "";
    }
    var rm = document.getElementById("htResMsg");
    if (rm) {
      rm.textContent = resolveMsg;
      rm.className = resolveMsg ? "show" : "";
    }
    renderCurrent();
    // reflect completion state on the active card
    var card = document.querySelector('.htCard.active');
    if (card && completed) card.classList.add("done");
  }

  function renderList() {
    var list = document.getElementById("htList");
    if (!list) return;
    list.innerHTML = "";
    // MCQ identification: the ordered card list (I..vii° per measure) would
    // hand out the answer; the MCQ strip replaces it entirely.
    if (answerMode === "mcq") return;
    // Echo listen phase: every card names its chord (roman + symbol), so the
    // list is withheld until the finish reveal.
    if (isVeiled()) return;
    // Card mode: display order is shuffled once per exercise — otherwise the
    // targets advance in exactly the list's order and clicking top-to-bottom
    // would complete the drill without reading the prompt.  Group headers are
    // dropped there (they assume measure order); grading indexes unchanged.
    // Spot mode keeps measure order — the order IS the progression.
    var order = targets().map(function (_, i) { return i; });
    if (answerMode === "card") {
      if (!cardOrder || cardOrder.length !== order.length) {
        for (var j = order.length - 1; j > 0; j--) {
          var k = Math.floor(Math.random() * (j + 1));
          var tmp = order[j]; order[j] = order[k]; order[k] = tmp;
        }
        cardOrder = order.slice();
      }
      order = cardOrder.slice();
    }
    var lastGroup = null;
    order.forEach(function (i) {
      var t = targets()[i];
      if (answerMode !== "card" && t.group && t.group !== lastGroup) {
        var g = document.createElement("div");
        g.className = "htGroup";
        g.textContent = t.group;
        list.appendChild(g);
        lastGroup = t.group;
      }
      var card = document.createElement("div");
      // Card-answer mode: marking the active card would answer the question,
      // so only correctly answered cards get a state.
      var active = (answerMode === "card" || answerMode === "spot")
        ? "" : (i === idx ? " active" : "");
      var done = answerMode === "card" && answeredCorrect.has(i) ? " done" : "";
      // Spot reveal: the found intruder's card turns amber.
      var intruder = (answerMode === "spot" && finished && t.intruder)
        ? " intruder" : "";
      card.className = "htCard" + active + done + intruder;
      card.dataset.index = String(i);
      if (answerMode === "spot" && !finished) {
        // The hunt: the intruder's roman IS the answer, so it shows "?";
        // function/degree metadata would leak it too — every card shows its
        // bar number instead.
        card.innerHTML =
          '<span class="rn">' + esc(t.romanHidden ? "?" : t.roman) + "</span>" +
          '<span class="sym">' + esc(t.chordSymbol) + "</span>" +
          '<span class="meta">bar ' + esc(t.measureNumber) + "</span>";
      } else {
        card.innerHTML =
          '<span class="rn">' + esc(t.roman) + "</span>" +
          '<span class="sym">' + esc(t.chordSymbol) + "</span>" +
          '<span class="meta">' + esc(t.intervalLayer) + " · " +
          esc(t.functionLabel) + "</span>";
      }
      card.addEventListener("click", function () {
        if (answerMode === "card" || answerMode === "spot") submitAnswer(i);
        else goTo(i);
      });
      list.appendChild(card);
    });
  }

  // One row of answer buttons (MCQ options, the ear stage's bar positions or
  // its follow-up degrees) — same look, same disabled rule.
  function optionButtons(options, onPick, disabled) {
    var row = document.createElement("div");
    row.className = "opts";
    (options || []).forEach(function (opt) {
      var b = document.createElement("button");
      b.className = "htOpt";
      b.textContent = opt;
      if (disabled) b.disabled = true;
      b.addEventListener("click", function () { onPick(opt); });
      row.appendChild(b);
    });
    return row;
  }

  // The answer strip: MCQ options for identification drills, the ear stage's
  // bar-position strip and follow-up question, or the click-a-card
  // instruction.  Empty (and inert) in classic midi mode.
  function renderAnswerUI() {
    var box = document.getElementById("htAnswer");
    if (!box) return;
    box.innerHTML = "";
    if (answerMode === "midi" || finished) return;
    var t = cur();
    if (!t) return;

    var followup = followupPending() ? spotFollowup() : null;
    var prompt = document.createElement("div");
    prompt.className = "prompt";
    prompt.textContent = followup
      ? (followup.prompt || "Which degree did that chord tonicise?")
      : answerMode === "mcq"
        ? ((t.mcq && t.mcq.prompt) || "Identify the chord:")
        : answerMode === "spot"
          ? (isVeiled()
              // Veiled: the cards are withheld, so the bar strip below IS the
              // answer surface — the question is *where*, not *which card*.
              ? "One bar leaves " + t.key + ". Which one did you hear?"
              : "One of these chords doesn't live in " + t.key + ". Click it.")
          : "Click the matching chord card below.";
    box.appendChild(prompt);

    if (followup) {
      box.appendChild(optionButtons(followup.options, submitFollowup));
    } else if (answerMode === "mcq") {
      box.appendChild(optionButtons(((t.mcq) && t.mcq.options) || [],
                                    submitAnswer, completed));
    } else if (answerMode === "spot" && isVeiled()) {
      // The ear stage's position strip: bar numbers only — no roman, no chord
      // symbol, nothing the veil is hiding.
      var strip = document.createElement("div");
      strip.className = "opts";
      targets().forEach(function (tt, i) {
        var b = document.createElement("button");
        b.className = "htOpt htPos";
        b.textContent = "bar " + tt.measureNumber;
        b.dataset.index = String(i);
        b.addEventListener("click", function () { submitAnswer(i); });
        strip.appendChild(b);
      });
      box.appendChild(strip);
    }

    var msg = document.createElement("div");
    msg.id = "htAnsMsg";
    if (lastAnswer && lastAnswer.idx === idx) {
      var named = lastAnswer.mode === "mcq"
        || lastAnswer.mode === "spot_followup";
      msg.className = lastAnswer.correct ? "ok" : "bad";
      msg.textContent = lastAnswer.correct
        ? "✓ Correct — " + (named ? String(lastAnswer.given) : "that's the one") + "!"
        : (named
            ? "✗ Not " + String(lastAnswer.given) + " — try again."
            : answerMode === "spot"
              ? (isVeiled()
                  ? "✗ That bar stayed in " + ((cur() || {}).key || "the key") +
                    " — listen again."
                  : "✗ That chord lives in " +
                    ((cur() || {}).key || "the key") + " — try again.")
              : "✗ Not that card — try again.");
      box.appendChild(msg);
    }
  }

  function renderPanel() {
    var title = document.getElementById("htTitle");
    if (title) {
      var renderWord = data.render === "arpeggio" ? "arpeggio" : "block triads";
      // Echo titles can spell the progression ("Echo: V–I …"), so while the
      // drill is veiled the header stays neutral; the finish reveal brings
      // the full title back alongside the notation.
      title.textContent = isVeiled()
        ? (answerMode === "spot"
            ? "🎧 Ear drill — listen, then spot the chromatic chord"
            : answerMode === "mcq"
            ? "🎧 Ear drill — listen, then identify  —  " + renderWord
            : dictation === "bass"
              ? "🎧 Bass-line dictation — listen, then play the bass line"
              : dictation === "soprano"
                ? "🎧 Soprano dictation — listen, then play the top line"
                : "🎧 Echo drill — listen, then play it back  —  " + renderWord)
        : (data.title || "Exercise") + "  —  " + renderWord;
    }
    renderList();
    renderAnswerUI();
    renderProgress();
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // ---- public API --------------------------------------------------------
  function init(payload) {
    app = window.ScoreApp;
    if (!app || !app.state) {
      return { ok: false, why: "ScoreApp not ready" };
    }
    data = payload || {};
    idx = 0;
    resetAttempt();
    finished = false;
    pbStamp = new Map();
    answerMode = (data.ANSWER_MODE === "mcq" || data.ANSWER_MODE === "card" ||
                  data.ANSWER_MODE === "spot")
      ? data.ANSWER_MODE : "midi";
    presentation = data.PRESENTATION === "echo" ? "echo" : "visual";
    dictation = (data.DICTATION === "bass" || data.DICTATION === "soprano")
      ? data.DICTATION : null;
    answerLog = [];
    lastAnswer = null;
    answeredCorrect = new Set();
    cardOrder = null;
    spotIds = [];
    tritoneIds = [];
    resolveMsg = "";
    spotFound = false;
    followupDone = false;

    ensureStyles();
    if (document.body) document.body.classList.add("ht-active");
    buildPanelSkeleton();
    wrapMidiHandlers();
    updateVeil();
    applySelection();
    if (cur()) placeHighlight(cur().absMeasure);
    renderPanel();
    emitTargetChange();

    return { ok: true, targets: targets().length };
  }

  window.HarmonyTrainer = {
    init: init,
    goTo: goTo,
    next: function () { goTo(idx + 1); },
    prev: function () { goTo(idx - 1); },
    reset: function () { goTo(0); },
    state: function () {
      return { idx: idx, completed: completed, finished: finished,
               arpIndex: arpIndex, heldNotes: activeNotes.size,
               total: targets().length,
               answerMode: answerMode, answered: answerLog.length,
               presentation: presentation, veiled: isVeiled(),
               dictation: dictation,
               // The ear stage's two-question flow (ticket 19): "where" is
               // answered, "which degree" is still open.
               followupPending: followupPending() };
    },
    // Non-MIDI answering (plan U2).  MCQ: answer("IV"); card: answer(3).
    answer: submitAnswer,
    answerState: function () {
      return { mode: answerMode, log: answerLog.slice(),
               last: lastAnswer || undefined };
    },
    // The current target chord (consumed by the Harmony Atlas to sync its
    // highlight to the live playback position). Null when nothing is loaded.
    // During an unfinished echo drill this is redacted to key/mode/position
    // (echoVeiled: true) so no external pane can leak the answer.
    currentTarget: publicTarget,
    // Target playback visuals (driven by audio/target_playback.py).
    playbackFlash: playbackFlash,
    playbackClear: playbackClear,
    playbackActiveIds: function () { return Array.from(pbStamp.keys()); },
    // Applied-chord highlights (ticket 17): the intruder's pulsing chromatic
    // noteheads and the resolve stage's green tritone-resolution noteheads.
    spotActiveIds: function () { return spotIds.slice(); },
    tritoneActiveIds: function () { return tritoneIds.slice(); },
  };
})();
