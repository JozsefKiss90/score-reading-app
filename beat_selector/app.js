import { Dom } from './dom.js';
import { State } from './state.js';
import { Geom } from './geom.js';
import { Cursor } from './cursor.js';
import { Sidebar } from './sidebar.js';

export function createApp(boot){
  return new App(boot);
}

class App {
  constructor(boot){
    this.state = new State(boot);

    // Cursor smoothing params
    this.SNAP_T=0.06;
    this.NUDGE_T=0.25;
    this.NUDGE_GAIN=0.35;
    this.SMOOTH_ALPHA=0.4;
    this.MONO_TOL=1.5;
  }

  // ------------------------------------------------------------------
  // Theme
  // ------------------------------------------------------------------
  setTheme(name){
    const THEMES={
      amber:{fill:'rgba(255,214,10,0.18)', stroke:'rgba(255,149,0,0.75)', cursor:'#ff3b30'},
      sky:{fill:'rgba(56,189,248,0.18)', stroke:'rgba(2,132,199,0.75)', cursor:'#0ea5e9'},
      mint:{fill:'rgba(110,231,183,0.18)', stroke:'rgba(5,150,105,0.65)', cursor:'#10b981'},
      violet:{fill:'rgba(196,181,253,0.20)', stroke:'rgba(124,58,237,0.70)', cursor:'#8b5cf6'}
    };
    const t = THEMES[name]||THEMES.amber;
    const s=document.documentElement.style;
    s.setProperty('--hl-fill', t.fill);
    s.setProperty('--hl-stroke', t.stroke);
    s.setProperty('--cursor', t.cursor);
  }

  // ------------------------------------------------------------------
  // Beat boxes
  // ------------------------------------------------------------------
  _destroyBeatBoxes(){
    this.state.beatDivs.forEach(b=>b.remove());
    this.state.beatDivs=[];
  }

  _updateBeatVisibility(){
    const disp = this.state.beatVisible ? 'block' : 'none';
    this.state.beatDivs.forEach(b=>{ b.style.display=disp; });
  }

  _clearNoteSelectionAndHighlights(){
    const S = this.state;
    S.selNoteIds = new Set();
    S.selNotesByMidi = new Map();

    // Remove blue and green classes from the SVG.
    const svg = Dom.svgRoot();
    if(svg){
      svg.querySelectorAll('.note-hl').forEach(n=>n.classList.remove('note-hl'));
      svg.querySelectorAll('.midi-ok').forEach(n=>n.classList.remove('midi-ok'));
    }

    // Clear applied MIDI state (we keep S.midiDown so held keys can reapply after rebuild).
    S.midiActiveIdsByMidi = new Map();
  }

  setBeatBoxesVisible(on){
    const S = this.state;
    S.beatVisible = !!on;
    this._updateBeatVisibility();

    if(!S.beatVisible){
      // Clear selection when hiding beat UI
      S.selBeats = new Map();
      this._clearNoteSelectionAndHighlights();
      Sidebar.rebuild(S, Cursor.setNoteHighlight, () => this.refreshMidiHighlights());
    }
  }

  // ------------------------------------------------------------------
  // Cursor API (called from Python)
  // ------------------------------------------------------------------
  jsSetCursorAbs(absIdx, tInMeasure, dur){
    const S=this.state;
    S.queued=[absIdx, tInMeasure, dur];
    if(!S.readySvg) return;

    const out=this._compute(absIdx,tInMeasure,dur);
    if(!out) return;

    const [x, box, t]=out;
    Cursor.placeCursorAt(x, box);
    if(S.lastHL!==absIdx){
      Cursor.placeHL(box);
      S.lastHL=absIdx;
    }
    S.last={page:S.pageIndex, abs:absIdx, t:t, x:x};
    Dom.hud().textContent=`page=${S.pageIndex} abs=${absIdx} x=${Math.round(x)} t=${t.toFixed(3)}s`;
  }

  setPageAndSvg(pageIndex, svgUrl){
    const S=this.state;
    S.pageIndex=pageIndex;
    S.readySvg=false;
    S.last={page:-1,abs:-1,t:0,x:0};
    S.lastHL=-1;

    S.selBeats = new Map();
    this._destroyBeatBoxes();
    this._clearNoteSelectionAndHighlights();

    const obj=Dom.pageObj();
    obj.addEventListener('load', ()=>{
      Geom.scanMeasures(S);
      this._ensureBeatBoxes();

      if(S.queued){
        const [a,t,d]=S.queued;
        const r=this._compute(a,t,d);
        if(r){
          const [x,box,tt]=r;
          Cursor.placeCursorAt(x,box);
          Cursor.placeHL(box);
          S.lastHL=a;
          S.last={page:S.pageIndex,abs:a,t:tt,x:x};
        }
      }

      // Ensure SVG styles exist before any highlighting is applied.
      this.refreshMidiHighlights();
      this.setTheme('amber');
    }, {once:true});

    obj.data = (svgUrl.indexOf('?')===-1 ? svgUrl+'?ts='+Date.now() : svgUrl);
  }

  _ensureBeatBoxes(){
    const S=this.state;
    const frame=Dom.frame();
    this._destroyBeatBoxes();

    // UI model:
    // - Exactly ONE overlay element per measure ("measureBox").
    // - Beats are represented as internal separators, and selection is computed from
    //   click position within the measure box. No per-beat boxes exist in the DOM.

    const renderSelection = (mdiv, abs, beats) => {
      mdiv.querySelectorAll('.beatFill').forEach(n=>n.remove());
      const set = S.selBeats.get(abs);
      if(!set || set.size===0) return;

      const W = mdiv.clientWidth || 1;
      const H = mdiv.clientHeight || 1;

      for(const b of [...set].sort((a,b)=>a-b)){
        const u0=(b-1)/beats, u1=b/beats;
        const fill=document.createElement('div');
        fill.className='beatFill';
        fill.style.position='absolute';
        fill.style.left=Math.round(W*u0)+'px';
        fill.style.top='0px';
        fill.style.width=Math.max(0, Math.round(W*(u1-u0)))+'px';
        fill.style.height=H+'px';
        fill.style.background='var(--hl-fill)';
        fill.style.pointerEvents='none';
        mdiv.appendChild(fill);
      }
    };

    for(const abs of S.orderAbs){
      const box=S.boxesByAbs[abs];
      if(!box) continue;

      // BEAT_TIMES_MAP keys are JSON-serialized in Python; prefer string keys.
      const beats = (S.boot.BEAT_TIMES_MAP?.[String(abs)]?.length)
                 || (S.boot.BEAT_TIMES_MAP?.[abs]?.length)
                 || 1;

      const xL = box.left;
      const xR = box.right;
      const span = Math.max(1, xR - xL);

      const mdiv=document.createElement('div');
      mdiv.className='measureBox';
      mdiv.dataset.abs=String(abs);
      mdiv.dataset.beats=String(beats);

      // Ensure visibility without requiring CSS edits
      mdiv.style.position='absolute';
      mdiv.style.boxSizing='border-box';
      mdiv.style.border='2px solid var(--hl-stroke)';
      mdiv.style.borderRadius='6px';
      mdiv.style.pointerEvents='auto';
      mdiv.style.background='transparent';
      mdiv.style.overflow='hidden';

      const pad=2;
      mdiv.style.left=(Math.round(xL)+pad)+'px';
      mdiv.style.top=(Math.round(box.top)+pad)+'px';
      mdiv.style.width=Math.max(0, Math.round(span)-pad*2)+'px';
      mdiv.style.height=Math.max(0, Math.round(box.bottom-box.top)-pad*2)+'px';

      // Internal beat separators (visual only)
      for(let b=1; b<beats; b++){
        const sep=document.createElement('div');
        sep.className='beatSep';
        sep.style.position='absolute';
        sep.style.top='0px';
        sep.style.bottom='0px';
        sep.style.width='1px';
        sep.style.left=Math.round((b/beats)*10000)/100+'%';
        sep.style.background='rgba(0,0,0,0.18)';
        sep.style.pointerEvents='none';
        mdiv.appendChild(sep);
      }

      // Click selects a beat by x-position within the measure box
      mdiv.addEventListener('click', (ev)=>{
        ev.stopPropagation();
        const rect=mdiv.getBoundingClientRect();
        const x=Math.max(0, Math.min(rect.width-1, ev.clientX-rect.left));
        const beat=Math.max(1, Math.min(beats, Math.floor((x/Math.max(1,rect.width))*beats)+1));

        const key=Number(abs);
        const set = S.selBeats.get(key) || new Set();
        if(set.has(beat)) set.delete(beat);
        else set.add(beat);

        if(set.size===0) S.selBeats.delete(key);
        else S.selBeats.set(key,set);

        renderSelection(mdiv, key, beats);

        Sidebar.rebuild(S, Cursor.setNoteHighlight, () => this.refreshMidiHighlights());
      });

      frame.appendChild(mdiv);
      S.beatDivs.push(mdiv);

      renderSelection(mdiv, Number(abs), beats);
    }

    this._updateBeatVisibility();
  }

  _compute(absIdx, t, dur){
    const S=this.state;
    const box=S.boxesByAbs[absIdx];
    if(!box) return null;

    const D=Math.max(1e-6,dur);
    const tt=Math.max(0,Math.min(D,t));

    const xs=S.anchorsByAbs[absIdx]||[];
    const [xL,xR]=Geom.span(xs, box);
    let x_lin = Geom.lerp(xL,xR, tt/D);

    const ts=(S.boot.NOTE_TIMES_MAP?.[absIdx]) || (S.boot.NOTE_TIMES_MAP?.[String(absIdx)]) || [];
    const [k,dT]=Cursor.nearest(ts, tt);

    if(k>=0 && xs.length){
      if(dT<=this.SNAP_T) x_lin = xs[Math.min(k,xs.length-1)];
      else if(dT<=this.NUDGE_T){
        const w=this.NUDGE_GAIN*(1-dT/this.NUDGE_T);
        const xn=xs[Math.min(k,xs.length-1)];
        x_lin = x_lin + w*(xn-x_lin);
      }
    }

    let x_out=x_lin;
    if(S.last.page===S.pageIndex && S.last.abs===absIdx && tt>=S.last.t){
      x_out = S.last.x + this.SMOOTH_ALPHA*(x_lin - S.last.x);
      if(x_out + this.MONO_TOL < S.last.x) x_out = S.last.x;
    }

    return [x_out, box, tt];
  }

  handleResize(){
    if(!Dom.svgRoot()) return;
    Geom.scanMeasures(this.state);
    this._ensureBeatBoxes();

    const q=this.state.queued;
    if(q){
      const [a,t,d]=q;
      const r=this._compute(a,t,d);
      if(r){
        const [x,box,tt]=r;
        Cursor.placeCursorAt(x,box);
        Cursor.placeHL(box);
        this.state.lastHL=a;
        this.state.last={page:this.state.pageIndex,abs:a,t:tt,x:x};
      }
    }

    this.refreshMidiHighlights();
  }

  // ------------------------------------------------------------------
  // MIDI bridge (called from Python)
  // ------------------------------------------------------------------
  onMidiNoteOn(pitch, velocity, timestamp){
    const S = this.state;
    const p = Number(pitch);
    if(!Number.isFinite(p)) return;

    S.midiDown.add(p);
    this._applyMidiForPitch(p);
  }

  onMidiNoteOff(pitch, timestamp){
    const S = this.state;
    const p = Number(pitch);
    if(!Number.isFinite(p)) return;

    S.midiDown.delete(p);
    this._clearMidiForPitch(p);
  }

  _applyMidiForPitch(pitch){
    const S = this.state;
    const svg = Dom.svgRoot();
    if(!svg) return;

    const ids = S.selNotesByMidi.get(pitch);
    if(!ids || ids.size===0) return;

    let active = S.midiActiveIdsByMidi.get(pitch);
    if(!active){
      active = new Set();
      S.midiActiveIdsByMidi.set(pitch, active);
    }

    for(const id of ids){
      const node = svg.ownerDocument.getElementById(id);
      if(node){
        Cursor.setMidiOk(node, true);
        active.add(id);
      }
    }
  }

  _clearMidiForPitch(pitch){
    const S = this.state;
    const svg = Dom.svgRoot();
    if(!svg) return;

    const active = S.midiActiveIdsByMidi.get(pitch);
    if(!active || active.size===0){
      S.midiActiveIdsByMidi.delete(pitch);
      return;
    }

    for(const id of active){
      const node = svg.ownerDocument.getElementById(id);
      if(node) Cursor.setMidiOk(node, false);
    }

    S.midiActiveIdsByMidi.delete(pitch);
  }

  refreshMidiHighlights(){
    const S = this.state;
    const svg = Dom.svgRoot();
    if(!svg) return;

    // Clear all previously applied green highlights.
    for(const [midi, ids] of S.midiActiveIdsByMidi.entries()){
      for(const id of ids){
        const node = svg.ownerDocument.getElementById(id);
        if(node) Cursor.setMidiOk(node, false);
      }
    }
    S.midiActiveIdsByMidi = new Map();

    // Re-apply based on currently held keys and current selection.
    for(const midi of S.midiDown.values()){
      this._applyMidiForPitch(midi);
    }
  }
}
