import { Dom } from './dom.js';

export class Sidebar {
  static _asciiPitch(s){
    return (s || '')
      .toString()
      .trim()
      .replace(/♯/g, '#')
      .replace(/♭/g, 'b');
  }

  // Normalized display form, e.g. "bb3" -> "Bb3", "F♯4" -> "F#4"
  static normPitch(s){
    const t = Sidebar._asciiPitch(s);
    const m = /^([A-Ga-g])([#b]{0,2})(-?\d+)$/.exec(t);
    if(!m) return t;
    return m[1].toUpperCase() + (m[2] || '') + m[3];
  }

  static pitchToMidi(pitch){
    const t = Sidebar._asciiPitch(pitch);
    const m = /^([A-Ga-g])([#b]{0,2})(-?\d+)$/.exec(t);
    if(!m) return null;

    const pc = m[1].toUpperCase();
    const acc = m[2] || '';
    const oct = parseInt(m[3], 10);

    const base = { C:0, D:2, E:4, F:5, G:7, A:9, B:11 }[pc];
    const delta = (acc.match(/#/g)||[]).length - (acc.match(/b/g)||[]).length;
    const semitone = base + delta;
    return (oct + 1) * 12 + semitone;
  }

  static rebuild(state, onHighlight, onSelectionChanged){
    const list = Dom.beatList();
    if(!list) return;
    list.innerHTML = '';

    const svg = Dom.svgRoot();
    if(!svg) return;

    // Clear previous selection highlight (blue). MIDI highlight (green) is managed by App.
    svg.querySelectorAll('.note-hl').forEach(n => n.classList.remove('note-hl'));

    // Collect selected beats: abs -> [beatIdx...]
    const byAbs = new Map();
    if(state.selBeats && typeof state.selBeats.entries === 'function'){
      for(const [abs, set] of state.selBeats.entries()){
        const beats = [...set].map(Number);
        if(beats.length) byAbs.set(Number(abs), beats);
      }
    } else {
      // Back-compat with older DOM-based beat selection.
      const hits = [...document.querySelectorAll('.beatHit.sel, .beatBox.sel')];
      for(const h of hits){
        const abs = Number(h.dataset.abs);
        const beat = Number(h.dataset.beat || 1);
        if(!byAbs.has(abs)) byAbs.set(abs, []);
        byAbs.get(abs).push(beat);
      }
    }

    // Prune old note selection to only notes still visible in the sidebar after rebuild.
    const oldSel = state.selNoteIds || new Set();
    const newSel = new Set();
    const selByMidi = new Map();

    const addSelMidi = (midi, id) => {
      if(midi === null || midi === undefined) return;
      let s = selByMidi.get(midi);
      if(!s){ s = new Set(); selByMidi.set(midi, s); }
      s.add(id);
    };

    for(const [abs, beats] of byAbs.entries()){
      const wrap = document.createElement('div');
      wrap.className = 'beatEntry';

      const head = document.createElement('div');
      head.className = 'beatTitle';
      const uniq = [...new Set(beats)].sort((a,b)=>a-b);
      head.textContent = `m${abs} • ${uniq.length} beat${uniq.length===1?'':'s'} selected`;
      wrap.appendChild(head);

      for(const beat of uniq){
        const sub = document.createElement('div');
        sub.className = 'beatSubTitle';

        const raw = (state.boot.PITCH_MAP?.[String(abs)]?.[String(beat)]) || [];
        const rows = Array.isArray(raw) ? raw : [];
        sub.textContent = `beat ${beat} — ${rows.length} notes`;
        wrap.appendChild(sub);

        rows.forEach((r, i) => {
          const id = r?.id ? String(r.id) : null;
          const pitch = r?.pitch ? Sidebar.normPitch(r.pitch) : null;
          const midi = pitch ? Sidebar.pitchToMidi(pitch) : null;

          const item = document.createElement('div');
          item.className = 'noteItem';
          item.textContent = pitch || `Note ${i+1}`;
          if(id) item.dataset.noteId = id;
          if(midi !== null && midi !== undefined) item.dataset.midi = String(midi);

          const isSel = !!(id && oldSel.has(id));
          if(isSel){
            item.classList.add('sel');
            newSel.add(id);
            if(midi !== null && midi !== undefined) addSelMidi(midi, id);
          }

          item.addEventListener('click', (ev) => {
            ev.stopPropagation();
            if(!id) return;

            const on = !item.classList.contains('sel');
            item.classList.toggle('sel', on);

            // Update selection sets
            if(on) state.selNoteIds.add(id);
            else state.selNoteIds.delete(id);

            // Blue selection highlight
            const node = svg.ownerDocument.getElementById(id);
            if(node) onHighlight(node, on);

            // Maintain midiPitch -> selected note ids
            if(midi !== null && midi !== undefined){
              let set = state.selNotesByMidi.get(midi);
              if(on){
                if(!set){ set = new Set(); state.selNotesByMidi.set(midi, set); }
                set.add(id);
              } else if(set){
                set.delete(id);
                if(set.size === 0) state.selNotesByMidi.delete(midi);
              }
            }

            if(typeof onSelectionChanged === 'function') onSelectionChanged();
          });

          wrap.appendChild(item);
        });
      }

      list.appendChild(wrap);
    }

    state.selNoteIds = newSel;
    state.selNotesByMidi = selByMidi;

    // Apply blue highlight after rebuild.
    for(const id of state.selNoteIds){
      const node = svg.ownerDocument.getElementById(id);
      if(node) onHighlight(node, true);
    }

    if(typeof onSelectionChanged === 'function') onSelectionChanged();
  }
}
