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

  // Highlight pitch labels in the sidebar when their corresponding noteheads
  // are highlighted in the SVG with .midi-ok.
  static updateMidiOk(state){
    const list = Dom.beatList();
    if(!list) return;

    // Clear existing label highlights
    list.querySelectorAll('.noteItem.midi-ok').forEach(el => el.classList.remove('midi-ok'));

    // Preferred: use the ids that App actually painted green
    const activeIds = new Set();
    if(state?.midiActiveIdsByMidi && typeof state.midiActiveIdsByMidi.values === 'function'){
      for(const s of state.midiActiveIdsByMidi.values()){
        if(!s) continue;
        for(const id of s) activeIds.add(String(id));
      }
    }

    // Fallback: derive from held keys + selected mapping
    if(activeIds.size === 0 && state?.midiDown && state?.selNotesByMidi){
      for(const midi of state.midiDown.values()){
        const ids = state.selNotesByMidi.get(midi);
        if(!ids) continue;
        for(const id of ids) activeIds.add(String(id));
      }
    }

    if(activeIds.size === 0) return;

    list.querySelectorAll('.noteItem[data-note-id]').forEach(el => {
      const id = String(el.dataset.noteId || '');
      if(id && activeIds.has(id)) el.classList.add('midi-ok');
    });
  }

  // Sidebar selection is BEAT-based: selecting a beat implicitly selects
  // *all* notes in that beat for MIDI highlighting.
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

    const selNoteIds = new Set();
    const selByMidi = new Map();

    const addSelMidi = (midi, id) => {
      if(midi === null || midi === undefined) return;
      let s = selByMidi.get(midi);
      if(!s){ s = new Set(); selByMidi.set(midi, s); }
      s.add(String(id));
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

          // Beat selection implies selecting all notes in the beat.
          if(id){
            selNoteIds.add(id);
            if(midi !== null && midi !== undefined) addSelMidi(midi, id);
          }

          wrap.appendChild(item);
        });
      }

      list.appendChild(wrap);
    }

    // Update selection sets used by App for MIDI mapping.
    state.selNoteIds = selNoteIds;
    state.selNotesByMidi = selByMidi;

    // Apply blue highlight to all selected notes (i.e., notes in selected beats).
    for(const id of state.selNoteIds){
      const node = svg.ownerDocument.getElementById(id);
      if(node) onHighlight(node, true);
    }

    // Keep sidebar pitch labels in sync with current MIDI-highlighted notes.
    Sidebar.updateMidiOk(state);

    if(typeof onSelectionChanged === 'function') onSelectionChanged();
  }
}
