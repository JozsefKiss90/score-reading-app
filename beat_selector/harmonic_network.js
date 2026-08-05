/*
 * Harmonic Network / Tonal Graph layer -- web UI controller.
 *
 * Loaded by beat_selector/harmonic_network.html inside a QWebEngineView. It
 * renders the JSON payload produced by
 * harmony.harmonic_network.HarmonicNetwork.to_payload() (schema
 * "harmony-network/v1") into three panels:
 *
 *   LEFT   -- node-class toggles, edge-relation toggles, search box, reset.
 *   CENTER -- the SVG harmonic network (node x/y come straight from Python;
 *             the JS does ZERO layout maths, so it is headless-safe).
 *   RIGHT  -- the selected node/edge explanation, related Atlas/Circle nodes,
 *             related Trainer drills (launchable vs reserved) + launch buttons,
 *             and related Lab experiments.
 *
 * Host-pollable API (window.HarmonicNetwork):
 *   init(payload)                 -> render everything; returns {ok, nodes, edges}
 *   selectNode(nodeId)            -> select + explain a node
 *   selectEdge(edgeId)            -> select + explain an edge
 *   setFilter(filter)             -> {kinds:{...}, relations:{...}, search}
 *   clearSelection()
 *   takeLaunch()                  -> dequeue a clicked exercise spec (host polls)
 *   highlightFromTrainerTarget(t) -> follow the trainer's current chord
 *   highlightFromAtlasSync(active)-> follow an Atlas sync payload
 *   exportState()                 -> inspectable state snapshot
 *
 * It never re-derives theory: every launchable exercise is a HarmonyExerciseSpec
 * dict that came straight from the Python model. Stateful logic (selection,
 * filters, launchQueue) is kept DOM-independent so it unit-tests headlessly
 * under Node (see tests/harmonic_network_node_test.js), exactly like atlas.js.
 */
(function () {
  "use strict";

  var SVGNS = "http://www.w3.org/2000/svg";

  // -- module state ---------------------------------------------------------
  var data = null;
  var nodesById = {};            // id -> node
  var edgeById = {};             // id -> edge
  var nodesByKind = {};          // kind -> [node]
  var pcIndex = {};              // pitchClass -> {major,minor,dom7,dim:[ids]}
  var adjacency = {};            // nodeId -> Set(edgeId)

  var filters = { kinds: {}, relations: {}, search: "" };
  var selectedNodeId = null;
  var selectedEdgeId = null;
  var launchQueue = [];          // clicked specs the host will pick up
  var lastLaunch = null;         // debug: {exerciseId, drill, queued, reason}
  var syncNodeIds = [];          // trainer-target sync highlight (separate from selection)
  var syncPrimaryId = null;      // the closest/primary sync node (returned to host)
  var searchHits = new Set();
  // Progressive-journey state (functional degree network payloads). Both are
  // host-driven and layered ON TOP of the user's kind/relation filters:
  //   visibleWhitelist -- optional stage whitelist (null = no whitelist);
  //   completedSet     -- permanently lit ("done") node ids for this session.
  var visibleWhitelist = null;   // Set(nodeId) | null
  var completedSet = new Set();

  // -- bidirectional drill<->graph state (plan sections 6, 11, 12) -----------
  //   mode         : "explore" | "graph_to_drill" | "drill_to_graph"
  //   projection   : the active DrillGraphProjection dict (null = none)
  //   flow*        : the running trainer position projected onto occurrences
  //   hostRequestQueue : typed requests the host polls (launch | seek | ...)
  var mode = "explore";
  var projection = null;
  var previewProjection = null;
  var occurrenceById = {};       // occurrenceId -> step
  var occByVisualNode = {};      // visualNodeId -> [occurrenceId]
  var proxyById = {};            // proxy/overlay node id -> projection node
  var visitedOccurrenceIds = new Set();
  var currentOccurrenceId = null;
  var nextOccurrenceId = null;
  var correctnessByOccurrence = {}; // occurrenceId -> "correct"|"incorrect"|null
  var hostRequestQueue = [];      // {type, ...} the host dequeues via takeHostRequest()

  // -- tiny DOM helpers (tolerant of the Node test's stubbed document) -------
  function byId(id) { return document.getElementById(id); }
  function clear(node) { if (node) node.innerHTML = ""; }

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

  function svg(tag, attrs) {
    var n = document.createElementNS(SVGNS, tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    return n;
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // -- pitch-class arithmetic (for sync highlighting only; not a chord table)-
  var LETTER_PC = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
  function parsePc(name) {
    if (!name) return null;
    var m = /^([A-Ga-g])([#b♯♭x]*)/.exec(String(name).trim());
    if (!m) return null;
    var pc = LETTER_PC[m[1].toUpperCase()];
    var acc = m[2] || "";
    for (var i = 0; i < acc.length; i++) {
      var ch = acc[i];
      if (ch === "#" || ch === "♯") pc += 1;
      else if (ch === "x") pc += 2;
      else if (ch === "b" || ch === "♭") pc -= 1;
    }
    return ((pc % 12) + 12) % 12;
  }

  // -- indexing -------------------------------------------------------------
  function indexPayload() {
    nodesById = {}; nodesByKind = {}; pcIndex = {}; edgeById = {}; adjacency = {};
    (data.nodes || []).forEach(function (n) {
      nodesById[n.id] = n;
      (nodesByKind[n.kind] = nodesByKind[n.kind] || []).push(n);
      var slot = pcIndex[n.pitchClass] = pcIndex[n.pitchClass] || {};
      (slot[n.kind] = slot[n.kind] || []).push(n.id);
      adjacency[n.id] = new Set();
    });
    (data.edges || []).forEach(function (e) {
      edgeById[e.id] = e;
      if (adjacency[e.source]) adjacency[e.source].add(e.id);
      if (adjacency[e.target]) adjacency[e.target].add(e.id);
    });
  }

  function defaultFilters() {
    var kinds = {}, relations = {};
    ((data.legend && data.legend.nodeClasses) || []).forEach(function (nc) {
      kinds[nc.kind] = true;                       // all node classes visible
    });
    ((data.legend && data.legend.edgeClasses) || []).forEach(function (ec) {
      if (ec.implemented) relations[ec.relation] = !!ec.defaultVisible;
    });
    return { kinds: kinds, relations: relations, search: "" };
  }

  // -- visibility model (pure; drives both the SVG and the test) ------------
  function nodeVisible(n) {
    if (visibleWhitelist && !visibleWhitelist.has(n.id)) return false;
    if (!filters.kinds[n.kind]) return false;
    if (filters.search) {
      return matchesSearch(n);
    }
    return true;
  }
  function matchesSearch(n) {
    var q = filters.search.toLowerCase();
    return (n.label && n.label.toLowerCase().indexOf(q) !== -1) ||
           (n.spelling && n.spelling.toLowerCase().indexOf(q) !== -1) ||
           (n.kind && n.kind.toLowerCase().indexOf(q) !== -1);
  }
  function edgeVisible(e) {
    if (!filters.relations[e.relation]) return false;
    if (visibleWhitelist &&
        (!visibleWhitelist.has(e.source) || !visibleWhitelist.has(e.target))) {
      return false;              // an edge into a whitelisted-out node is hidden
    }
    var a = nodesById[e.source], b = nodesById[e.target];
    if (!a || !b) return false;
    // a relation is only drawn if both endpoints' kinds are enabled
    if (!filters.kinds[a.kind] || !filters.kinds[b.kind]) return false;
    return true;
  }
  function visibleNodes() { return (data.nodes || []).filter(nodeVisible); }
  function visibleEdges() { return (data.edges || []).filter(edgeVisible); }

  // -- selection model ------------------------------------------------------
  function neighborsOf(nodeId) {
    var out = new Set();
    (adjacency[nodeId] ? Array.from(adjacency[nodeId]) : []).forEach(function (eid) {
      var e = edgeById[eid];
      if (!e) return;
      out.add(e.source === nodeId ? e.target : e.source);
    });
    return out;
  }
  function incidentEdges(nodeId) {
    return (adjacency[nodeId] ? Array.from(adjacency[nodeId]) : []).map(function (eid) {
      return edgeById[eid];
    });
  }

  // -- launch queue (host integration) --------------------------------------
  // The host (run_harmonic_network_demo.py) polls takeLaunch() and feeds the
  // dequeued dict straight into HarmonyExerciseSpec.from_dict(), so what we queue
  // MUST be a raw HarmonyExerciseSpec dict (carrying a real `drill`), never a
  // wrapper/entry object and never a reserved placeholder.
  var RESERVED_DRILLS = { seventh_chord: true };

  function launch(spec) {
    // Only a raw, launchable spec dict may enqueue.
    if (!spec || typeof spec !== "object" || !spec.drill) {
      lastLaunch = { exerciseId: (spec && spec.exercise_id) || null,
        drill: (spec && spec.drill) || null, queued: false,
        reason: "missing-or-malformed-spec" };
      return false;
    }
    if (RESERVED_DRILLS[spec.drill]) {     // reserved drills can never launch
      lastLaunch = { exerciseId: spec.exercise_id || null, drill: spec.drill,
        queued: false, reason: "reserved-drill" };
      return false;
    }
    launchQueue.push(spec);
    lastLaunch = { exerciseId: spec.exercise_id || null, drill: spec.drill,
      queued: true, reason: "ok" };
    return true;
  }
  function takeLaunch() { return launchQueue.length ? launchQueue.shift() : null; }

  // -- host request queue (Drill<->Graph navigation) ------------------------
  // The host polls takeHostRequest(); the UI (timeline / graph click / launch
  // button) enqueues typed requests. takeLaunch() stays a compat alias that
  // only dequeues launch-type requests carrying a raw spec.
  function enqueueHostRequest(req) { hostRequestQueue.push(req); return req; }
  function takeHostRequest() {
    return hostRequestQueue.length ? hostRequestQueue.shift() : null;
  }
  function requestSeek(occurrenceId) {
    var step = occurrenceById[occurrenceId];
    if (!step) return null;
    return enqueueHostRequest({ type: "seek", occurrenceId: occurrenceId,
      sequenceIndex: step.sequenceIndex });
  }

  // ======================================================================
  // Drill projection (Drill -> Graph) -- host pushes a DrillGraphProjection
  // ======================================================================
  function indexProjection() {
    occurrenceById = {}; occByVisualNode = {}; proxyById = {};
    if (!projection) return;
    (projection.steps || []).forEach(function (s) {
      occurrenceById[s.occurrenceId] = s;
      (occByVisualNode[s.visualNodeId] = occByVisualNode[s.visualNodeId] || [])
        .push(s.occurrenceId);
    });
    (projection.projectionNodes || []).forEach(function (n) { proxyById[n.id] = n; });
  }

  function setProjection(p) {
    projection = p || null;
    previewProjection = null;
    visitedOccurrenceIds = new Set();
    currentOccurrenceId = null;
    nextOccurrenceId = (projection && projection.steps && projection.steps.length)
      ? projection.steps[0].occurrenceId : null;
    correctnessByOccurrence = {};
    if (projection) mode = "drill_to_graph";
    indexProjection();
    renderGraph();
    renderTimeline();
    renderProjectionSummary();
    return exportState();
  }
  function clearProjection() {
    projection = null; previewProjection = null;
    occurrenceById = {}; occByVisualNode = {}; proxyById = {};
    visitedOccurrenceIds = new Set();
    currentOccurrenceId = null; nextOccurrenceId = null;
    correctnessByOccurrence = {};
    mode = "explore";
    renderGraph(); renderTimeline(); renderProjectionSummary();
    return exportState();
  }

  // Update the running trainer position (does NOT rebuild the projection). The
  // host calls this on each flow-state poll; it mutates flow vars + redraws the
  // graph only, leaving the user's explore-mode selection untouched.
  function updateFlowState(state) {
    if (!state || !projection) return exportState();
    var occ = state.occurrenceId;
    if (occ == null && state.sequenceIndex != null) {
      var s = (projection.steps || [])[state.sequenceIndex];
      occ = s ? s.occurrenceId : null;
    }
    if (occ != null && occurrenceById[occ]) {
      if (currentOccurrenceId != null && currentOccurrenceId !== occ) {
        visitedOccurrenceIds.add(currentOccurrenceId);
      }
      currentOccurrenceId = occ;
      var idx = occurrenceById[occ].sequenceIndex;
      var nxt = (projection.steps || [])[idx + 1];
      nextOccurrenceId = nxt ? nxt.occurrenceId : null;
    }
    if (state.correct === true) correctnessByOccurrence[occ] = "correct";
    else if (state.correct === false) correctnessByOccurrence[occ] = "incorrect";
    renderGraph();
    renderTimeline();
    return exportState();
  }

  function previewLaunch(proj) {
    // proj may be a projection dict (preview_projection) or null to clear.
    previewProjection = proj || null;
    renderGraph();
    renderProjectionSummary();
    return exportState();
  }

  function setMode(m) {
    if (m === "explore" || m === "graph_to_drill" || m === "drill_to_graph") mode = m;
    renderGraph();
    return mode;
  }

  // The projection currently driving the graph (active projection, else preview).
  function activeProjection() { return projection || previewProjection; }

  // Strongest flow/projection state class for a visual node id (canonical or proxy).
  function projectionClassFor(visualNodeId) {
    var ap = activeProjection();
    if (!ap) return "";
    var c = "";
    var occs = occByVisualNode[visualNodeId];
    var inProjection = !!occs ||
      (ap.constellationNodeIds && ap.constellationNodeIds.indexOf(visualNodeId) !== -1);
    if (inProjection) c += " in-projection";
    if (ap.anchorNodeIds && ap.anchorNodeIds.indexOf(visualNodeId) !== -1) c += " is-anchor";
    if (occs && projection) {
      var isCurrent = occs.indexOf(currentOccurrenceId) !== -1;
      var isNext = occs.indexOf(nextOccurrenceId) !== -1;
      var isVisited = occs.some(function (o) { return visitedOccurrenceIds.has(o); });
      if (isCurrent) c += " is-current";
      else if (isNext) c += " is-next";
      else if (isVisited) c += " is-visited";
      // correctness ring for the current occurrence
      var corr = correctnessByOccurrence[currentOccurrenceId];
      if (isCurrent && corr === "correct") c += " is-correct";
      else if (isCurrent && corr === "incorrect") c += " is-incorrect";
    }
    return c;
  }

  // ======================================================================
  // Occurrence timeline + projection summary (el()-built -> headless-safe).
  // The timeline is the authoritative occurrence-level view (one canonical node
  // may occur N times); the graph is the canonical-entity view.
  // ======================================================================
  function renderTimeline() {
    var root = byId("hnTimeline");
    if (!root) return;
    clear(root);
    if (!projection || !(projection.steps || []).length) return;
    projection.steps.forEach(function (s) {
      var cls = "occChip";
      if (s.occurrenceId === currentOccurrenceId) cls += " is-current";
      else if (s.occurrenceId === nextOccurrenceId) cls += " is-next";
      else if (visitedOccurrenceIds.has(s.occurrenceId)) cls += " is-visited";
      cls += mappingStatusClass(s.mappingStatus);
      var corr = correctnessByOccurrence[s.occurrenceId];
      if (corr) cls += (corr === "correct" ? " is-correct" : " is-incorrect");
      var chip = el("div", { class: cls, dataset: { occ: s.occurrenceId },
        onClick: (function (occ) { return function () { requestSeek(occ); }; })(s.occurrenceId) },
        [
          el("span", { class: "occIdx", text: String(s.sequenceIndex + 1) }),
          el("span", { class: "occRoman", text: s.roman || "" }),
          el("span", { class: "occChord", text: s.chordSymbol || "" }),
          el("span", { class: "occKey", text: s.keyContext || "" }),
          el("span", { class: "occStatus occStatus--" + s.mappingStatus,
            text: s.mappingStatus }),
        ]);
      root.appendChild(chip);
    });
  }

  function renderProjectionSummary() {
    var root = byId("hnSummary");
    if (!root) return;
    clear(root);
    var ap = activeProjection();
    if (!ap) return;
    var counts = ap.counts || {};
    var byStatus = counts.byMappingStatus || {};
    var total = (ap.steps || []).length;
    var curIdx = null;
    if (currentOccurrenceId && occurrenceById[currentOccurrenceId]) {
      curIdx = occurrenceById[currentOccurrenceId].sequenceIndex + 1;
    }
    root.appendChild(el("div", { class: "sumTitle", text: ap.title || "" }));
    root.appendChild(el("div", { class: "sumMeta" }, [
      el("span", { text: "family: " + (ap.drillFamily || "") }),
      el("span", { text: "group: " + (ap.semanticGroup || "") }),
      el("span", { text: "order: " + (ap.sequenceSemantics || "") }),
    ]));
    root.appendChild(el("div", { class: "sumPos",
      text: (curIdx == null ? "—" : curIdx) + " / " + total }));
    root.appendChild(el("div", { class: "sumMapping" }, [
      el("span", { class: "occStatus--exact", text: "exact " + (byStatus.exact || 0) }),
      el("span", { class: "occStatus--contextual",
        text: "contextual " + (byStatus.contextual || 0) }),
      el("span", { class: "occStatus--approximate",
        text: "approx " + (byStatus.approximate || 0) }),
      el("span", { class: "occStatus--unsupported",
        text: "unsupported " + (byStatus.unsupported || 0) }),
    ]));
    (ap.warnings || []).forEach(function (w) {
      root.appendChild(el("div", { class: "sumWarning", text: w }));
    });
  }

  // ======================================================================
  // LEFT: controls
  // ======================================================================
  function renderControls() {
    var root = byId("hnLeft");
    if (!root) return;
    clear(root);

    // node-class toggles
    var ncGroup = el("div", { class: "ctlGroup" }, []);
    ncGroup.appendChild(el("h2", { text: "Node classes" }));
    ((data.legend && data.legend.nodeClasses) || []).forEach(function (nc) {
      var cb = el("input", { type: "checkbox" });
      if (cb.setAttribute && filters.kinds[nc.kind]) cb.setAttribute("checked", "checked");
      cb.checked = !!filters.kinds[nc.kind];
      var row = el("label", { class: "toggleRow", onClick: function () {} }, [
        cb,
        el("span", { class: "swatch", style: "background:" + nc.color }),
        el("span", { class: "relLabel" }, [nc.label]),
      ]);
      cb.addEventListener("change", function () {
        filters.kinds[nc.kind] = !!cb.checked; renderGraph(); renderControls();
      });
      ncGroup.appendChild(row);
    });
    root.appendChild(ncGroup);

    // edge-relation toggles (implemented only; reserved listed but disabled)
    var ecGroup = el("div", { class: "ctlGroup" }, []);
    ecGroup.appendChild(el("h2", { text: "Edge relations" }));
    ((data.legend && data.legend.edgeClasses) || []).forEach(function (ec) {
      if (!ec.implemented) return;
      var cb = el("input", { type: "checkbox" });
      cb.checked = !!filters.relations[ec.relation];
      var style = edgeStyleOf(ec.visualClass);     // "solid" | "dashed" | "dotted"
      var sw = el("span", { class: "swatch line" +
          (style === "dashed" ? " dashed" : style === "dotted" ? " dotted" : ""),
        style: "border-top-color:" + edgeColor(ec.visualClass) });
      var lab = el("span", { class: "relLabel" }, [
        el("span", { text: ec.label }),
        el("small", { text: ec.relation }),
      ]);
      var row = el("label", { class: "toggleRow" }, [cb, sw, lab]);
      cb.addEventListener("change", function () {
        filters.relations[ec.relation] = !!cb.checked; renderGraph();
      });
      ecGroup.appendChild(row);
    });
    // reserved relations (named, not generated yet)
    var reserved = ((data.legend && data.legend.edgeClasses) || [])
      .filter(function (ec) { return !ec.implemented; });
    if (reserved.length) {
      ecGroup.appendChild(el("div", { class: "searchHits",
        html: "Reserved: " + reserved.map(function (ec) {
          return '<span class="reservedTag">' + esc(ec.relation) + "</span>";
        }).join(", ") }));
    }
    root.appendChild(ecGroup);

    // search
    var sGroup = el("div", { class: "ctlGroup" }, []);
    sGroup.appendChild(el("h2", { text: "Search" }));
    var input = el("input", { id: "hnSearch", type: "text",
      placeholder: "e.g. G7, B°, F#, minor" });
    input.value = filters.search;
    input.addEventListener("input", function () { setSearch(input.value); });
    sGroup.appendChild(input);
    sGroup.appendChild(el("div", { class: "searchHits", id: "hnSearchHits",
      text: searchHitsLabel() }));
    root.appendChild(sGroup);

    // reset
    var rGroup = el("div", { class: "ctlButtons" }, [
      el("button", { class: "ctlBtn", text: "Reset view",
        onClick: function () { resetView(); } }),
      el("button", { class: "ctlBtn", text: "All relations",
        onClick: function () { setAllRelations(true); } }),
      el("button", { class: "ctlBtn", text: "Core only",
        onClick: function () { setAllRelations(false); } }),
    ]);
    root.appendChild(rGroup);
  }

  function searchHitsLabel() {
    if (!filters.search) return "Type to filter / highlight nodes.";
    return searchHits.size + " match" + (searchHits.size === 1 ? "" : "es");
  }

  function setSearch(q) {
    filters.search = q || "";
    searchHits = new Set();
    if (filters.search) {
      (data.nodes || []).forEach(function (n) {
        if (matchesSearch(n)) searchHits.add(n.id);
      });
    }
    var hits = byId("hnSearchHits");
    if (hits) hits.textContent = searchHitsLabel();
    renderGraph();
  }

  function setAllRelations(on) {
    ((data.legend && data.legend.edgeClasses) || []).forEach(function (ec) {
      if (ec.implemented) filters.relations[ec.relation] = on ? true : !!ec.defaultVisible;
    });
    renderControls(); renderGraph();
  }

  function resetView() {
    filters = defaultFilters();
    searchHits = new Set();
    clearSelection();
    renderControls(); renderGraph();
  }

  // ======================================================================
  // CENTER: SVG graph
  // ======================================================================
  function renderGraph() {
    var root = byId("hnCenter");
    if (!root) return;
    clear(root);

    if (!document.createElementNS) {          // stubbed DOM (Node test): summary
      var vn = visibleNodes().length, ve = visibleEdges().length;
      var ap = activeProjection();
      var extra = "";
      if (ap) {
        extra = ", projection " + ((ap.steps || []).length) + " steps / " +
                ((ap.projectionNodes || []).length) + " proxies" +
                (currentOccurrenceId ? " @" + currentOccurrenceId : "");
      }
      root.appendChild(el("div", { class: "hnFallback", dataset: { mode: mode },
        text: (data.nodes || []).length + " nodes (" + vn + " shown), " +
              (data.edges || []).length + " edges (" + ve + " shown)" + extra }));
      return;
    }

    var s = svg("svg", { id: "hnSvg", viewBox: viewBoxSpec() });

    // arrowhead marker definitions, one per edge colour in use
    var defs = svg("defs", {});
    var colorsUsed = {};
    visibleEdges().forEach(function (e) { colorsUsed[e.visualClass] = edgeColor(e.visualClass); });
    Object.keys(colorsUsed).forEach(function (vc) {
      var m = svg("marker", { id: "arw-" + vc, viewBox: "0 0 10 10", refX: "9",
        refY: "5", markerWidth: "6", markerHeight: "6", orient: "auto-start-reverse" });
      m.appendChild(svg("path", { d: "M0,0 L10,5 L0,10 z", fill: colorsUsed[vc] }));
      defs.appendChild(m);
    });
    s.appendChild(defs);

    // centre crosshair (matches the reference image)
    var cm = svg("g", {});
    cm.appendChild(svg("line", { class: "hnCenterMark", x1: -10, y1: 0, x2: 10, y2: 0 }));
    cm.appendChild(svg("line", { class: "hnCenterMark", x1: 0, y1: -10, x2: 0, y2: 10 }));
    s.appendChild(cm);

    // edges first (so nodes sit on top)
    var sel = selectionHighlight();
    visibleEdges().forEach(function (e) {
      var a = nodesById[e.source], b = nodesById[e.target];
      // class carries BOTH the visual class (drives the dash style in CSS) and
      // the relation (so relation-specific tweaks / tests can target it). The
      // dash pattern lives in CSS keyed on .edge--<visualClass>, so it survives
      // relation toggles and is visible on the dark canvas.
      var path = svg("path", {
        class: "hnEdge edge edge--" + e.visualClass + " relation--" + e.relation +
               edgeStateClass(e, sel),
        d: edgePath(a, b),
        stroke: edgeColor(e.visualClass),
      });
      if (e.direction === "directed") path.setAttribute("marker-end", "url(#arw-" + e.visualClass + ")");
      path.addEventListener("click", function () { selectEdge(e.id); });
      s.appendChild(path);
    });

    // nodes
    visibleNodes().forEach(function (n) {
      var g = svg("g", { class: "hnNode" + nodeStateClass(n, sel),
        "data-id": n.id,
        transform: "translate(" + n.x + "," + n.y + ")" });
      g.appendChild(svg("circle", { r: n.radius, fill: nodeColor(n) }));
      var sub = n.data && n.data.sublabel;
      var tx = sub ? svg("text", { dy: "-4" }) : svg("text", {});
      tx.textContent = n.label;
      g.appendChild(tx);
      if (sub) {                       // small second line (e.g. chord symbol)
        var ts = svg("text", { class: "sub", dy: "8" });
        ts.textContent = String(sub);
        g.appendChild(ts);
      }
      g.addEventListener("click", function () {
        selectNode(n.id);
        // in Drill->Graph mode a graph-node click also seeks the trainer to that occurrence
        if (mode === "drill_to_graph" && occByVisualNode[n.id]) {
          requestSeek(occByVisualNode[n.id][0]);
        }
      });
      s.appendChild(g);
    });

    // -- drill-projection overlay: sequence edges + proxy nodes --------------
    var ap = activeProjection();
    if (ap) {
      (ap.projectionEdges || []).forEach(function (pe) {
        var a = visualNodePos(pe.source), b = visualNodePos(pe.target);
        if (!a || !b) return;
        s.appendChild(svg("path", {
          class: "hnEdge edge edge--" + pe.visualClass + " overlay-seq",
          d: edgePath(a, b), stroke: edgeColor(pe.visualClass),
        }));
      });
      (ap.projectionNodes || []).forEach(function (pn) {
        var cls = "hnNode hnProxy is-proxy" + projectionClassFor(pn.id) +
                  mappingStatusClass(pn.mappingStatus);
        var g = svg("g", { class: cls, "data-id": pn.id,
          transform: "translate(" + pn.x + "," + pn.y + ")" });
        g.appendChild(svg("circle", { r: 15, fill: "#0b1220" }));
        var tx = svg("text", {});
        tx.textContent = pn.label;
        g.appendChild(tx);
        g.addEventListener("click", function () {
          if (occByVisualNode[pn.id]) requestSeek(occByVisualNode[pn.id][0]);
        });
        s.appendChild(g);
      });
    }

    root.appendChild(s);
  }

  // Position of a visual node id (canonical node OR projection proxy).
  function visualNodePos(id) {
    if (nodesById[id]) return { x: nodesById[id].x, y: nodesById[id].y };
    if (proxyById[id]) return { x: proxyById[id].x, y: proxyById[id].y };
    return null;
  }
  function mappingStatusClass(status) {
    if (status === "approximate") return " is-approximate";
    if (status === "unsupported") return " is-unsupported";
    if (status === "contextual") return " is-contextual";
    return "";
  }

  function graphRadius() {
    var r = 0;
    (data.nodes || []).forEach(function (n) {
      r = Math.max(r, Math.sqrt(n.x * n.x + n.y * n.y) + (n.radius || 18));
    });
    return r || 320;
  }

  // The SVG viewBox. Legacy payloads without a whitelist keep the original
  // origin-centred square (the v1 circular field). With a stage whitelist
  // active it is the bounding box of the whitelisted nodes (+labels), so each
  // stage "zooms" to its panel and later stages appear to grow the graph; a
  // progressive payload with NO whitelist (free exploration) uses the all-node
  // bounding box, which equals the everything-whitelisted box -- no jump at
  // the last stage transition. Deliberately keyed on the WHITELIST (not on
  // search/kind filters) so typing in the search box never moves the viewport.
  function viewBoxSpec() {
    var pad = 40;
    var ns = null;
    if (visibleWhitelist) {
      ns = (data.nodes || []).filter(function (n) {
        return visibleWhitelist.has(n.id);
      });
    } else if (data && data.progressive) {
      ns = data.nodes || [];
    }
    if (!ns || !ns.length) {
      var R = graphRadius(), span = (R + pad) * 2;
      return (-(R + pad)) + " " + (-(R + pad)) + " " + span + " " + span;
    }
    var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    ns.forEach(function (n) {
      var r = (n.radius || 18) + 14;      // room for the label ring
      minX = Math.min(minX, n.x - r); maxX = Math.max(maxX, n.x + r);
      minY = Math.min(minY, n.y - r); maxY = Math.max(maxY, n.y + r);
    });
    return (minX - pad) + " " + (minY - pad) + " " +
           (maxX - minX + 2 * pad) + " " + (maxY - minY + 2 * pad);
  }

  // quadratic curve bowing toward the centre -> the reference image's "petals".
  function edgePath(a, b) {
    var mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
    var k = 0.22;                                  // pull control point inward
    var cx = mx * (1 - k), cy = my * (1 - k);
    return "M " + a.x + " " + a.y + " Q " + cx.toFixed(1) + " " + cy.toFixed(1) +
           " " + b.x + " " + b.y;
  }

  function selectionHighlight() {
    if (selectedNodeId) {
      // Only VISIBLE edges define the halo: in a sparse stage (relations
      // switched off) a hidden relation must not dim seemingly-unrelated
      // nodes. With no visible incident edge at all, keep the selection ring
      // but dim nothing (dimOthers false) -- uniform dimming with no visible
      // cause reads as noise.
      var incVisible = incidentEdges(selectedNodeId).filter(edgeVisible);
      var nb = new Set(incVisible.map(function (e) {
        return e.source === selectedNodeId ? e.target : e.source;
      }));
      var inc = new Set(incVisible.map(function (e) { return e.id; }));
      return { node: selectedNodeId, neighbors: nb, edges: inc, active: true,
        dimOthers: incVisible.length > 0 };
    }
    if (selectedEdgeId && edgeById[selectedEdgeId]) {
      var e = edgeById[selectedEdgeId];
      return { node: null, neighbors: new Set([e.source, e.target]),
        edges: new Set([e.id]), active: true, dimOthers: true };
    }
    return { node: null, neighbors: new Set(), edges: new Set(),
      active: false, dimOthers: false };
  }

  function nodeStateClass(n, sel) {
    var c = "";
    if (sel.active) {
      if (n.id === sel.node) c += " sel";
      else if (sel.neighbors.has(n.id)) c += " neighbor";
      else if (sel.dimOthers) c += " dim";
    }
    if (filters.search && searchHits.has(n.id)) c += " searchHit";
    // progressive-journey classes: done = permanently lit; unlit = the grey
    // default for progressive payloads (nothing for legacy payloads).
    if (completedSet.has(n.id)) c += " node--done";
    else if (data && data.progressive) c += " node--unlit";
    // sync highlight is independent of (and visually wins over) selection dimming
    if (syncNodeIds.indexOf(n.id) !== -1) {
      c += " node--sync";
      if (n.id === syncPrimaryId) c += " node--flash";
    }
    // drill projection / flow layer (independent of selection & sync)
    c += projectionClassFor(n.id);
    return c;
  }
  function edgeStateClass(e, sel) {
    var c = "";
    if (sel.active && sel.dimOthers) c += sel.edges.has(e.id) ? " sel" : " dim";
    // light up edges that connect two currently-synced nodes
    if (syncNodeIds.length > 1 &&
        syncNodeIds.indexOf(e.source) !== -1 &&
        syncNodeIds.indexOf(e.target) !== -1) {
      c += " edge--sync";
    }
    return c;
  }

  // ======================================================================
  // RIGHT: explanation + actions
  // ======================================================================
  function renderInfoPlaceholder() {
    var root = byId("hnRight");
    if (!root) return;
    clear(root);
    root.appendChild(el("div", { class: "placeholder",
      text: "Select a node or edge to see its theory explanation, related Atlas " +
            "nodes, Trainer drills and Lab experiments." }));
    var legend = el("div", { class: "sect" }, [el("h3", { text: "Legend" })]);
    ((data.legend && data.legend.nodeClasses) || []).forEach(function (nc) {
      legend.appendChild(el("div", { class: "ctxPill" }, [
        el("span", { class: "swatch", style: "background:" + nc.color +
          ";margin-right:5px;vertical-align:middle" }),
        nc.label,
      ]));
    });
    root.appendChild(legend);
  }

  function renderNodeInfo(n) {
    var root = byId("hnRight");
    if (!root) return;
    clear(root);
    var nc = (data.legend.nodeClasses || []).filter(function (c) { return c.kind === n.kind; })[0] || {};
    root.appendChild(el("span", { class: "kind k-" + n.kind, text: nc.label || n.kind }));
    root.appendChild(el("h2", { text: n.label }));
    root.appendChild(el("div", { class: "expl", text: n.explanation }));

    // key contexts
    if (n.keyContexts && n.keyContexts.length) {
      var ctx = el("div", { class: "sect" }, [el("h3", { text: "Key contexts" })]);
      n.keyContexts.forEach(function (c) { ctx.appendChild(el("span", { class: "ctxPill", text: c })); });
      root.appendChild(ctx);
    }

    // related Trainer drills
    var drills = el("div", { class: "sect" }, [el("h3", { text: "Trainer drills" })]);
    (n.trainerSpecs || []).forEach(function (t) {
      if (t.status === "launchable" && t.spec && !RESERVED_DRILLS[t.spec.drill]) {
        var item = el("div", { class: "launchItem" }, [
          el("div", { class: "lbl", text: t.label }),
          el("button", { class: "launchBtn", text: "Launch ▶",
            onClick: (function (spec) {
              return function () { flashLaunched(launch(spec)); };
            })(t.spec) }),
        ]);
        drills.appendChild(item);
      } else {
        var r = el("div", { class: "launchItem reserved" }, [
          el("div", { class: "lbl" }, [
            el("span", { class: "reservedBadge", text: "Reserved" }),
            el("span", { text: " " + t.label }),
          ]),
          el("div", { class: "reservedWhy", text: t.reason || "Not implemented yet." }),
        ]);
        drills.appendChild(r);
      }
    });
    root.appendChild(drills);

    // related Atlas nodes
    appendRefs(root, "Related Atlas nodes", n.atlasRefs);
    appendRefs(root, "Related Circle keys", n.circleRefs);

    // related Lab experiments
    if (n.labSpecs && n.labSpecs.length) {
      var lab = el("div", { class: "sect" }, [el("h3", { text: "Related Lab experiments" })]);
      n.labSpecs.forEach(function (l) {
        lab.appendChild(el("div", { class: "refList" }, [
          el("div", { html: "<b>" + esc(l.concept) + "</b> — " + esc(l.title) +
            ' <code>' + esc(l.status) + "</code>" }),
        ]));
      });
      root.appendChild(lab);
    }

    // neighbours (clickable). A stage whitelist also gates this list, so the
    // info panel never leaks (or lets the user select) not-yet-revealed nodes;
    // kind/search filters deliberately do NOT apply here (legacy behaviour).
    var nb = Array.from(neighborsOf(n.id)).filter(function (id) {
      return !visibleWhitelist || visibleWhitelist.has(id);
    });
    if (nb.length) {
      var nbSect = el("div", { class: "sect" }, [el("h3", { text: "Connected nodes" })]);
      nb.forEach(function (id) {
        var m = nodesById[id]; if (!m) return;
        nbSect.appendChild(el("span", { class: "ctxPill", onClick: (function (x) {
          return function () { selectNode(x); };
        })(id) }, [
          el("span", { class: "swatch", style: "background:" + nodeColor(m) +
            ";margin-right:5px;vertical-align:middle" }),
          m.label,
        ]));
      });
      root.appendChild(nbSect);
    }
  }

  function appendRefs(root, title, refs) {
    if (!refs || !refs.length) return;
    var sect = el("div", { class: "sect" }, [el("h3", { text: title })]);
    var ul = el("ul", { class: "refList" });
    refs.forEach(function (r) { ul.appendChild(el("li", { html: "<code>" + esc(r) + "</code>" })); });
    sect.appendChild(ul);
    root.appendChild(sect);
  }

  function renderEdgeInfo(e) {
    var root = byId("hnRight");
    if (!root) return;
    clear(root);
    var a = nodesById[e.source], b = nodesById[e.target];
    var ec = (data.legend.edgeClasses || []).filter(function (c) { return c.relation === e.relation; })[0] || {};
    root.appendChild(el("div", { class: "edgeCard" }, [
      el("div", { class: "rel", text: ec.label || e.relation }),
      el("div", { class: "ends", text: (a ? a.label : e.source) +
        (e.direction === "directed" ? "  →  " : "  —  ") + (b ? b.label : e.target) }),
      el("div", { class: "expl", text: e.explanation }),
      el("div", { class: "refList" }, [
        el("div", { html: "relation <code>" + esc(e.relation) + "</code>" }),
        el("div", { html: "strength <code>" + esc(e.strength) + "</code>" }),
      ]),
    ]));
    if (a) root.appendChild(el("span", { class: "ctxPill",
      onClick: function () { selectNode(a.id); } }, ["Open " + a.label]));
    if (b) root.appendChild(el("span", { class: "ctxPill",
      onClick: function () { selectNode(b.id); } }, ["Open " + b.label]));
  }

  function flashLaunched(ok) {
    var hits = byId("hnSearchHits");        // reuse the small status line if present
    if (hits) {
      hits.textContent = ok
        ? "Queued exercise for the trainer."
        : "That drill is reserved — nothing launched.";
    }
  }

  // ======================================================================
  // public selection / highlight API
  // ======================================================================
  function selectNode(nodeId) {
    if (!nodesById[nodeId]) return null;
    selectedNodeId = nodeId; selectedEdgeId = null;
    renderGraph();
    renderNodeInfo(nodesById[nodeId]);
    return nodeId;
  }
  function selectEdge(edgeId) {
    if (!edgeById[edgeId]) return null;
    selectedEdgeId = edgeId; selectedNodeId = null;
    renderGraph();
    renderEdgeInfo(edgeById[edgeId]);
    return edgeId;
  }
  function clearSelection() {
    selectedNodeId = null; selectedEdgeId = null;
    renderGraph(); renderInfoPlaceholder();
  }

  function setFilter(filter) {
    filter = filter || {};
    if (filter.kinds) Object.keys(filter.kinds).forEach(function (k) {
      filters.kinds[k] = !!filter.kinds[k];
    });
    if (filter.relations) Object.keys(filter.relations).forEach(function (r) {
      filters.relations[r] = !!filter.relations[r];
    });
    if (typeof filter.search === "string") { setSearch(filter.search); }
    renderControls(); renderGraph();
    return exportState();
  }

  // -- trainer-target SYNC highlight (separate from selection) ---------------
  // A sync highlight follows the trainer's current chord. It is deliberately
  // NOT a selection: the user's clicked/selected node persists underneath, and
  // the two highlights coexist (see node--sync / node--flash / edge--sync). The
  // host polls this every ~400ms via run_harmonic_network_demo.py.
  function setSyncHighlight(ids) {
    var seen = {};
    syncNodeIds = (ids || []).filter(function (id) {
      if (!id || !nodesById[id] || seen[id]) return false;
      seen[id] = true; return true;
    });
    syncPrimaryId = syncNodeIds.length ? syncNodeIds[0] : null;
    renderGraph();                         // re-draw the graph only; do NOT touch
    return syncPrimaryId;                  // the selection or the info panel.
  }
  function clearSync() { return setSyncHighlight([]); }

  // Map a trainer target (its current chord) onto network node id(s).
  // Real trainer targets carry {key, mode, roman, root, quality}; synthetic
  // ones (tests / Atlas) may carry only {key, mode, roman}. We prefer the
  // explicit chord root + quality, falling back to key-relative arithmetic
  // (V is a fifth above the tonic; the leading-tone vii° is a semitone below).
  function highlightFromTrainerTarget(target) {
    if (!target) return clearSync();
    var keyPc = parsePc(tonicOf(target.key));
    if (keyPc == null) return null;
    var mode = (target.mode || "major").indexOf("minor") !== -1 ? "minor" : "major";
    var roman = (target.roman || "").toLowerCase();
    var quality = (target.quality || "").toLowerCase();
    var rootPc = parsePc(tonicOf(target.root || ""));   // null on synthetic targets

    // the tonic/key context node (mode-aware) -- always part of the highlight
    var keySlot = pcIndex[keyPc] || {};
    var keyNode = (mode === "minor" && keySlot.minor_key) ? keySlot.minor_key[0]
      : (keySlot.major_key ? keySlot.major_key[0] : null);

    var primary = null;
    // A diminished chord acting as the leading-tone vii°. When the target
    // carries a quality, trust it; otherwise only treat the degree as
    // diminished if it explicitly bears the ° symbol -- so a bare "VII"
    // (the MAJOR subtonic of a natural minor key, which lowercases to "vii")
    // is never mistaken for a diminished node.
    var isDim = (quality === "diminished") ||
                (!quality && roman.indexOf("°") !== -1);
    // The dominant degree: roman "V"/"v" (NOT "vi"/"vii").
    var isDom = (roman.charAt(0) === "v" && roman.charAt(1) !== "i");
    if (isDim) {
      var dimPc = (rootPc != null) ? rootPc : (keyPc + 11) % 12;
      var ds = pcIndex[dimPc];
      if (ds && ds.diminished_triad) primary = ds.diminished_triad[0];
    } else if (isDom) {
      var domPc = (rootPc != null) ? rootPc : (keyPc + 7) % 12;
      var d7 = pcIndex[domPc];
      if (d7 && d7.dominant_seventh) primary = d7.dominant_seventh[0];
    }

    var ids = [];
    if (primary) ids.push(primary);             // most specific node first
    if (keyNode && ids.indexOf(keyNode) === -1) ids.push(keyNode);  // key context
    if (!ids.length) {                          // nearest graph context fallback
      var any = pcIndex[keyPc] || {};
      var first = (any.major_key || any.minor_key || any.dominant_seventh ||
                   any.diminished_triad || [])[0];
      if (first) ids.push(first);
    }
    return setSyncHighlight(ids);
  }

  // Map an Atlas sync payload (scale/degree/triad ids) onto a network node.
  // Also a sync highlight (coexists with selection), not a selection change.
  function highlightFromAtlasSync(active) {
    if (!active) return clearSync();
    var ref = active.scale || active.triad || null;   // "scale:C:major" / "triad:C:major:0"
    if (!ref) return clearSync();
    var parts = String(ref).split(":");
    var key = parts[1], mode = parts[2] || "major";
    var pc = parsePc(key);
    if (pc == null) return null;
    var slot = pcIndex[pc] || {};
    var id = (mode.indexOf("minor") !== -1 && slot.minor_key) ? slot.minor_key[0]
      : (slot.major_key ? slot.major_key[0] : null);
    return setSyncHighlight(id ? [id] : []);
  }

  function tonicOf(key) {
    if (!key) return key;
    var m = /^([A-Ga-g][#b♯♭x]*)/.exec(String(key).trim());
    return m ? m[1] : key;
  }

  // -- progressive-journey API (functional degree network payloads) ----------
  // Three additive host hooks (see docs/functional_network_plan.md §3.4). All
  // are safe no-ops / fallbacks on legacy payloads, so the v1 demo and its
  // Node test are untouched.

  // An optional node-id whitelist layered on top of the kind filters. This is
  // what makes stages *appear to grow the graph* without re-init(): a single
  // payload, progressively revealed -- no flicker, selection survives.
  function setVisibleNodes(ids) {
    if (ids == null) {
      visibleWhitelist = null;
    } else {
      visibleWhitelist = new Set();
      (ids || []).forEach(function (id) {
        if (nodesById[id]) visibleWhitelist.add(id);
      });
    }
    renderGraph();
    return exportState();
  }

  // Permanently light nodes for this session (rendered as node--done). The set
  // survives every re-render / filter change; init() with a fresh payload
  // clears it (the host re-applies persisted progress after init).
  function markCompleted(ids) {
    (ids || []).forEach(function (id) {
      if (nodesById[id]) completedSet.add(id);
    });
    renderGraph();
    return completedSet.size;
  }
  function completedIds() { return Array.from(completedSet); }

  // "fnet:deg:<tonic>:<degreeNumber-1>" for a trainer target, or null.
  function degreeNodeIdFor(key, degreeNumber) {
    var tonic = tonicOf(key || "");
    var num = parseInt(degreeNumber, 10);
    if (!tonic || !num || num < 1) return null;
    return "fnet:deg:" + tonic + ":" + (num - 1);
  }

  // Exact-id trainer sync for functional payloads: node ids encode
  // key+degree, so no pitch-class guessing is needed. Highlights the exact
  // degree node + its function group; when the host passes the NEXT chord
  // ({nextKey, nextDegreeNumber}) its node joins the sync set, so the
  // incident resolves_to / prepares edge lights via the existing
  // two-endpoint edge--sync rule. Falls back to the legacy
  // highlightFromTrainerTarget when the payload isn't a fnet template.
  function highlightFromDegreeTarget(target) {
    if (!target) return clearSync();
    var tid = data && data.template && data.template.template_id;
    var isFnet = String(tid || "").indexOf("functional_degree_network") === 0;
    if (!isFnet) return highlightFromTrainerTarget(target);
    // the functional graph is major-only: a minor-mode target must clear the
    // sync rather than land on the same-tonic MAJOR panel node
    if (String(target.mode || "").indexOf("minor") !== -1) {
      return setSyncHighlight([]);
    }
    var degId = degreeNodeIdFor(target.key, target.degreeNumber);
    if (!degId || !nodesById[degId]) return setSyncHighlight([]);
    var ids = [degId];
    var node = nodesById[degId];
    var group = node.data && node.data.functionGroup;
    var fnId = "fnet:fn:" + tonicOf(target.key) + ":" + group;
    if (group && nodesById[fnId]) ids.push(fnId);
    var nextId = degreeNodeIdFor(target.nextKey || target.key,
                                 target.nextDegreeNumber);
    if (nextId && nextId !== degId && nodesById[nextId]) ids.push(nextId);
    return setSyncHighlight(ids);
  }

  function exportState() {
    return {
      schema: data && data.schema,
      selectedNode: selectedNodeId,
      selectedEdge: selectedEdgeId,
      visibleNodes: visibleNodes().length,
      visibleEdges: visibleEdges().length,
      launchQueue: launchQueue.length,
      lastLaunch: lastLaunch ? Object.assign({}, lastLaunch) : null,
      syncNodes: syncNodeIds.slice(),
      syncPrimary: syncPrimaryId,
      searchHits: searchHits.size,
      completed: completedSet.size,
      visibleWhitelist: visibleWhitelist ? visibleWhitelist.size : null,
      filters: { kinds: Object.assign({}, filters.kinds),
        relations: Object.assign({}, filters.relations), search: filters.search },
      // -- bidirectional drill<->graph layer (additive) --
      mode: mode,
      projection: projection ? {
        projectionId: projection.projectionId,
        steps: (projection.steps || []).length,
        proxies: (projection.projectionNodes || []).length,
        drillFamily: projection.drillFamily,
        semanticGroup: projection.semanticGroup,
        sequenceSemantics: projection.sequenceSemantics,
      } : null,
      previewActive: !!previewProjection,
      currentOccurrence: currentOccurrenceId,
      nextOccurrence: nextOccurrenceId,
      visited: visitedOccurrenceIds.size,
      hostRequests: hostRequestQueue.length,
    };
  }

  // -- colours --------------------------------------------------------------
  function nodeColor(n) {
    var nc = ((data.legend && data.legend.nodeClasses) || [])
      .filter(function (c) { return c.kind === n.kind; })[0];
    return nc ? nc.color : "#94a3b8";
  }
  function edgeColor(visualClass) {
    return ({
      fifth: "#94a3b8", relative: "#38bdf8", resolve: "#fb7185",
      leading: "#c084fc", dominant: "#fbbf24", function: "#a78bfa",
      shared: "#22c55e", samepc: "#94a3b8", trainer: "#10b981",
      atlas: "#3b82f6", reserved: "#475569",
      // canonical theory relations used by the core / cadence / inversion templates
      membership: "#64748b", prepare: "#f59e0b", prolong: "#64748b",
      inversion: "#f43f5e", voicing: "#f472b6", substitute: "#f59e0b",
      // runtime projection overlay edges (sequence relations)
      "overlay-drill": "#eab308", "overlay-transpose": "#38bdf8",
      "overlay-enumerate": "#64748b", "overlay-voicing": "#f472b6",
    })[visualClass] || "#64748b";
  }
  // Dash style per edge visual class -- the SINGLE source of truth shared by the
  // left-panel legend swatch and (via CSS class .edge--<vc>) the SVG paths.
  //   solid : fifth, dominant, resolve, leading
  //   dashed: relative, shared, samepc, trainer, atlas
  //   dotted: function, reserved
  var EDGE_STYLE = {
    fifth: "solid", relative: "dashed", dominant: "solid", resolve: "solid",
    leading: "solid", shared: "dashed", samepc: "dashed", function: "dotted",
    trainer: "dashed", atlas: "dashed", reserved: "dotted",
  };
  function edgeStyleOf(visualClass) { return EDGE_STYLE[visualClass] || "solid"; }

  // ======================================================================
  // init
  // ======================================================================
  function init(payload) {
    data = payload || {};
    launchQueue = [];
    lastLaunch = null;
    syncNodeIds = []; syncPrimaryId = null;
    selectedNodeId = null; selectedEdgeId = null;
    searchHits = new Set();
    visibleWhitelist = null;
    completedSet = new Set();
    // reset the bidirectional drill<->graph layer
    mode = "explore";
    projection = null; previewProjection = null;
    occurrenceById = {}; occByVisualNode = {}; proxyById = {};
    visitedOccurrenceIds = new Set();
    currentOccurrenceId = null; nextOccurrenceId = null;
    correctnessByOccurrence = {};
    hostRequestQueue = [];
    indexPayload();
    filters = defaultFilters();
    // Let the payload's template name the header (this html shell is shared
    // by the v1 tonal graph and the functional degree network).
    var tpl = data.template || {};
    var ht = byId("hnTitle"), hsub = byId("hnSubtitle");
    if (ht && tpl.title) ht.textContent = tpl.title;
    if (hsub && tpl.description) hsub.textContent = tpl.description;
    renderControls();
    renderGraph();
    renderInfoPlaceholder();
    renderTimeline();
    renderProjectionSummary();
    return { ok: true, nodes: (data.nodes || []).length, edges: (data.edges || []).length };
  }

  // ======================================================================
  // Scene mode (GraphScene / graph_scene_router) -- the PRIMARY runtime path.
  //
  // The host routes the active exercise to a bounded, topic-specific
  // GraphScene and pushes it with setScene(); the legacy init/setProjection
  // API above stays for the standalone tonal-graph demo + its Node test.
  //
  // A scene is self-contained: nodes carry x/y + visualClass + entityType,
  // edges carry a LAYER (structure/theory/sequence/voice_leading/context),
  // occurrenceMap carries the running drill, layerDefinitions drive the
  // toggles. Rendered scene-natively with its OWN isolated state (so no legacy
  // pitch-class highlight can run in parallel), reusing the low-level helpers.
  // ======================================================================
  var SCENE_VC_COLOR = {
    slate: "#64748b", teal: "#14b8a6", amber: "#f59e0b", green: "#22c55e",
    rose: "#f43f5e", purple: "#a855f7", pink: "#ec4899", blue: "#38bdf8", yellow: "#facc15",
  };
  // "seventh" covers ALL seventh-chord qualities since G1b (the node's own
  // sublabel/quality names the specific one) — a "Dominant seventh" caption
  // would mislabel ii7 / Imaj7 / viiø7 nodes.
  var SCENE_ENTITY_LABEL = {
    key: "Key context", triad: "Diatonic triad", seventh: "Seventh chord",
    diminished: "Diminished", degree: "Abstract degree", function: "Function family",
    quality: "Quality class", inversion: "Inversion voicing", occurrence: "Overlay chord",
    score_slice: "Score chord",
  };
  // Entity types that are persistent CONTEXT anchors: a secondary style, never the current chord.
  var SCENE_CONTEXT_TYPES = { key: 1, function: 1, degree: 1, quality: 1 };

  var scene = null;                 // the active GraphScene dict (null in legacy/explore)
  var sceneNodeById = {};
  var sceneOccByNode = {};          // nodeId -> [occurrence]
  var sceneOccByIndex = {};         // sequenceIndex -> occurrence
  var sceneLayerVisible = {};       // layerId -> bool
  var sceneCurrentIdx = null;       // running trainer position (sequence index)
  var sceneVisitedIdx = new Set();
  var sceneCorrectByIdx = {};       // sequenceIndex -> "correct" | "incorrect"
  var sceneSelectedNodeId = null;
  // Detail-panel follow/pin model (plan section 7.2): the panel follows playback by default; a
  // pin freezes the SELECTED CONCEPT on one node while playback keeps updating graph highlights.
  var sceneDetailMode = "follow";   // "follow" | "pinned"
  var scenePinnedNodeId = null;

  function sceneNextIdx() { return sceneCurrentIdx == null ? 0 : sceneCurrentIdx + 1; }
  function sceneNodeColor(n) { return SCENE_VC_COLOR[n.visualClass] || "#64748b"; }
  function sceneCurrentOccurrence() {
    return sceneCurrentIdx == null ? null : (sceneOccByIndex[sceneCurrentIdx] || null);
  }
  // The honest "what lights up now" map for the current occurrence (family/context/edges),
  // derived server-side from the edge graph (plan section 4.2) -- never inferred from colour.
  function sceneCurrentActivation() {
    var o = sceneCurrentOccurrence();
    return o ? (o.activation || null) : null;
  }
  function _inList(list, id) { return !!list && list.indexOf(id) >= 0; }

  function indexScene() {
    sceneNodeById = {}; sceneOccByNode = {}; sceneOccByIndex = {};
    if (!scene) return;
    (scene.nodes || []).forEach(function (n) { sceneNodeById[n.id] = n; });
    (scene.occurrenceMap || []).forEach(function (o) {
      (sceneOccByNode[o.nodeId] = sceneOccByNode[o.nodeId] || []).push(o);
      sceneOccByIndex[o.sequenceIndex] = o;
    });
  }

  // Replace whatever scene is showing. Clears any legacy projection/sync state so no stale
  // highlight (or the old pitch-class sync) can run in parallel with the active scene.
  function setScene(payload) {
    scene = payload || null;
    sceneSelectedNodeId = null; sceneCurrentIdx = null;
    sceneDetailMode = "follow"; scenePinnedNodeId = null;   // a new scene clears any stale pin
    sceneVisitedIdx = new Set(); sceneCorrectByIdx = {};
    projection = null; previewProjection = null; syncNodeIds = []; syncPrimaryId = null;
    selectedNodeId = null; selectedEdgeId = null;
    mode = "scene";
    if (!scene) return clearScene("no scene");
    indexScene();
    // an honest fail-closed scene: prominent "no graph" view, trainer keeps running
    if (scene.sceneType === "unsupported" || !(scene.nodes || []).length) {
      return renderSceneUnsupportedView(scene.title, (scene.warnings || []).join(" ")
        || scene.subtitle || "");
    }
    sceneLayerVisible = {};
    (scene.layerDefinitions || []).forEach(function (l) {
      sceneLayerVisible[l.id] = !!l.defaultVisible;
    });
    renderSceneHeader(scene);
    renderSceneControls();
    renderSceneGraph();
    renderSceneTimeline();
    renderSceneDetail();
    return sceneExportState();
  }

  function clearScene(reason) {
    scene = null; sceneNodeById = {}; sceneOccByNode = {}; sceneOccByIndex = {};
    sceneCurrentIdx = null; sceneVisitedIdx = new Set(); sceneCorrectByIdx = {};
    sceneSelectedNodeId = null; sceneDetailMode = "follow"; scenePinnedNodeId = null; mode = "scene";
    return renderSceneUnsupportedView("No harmonic graph for this exercise", reason || "");
  }

  // The honest fail-closed view: a prominent "no graph" message; the trainer keeps running.
  function renderSceneUnsupportedView(title, why) {
    renderSceneHeader({ title: title || "No harmonic graph for this exercise", subtitle: "",
      sceneType: "unsupported", pedagogicalGoal: "", warnings: why ? [why] : [] });
    var center = byId("hnCenter");
    if (center) {
      clear(center);
      center.appendChild(el("div", { class: "hnUnsupported" }, [
        el("div", { class: "hnUnsupportedTitle",
          text: "No suitable harmonic graph is available for this exercise yet." }),
        el("div", { class: "hnUnsupportedWhy", text: why || "" }),
      ]));
    }
    var left = byId("hnLeft"); if (left) clear(left);
    var tl = byId("hnTimeline"); if (tl) clear(tl);
    var sum = byId("hnSummary"); if (sum) clear(sum);
    var right = byId("hnRight");
    if (right) {
      clear(right);
      right.appendChild(el("div", { class: "placeholder",
        text: "The trainer keeps running — there is just no honest harmonic graph for this "
            + "exercise type yet." }));
    }
    return sceneExportState();
  }

  // The host pushes the running trainer position each poll (does NOT rebuild the scene).
  function updateOccurrenceState(state) {
    if (!scene || !state) return sceneExportState();
    var idx = state.sequenceIndex;
    if (idx == null && state.occurrenceId != null) {
      (scene.occurrenceMap || []).forEach(function (o) {
        if (o.occurrenceId === state.occurrenceId) idx = o.sequenceIndex;
      });
    }
    if (idx != null && sceneOccByIndex[idx]) {
      if (sceneCurrentIdx != null && sceneCurrentIdx !== idx) sceneVisitedIdx.add(sceneCurrentIdx);
      sceneCurrentIdx = idx;
      if (state.correct === true) sceneCorrectByIdx[idx] = "correct";
      else if (state.correct === false) sceneCorrectByIdx[idx] = "incorrect";
    }
    renderSceneGraph();
    renderSceneTimeline();
    // The detail panel follows playback automatically (plan section 7.1); a pin freezes it while
    // the graph highlights above keep updating (plan section 7.2).
    if (sceneDetailMode !== "pinned") renderSceneDetail();
    return sceneExportState();
  }

  function requestSceneSeek(sequenceIndex) {
    var o = sceneOccByIndex[sequenceIndex];
    return enqueueHostRequest({ type: "seek", sequenceIndex: sequenceIndex,
      occurrenceId: o ? o.occurrenceId : null });
  }

  // The sequence index a click on this node should seek to, or null when it must not seek: a
  // family / key-context anchor inspects only (plan section 5) -- an explicit entity-type gate,
  // not a side effect of the occurrence map being empty for anchors.
  function sceneNodeSeekIndex(id) {
    var n = sceneNodeById[id];
    if (!n || SCENE_CONTEXT_TYPES[n.entityType]) return null;
    var occs = sceneOccByNode[id];
    return (occs && occs.length) ? occs[0].sequenceIndex : null;
  }

  function renderSceneHeader(s) {
    var t = byId("hnTitle"), sub = byId("hnSubtitle"), meta = byId("hnSceneMeta");
    if (t) t.textContent = (s && s.title) || "Harmonic scene";
    if (sub) sub.textContent = (s && s.subtitle) || "";
    if (!meta) return;
    clear(meta);
    if (!s) return;
    meta.appendChild(el("span", { class: "sceneChip sceneChip--" + (s.sceneType || ""),
      text: String(s.sceneType || "").replace(/_/g, " ") }));
    if (s.pedagogicalGoal) meta.appendChild(el("span", { class: "sceneGoal", text: s.pedagogicalGoal }));
    (s.warnings || []).forEach(function (w) {
      meta.appendChild(el("div", { class: "sceneWarn", text: w }));
    });
  }

  function sceneEntityColorByType(et) {
    var ns = scene ? (scene.nodes || []) : [];
    for (var i = 0; i < ns.length; i++) if (ns[i].entityType === et) return sceneNodeColor(ns[i]);
    return "#64748b";
  }

  function renderSceneControls() {
    var root = byId("hnLeft"); if (!root) return; clear(root);
    if (!scene) return;
    var lg = el("div", { class: "ctlGroup" }, [el("h2", { text: "Layers" })]);
    (scene.layerDefinitions || []).forEach(function (l) {
      var cb = el("input", { type: "checkbox" });
      cb.checked = !!sceneLayerVisible[l.id];
      cb.addEventListener("change", function () {
        sceneLayerVisible[l.id] = !!cb.checked; renderSceneGraph();
      });
      lg.appendChild(el("label", { class: "toggleRow" }, [cb,
        el("span", { class: "relLabel" }, [el("span", { text: l.label }),
          el("small", { text: l.description || l.id })])]));
    });
    root.appendChild(lg);
    var counts = (scene.counts && scene.counts.nodesByType) || {};
    var eg = el("div", { class: "ctlGroup" }, [el("h2", { text: "Node types" })]);
    Object.keys(counts).forEach(function (et) {
      eg.appendChild(el("div", { class: "toggleRow" }, [
        el("span", { class: "swatch", style: "background:" + sceneEntityColorByType(et) }),
        el("span", { class: "relLabel" },
          [(SCENE_ENTITY_LABEL[et] || et) + " (" + counts[et] + ")"])]));
    });
    root.appendChild(eg);
  }

  function sceneVisibleEdges() {
    if (!scene) return [];
    return (scene.edges || []).filter(function (e) {
      return sceneLayerVisible[e.layer] !== false
        && sceneNodeById[e.source] && sceneNodeById[e.target];
    });
  }

  function sceneNodeStateClass(n) {
    var c = "";
    var occs = sceneOccByNode[n.id] || [];
    var act = sceneCurrentActivation();
    if (occs.length) c += " in-projection";
    if (SCENE_CONTEXT_TYPES[n.entityType]) c += " is-anchor";   // persistent secondary context
    // --- secondary playback context, from the honest activation map (plan sections 4, 5) ---
    // A broad-function-family node haloes while one of its members plays; the key anchor stays a
    // low-intensity context. These are distinct from the current CHORD's own strong state below.
    if (act) {
      if (_inList(act.familyNodeIds, n.id)) c += " is-current-family";
      if (_inList(act.contextNodeIds, n.id)) c += " is-current-context";
    }
    if (occs.length) {
      var cur = sceneCurrentIdx, nxt = sceneNextIdx();
      var isCurrent = cur != null && occs.some(function (o) { return o.sequenceIndex === cur; });
      var isNext = occs.some(function (o) { return o.sequenceIndex === nxt; });
      var isVisited = occs.some(function (o) { return sceneVisitedIdx.has(o.sequenceIndex); });
      // the current CONCRETE chord: strongest state (is-current kept for back-compat/tests).
      if (isCurrent) c += " is-current is-current-occurrence";
      else if (isNext) c += " is-next";
      else if (isVisited) c += " is-visited";
      var corr = cur != null ? sceneCorrectByIdx[cur] : null;
      if (isCurrent && corr === "correct") c += " is-correct";
      else if (isCurrent && corr === "incorrect") c += " is-incorrect";
      c += mappingStatusClass(occs[0].mappingStatus);
    }
    if (n.entityType === "occurrence") c += " is-proxy";
    if (n.id === sceneSelectedNodeId) c += " sel";
    return c;
  }

  // The membership / sequence / theory edge that is active for the current occurrence gets a
  // distinct state class each (plan section 4/6): a membership edge lights as STRUCTURE, never as
  // harmonic motion.  Derived from the occurrence's activation edge-id lists.
  function sceneEdgeStateClass(e) {
    var act = sceneCurrentActivation();
    if (!act) return "";
    if (_inList(act.structureEdgeIds, e.id)) return " is-current-structure-edge";
    if (_inList(act.sequenceEdgeIds, e.id)) return " is-current-sequence-edge";
    if (_inList(act.theoryEdgeIds, e.id)) return " is-current-theory-edge";
    return "";
  }

  function renderSceneGraph() {
    var root = byId("hnCenter"); if (!root) return; clear(root);
    if (!scene) return;
    if (!document.createElementNS) {                 // headless summary (Node test)
      root.appendChild(el("div", { class: "hnFallback", dataset: { scene: scene.sceneType },
        text: (scene.nodes || []).length + " nodes, " + (scene.edges || []).length + " edges, " +
              (scene.occurrenceMap || []).length + " occurrences" +
              (sceneCurrentIdx != null ? " @" + sceneCurrentIdx : "") }));
      return;
    }
    var s = svg("svg", { id: "hnSvg", viewBox: sceneViewBox() });
    var defs = svg("defs", {}); var used = {};
    sceneVisibleEdges().forEach(function (e) { used[e.visualClass] = edgeColor(e.visualClass); });
    Object.keys(used).forEach(function (vc) {
      var m = svg("marker", { id: "sarw-" + vc, viewBox: "0 0 10 10", refX: "9", refY: "5",
        markerWidth: "6", markerHeight: "6", orient: "auto-start-reverse" });
      m.appendChild(svg("path", { d: "M0,0 L10,5 L0,10 z", fill: used[vc] }));
      defs.appendChild(m);
    });
    s.appendChild(defs);
    sceneVisibleEdges().forEach(function (e) {
      var a = sceneNodeById[e.source], b = sceneNodeById[e.target];
      var p = svg("path", {
        class: "hnEdge edge edge--" + e.visualClass + " scene-layer--" + e.layer
          + sceneEdgeStateClass(e),
        d: edgePath(a, b), stroke: edgeColor(e.visualClass) });
      if (e.directed) p.setAttribute("marker-end", "url(#sarw-" + e.visualClass + ")");
      p.addEventListener("click", function () { selectSceneNode(e.source); });
      s.appendChild(p);
    });
    (scene.nodes || []).forEach(function (n) {
      var g = svg("g", { class: "hnNode" + sceneNodeStateClass(n), "data-id": n.id,
        transform: "translate(" + n.x + "," + n.y + ")" });
      g.appendChild(svg("circle", { r: n.radius || 18, fill: sceneNodeColor(n) }));
      var tx = svg("text", n.sublabel ? { dy: "-3" } : {});
      tx.textContent = n.label; g.appendChild(tx);
      if (n.sublabel) {
        var ts = svg("text", { class: "sub", dy: "9" });
        ts.textContent = n.sublabel; g.appendChild(ts);
      }
      g.addEventListener("click", function () {
        selectSceneNode(n.id);
        var si = sceneNodeSeekIndex(n.id);
        if (si != null) requestSceneSeek(si);
      });
      s.appendChild(g);
    });
    root.appendChild(s);
  }

  function renderSceneTimeline() {
    var root = byId("hnTimeline"); if (!root) return; clear(root);
    if (!scene || !(scene.occurrenceMap || []).length) return;
    var nxt = sceneNextIdx();
    scene.occurrenceMap.forEach(function (o) {
      var cls = "occChip";
      if (o.sequenceIndex === sceneCurrentIdx) cls += " is-current";
      else if (o.sequenceIndex === nxt) cls += " is-next";
      else if (sceneVisitedIdx.has(o.sequenceIndex)) cls += " is-visited";
      cls += mappingStatusClass(o.mappingStatus);
      var corr = sceneCorrectByIdx[o.sequenceIndex];
      if (corr) cls += (corr === "correct" ? " is-correct" : " is-incorrect");
      root.appendChild(el("div", { class: cls, dataset: { idx: String(o.sequenceIndex) },
        onClick: (function (i) { return function () { requestSceneSeek(i); }; })(o.sequenceIndex) },
        [
          el("span", { class: "occIdx", text: String(o.sequenceIndex + 1) }),
          el("span", { class: "occRoman", text: o.roman || "" }),
          el("span", { class: "occChord", text: o.chordSymbol || "" }),
          el("span", { class: "occKey", text: o.keyContext || "" }),
          el("span", { class: "occStatus occStatus--" + o.mappingStatus, text: o.mappingStatus }),
        ]));
    });
  }

  // Retained name (called nowhere critical now) -> the follow/pin renderer.
  function renderSceneInfoPlaceholder() { renderSceneDetail(); }

  function _detailRows(pairs, into) {
    pairs.forEach(function (kv) {
      if (kv[1] == null || kv[1] === "") return;
      into.appendChild(el("div", { class: "detailRow" },
        [el("b", { text: kv[0] + ": " }), el("span", { text: String(kv[1]) })]));
    });
  }

  // The abstraction hierarchy (plan section 1), compact, for a chord occurrence:
  //   Em  ->  iii in C major  ->  mediant (specific role)  ->  Tonic-related family (broad)
  function sceneHierarchyRow(d, o) {
    var steps = [];
    if (o && (o.chordSymbol || o.roman)) steps.push(o.chordSymbol || o.roman);
    if (o && o.roman && o.keyContext) steps.push(o.roman + " in " + o.keyContext);
    if (d.specificRole) steps.push((d.specificRoleLabel || d.specificRole) + " (specific role)");
    if (d.broadFamilyLabel || d.broadFamily) {
      steps.push((d.broadFamilyLabel || d.broadFamily) + " (broad family)");
    }
    return steps.length >= 2 ? el("div", { class: "hierRow", text: steps.join("  →  ") }) : null;
  }

  // NOW PLAYING: the current occurrence, auto-updated on every playback tick (plan sections 7.1, 8).
  function sceneNowPlayingSection(o) {
    var d = o.detail || {};
    var sect = el("div", { class: "sect nowPlaying" });
    sect.appendChild(el("div", { class: "sectTag", text: "NOW PLAYING" }));
    sect.appendChild(el("h2", { text: (d.chordSymbol || o.chordSymbol || o.roman || "")
      + (o.roman ? "  ·  " + o.roman : "") }));
    if (o.keyContext) sect.appendChild(el("div", { class: "keyline", text: o.keyContext
      + (o.occurrenceRole ? "  ·  " + o.occurrenceRole + " chord" : "") }));
    var h = sceneHierarchyRow(d, o); if (h) sect.appendChild(h);
    // the two-level identity kept explicitly separate (plan sections 1, 8): specific role vs family
    _detailRows([
      ["Chord tones", (d.chordTones || []).join(" ")],
      ["Quality", d.quality],
      ["Interval layer", d.intervalLayer],
      ["Scale-degree name", d.scaleDegreeName],
      ["Specific role", d.specificRoleLabel || d.specificRole],
      ["Broad family", d.broadFamilyLabel || d.broadFamily],
      ["Family membership", d.familyMembershipType],
    ], sect);
    if (d.familyMembershipExplanation) {
      sect.appendChild(el("div", { class: "expl", text: d.familyMembershipExplanation }));
    }
    var prev = sceneOccByIndex[o.sequenceIndex - 1];
    if (prev) _detailRows([["From previous", prev.nextExplanation]], sect);
    _detailRows([
      ["To next", o.nextExplanation || d.relationToNext],
      ["Sequence edge", o.nextSequenceRelation],
      ["Theory edge", o.nextTheoryRelation],
    ], sect);
    return sect;
  }

  // SELECTED / PINNED CONCEPT: inspect one node (chord, family, key, ...) (plan sections 7.2, 7.3).
  function sceneConceptSection(title, n) {
    var sect = el("div", { class: "sect selectedConcept" });
    sect.appendChild(el("div", { class: "sectTag", text: title }));
    sect.appendChild(el("span", { class: "kind k-" + n.entityType,
      text: SCENE_ENTITY_LABEL[n.entityType] || n.entityType }));
    sect.appendChild(el("h2", { text: n.label }));
    if (n.entityType === "function") {
      // a broad-function-family node names its members' SPECIFIC roles (plan section 2.1)
      if (n.broadFunctionFamilyLabel) {
        sect.appendChild(el("div", { class: "familyLine", text: n.broadFunctionFamilyLabel }));
      }
      ((n.data && n.data.memberRoles) || []).forEach(function (m) {
        sect.appendChild(el("div", { class: "detailRow" }, [
          el("b", { text: m.roman + ": " }),
          el("span", { text: (m.specificRoleLabel || m.specificRole || "")
            + (m.contextual ? " (context-dependent)" : "") })]));
      });
    } else {
      _detailRows([
        ["Roman", n.roman], ["Key", n.keyContext], ["Quality", n.quality],
        ["Chord tones", (n.chordTones || []).join(" ")],
        ["Scale-degree name", n.scaleDegreeName],
        ["Specific role", n.specificRoleLabel || n.specificRole],
        ["Broad family", n.broadFunctionFamilyLabel || n.broadFunctionFamily],
      ], sect);
    }
    if (n.explanation) sect.appendChild(el("div", { class: "expl", text: n.explanation }));
    return sect;
  }

  function renderSceneDetailControls() {
    var bar = el("div", { class: "detailModeBar" });
    var follow = el("button", { class: "modeBtn" + (sceneDetailMode === "follow" ? " is-active" : ""),
      text: "Follow current" });
    follow.addEventListener("click", function () {
      sceneDetailMode = "follow"; scenePinnedNodeId = null; renderSceneDetail(); renderSceneGraph();
    });
    var pin = el("button", { class: "modeBtn" + (sceneDetailMode === "pinned" ? " is-active" : ""),
      text: "Pin selected" });
    pin.addEventListener("click", function () {
      if (sceneSelectedNodeId) { sceneDetailMode = "pinned"; scenePinnedNodeId = sceneSelectedNodeId; }
      renderSceneDetail(); renderSceneGraph();
    });
    bar.appendChild(follow); bar.appendChild(pin);
    bar.appendChild(el("span", { class: "detailModeStatus",
      text: sceneDetailMode === "pinned" ? "Pinned selection" : "Following current chord" }));
    return bar;
  }

  // The follow/pin detail panel (plan section 7). Follow: NOW PLAYING auto-updates + an optional
  // SELECTED CONCEPT for a clicked node. Pinned: a frozen PINNED SELECTION (graph still updates).
  function renderSceneDetail() {
    var root = byId("hnRight"); if (!root) return; clear(root);
    if (!scene) return;
    root.appendChild(renderSceneDetailControls());
    if (sceneDetailMode === "pinned" && scenePinnedNodeId && sceneNodeById[scenePinnedNodeId]) {
      root.appendChild(sceneConceptSection("PINNED SELECTION", sceneNodeById[scenePinnedNodeId]));
      return;
    }
    var cur = sceneCurrentOccurrence();
    if (cur) root.appendChild(sceneNowPlayingSection(cur));
    else root.appendChild(el("div", { class: "placeholder",
      text: "Following current chord — the panel updates as the trainer plays. "
          + "Click a node to inspect a concept." }));
    if (sceneSelectedNodeId && sceneNodeById[sceneSelectedNodeId]
        && (!cur || sceneSelectedNodeId !== cur.nodeId)) {
      root.appendChild(sceneConceptSection("SELECTED CONCEPT", sceneNodeById[sceneSelectedNodeId]));
    }
  }

  function selectSceneNode(id) {
    var n = sceneNodeById[id]; if (!n) return null;
    sceneSelectedNodeId = id;
    renderSceneGraph();
    renderSceneDetail();
    return id;
  }

  function sceneViewBox() {
    var pad = 46, ns = scene ? (scene.nodes || []) : [];
    if (!ns.length) return "-360 -360 720 720";
    var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    ns.forEach(function (n) {
      var r = (n.radius || 18) + 16;
      minX = Math.min(minX, n.x - r); maxX = Math.max(maxX, n.x + r);
      minY = Math.min(minY, n.y - r); maxY = Math.max(maxY, n.y + r);
    });
    return (minX - pad) + " " + (minY - pad) + " " +
           (maxX - minX + 2 * pad) + " " + (maxY - minY + 2 * pad);
  }

  function sceneExportState() {
    return {
      mode: mode,
      sceneId: scene && scene.sceneId,
      sceneType: scene && scene.sceneType,
      title: scene && scene.title,
      nodes: scene ? (scene.nodes || []).length : 0,
      edges: scene ? (scene.edges || []).length : 0,
      visibleEdges: sceneVisibleEdges().length,
      occurrences: scene ? (scene.occurrenceMap || []).length : 0,
      currentIndex: sceneCurrentIdx,
      nextIndex: scene ? sceneNextIdx() : null,
      visited: sceneVisitedIdx.size,
      selectedNode: sceneSelectedNodeId,
      detailMode: sceneDetailMode,
      pinnedNode: scenePinnedNodeId,
      layers: Object.assign({}, sceneLayerVisible),
      hostRequests: hostRequestQueue.length,
      warnings: scene ? (scene.warnings || []).slice() : [],
    };
  }

  var HarmonicNetwork = {
    init: init,
    // -- scene mode (primary runtime path) --
    setScene: setScene,
    clearScene: clearScene,
    updateOccurrenceState: updateOccurrenceState,
    requestSceneSeek: requestSceneSeek,
    selectSceneNode: selectSceneNode,
    // follow/pin detail-panel controls (plan section 7.2)
    sceneFollowCurrent: function () {
      sceneDetailMode = "follow"; scenePinnedNodeId = null;
      renderSceneDetail(); renderSceneGraph(); return sceneExportState();
    },
    scenePinSelected: function () {
      if (sceneSelectedNodeId) { sceneDetailMode = "pinned"; scenePinnedNodeId = sceneSelectedNodeId; }
      renderSceneDetail(); renderSceneGraph(); return sceneExportState();
    },
    sceneState: sceneExportState,
    sceneNodeIds: function () { return Object.keys(sceneNodeById); },
    sceneNodeById: function (id) { return sceneNodeById[id]; },
    // introspection seams (used by the headless scene test, where the SVG isn't rendered):
    sceneNodeClass: function (id) {
      var n = sceneNodeById[id]; return n ? sceneNodeStateClass(n) : null;
    },
    sceneEdgeClass: function (id) {
      var e = (scene && (scene.edges || []).filter(function (x) { return x.id === id; })[0]);
      return e ? sceneEdgeStateClass(e) : null;
    },
    sceneNodeSeekIndex: sceneNodeSeekIndex,
    selectNode: selectNode,
    selectEdge: selectEdge,
    setFilter: setFilter,
    clearSelection: clearSelection,
    takeLaunch: takeLaunch,
    launch: launch,                                  // exposed for host/tests
    pendingCount: function () { return launchQueue.length; },
    lastLaunch: function () { return lastLaunch ? Object.assign({}, lastLaunch) : null; },
    highlightFromTrainerTarget: highlightFromTrainerTarget,
    highlightFromAtlasSync: highlightFromAtlasSync,
    highlightFromDegreeTarget: highlightFromDegreeTarget,
    // -- bidirectional drill<->graph API (plan section 18) --
    setMode: setMode,
    setProjection: setProjection,
    clearProjection: clearProjection,
    updateFlowState: updateFlowState,
    previewLaunch: previewLaunch,
    takeHostRequest: takeHostRequest,
    requestSeek: requestSeek,
    setVisibleNodes: setVisibleNodes,
    markCompleted: markCompleted,
    completedIds: completedIds,
    clearSync: clearSync,
    syncNodes: function () { return syncNodeIds.slice(); },
    edgeStyleOf: edgeStyleOf,                         // "solid"|"dashed"|"dotted"
    exportState: exportState,
    // -- inspection helpers (used by the headless test) --
    nodeIds: function () { return Object.keys(nodesById); },
    nodeById: function (id) { return nodesById[id]; },
    neighborsOf: function (id) { return Array.from(neighborsOf(id)); },
    visibleNodeCount: function () { return visibleNodes().length; },
    visibleEdgeCount: function () { return visibleEdges().length; },
    counts: function () { return data && data.counts; },
  };
  window.HarmonicNetwork = HarmonicNetwork;
})();
