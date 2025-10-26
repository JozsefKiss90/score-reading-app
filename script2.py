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
  html, body { margin:0; padding:0; height:100%; background:#fff; color:#111; font:14px/1.4 system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
  #top   { position:sticky; top:0; z-index:9999; background:#fff; border-bottom:1px solid #e5e7eb; padding:8px 10px; }
  #frame { position:relative; height:calc(100vh - 40px); overflow:auto; background:#fff; }
  #svgHost { position:relative; background:#fff; }
  svg { display:block; width:100%; height:auto; background:#fff !important; }
  .beat-box {
    position:absolute;
    top:0;
    background: rgba(0, 102, 255, 0.06);
    border-left: 1px solid rgba(0, 102, 255, 0.30);
    border-right: 1px solid rgba(0, 102, 255, 0.30);
    pointer-events: auto;
    cursor: pointer;
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
  const selected = new Set(); // "m-b" keys (1-based)

  // --- utilities ---
  const debounce = (fn, ms)=>{ let t=null; return (...a)=>{ clearTimeout(t); t=setTimeout(()=>fn(...a), ms); }; };

  function denoiseXs(xs){
    xs.sort((a,b)=>a-b);
    const out=[];
    for (const x of xs){
      if (out.length===0 || Math.abs(out[out.length-1]-x) > 2) out.push(x);
    }
    return out;
  }

  // Read beats per measure (numerator), fallback to lastSeen or 4
  function beatsInMeasure(g, lastSeen){
    const tsg = g.querySelector('g[data-vrv-type="timeSig"], g.timeSig, .timeSig');
    if (tsg){
      const t = (tsg.textContent||'').replace(/\s+/g,'');
      if (/^[0-9]{2,}$/.test(t)){
        const num = parseInt(t.slice(0, Math.floor(t.length/2)), 10);
        if (Number.isFinite(num) && num>0) return num;
      }
      if (/^C$/.test(t) || /C(?!.*¢)/.test(t)) return 4;
      if (/[¢]/.test(t)) return 2;
    }
    return (lastSeen && lastSeen>0) ? lastSeen : 4;
  }

  // Find all per-staff measure groups in visual order
  function findMeasureGroups(){
    const list=[];
    for (const svg of host.querySelectorAll('svg')){
      let ms = svg.querySelectorAll('g[data-vrv-type="measure"]');
      if (!ms || ms.length===0) ms = svg.querySelectorAll('g.measure, g[class*="measure"]');
      for (const g of ms) list.push({svg, g});
    }
    return list;
  }

  // Cluster groups that represent the SAME visual measure (e.g., treble + bass)
  // Criterion: similar left/right (within ~6 px) on the same page; union top/bottom.
  function clusterMeasures(hostRect){
    const raw = findMeasureGroups();
    const clusters = [];
    const TOL = 6; // px

    for (const {svg, g} of raw){
      const r = g.getBoundingClientRect();
      const L = r.left - hostRect.left;
      const R = r.right - hostRect.left;
      const T = r.top - hostRect.top;
      const B = r.bottom - hostRect.top;

      let found = null;
      for (const c of clusters){
        if (c.svg === svg && Math.abs(c.left - L) < TOL && Math.abs(c.right - R) < TOL){
          found = c; break;
        }
      }
      if (!found){
        found = { svg, left:L, right:R, top:T, bottom:B, groups:[g] };
        clusters.push(found);
      }else{
        found.top    = Math.min(found.top, T);
        found.bottom = Math.max(found.bottom, B);
        found.groups.push(g);
      }
    }

    // Sort clusters left-to-right, top-to-bottom for deterministic m index
    clusters.sort((a,b)=>{
      if (Math.abs(a.top - b.top) > 20) return a.top - b.top;
      return a.left - b.left;
    });

    return clusters;
  }

  // Compute boxes for a clustered visual measure (single union rect), EXACTLY "beats" boxes (no subdivisions)
  // NEW: per-beat segment median snap -> avoids duplicate/near-equal centers that created slivers.
  function computeBoxesForCluster(cluster, beats){
    const hostLeft = host.getBoundingClientRect().left;

    const m = {
      left: cluster.left,
      right: cluster.right,
      top: cluster.top,
      bottom: cluster.bottom
    };
    const height = Math.max(0, m.bottom - m.top);
    const width  = Math.max(1, m.right - m.left);

    // Collect notehead anchors from ALL groups in the cluster
    const xs=[];
    for (const g of cluster.groups){
      const noteNodes = g.querySelectorAll('[data-vrv-type="note"], g.note, .note, use[href*="note"]');
      for (const el of noteNodes){
        const r = el.getBoundingClientRect();
        if (r && Number.isFinite(r.left) && Number.isFinite(r.right)){
          xs.push((r.left + r.right) * 0.5 - hostLeft);
        }
      }
    }
    const anchors = denoiseXs(xs);

    // Segment length and tolerance for including anchors near edges
    const segW = width / beats;
    const tol  = Math.min(6, segW * 0.25); // small, but enough to catch close anchors

    // For each beat segment, pick ONE center:
    // - If anchors in [segL - tol, segR + tol], use median of those anchors
    // - else use the segment geometric center
    const centers = [];
    for (let i=0;i<beats;i++){
      const segL = m.left + i * segW;
      const segR = m.left + (i+1) * segW;
      const inside = anchors.filter(x => x >= (segL - tol) && x <= (segR + tol));
      if (inside.length){
        inside.sort((a,b)=>a-b);
        const median = inside[Math.floor(inside.length/2)];
        centers.push(Math.max(m.left, Math.min(m.right, median)));
      }else{
        centers.push(segL + 0.5 * segW);
      }
    }

    // Enforce strict monotonic increase to guarantee non-zero widths
    const MIN_STEP = Math.max(4, segW * 0.08);
    for (let i=1;i<centers.length;i++){
      if (centers[i] <= centers[i-1] + MIN_STEP){
        centers[i] = centers[i-1] + MIN_STEP;
      }
    }
    // If we crossed the right edge, compress uniformly
    const over = centers[centers.length-1] - (m.right - MIN_STEP);
    if (over > 0){
      const span = centers[centers.length-1] - centers[0];
      for (let i=0;i<centers.length;i++){
        const t = span>0 ? (centers[i] - centers[0]) / span : 0;
        centers[i] -= over * t;
      }
    }

    // Boundaries from midpoints
    const boxes=[];
    for (let i=0;i<centers.length;i++){
      const L = (i===0 ? m.left : (centers[i-1] + centers[i]) * 0.5);
      const R = (i===centers.length-1 ? m.right : (centers[i] + centers[i+1]) * 0.5);
      boxes.push({left:L, right:R, top:m.top, height});
    }
    return boxes;
  }

  function buildOverlays(){
    const hostRect = host.getBoundingClientRect();
    const clusters = clusterMeasures(hostRect);

    // Clear old
    host.querySelectorAll('.beat-box').forEach(n=>n.remove());

    let lastBeats = 4;
    let absIndex  = 0; // 1-based across visual measures

    for (const cluster of clusters){
      // determine beats from any group carrying a time signature; else last seen
      let beats = lastBeats;
      for (const g of cluster.groups){
        const b = beatsInMeasure(g, beats);
        if (b !== beats) { beats = b; break; }
      }
      lastBeats = beats;

      absIndex += 1;
      const boxes = computeBoxesForCluster(cluster, beats);

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

        html = HTML_TEMPLATE.replace("{SVG_HERE}", svg_markup)
        self.web.setHtml(html, QUrl("about:blank"))
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
    svgs = [tk.renderToSVG(p) for p in range(1, pages+1)]
    return "\n".join(svgs)


def main():
    ap = argparse.ArgumentParser(description="Beat selection lab: one column per beat, clustered per visual measure.")
    ap.add_argument("--score", required=True, help="Path to MusicXML or MXL (XML with default-x also fine).")
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
