
# ui/score_view.py — robust, SMOOTH, measure-aware cursor with stable page mapping (by measure numbers)
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Tuple, Optional

from PyQt6.QtCore import Qt, QUrl, pyqtSlot
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout
from PyQt6.QtWebEngineWidgets import QWebEngineView
import verovio
import xml.etree.ElementTree as ET

from model.score_loader import (
    build_tempo_segments,         # -> [{start_ql,end_ql,bpm,start_sec,end_sec},]
    build_measure_times,          # -> [{"number", "start_ql","end_ql","start_sec","end_sec"}, .]
    ql_to_seconds,                # -> sec for absolute QL offset
    load_notes_from_mxl,          # -> (notes,bpm) notes: {"pitch","start","duration","staff"} in QL
)

def dlog(*args): print("[ScoreView]", *args, flush=True)

@dataclass
class Measure:
    index: int
    number: int
    start_ql: float
    end_ql: float
    start_sec: float
    end_sec: float

_HTML = r"""
<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  /* Light theme so music (black strokes) has strong contrast */
  html, body { margin:0; padding:0; background:#fff; height:100%; color:#111; }
  #frame { position:relative; width:100%; height:100vh; overflow:hidden; background:#fff; }
  #cursor { position:absolute; top:0; width:2px; background:#ff3b30; z-index:9999; transform: translateX(-1px); }
  #hud { position:absolute; right:8px; top:8px; color:#fff; font:12px/1.35 system-ui;
         background:rgba(0,0,0,.55); padding:6px 8px; border-radius:6px; }
  /* Ensure the embedded Verovio SVG never shows a dark backdrop */
  object, svg { display:block; width:100%; height:100%; background:#fff !important; }
</style></head>
<body>
<div id="frame">
  <div id="cursor"></div>
  <object id="page" type="image/svg+xml" data=""></object>
  <div id="hud">loading…</div>
</div>
<script>
  const ABS_INDEXES    = {ABS_INDEXES_JSON};
  const NOTE_TIMES_MAP = {NOTE_TIMES_MAP_JSON};

  const SNAP_T=0.06, NUDGE_T=0.25, NUDGE_GAIN=0.35, SMOOTH_ALPHA=0.4, MONO_TOL=1.5;

  let PAGE_IDX=0, READY_SVG=false;
  let BOXES_BY_ABS={}, ANCHORS_BY_ABS={}, ORDER_ABS=[];
  let QUEUED=null, LAST={page:-1, abs:-1, t:0, x:0};

  function svgDoc(){ const o=document.getElementById('page'); try{ return o.contentDocument; }catch(e){ return null; } }
  function svgRoot(){ const d=svgDoc(); return d? d.querySelector('svg') : null }

  function _rectRel(node, rootRect){
    const r=node.getBoundingClientRect();
    return {left:r.left-rootRect.left, right:r.right-rootRect.left, top:r.top-rootRect.top, bottom:r.bottom-rootRect.top};
  }
  function _midX(rect){ return (rect.left+rect.right)/2 }

  function _scan(){
    const svg=svgRoot(); if(!svg) return;
    const R=svg.getBoundingClientRect();
    BOXES_BY_ABS={}; ANCHORS_BY_ABS={}; ORDER_ABS=[];
    let groups=[...svg.querySelectorAll('[data-vrv-type="measure"]')];
    if(groups.length===0) groups=[...svg.querySelectorAll('g.measure,[class*="measure"]')];

    const n=Math.min(groups.length, ABS_INDEXES.length);
    for(let i=0;i<n;i++){
      const abs=ABS_INDEXES[i], g=groups[i];
      const box=_rectRel(g, R);
      BOXES_BY_ABS[abs]=box; ORDER_ABS.push(abs);

      const cand = g.querySelectorAll('[data-vrv-type="note"], g.note, .note, use[href*="note"]');
      const xs=[];
      cand.forEach(el=>{
        const rr=el.getBoundingClientRect();
        if(rr && isFinite(rr.left) && isFinite(rr.right)) xs.push(_midX(_rectRel(el, R)));
      });
      xs.sort((a,b)=>a-b);
      const filtered=[]; for(const x of xs){ if(!filtered.length || Math.abs(filtered[filtered.length-1]-x)>2) filtered.push(x); }
      ANCHORS_BY_ABS[abs]=filtered;
    }
    READY_SVG=true;
    document.getElementById('hud').textContent = `page=${PAGE_IDX} measures=${ORDER_ABS.length}`;
  }

  function _span(xs, box){
    if(xs.length>=2) return [xs[0], xs[xs.length-1]];
    if(xs.length===1){ const pad=Math.max(12,(box.right-box.left)*0.08); return [xs[0]-pad*0.5, xs[0]+pad*0.5]; }
    const pad=(box.right-box.left)*0.08; return [box.left+pad, box.right-pad];
  }
  function _nearest(ts, t){
    if(!ts || !ts.length) return [-1, 1e9];
    let lo=0, hi=ts.length-1;
    while(lo<hi){ const m=(lo+hi)>>1; if(ts[m]<t) lo=m+1; else hi=m; }
    let idx=lo, d=Math.abs(ts[idx]-t);
    if(idx>0 && Math.abs(ts[idx-1]-t)<d){ idx-=1; d=Math.abs(ts[idx]-t); }
    return [idx, d];
  }
  function _lerp(a,b,u){ return a + Math.max(0,Math.min(1,u))*(b-a); }

  function _place(x, box){
    const c=document.getElementById('cursor');
    c.style.left=`${x}px`; c.style.top=`${box.top}px`; c.style.height=`${box.bottom-box.top}px`;
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
    const [x, box, t] = r; _place(x, box); LAST={page:PAGE_IDX, abs:absIdx, t:t, x:x};
    document.getElementById('hud').textContent = `page=${PAGE_IDX} abs=${absIdx} x=${Math.round(x)} t=${t.toFixed(3)}s`;
  }

  function setPageAndSvg(pageIndex, svgUrl){
    PAGE_IDX=pageIndex; READY_SVG=false; LAST={page:-1,abs:-1,t:0,x:0};
    const obj=document.getElementById('page');
    obj.addEventListener('load', function onLoad(){
      obj.removeEventListener('load', onLoad);
      _scan();
      if(QUEUED){ const [a,t,d]=QUEUED; const r=_compute(a,t,d); if(r){ const [x,box,tt]=r; _place(x,box); LAST={page:PAGE_IDX,abs:a,t:tt,x:x}; } }
    }, {once:true});
    obj.data = (svgUrl.indexOf('?')===-1 ? svgUrl+'?ts='+Date.now() : svgUrl);
  }

  window.addEventListener('resize', ()=>{
    if(!svgRoot()) return;
    _scan();
    if(QUEUED){ const [a,t,d]=QUEUED; const r=_compute(a,t,d); if(r){ const [x,box,tt]=r; _place(x,box); LAST={page:PAGE_IDX,abs:a,t:tt,x:x}; } }
  });
</script>
</body></html>
"""

class ScoreView(QWidget):
    musicTimeChanged = None  # placeholder; view is passive and driven by PianoRoll

    def __init__(self, mxl_path: str, xml_path: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.mxl_path = str(mxl_path)
        self.xml_path = str(xml_path or mxl_path)

        layout = QVBoxLayout(self); layout.setContentsMargins(0,0,0,0)
        top = QHBoxLayout(); top.setContentsMargins(6,6,6,6)
        self.lbl = QLabel("Score"); self.lbl.setStyleSheet("color:#fff;")
        top.addWidget(self.lbl); top.addStretch(1); layout.addLayout(top)
        self.web = QWebEngineView(self); self.web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        layout.addWidget(self.web, 1)

        # Verovio render
        self._tk = verovio.toolkit()
        self._tk.setOptions({ "pageHeight": 1800, "pageWidth": 1200, "scale": 40, "breaks": "auto", "adjustPageHeight": 1, "svgViewBox": 1 })
        self._tk.loadFile(self.mxl_path)
        self._tk.redoLayout()
        self._page_count = int(self._tk.getPageCount() or 1)

        # Musical timing from loader
        self.tempo_segments = build_tempo_segments(self.mxl_path)
        mt = build_measure_times(self.mxl_path)
        self.measures: List[Measure] = [
            Measure(i, int(m["number"]), float(m["start_ql"]), float(m["end_ql"]), float(m["start_sec"]), float(m["end_sec"]))
            for i,m in enumerate(mt)
        ]

        # Onsets per measure (seconds relative)
        self.onsets_by_index: List[List[float]] = self._build_onsets()

        # Build paging map by parsing each page SVG for measure numbers ("n" attribute)
        self._page_svgs: List[str] = []
        self._page_abs_indexes: List[List[int]] = []  # per page, abs measure indexes in visual order
        self._index_to_page: Dict[int,int] = {}
        self._discover_pages_by_numbers()

        # temp files + initial page
        tmp = Path(tempfile.gettempdir())
        self._html_path = tmp / "score_host.html"
        self._svg_path = tmp / "score_page.svg"
        self._html_path.write_text(_HTML, encoding="utf-8")
        self._current_page = -1
        self._html_ready = False
        self._pending_sec: Optional[float] = None
        self._last_logged: Tuple[int,int] | None = None

        self._load_page(0)

    def _build_onsets(self) -> List[List[float]]:
        notes, _ = load_notes_from_mxl(self.mxl_path, self.xml_path)
        arr = [[] for _ in self.measures]
        # precompute for binary search
        starts = [m.start_ql for m in self.measures]
        def find_idx(ql: float) -> int:
            lo, hi = 0, len(starts)-1
            while lo<=hi:
                mid=(lo+hi)//2
                m=self.measures[mid]
                if ql < m.start_ql: hi=mid-1
                elif ql >= m.end_ql: lo=mid+1
                else: return mid
            return max(0, min(len(starts)-1, lo))

        for n in notes:
            ql=float(n["start"])
            i=find_idx(ql)
            m=self.measures[i]
            sec=ql_to_seconds(self.tempo_segments, ql)
            arr[i].append(max(0.0, sec - m.start_sec))
        # sort & dedup 10ms
        for i, L in enumerate(arr):
            L.sort()
            uniq=[]; 
            for t in L:
                if not uniq or abs(t-uniq[-1])>0.010: uniq.append(t)
            arr[i]=uniq
        return arr

    def _discover_pages_by_numbers(self):
        self._page_svgs.clear()
        self._page_abs_indexes.clear()
        self._index_to_page.clear()

        # helper: build mapping measure number -> absolute index in our measures
        num_to_abs: Dict[int,int] = {}
        for m in self.measures:
            if m.number not in num_to_abs:
                num_to_abs[m.number] = m.index

        for p in range(self._page_count):
            svg = self._tk.renderToSVG(p+1)  # 1-based API
            self._page_svgs.append(svg)
            abs_list: List[int] = []
            try:
                root = ET.fromstring(svg)
                # find all groups that declare data-vrv-type="measure"
                for g in root.iter():
                    tag = g.tag.split('}')[-1]
                    if tag != 'g': continue
                    typ = g.attrib.get('data-vrv-type') or g.attrib.get('data-type') or ''
                    if typ != 'measure' and 'measure' not in g.attrib.get('class',''):
                        continue
                    n_attr = g.attrib.get('n') or g.attrib.get('data-n') or ''
                    num = None
                    try:
                        if n_attr:
                            num = int(str(n_attr).strip().split()[0])
                    except: num = None
                    abs_idx = None
                    if num is not None and num in num_to_abs:
                        abs_idx = num_to_abs[num]
                    else:
                        # fallback: continue sequentially
                        abs_idx = (abs_list[-1]+1) if abs_list else len(sum(self._page_abs_indexes, []))
                        abs_idx = min(abs_idx, len(self.measures)-1)
                    abs_list.append(abs_idx)
            except Exception as e:
                dlog("SVG parse error:", e)
                # fallback: attempt to count measures by substring
                count = svg.count('data-vrv-type="measure"') or svg.count('class="measure"') or 1
                base = len(sum(self._page_abs_indexes, []))
                abs_list = [min(base+i, len(self.measures)-1) for i in range(count)]

            self._page_abs_indexes.append(abs_list)
            for a in abs_list:
                self._index_to_page[a] = p

        if not self._page_abs_indexes:
            self._page_abs_indexes = [[i for i in range(len(self.measures))]]
            self._index_to_page = {i:0 for i in range(len(self.measures))}

    def _page_for_index(self, abs_idx: int) -> int:
        return self._index_to_page.get(abs_idx, 0)

    def _load_page(self, page: int):
        page = max(0, min(self._page_count-1, page))
        self._svg_path.write_text(self._page_svgs[page], encoding="utf-8")

        # build injection arrays
        abs_indexes = self._page_abs_indexes[page]
        note_times_map = {i: self.onsets_by_index[i] for i in abs_indexes if i < len(self.onsets_by_index)}
        html = (_HTML
            .replace("{ABS_INDEXES_JSON}", json.dumps(abs_indexes))
            .replace("{NOTE_TIMES_MAP_JSON}", json.dumps(note_times_map))
        )
        self._html_path.write_text(html, encoding="utf-8")

        self._html_ready=False
        self._current_page = page
        self.lbl.setText(f"Score — page {page+1}/{self._page_count}")

        try:
            self.web.loadFinished.disconnect()
        except Exception:
            pass

        def on_loaded(ok: bool):
            self._html_ready=True
            self.web.page().runJavaScript(
                f"setPageAndSvg({page}, {json.dumps(self._svg_path.as_uri())});"
            )
            if self._pending_sec is not None:
                sec = self._pending_sec; self._pending_sec=None
                self._apply_time(sec)

        self.web.load(QUrl.fromLocalFile(str(self._html_path)))
        self.web.loadFinished.connect(on_loaded)

    @pyqtSlot(float)
    def set_music_time(self, sec: float):
        if not self._html_ready:
            self._pending_sec = sec
            return
        self._apply_time(sec)

    def _measure_for_time(self, sec: float) -> int:
        lo, hi = 0, len(self.measures)-1
        while lo<=hi:
            mid = (lo+hi)//2
            m = self.measures[mid]
            if sec < m.start_sec: hi=mid-1
            elif sec >= m.end_sec: lo=mid+1
            else: return mid
        return max(0, min(len(self.measures)-1, lo))

    def _apply_time(self, sec: float):
        if not self.measures: return
        m_idx = self._measure_for_time(sec)
        m = self.measures[m_idx]
        page = self._page_for_index(m_idx)
        if page != self._current_page:
            self._pending_sec = sec
            self._load_page(page)
            return
        dur = max(1e-6, m.end_sec - m.start_sec)
        t_in = max(0.0, sec - m.start_sec)
        self.web.page().runJavaScript(f"jsSetCursorAbs({int(m_idx)}, {float(t_in)}, {float(dur)})")
        if self._last_logged != (page, m_idx):
            dlog(f"page={page} meas_abs={m_idx} num={m.number} t_in={t_in:.3f}/{dur:.3f}")
            self._last_logged = (page, m_idx)
        self.lbl.setText(f"t={sec:7.3f}s  page {page+1}/{self._page_count}  meas {m_idx} (no.{m.number})  t={t_in:0.3f}/{dur:0.3f}s")
