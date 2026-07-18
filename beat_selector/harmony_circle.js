/*
 * Interactive Circle of Fifths -- the first visual module of the Harmony Atlas.
 *
 * Rendering only: it consumes the JSON payload built by harmony.circle_payload
 * (window.CIRCLE_DATA, injected by the host) and draws an interactive SVG circle
 * of fifths inside the Harmony Trainer window. It never builds MusicXML or
 * re-derives theory -- clicking a launch shortcut enqueues a spec-like request
 * that the Python trainer turns into a HarmonyExerciseSpec.
 *
 * It is safe to inject / init repeatedly (like harmony_trainer.js): init()
 * rebuilds cleanly and never stacks event listeners.
 *
 * Public: window.HarmonyCircle
 *   init(payload)
 *   updateFromTrainerState(state)   // sync highlight to the live target chord
 *   highlightKey(key, mode)
 *   highlightChord(chordSymbol)
 *   highlightDegree(roman)
 *   clearHighlight()
 *   onCellClick(callback)           // fired on every interaction
 *   takeLaunch()                    // host polls this for click->exercise requests
 *   highlightState()                // current highlight (for tests/inspection)
 */
(function () {
  "use strict";

  var SVGNS = "http://www.w3.org/2000/svg";

  // -- state ---------------------------------------------------------------
  var data = null;
  var byKey = {};            // "G|major" -> key entry
  var selKey = null, selMode = null, selDegree = null, selFunction = null;
  var hi = {};               // current sync highlight {key,mode,roman,chordSymbol,functionClass,degree}
  var cheatOn = false;
  var launchQueue = [];
  var labQueue = [];         // "Open ... lab" requests (only when data.labLaunch)
  var clickCbs = [];
  var cells = [];            // [{kind,key,mode,roman,el}] for highlight re-apply
  var evtHandler = null;     // bound harmonytrainer:targetchange listener

  // -- helpers -------------------------------------------------------------
  function keyId(key, mode) { return key + "|" + mode; }
  function entryFor(key, mode) { return byKey[keyId(key, mode)] || null; }
  function modeWord(mode) { return mode === "natural_minor" ? "minor" : "major"; }
  function tonicOf(key) { return String(key || "").split(" ")[0]; }

  // Function vocabulary comes from the payload cheatsheet (built from
  // harmony.harmonic_roles, the single vocabulary source) -- no legend text or
  // label->class table is hardcoded here (ticket 01 / plan F1).
  function functionClasses() {
    return (data && data.cheatsheet && data.cheatsheet.functionClasses) || [];
  }
  function familyEntryFor(cls) {
    var out = null;
    functionClasses().forEach(function (fc) { if (fc["class"] === cls) out = fc; });
    return out;
  }

  function el(tag, props, kids) {
    var n = document.createElement(tag);
    applyProps(n, props);
    (kids || []).forEach(function (k) {
      if (k == null) return;
      n.appendChild(typeof k === "string" ? textSpan(k) : k);
    });
    return n;
  }
  function textSpan(t) { var s = document.createElement("span"); s.textContent = t; return s; }

  function svg(tag, props, kids) {
    var n = document.createElementNS(SVGNS, tag);
    applyProps(n, props, true);
    (kids || []).forEach(function (k) { if (k != null) n.appendChild(k); });
    return n;
  }

  function applyProps(n, props, isSvg) {
    props = props || {};
    Object.keys(props).forEach(function (k) {
      if (k === "class") { if (isSvg) n.setAttribute("class", props[k]); else n.className = props[k]; }
      else if (k === "text") { n.textContent = props[k]; }
      else if (k === "html") { n.innerHTML = props[k]; }
      else if (k === "onClick") { n.addEventListener("click", props[k]); }
      else if (k === "dataset") {
        var ds = props[k];
        Object.keys(ds).forEach(function (d) { if (n.dataset) n.dataset[d] = ds[d]; });
      } else if (n.setAttribute) { n.setAttribute(k, props[k]); }
    });
  }

  function polar(cx, cy, r, deg) {
    var a = (deg - 90) * Math.PI / 180;
    return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
  }

  function root() { return document.getElementById("hcRoot") || document.body; }

  // -- styles (self-injected; colours via CSS vars, one source) ------------
  function injectStyles() {
    if (document.getElementById("hcStyle")) return;
    var st = document.createElement("style");
    st.id = "hcStyle";
    st.textContent = [
      "#hcRoot{--fnT:#16a34a;--fnS:#d97706;--fnD:#dc2626;--line:#e2e8f0;--muted:#64748b;",
      "  font:12px/1.4 system-ui,Segoe UI,Roboto,sans-serif;color:#0f172a;padding:6px;height:100%;overflow:auto;}",
      "#hcBar{display:flex;gap:6px;align-items:center;margin-bottom:4px;}",
      "#hcBar h3{margin:0;font-size:14px;color:#0b3a53;flex:1;}",
      "#hcBar button{cursor:pointer;border:1px solid var(--line);background:#fff;border-radius:6px;padding:3px 8px;font:12px system-ui;}",
      "#hcBar button.active{background:#dbeafe;border-color:#2563eb;color:#1e3a8a;font-weight:600;}",
      "#hcSvgWrap svg{width:100%;height:auto;max-height:52vh;display:block;}",
      ".hcCell{cursor:pointer;}",
      ".hcCell .bg{fill:#fff;stroke:#cbd5e1;stroke-width:1;}",
      ".hcCell text{font:11px system-ui;fill:#0f172a;text-anchor:middle;dominant-baseline:central;pointer-events:none;}",
      ".hcCell.major .bg{fill:#f8fafc;}",
      ".hcCell.minor .bg{fill:#eef2ff;}",
      ".hcCell:hover .bg{stroke:#2563eb;stroke-width:2;}",
      ".hcCell.sel .bg{stroke:#2563eb;stroke-width:3;}",
      ".hcCell.cur .bg{stroke:#16a34a;stroke-width:3;}",
      ".hcCell.dim .bg{opacity:.45;}",
      ".hcCell.fn-T .bg{fill:color-mix(in srgb,var(--fnT) 18%,#fff);}",
      ".hcCell.fn-S .bg{fill:color-mix(in srgb,var(--fnS) 18%,#fff);}",
      ".hcCell.fn-D .bg{fill:color-mix(in srgb,var(--fnD) 18%,#fff);}",
      "#hcDetail{border:1px solid var(--line);border-radius:8px;padding:8px;margin-top:6px;background:#fff;}",
      "#hcDetail .big{font-size:14px;font-weight:700;color:#0b3a53;margin-bottom:4px;}",
      "#hcDetail .row{margin:2px 0;}",
      "#hcDetail .lbl{color:var(--muted);display:inline-block;min-width:74px;}",
      ".hcChips{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px;}",
      ".hcChip{cursor:pointer;border:1px solid var(--line);border-radius:999px;padding:2px 8px;background:#fff;}",
      ".hcChip:hover{background:#dbeafe;}",
      ".hcChip.fn-T{border-color:var(--fnT);} .hcChip.fn-S{border-color:var(--fnS);} .hcChip.fn-D{border-color:var(--fnD);}",
      ".hcShort{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;}",
      ".hcShort button{cursor:pointer;border:1px solid #2563eb;background:#eff6ff;color:#1e3a8a;border-radius:6px;padding:4px 8px;font:12px system-ui;}",
      ".hcShort button:hover{background:#dbeafe;}",
      "#hcCheat{border:1px solid var(--line);border-radius:8px;padding:8px;margin-top:6px;background:#fff;}",
      "#hcCheat h4{margin:6px 0 3px;font-size:12px;color:#0b3a53;}",
      "#hcCheat table{border-collapse:collapse;font-size:11px;} #hcCheat td,#hcCheat th{border:1px solid var(--line);padding:2px 6px;}",
      ".legend span{display:inline-block;margin-right:10px;}",
      ".sw{display:inline-block;width:10px;height:10px;border-radius:2px;vertical-align:middle;margin-right:3px;}",
    ].join("\n");
    document.head.appendChild(st);
  }

  // -- skeleton ------------------------------------------------------------
  function buildSkeleton() {
    var r = root();
    r.innerHTML = "";
    var bar = el("div", { id: "hcBar" }, []);
    bar.appendChild(el("h3", { text: "Circle of Fifths" }));
    bar.appendChild(el("button", { id: "hcCheatBtn", text: "Cheatsheet",
      onClick: function () { cheatOn = !cheatOn; renderCheat(); syncCheatBtn(); } }));
    r.appendChild(bar);
    r.appendChild(el("div", { id: "hcSvgWrap" }, []));
    r.appendChild(el("div", { id: "hcDetail" }, []));
    r.appendChild(el("div", { id: "hcCheat", style: "display:none" }, []));
  }
  function syncCheatBtn() {
    var b = document.getElementById("hcCheatBtn");
    if (b && b.classList) b.classList.toggle("active", cheatOn);
  }

  // -- circle render -------------------------------------------------------
  function renderCircle() {
    var wrap = document.getElementById("hcSvgWrap");
    if (!wrap) return;
    wrap.innerHTML = "";
    cells = [];
    if (!document.createElementNS) {          // stubbed DOM: keep logical state only
      wrap.appendChild(el("div", { class: "meta",
        text: (data.majorKeys || []).length + " major keys" }));
      return;
    }
    var W = 360, C = 180;
    var s = svg("svg", { viewBox: "0 0 " + W + " " + W }, []);

    addRing(s, C, 152, 20, data.circleOrderMajor || [], "major");
    addRing(s, C, 112, 16, data.circleOrderMinor || [], "natural_minor");

    // selected key's 7 triads as an inner ring
    if (selKey && selMode) {
      var entry = entryFor(selKey, selMode);
      if (entry) addTriadRing(s, C, 66, 17, entry);
    }
    wrap.appendChild(s);
    applyHighlightClasses();
  }

  function addRing(s, C, R, r, order, mode) {
    var n = order.length || 12;
    order.forEach(function (key, i) {
      var p = polar(C, C, R, i * (360 / n));
      var label = mode === "major" ? key : key + "m";
      var cell = svg("g", {
        class: "hcCell " + (mode === "major" ? "major" : "minor"),
        dataset: { key: key, mode: mode, kind: "key" },
        onClick: function () { selectKey(key, mode, true); },
      }, [
        svg("circle", { class: "bg", cx: p.x, cy: p.y, r: r }),
        svg("text", { x: p.x, y: p.y, text: label }),
      ]);
      s.appendChild(cell);
      cells.push({ kind: "key", key: key, mode: mode, el: cell });
    });
  }

  function addTriadRing(s, C, R, r, entry) {
    var triads = entry.triads || [];
    triads.forEach(function (t, i) {
      var p = polar(C, C, R, i * (360 / triads.length));
      var cell = svg("g", {
        class: "hcCell triad fn-" + t.functionClass,
        dataset: { roman: t.degree, kind: "triad" },
        onClick: function () { selectDegree(t.degree, true); },
      }, [
        svg("circle", { class: "bg", cx: p.x, cy: p.y, r: r }),
        svg("text", { x: p.x, y: p.y, text: t.degree }),
      ]);
      s.appendChild(cell);
      cells.push({ kind: "triad", roman: t.degree, fnClass: t.functionClass,
        fn: t.functionLabel, sym: t.chordSymbol, el: cell });
    });
  }

  // -- highlight application ----------------------------------------------
  function applyHighlightClasses() {
    cells.forEach(function (c) {
      if (!c.el || !c.el.classList) return;
      c.el.classList.remove("sel", "cur", "dim");
      if (c.kind === "key") {
        if (c.key === selKey && c.mode === selMode) c.el.classList.add("sel");
        if (hi.key && tonicOf(hi.key) === c.key && hi.mode === c.mode) c.el.classList.add("cur");
      } else if (c.kind === "triad") {
        if (selDegree && c.roman === selDegree) c.el.classList.add("sel");
        if (hi.roman && c.roman === hi.roman) c.el.classList.add("cur");
        if (selFunction && c.fnClass !== selFunction) c.el.classList.add("dim");
      }
    });
  }

  // -- detail panel --------------------------------------------------------
  function shortcut(label, spec) {
    return el("button", { text: label, onClick: function () { requestLaunch(spec); } });
  }

  function renderDetail() {
    var d = document.getElementById("hcDetail");
    if (!d) return;
    d.innerHTML = "";
    if (!selKey) {
      d.appendChild(el("div", { class: "row", text: "Click a key to see its scale and triads." }));
      return;
    }
    var entry = entryFor(selKey, selMode);
    if (!entry) return;
    var mw = modeWord(selMode);
    var keyStr = selKey + " " + mw;

    d.appendChild(el("div", { class: "big", text: keyStr }));
    d.appendChild(row("Mode", mw));
    d.appendChild(row("Scale", (entry.scale || []).join(" ")));
    d.appendChild(row(selMode === "major" ? "Rel. minor" : "Rel. major",
      (entry.relativeMinor || entry.relativeMajor) + (selMode === "major" ? "m" : "")));

    // the 7 triads as clickable chips
    var chips = el("div", { class: "hcChips" }, []);
    (entry.triads || []).forEach(function (t) {
      chips.appendChild(el("span", {
        class: "hcChip fn-" + t.functionClass,
        text: t.degree + " " + t.chordSymbol,
        onClick: function () { selectDegree(t.degree, true); },
      }));
    });
    d.appendChild(el("div", { class: "row", html: "<span class='lbl'>Triads</span>" }));
    d.appendChild(chips);

    // selected triad details + degree shortcuts
    var sel = selDegree && (entry.triads || []).filter(function (t) { return t.degree === selDegree; })[0];
    if (sel) {
      d.appendChild(el("div", { class: "big", text: sel.degree + "  " + sel.chordSymbol }));
      d.appendChild(row("Tones", (sel.tones || []).join("–")));
      d.appendChild(row("Quality", sel.quality));
      d.appendChild(row("Layer", sel.intervalLayer));
      var fam = familyEntryFor(sel.functionClass);
      d.appendChild(row("Function", sel.functionLabel
        + (fam ? " — " + fam.label + (fam.short ? " (" + fam.short + ")" : "") : "")));
    }

    // function legend (clickable -> highlight that function group); the
    // entries come from the payload cheatsheet, never a local synonym table
    var leg = el("div", { class: "hcChips" }, []);
    functionClasses().forEach(function (fc) {
      leg.appendChild(el("span", {
        class: "hcChip fn-" + fc["class"], text: fc.label,
        onClick: function () { selectFunction(fc["class"]); },
      }));
    });
    d.appendChild(el("div", { class: "row", html: "<span class='lbl'>Functions</span>" }));
    d.appendChild(leg);

    // launch shortcuts
    var short = el("div", { class: "hcShort" }, []);
    short.appendChild(shortcut("Full-key block",
      { drill: "full_key", render: "block", mode: selMode, key: keyStr }));
    short.appendChild(shortcut("Full-key arpeggio",
      { drill: "full_key", render: "arpeggio", mode: selMode, key: keyStr }));
    if (sel) {
      short.appendChild(shortcut(sel.degree + " across keys",
        { drill: "horizontal_degree", render: "block", mode: selMode, degree: sel.degree }));
      short.appendChild(shortcut(sel.degree + " arpeggio",
        { drill: "horizontal_degree", render: "arpeggio", mode: selMode, degree: sel.degree }));
      // Scope the quality drill to the selected key so a single exercise stays
      // readable (all keys would be 36 chords, over the trainer's cap).
      short.appendChild(shortcut(sel.quality + " in " + selKey,
        { drill: "quality", render: "block", mode: selMode, quality: sel.quality,
          keys: [selKey] }));
    }
    d.appendChild(short);

    // Optional "Open ... lab" affordances (Music Theory Laboratory only; the
    // trainer's circle does not set data.labLaunch, so this block is inert there).
    if (data && data.labLaunch) {
      var tonicRoman = selMode === "major" ? "I" : "i";
      var lab = el("div", { class: "hcShort hcLab" }, []);
      lab.appendChild(el("span", { class: "lbl", text: "Open in Lab:" }));
      lab.appendChild(labBtn("Motive lab",
        { labConcept: "motive", key: keyStr, mode: selMode }));
      lab.appendChild(labBtn(selMode === "major" ? "ii–V–I voice-leading lab"
        : "iv–v–i voice-leading lab",
        { labConcept: "voice_leading", key: keyStr, mode: selMode }));
      if (sel) {
        lab.appendChild(labBtn("Inversion lab (" + sel.degree + ")",
          { labConcept: "inversion", key: keyStr, mode: selMode, degree: sel.degree }));
        if (sel.functionClass === "D") {
          lab.appendChild(labBtn("Cadence lab (" + sel.degree + "–" + tonicRoman + ")",
            { labConcept: "cadence", key: keyStr, mode: selMode,
              pattern: [sel.degree, tonicRoman] }));
        }
      }
      d.appendChild(lab);
    }
  }
  function labBtn(label, req) {
    return el("button", { text: label, onClick: function () { requestLabLaunch(req); } });
  }
  function row(label, value) {
    return el("div", { class: "row" },
      [el("span", { class: "lbl", text: label }), document.createTextNode ?
        document.createTextNode(String(value)) : textSpan(String(value))]);
  }

  // -- cheatsheet ----------------------------------------------------------
  function renderCheat() {
    var c = document.getElementById("hcCheat");
    if (!c) return;
    c.style.display = cheatOn ? "block" : "none";
    if (!cheatOn) { c.innerHTML = ""; return; }
    var cs = data.cheatsheet || {};
    c.innerHTML = "";
    c.appendChild(patternTable("Major degree pattern", cs.majorPattern || []));
    c.appendChild(patternTable("Natural minor degree pattern", cs.minorPattern || []));

    c.appendChild(el("h4", { text: "Interval layers" }));
    var il = el("div", {}, []);
    (cs.intervalLayers || []).forEach(function (L) {
      il.appendChild(el("div", { text: L.quality + " = " + L.intervalLayer }));
    });
    c.appendChild(il);

    c.appendChild(el("h4", { text: "Functions" }));
    var leg = el("div", { class: "legend" }, []);
    (cs.functionClasses || []).forEach(function (fc) {
      var v = fc["class"] === "T" ? "--fnT" : fc["class"] === "S" ? "--fnS" : "--fnD";
      leg.appendChild(el("span", { html:
        "<span class='sw' style='background:var(" + v + ")'></span>" + esc(fc.label) }));
    });
    c.appendChild(leg);
  }
  function patternTable(title, rows) {
    var wrap = el("div", {}, [el("h4", { text: title })]);
    var t = el("table", {}, []);
    t.appendChild(el("tr", {}, [el("th", { text: "Degree" }), el("th", { text: "Quality" }),
      el("th", { text: "Layer" }), el("th", { text: "Function" })]));
    rows.forEach(function (r) {
      t.appendChild(el("tr", {}, [el("td", { text: r.degree }), el("td", { text: r.quality }),
        el("td", { text: r.intervalLayer }), el("td", { text: r.functionClass })]));
    });
    wrap.appendChild(t);
    return wrap;
  }

  // -- selection / interaction --------------------------------------------
  function selectKey(key, mode, fromClick) {
    selKey = key; selMode = mode; selDegree = null; selFunction = null;
    renderCircle();
    renderDetail();
    if (fromClick) fire({ type: "key", key: key, mode: mode });
  }
  function selectDegree(roman, fromClick) {
    selDegree = roman; selFunction = null;
    applyHighlightClasses();
    renderDetail();
    if (fromClick) fire({ type: "triad", key: selKey, mode: selMode, roman: roman });
  }
  function selectFunction(fnClass) {
    selFunction = fnClass;
    applyHighlightClasses();
    fire({ type: "function", key: selKey, mode: selMode, functionClass: fnClass });
  }

  function requestLaunch(spec) {
    if (!spec) return;
    launchQueue.push(spec);
    fire({ type: "launch", spec: spec });
  }
  function takeLaunch() { return launchQueue.length ? launchQueue.shift() : null; }
  function requestLabLaunch(req) {
    if (!req) return;
    labQueue.push(req);
    fire({ type: "labLaunch", req: req });
  }
  function takeLabLaunch() { return labQueue.length ? labQueue.shift() : null; }
  function fire(detail) { clickCbs.forEach(function (cb) { try { cb(detail); } catch (e) {} }); }

  // -- public highlight API (Part 1) --------------------------------------
  function highlightKey(key, mode) {
    hi.key = key; hi.mode = mode || "major";
    if (!selKey) selectKey(tonicOf(key), hi.mode, false);
    applyHighlightClasses();
  }
  function highlightChord(chordSymbol) { hi.chordSymbol = chordSymbol; applyHighlightClasses(); }
  function highlightDegree(roman) { hi.roman = roman; applyHighlightClasses(); }
  function clearHighlight() { hi = {}; applyHighlightClasses(); }

  // -- Part 5: sync with the running trainer -------------------------------
  function updateFromTrainerState(state) {
    if (!state) { clearHighlight(); return; }
    var tonic = tonicOf(state.key);
    var mode = state.mode || "major";
    hi = {
      key: state.key, mode: mode, roman: state.roman,
      chordSymbol: state.chordSymbol, degree: state.roman,
      functionClass: classFor(state.functionLabel),
    };
    // Bring the current key into view (and its triad ring) without losing the
    // user's manual selection model.
    if (tonic && (tonic !== selKey || mode !== selMode)) {
      selKey = tonic; selMode = mode; selDegree = state.roman; selFunction = null;
      renderCircle();
    } else {
      selDegree = state.roman;
    }
    applyHighlightClasses();
    renderDetail();
  }
  function classFor(functionLabel) {
    // Derived from the payload cheatsheet patterns (which carry the Python-side
    // functionLabel -> functionClass collapse) rather than a local copy of it.
    var cheat = (data && data.cheatsheet) || {};
    var found = null;
    (cheat.majorPattern || []).concat(cheat.minorPattern || []).forEach(function (p) {
      if (p.functionLabel === functionLabel) found = p.functionClass;
    });
    return found;
  }

  function highlightState() {
    return {
      key: hi.key ? tonicOf(hi.key) : null, mode: hi.mode || null,
      roman: hi.roman || null, chordSymbol: hi.chordSymbol || null,
      functionClass: hi.functionClass || null, selectedKey: selKey,
      selectedMode: selMode, selectedDegree: selDegree,
    };
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // -- init (idempotent) ---------------------------------------------------
  function init(payload) {
    data = payload || {};
    byKey = {};
    (data.majorKeys || []).forEach(function (k) { byKey[keyId(k.key, "major")] = k; });
    (data.minorKeys || []).forEach(function (k) { byKey[keyId(k.key, "natural_minor")] = k; });
    selKey = selMode = selDegree = selFunction = null;
    hi = {};
    cheatOn = false;
    launchQueue = [];
    labQueue = [];

    injectStyles();
    buildSkeleton();
    renderCircle();
    renderDetail();

    // Listen for the trainer's target-change event (works when same-page; the
    // Qt host also pushes updateFromTrainerState for the side-panel case).
    if (evtHandler && typeof window.removeEventListener === "function") {
      window.removeEventListener("harmonytrainer:targetchange", evtHandler);
    }
    evtHandler = function (e) { updateFromTrainerState(e && e.detail); };
    if (typeof window.addEventListener === "function") {
      window.addEventListener("harmonytrainer:targetchange", evtHandler);
    }
    return { ok: true, majorKeys: (data.majorKeys || []).length };
  }

  window.HarmonyCircle = {
    init: init,
    updateFromTrainerState: updateFromTrainerState,
    highlightKey: highlightKey,
    highlightChord: highlightChord,
    highlightDegree: highlightDegree,
    clearHighlight: clearHighlight,
    onCellClick: function (cb) { if (typeof cb === "function") clickCbs.push(cb); },
    takeLaunch: takeLaunch,
    takeLabLaunch: takeLabLaunch,
    highlightState: highlightState,
    // test/host helpers
    selectKey: function (k, m) { selectKey(k, m, true); },
    selectDegree: function (r) { selectDegree(r, true); },
    pendingCount: function () { return launchQueue.length; },
  };
})();
