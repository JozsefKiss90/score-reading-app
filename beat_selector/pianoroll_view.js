import { Dom } from './dom.js';

function clamp(v, a, b){ return Math.max(a, Math.min(b, v)); }

export class PianoRollView {
  constructor(state){
    this.state = state;
    this.canvas = Dom.pianoroll();
    this.ctx = this.canvas.getContext('2d', { alpha: true });
    this.dpr = window.devicePixelRatio || 1;

    this.tAbs = 0;
    this.tRel = 0;
    this.dur = 1;

    window.addEventListener('resize', () => this.resize());
    this.resize();
  }

  resize(){
    const c = this.canvas;
    if(!c) return;
    const r = c.getBoundingClientRect();
    c.width  = Math.max(1, Math.floor(r.width  * this.dpr));
    c.height = Math.max(1, Math.floor(r.height * this.dpr));
    this.render();
  }

  setCursor(abs, tRel, dur){
    this.tAbs = Number(abs);
    this.tRel = Number(tRel);
    this.dur  = Math.max(1e-6, Number(dur));
    this.render();
  }

  render(){
    const c = this.canvas;
    const ctx = this.ctx;
    if(!c || !ctx) return;

    const S = this.state;
    const w = c.width, h = c.height;

    ctx.clearRect(0,0,w,h);

    // Background (track dark mode by a class set by your setDarkMode())
    const isDark = document.documentElement.classList.contains('dark-score') || document.body.classList.contains('dark-score');
    ctx.fillStyle = isDark ? 'rgba(0,0,0,0.35)' : 'rgba(255,255,255,0.85)';
    ctx.fillRect(0,0,w,h);

    // Determine which measures to show:
    // show current page measures (S.boot.ABS_INDEXES) as a continuous time strip.
    const absList = S.boot.ABS_INDEXES || [];
    if(!absList.length) return;

    // Build a flat list of note events with a global x mapping:
    // Each measure occupies equal horizontal fraction based on its duration (from NOTE_TIMES_MAP last beat + measure dur passed by cursor for current abs).
    // We can approximate measure duration using max(beat time) + 1 beat, but better: use cursor dur when abs matches.
    // Practical: derive per-measure span = last beat time + (delta to next beat) or fallback to 1.
    const spans = [];
    let totalSpan = 0;
    for(const abs of absList){
      const beats = (S.boot.BEAT_TIMES_MAP && S.boot.BEAT_TIMES_MAP[String(abs)]) || [];
      let span = 0;
      if(beats.length >= 2){
        const step = beats[1] - beats[0];
        span = beats[beats.length-1] + step;
      } else if(beats.length === 1){
        span = Math.max(0.5, beats[0] + 0.5);
      } else {
        span = 1.0;
      }
      spans.push(span);
      totalSpan += span;
    }
    totalSpan = Math.max(1e-6, totalSpan);

    // Pitch range: compute min/max midi in visible measures
    let minMidi = 128, maxMidi = -1;
    const measureEvents = new Map();
    for(const abs of absList){
      const ev = (S.boot.PITCH_EVENTS && S.boot.PITCH_EVENTS[String(abs)]) || [];
      measureEvents.set(Number(abs), ev);
      for(const e of ev){
        const m = e.midi;
        if(typeof m === 'number'){
          if(m < minMidi) minMidi = m;
          if(m > maxMidi) maxMidi = m;
        }
      }
    }
    if(maxMidi < 0){ return; }
    // Add padding
    minMidi = clamp(minMidi - 2, 0, 127);
    maxMidi = clamp(maxMidi + 2, 0, 127);

    const pitchSpan = Math.max(1, maxMidi - minMidi + 1);

    // Helpers
    const xOf = (measureIndex, tRel) => {
      let x0 = 0;
      for(let i=0;i<measureIndex;i++) x0 += spans[i];
      return ((x0 + clamp(tRel,0,spans[measureIndex])) / totalSpan) * w;
    };

    const yOfMidi = (midi) => {
      const k = (maxMidi - midi) / pitchSpan;
      return k * (h - 10) + 5;
    };

    // Grid: horizontal pitch lines
    ctx.strokeStyle = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';
    ctx.lineWidth = 1;
    for(let m=minMidi; m<=maxMidi; m++){
      if(m % 12 === 0){ // C lines
        const y = yOfMidi(m);
        ctx.beginPath();
        ctx.moveTo(0,y);
        ctx.lineTo(w,y);
        ctx.stroke();
      }
    }

    // Measure separators
    ctx.strokeStyle = isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.12)';
    let acc = 0;
    for(let i=0;i<absList.length;i++){
      const x = (acc / totalSpan) * w;
      ctx.beginPath();
      ctx.moveTo(x,0);
      ctx.lineTo(x,h);
      ctx.stroke();
      acc += spans[i];
    }

    // Notes
    // Color rules:
    // - selected beat notes: slightly emphasized
    // - midi-ok notes (your App paints SVG ids green) -> highlight in green here too if we can map by id
    // In events we do not have SVG ids; you *do* have them in PITCH_MAP. We’ll map pitch->ids per beat for "midi-ok".
    const okIds = new Set();
    if(S.midiActiveIdsByMidi && typeof S.midiActiveIdsByMidi.values === 'function'){
      for(const set of S.midiActiveIdsByMidi.values()){
        if(!set) continue;
        for(const id of set) okIds.add(String(id));
      }
    }

    // Build a set of "ok midis" as a fallback if no ids exist
    const okMidis = new Set(S.midiDown || []);

    for(let i=0;i<absList.length;i++){
      const abs = Number(absList[i]);
      const evs = measureEvents.get(abs) || [];
      for(const e of evs){
        const midi = e.midi;
        const t0 = e.t_rel || 0;
        const dur = e.dur_rel || 0.15;

        const x0 = xOf(i, t0);
        const x1 = xOf(i, t0 + dur);
        const y  = yOfMidi(midi);
        const hh = Math.max(3, Math.floor((h-10)/pitchSpan));

        // base fill
        let fill = isDark ? 'rgba(120,120,120,0.55)' : 'rgba(60,60,60,0.35)';

        // If midi is currently held: brighten
        if(okMidis.has(midi)){
          fill = isDark ? 'rgba(34,197,94,0.55)' : 'rgba(22,163,74,0.35)';
        }

        ctx.fillStyle = fill;
        ctx.fillRect(x0, y - hh/2, Math.max(1, x1-x0), hh);
      }
    }

    // Cursor line (current abs/tRel within the strip)
    // We place it only when current abs is visible
    const idx = absList.indexOf(this.tAbs);
    if(idx >= 0){
      const x = xOf(idx, this.tRel);
      ctx.strokeStyle = isDark ? 'rgba(255,80,80,0.9)' : 'rgba(220,38,38,0.7)';
      ctx.beginPath();
      ctx.moveTo(x,0);
      ctx.lineTo(x,h);
      ctx.stroke();
    }
  }
}
