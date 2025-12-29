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

function drawNodesAndLabels(ctx, cx, cy, r, colors, state) {
  const activePcs = state.activePitchClasses();
  const chord = state.chord;
  const chordToneSet = chord ? new Set(chord.chordTones || []) : null;
  const rootPc = chord ? chord.rootPc : null;
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

    // Base node styling
    let lw = isActive ? 1.8 : 1.2;
    let stroke = isActive ? colors.nodeStrokeActive : colors.nodeStroke;
    let fill = isActive ? colors.nodeFillActive : colors.nodeFill;

    // If we have a chord hypothesis, emphasize chord tones and the root
    if (chordToneSet && chordToneSet.has(pc)) {
      lw = Math.max(lw, 2.2);
      stroke = withAlpha(stroke, 0.92);
      fill = withAlpha(fill, 0.30);
    }
    if (rootPc != null && pc === rootPc) {
      lw = Math.max(lw, 2.4);
      stroke = withAlpha(colors.labelActive, 0.95);
      fill = withAlpha(fill, 0.34);
    }

    ctx.lineWidth = lw;
    ctx.strokeStyle = stroke;
    ctx.fillStyle = fill;

    ctx.beginPath();
    ctx.arc(x, y, nodeR, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    // Root marker ring
    if (rootPc != null && pc === rootPc) {
      ctx.save();
      ctx.lineWidth = 1.6;
      ctx.strokeStyle = withAlpha(colors.labelActive, 0.80);
      ctx.beginPath();
      ctx.arc(x, y, nodeR + 4.5, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

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

function drawChordHUD(ctx, w, h, colors, state) {
  const chord = state.chord;
  const fn = state.function;
  if (!chord) return;

  const padX = 12;
  const y1 = 46;
  const y2 = 62;

  ctx.save();
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";

  // Chord name
  ctx.font = "600 14px system-ui";
  ctx.fillStyle = withAlpha(colors.labelActive, 0.90);
  ctx.fillText(chord.name, padX, y1);

  // Confidence
  ctx.font = "12px system-ui";
  ctx.fillStyle = withAlpha(colors.label, 0.75);
  ctx.fillText(`${Math.round(chord.confidence * 100)}%`, padX + 80, y1);

  // Function badge
  if (fn && fn.badge) {
    const badge = fn.badge;
    const bx = padX;
    const by = y2;
    const bw = 22;
    const bh = 18;

    let bcol = withAlpha(colors.label, 0.75);
    if (badge === "T") bcol = "rgba(60, 190, 120, 0.85)";
    else if (badge === "S") bcol = "rgba(80, 140, 230, 0.85)";
    else if (badge === "D") bcol = "rgba(230, 150, 70, 0.88)";

    ctx.strokeStyle = withAlpha(bcol, 0.90);
    ctx.fillStyle = withAlpha(bcol, 0.18);
    ctx.lineWidth = 1.2;
    strokeRoundedRect(ctx, bx, by - bh/2, bw, bh, 6);
    ctx.fill();

    ctx.fillStyle = withAlpha(bcol, 0.95);
    ctx.font = "700 12px system-ui";
    ctx.textAlign = "center";
    ctx.fillText(badge, bx + bw/2, by);
    ctx.textAlign = "left";
  }

  // Inferred tonic name (optional)
  if (fn && fn.tonicPc != null) {
    const tonicName = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"][fn.tonicPc];
    ctx.font = "12px system-ui";
    ctx.fillStyle = withAlpha(colors.label, 0.70);
    ctx.fillText(`tonic ≈ ${tonicName}`, padX + 34, y2);
  }

  ctx.restore();
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

  drawHarmonicCenter(ctx, cx, cy, r, colors, state);
  drawPcTrailArrows(ctx, cx, cy, r, colors, state);

  drawNodesAndLabels(ctx, cx, cy, r, colors, state);
  drawCenterDot(ctx, cx, cy, colors);
  drawChordHUD(ctx, w, h, colors, state);
  drawHintIfEmpty(ctx, cx, cy, colors, state);
}
