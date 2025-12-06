# ui/score_view_beats.py
# Standalone viewer: same behaviour as ScoreView + static beat boxes
from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Tuple, Optional

from PyQt6.QtCore import Qt, QUrl, pyqtSlot
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QHBoxLayout,
    QPushButton,
    QApplication,
    QFileDialog,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
import verovio
import xml.etree.ElementTree as ET

from model.score_loader import (
    build_tempo_segments,         # -> [{start_ql,end_ql,bpm,start_sec,end_sec},]
    build_measure_times,          # -> [{"number", "start_ql","end_ql","start_sec","end_sec"}, .]
    ql_to_seconds,                # -> sec for absolute QL offset
    load_notes_from_mxl,          # -> (notes,bpm) notes: {"pitch","start","duration","staff"} in QL
)  

def dlog(*args): print("[ScoreViewBeats]", *args, flush=True)


@dataclass
class Measure:
    index: int
    number: int
    start_ql: float
    end_ql: float
    start_sec: float
    end_sec: float


# --- HTML/JS host -------------------------------------------------------------

_HTML = r'''
<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  :root {
    --hl-fill: rgba(255, 214, 10, 0.18);
    --hl-stroke: rgba(255, 149, 0, 0.75);
    --cursor: #ff3b30;
    --beat-fill: rgba(255, 214, 10, 0.14);
    --beat-stroke: rgba(255, 149, 0, 0.9);
  }
  html, body {
    margin:0; padding:0; background:#fff; height:100%; color:#111;
  }
  #frame {
    position:relative; width:100%; height:100vh; overflow:hidden; background:#fff;
  }
  #barHL {
    position:absolute; top:0; left:0; width:0; height:0;
    pointer-events:none; z-index:1000;
    background: var(--hl-fill);
    outline: 2px solid var(--hl-stroke);
    outline-offset:-2px; border-radius: 6px;
    transition: left .12s ease, top .12s ease,
                width .12s ease, height .12s ease;
  }
  #cursor {
    position:absolute; top:0; width:2px;
    background:var(--cursor); z-index:1010;
    transform: translateX(-1px);
  }
  #hud {
    position:absolute; right:8px; top:8px;
    color:#fff; font:12px/1.35 system-ui;
    background:rgba(0,0,0,.55);
    padding:6px 8px; border-radius:6px;
  }
  object, svg {
    display:block; width:100%; height:100%;
    background:#fff !important;
  }
  .beatBox {
    position:absolute;
    background:var(--beat-fill);
    outline:1px solid var(--beat-stroke);
    outline-offset:-1px;
    border-radius:4px;
    pointer-events:none;
    z-index:600; /* below barHL/cursor, above SVG */
    display:none; /* OFF by default */
  }
</style></head>
<body>
<div id="frame">
  <div id="barHL"></div>
  <div id="cursor"></div>
  <object id="page" type="image/svg+xml" data=""></object>
  <div id="hud">loading…</div>
</div>
<script>
  const ABS_INDEXES    = {ABS_INDEXES_JSON};
  const NOTE_TIMES_MAP = {NOTE_TIMES_MAP_JSON};
  const BEAT_TIMES_MAP = {BEAT_TIMES_MAP_JSON};
  const SNAP_T=0.06, NUDGE_T=0.25, NUDGE_GAIN=0.35, SMOOTH_ALPHA=0.4, MONO_TOL=1.5;

  let PAGE_IDX=0, READY_SVG=false;
  let BOXES_BY_ABS={}, ANCHORS_BY_ABS={}, ORDER_ABS=[];
  let QUEUED=null, LAST={page:-1, abs:-1, t:0, x:0}, LAST_HL=-1;

  // Static beat boxes
  let BEAT_BOXES=[];
  let BEAT_VISIBLE=false; // OFF by default

  const THEMES={
    amber:{fill:'rgba(255,214,10,0.18)', stroke:'rgba(255,149,0,0.75)', cursor:'#ff3b30'},
    sky:{fill:'rgba(56,189,248,0.18)', stroke:'rgba(2,132,199,0.75)', cursor:'#0ea5e9'},
    mint:{fill:'rgba(110,231,183,0.18)', stroke:'rgba(5,150,105,0.65)', cursor:'#10b981'},
    violet:{fill:'rgba(196,181,253,0.20)', stroke:'rgba(124,58,237,0.70)', cursor:'#8b5cf6'}
  };
  function setTheme(name){
    const t = THEMES[name] || THEMES.amber;
    const s = document.documentElement.style;
    s.setProperty('--hl-fill', t.fill);
    s.setProperty('--hl-stroke', t.stroke);
    s.setProperty('--cursor', t.cursor);
  }

  function svgDoc(){ const o=document.getElementById('page'); try{ return o.contentDocument; }catch(e){ return null; } }
  function svgRoot(){ const d=svgDoc(); return d? d.querySelector('svg') : null }

  function _rectRel(node, rootRect){
    const r=node.getBoundingClientRect();
    return {
      left:r.left-rootRect.left,
      right:r.right-rootRect.left,
      top:r.top-rootRect.top,
      bottom:r.bottom-rootRect.top
    };
  }
  function _midX(rect){ return (rect.left+rect.right)/2 }

  function _destroyBeatBoxes(){
    BEAT_BOXES.forEach(b => b.remove());
    BEAT_BOXES=[];
  }

  function _updateBeatVisibility(){
    const disp = BEAT_VISIBLE ? 'block' : 'none';
    BEAT_BOXES.forEach(b => { b.style.display = disp; });
  }

  function beatEdges(absIdx){
    const box = BOXES_BY_ABS[absIdx]; if (!box) return [];
    const ts = BEAT_TIMES_MAP[absIdx] || [];                 // metrical beats in this bar
    if (!ts.length) return [box.left, box.right];
    const beats = ts.length;
    const edges = [box.left];
    for (let k=1;k<beats;k++){
        // even slice first…
        const even = box.left + (box.right - box.left) * (k / beats);
        edges.push(even);
    }
    edges.push(box.right);

    // optional cosmetic snap toward note midpoints
    const xs = (ANCHORS_BY_ABS[absIdx] || []).slice();
    if (xs.length >= 2) {
        const mids = [];
        for (let i=0;i<xs.length-1;i++) mids.push((xs[i]+xs[i+1])/2);
        const maxShiftFrac = 0.25, minW = Math.max(18, (box.right-box.left)*0.07);
        for (let i=1;i<edges.length-1;i++){
        const slotW = Math.max(1, edges[i+1]-edges[i-1]);
        const maxShift = slotW*maxShiftFrac;
        let best = mids[0], d = Math.abs(mids[0]-edges[i]);
        for (let j=1;j<mids.length;j++){ const dj=Math.abs(mids[j]-edges[i]); if (dj<d){ d=dj; best=mids[j]; } }
        let snapped = best;
        if (Math.abs(snapped-edges[i])>maxShift) snapped = edges[i] + Math.sign(snapped-edges[i])*maxShift;
        edges[i] = Math.max(edges[i-1]+minW, Math.min(edges[i+1]-minW, snapped));
        }
    }
    return edges;
    }

function _ensureBeatBoxes(){
  const frame = document.getElementById('frame');
  _destroyBeatBoxes();
  for (const abs of ORDER_ABS){
    const box = BOXES_BY_ABS[abs]; if(!box) continue;
    const edges = beatEdges(abs); if (edges.length < 2) continue;
    for (let b=0;b<edges.length-1;b++){
      const div = document.createElement('div');
      div.className = 'beatBox';
      const pad=2;
      div.style.left   = (Math.round(edges[b])   + pad) + 'px';
      div.style.top    = (Math.round(box.top)    + pad) + 'px';
      div.style.width  = Math.max(0, Math.round(edges[b+1]-edges[b]) - pad*2) + 'px';
      div.style.height = Math.max(0, Math.round(box.bottom-box.top) - pad*2) + 'px';
      frame.appendChild(div);
      BEAT_BOXES.push(div);
    }
  }
  _updateBeatVisibility();
}


  // Called from Python
  function setBeatBoxesVisible(on){
    BEAT_VISIBLE = !!on;
    _updateBeatVisibility();
  }

 function _scan(){
  const svg = svgRoot(); if (!svg) return;
  const R = svg.getBoundingClientRect();
  BOXES_BY_ABS = {}; ANCHORS_BY_ABS = {}; ORDER_ABS = [];
  let groups = [...svg.querySelectorAll('[data-vrv-type="measure"]')];
  if (groups.length === 0)
    groups = [...svg.querySelectorAll('g.measure,[class*="measure"]')];

  const n = Math.min(groups.length, ABS_INDEXES.length);
  for (let i = 0; i < n; i++){
    const abs = ABS_INDEXES[i], g = groups[i];

    // 1) start from full measure box
    let box = _rectRel(g, R);

    // 2) shrink vertically to staff area if possible
    const staffEls = g.querySelectorAll('[data-vrv-type="staff"], .staff');
    let top = Infinity, bottom = -Infinity;
    staffEls.forEach(el => {
      const r = _rectRel(el, R);
      top    = Math.min(top, r.top);
      bottom = Math.max(bottom, r.bottom);
    });
    if (isFinite(top) && isFinite(bottom)) {
      box.top    = top - 4;      // small padding
      box.bottom = bottom + 4;
    }

    // 3) collect note anchors (unchanged)
    const cand = g.querySelectorAll('[data-vrv-type="note"], g.note, .note, use[href*="note"]');
    const xs = [];
    cand.forEach(el => {
      const rr = el.getBoundingClientRect();
      if (rr && isFinite(rr.left) && isFinite(rr.right))
        xs.push(_midX(_rectRel(el, R)));
    });
    xs.sort((a,b) => a - b);
    const filtered = [];
    for (const x of xs){
      if (!filtered.length || Math.abs(filtered[filtered.length-1] - x) > 2)
        filtered.push(x);
    }

    // 4) shrink horizontally to first/last note (so we don't follow slurs/dynamics)
    if (filtered.length){
      const padX = Math.max(10, (box.right - box.left) * 0.05);
      box.left  = filtered[0] - padX;
      box.right = filtered[filtered.length - 1] + padX;
    }

    BOXES_BY_ABS[abs] = box;
    ORDER_ABS.push(abs);
    ANCHORS_BY_ABS[abs] = filtered;
  }

  READY_SVG = true;
  _ensureBeatBoxes();          // unchanged
  document.getElementById('hud').textContent =
      `page=${PAGE_IDX} measures=${ORDER_ABS.length}`;
}

  function _span(xs, box){
    if(xs.length>=2) return [xs[0], xs[xs.length-1]];
    if(xs.length===1){
      const pad=Math.max(12,(box.right-box.left)*0.08);
      return [xs[0]-pad*0.5, xs[0]+pad*0.5];
    }
    const pad=(box.right-box.left)*0.08;
    return [box.left+pad, box.right-pad];
  }
  function _nearest(ts, t){
    if(!ts || !ts.length) return [-1, 1e9];
    let lo=0, hi=ts.length-1;
    while(lo<hi){
      const m=(lo+hi)>>1;
      if(ts[m]<t) lo=m+1; else hi=m;
    }
    let idx=lo, d=Math.abs(ts[idx]-t);
    if(idx>0 && Math.abs(ts[idx-1]-t)<d){
      idx-=1; d=Math.abs(ts[idx]-t);
    }
    return [idx, d];
  }
  function _lerp(a,b,u){ return a + Math.max(0,Math.min(1,u))*(b-a); }

  function _place(x, box){
    const c=document.getElementById('cursor');
    c.style.left=`${x}px`;
    c.style.top=`${box.top}px`;
    c.style.height=`${box.bottom-box.top}px`;
  }
  function _placeHL(box){
    const hl=document.getElementById('barHL');
    const pad=2;
    hl.style.left  = `${box.left+pad}px`;
    hl.style.top   = `${box.top+pad}px`;
    hl.style.width = `${Math.max(0,(box.right-box.left)-pad*2)}px`;
    hl.style.height= `${Math.max(0,(box.bottom-box.top)-pad*2)}px`;
  }

  function _compute(absIdx, t, dur){
    const box = BOXES_BY_ABS[absIdx]; if(!box) return null;
    const D=Math.max(1e-6,dur), tt=Math.max(0,Math.min(D,t));
    const xs = ANCHORS_BY_ABS[absIdx]||[];
    const [xL,xR] = _span(xs, box);
    let x_lin = _lerp(xL, xR, tt/D);

    const ts = NOTE_TIMES_MAP[absIdx]||[];
    const [k, dT] = _nearest(ts, tt);
    if(k>=0 && xs.length){
      if(dT<=SNAP_T) x_lin = xs[Math.min(k, xs.length-1)];
      else if(dT<=NUDGE_T){
        const w=NUDGE_GAIN*(1 - dT/NUDGE_T);
        const xn=xs[Math.min(k, xs.length-1)];
        x_lin = x_lin + w*(xn - x_lin);
      }
    }
    let x_out = x_lin;
    if(LAST.page===PAGE_IDX && LAST.abs===absIdx && tt>=LAST.t){
      x_out = LAST.x + SMOOTH_ALPHA*(x_lin - LAST.x);
      if(x_out + MONO_TOL < LAST.x) x_out = LAST.x;
    }
    return [x_out, box, tt];
  }

  function jsSetCursorAbs(absIdx, tInMeasure, dur){
    QUEUED=[absIdx, tInMeasure, dur];
    if(!READY_SVG) return;
    const r=_compute(absIdx, tInMeasure, dur); if(!r) return;
    const [x, box, t] = r;
    _place(x, box);
    if(LAST_HL!==absIdx){
      _placeHL(box); LAST_HL=absIdx;
    }
    LAST={page:PAGE_IDX, abs:absIdx, t:t, x:x};
    document.getElementById('hud').textContent =
      `page=${PAGE_IDX} abs=${absIdx} x=${Math.round(x)} t=${t.toFixed(3)}s`;
  }

  function setPageAndSvg(pageIndex, svgUrl){
    PAGE_IDX=pageIndex; READY_SVG=false;
    LAST={page:-1,abs:-1,t:0,x:0}; LAST_HL=-1;
    _destroyBeatBoxes();
    const obj=document.getElementById('page');
    obj.addEventListener('load', function onLoad(){
      obj.removeEventListener('load', onLoad);
      _scan();
      if(QUEUED){
        const [a,t,d]=QUEUED;
        const r=_compute(a,t,d);
        if(r){
          const [x,box,tt]=r;
          _place(x,box); _placeHL(box);
          LAST_HL=a; LAST={page:PAGE_IDX,abs:a,t:tt,x:x};
        }
      }
      setTheme('amber');
    }, {once:true});
    obj.data = (svgUrl.indexOf('?')===-1 ? svgUrl+'?ts='+Date.now() : svgUrl);
  }

  window.addEventListener('resize', ()=>{
    if(!svgRoot()) return;
    _scan();
    if(QUEUED){
      const [a,t,d]=QUEUED;
      const r=_compute(a,t,d);
      if(r){
        const [x,box,tt]=r;
        _place(x,box); _placeHL(box);
        LAST_HL=a; LAST={page:PAGE_IDX,abs:a,t:tt,x:x};
      }
    }
  });
</script>
</body></html>
'''


# --- QWidget wrapper ----------------------------------------------------------

class ScoreViewBeats(QWidget):
    """
    Variant of ScoreView: same cursor behaviour, but all beat/measure boxes
    are drawn at once and can be toggled on/off.
    """

    musicTimeChanged = None  # placeholder; view is passive and driven externally

    def __init__(self, mxl_path: str, xml_path: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.mxl_path = str(mxl_path)
        self.xml_path = str(xml_path or mxl_path)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        top.setContentsMargins(6, 6, 6, 6)
        self.lbl = QLabel("Score (static beat boxes)")
        self.lbl.setStyleSheet("color:#fff;")
        top.addWidget(self.lbl)

        top.addStretch(1)
        # Toggle button for beat boxes
        self._beats_visible = False
        self.btnBeats = QPushButton("Show beats")
        self.btnBeats.setCheckable(True)
        self.btnBeats.setChecked(False)
        self.btnBeats.clicked.connect(self._on_toggle_beats)
        top.addWidget(self.btnBeats)

        layout.addLayout(top)

        self.web = QWebEngineView(self)
        self.web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        layout.addWidget(self.web, 1)

        # Verovio render
        self._tk = verovio.toolkit()
        self._tk.setOptions({
            "pageHeight": 1800,
            "pageWidth": 1200,
            "scale": 40,
            "breaks": "auto",
            "adjustPageHeight": 1,
            "svgViewBox": 1,
        })
        self._tk.loadFile(self.mxl_path)
        self._tk.redoLayout()
        self._page_count = int(self._tk.getPageCount() or 1)

        # Musical timing from loader
        self.tempo_segments = build_tempo_segments(self.mxl_path)
        mt = build_measure_times(self.mxl_path)
        self.measures: List[Measure] = [
            Measure(
                i,
                int(m["number"]),
                float(m["start_ql"]),
                float(m["end_ql"]),
                float(m["start_sec"]),
                float(m["end_sec"]),
            )
            for i, m in enumerate(mt)
        ]

        # Onsets per measure (seconds relative)
        self.onsets_by_index: List[List[float]] = self._build_onsets()
        self.beats_by_index = self._build_beats()
        # Build paging map by parsing each page SVG for measure numbers ("n" attribute)
        self._page_svgs: List[str] = []
        self._page_abs_indexes: List[List[int]] = []  # per page, abs measure indexes
        self._index_to_page: Dict[int, int] = {}
        self._discover_pages_by_numbers()

        # temp files + initial page
        tmp = Path(tempfile.gettempdir())
        self._html_path = tmp / "score_host_beats.html"
        self._svg_path = tmp / "score_page_beats.svg"
        self._html_path.write_text(_HTML, encoding="utf-8")
        self._current_page = -1
        self._html_ready = False
        self._pending_sec: Optional[float] = None
        self._last_logged: Tuple[int, int] | None = None

        self._load_page(0)

    # --- beat toggle API ------------------------------------------------------

    def _on_toggle_beats(self, checked: bool):
        self.set_beats_visible(checked)

    def set_beats_visible(self, visible: bool):
        """Public method: show/hide all beat boxes."""
        self._beats_visible = bool(visible)
        try:
            self.web.page().runJavaScript(
                f"setBeatBoxesVisible({str(self._beats_visible).lower()});"
            )
        except Exception:
            pass
        self.btnBeats.setText("Hide beats" if self._beats_visible else "Show beats")

    def _build_beats(self):
        beats = [[] for _ in self.measures]
        for i, m in enumerate(self.measures):
            bar_ql = m.end_ql - m.start_ql
            n_beats = max(1, int(round(bar_ql)))   # quarter = beat (2/4,3/4,4/4…)
            step_ql = bar_ql / n_beats
            row=[]
            for k in range(n_beats):
                ql = m.start_ql + k*step_ql
                row.append(max(0.0, ql_to_seconds(self.tempo_segments, ql) - m.start_sec))
            beats[i]=row
        return beats
    # --- core implementation (mostly copied from original ScoreView) ---------

    def _build_onsets(self) -> List[List[float]]:
        notes, _ = load_notes_from_mxl(self.mxl_path, self.xml_path)
        arr = [[] for _ in self.measures]

        # precompute for binary search
        starts = [m.start_ql for m in self.measures]

        def find_idx(ql: float) -> int:
            lo, hi = 0, len(starts) - 1
            while lo <= hi:
                mid = (lo + hi) // 2
                m = self.measures[mid]
                if ql < m.start_ql:
                    hi = mid - 1
                elif ql >= m.end_ql:
                    lo = mid + 1
                else:
                    return mid
            return max(0, min(len(starts) - 1, lo))

        for n in notes:
            ql = float(n["start"])
            i = find_idx(ql)
            m = self.measures[i]
            sec = ql_to_seconds(self.tempo_segments, ql)
            arr[i].append(max(0.0, sec - m.start_sec))

        # sort & dedup 10ms
        for i, L in enumerate(arr):
            L.sort()
            uniq = []
            for t in L:
                if not uniq or abs(t - uniq[-1]) > 0.010:
                    uniq.append(t)
            arr[i] = uniq
        return arr

    def _discover_pages_by_numbers(self):
        self._page_svgs.clear()
        self._page_abs_indexes.clear()
        self._index_to_page.clear()

        # helper: build mapping measure number -> absolute index in our measures
        num_to_abs: Dict[int, int] = {}
        for m in self.measures:
            if m.number not in num_to_abs:
                num_to_abs[m.number] = m.index

        for p in range(self._page_count):
            svg = self._tk.renderToSVG(p + 1)  # 1-based API
            self._page_svgs.append(svg)
            abs_list: List[int] = []
            try:
                root = ET.fromstring(svg)
                # find all groups that declare data-vrv-type="measure"
                for g in root.iter():
                    tag = g.tag.split("}")[-1]
                    if tag != "g":
                        continue
                    typ = g.attrib.get("data-vrv-type") or g.attrib.get("data-type") or ""
                    if typ != "measure" and "measure" not in g.attrib.get("class", ""):
                        continue
                    n_attr = g.attrib.get("n") or g.attrib.get("data-n") or ""
                    num = None
                    try:
                        if n_attr:
                            num = int(str(n_attr).strip().split()[0])
                    except Exception:
                        num = None
                    if num is not None and num in num_to_abs:
                        abs_idx = num_to_abs[num]
                    else:
                        # fallback: continue sequentially
                        abs_idx = (abs_list[-1] + 1) if abs_list else len(
                            sum(self._page_abs_indexes, [])
                        )
                        abs_idx = min(abs_idx, len(self.measures) - 1)
                    abs_list.append(abs_idx)
            except Exception as e:
                dlog("SVG parse error:", e)
                # fallback: attempt to count measures by substring
                count = (
                    svg.count('data-vrv-type="measure"')
                    or svg.count('class="measure"')
                    or 1
                )
                base = len(sum(self._page_abs_indexes, []))
                abs_list = [
                    min(base + i, len(self.measures) - 1) for i in range(count)
                ]

            self._page_abs_indexes.append(abs_list)
            for a in abs_list:
                self._index_to_page[a] = p

        if not self._page_abs_indexes:
            self._page_abs_indexes = [[i for i in range(len(self.measures))]]
            self._index_to_page = {i: 0 for i in range(len(self.measures))}

    def _page_for_index(self, abs_idx: int) -> int:
        return self._index_to_page.get(abs_idx, 0)

    def _load_page(self, page: int):
        page = max(0, min(self._page_count - 1, page))
        self._svg_path.write_text(self._page_svgs[page], encoding="utf-8")

        # build injection arrays
        abs_indexes = self._page_abs_indexes[page]
        note_times_map = {
            i: self.onsets_by_index[i]
            for i in abs_indexes
            if i < len(self.onsets_by_index)
        }
        beat_times_map = {i: self.beats_by_index[i] for i in abs_indexes if i < len(self.beats_by_index)}
        html = (
            _HTML.replace("{ABS_INDEXES_JSON}", json.dumps(abs_indexes))
            .replace("{NOTE_TIMES_MAP_JSON}", json.dumps(note_times_map))
            .replace("{BEAT_TIMES_MAP_JSON}", json.dumps(beat_times_map))
        )
        self._html_path.write_text(html, encoding="utf-8")

        self._html_ready = False
        self._current_page = page
        self.lbl.setText(
            f"Score — page {page+1}/{self._page_count} (beat boxes off)"
        )

        try:
            self.web.loadFinished.disconnect()
        except Exception:
            pass

        def on_loaded(ok: bool):
            self._html_ready = True
            self.web.page().runJavaScript(
                f"setPageAndSvg({page}, {json.dumps(self._svg_path.as_uri())});"
            )
            # ensure our beat visibility state is applied
            self.set_beats_visible(self._beats_visible)
            if self._pending_sec is not None:
                sec = self._pending_sec
                self._pending_sec = None
                self._apply_time(sec)

        self.web.load(QUrl.fromLocalFile(str(self._html_path)))
        self.web.loadFinished.connect(on_loaded)

    # --- time-driven cursor (unchanged API) ----------------------------------

    @pyqtSlot(float)
    def set_music_time(self, sec: float):
        if not self._html_ready:
            self._pending_sec = sec
            return
        self._apply_time(sec)

    def _measure_for_time(self, sec: float) -> int:
        lo, hi = 0, len(self.measures) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            m = self.measures[mid]
            if sec < m.start_sec:
                hi = mid - 1
            elif sec >= m.end_sec:
                lo = mid + 1
            else:
                return mid
        return max(0, min(len(self.measures) - 1, lo))

    def _apply_time(self, sec: float):
        if not self.measures:
            return
        m_idx = self._measure_for_time(sec)
        m = self.measures[m_idx]
        page = self._page_for_index(m_idx)
        if page != self._current_page:
            self._pending_sec = sec
            self._load_page(page)
            return
        dur = max(1e-6, m.end_sec - m.start_sec)
        t_in = max(0.0, sec - m.start_sec)
        self.web.page().runJavaScript(
            f"jsSetCursorAbs({int(m_idx)}, {float(t_in)}, {float(dur)})"
        )
        if self._last_logged != (page, m_idx):
            dlog(
                f"page={page} meas_abs={m_idx} num={m.number} "
                f"t_in={t_in:.3f}/{dur:.3f}"
            )
            self._last_logged = (page, m_idx)
        self.lbl.setText(
            f"t={sec:7.3f}s  page {page+1}/{self._page_count}  "
            f"meas {m_idx} (no.{m.number})  t={t_in:0.3f}/{dur:0.3f}s"
        )


# --- simple executable harness ------------------------------------------------

def _pick_file_if_needed(path: Optional[str]) -> Optional[str]:
    if path:
        return path
    dlg = QFileDialog()
    dlg.setFileMode(QFileDialog.FileMode.ExistingFile)
    dlg.setNameFilter("Scores (*.mxl *.xml *.musicxml)")
    if dlg.exec():
        files = dlg.selectedFiles()
        if files:
            return files[0]
    return None


def main(argv: List[str] | None = None):
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)

    mxl_path = _pick_file_if_needed(argv[1] if len(argv) > 1 else None)
    if not mxl_path:
        print("No score selected, exiting.")
        return 0

    w = ScoreViewBeats(mxl_path)
    w.resize(900, 700)
    w.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
