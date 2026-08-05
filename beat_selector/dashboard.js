/*
 * Home dashboard (ticket 08, U3) -- the platform's landing surface.
 *
 * Loaded by beat_selector/dashboard.html inside a QWebEngineView, either
 * standalone (run_dashboard_demo.py) or as the "Home" tab of the Lab
 * workspace (run_harmony_lab_demo.py).  Renders, from a single
 * harmony-dashboard/v1 payload (harmony.progress_service.dashboard_payload):
 *
 *   - the practice streak + overall completion header;
 *   - the SM-2-lite "due today" review strip (click a card to launch);
 *   - the functional-journey summary;
 *   - the full-curriculum mastery heatmap -- one cell per exercise leaf,
 *     colored by state (click a cell to launch that leaf).
 *
 * It computes nothing itself: every number (due list, intervals, streaks,
 * counts) comes precomputed from Python, so the Py<->JS contract stays the
 * single source of truth.  The host bridges via the same runJavaScript
 * polling pattern as every other panel:
 *
 *   Dashboard.init(payload)     -> first render; {ok, leaves}
 *   Dashboard.setPayload(p)     -> re-render with fresh data (host push)
 *   Dashboard.takeLaunch()      -> dequeue a clicked leaf's node id
 *
 * Derivation helpers are DOM-decoupled (the _xxx exports) for the headless
 * Node test (tests/dashboard_node_test.js).
 */
(function () {
  "use strict";

  var payload = null;
  var launchQueue = [];          // clicked node ids (host picks up)

  var STATE_LABEL = {
    not_started: "not started", started: "started",
    completed: "completed", mastered: "mastered",
  };

  // -- tiny DOM helpers ------------------------------------------------------
  function dollar(id) { return document.getElementById(id); }

  function el(tag, props, children) {
    var node = document.createElement(tag);
    props = props || {};
    Object.keys(props).forEach(function (k) {
      if (k === "class") { node.className = props[k]; }
      else if (k === "text") { node.textContent = props[k]; }
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

  // -- pure derivations (exported for the Node test) -------------------------
  function streakLine(streak) {
    streak = streak || {};
    var current = streak.current || 0;
    var parts = ["🔥 " + current + "-day streak"];
    if ((streak.best || 0) > current) parts.push("best " + streak.best);
    parts.push(streak.practicedToday ? "practiced today"
                                     : "not practiced yet today");
    return parts.join(" · ");
  }

  function cellTooltip(cell) {
    var bits = [cell.title, STATE_LABEL[cell.state] || cell.state];
    if (cell.attempts) {
      bits.push(cell.attempts + " attempt" + (cell.attempts === 1 ? "" : "s"));
    }
    if (cell.dueAt) bits.push("due " + cell.dueAt.slice(0, 10));
    return bits.join(" — ");
  }

  function dueLine(item) {
    var days = Math.round(item.overdueDays || 0);
    if (days <= 0) return "due today";
    return days + " day" + (days === 1 ? "" : "s") + " overdue";
  }

  // -- render ----------------------------------------------------------------
  function renderHeader() {
    var overall = payload.overall || {};
    var streak = payload.streak || {};
    var host = dollar("dashSummary");
    clear(host);
    host.appendChild(el("div", { class: "dashStreak", text: streakLine(streak) }));
    var pct = overall.percent || 0;
    var fill = el("span", {});
    fill.style.width = pct + "%";
    var bar = el("div", { class: "dashBar" }, [fill]);
    host.appendChild(el("div", { class: "dashOverall" }, [
      el("span", { text: (overall.completed || 0) + " / " + (overall.total || 0)
                         + " exercises completed (" + pct + "%) · "
                         + (overall.mastered || 0) + " mastered" }),
    ]));
    host.appendChild(bar);
  }

  function renderReview() {
    var review = payload.review || { due: [], dueCount: 0 };
    var strip = dollar("dashDue");
    clear(strip);
    dollar("dashDueCount").textContent = review.dueCount
      ? review.dueCount + " due" : "";
    if (!review.due.length) {
      strip.appendChild(el("div", {
        class: "dashEmpty",
        text: "Nothing due for review — explore something new below.",
      }));
      return;
    }
    review.due.forEach(function (item) {
      strip.appendChild(el("div", {
        class: "dashDueCard dashState-" + item.state,
        dataset: { nodeId: item.nodeId },
        onClick: function () { launchQueue.push(item.nodeId); },
      }, [
        el("div", { class: "dashDueTitle", text: item.title }),
        el("div", { class: "dashDueMeta",
                    text: item.category + " · " + dueLine(item) }),
      ]));
    });
  }

  function renderJourney() {
    var j = payload.journey || {};
    var host = dollar("dashJourney");
    clear(host);
    [["Journey stages", (j.stagesCompleted || 0) + " / " + (j.stagesTotal || 0)],
     ["Journey drills", String(j.drillsFinished || 0)],
     ["Nodes lit", String(j.litNodes || 0)],
    ].forEach(function (pair) {
      host.appendChild(el("span", { class: "dashChip",
                                    text: pair[0] + ": " + pair[1] }));
    });
  }

  function renderHeatmap() {
    var heatmap = payload.heatmap || { categories: [] };
    var host = dollar("dashHeatmap");
    clear(host);
    heatmap.categories.forEach(function (category) {
      var grid = el("div", { class: "dashGrid" });
      category.leaves.forEach(function (cell) {
        grid.appendChild(el("div", {
          class: "dashCell dashState-" + cell.state,
          title: cellTooltip(cell),
          dataset: { nodeId: cell.id, state: cell.state },
          onClick: function () { launchQueue.push(cell.id); },
        }));
      });
      host.appendChild(el("div", { class: "dashCat" }, [
        el("div", { class: "dashCatHead" }, [
          el("span", { class: "dashCatLabel", text: category.label }),
          el("span", { class: "dashCatPct",
                       text: (category.percent || 0) + "%" }),
        ]),
        grid,
      ]));
    });
    var counts = heatmap.counts || {};
    dollar("dashLegend").textContent =
      (heatmap.totalLeaves || 0) + " exercises · " +
      (counts.mastered || 0) + " mastered · " +
      (counts.completed || 0) + " completed · " +
      (counts.started || 0) + " started · " +
      (counts.not_started || 0) + " untouched";
  }

  function render() {
    if (!payload) return;
    renderHeader();
    renderReview();
    renderJourney();
    renderHeatmap();
  }

  // -- host API --------------------------------------------------------------
  function init(p) {
    payload = p || null;
    if (!payload) return { ok: false, leaves: 0 };
    var placeholder = dollar("dashPlaceholder");
    if (placeholder) placeholder.style.display = "none";
    render();
    return { ok: true,
             leaves: (payload.heatmap && payload.heatmap.totalLeaves) || 0 };
  }

  function setPayload(p) {
    payload = p || payload;
    render();
  }

  function takeLaunch() { return launchQueue.length ? launchQueue.shift() : null; }

  window.Dashboard = {
    init: init,
    setPayload: setPayload,
    takeLaunch: takeLaunch,
    // DOM-decoupled derivations, for the headless Node test.
    _streakLine: streakLine,
    _cellTooltip: cellTooltip,
    _dueLine: dueLine,
  };
})();
