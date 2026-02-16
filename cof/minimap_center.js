// cofmm_es/minimap_center.js
import { inferDarkFromBody } from "./utils.js";
import { MiniMapUI } from "./ui.js";
import { MiniMapState } from "./minimap_state.js";
import { colors } from "./theme.js";
import { render } from "./render.js";

export class COFMiniMap {
  constructor(opts = {}) {
    this._raf = 0;
    this._running = false;

    const initialDark = (opts.dark != null) ? !!opts.dark : inferDarkFromBody();
    this.dark = initialDark;

    this.ui = new MiniMapUI({ ...(opts.ui || {}), dark: initialDark });
    this.state = new MiniMapState(opts.state || {});

    this._onNoteOn = this._onNoteOn.bind(this);
    this._onNoteOff = this._onNoteOff.bind(this);
    this._onTheme = this._onTheme.bind(this);
    this._onReset = this._onReset.bind(this);
    this._onWinResize = this._onWinResize.bind(this);

    this._initEvents();
    this._startLoop();
    this.requestDraw();
  }

  destroy() {
    this._stopLoop();
    window.removeEventListener("midi:noteon", this._onNoteOn);
    window.removeEventListener("midi:noteoff", this._onNoteOff);
    window.removeEventListener("ui:theme", this._onTheme);
    window.removeEventListener("ui:reset", this._onReset);
    window.removeEventListener("resize", this._onWinResize);
    this.ui?.destroy();
    this.ui = null;
    this.state = null;
  }

  reset() {
    this.state?.reset(performance.now());
    this.requestDraw();
  }

  _initEvents() {
    window.addEventListener("midi:noteon", this._onNoteOn);
    window.addEventListener("midi:noteoff", this._onNoteOff);
    window.addEventListener("ui:theme", this._onTheme);
    window.addEventListener("ui:reset", this._onReset);
    window.addEventListener("resize", this._onWinResize);
  }

  _onWinResize() {
    if (this.ui && this.ui.resize(false)) this.requestDraw();
  }

  _onTheme(e) {
    const dark = !!(e && e.detail && e.detail.dark);
    this.dark = dark;
    this.ui?.setDark(dark);
    this.requestDraw();
  }

  _onReset() {
    this.reset();
  }

  _onNoteOn(e) {
    const d = (e && e.detail) ? e.detail : {};
    this.state.noteOn(Number(d.midi), Number(d.velocity ?? d.vel ?? 0), Number(d.ts ?? performance.now()));
    this.requestDraw();
  }

  _onNoteOff(e) {
    const d = (e && e.detail) ? e.detail : {};
    this.state.noteOff(Number(d.midi), Number(d.ts ?? performance.now()));
    this.requestDraw();
  }

  _startLoop() {
    this._running = true;
    const loop = () => {
      if (!this._running) return;
      this.state.tick(performance.now());
      this.requestDraw();
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }

  _stopLoop() {
    this._running = false;
    if (this._raf) cancelAnimationFrame(this._raf);
    this._raf = 0;
  }

  requestDraw() {
    if (this._raf) return;
    this._raf = requestAnimationFrame(() => {
      this._raf = 0;
      this.draw();
    });
  }

  draw() {
    if (!this.ui?.ctx) return;
    const { w, h } = this.ui.geom();
    if (!w || !h) return;
    render(this.ui.ctx, w, h, colors(this.dark), this.state);
  }
}

export function bootCOFMiniMap(opts = {}) {
  return new COFMiniMap(opts);
}
