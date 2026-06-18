/*
 * Music Theory Laboratory -- web UI controller (concept selector + explanation).
 *
 * Loaded by beat_selector/harmony_lab.html inside a QWebEngineView (left/right
 * panes of run_harmony_lab_demo.py).  It renders the catalog of lab experiments
 * produced by harmony.lab.lab_demo_specs() into a concept selector, and shows a
 * rich explanation of the trainer's current target chord on the right.  It
 * exposes a small, host-pollable API mirroring beat_selector/atlas.js:
 *
 *   HarmonyLab.init(data)             -> render the selector; returns {ok, experiments}
 *   HarmonyLab.takeLaunch()           -> dequeue a clicked LabExperimentSpec (host polls)
 *   HarmonyLab.updateExplanation(t)   -> render the guide for the live target chord
 *   HarmonyLab.setSync(active)        -> highlight the bottom Atlas-mapping strip
 *   HarmonyLab.showConcept(id)        -> switch the selected concept section
 *
 * It deliberately does NOT touch MIDI or the score: the middle pane is the
 * existing ScoreViewBeats + the injected harmony_trainer.js, which own MIDI
 * validation.  The host bridges the two via runJavaScript polling (no
 * QWebChannel), exactly like the Atlas/Circle integrations.
 *
 * All stateful logic (launchQueue, experiments-by-concept grouping, explanation
 * model) is kept inspectable and decoupled from DOM querying, so it is
 * unit-testable headlessly under Node (see tests/harmony_lab_node_test.js).
 */
(function () {
  "use strict";

  // -- module state ---------------------------------------------------------
  var data = null;
  var conceptId = null;                 // currently selected concept section
  var launchQueue = [];                 // clicked specs the host will pick up
  var currentTarget = null;             // last target pushed by the host

  // Which spec.concept values belong to each selector concept id.
  var CONCEPT_MEMBERS = {
    inversion: ["inversion"],
    voice_leading_cadence: ["cadence", "voice_leading"],
    motive: ["motive"],
    polyphonic_harmony: ["polyphonic_harmony"],
    real_score_analysis: [],            // reserved placeholder (no experiments)
  };

  // -- tiny DOM helpers (tolerant of the Node test's stubbed document) -------
  function dollar(id) { return document.getElementById(id); }

  function el(tag, props, children) {
    var node = document.createElement(tag);
    props = props || {};
    Object.keys(props).forEach(function (k) {
      if (k === "class") { node.className = props[k]; }
      else if (k === "text") { node.textContent = props[k]; }
      else if (k === "html") { node.innerHTML = props[k]; }
      else if (k === "onClick") { node.addEventListener("click", props[k]); }
      else if (k === "dataset") {
        var ds = props[k];
        Object.keys(ds).forEach(function (d) { if (node.dataset) node.dataset[d] = ds[d]; });
      } else if (node.setAttribute) { node.setAttribute(k, props[k]); }
    });
    (children || []).forEach(function (c) {
      if (c == null) return;
      if (typeof c === "string") {
        var t = document.createElement("span"); t.textContent = c; node.appendChild(t);
      } else { node.appendChild(c); }
    });
    return node;
  }

  function clear(node) { if (node) node.innerHTML = ""; }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // -- pure helpers (also exercised by the Node test) -----------------------

  // Experiments belonging to a selector concept id, in catalog order.
  function experimentsFor(conceptKey) {
    var members = CONCEPT_MEMBERS[conceptKey] || [];
    return (data && data.experiments ? data.experiments : []).filter(function (e) {
      return members.indexOf(e.concept) !== -1;
    });
  }

  // The display model for the explanation pane (decoupled from the DOM).
  function explanationModel(t) {
    if (!t) return null;
    var rows = [];
    function add(label, value) {
      if (value != null && value !== "" &&
          !(Array.isArray(value) && value.length === 0)) {
        rows.push({ label: label, value: Array.isArray(value) ? value.join(", ") : value });
      }
    }
    var modeWord = t.mode === "natural_minor" ? "natural minor" : "major";
    add("Key", (t.key || "") + " (" + modeWord + ")");
    if (t.concept === "melody") {
      add("Motive", t.motiveLabel);
      add("Degrees", t.degreeLabels);
    } else {
      add("Chord", t.chordSymbol + (t.roman ? "  (" + t.roman + ")" : ""));
      add("Function", t.functionLabel);
    }
    if (t.inversionLabel) {
      add("Inversion", t.inversionLabel + (t.figuredBass ? "  " + t.figuredBass : ""));
      add("Bass", t.bassNote);
      add("Invariant tones", (t.chordTones || []).join("–"));
    }
    if (t.voices && t.voices.length) {
      add("Voices", t.voices.map(function (v) { return v[0] + " " + v[1]; }));
    }
    add("Common tones", t.commonTones);
    add("Bass motion", t.bassMotion);
    add("Tendency tones", t.tendencyTones);
    if (t.impliedChord) add("Implies", t.impliedChord + " (" + (t.impliedRoman || "") + ")");
    return {
      heading: headingFor(t),
      rows: rows,
      note: t.labNote || t.explanation || "",
    };
  }

  function headingFor(t) {
    if (t.concept === "melody") return t.motiveLabel + " — " + (t.key || "");
    var bits = [];
    if (t.chordSymbol) bits.push(t.chordSymbol);
    if (t.roman) bits.push(t.roman);
    if (t.inversionLabel) bits.push(t.inversionLabel);
    return bits.join("  ");
  }

  // Parse an Atlas node id ("triad:C:major:0") into {kind, label}.
  function syncChips(active) {
    var out = [];
    if (!active) return out;
    Object.keys(active).forEach(function (kind) {
      var id = active[kind];
      if (!id) return;
      var parts = String(id).split(":");
      out.push({ kind: kind, id: id, label: parts.slice(1).join(" ") });
    });
    return out;
  }

  // -- launch queue (host integration) --------------------------------------
  function launch(spec) {
    if (spec) launchQueue.push(spec);
  }
  function takeLaunch() {
    return launchQueue.length ? launchQueue.shift() : null;
  }

  // -- rendering ------------------------------------------------------------
  function renderConcepts() {
    var nav = dollar("labConcepts");
    if (!nav) return;
    clear(nav);
    (data.concepts || []).forEach(function (c) {
      var experiments = experimentsFor(c.id);
      var section = el("div", { class: "labConcept" + (c.id === conceptId ? " active" : "") });
      var head = el("div", {
        class: "labConceptHead" + (c.reserved ? " reserved" : ""),
        onClick: function () { if (!c.reserved) showConcept(c.id); },
      }, [c.label + (c.reserved ? "  (reserved)" : "  (" + experiments.length + ")")]);
      section.appendChild(head);
      if (c.detail) section.appendChild(el("div", { class: "labConceptDetail", text: c.detail }));
      if (c.id === conceptId) {
        var list = el("div", { class: "labExpList" });
        experiments.forEach(function (e) {
          list.appendChild(el("div", {
            class: "labExp", dataset: { id: e.experiment_id },
            onClick: function () { launch(e); flash(e.experiment_id); },
          }, [
            el("div", { class: "labExpTitle", text: e.title }),
            el("div", { class: "labExpMeta", text: (e.description || e.concept) }),
          ]));
        });
        if (!experiments.length) {
          list.appendChild(el("div", { class: "labExpMeta",
            text: "Reserved — real-score analysis is not implemented yet." }));
        }
        section.appendChild(list);
      }
      nav.appendChild(section);
    });
  }

  function flash(expId) {
    var hint = dollar("labLaunchHint");
    if (hint) hint.textContent = "Launching: " + expId;
  }

  function renderExplanation() {
    var pane = dollar("labExplain");
    if (!pane) return;
    var model = explanationModel(currentTarget);
    if (!model) {
      pane.innerHTML = '<div class="labPlaceholder">Pick an experiment, then play '
        + 'along — the current chord is explained here.</div>';
      return;
    }
    var html = '<div class="labExpHeading">' + esc(model.heading) + "</div>";
    model.rows.forEach(function (r) {
      html += '<div class="labRow"><span class="labLbl">' + esc(r.label)
        + '</span><span class="labVal">' + esc(r.value) + "</span></div>";
    });
    if (model.note) html += '<div class="labNote">' + esc(model.note) + "</div>";
    pane.innerHTML = html;
  }

  function renderSync(active) {
    var strip = dollar("labAtlas");
    if (!strip) return;
    var chips = syncChips(active);
    if (!chips.length) { strip.innerHTML = '<span class="labLbl">Atlas: —</span>'; return; }
    var html = '<span class="labLbl">Atlas:</span>';
    chips.forEach(function (c) {
      html += '<span class="labChip" title="' + esc(c.id) + '">' + esc(c.kind)
        + " · " + esc(c.label) + "</span>";
    });
    strip.innerHTML = html;
  }

  // -- public API -----------------------------------------------------------
  function showConcept(id) {
    conceptId = id;
    renderConcepts();
  }

  function updateExplanation(target) {
    currentTarget = target || null;
    renderExplanation();
  }

  function setSync(active) {
    renderSync(active);
  }

  function init(payload) {
    data = payload || {};
    var concepts = data.concepts || [];
    var firstReal = concepts.filter(function (c) { return !c.reserved; })[0];
    conceptId = firstReal ? firstReal.id : (concepts[0] && concepts[0].id) || null;
    renderConcepts();
    renderExplanation();
    renderSync(null);
    return { ok: true, experiments: (data.experiments || []).length };
  }

  window.HarmonyLab = {
    init: init,
    takeLaunch: takeLaunch,
    updateExplanation: updateExplanation,
    setSync: setSync,
    showConcept: showConcept,
    // exposed for the headless test
    _experimentsFor: experimentsFor,
    _explanationModel: explanationModel,
    _syncChips: syncChips,
  };
})();
