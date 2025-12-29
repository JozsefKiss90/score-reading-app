import { Dom } from './dom.js';

export class Cursor {
  // ------------------------------------------------------------------
  // Cursor placement
  // ------------------------------------------------------------------
  static nearest(ts, t){
    if(!ts || !ts.length) return [-1, 1e9];
    let lo=0, hi=ts.length-1;
    while(lo < hi){
      const m = (lo + hi) >> 1;
      if(ts[m] < t) lo = m + 1;
      else hi = m;
    }
    let idx = lo;
    let d = Math.abs(ts[idx] - t);
    if(idx > 0 && Math.abs(ts[idx-1] - t) < d){
      idx -= 1;
      d = Math.abs(ts[idx] - t);
    }
    return [idx, d];
  }

  static placeCursorAt(x, box){
    const c = Dom.cursor();
    if(!c) return;
    c.style.left   = `${x}px`;
    c.style.top    = `${box.top}px`;
    c.style.height = `${box.bottom - box.top}px`;
  }

  static placeHL(box){
    const hl = Dom.barHL();
    if(!hl) return;
    const pad = 2;
    hl.style.left   = `${box.left + pad}px`;
    hl.style.top    = `${box.top + pad}px`;
    hl.style.width  = `${Math.max(0, (box.right - box.left) - pad*2)}px`;
    hl.style.height = `${Math.max(0, (box.bottom - box.top) - pad*2)}px`;
  }

  // ------------------------------------------------------------------
  // SVG note highlighting
  // ------------------------------------------------------------------
  static _ensureSvgStyles(){
    const svg = Dom.svgRoot();
    if(!svg) return;

    const doc = svg.ownerDocument;
    const existing = doc.getElementById('beat-style');
    if(existing) return;

    const style = doc.createElementNS('http://www.w3.org/2000/svg', 'style');
    style.setAttribute('id', 'beat-style');

    // Keep selectors broad: Verovio emits noteheads as <g class="notehead"> with <use>.
    style.textContent = `
      .note-hl .notehead use,
      .note-hl .notehead path,
      .note-hl .notehead ellipse,
      .note-hl .notehead polygon,
      .note-hl .notehead rect {
        fill: #2563eb !important;
        stroke: #2563eb !important;
      }

      .midi-ok .notehead use,
      .midi-ok .notehead path,
      .midi-ok .notehead ellipse,
      .midi-ok .notehead polygon,
      .midi-ok .notehead rect {
        fill: #16a34a !important;
        stroke: #16a34a !important;
      }
    `;

    // Append to root so it applies in the embedded SVG document.
    svg.appendChild(style);
  }

  static setNoteHighlight(node, on){
    if(!node) return;
    Cursor._ensureSvgStyles();
    try {
      node.classList.toggle('note-hl', !!on);
    } catch { /* ignore */ }
  }

  static setMidiOk(node, on){
    if(!node) return;
    Cursor._ensureSvgStyles();
    try {
      node.classList.toggle('midi-ok', !!on);
    } catch { /* ignore */ }
  }
}
