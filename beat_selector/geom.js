import { Dom } from './dom.js';
import { rectRel, midX } from './utils.js';

export class Geom {
  static span(xs, box){
    if(xs.length>=2) return [xs[0], xs[xs.length-1]];
    if(xs.length===1){
      const pad=Math.max(12,(box.right-box.left)*0.08);
      return [xs[0]-pad*0.5, xs[0]+pad*0.5];
    }
    const pad=(box.right-box.left)*0.08;
    return [box.left+pad, box.right-pad];
  }
  static lerp(a,b,u){ return a + Math.max(0,Math.min(1,u))*(b-a); }

  static scanMeasures(state){
    const svg = Dom.svgRoot(); if(!svg) return;
    const R = svg.getBoundingClientRect();
    state.boxesByAbs={}; state.anchorsByAbs={}; state.orderAbs=[];

    let groups=[...svg.querySelectorAll('[data-vrv-type="measure"]')];
    if(groups.length===0) groups=[...svg.querySelectorAll('g.measure,[class*="measure"]')];

    const n=Math.min(groups.length, state.boot.ABS_INDEXES.length);
    for(let i=0;i<n;i++){
      const abs=state.boot.ABS_INDEXES[i], g=groups[i];

      // full measure -> shrink to staff verticals
      let box=rectRel(g,R);
      const staffEls=g.querySelectorAll('[data-vrv-type="staff"], .staff');
      let top=Infinity,bottom=-Infinity;
      staffEls.forEach(el=>{
        const rr=rectRel(el,R);
        top=Math.min(top, rr.top); bottom=Math.max(bottom, rr.bottom);
      });
      if(isFinite(top)&&isFinite(bottom)){ box.top=top-4; box.bottom=bottom+4; }

      // anchors from notes
      const cand=g.querySelectorAll('[data-vrv-type="note"], g.note, .note, use[href*="note"]');
      const xs=[];
      cand.forEach(el=>{
        const rr=el.getBoundingClientRect();
        if(rr && isFinite(rr.left) && isFinite(rr.right))
          xs.push(midX(rectRel(el,R)));
      });
      xs.sort((a,b)=>a-b);
      const filtered=[];
      for(const x of xs){ if(!filtered.length || Math.abs(filtered[filtered.length-1]-x)>2) filtered.push(x); }

      // shrink width to anchors
      if(filtered.length){
        const padX=Math.max(10,(box.right-box.left)*0.05);
        box.left=filtered[0]-padX; box.right=filtered[filtered.length-1]+padX;
      }

      state.boxesByAbs[abs]=box;
      state.anchorsByAbs[abs]=filtered;
      state.orderAbs.push(abs);
    }
    state.readySvg=true;
    Dom.hud().textContent = `page=${state.pageIndex} measures=${state.orderAbs.length}`;
  }
}
