# ui/beat_selector.py — JSON-driven beat/label selector (uses extract_pitches.py output)
from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtWidgets import QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QWidget
from PyQt6.QtWebEngineWidgets import QWebEngineView
import verovio
import xml.etree.ElementTree as ET

# If you already have these helpers elsewhere, you can keep them; they are not used for labels anymore.
# They’re only used to build the measure list and page mapping.
from model.score_loader import (
    build_tempo_segments,
    build_measure_times,
)

def dlog(*args): print("[BeatSelector]", *args, flush=True)

@dataclass
class Measure:
    index: int
    number: int
    start_ql: float
    end_ql: float
    start_sec: float
    end_sec: float

_HTML = r"""
<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<style>
  :root { --hl-fill: rgba(56,189,248,0.12); --hl-stroke: rgba(2,132,199,0.90); }
  html, body { margin:0; padding:0; height:100%; background:#fff; }
  #frame { position:relative; width:100%; height:100vh; overflow:hidden; background:#fff; display:flex; }
  #scorePane{ position:relative; flex:1 1 auto; height:100%; }
  #side{ width:280px; max-width:33vw; border-left:1px solid #e5e7eb; background:#fafafa; overflow:auto; font:13px/1.3 system-ui; }
  #side h3{ margin:8px 8px 4px; font:600 13px system-ui; color:#0b3a53; }
  #side .beat{ margin:6px; padding:6px; border:1px solid #dbeafe; background:#eff6ff; border-radius:6px; }
  #side .note{ margin:4px 0; padding:4px 6px; border-radius:4px; cursor:pointer; }
  #side .note:hover{ background:#e2e8f0; }
  #side .note.note-hl { background:#dbeafe; outline:1px solid #60a5fa; }
  object, svg { display:block; width:100%; height:100%; background:#fff !important; }
  .beat-box {
    position:absolute; top:0;
    background: rgba(2, 132, 199, 0.10);
    border-left: 1px solid rgba(2, 132, 199, 0.35);
    border-right: 1px solid rgba(2, 132, 199, 0.35);
    pointer-events:auto; cursor:pointer; z-index:20;
  }
  .beat-box.sel { background: rgba(2, 132, 199, 0.24); outline:1px solid rgba(2,132,199,0.90); outline-offset:-1px; }
  .beat-box:hover::after {
    content: attr(data-label);
    position:absolute; top:4px; right:4px; font:11px/1.1 system-ui;
    color:#0b3a53; background:rgba(255,255,255,0.9);
    border:1px solid rgba(2,132,199,.35); padding:2px 4px; border-radius:4px;
  }
  #hud { position:absolute; right:8px; top:8px; color:#fff; font:12px/1.3 system-ui;
         background:rgba(0,0,0,.55); padding:6px 8px; border-radius:6px; z-index:30; }
</style></head>
<body>
  <div id="frame">
    <div id="scorePane">
      <object id="page" type="image/svg+xml" data="{SVG_URL}"></object>
      <div id="hud">loading…</div>
    </div>
    <aside id="side"><h3>Selected beats</h3><div id="list"></div></aside>
  </div>
<script>
  (function () {
    const obj = document.getElementById("page");
    const initial = "{SVG_URL}";
    obj.addEventListener("load", function onLoad() {
      obj.removeEventListener("load", onLoad);
      buildBeatBoxes();
    }, { once: true });
    obj.data = initial.indexOf("?") === -1 ? initial + "?ts=" + Date.now() : initial;
  })();

  // Incoming per-page arrays
  const ABS_INDEXES    = {ABS_INDEXES_JSON};
  const PITCH_MAP      = {PITCH_MAP_JSON};     // { absIdx: { beatNo: ["F#4","A3",...] } }
  const MEASURE_BEATS  = {MEASURE_BEATS_JSON}; // { absIdx: 3|4|... }

  const SELECTED = new Set();

  function svgDoc() {
    const o = document.getElementById("page");
    try { return o.contentDocument; } catch (e) { return null; }
  }
  function svgRoot() {
    const d = svgDoc();
    return d ? d.querySelector("svg") : null;
  }
  function _rectRel(node, rootRect) {
    const r = node.getBoundingClientRect();
    return { left: r.left - rootRect.left, right: r.right - rootRect.left,
             top: r.top - rootRect.top, bottom: r.bottom - rootRect.top };
  }
  function beatsForMeasure(absIdx, fallback) {
    const v = MEASURE_BEATS[String(absIdx)];
    return (v || fallback || 4);
  }
  function measureGroupByAbs(absIdx) {
    const svg = svgRoot(); if (!svg) return null;
    let groups = [...svg.querySelectorAll('[data-vrv-type="measure"]')];
    if (groups.length === 0) groups = [...svg.querySelectorAll("g.measure,[class*='measure']")];
    const i = ABS_INDEXES.indexOf(absIdx);
    if (i < 0 || i >= groups.length) return null;
    return groups[i];
  }

  function nearest(x, arr){
  if (!arr.length) return x;
  let best = arr[0], d = Math.abs(arr[0] - x);
  for (let i=1;i<arr.length;i++){ const di = Math.abs(arr[i]-x); if (di < d){ d=di; best=arr[i]; } }
  return best;
}

// Returns an array of edges with length = beats+1
function nearest(x, arr){
    if (!arr.length) return x;
    let best = arr[0], d = Math.abs(arr[0] - x);
    for (let i=1;i<arr.length;i++){
      const di = Math.abs(arr[i]-x);
      if (di < d){ d = di; best = arr[i]; }
    }
    return best;
  }

  // Returns an array of edges with length = beats+1
  function beatEdges(absIdx){
    const svg = svgRoot(); if (!svg) return null;

    let groups = svg.querySelectorAll('[data-vrv-type="measure"]');
    if (groups.length === 0)
      groups = svg.querySelectorAll("g.measure,[class*='measure']");

    const i = ABS_INDEXES.indexOf(absIdx);
    if (i < 0 || i >= groups.length) return null;

    const R = svg.getBoundingClientRect();
    const g = groups[i];
    const rr = _rectRel(g, R);
    const beats = beatsForMeasure(absIdx, 4);

    const edges = [rr.left];

    // Purely geometric partition, snapped to note columns.
    const xs = noteAnchorsInMeasure(g);       // x-centres of noteheads
    const width = rr.right - rr.left;

    for (let k = 1; k < beats; k++) {
      // ideal split position if the bar were divided evenly
      const ideal = rr.left + (k / beats) * width;

      // midpoints between neighbouring note columns
      const mids = [];
      for (let j = 0; j < xs.length - 1; j++)
        mids.push((xs[j] + xs[j + 1]) / 2);

      // snap ideal position to nearest midpoint (or keep ideal if none)
      let e = mids.length ? nearest(ideal, mids) : ideal;
      // enforce strictly increasing edges and stay inside the measure
      e = Math.max(edges[edges.length - 1] + 1, Math.min(rr.right - 1, e));
      edges.push(e);
    }

    edges.push(rr.right);
    return edges;
  }
function beatBoxBounds(absIdx, beatNumber) {
  const edges = beatEdges(absIdx); if (!edges) return null;
  const b = Math.max(1, Math.min(beatsForMeasure(absIdx,4), beatNumber)) - 1;
  const svg = svgRoot(); const R = svg.getBoundingClientRect();
  // recover verticals from the measure group
  const g = measureGroupByAbs(absIdx); const rr = _rectRel(g, R);
  return { left: edges[b], right: edges[b+1], top: rr.top, bottom: rr.bottom };
}

function noteGroupsWithin(g, leftPx, rightPx, includeRight=false) {
  const svg = svgRoot(); if (!svg) return [];
  const candidates = g.querySelectorAll("[data-vrv-type='note'], g.note, g.chord g.note");
  const arr = [];
  candidates.forEach((n) => {
    const r = n.getBoundingClientRect();
    const cx = (r.left + r.right) / 2;
    const inLeft  = cx >= leftPx;
    const inRight = includeRight ? (cx <= rightPx) : (cx < rightPx);
    if (inLeft && inRight) arr.push(n);
  });
  arr.sort((a,b)=>a.getBoundingClientRect().left - b.getBoundingClientRect().left);
  return arr;
}

  function eachDrawable(node, fn) {
    const tags = ["path","ellipse","circle","rect","polygon","polyline","use"];
    if (node.tagName && tags.includes(node.tagName.toLowerCase())) fn(node);
    node.querySelectorAll(tags.join(",")).forEach(fn);
  }
  function applyDirectHighlight(node, on=true) {
    eachDrawable(node, (el) => {
      if (on) {
        if (!el.hasAttribute("data-prev-fill"))   el.setAttribute("data-prev-fill", el.style.fill || "");
        if (!el.hasAttribute("data-prev-stroke")) el.setAttribute("data-prev-stroke", el.style.stroke || "");
        el.style.fill   = "#2563eb";
        el.style.stroke = "#1e40af";
      } else {
        const pf = el.getAttribute("data-prev-fill");
        const ps = el.getAttribute("data-prev-stroke");
        el.style.fill   = pf || "";
        el.style.stroke = ps || "";
      }
    });
  }
  function highlightOneNote(el, on=true) {
    if (!el) return;
    if (on) { el.classList.add("note-hl"); applyDirectHighlight(el, true); }
    else    { el.classList.remove("note-hl"); applyDirectHighlight(el, false); }
  }

function normPitchLabel(s){
  if (!s) return "";
  return s.toString().trim()
    .replace(/♯/g, "#").replace(/♭/g, "b").toUpperCase();
}

function readNodePitch(node){
  // Try attributes on the note group, then descend
  const tryFrom = (el) => {
    if (!el) return null;
    const p = (el.getAttribute("pname") || el.getAttribute("data-pname") || "").toUpperCase();
    let a = (el.getAttribute("accid") || el.getAttribute("data-accid") || "");
    const o = el.getAttribute("oct") || el.getAttribute("data-oct");
    if (!p || o == null) return null;
    a = a.replace(/s/g,"#").replace(/f/g,"b").replace(/♯/g,"#").replace(/♭/g,"b");
    return normPitchLabel(p + a + o);
  };
  return tryFrom(node) || tryFrom(node.querySelector("[pname],[data-pname]"));
}

function assignLabelsForBeat(absIdx, beatNo, nodes) {
  const labels = (
    (PITCH_MAP[String(absIdx)] && PITCH_MAP[String(absIdx)][String(beatNo)]) ||
    (PITCH_MAP[absIdx] && PITCH_MAP[absIdx][beatNo]) || []
  ).map(normPitchLabel);

  // Precompute node pitches
  const pool = nodes.map(n => ({ node:n, pitch: readNodePitch(n), used:false }));

  const out = [];

  // Pass 1: exact pitch matches
  labels.forEach(lbl => {
    const i = pool.findIndex(x => !x.used && x.pitch && x.pitch === lbl);
    if (i >= 0) { pool[i].used = true; out.push({ label: lbl, node: pool[i].node }); }
    else        { out.push({ label: lbl, node: null }); }
  });

  // Pass 2: fill unmatched labels with nearest unused node (by left-to-right)
  out.forEach((a, k) => {
    if (a.node) return;
    const i = pool.findIndex(x => !x.used);
    if (i >= 0) { pool[i].used = true; a.node = pool[i].node; }
  });

  // Pass 3: leftover nodes become “Note n”
  pool.forEach((x, i) => { if (!x.used) out.push({ label: `Note ${i+1}`, node: x.node }); });

  return out;
}

  function buildSidebar() {
    const list = document.getElementById("list"); list.innerHTML = "";
    const ordered = Array.from(SELECTED).sort((a,b) => {
      const [am,ab] = a.split("-").map(Number), [bm,bb] = b.split("-").map(Number);
      return am===bm ? ab-bb : am-bm;
    });
    ordered.forEach((key) => {
      const [absIdx, beatNo] = key.split("-").map(Number);
      const g = measureGroupByAbs(absIdx); if (!g) return;
      const bb = beatBoxBounds(absIdx, beatNo); if (!bb) return;
      const beats = beatsForMeasure(absIdx, 4);
      const notes = noteGroupsWithin(g, bb.left, bb.right, beatNo === beats);
      const assignments = assignLabelsForBeat(absIdx, beatNo, notes);

      let labeled = 0;
      const wrap = document.createElement("div"); wrap.className = "beat";
      const title = document.createElement("div"); wrap.appendChild(title);

      assignments.forEach(({label, node}) => {
        const item = document.createElement("div"); item.className = "note"; item.textContent = label;
        if (node && label && !/^Note \d+$/i.test(label)) labeled += 1;
        if (node) {
          item.addEventListener("click", (ev) => {
            ev.preventDefault(); ev.stopPropagation();
            const turnOn = !node.classList.contains("note-hl");
            highlightOneNote(node, turnOn);
            item.classList.toggle("note-hl", turnOn);
          });
        } else {
          item.style.opacity = "0.6";
          item.title = "No matching notehead on this page";
        }
        wrap.appendChild(item);
      });

      title.textContent = `m${absIdx} • beat ${beatNo} — ${notes.length} notes (labels: ${labeled}/${notes.length})`;
      list.appendChild(wrap);
    });
  }

  function _midX(r){ return (r.left + r.right) / 2; }

  function noteAnchorsInMeasure(g){
    // Collect x-centers of visual noteheads in this measure
    const cand = g.querySelectorAll("[data-vrv-type='note'], g.note, .note, use[href*='note']");
    const xs = [];
    cand.forEach(n => { const r = n.getBoundingClientRect(); xs.push(_midX(r)); });
    xs.sort((a,b)=>a-b);
    return xs;
  }

  function snapToNearest(x, xs){
    if (!xs.length) return x;
    let i = 0;
    while (i < xs.length && xs[i] < x) i++;
    if (i === 0) return xs[0];
    if (i === xs.length) return xs[xs.length - 1];
    return (Math.abs(xs[i] - x) < Math.abs(xs[i-1] - x)) ? xs[i] : xs[i-1];
  }


  function publishSelection() {
    const arr = Array.from(SELECTED).sort((a,b) => {
      const [am,ab] = a.split("-").map(Number), [bm,bb] = b.split("-").map(Number);
      return am===bm ? ab-bb : am-bm;
    });
    document.title = "BEATS:" + JSON.stringify(arr);
    buildSidebar();
  }

  function clearBeatBoxes() {
    const frame = document.getElementById("frame");
    frame.querySelectorAll(".beat-box").forEach((n)=>n.remove());
  }

  function buildBeatBoxes() {
  const svg = svgRoot(); if (!svg) return;
  const frame = document.getElementById("frame");
  const R = svg.getBoundingClientRect();
  clearBeatBoxes();

  let groups = [...svg.querySelectorAll('[data-vrv-type="measure"]')];
  if (groups.length === 0) groups = [...svg.querySelectorAll("g.measure,[class*='measure']")];
  const n = Math.min(groups.length, ABS_INDEXES.length);

  for (let i = 0; i < n; i++) {
    const absIdx = ABS_INDEXES[i];
    const g = groups[i];
    const rr = _rectRel(g, R);
    const beats = beatsForMeasure(absIdx, 4);
    const edges = beatEdges(absIdx); if (!edges) continue;
    const height = Math.max(0, rr.bottom - rr.top);

    for (let b = 0; b < beats; b++) {
      const L = edges[b], Rr = edges[b + 1];
      const key = `${absIdx}-${b + 1}`;
      const box = document.createElement("div");
      box.className = "beat-box" + (SELECTED.has(key) ? " sel" : "");
      box.style.left = `${L}px`; box.style.top = `${rr.top}px`;
      box.style.width = `${Math.max(0, Rr - L)}px`; box.style.height = `${height}px`;
      box.dataset.label = `m${absIdx} • beat ${b + 1}/${beats}`;
      box.addEventListener("click", (ev) => {
        ev.preventDefault(); ev.stopPropagation();
        if (SELECTED.has(key)) { SELECTED.delete(key); box.classList.remove("sel"); }
        else { SELECTED.add(key); box.classList.add("sel"); }
        publishSelection();
      }, { passive: false });
      frame.appendChild(box);
    }
  }

  document.getElementById("hud").textContent = `measures on page: ${n}`;
  publishSelection();
}

function _midX(r){ return (r.left + r.right) / 2; }

function noteAnchorsWithTime(g){
  const nodes = g.querySelectorAll("[data-vrv-type='note'], g.note, g.chord g.note");
  const out = [];
  nodes.forEach(n => {
    const r = n.getBoundingClientRect();
    const x = _midX(r);
    const s = n.getAttribute("tstamp") || n.getAttribute("data-tstamp") || n.getAttribute("t");
    const t = s ? parseFloat(s) : NaN;
    if (!Number.isNaN(t)) out.push({ x, t });
  });
  out.sort((a,b)=>a.x-b.x);
  return out;
}

function median(xs){
  if (!xs.length) return NaN;
  const s = xs.slice().sort((a,b)=>a-b);
  const k = Math.floor(s.length/2);
  return s.length % 2 ? s[k] : (s[k-1] + s[k]) / 2;
}

  window.addEventListener("resize", () => { if (svgRoot()) buildBeatBoxes(); });
</script>
</body></html>
"""

class BeatSelector(QWidget):
    """Static viewer that gets beat counts + pitch labels from pitches.json (extract_pitches.py)."""

    selectionChanged = pyqtSignal(list)  # emits ['absIdx-beat', ...]

    def __init__(self, mxl_path: str, pitches_json_path: str, xml_path: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.mxl_path = str(mxl_path)
        self.xml_path = str(xml_path or mxl_path)
        self.pitches_json_path = str(pitches_json_path)

        self.setWindowTitle("Beat Selector — JSON-driven")
        layout = QVBoxLayout(self); layout.setContentsMargins(0,0,0,0)

        # Top bar
        top = QHBoxLayout(); top.setContentsMargins(6,6,6,6)
        self.lbl = QLabel("Page 1")
        self.btn_prev = QPushButton("◀ Prev Page")
        self.btn_next = QPushButton("Next Page ▶")
        self.btn_clear = QPushButton("Clear")
        top.addWidget(self.lbl); top.addStretch(1)
        top.addWidget(self.btn_prev); top.addWidget(self.btn_next); top.addWidget(self.btn_clear)
        layout.addLayout(top)

        # Web view
        self.web = QWebEngineView(self)
        self.web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.web.titleChanged.connect(self._on_title_changed)
        layout.addWidget(self.web, 1)

        # Verovio render setup (only for SVG paging/layout)
        self._tk = verovio.toolkit()
        self._tk.setOptions({
            "pageHeight": 1800,
            "pageWidth": 1200,
            "scale": 40,
            "breaks": "auto",
            "adjustPageHeight": 1,
            "svgViewBox": 1,
            "svgAdditionalAttribute": "pname,accid,oct,midi"
        })
        self._tk.loadFile(self.mxl_path)
        self._tk.redoLayout()
        self._page_count = int(self._tk.getPageCount() or 1)

        # Build measure list (absolute indices) to map pages<->measures
        self.tempo_segments = build_tempo_segments(self.mxl_path)
        mt = build_measure_times(self.mxl_path)
        self.measures: List[Measure] = [
            Measure(i, int(m["number"]), float(m["start_ql"]), float(m["end_ql"]),
                    float(m["start_sec"]), float(m["end_sec"]))
            for i, m in enumerate(mt)
        ]

        # Load JSON labels (beats_by_measure) -> pitch_map + beats per measure
        self.pitch_map, self.measure_beats = self._load_pitch_map_from_json(self.pitches_json_path)

        # Page mapping (SVG -> absolute measure indexes)
        self._page_svgs: List[str] = []
        self._page_abs_indexes: List[List[int]] = []
        self._discover_pages_by_numbers()

        # Temp host files
        tmp = Path(tempfile.gettempdir())
        self._html_path = tmp / "beat_host.html"
        self._svg_path  = tmp / "beat_page.svg"
        self._current_page = -1

        # Wire buttons
        self.btn_prev.clicked.connect(lambda: self._load_page(self._current_page - 1))
        self.btn_next.clicked.connect(lambda: self._load_page(self._current_page + 1))
        self.btn_clear.clicked.connect(self._clear_selection)

        # Initial page
        self._load_page(0)

    # ---------- JSON → in-memory maps ----------
    def _load_pitch_map_from_json(self, json_path: str) -> tuple[dict, dict]:
        """
        Returns:
          pitch_map: { abs_idx: { beat_no: [labels...] } }
          measure_beats: { abs_idx: beats }
        """
        p = Path(json_path)
        if not p.exists():
            raise FileNotFoundError(f"pitches.json not found at: {json_path}")

        data = json.loads(p.read_text(encoding="utf-8"))
        beats_by_measure: Dict[str, Dict[str, List[str]]] = data.get("beats_by_measure", {})

        pitch_map: Dict[int, Dict[int, List[str]]] = {}
        measure_beats: Dict[int, int] = {}

        for k_abs, beats_dict in beats_by_measure.items():
            try:
                abs_idx = int(k_abs)
            except ValueError:
                continue
            # Normalize keys to ints and ensure order 1..N
            labels_per = {}
            max_beat = 0
            for beat_k, labels in beats_dict.items():
                try:
                    b = int(beat_k)
                except ValueError:
                    continue
                labels_per[b] = list(labels)
                if b > max_beat: max_beat = b

            if labels_per:
                pitch_map[abs_idx] = labels_per
                measure_beats[abs_idx] = max_beat
            else:
                # default to 4 if nothing there
                measure_beats[abs_idx] = 4

        return pitch_map, measure_beats

    # ---------- page/selection plumbing ----------
    def _on_title_changed(self, title: str):
        if not title.startswith("BEATS:"):
            return
        try:
            items = json.loads(title[len("BEATS:"):])
            self.selectionChanged.emit(items)
            self.lbl.setText(f"Page {self._current_page+1}/{self._page_count} — selected: {len(items)} beats")
        except Exception:
            pass

    def _discover_pages_by_numbers(self):
        """Map SVG measures to absolute measure indexes by their printed number."""
        self._page_svgs.clear()
        self._page_abs_indexes.clear()

        num_to_abs: Dict[int, int] = {}
        for m in self.measures:
            if m.number not in num_to_abs:
                num_to_abs[m.number] = m.index

        for p in range(self._page_count):
            svg = self._tk.renderToSVG(p + 1)
            self._page_svgs.append(svg)
            abs_list: List[int] = []
            try:
                root = ET.fromstring(svg)
                for g in root.iter():
                    tag = g.tag.split('}')[-1]
                    if tag != 'g': continue
                    typ = g.attrib.get('data-vrv-type') or g.attrib.get('data-type') or ''
                    if typ != 'measure' and 'measure' not in g.attrib.get('class', ''): continue
                    n_attr = g.attrib.get('n') or g.attrib.get('data-n') or ''
                    num = None
                    try:
                        if n_attr: num = int(str(n_attr).strip().split()[0])
                    except: num = None
                    if num is not None and num in num_to_abs:
                        abs_idx = num_to_abs[num]
                    else:
                        abs_idx = (abs_list[-1] + 1) if abs_list else sum(len(x) for x in self._page_abs_indexes)
                        abs_idx = min(abs_idx, len(self.measures) - 1)
                    abs_list.append(abs_idx)
            except Exception as e:
                dlog("SVG parse error:", e)
                count = svg.count('data-vrv-type="measure"') or svg.count('class="measure"') or 1
                base = sum(len(x) for x in self._page_abs_indexes)
                abs_list = [min(base + i, len(self.measures) - 1) for i in range(count)]
            self._page_abs_indexes.append(abs_list)

        if not self._page_abs_indexes:
            self._page_abs_indexes = [[i for i in range(len(self.measures))]]

    def _load_page(self, page: int):
        page = max(0, min(self._page_count - 1, page))
        self._svg_path.write_text(self._page_svgs[page], encoding="utf-8")

        abs_indexes = self._page_abs_indexes[page]
        svg_url = QUrl.fromLocalFile(str(self._svg_path)).toString()

        pitch_map_page = {i: self.pitch_map.get(i, {}) for i in abs_indexes}
        measure_beats_page = {i: self.measure_beats.get(i, 4) for i in abs_indexes}

        html = (
            _HTML
            .replace("{ABS_INDEXES_JSON}", json.dumps(abs_indexes))
            .replace("{PITCH_MAP_JSON}", json.dumps(pitch_map_page))
            .replace("{MEASURE_BEATS_JSON}", json.dumps(measure_beats_page))
            .replace("{SVG_URL}", svg_url)
        )

        self._html_path.write_text(html, encoding="utf-8")
        self._current_page = page
        self.lbl.setText(f"Page {page+1}/{self._page_count} — selected: 0 beats")
        self.web.load(QUrl.fromLocalFile(str(self._html_path)))

    def _clear_selection(self):
        self._load_page(self._current_page)


# --- convenience CLI ---------------------------------------------------------
def _main(argv: List[str]) -> int:
    """
    Args:
      argv[1] = path to .mxl (or .xml)
      argv[2] = path to pitches.json (from extract_pitches.py)
      argv[3] = optional path to original MusicXML (if different from argv[1])
    """
    from PyQt6.QtWidgets import QApplication
    if len(argv) < 3:
        print("Usage: python -m ui.beat_selector <score.mxl> <pitches.json> [score.xml]")
        return 2
    mxl = argv[1]
    pj = argv[2]
    xml = argv[3] if len(argv) > 3 else None

    app = QApplication(sys.argv)
    w = BeatSelector(mxl, pj, xml)
    w.resize(1200, 900)
    w.show()
    return app.exec()

if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
