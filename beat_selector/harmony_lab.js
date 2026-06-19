/*
 * Music Theory Laboratory -- left-panel web UI controller.
 *
 * Loaded by beat_selector/harmony_lab.html inside a QWebEngineView (the LEFT
 * panel of run_harmony_lab_demo.py's three-pane workspace). It renders the
 * learning workspace's left column:
 *
 *   A. Concept Catalogue   -- concepts grouped, each with a one-line summary and
 *                             its experiments (click -> launch).
 *   B. Concept Theory      -- a rich, collapsible theory explanation of the
 *                             selected concept (from harmony.lab_explanations,
 *                             embedded per-concept in the catalogue payload).
 *   C. Example Explanation -- a dynamically generated explanation of the selected
 *                             experiment (the host pushes it after compiling).
 *   + a live "Now playing" guide for the trainer's current chord, and an Atlas
 *     sync strip.
 *
 * It deliberately does NOT touch MIDI or the score: the middle pane is the
 * existing ScoreViewBeats + harmony_trainer.js. The host bridges everything via
 * runJavaScript polling (no QWebChannel), exactly like the Atlas/Circle panels.
 *
 * Host-facing API (stable):
 *   HarmonyLab.init(data)                  -> render the workspace; {ok, experiments}
 *   HarmonyLab.takeLaunch()                -> dequeue a clicked LabExperimentSpec
 *   HarmonyLab.updateExplanation(target)   -> live guide for the current chord
 *   HarmonyLab.setExperimentExplanation(e) -> render the Example Explanation (C)
 *   HarmonyLab.setSync(active)             -> Atlas sync strip
 *   HarmonyLab.showConcept(id)             -> switch the selected concept
 *
 * All stateful/derivation logic is decoupled from the DOM so it is unit-testable
 * headlessly under Node (see tests/harmony_lab_node_test.js).
 */
(function () {
  "use strict";

  // -- module state ---------------------------------------------------------
  var data = null;
  var conceptId = null;                 // currently selected concept section
  var launchQueue = [];                 // clicked specs the host will pick up
  var currentTarget = null;             // last target pushed by the host
  var experimentExplanation = null;     // last Example Explanation (C) pushed
  var collapsed = {};                   // collapsible section open/closed state

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

  // The concept catalogue entry for a selector id.
  function conceptEntry(id) {
    return ((data && data.concepts) || []).filter(function (c) {
      return c.id === id;
    })[0] || null;
  }

  // The display model for the live "Now playing" guide (decoupled from the DOM).
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

  // -- collapsible section --------------------------------------------------
  function section(key, title, bodyNodes, startOpen) {
    if (collapsed[key] === undefined) collapsed[key] = !startOpen;
    var open = !collapsed[key];
    var head = el("div", {
      class: "labSecHead" + (open ? " open" : ""),
      onClick: function () { collapsed[key] = !collapsed[key]; rerenderActive(); },
    }, [ (open ? "▾ " : "▸ ") + title ]);
    var sec = el("div", { class: "labSec" + (open ? "" : " collapsed") }, [head]);
    if (open) {
      var body = el("div", { class: "labSecBody" }, []);
      (bodyNodes || []).forEach(function (n) { if (n) body.appendChild(n); });
      sec.appendChild(body);
    }
    return sec;
  }

  function bullets(items) {
    var ul = el("ul", { class: "labBullets" }, []);
    (items || []).forEach(function (it) { ul.appendChild(el("li", { text: it })); });
    return ul;
  }

  function paragraph(textStr, cls) {
    return el("div", { class: cls || "labPara", text: textStr });
  }

  // -- A. concept catalogue -------------------------------------------------
  function renderConcepts() {
    var nav = dollar("labConcepts");
    if (!nav) return;
    clear(nav);
    nav.appendChild(el("div", { class: "labPanelTitle", text: "Concept catalogue" }));
    (data.concepts || []).forEach(function (c) {
      var experiments = experimentsFor(c.id);
      var sec = el("div", { class: "labConcept" + (c.id === conceptId ? " active" : "") });
      var head = el("div", {
        class: "labConceptHead" + (c.reserved ? " reserved" : ""),
        onClick: function () { if (!c.reserved) showConcept(c.id); },
      }, [c.label + (c.reserved ? "  (reserved)" : "  (" + experiments.length + ")")]);
      sec.appendChild(head);
      if (c.detail) sec.appendChild(el("div", { class: "labConceptDetail", text: c.detail }));
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
        sec.appendChild(list);
      }
      nav.appendChild(sec);
    });
  }

  function flash(expId) {
    var hint = dollar("labLaunchHint");
    if (hint) hint.textContent = "Launching: " + expId;
  }

  // -- B. concept theory ----------------------------------------------------
  function renderConceptTheory() {
    var pane = dollar("labConceptTheory");
    if (!pane) return;
    clear(pane);
    var c = conceptEntry(conceptId);
    var ex = c && c.explanation;
    if (!ex) {
      pane.appendChild(el("div", { class: "labPanelTitle", text: "Concept theory" }));
      pane.appendChild(el("div", { class: "labPlaceholder",
        text: "Select a concept to read its theory." }));
      return;
    }
    pane.appendChild(el("div", { class: "labPanelTitle", text: ex.title || "Concept theory" }));
    if (ex.short_definition) {
      pane.appendChild(paragraph(ex.short_definition, "labLede"));
    }
    pane.appendChild(section("th_core", "Core idea",
      [paragraph(ex.core_idea)], true));
    pane.appendChild(section("th_listen", "What to listen for",
      [bullets(ex.what_to_listen_for)], true));
    pane.appendChild(section("th_play", "What to play",
      [bullets(ex.what_to_play)], false));
    if (ex.theory_terms && ex.theory_terms.length) {
      pane.appendChild(section("th_terms", "Theory terms",
        [el("div", { class: "labChips" }, ex.theory_terms.map(function (term) {
          return el("span", { class: "labTermChip", text: term });
        }))], false));
    }
    pane.appendChild(section("th_atlas", "Atlas connections",
      [bullets(ex.atlas_connections)], false));
    pane.appendChild(section("th_misc", "Common misconceptions",
      [bullets(ex.common_misconceptions)], false));
    pane.appendChild(section("th_next", "Next steps",
      [bullets(ex.next_steps)], false));
  }

  // -- C. example explanation (from the compiled experiment) ----------------
  function renderExample() {
    var pane = dollar("labExample");
    if (!pane) return;
    clear(pane);
    pane.appendChild(el("div", { class: "labPanelTitle", text: "Example explanation" }));
    var e = experimentExplanation;
    if (!e) {
      pane.appendChild(el("div", { class: "labPlaceholder",
        text: "Pick an experiment above — its concrete musical detail appears here." }));
      return;
    }
    pane.appendChild(el("div", { class: "labExHeading",
      text: e.title || "" }));
    if (e.conceptLabel) {
      pane.appendChild(el("div", { class: "labExSub", text: e.conceptLabel }));
    }
    if (e.summary) pane.appendChild(paragraph(e.summary, "labLede"));

    (e.facts || []).forEach(function (f) {
      pane.appendChild(el("div", { class: "labRow" }, [
        el("span", { class: "labLbl", text: f.label }),
        el("span", { class: "labVal", text: Array.isArray(f.value) ? f.value.join(", ") : f.value }),
      ]));
    });

    if (e.invariants && e.invariants.length) {
      pane.appendChild(section("ex_inv", "What stays invariant",
        [bullets(e.invariants)], true));
    }
    if (e.changes && e.changes.length) {
      pane.appendChild(section("ex_chg", "What changes",
        [bullets(e.changes)], true));
    }
    if (e.sections && e.sections.length) {
      var detail = e.sections.map(function (s) {
        return el("div", { class: "labDetailItem" }, [
          el("div", { class: "labDetailTitle", text: s.title }),
          bullets(s.lines),
        ]);
      });
      pane.appendChild(section("ex_detail", "Step-by-step detail", detail, false));
    }
    if (e.practice && e.practice.length) {
      pane.appendChild(section("ex_practice", "How to practise",
        [bullets(e.practice)], true));
    }
  }

  // -- live "Now playing" guide (current chord/measure) ---------------------
  function renderExplanation() {
    var pane = dollar("labExplain");
    if (!pane) return;
    var model = explanationModel(currentTarget);
    if (!model) {
      pane.innerHTML = '<div class="labPanelTitle">Now playing</div>'
        + '<div class="labPlaceholder">Pick an experiment, then play '
        + 'along — the current chord is explained here.</div>';
      return;
    }
    var html = '<div class="labPanelTitle">Now playing</div>';
    html += '<div class="labExpHeading">' + esc(model.heading) + "</div>";
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

  // -- re-render the collapsible-bearing panes (called on toggle) -----------
  function rerenderActive() {
    renderConceptTheory();
    renderExample();
  }

  // -- public API -----------------------------------------------------------
  function showConcept(id) {
    conceptId = id;
    renderConcepts();
    renderConceptTheory();
  }

  function updateExplanation(target) {
    currentTarget = target || null;
    renderExplanation();
  }

  function setExperimentExplanation(expl) {
    experimentExplanation = expl || null;
    renderExample();
  }

  function setSync(active) {
    renderSync(active);
  }

  function init(payload) {
    data = payload || {};
    collapsed = {};
    experimentExplanation = null;
    currentTarget = null;
    var concepts = data.concepts || [];
    var firstReal = concepts.filter(function (c) { return !c.reserved; })[0];
    conceptId = firstReal ? firstReal.id : (concepts[0] && concepts[0].id) || null;
    renderConcepts();
    renderConceptTheory();
    renderExample();
    renderExplanation();
    renderSync(null);
    return { ok: true, experiments: (data.experiments || []).length };
  }

  window.HarmonyLab = {
    init: init,
    takeLaunch: takeLaunch,
    updateExplanation: updateExplanation,
    setExperimentExplanation: setExperimentExplanation,
    setSync: setSync,
    showConcept: showConcept,
    // exposed for the headless test
    _experimentsFor: experimentsFor,
    _explanationModel: explanationModel,
    _syncChips: syncChips,
    _conceptEntry: conceptEntry,
  };
})();
