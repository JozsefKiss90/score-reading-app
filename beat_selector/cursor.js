import { Dom } from './dom.js';

export class Cursor {
  static eachDrawable(node, fn){
    const tags=["path","ellipse","circle","rect","polygon","polyline","use"];
    if(node.tagName && tags.includes(node.tagName.toLowerCase())) fn(node);
    node.querySelectorAll(tags.join(",")).forEach(fn);
  }
  static setNoteHighlight(node, on=true){
    if(!node) return;
    Cursor.eachDrawable(node, el=>{
      if(on){
        if(!el.hasAttribute("data-prev-fill"))   el.setAttribute("data-prev-fill", el.style.fill||"");
        if(!el.hasAttribute("data-prev-stroke")) el.setAttribute("data-prev-stroke", el.style.stroke||"");
        el.style.fill="#2563eb"; el.style.stroke="#1e40af";
      }else{
        el.style.fill = el.getAttribute("data-prev-fill")||"";
        el.style.stroke=el.getAttribute("data-prev-stroke")||"";
      }
    });
    if(on) node.classList.add("note-hl"); else node.classList.remove("note-hl");
  }
  static nearest(ts,t){
    if(!ts?.length) return [-1,1e9];
    let lo=0, hi=ts.length-1;
    while(lo<hi){ const m=(lo+hi)>>1; if(ts[m]<t) lo=m+1; else hi=m; }
    let idx=lo, d=Math.abs(ts[idx]-t);
    if(idx>0 && Math.abs(ts[idx-1]-t)<d){ idx-=1; d=Math.abs(ts[idx]-t); }
    return [idx,d];
  }
  static placeCursorAt(x, box){
    const c=Dom.cursor();
    c.style.left=`${x}px`; c.style.top=`${box.top}px`; c.style.height=`${box.bottom-box.top}px`;
  }
  static placeHL(box){
    const hl=Dom.barHL(), pad=2;
    hl.style.left=`${box.left+pad}px`; hl.style.top=`${box.top+pad}px`;
    hl.style.width=`${Math.max(0,(box.right-box.left)-pad*2)}px`;
    hl.style.height=`${Math.max(0,(box.bottom-box.top)-pad*2)}px`;
  }
}
