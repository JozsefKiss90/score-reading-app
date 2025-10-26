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
  <div id="frame"><!-- scroll container -->
    <div id="svgHost">{SVG_HERE}</div>
  </div>

<script>
(function(){
  const host    = document.getElementById('svgHost');
  const frameEl = document.getElementById('frame');
  const selStr  = document.getElementById('selStr');

  // Selection set -> "m-b" keys (1-based)
  const selected = new Set();

  // --- utilities ---
  const debounce = (fn, ms)=>{ let t=null; return (...a)=>{ clearTimeout(t); t=setTimeout(()=>fn(...a), ms); }; };

  // Denoise anchors by dropping Xs nearer than ~2 px (SVG device pixels)
  function denoiseXs(xs){
    xs.sort((a,b)=>a-b);
    const out=[];
    for (const x of xs){
      if (out.length===0 || Math.abs(out[out.length-1]-x) > 2) out.push(x);
    }
    return out;
  }

  // Robust time-signature read per measure -> numerator (beats per measure)
  function beatsInMeasure(measureGroup, lastSeen){
    // Try common Verovio nodes
    const tsg = measureGroup.querySelector('g[data-vrv-type="timeSig"], g.timeSig, .timeSig');
    if (tsg){
      const t = (tsg.textContent||'').replace(/\s+/g,'');
      // "34" or "44" stacked numer/denom, sometimes Unicode common/cut time
      if (/^[0-9]{2,}$/.test(t)){
        // assume first half are numerator digits
        const num = parseInt(t.slice(0, Math.floor(t.length/2)), 10);
        if (Number.isFinite(num) && num>0) return num;
      }
      if (/^C$/.test(t) || /C(?!.*¢)/.test(t)) return 4; // common time
      if (/[¢]/.test(t)) return 2; // cut time
    }
    return (lastSeen && lastSeen>0) ? lastSeen : 4;
  }

  // Find all measures in page order
  function findMeasures(){
    const out=[];
    for (const svg of host.querySelectorAll('svg')){
      let ms = svg.querySelectorAll('g[data-vrv-type="measure"]');
      if (!ms || ms.length===0) ms = svg.querySelectorAll('g.measure, g[class*="measure"]');
      for (const g of ms) out.push({svg, g});
    }
    return out;
  }

  // The heart: compute exactly "beats" boxes, no subdivisions
  function computeBoxesForMeasure(g, absIndex, beats, hostRect){
    const gRect = g.getBoundingClientRect();
    const m = {
      left:   gRect.left - hostRect.left,
      right:  gRect.right - hostRect.left,
      top:    gRect.top - hostRect.top,
      bottom: gRect.bottom - hostRect.top,
    };
    const height = Math.max(0, m.bottom - m.top);
    const width  = Math.max(1, m.right - m.left);

    // Collect engraved NOTEHEAD-ish anchors inside the measure
    // Keep it strict to avoid clefs, articulations, etc.
    const noteNodes = g.querySelectorAll('[data-vrv-type="note"], g.note, .note, use[href*="note"]');
    const xs=[];
    for (const el of noteNodes){
      const r = el.getBoundingClientRect();
      if (r && Number.isFinite(r.left) && Number.isFinite(r.right)){
        xs.push((r.left + r.right) * 0.5 - hostRect.left);
      }
    }
    const anchors = denoiseXs(xs);

    // Step 1: theoretical beat centers (evenly spaced across the measure bbox)
    const centers = [];
    for (let b=0;b<beats;b++){
      const tL =  b   / beats;
      const tR = (b+1)/ beats;
      centers.push(m.left + ((tL + tR) * 0.5) * width);
    }

    // Step 2: snap each center to nearest notehead X (if any)
    const snapped = (anchors.length? centers.map(c=>{
      // lower_bound in sorted anchors
      let lo=0, hi=anchors.length-1;
      while (lo<hi){
        const mid=(lo+hi)>>1;
        if (anchors[mid] < c) lo=mid+1; else hi=mid;
      }
      let idx=lo, best=anchors[idx], d=Math.abs(best-c);
      if (idx>0 && Math.abs(anchors[idx-1]-c) < d){ idx-=1; best=anchors[idx]; }
      return best;
    }) : centers);

    // Step 3: boundaries from midpoints of neighbor centers (guarantees exactly "beats" boxes)
    const boxes=[];
    for (let i=0;i<snapped.length;i++){
      const L = (i===0              ? m.left  : (snapped[i-1] + snapped[i]) * 0.5);
      const R = (i===snapped.length-1? m.right : (snapped[i]   + snapped[i+1]) * 0.5);
      boxes.push({left:L, right:R, top:m.top, height});
    }
    // Clamp minor numeric noise
    for (const b of boxes){
      if (b.left < m.left)   b.left  = m.left;
      if (b.right > m.right) b.right = m.right;
    }
    return boxes;
  }

  // Build (or rebuild) all overlays
  function buildOverlays(){
    const measures = findMeasures();
    const hostRect = host.getBoundingClientRect();

    // Remove previous overlays, keep the selection set
    host.querySelectorAll('.beat-box').forEach(n=>n.remove());

    let lastBeats = 4;
    let absIndex  = 0; // 1-based across the whole document
    for (const {g} of measures){
      absIndex += 1;
      const bpm = beatsInMeasure(g, lastBeats);
      lastBeats = bpm;

      const boxes = computeBoxesForMeasure(g, absIndex, bpm, hostRect);
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

    publishSelection(); // sync header + title
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
  // a tick later in case fonts/layout shift
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

        # Listen for BEATS payloads via document title
        self.web.titleChanged.connect(self._on_title_changed)

    def _on_title_changed(self, title: str):
        if not title.startswith("BEATS:"):
            return
        try:
            import json
            keys = json.loads(title[len("BEATS:"):])
            txt = " ".join(keys) if keys else "(none)"
            self.header.setText(f"Selected beats: {txt}")
        except Exception:
            pass


def render_score_to_inline_svg(score_path: str) -> str:
    """
    Render all pages to inline SVG using the Verovio toolkit.
    Returns a single string concatenating page SVGs.
    """
    tk = verovio.toolkit()
    # Minimal, robust options; avoid tool-specific signatures.
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
    ap = argparse.ArgumentParser(description="Beat selection lab: render with Verovio and select beats (no subdivisions).")
    ap.add_argument("--score", required=True, help="Path to MusicXML or MXL score (XML with default-x works well).")
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
