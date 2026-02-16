// cofmm_es/render.js
import { COF_PCS, COF_LABELS, pcToIndex } from "./cof.js";
import { withAlpha, strokeRoundedRect, drawArrow, clamp } from "./utils.js";

function drawPcTrailArrows(ctx, cx, cy, r, colors, state, style) {
  const st = style || {};
  const alphaMul = (st.alphaMul ?? 1.0);
  const widthMul = (st.widthMul ?? 1.0);
  const headMul  = (st.headMul  ?? 1.0);
  const windowMul = (st.windowMul ?? 1.0);
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

    const age = clamp((now - p1.t) / (state.pcTrailWindowMs * windowMul), 0, 1);
    const alpha = 1 - age;
    const aStroke = 0.10 + 0.45 * alpha;
    const aHead = 0.12 + 0.55 * alpha;

    ctx.save();
    ctx.lineWidth = 1.6 * widthMul;
    ctx.strokeStyle = withAlpha(colors.arrow, clamp(aStroke * alphaMul, 0, 1));
    ctx.fillStyle = withAlpha(colors.arrowHead, clamp(aHead * alphaMul, 0, 1));

    const pad = 10;
    const ux = dx / d, uy = dy / d;
    const x0 = p0.x + ux * pad;
    const y0 = p0.y + uy * pad;
    const x1 = p1.x - ux * pad;
    const y1 = p1.y - uy * pad;

    drawArrow(ctx, x0, y0, x1, y1, 8 * headMul, 6 * headMul);
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

function drawNodesAndLabels(ctx, cx, cy, r, colors, state, st) {
  // Be robust: accept Set or Array from state.activePitchClasses()
  let activePcsRaw = null;
  try {
    activePcsRaw = (typeof state.activePitchClasses === "function") ? state.activePitchClasses() : null;
  } catch (e) {
    activePcsRaw = null;
  }

  const activePcs =
    (activePcsRaw instanceof Set) ? activePcsRaw
    : Array.isArray(activePcsRaw) ? new Set(activePcsRaw)
    : new Set();

  const lastPc = state.lastPc;
  const pulse = (typeof state.pulse === "function") ? state.pulse() : 0;

  // Arrow-style multipliers might be missing; default safely
  const widthMul = (st && Number.isFinite(st.widthMul)) ? st.widthMul : 1.0;

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
      ctx.lineWidth = 1.6 * widthMul;
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

// Requires clamp, withAlpha, pcToIndex to already be in scope (they are in your renderer).

function drawOuterKeyGlow(ctx, cx, cy, r, colors, state) {
  const tonal = state.tonal;
  if (!tonal) return;

  const pcs = [];
  if (tonal.prevGlobalPc != null) pcs.push({ pc: tonal.prevGlobalPc, s: Math.max(0, tonal.prevGlobalStrength || 0) * 0.55 });
  if (tonal.globalTonicPc != null) pcs.push({ pc: tonal.globalTonicPc, s: Math.max(0, tonal.globalStrength || 0.0) });

  const ringR = r;
  const baseNodeR = 7.5;

  for (const item of pcs) {
    const idx = pcToIndex(item.pc);
    if (idx == null) continue;

    const a = (idx / 12) * Math.PI * 2 - Math.PI / 2;
    const x = cx + ringR * Math.cos(a);
    const y = cy + ringR * Math.sin(a);

    const glowAlpha = clamp(0.06 + 0.34 * item.s, 0, 0.42);
    const glowR = baseNodeR + 12 + 12 * item.s;

    ctx.save();
    ctx.fillStyle = withAlpha(colors.labelActive, glowAlpha);
    ctx.beginPath();
    ctx.arc(x, y, glowR, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = withAlpha(colors.labelActive, clamp(0.22 + 0.40 * item.s, 0, 0.65));
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.arc(x, y, baseNodeR + 4 + 4 * item.s, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }
}

function drawDualVectors(ctx, cx, cy, r, colors, state) {
  const tonal = state.tonal;
  if (!tonal) return;

  const globalPc = tonal.globalTonicPc;
  const candPc = tonal.candidatePc;
  if (globalPc == null || candPc == null || candPc === globalPc) return;

  const hold = tonal.candidateHoldMs || 0;
  if (hold < 350) return;

  const ringR = r * 0.86;

  function vecToPc(pc) {
    const idx = pcToIndex(pc);
    if (idx == null) return null;
    const ang = (idx / 12) * Math.PI * 2 - Math.PI / 2;
    return { ux: Math.cos(ang), uy: Math.sin(ang) };
  }

  const gv = vecToPc(globalPc);
  const cv = vecToPc(candPc);
  if (!gv || !cv) return;

  ctx.save();

  // Global (solid, faint)
  ctx.strokeStyle = withAlpha(colors.vector, clamp(0.18 + 0.22 * (tonal.globalStrength || 0.5), 0, 0.45));
  ctx.lineWidth = 1.1;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(cx + gv.ux * ringR, cy + gv.uy * ringR);
  ctx.stroke();

  // Candidate (dashed, slightly brighter)
  const cs = clamp(tonal.candidateStrength || 0.0, 0, 1);
  ctx.strokeStyle = withAlpha(colors.vector, clamp(0.20 + 0.28 * cs, 0, 0.55));
  ctx.lineWidth = 1.2;
  ctx.setLineDash([6, 6]);
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(cx + cv.ux * ringR, cy + cv.uy * ringR);
  ctx.stroke();

  ctx.restore();
}

function drawTonicizationHalo(ctx, cx, cy, r, colors, state) {
  const tonal = state.tonal;
  const mr = state.middleRing;
  if (!tonal || !mr || !mr.degrees) return;
  if (tonal.tonicizeTargetPc == null || !tonal.tonicizeStrength) return;

  const targetPc = tonal.tonicizeTargetPc;
  const s = clamp(tonal.tonicizeStrength, 0, 1);

  const degNode = mr.degrees.find(d => d.rootPc === targetPc);
  if (!degNode) return;

  const idx = pcToIndex(degNode.rootPc);
  if (idx == null) return;

  const ringR = r * 0.78;
  const a = (idx / 12) * Math.PI * 2 - Math.PI / 2;
  const x = cx + ringR * Math.cos(a);
  const y = cy + ringR * Math.sin(a);

  const tt = performance.now();
  const pulse = 0.5 + 0.5 * Math.sin((tt / 760) * Math.PI * 2);
  const haloR = 6 + (6 + 8 * pulse) * s;
  const alpha = (0.08 + 0.22 * pulse) * s;

  ctx.save();
  ctx.lineWidth = 1.8;
  ctx.strokeStyle = withAlpha(colors.labelActive, clamp(alpha, 0, 0.42));
  ctx.beginPath();
  ctx.arc(x, y, haloR, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();
}

function computeArrowStyleMultipliers(state) {
  const tonal = state.tonal;

  let alphaMul = 1.0;
  let widthMul = 1.0;
  let headMul = 1.0;
  let windowMul = 1.0;

  if (!tonal) return { alphaMul, widthMul, headMul, windowMul };

  const tonicizing =
    tonal.tonicizeTargetPc != null &&
    (tonal.tonicizeStrength || 0) > 0.08;

  const transitioning =
    tonal.candidatePc != null &&
    tonal.globalTonicPc != null &&
    tonal.candidatePc !== tonal.globalTonicPc &&
    (tonal.candidateHoldMs || 0) > 350;

  if (tonicizing && !transitioning) {
    alphaMul *= 0.70;
    widthMul *= 0.85;
    headMul *= 0.85;
    windowMul *= 0.70;
  } else if (transitioning) {
    alphaMul *= 0.95;
    widthMul *= 1.05;
  }

  const switchedRecently =
    tonal.switchTs &&
    (performance.now() - tonal.switchTs) < 3200;

  if (switchedRecently) {
    alphaMul *= 1.10;
    widthMul *= 1.20;
    headMul *= 1.10;
    windowMul *= 1.15;
  }

  return { alphaMul, widthMul, headMul, windowMul };
}

export function render(ctx, w, h, colors, state) {
  ctx.clearRect(0, 0, w, h);

  const cx = w / 2;
  const cy = h / 2 + 8;
  const r = Math.min(w, h) * 0.5 - 34;

  drawFrame(ctx, w, h, colors);
  drawCrosshair(ctx, cx, cy, w, h, colors);
  drawRing(ctx, cx, cy, r, colors);
  drawOuterKeyGlow(ctx, cx, cy, r, colors, state);
  drawTonicizationHalo(ctx, cx, cy, r, colors, state);
  drawDualVectors(ctx, cx, cy, r, colors, state);

  drawMiddleRing(ctx, cx, cy, r, colors, state);

  drawHarmonicCenter(ctx, cx, cy, r, colors, state);
  const arrowStyle = computeArrowStyleMultipliers(state);
  drawPcTrailArrows(ctx, cx, cy, r, colors, state, arrowStyle);

  drawNodesAndLabels(ctx, cx, cy, r, colors, state, arrowStyle);
  drawCenterDot(ctx, cx, cy, colors);
  drawHintIfEmpty(ctx, cx, cy, colors, state);
}
