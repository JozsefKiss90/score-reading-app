/*
 * Interactive Harmony Atlas -- web UI controller.
 *
 * Loaded by beat_selector/atlas.html inside a QWebEngineView. It renders the
 * JSON model produced by harmony.atlas.Atlas.to_json() into the tabbed views
 * (Parts I-XI of the Atlas spec) and exposes a small, host-pollable API:
 *
 *   AtlasUI.init(data)            -> render everything; returns {ok, tabs}
 *   AtlasUI.showTab(id)           -> switch view
 *   AtlasUI.takeLaunch()          -> dequeue a clicked exercise spec (host polls)
 *   AtlasUI.setSync(active)       -> highlight the current key/degree/triad/... (Part VII)
 *   AtlasUI.hoverRelated(facets)  -> highlight related elements (Part I hover)
 *
 * All stateful logic is kept inspectable (launchQueue, activeIds, hover) and
 * decoupled from DOM querying, so it is unit-testable headlessly under Node
 * (see tests/atlas_node_test.js) exactly like beat_selector/harmony_trainer.js.
 *
 * It never re-derives theory: every launchable exercise is a HarmonyExerciseSpec
 * dict that came straight from the Python model.
 */
(function () {
  "use strict";

  // -- module state ---------------------------------------------------------
  var data = null;
  var tabId = null;
  var modeByTab = {};                 // per-tab major/natural_minor toggle
  var launchQueue = [];               // clicked specs the host will pick up
  var activeIds = new Set();          // current sync highlight (Part VII)
  var hoverIds = new Set();           // current hover highlight (Part I)
  var relatables = [];                // [{el, facets}] registered each render

  var TABS = [
    { id: "global", label: "Global map", render: renderGlobal },
    { id: "matrix", label: "Transposition", render: renderMatrix },
    { id: "quality", label: "Quality", render: renderQuality },
    { id: "function", label: "Function", render: renderFunction },
    { id: "layers", label: "Interval layers", render: renderLayers },
    { id: "cadences", label: "Cadences", render: renderCadences },
    { id: "path", label: "Learning path", render: renderPath },
    { id: "progress", label: "Progress", render: renderProgress },
    { id: "graph", label: "Graph", render: renderGraph },
  ];

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
      else if (k === "onHover") {
        node.addEventListener("mouseenter", props[k]);
        node.addEventListener("mouseleave", clearHover);
      } else if (k === "dataset") {
        var ds = props[k];
        Object.keys(ds).forEach(function (d) {
          if (node.dataset) node.dataset[d] = ds[d];
        });
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

  function clearChildren(node) { if (node) node.innerHTML = ""; }

  // -- launch queue (host integration) --------------------------------------
  function launch(spec) {
    if (!spec) return;
    launchQueue.push(spec);
  }
  function takeLaunch() { return launchQueue.length ? launchQueue.shift() : null; }

  // -- relatable registry: powers both sync (Part VII) and hover (Part I) ----
  // facets: {node, key, mode, degree(roman), quality, layer, function}
  function relate(node, facets) {
    if (!node) return node;
    relatables.push({ el: node, facets: facets || {} });
    return node;
  }

  function _matchFacet(facets, want) {
    // want: an object of facet->value (any one match counts), or a node id list.
    if (want.nodeIds && want.nodeIds.indexOf(facets.node) !== -1) return true;
    if (want.quality && facets.quality === want.quality) return true;
    if (want.layer && facets.layer === want.layer) return true;
    if (want.fn && facets["function"] === want.fn) return true;
    if (want.degree && facets.degree === want.degree && facets.mode === want.mode) return true;
    if (want.key && facets.key === want.key && facets.mode === want.mode) return true;
    // set membership (used by cadence hover: many degrees / functions at once)
    if (want.fns && want.fns.indexOf(facets["function"]) !== -1) return true;
    if (want.degrees && facets.mode === want.mode &&
        want.degrees.indexOf(facets.degree) !== -1) return true;
    return false;
  }

  function _applyHighlight(cls, want, bag) {
    bag.clear();
    relatables.forEach(function (r) {
      var on = _matchFacet(r.facets, want);
      if (r.el && r.el.classList) {
        if (on) r.el.classList.add(cls); else r.el.classList.remove(cls);
      }
      if (on && r.facets.node) bag.add(r.facets.node);
    });
  }

  // -- Part VII: sync ------------------------------------------------------
  // active: {scale, degree, triad, quality, layer, function} of node ids
  function setSync(active) {
    active = active || {};
    var ids = Object.keys(active).map(function (k) { return active[k]; })
      .filter(Boolean);
    var want = { nodeIds: ids };
    // Derive facets from the structured ids so we also light up matrix cells,
    // quality chips, etc. that share the current quality/layer/function/key.
    parseIds(ids, want);
    _applyHighlight("sync-on", want, activeIds);
  }

  function parseIds(ids, want) {
    ids.forEach(function (id) {
      var p = String(id).split(":");
      if (p[0] === "quality") want.quality = p[1];
      else if (p[0] === "layer") want.layer = id.slice("layer:".length);
      else if (p[0] === "function") { want.mode = p[1]; want.fn = p.slice(2).join(":"); }
      else if (p[0] === "degree") { want.mode = p[1]; want.degree = p.slice(2).join(":"); }
      else if (p[0] === "scale") { want.mode = p[2]; want.key = p[1]; }
      else if (p[0] === "triad") { want.key = p[1]; want.mode = p[2]; }
    });
  }

  function syncState() { return Array.from(activeIds); }

  // -- Part I: hover relationships -----------------------------------------
  function hoverRelated(facets) {
    facets = facets || {};
    var want = {
      quality: facets.quality, layer: facets.layer, fn: facets["function"],
      degree: facets.degree, mode: facets.mode, key: facets.key,
      fns: facets.fns, degrees: facets.degrees,
    };
    _applyHighlight("hover-on", want, hoverIds);
  }
  function clearHover() { _applyHighlight("hover-on", {}, hoverIds); }
  function hoverState() { return Array.from(hoverIds); }

  // -- tab chrome ----------------------------------------------------------
  function showTab(id) {
    tabId = id;
    var bar = dollar("atlasTabs");
    if (bar && bar.querySelectorAll) {
      var btns = bar.querySelectorAll(".atlasTab");
      for (var i = 0; i < btns.length; i++) {
        var b = btns[i];
        if (b.classList) b.classList.toggle("active", b.dataset && b.dataset.tab === id);
      }
    }
    var tab = TABS.filter(function (t) { return t.id === id; })[0];
    var content = dollar("atlasContent");
    clearChildren(content);
    relatables = [];
    if (tab && content) tab.render(content);
    return id;
  }

  function buildTabs() {
    var bar = dollar("atlasTabs");
    if (!bar) return;
    clearChildren(bar);
    TABS.forEach(function (t) {
      bar.appendChild(el("button", {
        class: "atlasTab", text: t.label, dataset: { tab: t.id },
        onClick: function () { showTab(t.id); },
      }));
    });
  }

  function modeOf(tab) { return modeByTab[tab] || "major"; }

  function modeToggle(tab) {
    function mk(mode, label) {
      return el("button", {
        class: "click" + (modeOf(tab) === mode ? " active" : ""), text: label,
        onClick: function () { modeByTab[tab] = mode; showTab(tab); },
      });
    }
    return el("div", { class: "modeToggle" },
      [mk("major", "Major"), mk("natural_minor", "Natural minor")]);
  }

  function qcls(q) { return "q-" + q; }
  function fcls(f) { return "f-" + f; }

  // -- Part I: global diatonic map -----------------------------------------
  function renderGlobal(root) {
    var mode = modeOf("global");
    root.appendChild(el("div", { class: "viewTitle", text: "Global diatonic map" }));
    root.appendChild(el("div", { class: "viewHint",
      text: "The invariant degree pattern — identical in every key. Hover a row to relate it; click to drill that degree across all keys." }));
    root.appendChild(modeToggle("global"));

    var rows = (data.globalMap[mode] || []);
    var table = el("table", { class: "atlas" });
    table.appendChild(el("tr", {}, [
      el("th", { text: "Degree" }), el("th", { text: "Quality" }),
      el("th", { text: "Interval layer" }), el("th", { text: "Function" }),
      el("th", { text: "Scale degree" }),
    ]));
    rows.forEach(function (r) {
      var facets = {
        node: r.nodeId, mode: mode, degree: r.roman,
        quality: r.quality, layer: r.intervalLayer, "function": r.functionLabel,
      };
      var tr = relate(el("tr", {
        class: "click",
        onClick: function () { launch(r.spec); },
        onHover: function () { hoverRelated(facets); },
        dataset: { node: r.nodeId },
      }, [
        el("td", { class: "rn", text: r.roman }),
        el("td", { class: qcls(r.quality), text: r.quality }),
        el("td", { text: r.intervalLayer }),
        el("td", { class: fcls(r.functionLabel), text: r.functionLabel }),
        el("td", { text: r.scaleDegreeName }),
      ]), facets);
      table.appendChild(tr);
    });
    root.appendChild(table);
  }

  // -- Part II: transposition matrix ---------------------------------------
  function renderMatrix(root) {
    var mode = modeOf("matrix");
    var m = data.transpositionMatrix[mode];
    root.appendChild(el("div", { class: "viewTitle", text: "Horizontal transposition matrix" }));
    root.appendChild(el("div", { class: "viewHint",
      text: "Rows = scale degrees, columns = keys. Click a row to drill it across all keys, or a cell to practise that key." }));
    root.appendChild(modeToggle("matrix"));

    var wrap = el("div", { class: "matrixWrap" });
    var table = el("table", { class: "atlas" });
    var head = el("tr", {}, [el("th", { text: "Degree \\ Key" })]);
    m.keys.forEach(function (k) { head.appendChild(el("th", { text: k })); });
    table.appendChild(head);

    m.rows.forEach(function (row) {
      var tr = el("tr", {});
      var rh = relate(el("th", {
        class: "click rn", text: row.roman,
        onClick: function () { launch(row.rowSpec); },
        onHover: function () { hoverRelated({ degree: row.roman, mode: mode }); },
        dataset: { node: row.degreeNodeId },
      }, []), { node: row.degreeNodeId, degree: row.roman, mode: mode });
      tr.appendChild(rh);
      row.cells.forEach(function (c) {
        var facets = { node: c.nodeId, key: c.key, mode: mode,
                       degree: c.roman, layer: c.intervalLayer };
        var td = relate(el("td", {
          class: "cell click",
          onClick: function () { launch(c.spec); },
          onHover: function () { hoverRelated({ degree: c.roman, mode: mode }); },
          dataset: { node: c.nodeId },
        }, [
          el("span", { class: "sym", text: c.chordSymbol }), " ",
          el("span", { class: "tones", text: (c.chordTones || []).join("–") }),
        ]), facets);
        tr.appendChild(td);
      });
      table.appendChild(tr);
    });
    wrap.appendChild(table);
    root.appendChild(wrap);
  }

  // -- Part III: quality matrix --------------------------------------------
  function renderQuality(root) {
    var mode = modeOf("quality");
    root.appendChild(el("div", { class: "viewTitle", text: "Quality matrix" }));
    root.appendChild(el("div", { class: "viewHint",
      text: "Every triad of each quality across all keys. Click a quality to drill it; click a key to practise that key." }));
    root.appendChild(modeToggle("quality"));

    (data.qualityMatrix[mode] || []).forEach(function (cat) {
      var card = el("div", { class: "card" });
      card.appendChild(relate(el("h3", {
        class: "click " + qcls(cat.quality),
        text: cat.quality + "  (" + cat.intervalLayer + ")",
        onClick: function () { launch(cat.spec); },
        onHover: function () { hoverRelated({ quality: cat.quality }); },
        dataset: { node: cat.qualityNodeId },
      }, []), { node: cat.qualityNodeId, quality: cat.quality, layer: cat.intervalLayer }));
      var chips = el("div", { class: "chips" });
      (cat.entries || []).forEach(function (e) {
        var keySpec = (data.keySpecs[mode] || {})[e.key];
        chips.appendChild(relate(el("span", {
          class: "chip", text: e.chordSymbol + " (" + e.key + ")",
          onClick: function () { launch(keySpec); },
          dataset: { node: e.nodeId },
        }, []), { node: e.nodeId, key: e.key, mode: mode, quality: cat.quality }));
      });
      card.appendChild(chips);
      root.appendChild(card);
    });
  }

  // -- Part IV: function map -----------------------------------------------
  function renderFunction(root) {
    var mode = modeOf("function");
    var fm = data.functionMap[mode];
    root.appendChild(el("div", { class: "viewTitle", text: "Function map" }));
    root.appendChild(el("div", { class: "viewHint",
      text: "Function stays invariant while chord names change. Click a cell to play that function's chords in that key." }));
    root.appendChild(modeToggle("function"));

    var wrap = el("div", { class: "matrixWrap" });
    var table = el("table", { class: "atlas" });
    var head = el("tr", {}, [el("th", { text: "Function \\ Key" })]);
    fm.keys.forEach(function (k) { head.appendChild(el("th", { text: k })); });
    table.appendChild(head);

    fm.rows.forEach(function (row) {
      var tr = el("tr", {});
      tr.appendChild(relate(el("th", {
        class: fcls(row.functionLabel),
        text: row.functionLabel + " (" + row.romans.join(" ") + ")",
        onHover: function () { hoverRelated({ fn: row.functionLabel, mode: mode }); },
        dataset: { node: row.functionNodeId },
      }, []), { node: row.functionNodeId, "function": row.functionLabel, mode: mode }));
      row.cells.forEach(function (c) {
        var label = (c.chords || []).map(function (x) { return x.chordSymbol; }).join(" ");
        tr.appendChild(relate(el("td", {
          class: "cell click", text: label,
          onClick: function () { launch(c.spec); },
          onHover: function () { hoverRelated({ fn: row.functionLabel, mode: mode }); },
          dataset: { node: row.functionNodeId, key: c.key },
        }, []), { node: row.functionNodeId, key: c.key, mode: mode,
                  "function": row.functionLabel }));
      });
      table.appendChild(tr);
    });
    wrap.appendChild(table);
    root.appendChild(wrap);
  }

  // -- Part V: interval-layer map ------------------------------------------
  function renderLayers(root) {
    root.appendChild(el("div", { class: "viewTitle", text: "Interval layer map" }));
    root.appendChild(el("div", { class: "viewHint",
      text: "A triad is two stacked thirds. Click a formula to generate a recognition drill." }));
    var grid = el("div", { class: "cardGrid" });
    (data.intervalLayerMap || []).forEach(function (L) {
      var card = relate(el("div", {
        class: "card" + (L.spec ? " click" : ""),
        onClick: function () { if (L.spec) launch(L.spec); },
        onHover: function () { hoverRelated({ layer: L.intervalLayer, quality: L.quality }); },
        dataset: { node: L.layerNodeId },
      }, [
        el("h3", { class: qcls(L.quality), text: L.intervalLayer }),
        el("div", { class: "meta", text: L.quality + (L.diatonic ? "" : " (non-diatonic)") }),
      ]), { node: L.layerNodeId, layer: L.intervalLayer, quality: L.quality });
      grid.appendChild(card);
    });
    root.appendChild(grid);
  }

  // -- Part VI: cadence map ------------------------------------------------
  function renderCadences(root) {
    root.appendChild(el("div", { class: "viewTitle", text: "Cadence map" }));
    root.appendChild(el("div", { class: "viewHint",
      text: "Canonical cadences: Roman numerals, function path, and the same progression transposed to every key. Click a card to play it." }));
    var grid = el("div", { class: "cardGrid" });
    (data.cadenceMap || []).forEach(function (cad) {
      var refChords = (cad.referenceChords || []).map(function (c) { return c.chordSymbol; }).join(" – ");
      var card = relate(el("div", {
        class: "card click", dataset: { node: cad.cadenceNodeId },
        onClick: function () { launch(cad.spec); },
        onHover: function () {
          hoverRelated({ mode: cad.mode, degrees: cad.tokens,
            fns: cad.functionPath || [] });
        },
      }, [
        el("h3", { text: cad.label + "  ·  " + cad.cadenceType }),
        el("div", { class: "meta", text: cad.tokens.join(" – ") + "   (" + (cad.mode === "major" ? "major" : "natural minor") + ")" }),
        el("div", { class: "meta", text: "Functions: " + (cad.functionPath || []).join(" → ") }),
        el("div", { class: "meta", text: "In " + cad.referenceChords[0].chordSymbol.replace(/m|°/g, "") + ": " + refChords }),
      ]), { node: cad.cadenceNodeId, mode: cad.mode });
      grid.appendChild(card);
    });
    root.appendChild(grid);
  }

  // -- Part XI: learning path ----------------------------------------------
  function renderPath(root) {
    root.appendChild(el("div", { class: "viewTitle", text: "Learning path" }));
    root.appendChild(el("div", { class: "viewHint",
      text: "Scales → Triads → Interval layers → Transposition → Functions → Cadences → Real music. The current exercise's level is highlighted during play." }));
    var wrap = el("div", { class: "path" });
    var steps = data.learningPath || [];
    steps.forEach(function (s, i) {
      wrap.appendChild(el("div", {
        class: "pathStep" + (AtlasUI._currentLevel === s.id ? " current" : ""),
        dataset: { level: s.id },
      }, [
        el("div", { class: "lvl", text: "Level " + s.level }),
        el("div", { html: "<b>" + esc(s.title) + "</b>" }),
        el("div", { class: "meta", text: s.detail }),
      ]));
      if (i < steps.length - 1) wrap.appendChild(el("div", { class: "pathArrow", text: "↓" }));
    });
    root.appendChild(wrap);
  }

  // -- Part IX: progress map -----------------------------------------------
  function renderProgress(root) {
    var p = data.progress || { categories: [], overallPercent: 0 };
    root.appendChild(el("div", { class: "viewTitle",
      text: "Progress — " + p.overallPercent + "% overall" }));
    root.appendChild(el("div", { class: "viewHint",
      text: "Completion by category (the host persists which exercises you finish). Click an item to launch it." }));
    (p.categories || []).forEach(function (cat) {
      var rowEl = el("div", { class: "progRow" }, [
        el("span", { class: "name", text: cat.category }),
        el("div", { class: "bar" }, [el("span", { dataset: { w: cat.percent } })]),
        el("span", { class: "pct", text: cat.completed + "/" + cat.total }),
      ]);
      // width is set as inline style after creation (kept simple/testable).
      try {
        var bar = rowEl.querySelector ? rowEl.querySelector(".bar > span") : null;
        if (bar && bar.style) bar.style.width = cat.percent + "%";
      } catch (e) { /* stubbed DOM */ }
      root.appendChild(rowEl);

      var grid = el("div", { class: "chips" });
      (cat.items || []).forEach(function (it) {
        grid.appendChild(el("span", {
          class: "chip", text: (it.done ? "✓ " : "□ ") + it.title,
          onClick: function () { launch(it.spec); },
        }, []));
      });
      root.appendChild(grid);
    });
  }

  // -- Part X: graph -------------------------------------------------------
  function renderGraph(root) {
    root.appendChild(el("div", { class: "viewTitle", text: "Ontology graph" }));
    root.appendChild(el("div", { class: "viewHint",
      text: "The harmonic ontology (degree / quality / function / interval-layer / scale / cadence nodes and their typed edges) that will drive automatic score analysis." }));

    var g = data.graph || { nodes: [], edges: [] };
    // Deterministic layered layout: one column per node-kind.
    var kinds = ["scale", "degree", "function", "quality", "layer", "cadence"];
    var byKind = {};
    kinds.forEach(function (k) { byKind[k] = []; });
    g.nodes.forEach(function (n) { if (byKind[n.kind]) byKind[n.kind].push(n); });

    var W = 1100, colGap = W / (kinds.length + 1), rowGap = 26, top = 30;
    var pos = {};
    kinds.forEach(function (k, ci) {
      byKind[k].forEach(function (n, ri) {
        pos[n.id] = { x: colGap * (ci + 1), y: top + rowGap * ri };
      });
    });
    var maxRows = Math.max.apply(null, kinds.map(function (k) { return byKind[k].length; }));
    var H = top + rowGap * (maxRows + 1);

    var svgNS = "http://www.w3.org/2000/svg";
    if (!document.createElementNS) {       // stubbed DOM (Node test): skip SVG
      root.appendChild(el("div", { class: "meta",
        text: g.nodes.length + " nodes, " + g.edges.length + " edges" }));
      return;
    }
    var svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("id", "graphSvg");
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);

    g.edges.forEach(function (e) {
      var a = pos[e.source], b = pos[e.target];
      if (!a || !b) return;
      var line = document.createElementNS(svgNS, "line");
      line.setAttribute("class", "gedge");
      line.setAttribute("x1", a.x); line.setAttribute("y1", a.y);
      line.setAttribute("x2", b.x); line.setAttribute("y2", b.y);
      svg.appendChild(line);
    });
    g.nodes.forEach(function (n) {
      var p = pos[n.id]; if (!p) return;
      var grp = document.createElementNS(svgNS, "g");
      grp.setAttribute("class", "gnode");
      var c = document.createElementNS(svgNS, "circle");
      c.setAttribute("cx", p.x); c.setAttribute("cy", p.y); c.setAttribute("r", 5);
      c.setAttribute("fill", kindColor(n.kind));
      var tx = document.createElementNS(svgNS, "text");
      tx.setAttribute("x", p.x + 8); tx.setAttribute("y", p.y + 3);
      tx.textContent = n.label;
      grp.appendChild(c); grp.appendChild(tx);
      if (n.spec) grp.addEventListener("click", function () { launch(n.spec); });
      svg.appendChild(grp);
    });
    root.appendChild(svg);

    var legend = el("div", { class: "legend" });
    kinds.forEach(function (k) {
      legend.appendChild(el("span", { html:
        '<b style="color:' + kindColor(k) + '">●</b> ' + k }));
    });
    root.appendChild(legend);
  }

  function kindColor(kind) {
    return ({ scale: "#0ea5e9", degree: "#2563eb", function: "#dc2626",
      quality: "#7c3aed", layer: "#b45309", cadence: "#16a34a" })[kind] || "#64748b";
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // -- public API ----------------------------------------------------------
  function init(payload) {
    data = payload || {};
    launchQueue = [];
    activeIds = new Set();
    hoverIds = new Set();
    buildTabs();
    showTab(TABS[0].id);
    return { ok: true, tabs: TABS.map(function (t) { return t.id; }) };
  }

  var AtlasUI = {
    init: init,
    showTab: showTab,
    currentTab: function () { return tabId; },
    takeLaunch: takeLaunch,
    launch: launch,                         // exposed for tests/host
    pendingCount: function () { return launchQueue.length; },
    setSync: setSync,
    syncState: syncState,
    hoverRelated: hoverRelated,
    clearHover: clearHover,
    hoverState: hoverState,
    setCurrentLevel: function (lvl) { this._currentLevel = lvl; },
    _currentLevel: null,
    tabs: function () { return TABS.map(function (t) { return t.id; }); },
  };
  window.AtlasUI = AtlasUI;
})();
