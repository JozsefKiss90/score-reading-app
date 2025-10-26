import json
from verovio import toolkit

from PyQt6.QtCore import pyqtSlot
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtWebEngineWidgets import QWebEngineView


HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>SEL:[]</title>
  <style>
    html,body{margin:0;padding:0;height:100%;overflow:hidden;background:#fff;color:#111;font-family:system-ui;}
    #top{height:36px;display:flex;align-items:center;gap:12px;padding:0 12px;border-bottom:1px solid #ddd;background:#f7f7f7;}
    #frame{position:relative;height:calc(100% - 36px);overflow:auto;background:#fff;}
    .pill{padding:4px 10px;border-radius:999px;background:#fff;border:1px solid #ddd;box-shadow:0 1px 1px rgba(0,0,0,0.05);}
    svg{display:block;margin:12px auto;max-width:98%;height:auto;}
    /* Coloring */
    .note-hit { fill:#2ecc71 !important; stroke:#2ecc71 !important; }
    .note-miss{ fill:#f1c40f !important; stroke:#f39c12 !important; }
    .note-dim { opacity:0.35; }
    /* Beat overlays */
    .beat-box{ position:absolute; top:0; bottom:0; background:rgba(0,0,0,0.03);
               border-left:1px solid rgba(0,0,0,0.12); border-right:1px solid rgba(0,0,0,0.12); pointer-events:auto; }
    .beat-box.sel{ background:rgba(0,120,215,0.08); outline:2px solid rgba(0,120,215,0.35); }
  </style>
</head>
<body>
  <div id="top">
    <div class="pill" id="status">Click a shaded beat column to toggle it. Expected notes turn amber; hits are green.</div>
    <div class="pill" id="hud">exp:0 held:0 hits:0 miss:0</div>
  </div>

  <div id="frame"><div id="svgHost">__SVG__</div></div>

  <script>
    window.BEAT_COUNT = __BEATCOUNTS__;

    let MEASURE_NODES=[], BEAT_RECTS={}, READY=false, SEL_BEATS=new Set();

    function announce(){
      document.getElementById('status').textContent =
        (SEL_BEATS.size ? ('Beats: ' + Array.from(SEL_BEATS).join(' ')) : 'Click a shaded beat column to toggle it.');
    }
    function mid(a,b){ return (a+b)/2; }
    function nearest(xs, x){
      if(!xs || !xs.length) return x;
      let best=xs[0], d=Math.abs(xs[0]-x);
      for(const v of xs){ const dd=Math.abs(v-x); if(dd<d){d=dd; best=v;} }
      return best;
    }

    function buildBeatBoxes(){
      const frame=document.getElementById('frame');
      const host=document.getElementById('svgHost');
      const measures = host.querySelectorAll('[data-vrv-type="measure"], g.measure, [data-type="measure"]');
      const f = frame.getBoundingClientRect();

      MEASURE_NODES = [];
      BEAT_RECTS = {};
      let idx=0;

      measures.forEach(m=>{
        const r = m.getBoundingClientRect();
        const rect = {l:r.left - f.left + frame.scrollLeft, r:r.right - f.left + frame.scrollLeft,
                      t:r.top  - f.top  + frame.scrollTop,  b:r.bottom - f.top  + frame.scrollTop};
        MEASURE_NODES.push(m);

        // notehead X anchors
        const cand = m.querySelectorAll('[data-vrv-type="note"], g.note, .note, use[href*="note"]');
        const xs=[];
        cand.forEach(el=>{
          const rr=el.getBoundingClientRect();
          if(rr && isFinite(rr.left) && isFinite(rr.right)){
            xs.push((rr.left+rr.right)/2 - f.left + frame.scrollLeft);
          }
        });
        xs.sort((a,b)=>a-b);
        const anchors=[]; for(const x of xs){ if(!anchors.length || Math.abs(x-anchors[anchors.length-1])>2) anchors.push(x); }

        const beats = Math.max(1, (window.BEAT_COUNT[String(idx)] ?? 4));
        const W = rect.r - rect.l, H = rect.b - rect.t;

        const centers=[];
        for(let b=0;b<beats;b++){
          const c = rect.l + (b+0.5)*(W/beats);
          centers.push(nearest(anchors, c));
        }

        const bounds=[];
        for(let i=0;i<=beats;i++){
          if(i===0) bounds.push( Math.max(rect.l, centers.length? mid(rect.l, centers[0]) : rect.l) );
          else if(i===beats) bounds.push( Math.min(rect.r, centers.length? mid(centers[beats-1], rect.r) : rect.r) );
          else bounds.push( mid(centers[i-1], centers[i]) );
        }

        BEAT_RECTS[idx] = [];
        for(let b=0;b<beats;b++){
          const l=bounds[b], r=bounds[b+1];
          const el=document.createElement('div');
          el.className='beat-box';
          el.style.left=l+'px'; el.style.top=rect.t+'px';
          el.style.width=(r-l)+'px'; el.style.height=H+'px';
          el.dataset.measure=idx; el.dataset.beat=(b+1);
          el.addEventListener('click',(ev)=>{
            ev.stopPropagation();
            const key = `${idx}-${b+1}`;
            if(SEL_BEATS.has(key)){ SEL_BEATS.delete(key); el.classList.remove('sel'); }
            else { SEL_BEATS.add(key); el.classList.add('sel'); }
            announce();
            document.title = 'BEATS:' + JSON.stringify(Array.from(SEL_BEATS));
          });
          frame.appendChild(el);
          BEAT_RECTS[idx].push({l,r,t:rect.t,b:rect.b,idx:(b+1),el});
        }

        idx++;
      });

      READY=true;
    }

    function pnameToSemitone(p){ const map={c:0,d:2,e:4,f:5,g:7,a:9,b:11}; return map[p] ?? 0; }
    function accidToDelta(a){
      if(!a) return 0;
      if(a.includes('dblsharp')) return 2;
      if(a.includes('sharp')) return 1;
      if(a.includes('dblflat')) return -2;
      if(a.includes('flat')) return -1;
      return 0;
    }
    function noteInSelectedBeats(n){
      const frame=document.getElementById('frame');
      const f=frame.getBoundingClientRect();
      const rr=n.getBoundingClientRect();
      const cx=(rr.left+rr.right)/2 - f.left + frame.scrollLeft;
      let m = n.closest('[data-vrv-type="measure"], g.measure, [data-type="measure"]');
      if(!m) return false;
      const mIdx = Array.prototype.indexOf.call(MEASURE_NODES, m);
      const rects = BEAT_RECTS[mIdx]||[];
      for(const r of rects){
        const key = `${mIdx}-${r.idx}`;
        if(cx>=r.l && cx<=r.r && SEL_BEATS.has(key)) return true;
      }
      return false;
    }

    function updateHighlights(expected, held){
      const host=document.getElementById('svgHost');
      host.querySelectorAll('.note-hit, .note-miss, .note-dim').forEach(n=>n.classList.remove('note-hit','note-miss','note-dim'));

      const notes = host.querySelectorAll('[data-vrv-type="note"], .note');
      notes.forEach(n=>{
        const dm = n.getAttribute('data-midi');
        let midi;
        if (dm && !isNaN(parseInt(dm,10))) midi = parseInt(dm,10);
        else {
          const pn=(n.getAttribute('data-pname')||n.getAttribute('data-pitchName')||'').toLowerCase();
          const oc=parseInt(n.getAttribute('data-oct')||n.getAttribute('data-octave')||'0',10);
          const ac=(n.getAttribute('data-accid')||n.getAttribute('data-accidental')||'').toLowerCase();
          if(!pn || isNaN(oc)){ n.classList.add('note-dim'); return; }
          midi = 12*(oc+1)+pnameToSemitone(pn)+accidToDelta(ac);
        }

        const inBeats = noteInSelectedBeats(n);
        if (!SEL_BEATS.size || !inBeats) { n.classList.add('note-dim'); return; }

        if (held.indexOf(midi)!==-1 && expected.indexOf(midi)!==-1) n.classList.add('note-hit');
        else if (expected.indexOf(midi)!==-1) n.classList.add('note-miss');
        else n.classList.add('note-dim');
      });

      const hud=document.getElementById('hud');
      hud.textContent = `exp:${expected.length} held:${held.length} hits:${expected.filter(x=>held.indexOf(x)!==-1).length} miss:${expected.filter(x=>held.indexOf(x)===-1).length}`;
    }

    // Kick overlays after SVG is in DOM
    window.addEventListener('load', ()=> setTimeout(buildBeatBoxes, 0));
  </script>
</body>
</html>
"""


class SelectionWindow(QWidget):
    """
    Minimal selection window:
      - Renders the given MusicXML/MXL to inline SVG with Verovio
      - Builds beat overlays aligned to engraved noteheads
      - titleChanged('BEATS:[...]') -> computes expected set and colors notes
      - note_on/note_off update colors immediately
    """
    def __init__(self, evaluator, beat_index, score_path: str):
        super().__init__()
        self.evaluator = evaluator
        self.beat_index = beat_index
        self.score_path = score_path
        self._last_evt = "—"

        self.setWindowTitle("Selection Lab")
        self.resize(1200, 800)

        root = QHBoxLayout(self)
        self.web = QWebEngineView()
        root.addWidget(self.web, stretch=5)

        # Right: skinny HUD only
        side = QVBoxLayout()
        self.lblSel = QLabel("Beats: —")
        self.lblExpected = QLabel("Expected: —")
        self.lblStatus = QLabel("Held: — | Hits: — | Misses: —")
        for w in (self.lblSel, self.lblExpected, self.lblStatus):
            w.setStyleSheet("font: 12px 'Segoe UI';")
        btnClear = QPushButton("Clear selection")
        btnClear.clicked.connect(self._clear_selection)

        side.addWidget(self.lblSel)
        side.addWidget(self.lblExpected)
        side.addWidget(self.lblStatus)
        side.addWidget(btnClear)
        root.addLayout(side, stretch=2)

        self.web.titleChanged.connect(self._on_title_changed)

        # Render SVG now and inject HTML
        self._load_svg_into_page()

    # --- Verovio render ---
    def _load_svg_into_page(self):
      tk = toolkit()
      opts = {
          "pageHeight": 2600,
          "pageWidth": 2000,
          "scale": 45,
          "adjustPageHeight": 1,
      }
      tk.setOptions(opts)
      tk.loadFile(self.score_path)

      pages = tk.getPageCount()

      svg_parts = []
      if pages and pages > 1:
          # Per-page rendering (most common)
          for p in range(1, pages + 1):
              # Correct signature: no dict as 2nd param
              svg_parts.append(tk.renderToSVG(p))
      else:
          # Single-page fallback (works across versions)
          svg_parts.append(tk.renderToSVG())

      svg_markup = "\n".join(svg_parts)

      beats_map = self.beat_index.beats_in_measure
      html = HTML_TEMPLATE.replace("__BEATCOUNTS__", json.dumps(beats_map))
      html = html.replace("__SVG__", svg_markup)
      self.web.setHtml(html)

    # --- Selection from webview ---
    @pyqtSlot(str)
    def _on_title_changed(self, title: str):
        try:
            if title.startswith("BEATS:"):
                items = json.loads(title[6:])  # ["3-1","3-2", ...]
                beats = []
                for tok in items:
                    m, b = tok.split('-')
                    beats.append((int(m), int(b)))
                # update expected via per_beat
                self.evaluator.select_beats(beats, self.beat_index.per_beat)
                self.lblSel.setText("Beats: " + (" ".join(items) if items else "—"))
                exp = sorted(self.evaluator.expected)
                self.lblExpected.setText("Expected: " + (", ".join(map(str, exp)) if exp else "—"))
                self._push_highlights()
        except Exception:
            pass

    # --- MIDI API from runner ---
    def note_on(self, midi: int):
        self._last_evt = f"on {midi}"
        self.evaluator.note_on(midi)
        self._push_highlights()

    def note_off(self, midi: int):
        self._last_evt = f"off {midi}"
        self.evaluator.note_off(midi)
        self._push_highlights()

    # --- Helpers ---
    def _push_highlights(self):
        hits, misses = self.evaluator.status()
        held = sorted(self.evaluator.down_now)
        self.lblStatus.setText(f"Held: {held} | Hits: {sorted(hits)} | Misses: {sorted(misses)} | last: {self._last_evt}")
        try:
            exp = sorted(self.evaluator.expected)
            self.web.page().runJavaScript(f"updateHighlights({json.dumps(exp)}, {json.dumps(held)});")
        except Exception:
            pass

    def _clear_selection(self):
        self.evaluator.set_expected([])
        self.lblSel.setText("Beats: —")
        self.lblExpected.setText("Expected: —")
        self._push_highlights()
