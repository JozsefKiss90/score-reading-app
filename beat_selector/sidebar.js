import { Dom } from './dom.js';

export class Sidebar {
  static normPitch(s) {
    return (s || "")
      .toString()
      .trim()
      .replace(/♯/g, "#")
      .replace(/♭/g, "b")
      .toUpperCase();
  }

  static readNodePitch(node) {
    if (!node) return null;

    const tryFrom = (el) => {
      if (!el) return null;
      const pname = el.getAttribute("data-pname");
      const accid = (el.getAttribute("data-accid") || "").toLowerCase();
      const oct   = el.getAttribute("data-oct");
      if (!pname || !oct) return null;

      const pc = pname.toString().toUpperCase();
      const acc =
        accid === "s" || accid === "sharp" ? "#" :
        accid === "f" || accid === "flat"  ? "b" :
        accid === "ss" || accid === "x" || accid === "2s" ? "##" :
        accid === "ff" || accid === "2f" ? "bb" : "";

      return pc + acc + oct;
    };

    // 1) Walk *up* the DOM for a few generations – Verovio often
    //    hangs the data-pname/accid/oct on a parent <g>.
    let el = node;
    for (let depth = 0; el && depth < 6; depth++) {
      const p = tryFrom(el);
      if (p) return p;
      el = el.parentElement;
    }

    // 2) Fallback: search all descendants for something pitch-like.
    for (const el2 of node.querySelectorAll("[data-pname]")) {
      const p = tryFrom(el2);
      if (p) return p;
    }

    return null;
  }

  static measureGroupByAbs(state, abs){
    const svg=Dom.svgRoot(); if(!svg) return null;
    let groups=[...svg.querySelectorAll('[data-vrv-type="measure"]')];
    if(groups.length===0) groups=[...svg.querySelectorAll('g.measure,[class*="measure"]')];
    const i=state.boot.ABS_INDEXES.indexOf(abs);
    if(i<0 || i>=groups.length) return null;
    return groups[i];
  }

  static noteGroupsWithin(g, L, R, includeRight=false){
    const nodes=g.querySelectorAll("[data-vrv-type='note'], g.note, g.chord g.note");
    const arr=[];
    nodes.forEach(n=>{
      const r=n.getBoundingClientRect();
      const cx=(r.left+r.right)/2;
      const inLeft=cx>=L, inRight=includeRight ? (cx<=R) : (cx<R);
      if(inLeft && inRight) arr.push(n);
    });
    arr.sort((a,b)=>a.getBoundingClientRect().left - b.getBoundingClientRect().left);
    return arr;
  }

  static beatIndexForBox(state, abs, boxRect){
    const xs=state.anchorsByAbs[abs]||[];
    if(!xs.length) return 1;
    const first=xs[0], last=xs[xs.length-1], span=Math.max(1,last-first);
    const beats=(state.boot.BEAT_TIMES_MAP[abs]?.length)||1;
    const cx=(boxRect.left+boxRect.right)/2;
    const u=Math.max(0, Math.min(0.9999, (cx-first)/span));
    return Math.max(1, Math.min(beats, Math.floor(u*beats)+1));
  }

  static rebuild(state, onHighlight){
    const list = Dom.beatList(); list.innerHTML="";
    const svg = Dom.svgRoot(); if(!svg) return;
    svg.querySelectorAll(".note-hl").forEach(n=> n.classList.remove("note-hl"));

    // Selection model:
    // - Score view uses ONE overlay per measure.
    // - Beats are inferred from click position and stored in state.selBeats.
    //   (Fallback to DOM selection if older builds still use .beatBox/.beatHit.)
    const byAbs=new Map();

    if(state.selBeats && typeof state.selBeats.entries === 'function'){
      for(const [abs, set] of state.selBeats.entries()){
        const beats=[...set].map(Number);
        if(beats.length) byAbs.set(Number(abs), beats);
      }
    } else {
      const hits=[...document.querySelectorAll(".beatHit.sel, .beatBox.sel")];
      for(const h of hits){
        const abs=Number(h.dataset.abs);
        const beat=Number(h.dataset.beat||1);
        if(!byAbs.has(abs)) byAbs.set(abs, []);
        byAbs.get(abs).push(beat);
      }
    }

    for(const [abs, beats] of byAbs.entries()){
      const wrap=document.createElement("div");
      wrap.className="beatEntry";

      const head=document.createElement("div");
      head.className="beatTitle";
      const uniq=[...new Set(beats)].sort((a,b)=>a-b);
      head.textContent = `m${abs} • ${uniq.length} beat${uniq.length===1?'':'s'} selected`;
      wrap.appendChild(head);

      // Render each selected beat as a subsection within the single measure entry
      for(const beat of uniq){
        const sub=document.createElement("div");
        sub.className="beatSubTitle";

        const raw = (state.boot.PITCH_MAP?.[String(abs)]?.[String(beat)]) || [];
        const rows = Array.isArray(raw) ? raw : [];
        sub.textContent = `beat ${beat} — ${rows.length} notes`;
        wrap.appendChild(sub);

        rows.forEach((r, i)=>{
          const item=document.createElement("div");
          item.className="noteItem";
          item.textContent = r?.pitch ? Sidebar.normPitch(r.pitch) : `Note ${i+1}`;

          item.addEventListener("click", (ev)=>{
            ev.stopPropagation();
            const on=!item.classList.contains("sel");
            item.classList.toggle("sel", on);

            const svg = Dom.svgRoot();
            if(!svg) return;
            const node = svg.getElementById ? svg.getElementById(r.id) : null;
            if(node) onHighlight(node, on);
            const livePitch = Sidebar.readNodePitch(node);
            const label = livePitch || r?.pitch || null;

            item.textContent = label ? Sidebar.normPitch(label) : `Note ${i+1}`;
          });
          wrap.appendChild(item);
        });
      }

      list.appendChild(wrap);
    }
  }
}
