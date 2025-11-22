from __future__ import annotations
import json

_HTML = r"""
<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<style>
  :root { --hl-fill: rgba(56,189,248,0.12); --hl-stroke: rgba(2,132,199,0.90); }
  html, body { margin:0; padding:0; height:100%; background:#fff; }
  #frame { position:relative; width:100%; height:100vh; overflow:hidden; background:#fff; display:flex; }
  #scorePane{ position:relative; flex:1 1 auto; height:100%; }
  #side{ width:280px; max-width:33vw; border-left:1px solid #e5e7eb; background:#fafafa; overflow:auto; font:13px/1.3 system-ui; }
  #side h3{ margin:8px 8px 4px; font:600 13px system-ui; color:#0b3a53; }
  #side .beat{ margin:6px; padding:6px; border:1px solid #dbeafe; background:#eff6ff; border-radius:6px; }
  #side .note{ margin:4px 0; padding:4px 6px; border-radius:4px; cursor:pointer; }
  #side .note:hover{ background:#e2e8f0; }
  #side .note.note-hl { background:#dbeafe; outline:1px solid #60a5fa; }
  .note-hl path, .note-hl ellipse, .note-hl circle { fill:#2563eb !important; stroke:#1e40af !important; }
  object, svg { display:block; width:100%; height:100%; background:#fff !important; }
  .beat-box { position:absolute; top:0; background: rgba(2, 132, 199, 0.10);
    border-left: 1px solid rgba(2, 132, 199, 0.35);
    border-right: 1px solid rgba(2, 132, 199, 0.35);
    pointer-events:auto; cursor:pointer; z-index:20; }
  .beat-box.sel { background: rgba(2, 132, 199, 0.24); outline:1px solid rgba(2,132,199,0.90); outline-offset:-1px; }
  .beat-box:hover::after { content: attr(data-label); position:absolute; top:4px; right:4px; font:11px/1.1 system-ui;
    color:#0b3a53; background:rgba(255,255,255,0.9); border:1px solid rgba(2,132,199,.35); padding:2px 4px; border-radius:4px; }
  #hud { position:absolute; right:8px; top:8px; color:#fff; font:12px/1.3 system-ui;
         background:rgba(0,0,0,.55); padding:6px 8px; border-radius:6px; z-index:30; }
</style></head>
<body>
  <div id="frame">
    <div id="scorePane">
      <object id="page" type="image/svg+xml" data="{SVG_URL}"></object>
      <div id="hud">loading…</div>
    </div>
    <aside id="side"><h3>Selected beats</h3><div id="list"></div></aside>
  </div>
<script>
  (function(){
    const obj = document.getElementById('page');
    const initial = "{SVG_URL}";
    obj.addEventListener('load', function onLoad(){
      obj.removeEventListener('load', onLoad);
      buildBeatBoxes();
    }, {once:true});
    obj.data = (initial.indexOf('?')===-1 ? initial+'?ts='+Date.now() : initial);
  })();

  const ABS_INDEXES    = {ABS_INDEXES_JSON};
  const NOTE_TIMES_MAP = {NOTE_TIMES_MAP_JSON};
  const PITCH_MAP = {PITCH_MAP_JSON};

  // ---- Helpers for mapping labels to visual notes ----
  function pitchNameToMidi(name){
    // Accept forms like C4, C#4, C♯4, Db3, D♭3
    if (!name) return null;
    const m = String(name).trim().match(/^([A-Ga-g])([#♯b♭]?)(-?\d+)$/);
    if (!m) return null;
    const base = m[1].toUpperCase();
    const acc  = m[2];
    const oct  = parseInt(m[3], 10);
    const baseMap = {C:0,D:2,E:4,F:5,G:7,A:9,B:11};
    let semis = baseMap[base];
    if (acc === '#' || acc === '♯') semis += 1;
    if (acc === 'b' || acc === '♭') semis -= 1;
    return (oct + 1) * 12 + ((semis % 12) + 12) % 12;
  }

  function mapLabelsToNotesByY(notes, labs){
    // notes: array of DOM nodes (g.note), labs: array of pitch names from PITCH_MAP
    if (!labs || labs.length === 0) return Array(notes.length).fill(null);
    const noteYs = notes.map((n, i)=>({i, y: (n.getBoundingClientRect().top + n.getBoundingClientRect().bottom)/2}));
    noteYs.sort((a,b)=> a.y - b.y); // top (small y) to bottom (large y)

    const labMs = labs.map((L, j)=>({j, L, m: pitchNameToMidi(L)}))
                      .filter(x=>x.m!==null)
                      .sort((a,b)=> b.m - a.m); // high pitch first

    if (labMs.length === 0) return Array(notes.length).fill(null);

    const out = Array(notes.length).fill(null);
    // If counts match, map 1:1 by rank
    if (labMs.length === noteYs.length){
      for (let k=0; k<noteYs.length; k++){
        out[noteYs[k].i] = labMs[k].L;
      }
      return out;
    }
    // Otherwise, scale indices so every visual note gets a nearby ranked label
    for (let k=0; k<noteYs.length; k++){
      const idx = Math.round(k * (labMs.length - 1) / Math.max(1, noteYs.length - 1));
      out[noteYs[k].i] = labMs[idx].L;
    }
    return out;
  }

  const SELECTED = new Set();

  function svgDoc(){ const o=document.getElementById('page'); try{ return o.contentDocument; }catch(e){ return null; } }
  function svgRoot(){ const d=svgDoc(); return d? d.querySelector('svg') : null }

  function _rectRel(node, rootRect){
    const r=node.getBoundingClientRect();
    return {left:r.left-rootRect.left, right:r.right-rootRect.left, top:r.top-rootRect.top, bottom:r.bottom-rootRect.top};
  }

  function beatsInMeasure(g, lastSeen){
    const tsg = g.querySelector('g[data-vrv-type="timeSig"], g.timeSig, .timeSig');
    if (tsg){
      const t = (tsg.textContent||'').replace(/\s+/g,'');
      if (/^\d+\/\d+$/.test(t)) return Math.max(1, Math.min(parseInt(t.split('/')[0],10)||4, 12));
      if (/^[0-9]{2,}$/.test(t)){ const num=parseInt(t.slice(0,Math.floor(t.length/2)),10); if(num>0) return Math.min(num,12); }
      if (/^C$/.test(t)) return 4;
      if (/[¢]/.test(t)) return 2;
    }
    return lastSeen || 4;
  }

  function midiToPitch(m){
    const names = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
    const n = Math.round(Number(m)||0);
    const name = names[(n%12+12)%12];
    const oct = Math.floor(n/12) - 1;
    return name + oct;
  }
  function pnameAccidOctToPitch(pname, accid, oct){
    if (!pname) return null;
    const base = String(pname).toUpperCase();
    const acc = (accid||'').replace('s','♯').replace('f','♭').replace('#','♯');
    return base + acc + (oct!==undefined && oct!==null ? String(oct) : '');
  }

  // ---- Robust pitch extraction (non-breaking for selection) ----
  function readPitchFromAttrs(n){
    if (!n || !n.getAttribute) return null;
    const pn = n.getAttribute('data-pname') || n.getAttribute('pname');
    const ac = n.getAttribute('data-accid') || n.getAttribute('accid');
    const oc = n.getAttribute('data-oct')   || n.getAttribute('oct');
    const md = n.getAttribute('data-midi')  || n.getAttribute('midi');
    if (pn) return pnameAccidOctToPitch(pn, ac, oc);
    if (md) return midiToPitch(md);
    return null;
  }
  function getNoteLabel(node){
    // 1) on the node
    let lab = readPitchFromAttrs(node);
    if (lab) return lab;

    // 2) quick descendant
    const quick = node.querySelector('[data-pname],[pname],[data-midi],[midi]');
    if (quick){ lab = readPitchFromAttrs(quick); if (lab) return lab; }

    // 3) bounded BFS (≤200 descendants)
    const queue = Array.from(node.children || []);
    let seen = 0;
    while (queue.length && seen < 200){
      const n = queue.shift(); seen++;
      lab = readPitchFromAttrs(n); if (lab) return lab;
      if (n && n.children && n.children.length){
        for (const c of n.children) queue.push(c);
      }
    }

    // 4) up to 3 ancestors (covers chord/voice containers)
    let p = node.parentElement;
    for (let i=0; i<3 && p; i++, p=p.parentElement){
      lab = readPitchFromAttrs(p); if (lab) return lab;
      const sib = p.querySelector && p.querySelector('[data-pname],[pname],[data-midi],[midi]');
      if (sib){ lab = readPitchFromAttrs(sib); if (lab) return lab; }
    }
    return null;
  }


  function eachDrawable(node, fn){
    const tags = ['path','ellipse','circle','rect','polygon','polyline','use'];
    if (node.tagName && tags.includes(node.tagName.toLowerCase())) fn(node);
    node.querySelectorAll(tags.join(',')).forEach(fn);
  }
  function applyDirectHighlight(node, on=true){
    eachDrawable(node, (el)=>{
      if (on){
        if (!el.hasAttribute('data-prev-fill'))   el.setAttribute('data-prev-fill',   el.style.fill   || '');
        if (!el.hasAttribute('data-prev-stroke')) el.setAttribute('data-prev-stroke', el.style.stroke || '');
        el.style.fill   = '#2563eb';
        el.style.stroke = '#1e40af';
      }else{
        const prevF = el.getAttribute('data-prev-fill');
        const prevS = el.getAttribute('data-prev-stroke');
        el.style.fill   = prevF || '';
        el.style.stroke = prevS || '';
      }
    });
  }

  function svgRootRect(){ const svg = svgRoot(); return svg? svg.getBoundingClientRect() : null }

  function measureGroupByAbs(absIdx){
    const svg = svgRoot(); if(!svg) return null;
    let groups=[...svg.querySelectorAll('[data-vrv-type="measure"]')];
    if(groups.length===0) groups=[...svg.querySelectorAll('g.measure,[class*="measure"]')];
    const i = ABS_INDEXES.indexOf(absIdx);
    if (i<0 || i>=groups.length) return null;
    return groups[i];
  }

  function beatBoxBounds(absIdx, beatNumber){
    const svg = svgRoot(); const R = svgRootRect(); if(!svg||!R) return null;
    let groups=[...svg.querySelectorAll('[data-vrv-type="measure"]')];
    if(groups.length===0) groups=[...svg.querySelectorAll('g.measure,[class*="measure"]')];
    const i = ABS_INDEXES.indexOf(absIdx);
    if (i<0 || i>=groups.length) return null;
    const g = groups[i];
    const rr = _rectRel(g, R);
    const beats = beatsInMeasure(g, 4);
    const b = Math.max(1, Math.min(beats, beatNumber)) - 1;
    const width=Math.max(1, rr.right - rr.left);
    const L = rr.left + (b/beats)*width;
    const Rr= rr.left + ((b+1)/beats)*width;
    return {left:L, right:Rr, top:rr.top, bottom:rr.bottom};
  }

  function noteGroupsWithin(g, leftPx, rightPx){
    const candidates = g.querySelectorAll('[data-vrv-type="note"], g.note, g.chord g.note');
    const arr=[];
    candidates.forEach(n=>{
      const r = n.getBoundingClientRect();
      const cx = (r.left + r.right)/2;
      if (cx>=leftPx && cx<=rightPx) arr.push(n);
    });
    arr.sort((a,b)=>a.getBoundingClientRect().left - b.getBoundingClientRect().left);
    return arr;
  }

  function clearAllNoteHighlights(){
    const svg = svgRoot(); if(!svg) return;
    svg.querySelectorAll('.note-hl').forEach(n=>{
      n.classList.remove('note-hl');
      applyDirectHighlight(n, false);
    });
  }
  function highlightOneNote(el, on=true){
    if (!el) return;
    if (on){ el.classList.add('note-hl'); applyDirectHighlight(el, true); }
    else   { el.classList.remove('note-hl'); applyDirectHighlight(el, false); }
  }

  function buildSidebar(){
    try{
      const list = document.getElementById('list');
      list.innerHTML = '';
      const ordered = Array.from(SELECTED).sort((a,b)=>{
        const [am,ab]=a.split('-').map(Number); const [bm,bb]=b.split('-').map(Number);
        return am===bm ? (ab-bb) : (am-bm);
      });
      ordered.forEach(key=>{
        const labelsFromMapRaw = (PITCH_MAP[String(absIdx)] && PITCH_MAP[String(absIdx)][String(beatNo)]) ||
                                 (PITCH_MAP[absIdx] && PITCH_MAP[absIdx][beatNo]) || [];
        const labelsByRank = mapLabelsToNotesByY(notes, labelsFromMapRaw);

        const [absIdx, beatNo] = key.split('-').map(Number);
        const g = measureGroupByAbs(absIdx); if(!g) return;
        const bb = beatBoxBounds(absIdx, beatNo); if(!bb) return;
        const notes = noteGroupsWithin(g, bb.left, bb.right);

        let labeled=0, unlabeled=0;
        const wrap = document.createElement('div'); wrap.className='beat';
        const title = document.createElement('div'); wrap.appendChild(title);

        notes.forEach((node, i)=>{
          const item = document.createElement('div'); item.className='note';
          let lab = getNoteLabel(node);
          if (!lab) {
            lab = labelsByRank[i] || null;
          }

          if (lab) labeled++; else unlabeled++;
          item.textContent = lab ? lab : `Note ${i+1}`;
          item.addEventListener('click', (ev)=>{
            ev.preventDefault(); ev.stopPropagation();
            const turnOn = !node.classList.contains('note-hl');
            highlightOneNote(node, turnOn);
            item.classList.toggle('note-hl', turnOn);
          });
          wrap.appendChild(item);
        });

        title.textContent = `m${absIdx} • beat ${beatNo} — ${notes.length} notes (labels: ${labeled}/${notes.length})`;
        if (unlabeled>0){
          console.warn(`[BeatSelector] missing labels on m${absIdx} beat ${beatNo}; unlabeled=${unlabeled}`);
        }
        document.getElementById('list').appendChild(wrap);
      });
    }catch(e){
      console.error('[BeatSelector] buildSidebar error:', e);
    }
  }

  function publishSelection(){
    const arr = Array.from(SELECTED);
    arr.sort((a,b)=>{
      const [am,ab]=a.split('-').map(Number); const [bm,bb]=b.split('-').map(Number);
      return am===bm ? (ab-bb) : (am-bm);
    });
    document.title = 'BEATS:' + JSON.stringify(arr);
    buildSidebar();
  }

  function clearBeatBoxes(){
    const frame = document.getElementById('frame');
    frame.querySelectorAll('.beat-box').forEach(n=>n.remove());
  }

  function buildBeatBoxes(){
    const svg = svgRoot(); const R = svgRootRect(); if(!svg||!R) return;
    const frame = document.getElementById('frame');
    clearBeatBoxes();

    let groups=[...svg.querySelectorAll('[data-vrv-type="measure"]')];
    if(groups.length===0) groups=[...svg.querySelectorAll('g.measure,[class*="measure"]')];
    const n=Math.min(groups.length, ABS_INDEXES.length);
    let lastBeats=4;
    for (let i=0;i<n;i++){
      const absIdx = ABS_INDEXES[i], g=groups[i];
      const rr = _rectRel(g, R);
      const beats = (lastBeats = beatsInMeasure(g, lastBeats));
      const width=Math.max(1, rr.right - rr.left), height=Math.max(0, rr.bottom - rr.top);
      for (let b=0;b<beats;b++){
        const L = rr.left + (b/beats)*width;
        const Rr= rr.left + ((b+1)/beats)*width;

        const key = `${absIdx}-${b+1}`;
        const box = document.createElement('div');
        box.className = 'beat-box' + (SELECTED.has(key) ? ' sel' : '');
        box.style.left   = `${L}px`;
        box.style.top    = `${rr.top}px`;
        box.style.width  = `${Math.max(0,Rr-L)}px`;
        box.style.height = `${height}px`;
        box.dataset.label = `m${absIdx} • beat ${b+1}/${beats}`;

        box.addEventListener('click', ev=>{
          ev.preventDefault(); ev.stopPropagation();
          if (SELECTED.has(key)){ SELECTED.delete(key); box.classList.remove('sel'); }
          else { SELECTED.add(key); box.classList.add('sel'); }
          publishSelection();
        }, {passive:false});

        frame.appendChild(box);
      }
    }
    document.getElementById('hud').textContent = `measures on page: ${n}`;
    publishSelection();
    buildSidebar();
  }

  function setPageSvg(svgUrl){
    const obj = document.getElementById('page');
    obj.addEventListener('load', function onLoad(){
      obj.removeEventListener('load', onLoad);
      buildBeatBoxes();
    }, {once:true});
    obj.data = (svgUrl.indexOf('?')===-1 ? svgUrl+'?ts='+Date.now() : svgUrl);
  }

  window.addEventListener('resize', ()=>{ if(svgRoot()) buildBeatBoxes(); });
</script>
</body></html>
"""

def render_html(svg_url: str, abs_indexes, note_times_map, pitch_map_page) -> str:
    return (_HTML
            .replace("{ABS_INDEXES_JSON}", json.dumps(abs_indexes))
            .replace("{NOTE_TIMES_MAP_JSON}", json.dumps(note_times_map))
            .replace("{PITCH_MAP_JSON}", json.dumps(pitch_map_page))
            .replace("{SVG_URL}", svg_url))
