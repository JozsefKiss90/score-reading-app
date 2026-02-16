// cofmm_es/render.js
import { COF_PCS, COF_LABELS, pcToIndex } from "./cof.js";
import { withAlpha, strokeRoundedRect, drawArrow, clamp } from "./utils.js";

function drawPcTrailArrows(ctx, cx, cy, r, colors, state) {
  const now = performance.now();
  const trail = state.pcTrail || [];
  if (trail.length < 2) return;

  const pts = [];
  for (const it of trail) {
    const idx = pcToIndex(it.pc);
    if (idx == null) continue;
    const a = (idx / 12) * Math.PI * 2 - Math.PI / 2;
    pts.push({ x: cx + r * Math.cos(a), y: cy + r * Math.sin(a), t: it.t });
  }
  if (pts.length < 2) return;

  for (let i = 1; i < pts.length; i++) {
    const p0 = pts[i - 1];
    const p1 = pts[i];
    const dx = p1.x - p0.x, dy = p1.y - p0.y;
    const d = Math.hypot(dx, dy);
    if (d < 2) continue;

    const age = clamp((now - p1.t) / state.pcTrailWindowMs, 0, 1);
    const alpha = 1 - age;
    const aStroke = 0.10 + 0.45 * alpha;
    const aHead = 0.12 + 0.55 * alpha;

    ctx.save();
    ctx.lineWidth = 1.6;
    ctx.strokeStyle = withAlpha(colors.arrow, aStroke);
    ctx.fillStyle = withAlpha(colors.arrowHead, aHead);

    const pad = 10;
    const ux = dx / d, uy = dy / d;
    const x0 = p0.x + ux * pad;
    const y0 = p0.y + uy * pad;
    const x1 = p1.x - ux * pad;
    const y1 = p1.y - uy * pad;

    drawArrow(ctx, x0, y0, x1, y1, 8, 6);
    ctx.restore();
  }
}

function drawHarmonicCenter(ctx, cx, cy, r, colors, state) {
  const v = state.computeHarmonicCenterVec();
  if (!v || v.mag <= 0.02) return;

  const baseRad = r * 0.20;
  const maxRad = r * 0.58;
  const t = clamp(v.mag * 1.35, 0, 1);
  const rad = baseRad + (maxRad - baseRad) * t;

  const x = cx + v.ux * rad;
  const y = cy + v.uy * rad;

  ctx.save();

  ctx.lineWidth = 1.4;
  ctx.strokeStyle = withAlpha(colors.centerVector, 0.10 + 0.40 * t);
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(x, y);
  ctx.stroke();

  const haloR = 10 + 16 * t;
  ctx.fillStyle = withAlpha(colors.centerHalo, 0.10 + 0.28 * t);
  ctx.beginPath();
  ctx.arc(x, y, haloR, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = withAlpha(colors.centerDot2, 0.45 + 0.45 * t);
  ctx.strokeStyle = withAlpha(colors.centerDot2Stroke, 0.35 + 0.45 * t);
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  ctx.arc(x, y, 4.2 + 2.2 * t, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();

  ctx.restore();
}

function drawFrame(ctx, w, h, colors) {
  ctx.lineWidth = 1;
  ctx.strokeStyle = colors.frame;
  strokeRoundedRect(ctx, 6, 6, w - 12, h - 12, 12);
}

function drawCrosshair(ctx, cx, cy, w, h, colors) {
  ctx.strokeStyle = colors.cross;
  ctx.beginPath(); ctx.moveTo(cx, 18); ctx.lineTo(cx, h - 18); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(18, cy); ctx.lineTo(w - 18, cy); ctx.stroke();
}

function drawRing(ctx, cx, cy, r, colors) {
  ctx.lineWidth = 1.25;
  ctx.strokeStyle = colors.ring;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.stroke();
}


function drawMiddleRing(ctx, cx, cy, r, colors, state) {
  const mr = state.middleRing;
  if (!mr || !mr.degrees) return;

  const analysis = state.chordDiatonic || null;

  const ringR = r * 0.78;          // middle ring radius (inside outer ring)
  const nodeR = 6.0;

  // subtle ring line
  ctx.save();
  ctx.lineWidth = 1.0;
  ctx.strokeStyle = withAlpha(colors.ring, 0.55);
  ctx.beginPath();
  ctx.arc(cx, cy, ringR, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();

  for (const deg of mr.degrees) {
    const idx = pcToIndex(deg.rootPc);
    if (idx == null) continue;

    const a = (idx / 12) * Math.PI * 2 - Math.PI / 2;
    const x = cx + ringR * Math.cos(a);
    const y = cy + ringR * Math.sin(a);

    const isCurrent = analysis && analysis.degree === deg.degree;

    // Function colors (T/S/D)
    let col = withAlpha(colors.label, 0.75);
    if (deg.func === "T") col = "rgba(60, 190, 120, 0.80)";
    else if (deg.func === "S") col = "rgba(80, 140, 230, 0.80)";
    else if (deg.func === "D") col = "rgba(230, 150, 70, 0.84)";

    ctx.save();
    ctx.lineWidth = isCurrent ? 2.2 : 1.2;
    ctx.strokeStyle = withAlpha(col, isCurrent ? 0.95 : 0.70);
    ctx.fillStyle = withAlpha(col, isCurrent ? 0.22 : 0.10);
    ctx.beginPath();
    ctx.arc(x, y, isCurrent ? (nodeR + 1.0) : nodeR, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    // Roman label
    ctx.font = isCurrent ? "700 11px system-ui" : "600 10px system-ui";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = withAlpha(colors.labelActive, isCurrent ? 0.90 : 0.65);
    ctx.fillText(deg.roman, x, y);

    ctx.restore();
  }

  // If analysis exists but is non-diatonic, show a subtle hint inside
  if (analysis && analysis.diatonicity && analysis.diatonicity !== "diatonic") {
    ctx.save();
    ctx.font = "12px system-ui";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const txt = (analysis.diatonicity === "borrowed") ? "borrowed" : "chromatic";
    ctx.fillStyle = withAlpha(colors.label, 0.55);
    ctx.fillText(txt, cx, cy + r * 0.33);
    ctx.restore();
  }
}

function drawNodesAndLabels(ctx, cx, cy, r, colors, state) {
  const activePcs = state.activePitchClasses();
  const lastPc = state.lastPc;
  const pulse = state.pulse();

  for (let i = 0; i < 12; i++) {
    const pc = COF_PCS[i];
    const a = (i / 12) * Math.PI * 2 - Math.PI / 2;
    const x = cx + r * Math.cos(a);
    const y = cy + r * Math.sin(a);

    const isActive = activePcs.has(pc);
    const isLast = (lastPc === pc);
    const nodeR = isActive ? 8.5 : 7.0;

    ctx.lineWidth = isActive ? 1.8 : 1.2;
    ctx.strokeStyle = isActive ? colors.nodeStrokeActive : colors.nodeStroke;
    ctx.fillStyle = isActive ? colors.nodeFillActive : colors.nodeFill;

    ctx.beginPath();
    ctx.arc(x, y, nodeR, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    if (isLast) {
      const rr = nodeR + 5 + 3 * pulse;
      ctx.lineWidth = 1.6;
      ctx.strokeStyle = colors.lastRing;
      ctx.beginPath();
      ctx.arc(x, y, rr, 0, Math.PI * 2);
      ctx.stroke();
    }

    const lx = cx + (r + 16) * Math.cos(a);
    const ly = cy + (r + 16) * Math.sin(a);

    ctx.font = "11px system-ui";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = isActive ? colors.labelActive : colors.label;
    ctx.fillText(COF_LABELS[i], lx, ly);
  }
}

function drawCenterDot(ctx, cx, cy, colors) {
  ctx.fillStyle = colors.centerDot;
  ctx.beginPath();
  ctx.arc(cx, cy, 2.5, 0, Math.PI * 2);
  ctx.fill();
}

function drawHintIfEmpty(ctx, cx, cy, colors, state) {
  if (state.activeMidi.size !== 0) return;
  ctx.fillStyle = colors.hint;
  ctx.font = "12px system-ui";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText("MIDI-driven mini-map", cx, cy + 22);
}

export function render(ctx, w, h, colors, state) {
  ctx.clearRect(0, 0, w, h);

  const cx = w / 2;
  const cy = h / 2 + 8;
  const r = Math.min(w, h) * 0.5 - 34;

  drawFrame(ctx, w, h, colors);
  drawCrosshair(ctx, cx, cy, w, h, colors);
  drawRing(ctx, cx, cy, r, colors);
  drawMiddleRing(ctx, cx, cy, r, colors, state);

  drawHarmonicCenter(ctx, cx, cy, r, colors, state);
  drawPcTrailArrows(ctx, cx, cy, r, colors, state);

  drawNodesAndLabels(ctx, cx, cy, r, colors, state);
  drawCenterDot(ctx, cx, cy, colors);
  drawHintIfEmpty(ctx, cx, cy, colors, state);
}
