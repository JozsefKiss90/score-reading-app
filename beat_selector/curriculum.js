/*
 * Music Theory Laboratory -- curriculum browser (left-panel controller).
 *
 * The canonical educational frontend of the Harmony Trainer.  Loaded by
 * beat_selector/curriculum.html inside a QWebEngineView (the LEFT pane of
 * run_harmony_lab_demo.py).  It replaces the old flat "Concept Catalogue" with a
 * full curriculum TREE (harmony.curriculum) and renders, on the right of the
 * tree, the LESSON page (for a category/lesson/group) or the EXERCISE page (for a
 * leaf) -- definition, theory, harmonic analysis, practice advice, voice-leading
 * notes, Atlas/Circle mappings, trainer preview, and a Launch action.
 *
 * It never touches MIDI or the score: the middle pane is the existing
 * ScoreViewBeats + harmony_trainer.js; the host bridges via runJavaScript polling
 * (no QWebChannel), exactly like the Atlas / Circle / old-Lab panels.
 *
 * Host-facing API (stable):
 *   Curriculum.init(data)                 -> render the tree; {ok, exercises}
 *   Curriculum.takeLaunch()               -> dequeue a clicked LabExperimentSpec
 *   Curriculum.takeSelection()            -> dequeue the last selected node (for
 *                                            curriculum -> Atlas/Circle sync)
 *   Curriculum.select(nodeId)             -> select/show a node (Atlas/Circle -> curriculum)
 *   Curriculum.selectByExerciseId(exId)   -> select the leaf that owns a trainer exercise
 *   Curriculum.updateExplanation(target)  -> live "Now playing" guide
 *   Curriculum.setSync(active)            -> Atlas sync strip
 *   Curriculum.setProgress(payload)       -> overlay hierarchical progress
 *   Curriculum.search(query)              -> filter the tree to matches
 *
 * All derivation logic is decoupled from the DOM (the _xxx exports) so it is
 * unit-testable headlessly under Node (see tests/curriculum_node_test.js).
 */
(function () {
  "use strict";

  // -- module state ---------------------------------------------------------
  var data = null;
  var byId = {};                 // id -> node (with children)
  var parentOf = {};             // id -> parentId
  var pages = {};                // id -> page payload
  var index = [];                // flat search index
  var expanded = {};             // id -> bool (tree expand state)
  var progressStats = {};        // id -> rollup stats (from setProgress)
  var selectedId = null;         // node whose page is shown
  var focusId = null;            // keyboard-focused row
  var filterSet = null;          // Set(ids) when searching, else null
  var launchQueue = [];          // clicked LabExperimentSpecs (host picks up)
  var selectionQueue = [];       // selected node ids (host picks up for sync)
  var currentTarget = null;      // last live target

  var KIND_ICON = {
    curriculum: "◆", category: "▣", lesson: "▤", group: "▦", exercise: "♪",
    reserved: "▢",
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
      else if (k === "onDblClick") { node.addEventListener("dblclick", props[k]); }
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

  // ========================================================================
  // Indexing
  // ========================================================================
  function indexTree(root) {
    byId = {}; parentOf = {};
    (function walk(node, parent) {
      byId[node.id] = node;
      parentOf[node.id] = parent ? parent.id : null;
      (node.children || []).forEach(function (c) { walk(c, node); });
    })(root, null);
  }

  function nodeById(id) { return byId[id] || null; }
  function pageFor(id) { return pages[id] || null; }
  function childrenOf(id) { var n = byId[id]; return (n && n.children) || []; }
  function hasChildren(id) { return childrenOf(id).length > 0; }

  function ancestorsOf(id) {
    var out = [], cur = parentOf[id];
    while (cur) { out.push(cur); cur = parentOf[cur]; }
    return out;
  }

  // ========================================================================
  // Search (mirrors harmony.curriculum.search_curriculum: token-AND over terms)
  // ========================================================================
  function searchNodes(query) {
    var q = String(query == null ? "" : query).trim().toLowerCase();
    if (!q) return [];
    var tokens = q.replace(/-/g, " ").split(/\s+/).filter(Boolean);
    var scored = [];
    index.forEach(function (entry) {
      var hay = entry.terms.join(" ");
      var ok = tokens.every(function (tok) { return hay.indexOf(tok) !== -1; });
      if (!ok) return;
      var score = 0;
      if (entry.title.toLowerCase().indexOf(q) !== -1) score -= 100;
      if (entry.kind === "exercise") score -= 10;
      score += entry.path.length;
      scored.push({ score: score, id: entry.id });
    });
    scored.sort(function (a, b) { return a.score - b.score || (a.id < b.id ? -1 : 1); });
    return scored.map(function (s) { return s.id; });
  }

  // The set of nodes to SHOW while filtering: matches + all their ancestors.
  function matchSet(query) {
    var matches = searchNodes(query);
    if (!matches.length) return null;
    var set = {};
    matches.forEach(function (id) {
      set[id] = true;
      ancestorsOf(id).forEach(function (a) { set[a] = true; });
    });
    return set;
  }

  // ========================================================================
  // Visible rows (honours expand state, or the filter set while searching)
  // ========================================================================
  function visibleRows() {
    var rows = [];
    var root = data && data.tree;
    if (!root) return rows;
    (function walk(node, depth) {
      (node.children || []).forEach(function (child) {
        var show = filterSet ? !!filterSet[child.id] : true;
        if (show) {
          rows.push({
            id: child.id, depth: depth, kind: child.kind,
            hasChildren: (child.children || []).length > 0,
            expanded: filterSet ? true : !!expanded[child.id],
          });
        }
        var recurse = filterSet
          ? !!filterSet[child.id]                 // keep descending matched branches
          : !!expanded[child.id];
        if (recurse) walk(child, depth + 1);
      });
    })(root, 0);
    return rows;
  }

  // ========================================================================
  // Tree rendering
  // ========================================================================
  function progressFor(id) { return progressStats[id] || null; }

  function renderTree() {
    var pane = dollar("curTree");
    if (!pane) return;
    clear(pane);
    var rows = visibleRows();
    if (!rows.length && filterSet) {
      pane.appendChild(el("div", { class: "curPlaceholder", text: "No matches." }));
      return;
    }
    rows.forEach(function (r) {
      var node = byId[r.id];
      var stats = progressFor(r.id);
      var state = stats ? stats.state : null;
      var cls = "curRow" + (r.id === selectedId ? " selected" : "")
        + (r.id === focusId ? " focused" : "")
        + (node.reserved ? " reserved" : "")
        + (state ? " curState-" + state : "");
      var twisty = r.hasChildren ? (r.expanded ? "▾" : "▸") : "";
      var rowChildren = [
        el("span", { class: "curTwisty", text: twisty,
          onClick: function (ev) { toggle(r.id); stop(ev); } }),
        el("span", { class: "curIcon", text: KIND_ICON[node.kind] || "•" }),
        el("span", { class: "curLabel", text: node.title }),
      ];
      if (node.exerciseCount && node.kind !== "exercise") {
        rowChildren.push(el("span", { class: "curCount", text: String(node.exerciseCount) }));
      }
      if (stats && stats.total) {
        rowChildren.push(progressBar(stats.percent, "curBar"));
      }
      var row = el("div", {
        class: cls, dataset: { id: r.id, depth: String(r.depth) },
        onClick: function () { onRowClick(r.id); },
        onDblClick: function () { onRowDblClick(r.id); },
      }, rowChildren);
      if (row.style) row.style.paddingLeft = (4 + r.depth * 14) + "px";
      pane.appendChild(row);
    });
  }

  function progressBar(percent, cls) {
    var bar = el("div", { class: cls || "curProgressBar" }, []);
    var fill = el("span", {}, []);
    if (fill.style) fill.style.width = Math.max(0, Math.min(100, percent || 0)) + "%";
    bar.appendChild(fill);
    return bar;
  }

  function stop(ev) { if (ev && ev.stopPropagation) ev.stopPropagation(); }

  function toggle(id) {
    if (!hasChildren(id)) return;
    expanded[id] = !expanded[id];
    saveExpanded();
    renderTree();
  }

  function onRowClick(id) {
    focusId = id;
    if (hasChildren(id) && !filterSet) {
      // a container row: toggle expand AND show its lesson page
      expanded[id] = !expanded[id];
      saveExpanded();
    }
    select(id);
  }

  function onRowDblClick(id) {
    var node = byId[id];
    if (node && node.kind === "exercise") launchNode(id);
  }

  // ========================================================================
  // Selection + pages
  // ========================================================================
  function select(id) {
    if (!byId[id]) return;
    selectedId = id;
    focusId = id;
    selectionQueue.push(id);
    renderTree();
    renderDetail();
    renderProgressPanel();
  }

  function takeSelection() {
    return selectionQueue.length ? selectionQueue.shift() : null;
  }

  function selectByExerciseId(exId) {
    // find the leaf whose embedded trainer exercise (or experiment) matches
    var hit = null;
    Object.keys(byId).forEach(function (id) {
      if (hit) return;
      var n = byId[id];
      if (n.kind !== "exercise" || !n.labSpec) return;
      if (n.labSpec.experiment_id === exId) { hit = id; return; }
      (n.exerciseSpecs || []).forEach(function (es) {
        if (es.exercise_id === exId) hit = id;
      });
    });
    if (hit) {
      ancestorsOf(hit).forEach(function (a) { expanded[a] = true; });
      saveExpanded();
      select(hit);
    }
    return hit;
  }

  function exerciseModel(page) {
    if (!page) return null;
    return {
      title: page.title,
      subtitle: page.subtitle,
      difficulty: page.difficulty,
      minutes: page.estimatedMinutes,
      definition: page.definition,
      theory: page.musicTheory,
      analysis: page.harmonicAnalysis || [],
      preview: page.trainerPreview || { chords: [] },
      voiceLeading: page.voiceLeadingNotes || [],
      practice: page.practiceAdvice || [],
      mistakes: page.commonMistakes || [],
      atlas: page.atlasMapping || [],
      circle: page.circleMapping || [],
      currentMapping: page.currentMapping || "",
      launch: page.launch || null,
    };
  }

  function lessonModel(page) {
    if (!page) return null;
    return {
      title: page.title,
      subtitle: page.subtitle,
      kind: page.kind,
      reserved: page.reserved,
      definition: page.definition,
      goal: page.goal,
      theory: page.theory,
      skills: page.skillsAcquired || [],
      mistakes: page.commonMistakes || [],
      order: page.recommendedOrder || [],
      related: page.relatedLessons || [],
      atlas: page.atlasLinks || [],
      circle: page.circleLinks || [],
      audio: page.audioObjective,
      visual: page.visualObjective,
      minutes: page.estimatedPracticeTime,
      exerciseCount: page.exerciseCount,
    };
  }

  function renderDetail() {
    var pane = dollar("curDetail");
    if (!pane) return;
    clear(pane);
    if (!selectedId) {
      pane.appendChild(el("div", { class: "curTitle", text: "Curriculum" }));
      pane.appendChild(el("div", { class: "curPlaceholder",
        text: "Pick a category or lesson on the left to read its theory, then open an exercise." }));
      return;
    }
    var node = byId[selectedId];
    var page = pageFor(selectedId);
    if (node.kind === "exercise") renderExercise(pane, exerciseModel(page));
    else renderLesson(pane, lessonModel(page), node);
  }

  function chips(items, cls, labelFn, onClick) {
    var wrap = el("div", { class: "curChips" }, []);
    (items || []).forEach(function (it) {
      var props = { class: "curChip" + (cls ? " " + cls : ""), text: labelFn(it) };
      if (onClick) props.onClick = function () { onClick(it); };
      wrap.appendChild(el("span", props));
    });
    return wrap;
  }

  function bullets(items) {
    var ul = el("ul", { class: "curBullets" }, []);
    (items || []).forEach(function (it) { ul.appendChild(el("li", { text: it })); });
    return ul;
  }

  function sec(title) { return el("div", { class: "curSecTitle", text: title }); }

  function renderExercise(pane, m) {
    if (!m) { pane.appendChild(el("div", { class: "curPlaceholder", text: "No page." })); return; }
    pane.appendChild(el("div", { class: "curTitle", text: m.title }));
    if (m.subtitle) pane.appendChild(el("div", { class: "curSub", text: m.subtitle }));
    pane.appendChild(chips(
      ["Difficulty " + m.difficulty + "/5", "~" + m.minutes + " min"], null,
      function (x) { return x; }));
    if (m.definition) pane.appendChild(el("div", { class: "curLede", text: m.definition }));

    if (m.theory) { pane.appendChild(sec("Music theory")); pane.appendChild(el("div", { class: "curPara", text: m.theory })); }
    if (m.analysis.length) { pane.appendChild(sec("Harmonic analysis")); pane.appendChild(bullets(m.analysis)); }

    pane.appendChild(sec("Trainer preview"));
    if (m.preview.kind === "motive") {
      pane.appendChild(chips(m.preview.degrees, "chord", function (x) { return x; }));
    } else {
      pane.appendChild(chips(m.preview.chords || [], "chord",
        function (c) { return c.chordSymbol + " (" + c.roman + ")"; }));
    }

    if (m.voiceLeading.length) { pane.appendChild(sec("Voice-leading notes")); pane.appendChild(bullets(m.voiceLeading)); }
    if (m.practice.length) { pane.appendChild(sec("How to practise")); pane.appendChild(bullets(m.practice)); }
    if (m.mistakes.length) { pane.appendChild(sec("Common mistakes")); pane.appendChild(bullets(m.mistakes)); }

    if (m.atlas.length) {
      pane.appendChild(sec("Atlas mapping"));
      pane.appendChild(chips(m.atlas, "atlas", function (a) { return a.kind + " · " + a.label; },
        function (a) { hoverAtlas(a.id); }));
    }
    if (m.circle.length) {
      pane.appendChild(sec("Circle mapping"));
      pane.appendChild(chips(m.circle, "circle", function (c) { return c.kind + " · " + c.label; }));
    }
    if (m.currentMapping) pane.appendChild(el("div", { class: "curNote", text: m.currentMapping }));

    var launchProps = { class: "curLaunch", text: "▶ Launch exercise",
      onClick: function () { launchNode(selectedId); } };
    pane.appendChild(el("button", launchProps));

    // Echo twin (plan A1, ticket 07): the same drill by ear — available on
    // native trainer leaves once the visual leaf is at least *started*
    // (sound-before-symbol lives inside a vocabulary you have met).  Aural
    // attempts land on the same leaf, so both feed one mastery record.
    var node = byId[selectedId];
    if (node && node.echoEligible) {
      var unlocked = echoUnlocked(selectedId);
      var echoProps = {
        class: "curLaunch curEcho" + (unlocked ? "" : " locked"),
        text: unlocked ? "🎧 Echo drill — play it by ear"
                       : "🎧 Echo drill — locked (start the visual drill first)",
        onClick: function () { launchNode(selectedId, true); },
      };
      if (!unlocked) echoProps.disabled = "disabled";
      pane.appendChild(el("button", echoProps));
    }
  }

  function renderLesson(pane, m, node) {
    if (!m) { pane.appendChild(el("div", { class: "curPlaceholder", text: "No page." })); return; }
    pane.appendChild(el("div", { class: "curTitle", text: m.title }));
    if (m.subtitle) pane.appendChild(el("div", { class: "curSub", text: m.subtitle }));
    var meta = [];
    if (m.exerciseCount) meta.push(m.exerciseCount + " exercises");
    if (m.minutes) meta.push("~" + m.minutes + " min");
    if (m.reserved) meta.push("reserved");
    if (meta.length) pane.appendChild(chips(meta, null, function (x) { return x; }));
    if (m.definition) pane.appendChild(el("div", { class: "curLede", text: m.definition }));
    if (m.goal) { pane.appendChild(sec("Goal")); pane.appendChild(el("div", { class: "curPara", text: m.goal })); }
    if (m.theory) { pane.appendChild(sec("Theory")); pane.appendChild(el("div", { class: "curPara", text: m.theory })); }
    if (m.skills.length) { pane.appendChild(sec("Skills acquired")); pane.appendChild(bullets(m.skills)); }
    if (m.mistakes.length) { pane.appendChild(sec("Common mistakes")); pane.appendChild(bullets(m.mistakes)); }

    if (m.audio || m.visual) {
      pane.appendChild(sec("Objectives"));
      if (m.audio) pane.appendChild(el("div", { class: "curRow2" }, [
        el("span", { class: "curLbl", text: "Audio" }), el("span", { class: "curVal", text: m.audio })]));
      if (m.visual) pane.appendChild(el("div", { class: "curRow2" }, [
        el("span", { class: "curLbl", text: "Visual" }), el("span", { class: "curVal", text: m.visual })]));
    }

    if (m.order.length) {
      pane.appendChild(sec("Recommended order"));
      var ol = el("div", {}, []);
      m.order.forEach(function (o, i) {
        ol.appendChild(el("div", { class: "curRow2" }, [
          el("span", { class: "curLink", text: (i + 1) + ". " + o.title,
            onClick: function () { jumpTo(o.id); } })]));
      });
      pane.appendChild(ol);
    }
    if (m.related.length) {
      pane.appendChild(sec("Related lessons"));
      var rl = el("div", {}, []);
      m.related.forEach(function (r) {
        rl.appendChild(el("span", { class: "curLink", text: r.title + "  ",
          onClick: function () { jumpTo(r.id); } }));
      });
      pane.appendChild(rl);
    }
    if (m.atlas.length) {
      pane.appendChild(sec("Atlas links"));
      pane.appendChild(chips(m.atlas, "atlas", function (a) { return a.kind + " · " + a.label; },
        function (a) { hoverAtlas(a.id); }));
    }
    if (m.circle.length) {
      pane.appendChild(sec("Circle links"));
      pane.appendChild(chips(m.circle, "circle", function (c) { return c.kind + " · " + c.label; }));
    }
  }

  function jumpTo(id) {
    if (!byId[id]) return;
    ancestorsOf(id).forEach(function (a) { expanded[a] = true; });
    saveExpanded();
    if (filterSet) { filterSet = null; var s = dollar("curSearch"); if (s) s.value = ""; }
    select(id);
  }

  // ========================================================================
  // Launch
  // ========================================================================
  // Echo unlock gate: the aural twin opens once the visual leaf has been
  // started.  Allowlist (mirroring harmony/echo_drills.echo_unlocked), so
  // unknown or future states stay locked exactly like the Python gate.
  function echoUnlocked(id) {
    var stats = progressFor(id);
    var s = stats && stats.state;
    return s === "started" || s === "completed" || s === "mastered";
  }

  function launchNode(id, echo) {
    var node = byId[id];
    if (!node || node.kind !== "exercise" || !node.labSpec) return;
    if (echo) {
      // Locked or ineligible echo requests are dropped (the button is
      // disabled anyway; this keeps the queue honest for keyboard paths).
      if (!node.echoEligible || !echoUnlocked(id)) return;
      var spec = {};
      Object.keys(node.labSpec).forEach(function (k) { spec[k] = node.labSpec[k]; });
      spec.echo = true;   // host flag; LabExperimentSpec.from_dict ignores it
      launchQueue.push(spec);
    } else {
      launchQueue.push(node.labSpec);
    }
    var hint = dollar("curLaunchHint");
    if (hint) hint.textContent =
      (echo ? "Launching echo: " : "Launching: ") + node.title;
  }
  function takeLaunch() { return launchQueue.length ? launchQueue.shift() : null; }

  // ========================================================================
  // Live "Now playing" guide
  // ========================================================================
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
    // Echo listen phase (ticket 07): the trainer redacts the target, so the
    // guide names only the key and says why the rest is hidden.
    if (t.echoVeiled) {
      add("Bar", t.measureNumber);
      add("Echo", "listen and play it back — details appear when you finish");
      return { heading: headingFor(t), rows: rows, note: "" };
    }
    if (t.concept === "melody") {
      add("Motive", t.motiveLabel);
      add("Degrees", t.degreeLabels);
    } else {
      add("Chord", (t.chordSymbol || "") + (t.roman ? "  (" + t.roman + ")" : ""));
      add("Function", t.functionLabel);
    }
    if (t.inversionLabel) {
      add("Inversion", t.inversionLabel + (t.figuredBass ? "  " + t.figuredBass : ""));
      add("Bass", t.bassNote);
    }
    if (t.voices && t.voices.length) {
      add("Voices", t.voices.map(function (v) { return v[0] + " " + v[1]; }));
    }
    add("Common tones", t.commonTones);
    add("Bass motion", t.bassMotion);
    if (t.impliedChord) add("Implies", t.impliedChord + " (" + (t.impliedRoman || "") + ")");
    return { heading: headingFor(t), rows: rows, note: t.labNote || t.explanation || "" };
  }

  function headingFor(t) {
    if (t.concept === "melody") return (t.motiveLabel || "") + " — " + (t.key || "");
    var bits = [];
    if (t.chordSymbol) bits.push(t.chordSymbol);
    if (t.roman) bits.push(t.roman);
    if (t.inversionLabel) bits.push(t.inversionLabel);
    return bits.join("  ");
  }

  function renderLive() {
    var pane = dollar("curLive");
    if (!pane) return;
    var model = explanationModel(currentTarget);
    if (!model) {
      pane.innerHTML = '<div class="curSecTitle">Now playing</div>'
        + '<div class="curPlaceholder">Launch an exercise and play along — '
        + 'the current chord is explained here.</div>';
      return;
    }
    var html = '<div class="curSecTitle">Now playing</div>';
    html += '<div class="curTitle">' + esc(model.heading) + "</div>";
    model.rows.forEach(function (r) {
      html += '<div class="curRow2"><span class="curLbl">' + esc(r.label)
        + '</span><span class="curVal">' + esc(r.value) + "</span></div>";
    });
    if (model.note) html += '<div class="curNote">' + esc(model.note) + "</div>";
    pane.innerHTML = html;
  }

  // ========================================================================
  // Progress panel
  // ========================================================================
  function renderProgressPanel() {
    var pane = dollar("curProgress");
    if (!pane) return;
    clear(pane);
    pane.appendChild(sec("Progress"));
    var rootStats = data && data.tree ? progressFor(data.tree.id) : null;
    var sel = selectedId ? progressFor(selectedId) : null;
    if (!rootStats) {
      pane.appendChild(el("div", { class: "curPlaceholder", text: "No progress yet." }));
      return;
    }
    pane.appendChild(progressLine("Overall", rootStats));
    if (sel && sel.id !== rootStats.id && sel.total) {
      pane.appendChild(progressLine(byId[selectedId].title, sel));
    } else if (sel && sel.kind === "exercise") {
      pane.appendChild(el("div", { class: "curRow2" }, [
        el("span", { class: "curLbl", text: byId[selectedId].title }),
        el("span", { class: "curVal", text: (sel.state || "not_started")
          + (sel.attempts ? " · " + sel.attempts + " attempts · best " + sel.bestScore : "") })]));
    }
  }

  function progressLine(label, s) {
    var wrap = el("div", {}, []);
    wrap.appendChild(el("div", { class: "curRow2" }, [
      el("span", { class: "curLbl", text: label }),
      el("span", { class: "curVal", text: s.completed + "/" + s.total + " done · "
        + s.percent + "%" + (s.mastered ? " · " + s.mastered + " mastered" : "") })]));
    wrap.appendChild(progressBar(s.percent, "curProgressBar"));
    return wrap;
  }

  // ========================================================================
  // Atlas sync strip + cross-highlight
  // ========================================================================
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
  function renderSync(active) {
    var strip = dollar("curAtlas");
    if (!strip) return;
    var cs = syncChips(active);
    if (!cs.length) { strip.innerHTML = '<span class="curLbl">Atlas: —</span>'; return; }
    var html = '<span class="curLbl">Atlas:</span>';
    cs.forEach(function (c) {
      html += '<span class="curSyncChip" title="' + esc(c.id) + '">' + esc(c.kind)
        + " · " + esc(c.label) + "</span>";
    });
    strip.innerHTML = html;
  }
  function hoverAtlas(/* id */) { /* host may poll selection; chip click is a no-op hook */ }

  // ========================================================================
  // Expand-state persistence (tolerant of no localStorage, e.g. in Node)
  // ========================================================================
  function saveExpanded() {
    try {
      if (typeof localStorage !== "undefined")
        localStorage.setItem("curExpanded", JSON.stringify(expanded));
    } catch (e) { /* ignore */ }
  }
  function loadExpanded() {
    try {
      if (typeof localStorage !== "undefined") {
        var raw = localStorage.getItem("curExpanded");
        if (raw) return JSON.parse(raw) || {};
      }
    } catch (e) { /* ignore */ }
    return null;
  }

  // ========================================================================
  // Keyboard navigation
  // ========================================================================
  function keyMove(key) {
    var rows = visibleRows();
    if (!rows.length) return focusId;
    var ids = rows.map(function (r) { return r.id; });
    var i = focusId ? ids.indexOf(focusId) : -1;
    var cur = i >= 0 ? rows[i] : null;

    if (key === "ArrowDown") { i = Math.min(ids.length - 1, i + 1); if (i < 0) i = 0; focusId = ids[i]; }
    else if (key === "ArrowUp") { i = Math.max(0, i - 1); focusId = ids[i]; }
    else if (key === "ArrowRight") {
      if (cur && cur.hasChildren && !cur.expanded) { expanded[cur.id] = true; saveExpanded(); }
      else if (cur && cur.hasChildren) { focusId = childrenOf(cur.id)[0].id; }
    } else if (key === "ArrowLeft") {
      if (cur && cur.hasChildren && cur.expanded && !filterSet) { expanded[cur.id] = false; saveExpanded(); }
      else if (cur && parentOf[cur.id] && parentOf[cur.id] !== (data.tree && data.tree.id)) { focusId = parentOf[cur.id]; }
    } else if (key === "Enter" || key === " ") {
      if (focusId) {
        var node = byId[focusId];
        if (node && node.kind === "exercise" && focusId === selectedId) launchNode(focusId);
        else select(focusId);
      }
    }
    renderTree();
    return focusId;
  }

  function bindKeys() {
    var tree = dollar("curTree");
    if (!tree || !tree.addEventListener) return;
    tree.addEventListener("keydown", function (ev) {
      var keys = ["ArrowDown", "ArrowUp", "ArrowRight", "ArrowLeft", "Enter", " "];
      if (keys.indexOf(ev.key) === -1) return;
      if (ev.preventDefault) ev.preventDefault();
      keyMove(ev.key);
    });
  }

  function bindSearch() {
    var box = dollar("curSearch");
    if (!box || !box.addEventListener) return;
    box.addEventListener("input", function () { search(box.value); });
  }

  // ========================================================================
  // Public API
  // ========================================================================
  function search(query) {
    filterSet = matchSet(query);
    renderTree();
  }

  function updateExplanation(target) { currentTarget = target || null; renderLive(); }
  function setSync(active) { renderSync(active); }

  function setProgress(payload) {
    progressStats = (payload && payload.stats) || {};
    renderTree();
    renderProgressPanel();
    renderDetail();   // the echo affordance gates on the leaf's state
  }

  function init(payload) {
    data = payload || {};
    pages = data.pages || {};
    index = data.index || [];
    indexTree(data.tree || { id: "cur", children: [] });
    expanded = loadExpanded() || {};
    // default: expand the first category so the workspace is not blank
    if (data.tree && data.tree.children && data.tree.children.length
        && Object.keys(expanded).length === 0) {
      expanded[data.tree.children[0].id] = true;
    }
    progressStats = {};
    selectedId = null; focusId = null; filterSet = null;
    currentTarget = null; launchQueue = []; selectionQueue = [];

    renderTree();
    renderDetail();
    renderLive();
    renderProgressPanel();
    renderSync(null);
    bindKeys();
    bindSearch();

    var leaves = Object.keys(byId).filter(function (id) {
      return byId[id].kind === "exercise";
    }).length;
    return { ok: true, exercises: leaves };
  }

  window.Curriculum = {
    init: init,
    takeLaunch: takeLaunch,
    takeSelection: takeSelection,
    select: jumpTo,
    selectByExerciseId: selectByExerciseId,
    updateExplanation: updateExplanation,
    setSync: setSync,
    setProgress: setProgress,
    search: search,
    // exposed for the headless test:
    _searchNodes: searchNodes,
    _matchSet: matchSet,
    _visibleRows: visibleRows,
    _exerciseModel: exerciseModel,
    _lessonModel: lessonModel,
    _explanationModel: explanationModel,
    _syncChips: syncChips,
    _keyMove: keyMove,
    _nodeById: nodeById,
    _pageFor: pageFor,
    _ancestorsOf: ancestorsOf,
  };
})();
