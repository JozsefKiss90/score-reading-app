/* cof_minimap.js
 *
 * Standalone Circle-of-Fifths mini-map (UI + placeholder ring + real-time MIDI note highlights)
 * - Injects its own container UI automatically
 * - Handles resize + devicePixelRatio scaling
 * - Listens to:
 *     - window events: "midi:noteon", "midi:noteoff"
 *     - window event:  "ui:theme"
 *
 * Expected event payloads:
 *   window.dispatchEvent(new CustomEvent("midi:noteon", { detail: { midi: 60, velocity: 96, ts: 123456 } }))
 *   window.dispatchEvent(new CustomEvent("midi:noteoff", { detail: { midi: 60, ts: 123457 } }))
 *   window.dispatchEvent(new CustomEvent("ui:theme", { detail: { dark: true } }))
 *
 * No dependencies on beat selector scripts.
 */

(() => {
  "use strict";

  // ----------------------------
  // Utilities
  // ----------------------------
  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

  function inferDarkFromBody() {
    // Heuristic: if body background is dark-ish, assume dark mode.
    try {
      const bg = getComputedStyle(document.body).backgroundColor || "";
      const m = bg.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i);
      if (!m) return false;
      const r = Number(m[1]) || 0, g = Number(m[2]) || 0, b = Number(m[3]) || 0;
      return (r + g + b) < 180;
    } catch (_) {
      return false;
    }
  }

  // Circle of Fifths order (pitch classes) starting at C:
  // C, G, D, A, E, B, F#, C#, G#, D#, A#, F
  const COF_PCS = [0, 7, 2, 9, 4, 11, 6, 1, 8, 3, 10, 5];
  const COF_LABELS = ["C", "G", "D", "A", "E", "B", "F#", "C#", "G#", "D#", "A#", "F"];

  const PC_TO_INDEX = (() => {
    const m = new Map();
    for (let i = 0; i < COF_PCS.length; i++) m.set(COF_PCS[i], i);
    return m;
  })();

  // ----------------------------
  // Mini-map class
  // ----------------------------
  class COFMiniMap {
    constructor() {
      this.dark = inferDarkFromBody();

      this.root = null;
      this.canvas = null;
      this.ctx = null;

      this._raf = 0;
      this._resizeObs = null;

      // Active MIDI tracking (by midi number); highlight is per pitch-class
      this.activeMidi = new Set();
      this.lastPc = null;
      this.lastVel = 0;
      this.lastTs = 0;

      // Motion trail: recent pitch-class steps (for vector arrows)
      this.pcTrail = [];                 // [{pc:int, t:ms}]
      this.pcTrailMax = 18;              // max nodes stored
      this.pcTrailWindowMs = 4500;       // keep last N ms
      this._ignoreRepeatedPc = true;     // do not add same-pc steps

      this.cssW = 0;
      this.cssH = 0;
      this.dpr = 1;

      this._onNoteOn = this._onNoteOn.bind(this);
      this._onNoteOff = this._onNoteOff.bind(this);
      this._onTheme = this._onTheme.bind(this);
      this._onWinResize = this._onWinResize.bind(this);

      this._initUI();
      this._initEvents();
      this._resize(true);
      this._requestDraw();
    }

    destroy() {
      window.removeEventListener("midi:noteon", this._onNoteOn);
      window.removeEventListener("midi:noteoff", this._onNoteOff);
      window.removeEventListener("ui:theme", this._onTheme);
      window.removeEventListener("resize", this._onWinResize);

      if (this._resizeObs) {
        try { this._resizeObs.disconnect(); } catch (_) {}
        this._resizeObs = null;
      }

      if (this._raf) cancelAnimationFrame(this._raf);
      this._raf = 0;

      if (this.root && this.root.parentNode) this.root.parentNode.removeChild(this.root);
      this.root = null;
      this.canvas = null;
      this.ctx = null;
    }

    // ----------------------------
    // UI injection
    // ----------------------------
    _initUI() {
      // If already present, reuse it.
      const existing = document.getElementById("miniMap");
      if (existing) {
        this.root = existing;
        this.canvas = existing.querySelector("canvas") || null;
      }

      if (!this.root) {
        const host = document.getElementById("scorePane") || document.body;

        const root = document.createElement("div");
        root.id = "miniMap";
        root.setAttribute("aria-hidden", "true");
        root.style.position = "absolute";
        root.style.right = "12px";
        root.style.bottom = "12px";
        root.style.width = "220px";
        root.style.height = "220px";
        root.style.zIndex = "1020";
        root.style.borderRadius = "14px";
        root.style.overflow = "hidden";
        root.style.pointerEvents = "none";
        root.style.backdropFilter = "blur(6px)";
        root.style.webkitBackdropFilter = "blur(6px)";

        // Header
        const header = document.createElement("div");
        header.id = "miniMapHeader";
        header.textContent = "Harmony";
        header.style.position = "absolute";
        header.style.left = "10px";
        header.style.top = "8px";
        header.style.font = "600 12px/1.1 system-ui";
        header.style.letterSpacing = "0.02em";
        header.style.textTransform = "uppercase";
        header.style.userSelect = "none";
        header.style.pointerEvents = "none";

        const sub = document.createElement("div");
        sub.id = "miniMapSub";
        sub.textContent = "Circle of Fifths";
        sub.style.position = "absolute";
        sub.style.left = "10px";
        sub.style.top = "24px";
        sub.style.font = "500 11px/1.1 system-ui";
        sub.style.userSelect = "none";
        sub.style.pointerEvents = "none";

        const canvas = document.createElement("canvas");
        canvas.id = "miniMapCanvas";
        canvas.style.display = "block";
        canvas.style.width = "100%";
        canvas.style.height = "100%";
        canvas.style.pointerEvents = "none";

        root.appendChild(header);
        root.appendChild(sub);
        root.appendChild(canvas);

        // Ensure host positioning if needed
        const hostCS = getComputedStyle(host);
        if (host !== document.body && hostCS.position === "static") {
          host.style.position = "relative";
        }

        host.appendChild(root);

        this.root = root;
        this.canvas = canvas;
      }

      this.ctx = this.canvas ? this.canvas.getContext("2d") : null;
      this._applyThemeToContainer();
    }

    _applyThemeToContainer() {
      if (!this.root) return;
      const mmH = this.root.querySelector("#miniMapHeader");
      const mmS = this.root.querySelector("#miniMapSub");

      if (this.dark) {
        this.root.style.background = "rgba(0,0,0,0.58)";
        this.root.style.border = "1px solid rgba(255,255,255,0.18)";
        this.root.style.boxShadow = "0 10px 28px rgba(0,0,0,0.45)";
        if (mmH) mmH.style.color = "rgba(255,255,255,0.72)";
        if (mmS) mmS.style.color = "rgba(255,255,255,0.60)";
      } else {
        this.root.style.background = "rgba(255,255,255,0.78)";
        this.root.style.border = "1px solid rgba(0,0,0,0.12)";
        this.root.style.boxShadow = "0 10px 28px rgba(0,0,0,0.18)";
        if (mmH) mmH.style.color = "rgba(0,0,0,0.65)";
        if (mmS) mmS.style.color = "rgba(0,0,0,0.55)";
      }
    }

    // ----------------------------
    // Event hookup
    // ----------------------------
    _initEvents() {
      window.addEventListener("midi:noteon", this._onNoteOn);
      window.addEventListener("midi:noteoff", this._onNoteOff);
      window.addEventListener("ui:theme", this._onTheme);
      window.addEventListener("resize", this._onWinResize);

      if (this.root && "ResizeObserver" in window) {
        this._resizeObs = new ResizeObserver(() => this._resize(false));
        this._resizeObs.observe(this.root);
      }
    }

    _onWinResize() {
      this._resize(false);
    }

    _onTheme(e) {
      const dark = !!(e && e.detail && e.detail.dark);
      this.dark = dark;
      this._applyThemeToContainer();
      this._requestDraw();
    }

    _onNoteOn(e) {
      const d = (e && e.detail) ? e.detail : {};
      const midi = Number(d.midi);
      const vel = Number(d.velocity ?? d.vel ?? 0);
      const ts = Number(d.ts ?? performance.now());

      if (!Number.isFinite(midi)) return;

      // MIDI convention: note-on with velocity 0 == note-off
      if (vel <= 0) {
        this.activeMidi.delete(midi);
      } else {
        this.activeMidi.add(midi);
        const pc = ((midi % 12) + 12) % 12;

        // Push into trail (optionally ignore same-pc repeats)
        if (!this._ignoreRepeatedPc || this.pcTrail.length === 0 || this.pcTrail[this.pcTrail.length - 1].pc !== pc) {
          this.pcTrail.push({ pc, t: ts });
          if (this.pcTrail.length > this.pcTrailMax) this.pcTrail.shift();
        }

        // Drop stale items by time window
        const cutoff = ts - this.pcTrailWindowMs;
        while (this.pcTrail.length > 0 && this.pcTrail[0].t < cutoff) this.pcTrail.shift();

        this.lastPc = pc;
        this.lastVel = clamp(vel / 127, 0, 1);
        this.lastTs = ts;
      }

      this._requestDraw();
    }

    _onNoteOff(e) {
      const d = (e && e.detail) ? e.detail : {};
      const midi = Number(d.midi);
      if (!Number.isFinite(midi)) return;
      this.activeMidi.delete(midi);
      this._requestDraw();
    }

    // ----------------------------
    // Resize / DPR
    // ----------------------------
    _resize(force) {
      if (!this.root || !this.canvas || !this.ctx) return;

      const rect = this.root.getBoundingClientRect();
      const cssW = Math.max(1, Math.round(rect.width));
      const cssH = Math.max(1, Math.round(rect.height));
      const dpr = window.devicePixelRatio || 1;

      const pxW = Math.max(1, Math.round(cssW * dpr));
      const pxH = Math.max(1, Math.round(cssH * dpr));

      const changed =
        force ||
        this.cssW !== cssW ||
        this.cssH !== cssH ||
        this.dpr !== dpr ||
        this.canvas.width !== pxW ||
        this.canvas.height !== pxH;

      if (changed) {
        this.cssW = cssW;
        this.cssH = cssH;
        this.dpr = dpr;

        this.canvas.width = pxW;
        this.canvas.height = pxH;
        this.canvas.style.width = cssW + "px";
        this.canvas.style.height = cssH + "px";

        // Draw in CSS pixel space
        this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        this._requestDraw();
      }
    }

    _requestDraw() {
      if (this._raf) return;
      this._raf = requestAnimationFrame(() => {
        this._raf = 0;
        this._draw();
      });
    }

    // ----------------------------
    // Rendering
    // ----------------------------
    _draw() {
      if (!this.ctx || !this.cssW || !this.cssH) return;

      const ctx = this.ctx;
      const w = this.cssW;
      const h = this.cssH;

      ctx.clearRect(0, 0, w, h);

      const colors = this._colors();

      // CoF ring center (compute before crosshair so axes cross the origin)
      const cx = w / 2;
      const cy = h / 2 + 8; // slight down shift to clear header

      // Outer frame guide (subtle)
      ctx.lineWidth = 1;
      ctx.strokeStyle = colors.frame;
      this._strokeRoundedRect(ctx, 6, 6, w - 12, h - 12, 12);

      // Crosshair (must cross the origin)
      ctx.strokeStyle = colors.cross;
      ctx.beginPath(); ctx.moveTo(cx, 18); ctx.lineTo(cx, h - 18); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(18, cy); ctx.lineTo(w - 18, cy); ctx.stroke();

      // CoF ring
      const r = Math.min(w, h) * 0.5 - 34;

      ctx.lineWidth = 1.25;
      ctx.strokeStyle = colors.ring;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.stroke();

      // Motion arrows between successive pitch classes
      this._drawPcTrailArrows(ctx, cx, cy, r, colors);

      // Gather active pitch classes
      const activePcCounts = new Array(12).fill(0);
      for (const midi of this.activeMidi) {
        const pc = ((midi % 12) + 12) % 12;
        activePcCounts[pc] += 1;
      }
      const activePcs = new Set();
      for (let pc = 0; pc < 12; pc++) if (activePcCounts[pc] > 0) activePcs.add(pc);

      // Nodes + labels
      for (let i = 0; i < 12; i++) {
        const pc = COF_PCS[i];
        const a = (i / 12) * Math.PI * 2 - Math.PI / 2; // start at top
        const x = cx + r * Math.cos(a);
        const y = cy + r * Math.sin(a);

        const isActive = activePcs.has(pc);
        const isLast = (this.lastPc === pc);

        const nodeR = isActive ? 8.5 : 7.0;

        // Node
        ctx.lineWidth = isActive ? 1.8 : 1.2;
        ctx.strokeStyle = isActive ? colors.nodeStrokeActive : colors.nodeStroke;
        ctx.fillStyle = isActive ? colors.nodeFillActive : colors.nodeFill;

        ctx.beginPath();
        ctx.arc(x, y, nodeR, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        // "Last note" accent ring
        if (isLast) {
          const pulse = this._pulse();
          const rr = nodeR + 5 + 3 * pulse;
          ctx.lineWidth = 1.6;
          ctx.strokeStyle = colors.lastRing;
          ctx.beginPath();
          ctx.arc(x, y, rr, 0, Math.PI * 2);
          ctx.stroke();
        }

        // Label (outside the ring)
        const lx = cx + (r + 16) * Math.cos(a);
        const ly = cy + (r + 16) * Math.sin(a);

        ctx.font = "11px system-ui";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillStyle = isActive ? colors.labelActive : colors.label;
        ctx.fillText(COF_LABELS[i], lx, ly);
      }

      // Center mark
      ctx.fillStyle = colors.centerDot;
      ctx.beginPath();
      ctx.arc(cx, cy, 2.5, 0, Math.PI * 2);
      ctx.fill();

      // Footer hint (only if empty)
      if (this.activeMidi.size === 0) {
        ctx.fillStyle = colors.hint;
        ctx.font = "12px system-ui";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("MIDI-driven mini-map", cx, cy + 22);
      }
    }

    _drawPcTrailArrows(ctx, cx, cy, r, colors) {
      const now = performance.now();
      if (!this.pcTrail || this.pcTrail.length < 2) return;

      // Build node positions for each trail element
      const pts = [];
      for (const it of this.pcTrail) {
        const idx = PC_TO_INDEX.get(it.pc);
        if (idx == null) continue;

        const a = (idx / 12) * Math.PI * 2 - Math.PI / 2; // same angle convention as nodes
        const x = cx + r * Math.cos(a);
        const y = cy + r * Math.sin(a);
        pts.push({ x, y, t: it.t });
      }
      if (pts.length < 2) return;

      // Draw segment arrows with age-based fading (older = fainter)
      for (let i = 1; i < pts.length; i++) {
        const p0 = pts[i - 1];
        const p1 = pts[i];

        // Skip near-zero movement
        const dx = p1.x - p0.x, dy = p1.y - p0.y;
        const d = Math.hypot(dx, dy);
        if (d < 2) continue;

        // Fade based on age of the destination point
        const age = clamp((now - p1.t) / this.pcTrailWindowMs, 0, 1);
        const alpha = 1 - age; // recent = 1, old = 0
        const aStroke = 0.10 + 0.45 * alpha; // keep a minimum visibility
        const aHead = 0.12 + 0.55 * alpha;

        ctx.save();
        ctx.lineWidth = 1.6;
        ctx.strokeStyle = this._withAlpha(colors.arrow, aStroke);
        ctx.fillStyle = this._withAlpha(colors.arrowHead, aHead);

        // Pull endpoints slightly inward so arrows don't collide with node circles
        const pad = 10;
        const ux = dx / d, uy = dy / d;
        const x0 = p0.x + ux * pad;
        const y0 = p0.y + uy * pad;
        const x1 = p1.x - ux * pad;
        const y1 = p1.y - uy * pad;

        this._drawArrow(ctx, x0, y0, x1, y1, 8, 6);
        ctx.restore();
      }
    }

    _drawArrow(ctx, x0, y0, x1, y1, headLen, headWidth) {
      // shaft
      ctx.beginPath();
      ctx.moveTo(x0, y0);
      ctx.lineTo(x1, y1);
      ctx.stroke();

      // head
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

    _withAlpha(rgba, a) {
      // Accept "rgba(r,g,b,x)" or "rgb(r,g,b)" and return rgba(...) with new alpha
      const m = String(rgba).match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([0-9.]+))?\s*\)/i);
      if (!m) return rgba;
      const r = Number(m[1]) | 0, g = Number(m[2]) | 0, b = Number(m[3]) | 0;
      const aa = clamp(a, 0, 1);
      return `rgba(${r},${g},${b},${aa})`;
    }

    _pulse() {
      // Gentle pulse based on time since last note-on
      const now = performance.now();
      const dt = Math.max(0, now - (this.lastTs || now));
      const t = dt / 700; // slower pulse
      const decay = Math.exp(-dt / 2200);
      return Math.sin(t * Math.PI * 2) * 0.5 * decay;
    }

    _strokeRoundedRect(ctx, x, y, w, h, r) {
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

    _colors() {
      if (this.dark) {
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
      };
    }
  }

  // ----------------------------
  // Auto-start
  // ----------------------------
  function boot() {
    // Avoid double instantiation
    if (window.COFMiniMap && typeof window.COFMiniMap.destroy === "function") return;

    window.COFMiniMap = new COFMiniMap();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
