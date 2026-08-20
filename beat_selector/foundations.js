/*
 * Chord Progression Foundations -- the beginner C/G/F lesson page controller.
 *
 * Loaded by beat_selector/foundations.html inside a QWebEngineView (a LEFT tab
 * of run_harmony_lab_demo.py, beside the curriculum browser).  Renders the
 * guided collection built by harmony.progression_foundations: four Roman
 * transposition families (A-D), each selectable in C, G and F major.
 * Selecting an example queues its LabExperimentSpec for the host (the score,
 * MIDI playback and validation are the existing trainer pipeline) and shows
 * the example's DERIVED chord table -- one row per score measure, straight
 * from the compiled trainer targets, never hand-authored here.
 *
 * Progressive disclosure: the table starts at Position / Key / Chord symbol;
 * the reveal toggle (aria-expanded) adds the Roman numerals and the
 * explanatory columns.  Nothing is communicated by colour alone.
 *
 * Host-facing API (stable, mirrors the other panels' polling bridges):
 *   Foundations.init(data)              -> render; {ok, groups, examples}
 *   Foundations.takeLaunch()            -> dequeue a selected LabExperimentSpec
 *   Foundations.takeAtlasSelection()    -> dequeue clicked Atlas node-id lists
 *   Foundations.selectExample(id)       -> select + queue an example by id
 *   Foundations.toggleReveal()          -> flip the analysis columns
 *   Foundations.setCurrent(nodeId, tgt) -> live active-measure row highlight
 *
 * Derivation logic is decoupled from the DOM (the _xxx exports) so it is
 * unit-testable headlessly under Node (see tests/foundations_node_test.js).
 */
(function () {
  "use strict";

  // -- module state ---------------------------------------------------------
  var data = null;
  var examplesById = {};         // exampleId -> example payload
  var groupOf = {};              // exampleId -> group payload
  var selectedId = null;         // selected exampleId
  var revealed = false;          // analysis columns shown?
  var focusRow = 0;              // keyboard-focused table row index
  var activeAbs = null;          // live 0-based measure from the host, or null
  var launchQueue = [];          // LabExperimentSpec dicts (host picks up)
  var atlasQueue = [];           // lists of Atlas node ids (host picks up)

  // -- tiny DOM helpers (tolerant of the Node test's stubbed document) ------
  function dollar(id) { return document.getElementById(id); }

  function el(tag, props, children) {
    var node = document.createElement(tag);
    props = props || {};
    Object.keys(props).forEach(function (k) {
      if (k === "class") { node.className = props[k]; }
      else if (k === "text") { node.textContent = props[k]; }
      else if (k === "onClick") { node.addEventListener("click", props[k]); }
      else if (k === "onKeyDown") { node.addEventListener("keydown", props[k]); }
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

  // ========================================================================
  // Pure models (exported for the headless test)
  // ========================================================================

  //: The table columns.  `base` columns show before the reveal; the rest are
  //: the Roman numerals + explanatory columns behind the toggle (plan: show
  //: key, score and chord symbols first).  `cell(row)` returns plain text;
  //: chips/links render their own cells (kind !== "text").
  var COLUMNS = [
    { key: "position", label: "Position", base: true, kind: "rowhead",
      cell: function (r) { return String(r.position); } },
    { key: "key", label: "Key", base: true, kind: "text",
      cell: function (r) { return r.key || ""; } },
    { key: "chordSymbol", label: "Chord symbol", base: true, kind: "text",
      cell: function (r) { return r.chordSymbolDisplay || r.chordSymbol || ""; } },
    { key: "scale", label: "Scale", base: false, kind: "text",
      cell: function (r) { return (r.scaleDisplay || r.scale || []).join(" "); } },
    { key: "degree", label: "Degree", base: false, kind: "text",
      cell: function (r) { return r.degree == null ? "" : String(r.degree); } },
    { key: "roman", label: "Roman numeral", base: false, kind: "text",
      cell: function (r) { return r.roman || ""; } },
    { key: "chordNotes", label: "Chord notes", base: false, kind: "text",
      cell: function (r) { return (r.chordNotesDisplay || r.chordNotes || []).join("–"); } },
    { key: "quality", label: "Quality", base: false, kind: "text",
      cell: function (r) { return r.qualityLabel || r.quality || ""; } },
    { key: "function", label: "Function", base: false, kind: "text",
      cell: function (r) {
        var f = r["function"] || "";
        return r.functionGloss ? f + " (" + r.functionGloss + ")" : f;
      } },
    { key: "chordSize", label: "Chord size", base: false, kind: "text",
      cell: function (r) { return r.chordSize || ""; } },
    { key: "atlas", label: "Atlas mapping", base: false, kind: "atlas",
      cell: function (r) { return (r.atlasNodes || []).join(" "); } },
    { key: "lessons", label: "Related lesson", base: false, kind: "lessons",
      cell: function (r) { return (r.relatedLessons || []).join(" "); } },
  ];

  function visibleColumns(isRevealed) {
    return COLUMNS.filter(function (c) { return isRevealed || c.base; });
  }

  //: The rendered-table model: visible column labels + one cell-text row per
  //: table row.  What the Node test asserts on instead of markup.
  function tableModel(example, isRevealed) {
    var cols = visibleColumns(isRevealed);
    return {
      columns: cols.map(function (c) { return c.label; }),
      rows: (example.table || []).map(function (r) {
        return cols.map(function (c) { return c.cell(r); });
      }),
    };
  }

  //: The group model: per key, the chord-symbol row of the shared Roman
  //: pattern -- the visible "same pattern in another key" comparison.
  function transpositionStrip(group) {
    return (group.examples || []).map(function (ex) {
      return {
        exampleId: ex.exampleId,
        key: ex.keyDisplay || ex.key,
        chords: (ex.chordSymbolsDisplay || ex.chordSymbols || []).join("–"),
      };
    });
  }

  function model() {
    if (!data) return { groups: 0, examples: 0 };
    var n = 0;
    (data.groups || []).forEach(function (g) { n += (g.examples || []).length; });
    return { groups: (data.groups || []).length, examples: n };
  }

  // ========================================================================
  // Rendering
  // ========================================================================

  function renderIntro() {
    var box = dollar("fnIntro");
    if (!box) return;
    clear(box);
    box.appendChild(el("div", { class: "fnTitle", text: data.title || "" }));
    (data.intro || []).forEach(function (p) {
      box.appendChild(el("p", { class: "fnPara", text: p }));
    });
  }

  function renderGroups() {
    var box = dollar("fnGroups");
    if (!box) return;
    clear(box);
    box.appendChild(el("div", { class: "fnSecTitle", text: "The four example groups" }));
    (data.groups || []).forEach(function (g) {
      var sec = el("section", { class: "fnGroup",
                                "aria-label": "Group " + g.letter + ": " + g.title });
      sec.appendChild(el("div", {}, [
        el("span", { class: "fnTitle", text: g.letter + " · " + g.title + " — " }),
        el("span", { class: "fnRoman", text: g.romanLabel || "" }),
      ]));
      sec.appendChild(el("div", { class: "fnPara", text: g.blurb || "" }));

      // The same-pattern-in-three-keys strip (transposition made visible).
      var strip = transpositionStrip(g);
      var table = el("table", { class: "fnTransposed" });
      var tb = el("tbody", {});
      strip.forEach(function (s) {
        tb.appendChild(el("tr", {}, [
          el("th", { scope: "row", text: s.key }),
          el("td", { text: s.chords }),
        ]));
      });
      table.appendChild(tb);
      sec.appendChild(table);

      // The C / G / F selection buttons.
      var keysRow = el("div", { class: "fnKeys", role: "group",
                                "aria-label": "Choose a key for group " + g.letter });
      (g.examples || []).forEach(function (ex) {
        var btn = el("button", {
          class: "fnKeyBtn", type: "button",
          "aria-pressed": ex.exampleId === selectedId ? "true" : "false",
          dataset: { id: ex.exampleId },
          title: ex.reused
            ? "Shares its drill with an existing curriculum exercise"
            : ex.title,
          onClick: function () { api.selectExample(ex.exampleId); },
        }, [ex.label + " · " + (ex.keyDisplay || ex.key)]);
        keysRow.appendChild(btn);
        if (ex.reused) {
          keysRow.appendChild(el("span", { class: "fnReusedTag",
                                           text: "shared drill" }));
        }
      });
      sec.appendChild(keysRow);
      box.appendChild(sec);
    });
  }

  function rowId(i) { return "fnRow_" + i; }

  function renderDetail() {
    var box = dollar("fnDetail");
    if (!box) return;
    clear(box);
    var ex = examplesById[selectedId];
    if (!ex) {
      box.appendChild(el("div", { class: "fnPlaceholder", text: "Pick an example above." }));
      return;
    }
    box.appendChild(el("div", { class: "fnTitle", text: ex.title || ex.exampleId }));
    box.appendChild(el("div", { class: "fnSub",
      text: (ex.keyDisplay || ex.key) + " — scale: "
            + (ex.scaleDisplay || ex.scale || []).join(" ")
            + ". One chord per bar; play along on MIDI." }));

    var btn = el("button", {
      id: "fnReveal", type: "button",
      "aria-expanded": revealed ? "true" : "false",
      "aria-controls": "fnTableWrap",
      onClick: function () { api.toggleReveal(); },
    }, [revealed ? "Hide Roman numerals & analysis"
                 : "Show Roman numerals & analysis"]);
    box.appendChild(btn);

    var wrap = el("div", { id: "fnTableWrap" });
    var table = el("table", { id: "fnTable" });
    table.appendChild(el("caption", {
      text: "One row per score measure, derived from the compiled exercise "
            + "targets. Use the arrow keys to move between rows." }));
    var cols = visibleColumns(revealed);
    var thead = el("thead", {});
    var hrow = el("tr", {});
    cols.forEach(function (c) {
      hrow.appendChild(el("th", { scope: "col", text: c.label }));
    });
    thead.appendChild(hrow);
    table.appendChild(thead);

    var tbody = el("tbody", {});
    (ex.table || []).forEach(function (r, i) {
      var isActive = activeAbs != null && r.measureNumber === activeAbs + 1;
      var tr = el("tr", {
        id: rowId(i),
        class: isActive ? "fnRowActive" : "",
        tabindex: i === focusRow ? "0" : "-1",
        dataset: { abs: String(r.measureNumber - 1) },
        onKeyDown: onRowKeyDown,
      });
      if (isActive && tr.setAttribute) tr.setAttribute("aria-current", "true");
      cols.forEach(function (c) {
        if (c.kind === "rowhead") {
          tr.appendChild(el("th", { scope: "row", text: c.cell(r) }));
        } else if (c.kind === "atlas") {
          var td = el("td", {});
          (r.atlasNodes || []).forEach(function (nid) {
            td.appendChild(el("button", {
              class: "fnChip", type: "button", title: nid,
              "aria-label": "Highlight " + nid + " in the Harmony Atlas",
              dataset: { atlas: nid },
              onClick: (function (nodes) {
                return function () { atlasQueue.push(nodes); };
              })((r.atlasNodes || []).slice()),
            }, [nid.split(":").slice(0, 2).join(":")]));
          });
          tr.appendChild(td);
        } else if (c.kind === "lessons") {
          var td2 = el("td", {});
          (r.relatedLessons || []).forEach(function (lid) {
            td2.appendChild(el("span", { class: "fnLesson", text: lid }));
          });
          tr.appendChild(td2);
        } else {
          tr.appendChild(el("td", { text: c.cell(r) }));
        }
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    box.appendChild(wrap);
  }

  function renderTransposition() {
    var box = dollar("fnTransposition");
    if (!box) return;
    clear(box);
    var t = data.transposition || {};
    box.appendChild(el("div", { class: "fnSecTitle",
      text: "Same pattern in another key" }));
    box.appendChild(el("div", { class: "fnPara", text: t.note || "" }));
    var flex = el("div", { class: "fnInvariant" });
    [["Stays the same", t.invariant || []],
     ["Changes", t.changing || []]].forEach(function (pair) {
      var d = el("div", {});
      d.appendChild(el("div", { class: "fnSecTitle", text: pair[0] }));
      var ul = el("ul", {});
      pair[1].forEach(function (item) {
        ul.appendChild(el("li", { text: item }));
      });
      d.appendChild(ul);
      flex.appendChild(d);
    });
    box.appendChild(flex);
  }

  function renderAll() {
    renderIntro();
    renderGroups();
    renderDetail();
    renderTransposition();
  }

  // ========================================================================
  // Keyboard navigation (roving tabindex over the table rows)
  // ========================================================================

  function keyMove(delta) {
    var ex = examplesById[selectedId];
    if (!ex || !(ex.table || []).length) return focusRow;
    var n = ex.table.length;
    focusRow = Math.max(0, Math.min(n - 1, focusRow + delta));
    return focusRow;
  }

  function onRowKeyDown(e) {
    var key = (e && e.key) || "";
    if (key !== "ArrowDown" && key !== "ArrowUp") return;
    if (e && e.preventDefault) e.preventDefault();
    keyMove(key === "ArrowDown" ? 1 : -1);
    renderDetail();
    var row = dollar(rowId(focusRow));
    if (row && row.focus) row.focus();
  }

  // ========================================================================
  // Public API
  // ========================================================================

  var api = {
    init: function (payload) {
      data = payload || {};
      examplesById = {};
      groupOf = {};
      (data.groups || []).forEach(function (g) {
        (g.examples || []).forEach(function (ex) {
          examplesById[ex.exampleId] = ex;
          groupOf[ex.exampleId] = g;
        });
      });
      selectedId = null;
      revealed = false;
      focusRow = 0;
      activeAbs = null;
      launchQueue = [];
      atlasQueue = [];
      renderAll();
      var m = model();
      return { ok: true, groups: m.groups, examples: m.examples };
    },

    selectExample: function (exampleId) {
      var ex = examplesById[exampleId];
      if (!ex) return false;
      selectedId = exampleId;
      focusRow = 0;
      activeAbs = null;
      if (ex.labSpec) launchQueue.push(ex.labSpec);
      renderAll();
      return true;
    },

    toggleReveal: function () {
      revealed = !revealed;
      renderDetail();
      return revealed;
    },

    // Live sync from the host: highlight the table row of the trainer's
    // current measure -- only when the playing drill IS the selected example.
    setCurrent: function (nodeId, target) {
      var ex = examplesById[selectedId];
      if (!ex || !target || nodeId !== ex.curriculumNodeId) return;
      var abs = target.absMeasure;
      if (typeof abs !== "number" || abs === activeAbs) return;
      activeAbs = abs;
      renderDetail();
    },

    takeLaunch: function () { return launchQueue.shift() || null; },
    takeAtlasSelection: function () { return atlasQueue.shift() || null; },

    // -- exposed for the headless test -----------------------------------
    _model: model,
    _visibleColumns: visibleColumns,
    _tableModel: tableModel,
    _transpositionStrip: transpositionStrip,
    _selected: function () { return selectedId; },
    _revealed: function () { return revealed; },
    _activeAbs: function () { return activeAbs; },
    _keyMove: keyMove,
    _focusRow: function () { return focusRow; },
  };

  window.Foundations = api;
})();
