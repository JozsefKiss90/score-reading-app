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

  // Map: pitch class -> Set(noteId) for a given measure, from boot.PITCH_MAP.
  function idsByPcForMeasure(absMeasure) {
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
        var pc = mod12(mm);
        if (!out.has(pc)) out.set(pc, new Set());
        out.get(pc).add(String(r.id));
      });
    });
    return out;
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

  // ---- navigation --------------------------------------------------------
  function goTo(i) {
    var N = targets().length;
    if (N === 0) return;
    if (i < 0) i = 0;
    if (i > N - 1) i = N - 1;
    idx = i;
    satisfied = new Set();
    arpIndex = 0;
    completed = false;
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
        completed = true;
        renderProgress();
      }
    }
  }

  function afterNoteOff() {
    if (finished) return;
    if (isArpeggio()) return;                // arpeggio advances on note-on
    if (completed && app.state.midiDown.size === 0) {
      advance();
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
      /* dark mode */
      ".dark-score #trainerPanel{border-bottom-color:#222;}",
      ".dark-score #trainerPanel h3{color:#93c5fd;}",
      ".dark-score #htControls button{background:#1f2937;border-color:#374151;color:#e5e7eb;}",
      ".dark-score #htCurrent{background:#0b1220;border-color:#1e3a8a;color:#e5e7eb;}",
      ".dark-score #htCurrent .big{color:#93c5fd;}",
      ".dark-score #htCurrent .exp{color:#cbd5e1;}",
      ".dark-score .htCard{background:#0b0b0b;border-color:#1f2933;color:#e5e7eb;}",
      ".dark-score .htCard.active{background:#1e3a8a;border-color:#60a5fa;}",
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
      '<div id="htCurrent"></div>' +
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
    el.className = completed ? "done" : "";
    el.innerHTML =
      '<div class="row big">' + esc(t.key) + " — " + esc(t.roman) +
      " (" + esc(t.functionLabel) + ")</div>" +
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
    renderCurrent();
    // reflect completion state on the active card
    var card = document.querySelector('.htCard.active');
    if (card && completed) card.classList.add("done");
  }

  function renderList() {
    var list = document.getElementById("htList");
    if (!list) return;
    list.innerHTML = "";
    var lastGroup = null;
    targets().forEach(function (t, i) {
      if (t.group && t.group !== lastGroup) {
        var g = document.createElement("div");
        g.className = "htGroup";
        g.textContent = t.group;
        list.appendChild(g);
        lastGroup = t.group;
      }
      var card = document.createElement("div");
      card.className = "htCard" + (i === idx ? " active" : "");
      card.dataset.index = String(i);
      card.innerHTML =
        '<span class="rn">' + esc(t.roman) + "</span>" +
        '<span class="sym">' + esc(t.chordSymbol) + "</span>" +
        '<span class="meta">' + esc(t.intervalLayer) + " · " +
        esc(t.functionLabel) + "</span>";
      card.addEventListener("click", function () { goTo(i); });
      list.appendChild(card);
    });
  }

  function renderPanel() {
    var title = document.getElementById("htTitle");
    if (title) {
      title.textContent = (data.title || "Exercise") +
        "  —  " + (data.render === "arpeggio" ? "arpeggio" : "block triads");
    }
    renderList();
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
    satisfied = new Set();
    arpIndex = 0;
    completed = false;
    finished = false;

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
               arpIndex: arpIndex, total: targets().length };
    },
    // The current target chord (consumed by the Harmony Atlas to sync its
    // highlight to the live playback position). Null when nothing is loaded.
    currentTarget: function () { return cur(); },
  };
})();
