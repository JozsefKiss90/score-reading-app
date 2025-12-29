// cofmm_es/utils.js
export function clamp(v, a, b) {
  return Math.max(a, Math.min(b, v));
}

export function inferDarkFromBody() {
  try {
    const bg = getComputedStyle(document.body).backgroundColor || "";
    const m = bg.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i);
    if (!m) return false;
    const r = Number(m[1]) || 0, g = Number(m[2]) || 0, b = Number(m[3]) || 0;
    return (r + g + b) < 180;
  } catch {
    return false;
  }
}

export function withAlpha(rgba, a) {
  const m = String(rgba).match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([0-9.]+))?\s*\)/i);
  if (!m) return rgba;
  const r = Number(m[1]) | 0, g = Number(m[2]) | 0, b = Number(m[3]) | 0;
  const aa = clamp(a, 0, 1);
  return `rgba(${r},${g},${b},${aa})`;
}

export function strokeRoundedRect(ctx, x, y, w, h, r) {
  const rr = Math.max(0, Math.min(r, w / 2, h / 2));
  ctx.beginPath();
  if (typeof ctx.roundRect === "function") {
    ctx.roundRect(x, y, w, h, rr);
  } else {
    ctx.moveTo(x + rr, y);
    ctx.arcTo(x + w, y, x + w, y + h, rr);
    ctx.arcTo(x + w, y + h, x, y + h, rr);
    ctx.arcTo(x, y + h, x, y, rr);
    ctx.arcTo(x, y, x + w, y, rr);
  }
  ctx.stroke();
}

export function drawArrow(ctx, x0, y0, x1, y1, headLen, headWidth) {
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  ctx.lineTo(x1, y1);
  ctx.stroke();

  const dx = x1 - x0, dy = y1 - y0;
  const ang = Math.atan2(dy, dx);

  const hx1 = x1 - headLen * Math.cos(ang) + headWidth * Math.sin(ang);
  const hy1 = y1 - headLen * Math.sin(ang) - headWidth * Math.cos(ang);

  const hx2 = x1 - headLen * Math.cos(ang) - headWidth * Math.sin(ang);
  const hy2 = y1 - headLen * Math.sin(ang) + headWidth * Math.cos(ang);

  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(hx1, hy1);
  ctx.lineTo(hx2, hy2);
  ctx.closePath();
  ctx.fill();
}
