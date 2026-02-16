import { Dom } from './dom.js';

const BLACK_PCS = new Set([1, 3, 6, 8, 10]); // C#, D#, F#, G#, A#
const NAMES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"];

function pc(m){ return ((m % 12) + 12) % 12; }
function isBlack(m){ return BLACK_PCS.has(pc(m)); }
function midiToName(m){
  const name = NAMES[pc(m)];
  const oct = Math.floor(m / 12) - 1;
  return `${name}${oct}`;
}

// Defaults are irrelevant because you pass opts, but keep sane.
const DEFAULT_MIN = 36; // C2
const DEFAULT_MAX = 96; // C7 (61 keys total for 36..96 inclusive)

export class KeyboardView {
  constructor(state, opts = {}){
    this.state = state;

    // New, backward compatible host resolution:
    this.el =
      opts.hostEl ||
      (opts.hostId ? Dom.keyboard(opts.hostId) : null) ||
      Dom.keyboard();

    this.minMidi = Number.isFinite(opts.minMidi) ? opts.minMidi : DEFAULT_MIN;
    this.maxMidi = Number.isFinite(opts.maxMidi) ? opts.maxMidi : DEFAULT_MAX;
    this.showLabels = !!opts.showLabels;

    this._keysByMidi = new Map();
    this._whiteMidis = [];
    this._blackMidis = [];

    this._build();
    window.addEventListener('resize', () => this.layout());
    this.layout();
  }

  _build(){
    const root = this.el;
    if(!root) return;
    root.innerHTML = '';

    this._keysByMidi.clear();
    this._whiteMidis = [];
    this._blackMidis = [];

    // Build midi range
    for(let m = this.minMidi; m <= this.maxMidi; m++){
      if(isBlack(m)) this._blackMidis.push(m);
      else this._whiteMidis.push(m);
    }

    // White keys first (background)
    for(const m of this._whiteMidis){
      const k = document.createElement('div');
      k.className = 'keyW';
      k.dataset.midi = String(m);
      k.dataset.note = midiToName(m);
      k.dataset.pc   = String(pc(m));
      k.dataset.oct  = String(Math.floor(m / 12) - 1);
      k.setAttribute('aria-label', midiToName(m));

      if (this.showLabels) {
        const lbl = document.createElement('div');
        lbl.className = 'keyLbl';
        lbl.textContent = midiToName(m);
        k.appendChild(lbl);
      }


      root.appendChild(k);
      this._keysByMidi.set(m, k);
    }

    // Black keys on top (overlay)
    for(const m of this._blackMidis){
      const k = document.createElement('div');
      k.className = 'keyB';
      k.dataset.midi = String(m);

      if(this.showLabels){
        const lbl = document.createElement('div');
        lbl.className = 'keyLbl keyLblB';
        lbl.textContent = midiToName(m);
        k.appendChild(lbl);
      }

      root.appendChild(k);
      this._keysByMidi.set(m, k);
    }
  }

  // Add inside KeyboardView class

setPcHighlights({ pcs = [], okPcs = [], badPcs = [], heldMidis = null } = {}) {
  this._clearAllState();

  const pcsSet    = new Set(pcs);
  const okSet     = new Set(okPcs);
  const badSet    = new Set(badPcs);
  const heldSet   = heldMidis instanceof Set ? heldMidis : new Set(heldMidis || []);

  // Walk every rendered key; decide state by PC membership.
  for (const [midi, el] of this._keysByMidi.entries()) {
    const p = ((midi % 12) + 12) % 12;

    // If pcs filter is given, only render those pitch-classes
    if (pcsSet.size && !pcsSet.has(p)) continue;

    const black = BLACK_PCS.has(p);

    // Priority: held > ok > bad > neutral (neutral = no class)
    if (heldSet.has(midi)) {
      el.classList.add(black ? "keyDownB" : "keyDownW");
    } else if (okSet.has(p)) {
      el.classList.add(black ? "keyOkB" : "keyOkW");
    } else if (badSet.has(p)) {
      el.classList.add(black ? "keyBadB" : "keyBadW");
    }
  }
}

layout(){
  const root = this.el;
  if(!root) return;

  const whiteCount = Math.max(1, this._whiteMidis.length);

  // midi -> white index
  const whiteIndex = new Map();
  this._whiteMidis.forEach((m, i) => whiteIndex.set(m, i));

  // Use percentages to avoid cumulative rounding drift
  const wPct = 100 / whiteCount;

  // White keys
  for(const m of this._whiteMidis){
    const i = whiteIndex.get(m);
    const k = this._keysByMidi.get(m);
    k.style.left  = `${i * wPct}%`;
    k.style.width = `${wPct}%`;
  }

  // Black keys
  const bwPct = wPct * 0.62;
  const halfPct = bwPct / 2;

  for(const m of this._blackMidis){
    const k = this._keysByMidi.get(m);

    const leftWhiteMidi = m - 1;
    const li = whiteIndex.get(leftWhiteMidi);
    if(li === undefined){
      k.style.display = 'none';
      continue;
    }
    k.style.display = 'block';

    // center at the boundary between white li and li+1
    const xCenterPct = (li + 1) * wPct;
    k.style.left  = `${xCenterPct - halfPct}%`;
    k.style.width = `${bwPct}%`;
  }
}

  _clearAllState(){
    for(const el of this._keysByMidi.values()){
      el.classList.remove(
        'keyDownW','keyDownB',
        'keyOkW','keyOkB',
        'keyBadW','keyBadB'
      );
    }
  }

  /**
   * Update key states from MIDI.
   * - midiDownSet: Set of held midi pitches
   * - statusMap: Map<midi, 'ok'|'bad'> computed in app.js
   */
  setKeyStates(midiDownSet, statusMap){
    this._clearAllState();
    if(!midiDownSet) return;

    for(const midi of midiDownSet.values()){
      const el = this._keysByMidi.get(midi);
      if(!el) continue;

      const black = isBlack(midi);
      const st = statusMap?.get?.(midi) || null;

      if(st === 'ok'){
        el.classList.add(black ? 'keyOkB' : 'keyOkW');
      } else if(st === 'bad'){
        el.classList.add(black ? 'keyBadB' : 'keyBadW');
      } else {
        // fallback: held but unknown -> just show as held
        el.classList.add(black ? 'keyDownB' : 'keyDownW');
      }
    }
  }
}
