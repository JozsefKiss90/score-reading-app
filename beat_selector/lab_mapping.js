/*
 * Music Theory Laboratory -- "Current Mapping" panel (right-hand dashboard tab).
 *
 * Shows the live theoretical mapping of the trainer's current measure: the lab
 * concept, experiment title, measure number, key, scale, Roman numeral, chord
 * symbol, chord tones, the concept-specific fields (inversion / cadence / motive
 * / polyphony), the precomputed Atlas node ids, and the related Atlas edges.
 *
 * It renders the payload built by harmony.lab_explanations.get_measure_explanation
 * (or .mapping_from_target) -- it re-derives no theory, only presents the
 * Python-derived mapping the host pushes on every sync tick.
 *
 * Loaded by beat_selector/lab_mapping.html in a QWebEngineView; the host calls
 * LabMapping.update(mapping) on each current-target change.
 *
 * Public: window.LabMapping
 *   update(mapping) -> render the current mapping; returns {ok}
 *   _rows(mapping)  -> the flat label/value rows (for the headless test)
 */
(function () {
  "use strict";

  function dollar(id) { return document.getElementById(id); }

  function el(tag, props, children) {
    var node = document.createElement(tag);
    props = props || {};
    Object.keys(props).forEach(function (k) {
      if (k === "class") node.className = props[k];
      else if (k === "text") node.textContent = props[k];
      else if (k === "html") node.innerHTML = props[k];
      else if (node.setAttribute) node.setAttribute(k, props[k]);
    });
    (children || []).forEach(function (c) {
      if (c == null) return;
      node.appendChild(typeof c === "string"
        ? (function () { var s = document.createElement("span"); s.textContent = c; return s; })()
        : c);
    });
    return node;
  }

  function join(v) { return Array.isArray(v) ? v.join("–") : v; }

  // Pure: the flat label/value rows of a mapping (also used by the test).
  function rows(mp) {
    if (!mp) return [];
    var out = [];
    function add(label, value) {
      if (value == null || value === "" ||
          (Array.isArray(value) && value.length === 0)) return;
      out.push({ label: label, value: join(value) });
    }
    add("Concept", mp.conceptLabel || mp.concept);
    add("Experiment", mp.experimentTitle);
    add("Measure", mp.measureNumber);
    add("Key", mp.key + (mp.modeWord ? " (" + mp.modeWord + ")" : ""));
    add("Scale", mp.scale);
    add("Roman numeral", mp.roman);
    add("Chord symbol", mp.chordSymbol);
    add("Chord tones", mp.tones);
    add("Function", mp.function);
    add("Interval layer", mp.intervalLayer);

    if (mp.inversion) {
      add("Inversion", mp.inversion.label +
        (mp.inversion.figuredBass ? "  " + mp.inversion.figuredBass : ""));
      add("Bass", mp.inversion.bass);
      add("Slash chord", mp.inversion.slash);
    }
    if (mp.cadence) {
      add("Bass motion", mp.cadence.bassMotion);
      add("Common tones", mp.cadence.commonTones);
      add("Tendency tones", mp.cadence.tendencyTones);
      add("Cadence type", mp.cadence.cadenceType);
      if (mp.cadence.voices && mp.cadence.voices.length) {
        add("Voices", mp.cadence.voices.map(function (v) { return v[0] + " " + v[1]; }));
      }
    }
    if (mp.motive) {
      add("Motive", mp.motive.label);
      add("Degrees", mp.motive.degrees);
      add("Notes", mp.motive.notes);
    }
    if (mp.polyphony) {
      add("Implies", mp.polyphony.impliedChord +
        (mp.polyphony.impliedRoman ? " (" + mp.polyphony.impliedRoman + ")" : ""));
      if (mp.polyphony.voices && mp.polyphony.voices.length) {
        add("Voices", mp.polyphony.voices.map(function (v) { return v[0] + " " + v[1]; }));
      }
    }
    return out;
  }

  function nodeIdRows(ids) {
    ids = ids || {};
    return Object.keys(ids).filter(function (k) { return ids[k]; })
      .map(function (k) { return { label: k, value: ids[k] }; });
  }

  function update(mapping) {
    var root = dollar("mapRoot") || document.body;
    root.innerHTML = "";
    root.appendChild(el("div", { class: "mapTitle", text: "Current mapping" }));
    if (!mapping) {
      root.appendChild(el("div", { class: "mapHint",
        text: "Play an experiment — the current measure's mapping appears here." }));
      return { ok: true };
    }
    rows(mapping).forEach(function (r) {
      root.appendChild(el("div", { class: "mapRow" }, [
        el("span", { class: "mapLbl", text: r.label }),
        el("span", { class: "mapVal", text: r.value }),
      ]));
    });

    var ids = nodeIdRows(mapping.atlasNodeIds);
    if (ids.length) {
      root.appendChild(el("div", { class: "mapSubTitle", text: "Atlas nodes" }));
      ids.forEach(function (r) {
        root.appendChild(el("div", { class: "mapRow" }, [
          el("span", { class: "mapLbl", text: r.label }),
          el("span", { class: "mapNode", text: r.value }),
        ]));
      });
    }

    var edges = mapping.atlasEdges || [];
    if (edges.length) {
      root.appendChild(el("div", { class: "mapSubTitle",
        text: "Related Atlas edges (" + edges.length + ")" }));
      var list = el("div", { class: "mapEdges" }, []);
      edges.slice(0, 40).forEach(function (e) {
        list.appendChild(el("div", { class: "mapEdge",
          text: e.source + "  —" + e.relation + "→  " + e.target }));
      });
      root.appendChild(list);
    }
    return { ok: true };
  }

  window.LabMapping = { update: update, _rows: rows };
})();
