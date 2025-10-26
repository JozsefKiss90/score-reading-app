# run_selection_lab.py
# Usage:  python run_selection_lab.py --score path/to/score.{xml|mxl}
# Requires: Python 3.10+, PyQt6 (with QtWebEngine), verovio (Python toolkit)

import argparse
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel
from PyQt6.QtWebEngineWidgets import QWebEngineView
import verovio


HTML_TEMPLATE = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BeatSelect</title>
<style>
  html, body { margin:0; padding:0; height:100%; background:#fff; color:#111;
               font:14px/1.4 system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
  #top   { position:sticky; top:0; z-index:9999; background:#fff; border-bottom:1px solid #e5e7eb; padding:8px 10px; }
  #frame { position:relative; height:calc(100vh - 40px); overflow:auto; background:#fff; }
  #svgHost { position:relative; background:#fff; }
  svg { display:block; width:100%; height:auto; background:#fff !important; }

  /* Overlay columns */
  .beat-box {
    position:absolute;
    top:0;
    background: rgba(0, 102, 255, 0.08);
    border-left: 1px solid rgba(0, 102, 255, 0.30);
    border-right: 1px solid rgba(0, 102, 255, 0.30);
    pointer-events:auto;
    cursor:pointer;
  }
  .beat-box.sel {
    background: rgba(0, 102, 255, 0.22);
    outline: 1px solid rgba(0, 102, 255, 0.75);
    outline-offset: -1px;
  }

  * { box-sizing:border-box; }
</style>
</head>
<body>
  <div id="top">Selected beats: <span id="selStr">(none)</span></div>
  <div id="frame">
    <div id="svgHost">{SVG_HERE}</div>
  </div>

<script>
(function(){
  const host    = document.getElementById('svgHost');
  const frameEl = document.getElementById('frame');
  const selStr  = document.getElementById('selStr');

  // Persistent selection set — keys are "m-b" (1-based absolute measure index, beat index)
  const selected = new Set();

  // --- utilities ---
  const debounce = (fn, ms)=>{ let t=null; return (...a)=>{ clearTimeout(t); t=setTimeout(()=>fn(...a), ms); }; };

  // Read beats-per-measure from any time signature inside that measure; fallback to last seen (or 4)
  function beatsInMeasure(g, lastSeen){
    // Common Verovio structure: g[data-vrv-type="timeSig"]
    const tsg = g.querySelector('g[data-vrv-type="timeSig"], g.timeSig, .timeSig');
    if (tsg){
      const t = (tsg.textContent||'').replace(/\s+/g,'');
      if (/^[0-9]{2,}$/.test(t)){
        // stacked numerator/denominator; assume first half is numerator
        const num = parseInt(t.slice(0, Math.floor(t.length/2)), 10);
        if (Number.isFinite(num) && num>0) return num;
      }
      if (/^C$/.test(t) || /C(?!.*¢)/.test(t)) return 4; // common time
      if (/[¢]/.test(t)) return 2;                        // cut time
    }
    return (lastSeen && lastSeen>0) ? lastSeen : 4;
  }

  // Find all per-staff measure groups across all page SVGs (keeps visual order)
  function findMeasureGroups(){
    const list=[];
    const svgs = Array.from(host.querySelectorAll('svg'));
    svgs.forEach((svg, svgIndex)=>{
      let ms = svg.querySelectorAll('g[data-vrv-type="measure"]');
      if (!ms || ms.length===0) ms = svg.querySelectorAll('g.measure, g[class*="measure"]');
      for (const g of ms) {
        const measNo = g.getAttribute('data-n') || g.getAttribute('n') || (g.dataset ? g.dataset.n : null);
        list.push({svg, svgIndex, g, measNo});
      }
    });
    return list;
  }

  // Cluster staves that belong to the SAME visual measure.
  // Primary key: (page, measure number). Fallback: similar left/right on the same page.
  function clusterMeasures(hostRect){
    const raw = findMeasureGroups();
    const clusters = [];
    const keyed = new Map();
    const fallback = [];
    const TOL = 6; // px tolerance for left/right matching

    for (const it of raw){
      if (it.measNo){
        const key = it.svgIndex + '#' + it.measNo;
        if (!keyed.has(key)) keyed.set(key, { svg: it.svg, svgIndex: it.svgIndex, groups: [] });
        keyed.get(key).groups.push(it.g);
      } else {
        fallback.push(it);
      }
    }

    // Build clusters from keyed groups (by measure number)
    for (const [_k, pack] of keyed){
      let L=+Infinity, R=-Infinity, T=+Infinity, B=-Infinity;
      for (const g of pack.groups){
        const r = g.getBoundingClientRect();
        L = Math.min(L, r.left  - hostRect.left);
        R = Math.max(R, r.right - hostRect.left);
        T = Math.min(T, r.top   - hostRect.top);
        B = Math.max(B, r.bottom- hostRect.top);
      }
      clusters.push({ svg: pack.svg, svgIndex: pack.svgIndex, left:L, right:R, top:T, bottom:B, groups: pack.groups });
    }

    // Fallback groups: merge by left/right proximity within the same page
    for (const it of fallback){
      const r = it.g.getBoundingClientRect();
      const L=r.left-hostRect.left, R=r.right-hostRect.left, T=r.top-hostRect.top, B=r.bottom-hostRect.top;
      let found=null;
      for (const c of clusters){
        if (c.svg===it.svg && Math.abs(c.left-L)<TOL && Math.abs(c.right-R)<TOL){ found=c; break; }
      }
      if (!found){
        clusters.push({ svg: it.svg, svgIndex: it.svgIndex, left:L, right:R, top:T, bottom:B, groups:[it.g] });
      }else{
        found.left   = Math.min(found.left, L);
        found.right  = Math.max(found.right, R);
        found.top    = Math.min(found.top, T);
        found.bottom = Math.max(found.bottom, B);
        found.groups.push(it.g);
      }
    }

    // Reading order: by page, then staff system Y, then X
    clusters.sort((a,b)=>{
      if (a.svgIndex !== b.svgIndex) return a.svgIndex - b.svgIndex;
      if (Math.abs(a.top - b.top) > 20) return a.top - b.top;
      return a.left - b.left;
    });

    return clusters;
  }

  // Compute EXACTLY "beats" equal-width boxes for a measure cluster — NO snapping to noteheads.
  function equalBeatBoxes(cluster, beats){
    const m = { left:cluster.left, right:cluster.right, top:cluster.top, bottom:cluster.bottom };
    const width  = Math.max(1, m.right - m.left);
    const height = Math.max(0, m.bottom - m.top);

    const boxes=[];
    for (let i=0;i<beats;i++){
      const L = m.left + (i/ beats)    * width;
      const R = m.left + ((i+1)/beats) * width;
      boxes.push({left:L, right:R, top:m.top, height});
    }
    return boxes;
  }

  function buildOverlays(){
    const hostRect = host.getBoundingClientRect();
    const clusters = clusterMeasures(hostRect);

    // Clear old overlays but keep selection set
    host.querySelectorAll('.beat-box').forEach(n=>n.remove());

    let lastBeats = 4;
    let absIndex  = 0;  // 1-based across visual measures

    for (const cluster of clusters){
      // Determine beats from any group that carries a time signature; fallback to last seen
      let beats = lastBeats;
      for (const g of cluster.groups){
        const b = beatsInMeasure(g, beats);
        if (b !== beats) { beats = b; break; }
      }
      lastBeats = beats;

      absIndex += 1;
      const boxes = equalBeatBoxes(cluster, beats);

      boxes.forEach((bx, i)=>{
        const div = document.createElement('div');
        div.className = 'beat-box';
        const w = Math.max(0, bx.right - bx.left);
        div.style.left   = bx.left + 'px';
        div.style.top    = bx.top  + 'px';
        div.style.width  = w + 'px';
        div.style.height = bx.height + 'px';

        const key = absIndex + '-' + (i+1);
        if (selected.has(key)) div.classList.add('sel');

        div.addEventListener('click', (ev)=>{
          ev.preventDefault(); ev.stopPropagation();
          if (selected.has(key)){ selected.delete(key); div.classList.remove('sel'); }
          else { selected.add(key); div.classList.add('sel'); }
          publishSelection();
        }, {passive:false});

        host.appendChild(div);
      });
    }

    publishSelection();
  }

  function publishSelection(){
    const keys = Array.from(selected).sort((a,b)=>{
      const [am,ab]=a.split('-').map(Number);
      const [bm,bb]=b.split('-').map(Number);
      return am===bm ? (ab-bb) : (am-bm);
    });
    selStr.textContent = keys.length ? keys.join(' ') : '(none)';
    // Mirror to document.title so the PyQt side can receive updates
    document.title = 'BEATS:' + JSON.stringify(keys);
  }

  const rebuildDebounced = debounce(buildOverlays, 80);

  window.addEventListener('load', buildOverlays);
  window.addEventListener('resize', rebuildDebounced);
  frameEl.addEventListener('scroll', rebuildDebounced, {passive:true});
  setTimeout(buildOverlays, 0);
})();
</script>
</body>
</html>
"""


class BeatSelectionWindow(QWidget):
    def __init__(self, svg_markup: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Beats — Minimal Prototype")

        self.header = QLabel("Selected beats: (none)")
        self.header.setStyleSheet(
            "padding:6px 10px; border-bottom:1px solid #e5e7eb; background:#fff; color:#111;"
        )

        self.web = QWebEngineView(self)
        self.web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addWidget(self.web, 1)

        # Inject HTML with inline SVG(s)
        html = HTML_TEMPLATE.replace("{SVG_HERE}", svg_markup)
        self.web.setHtml(html, QUrl("about:blank"))

        # Listen for selection payloads via document.title
        self.web.titleChanged.connect(self._on_title_changed)

    def _on_title_changed(self, title: str):
        if not title.startswith("BEATS:"):
            return
        try:
            import json
            keys = json.loads(title[len("BEATS:"):])
            self.header.setText(f"Selected beats: {' '.join(keys) if keys else '(none)'}")
        except Exception:
            pass


def render_score_to_inline_svg(score_path: str) -> str:
    """
    Render all pages to inline SVG using Verovio and return a single concatenated string.
    """
    tk = verovio.toolkit()
    opts = {
        "pageHeight": 1800,
        "pageWidth":  1200,
        "scale": 40,
        "breaks": "auto",
        "adjustPageHeight": 1,
        "svgViewBox": 1
    }
    tk.setOptions(opts)
    if not tk.loadFile(score_path):
        raise RuntimeError(f"Verovio failed to load: {score_path}")
    tk.redoLayout()
    pages = int(tk.getPageCount() or 1)
    return "\n".join(tk.renderToSVG(p) for p in range(1, pages+1))


def main():
    ap = argparse.ArgumentParser(
        description="Beat selection lab: one equal-width column per beat (no snapping)."
    )
    ap.add_argument("--score", required=True, help="Path to MusicXML or MXL")
    args = ap.parse_args()

    score_path = Path(args.score).expanduser().resolve()
    if not score_path.exists():
        print(f"Score not found: {score_path}")
        sys.exit(1)

    app = QApplication(sys.argv)
    try:
        svg_markup = render_score_to_inline_svg(str(score_path))
    except Exception as e:
        print("Failed to render score with Verovio:", e)
        sys.exit(1)

    win = BeatSelectionWindow(svg_markup)
    win.resize(1200, 800)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
