// cofmm_es/theme.js
export function colors(dark) {
  if (dark) {
    return {
      frame: "rgba(255,255,255,0.18)",
      cross: "rgba(255,255,255,0.12)",
      ring: "rgba(255,255,255,0.22)",

      nodeStroke: "rgba(255,255,255,0.20)",
      nodeFill: "rgba(255,255,255,0.06)",

      nodeStrokeActive: "rgba(255,255,255,0.60)",
      nodeFillActive: "rgba(255,255,255,0.22)",

      label: "rgba(255,255,255,0.55)",
      labelActive: "rgba(255,255,255,0.85)",

      lastRing: "rgba(255,255,255,0.55)",
      centerDot: "rgba(255,255,255,0.30)",
      hint: "rgba(255,255,255,0.45)",

      arrow: "rgba(255,255,255,0.45)",
      arrowHead: "rgba(255,255,255,0.60)",

      centerVector: "rgba(255,255,255,0.55)",
      centerHalo: "rgba(255,255,255,0.40)",
      centerDot2: "rgba(255,255,255,0.85)",
      centerDot2Stroke: "rgba(255,255,255,0.70)",
    };
  }

  return {
    frame: "rgba(0,0,0,0.16)",
    cross: "rgba(0,0,0,0.10)",
    ring: "rgba(0,0,0,0.18)",

    nodeStroke: "rgba(0,0,0,0.20)",
    nodeFill: "rgba(0,0,0,0.06)",

    nodeStrokeActive: "rgba(0,0,0,0.55)",
    nodeFillActive: "rgba(0,0,0,0.20)",

    label: "rgba(0,0,0,0.50)",
    labelActive: "rgba(0,0,0,0.85)",

    lastRing: "rgba(0,0,0,0.50)",
    centerDot: "rgba(0,0,0,0.28)",
    hint: "rgba(0,0,0,0.42)",

    arrow: "rgba(0,0,0,0.35)",
    arrowHead: "rgba(0,0,0,0.50)",

    centerVector: "rgba(0,0,0,0.50)",
    centerHalo: "rgba(0,0,0,0.25)",
    centerDot2: "rgba(0,0,0,0.80)",
    centerDot2Stroke: "rgba(0,0,0,0.65)",
  };
}
