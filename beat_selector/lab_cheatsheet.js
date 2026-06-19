/*
 * Music Theory Laboratory -- Cheatsheet panel (right-hand dashboard tab).
 *
 * A read-only reference rendered from the SAME cheatsheet data the Circle of
 * Fifths uses (harmony.circle_payload.build_circle_payload()["cheatsheet"]): the
 * major / natural-minor degree patterns, the interval-layer formulas, and the
 * three function colour classes. It re-derives no theory -- it only presents the
 * payload -- so it stays in lockstep with the rest of the app.
 *
 * Loaded by beat_selector/lab_cheatsheet.html in a QWebEngineView; the host calls
 * LabCheatsheet.init(cheatsheet) after injecting window.CHEATSHEET_DATA.
 *
 * Public: window.LabCheatsheet
 *   init(cheatsheet)   -> render; returns {ok}
 *   _model(cheatsheet) -> the table model (for the headless test)
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

  // Pure model (also exercised by the headless test).
  function model(cs) {
    cs = cs || {};
    return {
      major: cs.majorPattern || [],
      minor: cs.minorPattern || [],
      layers: cs.intervalLayers || [],
      functions: cs.functionClasses || [],
    };
  }

  function patternTable(title, rows) {
    var t = el("table", { class: "csTable" }, [
      el("tr", {}, [
        el("th", { text: "Degree" }), el("th", { text: "Quality" }),
        el("th", { text: "Interval layer" }), el("th", { text: "Function" }),
      ]),
    ]);
    (rows || []).forEach(function (r) {
      t.appendChild(el("tr", { class: "fn-" + (r.functionClass || "T") }, [
        el("td", { class: "rn", text: r.degree }),
        el("td", { text: r.quality }),
        el("td", { text: r.intervalLayer }),
        el("td", { text: r.functionLabel + " (" + (r.functionClass || "") + ")" }),
      ]));
    });
    return el("div", { class: "csBlock" }, [el("h4", { text: title }), t]);
  }

  function init(cheatsheet) {
    var root = dollar("csRoot") || document.body;
    var m = model(cheatsheet);
    root.innerHTML = "";
    root.appendChild(el("div", { class: "csTitle", text: "Diatonic cheatsheet" }));
    root.appendChild(el("div", { class: "csHint",
      text: "The invariant degree patterns, interval-layer formulas, and function colours — identical in every key." }));
    root.appendChild(patternTable("Major degree pattern", m.major));
    root.appendChild(patternTable("Natural-minor degree pattern", m.minor));

    var layers = el("div", { class: "csBlock" }, [el("h4", { text: "Interval layers" })]);
    m.layers.forEach(function (L) {
      layers.appendChild(el("div", { class: "csLayer",
        text: L.quality + " = " + L.intervalLayer }));
    });
    root.appendChild(layers);

    var fns = el("div", { class: "csBlock" }, [el("h4", { text: "Function colours" })]);
    m.functions.forEach(function (fc) {
      fns.appendChild(el("div", { class: "csFn fn-" + fc["class"],
        text: fc["class"] + " — " + fc.label }));
    });
    root.appendChild(fns);
    return { ok: true };
  }

  window.LabCheatsheet = { init: init, _model: model };
})();
