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
    this.SNAP_T=0.06; this.NUDGE_T=0.25; this.NUDGE_GAIN=0.35; this.SMOOTH_ALPHA=0.4; this.MONO_TOL=1.5;
  }

  setTheme(name){
    const THEMES={
      amber:{fill:'rgba(255,214,10,0.18)', stroke:'rgba(255,149,0,0.75)', cursor:'#ff3b30'},
      sky:{fill:'rgba(56,189,248,0.18)', stroke:'rgba(2,132,199,0.75)', cursor:'#0ea5e9'},
      mint:{fill:'rgba(110,231,183,0.18)', stroke:'rgba(5,150,105,0.65)', cursor:'#10b981'},
      violet:{fill:'rgba(196,181,253,0.20)', stroke:'rgba(124,58,237,0.70)', cursor:'#8b5cf6'}
    };
    const t = THEMES[name]||THEMES.amber, s=document.documentElement.style;
    s.setProperty('--hl-fill', t.fill); s.setProperty('--hl-stroke', t.stroke); s.setProperty('--cursor', t.cursor);
  }

  _destroyBeatBoxes(){ this.state.beatDivs.forEach(b=>b.remove()); this.state.beatDivs=[]; }
  _updateBeatVisibility(){
    const disp = this.state.beatVisible ? 'block' : 'none';
    this.state.beatDivs.forEach(b=>{ b.style.display=disp; });
  }

  setBeatBoxesVisible(on){
    this.state.beatVisible=!!on; this._updateBeatVisibility();
    if(!this.state.beatVisible){
      document.querySelectorAll('.beatBox.sel').forEach(b=>b.classList.remove('sel'));
      Sidebar.rebuild(this.state, Cursor.setNoteHighlight);
    }
  }

  jsSetCursorAbs(absIdx, tInMeasure, dur){
    const S=this.state; S.queued=[absIdx, tInMeasure, dur];
    if(!S.readySvg) return;
    const out=this._compute(absIdx,tInMeasure,dur); if(!out) return;
    const [x, box, t]=out;
    Cursor.placeCursorAt(x, box);
    if(S.lastHL!==absIdx){ Cursor.placeHL(box); S.lastHL=absIdx; }
    S.last={page:S.pageIndex, abs:absIdx, t:t, x:x};
    Dom.hud().textContent=`page=${S.pageIndex} abs=${absIdx} x=${Math.round(x)} t=${t.toFixed(3)}s`;
  }

  setPageAndSvg(pageIndex, svgUrl){
    const S=this.state; S.pageIndex=pageIndex; S.readySvg=false; S.last={page:-1,abs:-1,t:0,x:0}; S.lastHL=-1;
    this._destroyBeatBoxes();
    const obj=Dom.pageObj();
    obj.addEventListener('load', ()=>{
      Geom.scanMeasures(S);
      this._ensureBeatBoxes();
      if(S.queued){
        const [a,t,d]=S.queued;
        const r=this._compute(a,t,d);
        if(r){ const [x,box,tt]=r; Cursor.placeCursorAt(x,box); Cursor.placeHL(box);
          S.lastHL=a; S.last={page:S.pageIndex,abs:a,t:tt,x:x}; }
      }
      this.setTheme('amber');
    }, {once:true});
    obj.data = (svgUrl.indexOf('?')===-1 ? svgUrl+'?ts='+Date.now() : svgUrl);
  }

  _ensureBeatBoxes(){
    const S=this.state, frame=Dom.frame(); this._destroyBeatBoxes();
    for(const abs of S.orderAbs){
      const box=S.boxesByAbs[abs]; if(!box) continue;
      const div=document.createElement('div'); div.className='beatBox'; div.dataset.abs=String(abs);
      div.addEventListener('click', ev=>{
        ev.stopPropagation(); div.classList.toggle('sel');
        Sidebar.rebuild(S, Cursor.setNoteHighlight);
      });
      const pad=2;
      div.style.left=(Math.round(box.left)+pad)+'px';
      div.style.top=(Math.round(box.top)+pad)+'px';
      div.style.width=Math.max(0, Math.round(box.right-box.left)-pad*2)+'px';
      div.style.height=Math.max(0, Math.round(box.bottom-box.top)-pad*2)+'px';
      frame.appendChild(div); S.beatDivs.push(div);
    }
    this._updateBeatVisibility();
  }

  _compute(absIdx, t, dur){
    const S=this.state;
    const box=S.boxesByAbs[absIdx]; if(!box) return null;
    const D=Math.max(1e-6,dur), tt=Math.max(0,Math.min(D,t));
    const xs=S.anchorsByAbs[absIdx]||[];
    const [xL,xR]=Geom.span(xs, box);
    let x_lin = Geom.lerp(xL,xR, tt/D);

    const ts=S.boot.NOTE_TIMES_MAP[absIdx]||[];
    const [k,dT]=Cursor.nearest(ts, tt);
    if(k>=0 && xs.length){
      if(dT<=this.SNAP_T) x_lin = xs[Math.min(k,xs.length-1)];
      else if(dT<=this.NUDGE_T){
        const w=this.NUDGE_GAIN*(1-dT/this.NUDGE_T), xn=xs[Math.min(k,xs.length-1)];
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
      if(r){ const [x,box,tt]=r; Cursor.placeCursorAt(x,box); Cursor.placeHL(box);
        this.state.lastHL=a; this.state.last={page:this.state.pageIndex,abs:a,t:tt,x:x}; }
    }
  }
}
