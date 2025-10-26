# select_beats_min.py
# Run:  python select_beats_min.py --score path/to/score.mxl
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
  /* Overlay columns */
  .beat-box {
    position:absolute;
    top:0; bottom:auto; /* we'll set explicit height/coords via JS */
    background: rgba(0, 102, 255, 0.06); /* faint to show columns exist */
    border-left: 1px solid rgba(0, 102, 255, 0.25);
    border-right: 1px solid rgba(0, 102, 255, 0.25);
    pointer-events: auto;
    cursor: pointer;
  }
  .beat-box.sel {
    background: rgba(0, 102, 255, 0.22);
    outline: 1px solid rgba(0, 102, 255, 0.70);
    outline-offset: -1px;
  }
  svg { display:block; width:100%; height:auto; background:#fff !important; }
  /* keep things crisp */
  * { box-sizing:border-box; }
</style>
</head>
<body>
  <div id="top">Selected beats: <span id="selStr">(none)</span></div>
  <div id="frame">
    <div id="svgHost">
      {SVG_HERE}
    </div>
  </div>

<script>
(function(){
  const host    = document.getElementById('svgHost');
  const frameEl = document.getElementById('frame');
  const selStr  = document.getElementById('selStr');

  // persistent selection set -> strings like "m-b" where m is 1-based absolute measure index, b is 1-based beat number in that measure
  const selected = new Set();

  // util: debounce
  function debounce(fn, ms){ let t=null; return (...a)=>{ clearTimeout(t); t=setTimeout(()=>fn(...a), ms); }; }

  // find all measures across all inline SVGs (visual order)
  function findMeasureGroups(){
    const roots = Array.from(host.querySelectorAll('svg'));
    const out = [];
    for (const svg of roots){
      // primary: Verovio uses g[data-vrv-type="measure"]
      let groups = svg.querySelectorAll('g[data-vrv-type="measure"]');
      if (!groups || groups.length===0){
        // fallbacks
        groups = svg.querySelectorAll('g.measure, g[class*="measure"]');
      }
      for (const g of groups) out.push({svg, g});
    }
    return out;
  }

  // dedupe/denoise consecutive Xs closer than 2px
  function denoiseXs(xs){
    xs.sort((a,b)=>a-b);
    const out=[];
    for (const x of xs){
      if (out.length===0 || Math.abs(out[out.length-1]-x) > 2) out.push(x);
    }
    return out;
  }

  // discover beats-per-measure: inspect time signature within the measure; fallback to lastSeen or 4
  function beatsInMeasure(g, lastSeen){
    // Typical verovio: <g data-vrv-type="timeSig"> with text children, numerator then denominator
    const tsg = g.querySelector('g[data-vrv-type="timeSig"], g.timeSig, .timeSig');
    if (tsg){
      // read digits from its textContent
      const txt = (tsg.textContent || "").replace(/\s+/g, '');
      // Find patterns like "44", "34", "68", or "C" (common time) / "¢" (cut time)
      if (/^[0-9]{2,}$/.test(txt)){
        // treat first 1–2 digits as numerator (safe heuristic)
        // Some fonts place numerator+denominator stacked; textContent may be "44".
        const num = parseInt(txt.slice(0, txt.length/2), 10);
        if (Number.isFinite(num) && num>0) return num;
      }
      if (/C/.test(txt) && !/¢/.test(txt)) return 4; // common time
      if (/¢/.test(txt)) return 2; // cut time (alla breve) → treat as 2 beats
    }
    return (lastSeen && lastSeen>0) ? lastSeen : 4;
  }

  // Compute beat center Xs inside a measure box, then snap each center to nearest engraved notehead X
  function measureBeatCenters(measureRect, anchorsX, beats){
    // equal subdivisions (center of each segment)
    const spanL = measureRect.left, spanR = measureRect.right;
    const width = Math.max(1, spanR - spanL);
    const centers = [];
    for (let i=0;i<beats;i++){
      const tL = i / beats, tR = (i+1) / beats;
      const cx = spanL + ( (tL + tR) * 0.5 ) * width;
      centers.push(cx);
    }
    if (!anchorsX || anchorsX.length===0) return centers;
    // snap each center to nearest anchor
    const snapped = centers.map(c=>{
      // binary-ish search in sorted anchors
      let lo=0, hi=anchorsX.length-1;
      while (lo<hi){
        const m=(lo+hi)>>1;
        if (anchorsX[m] < c) lo = m+1; else hi = m;
      }
      let idx=lo, best=anchorsX[idx], d=Math.abs(best - c);
      if (idx>0 && Math.abs(anchorsX[idx-1]-c) < d){ idx=idx-1; best=anchorsX[idx]; d=Math.abs(best - c); }
      return best;
    });
    return snapped;
  }

  // Given centers, compute boundaries (midpoints) and return beat boxes [L,R] within measureRect
  function beatBoundaries(measureRect, centers){
    const L0 = measureRect.left, R0 = measureRect.right;
    if (centers.length===0) return [[L0,R0]];
    const B = [];
    for (let i=0;i<centers.length;i++){
      const left  = (i===0) ? L0 : ( (centers[i-1] + centers[i]) * 0.5 );
      const right = (i===centers.length-1) ? R0 : ( (centers[i] + centers[i+1]) * 0.5 );
      B.push([left, right]);
    }
    return B;
  }

  // build overlay columns
  let overlayBuiltOnce = false;

  function buildOverlays(){
    const groups = findMeasureGroups();
    const hostRect = host.getBoundingClientRect();

    // First clear previous overlays (but keep selection set)
    host.querySelectorAll('.beat-box').forEach(n=>n.remove());

    // Collect anchors per measure and place columns
    let lastBeats = 4;
    let absMeasureIndex = 0; // 1-based for user-visible m in "m-b"
    for (const {svg, g} of groups){
      absMeasureIndex += 1;
      const gRectAbs = g.getBoundingClientRect();
      const mRect = {
        left:  gRectAbs.left - hostRect.left,
        right: gRectAbs.right - hostRect.left,
        top:   gRectAbs.top - hostRect.top,
        bottom:gRectAbs.bottom - hostRect.top
      };

      // Notehead anchors inside this measure
      const noteNodes = g.querySelectorAll('[data-vrv-type="note"], g.note, .note, use[href*="note"]');
      const xs = [];
      for (const el of noteNodes){
        const r = el.getBoundingClientRect();
        if (r && Number.isFinite(r.left) && Number.isFinite(r.right)){
          xs.push(( (r.left + r.right) * 0.5 ) - hostRect.left);
        }
      }
      const anchorsX = denoiseXs(xs);

      // beats per measure (from time signature within this measure if present)
      const bpm = beatsInMeasure(g, lastBeats);
      lastBeats = bpm;

      // Compute centers -> boundaries
      const centers = measureBeatCenters(mRect, anchorsX, bpm);
      const bounds  = beatBoundaries(mRect, centers);

      // Place .beat-box for each beat
      const height = Math.max(0, mRect.bottom - mRect.top);
      bounds.forEach((pair, i)=>{
        const bL = Math.max(0, Math.min(pair[0], pair[1]));
        const bR = Math.max(0, Math.max(pair[0], pair[1]));
        const w  = Math.max(0, bR - bL);

        const div = document.createElement('div');
        div.className = 'beat-box';
        div.style.left   = bL + 'px';
        div.style.top    = mRect.top + 'px';
        div.style.width  = w  + 'px';
        div.style.height = height + 'px';

        const key = absMeasureIndex + '-' + (i+1);
        if (selected.has(key)) div.classList.add('sel');

        div.addEventListener('click', (ev)=>{
          ev.preventDefault();
          ev.stopPropagation();
          if (selected.has(key)){
            selected.delete(key);
            div.classList.remove('sel');
          }else{
            selected.add(key);
            div.classList.add('sel');
          }
          publishSelection();
        }, {passive:false});

        host.appendChild(div);
      });
    }

    overlayBuiltOnce = true;
    publishSelection(); // refresh title & header on any rebuild
  }

  function publishSelection(){
    const keys = Array.from(selected).sort((a,b)=>{
      const [am,ab] = a.split('-').map(Number);
      const [bm,bb] = b.split('-').map(Number);
      if (am !== bm) return am - bm;
      return ab - bb;
    });
    selStr.textContent = keys.length ? keys.join(' ') : '(none)';
    // Mirror to document.title for the Python side:
    document.title = 'BEATS:' + JSON.stringify(keys);
  }

  const rebuildDebounced = debounce(buildOverlays, 80);

  // Build when content is ready
  window.addEventListener('load', ()=>{
    // Observe resize (window + any font/layout changes)
    buildOverlays();
  });

  // Rebuild on frame scroll/resize to keep columns aligned
  window.addEventListener('resize', rebuildDebounced);
  // If fonts/images/layout cause late shifts, rebuild after a tick
  setTimeout(buildOverlays, 0);

  // When the user scrolls, positions don't change relative to the host rect (absolute),
  // but some platforms may reflow SVGs; a light debounce doesn't hurt:
  frameEl.addEventListener('scroll', rebuildDebounced, {passive:true});
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
        self.header.setStyleSheet("padding:6px 10px; border-bottom:1px solid #e5e7eb; background:#fff; color:#111;")

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
            payload = title[len("BEATS:"):]
            keys = json.loads(payload)
            # Render like: "3-1 3-2 4-1" or "(none)"
            txt = " ".join(keys) if keys else "(none)"
            self.header.setText(f"Selected beats: {txt}")
        except Exception:
            # Ignore malformed titles
            pass


def render_score_to_inline_svg(score_path: str) -> str:
    """
    Use verovio.toolkit to render all pages to SVG and return a single inline string
    with the pages stacked vertically.
    """
    tk = verovio.toolkit()
    # Safe, minimal options; avoid extra params to keep signatures stable.
    # Use viewBox for responsive sizing.
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
    svgs = []
    for p in range(1, pages + 1):
        svg = tk.renderToSVG(p)
        # Ensure each page SVG is block-level; we'll just concatenate.
        svgs.append(svg)
    # Join pages; inline — no external files.
    return "\n".join(svgs)


def main():
    ap = argparse.ArgumentParser(description="Minimal beat-selection prototype on engraved score (Verovio + PyQt6 WebEngine).")
    ap.add_argument("--score", required=True, help="Path to MusicXML/MXL file")
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
    win.resize(1100, 800)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
