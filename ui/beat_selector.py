
# ui/beat_selector.py — static window for clickable beat selection (no time-driven cursor)
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton
from PyQt6.QtWebEngineWidgets import QWebEngineView
import verovio
import xml.etree.ElementTree as ET

# Reuse ONLY generic loaders, not ui.score_view
from model.score_loader import (
    build_tempo_segments,
    build_measure_times,
    ql_to_seconds,
    load_notes_from_mxl,
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
.note-hl path, .note-hl ellipse, .note-hl circle { fill:#2563eb !important; stroke:#1e40af !important; }
  object, svg { display:block; width:100%; height:100%; background:#fff !important; }
  /* Static clickable beat boxes */
  .beat-box {
    position:absolute; top:0;
    background: rgba(2, 132, 199, 0.10);
    border-left: 1px solid rgba(2, 132, 199, 0.35);
    border-right: 1px solid rgba(2, 132, 199, 0.35);
    pointer-events:auto; cursor:pointer; z-index:20;
  }
  .beat-box.sel { background: rgba(2, 132, 199, 0.24); outline:1px solid rgba(2,132,199,0.90); outline-offset:-1px; }
  /* Hover hint */
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
  // Bootstrap: attach load listener and set initial SVG URL
  (function(){
    const obj = document.getElementById('page');
    const initial = "{SVG_URL}";
    obj.addEventListener('load', function onLoad(){
      obj.removeEventListener('load', onLoad);
      buildBeatBoxes();
    }, {once:true});
    // force-refresh to ensure 'load' fires
    obj.data = (initial.indexOf('?')===-1 ? initial+'?ts='+Date.now() : initial);
  })();
  // Incoming per-page arrays
  const ABS_INDEXES    = {ABS_INDEXES_JSON};
  const NOTE_TIMES_MAP = {NOTE_TIMES_MAP_JSON};

  // Global selection store across pages (measureAbs-beat)
  const SELECTED = new Set();

  function svgDoc(){ const o=document.getElementById('page'); try{ return o.contentDocument; }catch(e){ return null; } }
  function svgRoot(){ const d=svgDoc(); return d? d.querySelector('svg') : null }

  function _rectRel(node, rootRect){
    const r=node.getBoundingClientRect();
    return {left:r.left-rootRect.left, right:r.right-rootRect.left, top:r.top-rootRect.top, bottom:r.bottom-rootRect.top};
  }

  // basic beats-per-measure guess using timesig if visible; default 4
  function beatsInMeasure(g, lastSeen){
    const tsg = g.querySelector('g[data-vrv-type="timeSig"], g.timeSig, .timeSig');
    if (tsg){
      const t = (tsg.textContent||'').replace(/\s+/g,'');
      if (/^\d+\/\d+$/.test(t)) return Math.max(1, Math.min(parseInt(t.split('/')[0],10)||4, 12));
      if (/^[0-9]{2,}$/.test(t)){ const num=parseInt(t.slice(0,Math.floor(t.length/2)),10); if(num>0) return Math.min(num,12); }
      if (/^C$/.test(t)) return 4;
      if (/[¢]/.test(t)) return 2;
    }
    return lastSeen || 4;
  }


  // --- Helpers to collect and highlight notes inside a beat box ---
    // --- Pitch helpers ---
  function midiToPitch(m){
    const names = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
    const n = Math.round(Number(m)||0);
    const name = names[(n%12+12)%12];
    const oct = Math.floor(n/12) - 1;  // C4 = 60
    return name + oct;
  }
  function pnameAccidOctToPitch(pname, accid, oct){
    if (!pname) return null;
    const base = String(pname).toUpperCase();
    const acc = (accid||'').replace('s','♯').replace('f','♭').replace('#','♯');
    return base + acc + (oct!==undefined && oct!==null ? String(oct) : '');
  }
  function getNoteLabel(node){
    // try attributes on the note group first
    const pn = node.getAttribute('data-pname') || node.getAttribute('pname');
    const ac = node.getAttribute('data-accid') || node.getAttribute('accid');
    const oc = node.getAttribute('data-oct') || node.getAttribute('oct');
    if (pn) return pnameAccidOctToPitch(pn, ac, oc);

    const midi = node.getAttribute('data-midi') || node.getAttribute('midi');
    if (midi) return midiToPitch(midi);

    // try child elements (some builds put attrs on a child)
    const head = node.querySelector('[data-midi],[midi],[data-pname],[pname]');
    if (head){
      const pn2 = head.getAttribute('data-pname') || head.getAttribute('pname');
      const ac2 = head.getAttribute('data-accid') || head.getAttribute('accid');
      const oc2 = head.getAttribute('data-oct') || head.getAttribute('oct');
      const md2 = head.getAttribute('data-midi') || head.getAttribute('midi');
      if (pn2) return pnameAccidOctToPitch(pn2, ac2, oc2);
      if (md2) return midiToPitch(md2);
    }
    return null; // fallback to "Note 1/2/…"
  }

  // --- Robust highlight via inline styles on drawable descendants ---
  function eachDrawable(node, fn){
    const tags = ['path','ellipse','circle','rect','polygon','polyline','use'];
    if (node.tagName && tags.includes(node.tagName.toLowerCase())) fn(node);
    node.querySelectorAll(tags.join(',')).forEach(fn);
  }
  function applyDirectHighlight(node, on=true){
    eachDrawable(node, (el)=>{
      if (on){
        if (!el.hasAttribute('data-prev-fill'))   el.setAttribute('data-prev-fill',   el.style.fill   || '');
        if (!el.hasAttribute('data-prev-stroke')) el.setAttribute('data-prev-stroke', el.style.stroke || '');
        el.style.fill   = '#2563eb';
        el.style.stroke = '#1e40af';
      }else{
        const prevF = el.getAttribute('data-prev-fill');
        const prevS = el.getAttribute('data-prev-stroke');
        el.style.fill   = prevF || '';
        el.style.stroke = prevS || '';
      }
    });
  }

  function measureGroupByAbs(absIdx){
    const svg = svgRoot(); if(!svg) return null;
    let groups=[...svg.querySelectorAll('[data-vrv-type="measure"]')];
    if(groups.length===0) groups=[...svg.querySelectorAll('g.measure,[class*="measure"]')];
    const i = ABS_INDEXES.indexOf(absIdx);
    if (i<0 || i>=groups.length) return null;
    return groups[i];
  }

  function beatBoxBounds(absIdx, beatNumber){
    const svg = svgRoot(); if(!svg) return null;
    const frame = document.getElementById('frame');
    const R = svg.getBoundingClientRect();
    let groups=[...svg.querySelectorAll('[data-vrv-type="measure"]')];
    if(groups.length===0) groups=[...svg.querySelectorAll('g.measure,[class*="measure"]')];
    const i = ABS_INDEXES.indexOf(absIdx);
    if (i<0 || i>=groups.length) return null;
    const g = groups[i];
    const rr = _rectRel(g, R);
    const beats = beatsInMeasure(g, 4);
    const b = Math.max(1, Math.min(beats, beatNumber)) - 1;
    const width=Math.max(1, rr.right - rr.left);
    const L = rr.left + (b/beats)*width;
    const Rr= rr.left + ((b+1)/beats)*width;
    return {left:L, right:Rr, top:rr.top, bottom:rr.bottom};
  }

  function noteGroupsWithin(g, leftPx, rightPx){
    // Verovio note groups are fairly consistently marked; try robust selectors
    const svg = svgRoot(); const R = svg.getBoundingClientRect();
    const candidates = g.querySelectorAll('[data-vrv-type="note"], g.note, g.chord g.note');
    const arr=[];
    candidates.forEach(n=>{
      const r = n.getBoundingClientRect();
      const cx = (r.left + r.right)/2;
      if (cx>=leftPx && cx<=rightPx) arr.push(n);
    });
    // sort by x
    arr.sort((a,b)=>a.getBoundingClientRect().left - b.getBoundingClientRect().left);
    return arr;
  }

  function clearAllNoteHighlights(){
    const svg = svgRoot(); if(!svg) return;
    svg.querySelectorAll('.note-hl').forEach(n=>{
      n.classList.remove('note-hl');
      applyDirectHighlight(n, false);
    });
  }

  function highlightOneNote(el, on=true){
    if (!el) return;
    if (on){
      el.classList.add('note-hl');
      applyDirectHighlight(el, true);
    }else{
      el.classList.remove('note-hl');
      applyDirectHighlight(el, false);
    }
  }

  function buildSidebar(){
    const list = document.getElementById('list');
    list.innerHTML = '';
    const ordered = Array.from(SELECTED).sort((a,b)=>{
      const [am,ab]=a.split('-').map(Number); const [bm,bb]=b.split('-').map(Number);
      return am===bm ? (ab-bb) : (am-bm);
    });
    ordered.forEach(key=>{
      const [absIdx, beatNo] = key.split('-').map(Number);
      const g = measureGroupByAbs(absIdx); if(!g) return;
      const bb = beatBoxBounds(absIdx, beatNo); if(!bb) return;
      const notes = noteGroupsWithin(g, bb.left, bb.right);
      const wrap = document.createElement('div'); wrap.className='beat';
      const title = document.createElement('div'); title.textContent = `m${absIdx} • beat ${beatNo} — ${notes.length} notes`; wrap.appendChild(title);
      notes.forEach((node, i)=>{
        const item = document.createElement('div'); item.className='note';
        const lab = getNoteLabel(node);
        item.textContent = lab ? lab : `Note ${i+1}`;
        item.addEventListener('click', (ev)=>{
          ev.preventDefault(); ev.stopPropagation();
          // toggle highlight only for this note
          const on = !node.classList.contains('note-hl');
          // if ctrl not held, clear other highlights first
          if (!ev.ctrlKey) clearAllNoteHighlights();
          highlightOneNote(node, on);
        });
        wrap.appendChild(item);
      });
      list.appendChild(wrap);
    });
  }

  function publishSelection(){
    const arr = Array.from(SELECTED);
    arr.sort((a,b)=>{
      const [am,ab]=a.split('-').map(Number); const [bm,bb]=b.split('-').map(Number);
      return am===bm ? (ab-bb) : (am-bm);
    });
    document.title = 'BEATS:' + JSON.stringify(arr);
    buildSidebar();
  }

  function clearBeatBoxes(){
    const frame = document.getElementById('frame');
    frame.querySelectorAll('.beat-box').forEach(n=>n.remove());
  }

  function buildBeatBoxes(){
    const svg = svgRoot(); if(!svg) return;
    const frame = document.getElementById('frame');
    const R = svg.getBoundingClientRect();
    clearBeatBoxes();

    let groups=[...svg.querySelectorAll('[data-vrv-type="measure"]')];
    if(groups.length===0) groups=[...svg.querySelectorAll('g.measure,[class*="measure"]')];
    const n=Math.min(groups.length, ABS_INDEXES.length);
    let lastBeats=4;
    for (let i=0;i<n;i++){
      const absIdx = ABS_INDEXES[i], g=groups[i];
      const rr = _rectRel(g, R);
      const beats = (lastBeats = beatsInMeasure(g, lastBeats));
      const width=Math.max(1, rr.right - rr.left), height=Math.max(0, rr.bottom - rr.top);
      for (let b=0;b<beats;b++){
        const L = rr.left + (b/beats)*width;
        const Rr= rr.left + ((b+1)/beats)*width;

        const key = `${absIdx}-${b+1}`;
        const box = document.createElement('div');
        box.className = 'beat-box' + (SELECTED.has(key) ? ' sel' : '');
        box.style.left   = `${L}px`;
        box.style.top    = `${rr.top}px`;
        box.style.width  = `${Math.max(0,Rr-L)}px`;
        box.style.height = `${height}px`;
        box.dataset.label = `m${absIdx} • beat ${b+1}/${beats}`;

        box.addEventListener('click', ev=>{
          ev.preventDefault(); ev.stopPropagation();
          if (SELECTED.has(key)){ SELECTED.delete(key); box.classList.remove('sel'); }
          else { SELECTED.add(key); box.classList.add('sel'); }
          publishSelection();
        }, {passive:false});

        frame.appendChild(box);
      }
    }
    document.getElementById('hud').textContent = `measures on page: ${n}`;
    publishSelection();
    buildSidebar();
  }

  function setPageSvg(svgUrl){
    const obj = document.getElementById('page');
    obj.addEventListener('load', function onLoad(){
      obj.removeEventListener('load', onLoad);
      buildBeatBoxes();
    }, {once:true});
    obj.data = (svgUrl.indexOf('?')===-1 ? svgUrl+'?ts='+Date.now() : svgUrl);
  }

  // Rebuild on resize
  window.addEventListener('resize', ()=>{ if(svgRoot()) buildBeatBoxes(); });
</script>
</body></html>
"""

class BeatSelector(QWidget):
    """Standalone static viewer that lets the user click beats to select/deselect them."""

    selectionChanged = pyqtSignal(list)  # emits ['absIdx-beat', ...]

    def __init__(self, mxl_path: str, xml_path: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.mxl_path = str(mxl_path)
        self.xml_path = str(xml_path or mxl_path)

        self.setWindowTitle("Beat Selector — static")
        layout = QVBoxLayout(self); layout.setContentsMargins(0,0,0,0)

        # Top bar
        top = QHBoxLayout(); top.setContentsMargins(6,6,6,6)
        self.lbl = QLabel("Page 1")
        top.addWidget(self.lbl); top.addStretch(1)
        self.btn_prev = QPushButton("◀ Prev Page"); self.btn_next = QPushButton("Next Page ▶")
        self.btn_clear = QPushButton("Clear")
        top.addWidget(self.btn_prev); top.addWidget(self.btn_next); top.addWidget(self.btn_clear)
        layout.addLayout(top)

        # Web view
        self.web = QWebEngineView(self)
        self.web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        # Use title bridge to receive selection JSON from the page
        self.web.titleChanged.connect(self._on_title_changed)
        layout.addWidget(self.web, 1)

        # Verovio render (no time cursor, only svg pages)
        self._tk = verovio.toolkit()
        self._tk.setOptions({
            "pageHeight": 1800, "pageWidth": 1200, "scale": 40,
            "breaks": "auto", "adjustPageHeight": 1, "svgViewBox": 1
        })
        self._tk.loadFile(self.mxl_path)
        self._tk.redoLayout()
        self._page_count = int(self._tk.getPageCount() or 1)

        # Musical structure (for onsets per measure if desired later)
        self.tempo_segments = build_tempo_segments(self.mxl_path)
        mt = build_measure_times(self.mxl_path)
        self.measures: List[Measure] = [
            Measure(i, int(m["number"]), float(m["start_ql"]), float(m["end_ql"]), float(m["start_sec"]), float(m["end_sec"]))
            for i,m in enumerate(mt)
        ]

        # Onsets per measure (seconds relative) — used only if you later want note anchors; but wiring kept
        self.onsets_by_index: List[List[float]] = self._build_onsets()

        # Page mapping: map SVG measures to absolute indices like score_view
        self._page_svgs: List[str] = []
        self._page_abs_indexes: List[List[int]] = []
        self._discover_pages_by_numbers()

        # Temp host files
        tmp = Path(tempfile.gettempdir())
        self._html_path = tmp / "beat_host.html"
        self._svg_path = tmp / "beat_page.svg"
        self._current_page = -1

        # Wire buttons
        self.btn_prev.clicked.connect(lambda: self._load_page(self._current_page - 1))
        self.btn_next.clicked.connect(lambda: self._load_page(self._current_page + 1))
        self.btn_clear.clicked.connect(self._clear_selection)

        # Initial page
        self._load_page(0)

    # -------- communication from web page --------
    def _on_title_changed(self, title: str):
        if not title.startswith("BEATS:"):
            return
        try:
            items = json.loads(title[len("BEATS:"):])
            self.selectionChanged.emit(items)
            self.lbl.setText(f"Page {self._current_page+1}/{self._page_count} — selected: {len(items)} beats")
        except Exception:
            pass

    # -------- data prep --------
    def _build_onsets(self) -> List[List[float]]:
        notes, _ = load_notes_from_mxl(self.mxl_path, self.xml_path)
        arr = [[] for _ in self.measures]
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
        for i, L in enumerate(arr):
            L.sort()
            uniq=[]
            for t in L:
                if not uniq or abs(t-uniq[-1])>0.010: uniq.append(t)
            arr[i]=uniq
        return arr

    def _discover_pages_by_numbers(self):
        self._page_svgs.clear()
        self._page_abs_indexes.clear()

        num_to_abs: Dict[int,int] = {}
        for m in self.measures:
            if m.number not in num_to_abs:
                num_to_abs[m.number] = m.index

        for p in range(self._page_count):
            svg = self._tk.renderToSVG(p+1)
            self._page_svgs.append(svg)
            abs_list: List[int] = []
            try:
                root = ET.fromstring(svg)
                for g in root.iter():
                    tag = g.tag.split('}')[-1]
                    if tag != 'g': continue
                    typ = g.attrib.get('data-vrv-type') or g.attrib.get('data-type') or ''
                    if typ != 'measure' and 'measure' not in g.attrib.get('class',''): continue
                    n_attr = g.attrib.get('n') or g.attrib.get('data-n') or ''
                    num = None
                    try:
                        if n_attr: num = int(str(n_attr).strip().split()[0])
                    except: num = None
                    if num is not None and num in num_to_abs:
                        abs_idx = num_to_abs[num]
                    else:
                        abs_idx = (abs_list[-1]+1) if abs_list else sum(len(x) for x in self._page_abs_indexes)
                        abs_idx = min(abs_idx, len(self.measures)-1)
                    abs_list.append(abs_idx)
            except Exception as e:
                dlog("SVG parse error:", e)
                count = svg.count('data-vrv-type="measure"') or svg.count('class="measure"') or 1
                base = sum(len(x) for x in self._page_abs_indexes)
                abs_list = [min(base+i, len(self.measures)-1) for i in range(count)]
            self._page_abs_indexes.append(abs_list)

        if not self._page_abs_indexes:
            self._page_abs_indexes = [[i for i in range(len(self.measures))]]

    # -------- page IO --------
    def _load_page(self, page: int):
      page = max(0, min(self._page_count-1, page))
      self._svg_path.write_text(self._page_svgs[page], encoding='utf-8')

      abs_indexes = self._page_abs_indexes[page]
      note_times_map = {i: self.onsets_by_index[i] for i in abs_indexes if i < len(self.onsets_by_index)}

      svg_url = QUrl.fromLocalFile(str(self._svg_path)).toString()
      html = (_HTML
          .replace("{ABS_INDEXES_JSON}", json.dumps(abs_indexes))
          .replace("{NOTE_TIMES_MAP_JSON}", json.dumps(note_times_map))
          .replace("{SVG_URL}", svg_url)
      )
      self._html_path.write_text(html, encoding='utf-8')

      self._current_page = page
      self.lbl.setText(f"Page {page+1}/{self._page_count} — selected: 0 beats")

      # load into webview
      self.web.load(QUrl.fromLocalFile(str(self._html_path)))
      # on load the JS will call buildBeatBoxes()

# -------- actions --------
    def _clear_selection(self):
        # Ask the page to clear its SELECTED Set by reloading the page (cheapest, keeps UI simple)
        self._load_page(self._current_page)
