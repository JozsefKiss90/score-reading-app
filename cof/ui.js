// cofmm_es/ui.js
import { inferDarkFromBody } from "./utils.js";

export class MiniMapUI {
  constructor(opts = {}) {
    this.opts = {
      hostId: opts.hostId || "scorePane",
      sizePx: Number.isFinite(opts.sizePx) ? opts.sizePx : 360,
      rightPx: Number.isFinite(opts.rightPx) ? opts.rightPx : 12,
      bottomPx: Number.isFinite(opts.bottomPx) ? opts.bottomPx : 12,
    };

    this.dark = (opts.dark != null) ? !!opts.dark : inferDarkFromBody();

    this.root = null;
    this.canvas = null;
    this.ctx = null;

    this.cssW = 0;
    this.cssH = 0;
    this.dpr = 1;

    this._resizeObs = null;

    this._ensureUI();
    this._applyTheme();
    this._setupResizeObserver();
    this.resize(true);
  }

  destroy() {
    if (this._resizeObs) {
      try { this._resizeObs.disconnect(); } catch {}
      this._resizeObs = null;
    }
    if (this.root && this.root.parentNode) this.root.parentNode.removeChild(this.root);
    this.root = null; this.canvas = null; this.ctx = null;
  }

  setDark(dark) {
    this.dark = !!dark;
    this._applyTheme();
  }

  _ensureUI() {
    const existing = document.getElementById("miniMap");
    if (existing) {
      this.root = existing;
      this.canvas = existing.querySelector("canvas") || null;
    }

    if (!this.root) {
      const host = document.getElementById(this.opts.hostId) || document.body;

      const root = document.createElement("div");
      root.id = "miniMap";
      root.setAttribute("aria-hidden", "true");
      root.style.position = "absolute";
      root.style.right = `${this.opts.rightPx}px`;
      root.style.bottom = `${this.opts.bottomPx}px`;
      root.style.width = `${this.opts.sizePx}px`;
      root.style.height = `${this.opts.sizePx}px`;
      root.style.zIndex = "1020";
      root.style.borderRadius = "14px";
      root.style.overflow = "hidden";
      root.style.pointerEvents = "none";
      root.style.backdropFilter = "blur(6px)";
      root.style.webkitBackdropFilter = "blur(6px)";

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

      const hostCS = getComputedStyle(host);
      if (host !== document.body && hostCS.position === "static") host.style.position = "relative";
      host.appendChild(root);

      this.root = root;
      this.canvas = canvas;
    }

    this.ctx = this.canvas ? this.canvas.getContext("2d") : null;
  }

  _applyTheme() {
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

  _setupResizeObserver() {
    if (!this.root) return;
    if (!("ResizeObserver" in window)) return;
    this._resizeObs = new ResizeObserver(() => this.resize(false));
    this._resizeObs.observe(this.root);
  }

  resize(force) {
    if (!this.root || !this.canvas || !this.ctx) return false;

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

    if (!changed) return false;

    this.cssW = cssW; this.cssH = cssH; this.dpr = dpr;
    this.canvas.width = pxW; this.canvas.height = pxH;
    this.canvas.style.width = cssW + "px";
    this.canvas.style.height = cssH + "px";

    // draw in CSS pixel space
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return true;
  }

  geom() {
    return { w: this.cssW, h: this.cssH };
  }
}
