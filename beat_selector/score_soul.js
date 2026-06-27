/* Score Soul Graph controller -- window.ScoreSoul.
 *
 * Renders ONE piece's curated harmonic analysis: a left navigator (form
 * sections / measures / cadences) + a "trainer-style" current-chord card, and
 * a radial harmonic "mandala" (the score graph).  ALL geometry is precomputed
 * in Python (harmony/score_graph.py); this script does ZERO layout math -- it
 * only plots x/y and toggles CSS classes, so it is headless-safe (when no real
 * DOM/SVG is available it keeps all data/state logic working and skips drawing,
 * exactly like atlas.js / harmonic_network.js).
 *
 * Host bridge (polling, no QWebChannel):
 *   - host injects window.SCORE_SOUL_DATA = {analysis, graph} then calls init().
 *   - host pushes the live measure via setCurrentMeasure(m).
 *   - host polls takeSelection() to learn when the user clicked a measure/node.
 */
(function (global) {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";

  var state = {
    data: null,
    analysis: null,
    graph: null,
    slicesByMeasure: {},
    sections: [],
    cadences: [],
    measures: [],
    nodesById: {},
    adjacency: {},          // nodeId -> [neighborId]
    incidentEdges: {},      // nodeId -> [edgeIndex]
    current: null,
    selectionQueue: [],
    svgEls: { nodes: {}, edges: [], labels: {} },
    dom: false
  };

  function hasDom() {
    return (typeof document !== "undefined" && document &&
            typeof document.getElementById === "function");
  }
  function canSvg() {
    return hasDom() && typeof document.createElementNS === "function";
  }
  function el(id) { return hasDom() ? document.getElementById(id) : null; }

  // ---------------------------------------------------------------- index
  function indexData(payload) {
    state.data = payload || {};
    state.analysis = state.data.analysis || {};
    state.graph = state.data.graph || { nodes: [], edges: [] };

    state.slicesByMeasure = {};
    (state.analysis.slices || []).forEach(function (s) {
      state.slicesByMeasure[s.measure] = s;
    });
    state.measures = (state.analysis.slices || [])
      .map(function (s) { return s.measure; })
      .sort(function (a, b) { return a - b; });
    state.sections = state.analysis.sections || [];
    state.cadences = state.analysis.cadences || [];

    state.nodesById = {};
    (state.graph.nodes || []).forEach(function (n) { state.nodesById[n.id] = n; });

    state.adjacency = {};
    state.incidentEdges = {};
    (state.graph.edges || []).forEach(function (e, i) {
      (state.adjacency[e.source] = state.adjacency[e.source] || []).push(e.target);
      (state.adjacency[e.target] = state.adjacency[e.target] || []).push(e.source);
      (state.incidentEdges[e.source] = state.incidentEdges[e.source] || []).push(i);
      (state.incidentEdges[e.target] = state.incidentEdges[e.target] || []).push(i);
    });
  }

  // ---------------------------------------------------------------- lists
  function functionClass(slice) {
    if (!slice) return "";
    if (slice.status === "unsupported_chromatic") return "chromatic";
    if (slice.status === "ambiguous") return "ambiguous";
    var f = (slice.functionLabel || "").toLowerCase();
    if (f === "tonic" || f === "mediant" || f === "submediant") return "tonic";
    if (f === "dominant" || f === "subtonic") return "dominant";
    if (f === "predominant" || f === "subdominant") return "predominant";
    return "tonic";
  }

  function makeLi(html, onClick, cls) {
    var li = document.createElement("li");
    li.innerHTML = html;
    if (cls) li.className = cls;
    if (onClick) li.addEventListener("click", onClick);
    return li;
  }

  function renderLists() {
    if (!hasDom()) return;
    var title = el("soulTitle"), sub = el("soulSub");
    if (title) title.textContent = state.analysis.title || "Score Soul Graph";
    if (sub) {
      sub.textContent = [
        state.analysis.composer || "",
        (state.analysis.key || "") + " " + (state.analysis.mode || ""),
        (state.analysis.measureCount || state.measures.length) + " bars"
      ].filter(Boolean).join("  ·  ");
    }

    var secUl = el("soulSections");
    if (secUl) {
      secUl.innerHTML = "";
      state.sections.forEach(function (sec) {
        secUl.appendChild(makeLi(
          '<span class="soul-badge">' + esc(sec.label) + '</span>' +
          '<span class="soul-secrange">m' + sec.startMeasure + "–" + sec.endMeasure +
          "</span>",
          function () { selectMeasure(sec.startMeasure); }, "soul-section-li"));
      });
    }

    var mOl = el("soulMeasures");
    if (mOl) {
      mOl.innerHTML = "";
      state.measures.forEach(function (m) {
        var s = state.slicesByMeasure[m];
        var li = makeLi(
          '<span class="soul-mnum">m' + m + '</span>' +
          '<span class="soul-badge">' + esc(s.roman || s.chordSymbol || "?") + '</span>' +
          '<span class="soul-dot dot-' + (s.status || "ok") + '"></span>',
          function () { selectMeasure(m); }, "soul-measure-li");
        li.setAttribute("data-measure", m);
        mOl.appendChild(li);
      });
    }

    var cadUl = el("soulCadences");
    if (cadUl) {
      cadUl.innerHTML = "";
      if (!state.cadences.length) {
        cadUl.appendChild(makeLi('<span class="soul-secrange">none annotated</span>', null));
      }
      state.cadences.forEach(function (c) {
        cadUl.appendChild(makeLi(
          '<span class="soul-badge">' + esc(c.cadenceType || (c.pattern || []).join("–")) +
          '</span>' +
          '<span class="soul-secrange">m' + c.startMeasure + "–" + c.endMeasure + "</span>",
          function () { selectMeasure(c.startMeasure); }, "soul-cadence-li"));
      });
    }

    var counts = el("soulMandalaCounts");
    if (counts && state.graph.counts) {
      counts.textContent = state.graph.counts.nodes + " nodes · " +
        state.graph.counts.edges + " edges";
    }
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // ---------------------------------------------------------------- card
  function renderCard(measure) {
    if (!hasDom()) return;
    var body = el("soulChordBody");
    if (!body) return;
    var s = state.slicesByMeasure[measure];
    if (!s) { body.className = "soul-chord-empty";
      body.textContent = "Select a measure to begin."; return; }
    var fc = functionClass(s);
    var html = '<div><span class="soul-chord-roman">' + esc(s.roman || "?") +
      '</span><span class="soul-chord-sym">' + esc(s.chordSymbol || "") + "</span></div>";
    html += '<div class="soul-chord-row">';
    html += '<span class="soul-pill">m' + measure + "</span>";
    if (s.functionLabel) html += '<span class="soul-pill ' + fc + '">' +
      esc(s.functionLabel) + "</span>";
    html += '<span class="soul-pill">' + esc((state.analysis.key || "") + " " +
      (s.mode || state.analysis.mode || "")) + "</span>";
    if (s.intervalLayer) html += '<span class="soul-pill">' + esc(s.intervalLayer) + "</span>";
    html += "</div>";
    if (s.notes && s.notes.length)
      html += '<div class="soul-refs">notes: <code>' + esc(s.notes.join(" ")) + "</code></div>";
    if (s.status === "unsupported_chromatic")
      html += '<div class="soul-status-flag chromatic">⚠ chromatic — ' +
        'requires reserved chromatic layer</div>';
    else if (s.status === "ambiguous")
      html += '<div class="soul-status-flag ambiguous">≈ ambiguous reading</div>';
    if (s.explanation)
      html += '<div class="soul-chord-expl">' + esc(s.explanation) + "</div>";
    if (s.atlasRefs && s.atlasRefs.length)
      html += '<div class="soul-refs">Atlas: <code>' + esc(s.atlasRefs.join("  ")) + "</code></div>";
    if (s.networkRefs && s.networkRefs.length)
      html += '<div class="soul-refs">Network: <code>' + esc(s.networkRefs.join("  ")) + "</code></div>";
    body.className = "soul-chord-detail";
    body.innerHTML = html;
  }

  // ---------------------------------------------------------------- mandala
  function svg(tag, attrs) {
    var e = document.createElementNS(SVG_NS, tag);
    for (var k in attrs) if (attrs.hasOwnProperty(k)) e.setAttribute(k, attrs[k]);
    return e;
  }

  function renderMandala() {
    var host = el("soulMandala");
    if (!host) return;
    if (!canSvg()) {
      host.className = "soul-headless";
      host.textContent = "Mandala: " + (state.graph.nodes || []).length +
        " nodes, " + (state.graph.edges || []).length +
        " edges (SVG unavailable in this environment).";
      return;
    }
    host.innerHTML = "";
    var w = state.graph.width || 1600, h = state.graph.height || 1600;
    var root = svg("svg", { viewBox: "0 0 " + w + " " + h,
      preserveAspectRatio: "xMidYMid meet" });
    var gEdges = svg("g", { "class": "soul-edges" });
    var gNodes = svg("g", { "class": "soul-nodes" });
    var gLabels = svg("g", { "class": "soul-labels" });
    root.appendChild(gEdges); root.appendChild(gNodes); root.appendChild(gLabels);

    state.svgEls = { nodes: {}, edges: [], labels: {} };
    (state.graph.edges || []).forEach(function (e) {
      var a = state.nodesById[e.source], b = state.nodesById[e.target];
      if (!a || !b) { state.svgEls.edges.push(null); return; }
      var line = svg("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y,
        "class": "soul-edge rel-" + e.relation });
      gEdges.appendChild(line);
      state.svgEls.edges.push(line);
    });

    (state.graph.nodes || []).forEach(function (n) {
      var c = svg("circle", { cx: n.x, cy: n.y, r: n.radius || 10,
        "class": "soul-node vc-" + (n.visualClass || "default") });
      c.setAttribute("data-id", n.id);
      if (n.type === "measure" || n.type === "harmony_slice") {
        c.addEventListener("click", function () {
          if (n.measure != null) selectMeasure(n.measure);
        });
      }
      gNodes.appendChild(c);
      state.svgEls.nodes[n.id] = c;
      if (shouldLabel(n)) {
        var t = svg("text", { x: n.x, y: n.y, "class": "soul-nlabel" });
        t.textContent = labelOf(n);
        gLabels.appendChild(t);
        state.svgEls.labels[n.id] = t;
      }
    });

    host.appendChild(root);
  }

  function shouldLabel(n) {
    return n.type === "score" || n.type === "form_section" ||
      n.type === "function" || n.type === "cadence" || n.type === "measure" ||
      n.type === "key_area";
  }
  function labelOf(n) {
    if (n.type === "measure") return String(n.measure);
    if (n.label && n.label.length > 16) return n.label.slice(0, 15) + "…";
    return n.label || "";
  }

  // ------------------------------------------------------------ highlight
  function activeSetFor(measure) {
    var ids = {};
    ["measure:" + measure, "slice:" + measure].forEach(function (id) {
      if (state.nodesById[id]) {
        ids[id] = true;
        (state.adjacency[id] || []).forEach(function (nb) { ids[nb] = true; });
      }
    });
    return ids;
  }

  function applyHighlight(measure) {
    if (!canSvg()) return;
    var activeIds = activeSetFor(measure);
    var activeEdge = {};
    ["measure:" + measure, "slice:" + measure].forEach(function (id) {
      (state.incidentEdges[id] || []).forEach(function (ei) { activeEdge[ei] = true; });
    });
    Object.keys(state.svgEls.nodes).forEach(function (id) {
      var c = state.svgEls.nodes[id];
      var on = !!activeIds[id];
      c.classList.toggle("node-active", on);
      c.classList.toggle("node-dim", !on);
    });
    Object.keys(state.svgEls.labels).forEach(function (id) {
      state.svgEls.labels[id].classList.toggle("lbl-dim", !activeIds[id]);
    });
    state.svgEls.edges.forEach(function (line, i) {
      if (line) line.classList.toggle("edge-active", !!activeEdge[i]);
    });
  }

  function applyListActive(measure) {
    if (!hasDom()) return;
    var ol = el("soulMeasures");
    if (!ol) return;
    var items = ol.querySelectorAll("li");
    for (var i = 0; i < items.length; i++) {
      var m = parseInt(items[i].getAttribute("data-measure"), 10);
      items[i].classList.toggle("active", m === measure);
    }
  }

  // ------------------------------------------------------------ public API
  function init(payload) {
    indexData(payload || global.SCORE_SOUL_DATA || {});
    state.dom = hasDom();
    renderLists();
    renderMandala();
    if (state.measures.length) setCurrentMeasure(state.measures[0]);
    return { ok: true, measures: state.measures.length,
             nodes: (state.graph.nodes || []).length,
             edges: (state.graph.edges || []).length };
  }

  function setCurrentMeasure(measure) {
    measure = parseInt(measure, 10);
    if (isNaN(measure)) return null;
    state.current = measure;
    renderCard(measure);
    applyListActive(measure);
    applyHighlight(measure);
    return measure;
  }

  // user-initiated selection: update locally AND queue for the host to pick up
  function selectMeasure(measure) {
    measure = parseInt(measure, 10);
    if (isNaN(measure)) return null;
    setCurrentMeasure(measure);
    state.selectionQueue.push({ measure: measure });
    return measure;
  }

  function takeSelection() {
    return state.selectionQueue.length ? state.selectionQueue.shift() : null;
  }

  function exportState() {
    return {
      currentMeasure: state.current,
      measureCount: state.analysis ? (state.analysis.measureCount || state.measures.length) : 0,
      nodeCount: (state.graph && state.graph.nodes ? state.graph.nodes.length : 0),
      edgeCount: (state.graph && state.graph.edges ? state.graph.edges.length : 0),
      pendingSelections: state.selectionQueue.length
    };
  }

  global.ScoreSoul = {
    init: init,
    setCurrentMeasure: setCurrentMeasure,
    selectMeasure: selectMeasure,
    takeSelection: takeSelection,
    currentMeasure: function () { return state.current; },
    measureCount: function () {
      return state.analysis ? (state.analysis.measureCount || state.measures.length) : 0;
    },
    measures: function () { return state.measures.slice(); },
    sliceForMeasure: function (m) { return state.slicesByMeasure[m] || null; },
    slices: function () { return (state.analysis && state.analysis.slices) || []; },
    nodeCount: function () { return (state.graph && state.graph.nodes ? state.graph.nodes.length : 0); },
    edgeCount: function () { return (state.graph && state.graph.edges ? state.graph.edges.length : 0); },
    nodeIds: function () { return Object.keys(state.nodesById); },
    activeNodesFor: function (m) { return Object.keys(activeSetFor(m)); },
    graphCounts: function () { return (state.graph && state.graph.counts) || null; },
    exportState: exportState
  };

  // auto-init when the host injected data before this script ran
  if (hasDom() && global.SCORE_SOUL_DATA) {
    try { init(global.SCORE_SOUL_DATA); } catch (e) { /* host will call init */ }
  }
})(typeof window !== "undefined" ? window : this);
