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

  // ---- answer modes (plan U2, ticket 06) ---------------------------------
  // "midi" is the classic play-the-chord flow.  "mcq" renders an answer
  // strip for identification drills; "card" turns the chord-card list into
  // the answer surface.  In both non-midi modes MIDI events keep their
  // monitoring visuals but never grade.
  var ANSWER_ADVANCE_MS = 600;
  var answerMode = "midi";  // "midi" | "mcq" | "card"
  var answerLog = [];       // {idx, mode, given, expected, correct}
  var lastAnswer = null;    // latest entry (feedback for the current target)
  var answeredCorrect = new Set();   // target indexes answered correctly
  var cardOrder = null;     // card mode: shuffled DISPLAY order (once per
                            // exercise) so the list doesn't mirror the
                            // question sequence — indexes/grading unchanged

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

  function resetAttempt() {
    satisfied = new Set();
    arpIndex = 0;
    completed = false;
    bassMiss = false;
    bassMissText = "";
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

  function expectedPcsForCurrent() {
    var t = cur();
    if (!t) return [];
    if (isArpeggio()) {
      return t.pitchClasses.slice(0, Math.min(arpIndex + 1, t.pitchClasses.length));
    }
    return t.pitchClasses.slice();
  }

  function applySelection() {
    var t = cur();
    if (!t) return;
    buildSelection(expectedPcsForCurrent(), t.absMeasure);
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
          { detail: detail === undefined ? cur() : detail }));
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
      renderPanel();
    }
  }

  // ---- MIDI event hooks (run after the base app handlers) ----------------
  function afterNoteOn(pitch, velocity) {
    if (answerMode !== "midi") return;       // ID drills grade via answer()
    if (Number(velocity) <= 0) return;       // velocity-0 is a note-off
    var t = cur();
    if (!t || finished) return;
    var pc = mod12(Math.trunc(Number(pitch)));

    if (isArpeggio()) {
      if (pc === mod12(t.pitchClasses[arpIndex])) {
        arpIndex += 1;
        if (arpIndex >= t.pitchClasses.length) {
          completed = true;
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
        var low = wantBass === null ? null : lowestHeldChordTone(t);
        if (wantBass === null || (low !== null && mod12(low) === wantBass)) {
          completed = true;
          bassMiss = false;
          bassMissText = "";
          renderProgress();
        } else if (low !== null) {
          // Right pitch classes, wrong sounding bass: fail with feedback naming
          // the demanded bass.  Recoverable by adding it below (no release) or
          // by releasing everything for a fresh attempt.
          bassMiss = true;
          bassMissText = "✗ Right chord, wrong bass: " + toneName(t, wantBass) +
            " must be the lowest sounding note" +
            (t.figuredBass ? " (" + t.figuredBass + ")" : "") +
            " — you have " + toneName(t, low) + " in the bass.";
          renderProgress();
        }
      }
    }
  }

  function afterNoteOff() {
    if (answerMode !== "midi") return;       // ID drills grade via answer()
    if (finished) return;
    if (isArpeggio()) return;                // arpeggio advances on note-on
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
  // or a per-target `answerIndex` override (the "spot the intruder" seam).
  // Returns the recorded log entry, or null when answering is not available.
  function submitAnswer(given) {
    var t = cur();
    if (!t || finished || completed) return null;
    var entry;
    if (answerMode === "mcq") {
      entry = { idx: idx, mode: "mcq", given: given,
                expected: (t.mcq || {}).answer };
    } else if (answerMode === "card") {
      var want = (t.answerIndex === undefined || t.answerIndex === null)
        ? idx : Math.trunc(Number(t.answerIndex));
      entry = { idx: idx, mode: "card", given: Math.trunc(Number(given)),
                expected: want };
    } else {
      return null;                    // midi mode: cards navigate, not answer
    }
    entry.correct = entry.given === entry.expected;
    answerLog.push(entry);
    lastAnswer = entry;
    if (entry.correct) {
      completed = true;
      answeredCorrect.add(entry.idx);
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
      ".dark-score #htCurrent .big{color:#93c5fd;}",
      ".dark-score #htCurrent .exp{color:#cbd5e1;}",
      ".dark-score .htCard{background:#0b0b0b;border-color:#1f2933;color:#e5e7eb;}",
      ".dark-score .htCard.active{background:#1e3a8a;border-color:#60a5fa;}",
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
    var modeWord = t.mode === "natural_minor" ? "natural minor" : "major";
    var wantBass = strictBassPc(t);
    el.className = completed ? "done" : "";
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
    // Card mode: display order is shuffled once per exercise — otherwise the
    // targets advance in exactly the list's order and clicking top-to-bottom
    // would complete the drill without reading the prompt.  Group headers are
    // dropped there (they assume measure order); grading indexes unchanged.
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
      var active = answerMode === "card" ? "" : (i === idx ? " active" : "");
      var done = answerMode === "card" && answeredCorrect.has(i) ? " done" : "";
      card.className = "htCard" + active + done;
      card.dataset.index = String(i);
      card.innerHTML =
        '<span class="rn">' + esc(t.roman) + "</span>" +
        '<span class="sym">' + esc(t.chordSymbol) + "</span>" +
        '<span class="meta">' + esc(t.intervalLayer) + " · " +
        esc(t.functionLabel) + "</span>";
      card.addEventListener("click", function () {
        if (answerMode === "card") submitAnswer(i);
        else goTo(i);
      });
      list.appendChild(card);
    });
  }

  // The answer strip: MCQ options for identification drills, or the
  // click-a-card instruction.  Empty (and inert) in classic midi mode.
  function renderAnswerUI() {
    var box = document.getElementById("htAnswer");
    if (!box) return;
    box.innerHTML = "";
    if (answerMode === "midi" || finished) return;
    var t = cur();
    if (!t) return;

    var prompt = document.createElement("div");
    prompt.className = "prompt";
    prompt.textContent = answerMode === "mcq"
      ? ((t.mcq && t.mcq.prompt) || "Identify the chord:")
      : "Click the matching chord card below.";
    box.appendChild(prompt);

    if (answerMode === "mcq") {
      var opts = document.createElement("div");
      opts.className = "opts";
      (((t.mcq) && t.mcq.options) || []).forEach(function (opt) {
        var b = document.createElement("button");
        b.className = "htOpt";
        b.textContent = opt;
        if (completed) b.disabled = true;
        b.addEventListener("click", function () { submitAnswer(opt); });
        opts.appendChild(b);
      });
      box.appendChild(opts);
    }

    var msg = document.createElement("div");
    msg.id = "htAnsMsg";
    if (lastAnswer && lastAnswer.idx === idx) {
      msg.className = lastAnswer.correct ? "ok" : "bad";
      msg.textContent = lastAnswer.correct
        ? "✓ Correct — " + (answerMode === "mcq" ? String(lastAnswer.given) : "that's the one") + "!"
        : (answerMode === "mcq"
            ? "✗ Not " + String(lastAnswer.given) + " — try again."
            : "✗ Not that card — try again.");
      box.appendChild(msg);
    }
  }

  function renderPanel() {
    var title = document.getElementById("htTitle");
    if (title) {
      title.textContent = (data.title || "Exercise") +
        "  —  " + (data.render === "arpeggio" ? "arpeggio" : "block triads");
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
    answerMode = (data.ANSWER_MODE === "mcq" || data.ANSWER_MODE === "card")
      ? data.ANSWER_MODE : "midi";
    answerLog = [];
    lastAnswer = null;
    answeredCorrect = new Set();
    cardOrder = null;

    ensureStyles();
    if (document.body) document.body.classList.add("ht-active");
    buildPanelSkeleton();
    wrapMidiHandlers();
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
               arpIndex: arpIndex, total: targets().length,
               answerMode: answerMode, answered: answerLog.length };
    },
    // Non-MIDI answering (plan U2).  MCQ: answer("IV"); card: answer(3).
    answer: submitAnswer,
    answerState: function () {
      return { mode: answerMode, log: answerLog.slice(),
               last: lastAnswer || undefined };
    },
    // The current target chord (consumed by the Harmony Atlas to sync its
    // highlight to the live playback position). Null when nothing is loaded.
    currentTarget: function () { return cur(); },
    // Target playback visuals (driven by audio/target_playback.py).
    playbackFlash: playbackFlash,
    playbackClear: playbackClear,
    playbackActiveIds: function () { return Array.from(pbStamp.keys()); },
  };
})();
