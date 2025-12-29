export class State {
  constructor(boot){
    this.boot = boot;
    this.pageIndex = 0;
    this.readySvg  = false;

    this.boxesByAbs   = {};  // abs -> {l,r,t,b}
    this.anchorsByAbs = {};  // abs -> [x...]
    this.orderAbs     = [];  // visible order

    this.queued = null;      // pending cursor params
    this.last   = {page:-1, abs:-1, t:0, x:0};
    this.lastHL = -1;

    this.beatVisible = false;
    this.beatDivs = [];      // overlay divs

    /* ---------- harmonic / MIDI state ---------- */

    this.activeMidi = new Set();

    this.chordActiveWindowMs = 550;
    this._pcLastOnTs = new Array(12).fill(0);
    this._lastChordUpdateTs = 0;

    this.chord = null;
    this.tonicPc = null;
    this.function = null;
  }

  /* ============================================================
     Chord + function inference
     ============================================================ */

  activePitchClassesWithinWindow(nowTs) {
    const t = Number.isFinite(nowTs) ? nowTs : performance.now();
    const pcs = new Set();

    // Currently active notes
    for (const midi of this.activeMidi) {
      const pc = ((midi % 12) + 12) % 12;
      pcs.add(pc);
    }

    // Recently struck notes (rolled chords)
    const cutoff = t - this.chordActiveWindowMs;
    for (let pc = 0; pc < 12; pc++) {
      if ((this._pcLastOnTs[pc] || 0) >= cutoff) {
        pcs.add(pc);
      }
    }

    return [...pcs].sort((a,b)=>a-b);
  }

  _updateChordAndFunction(nowTs) {
    const t = Number.isFinite(nowTs) ? nowTs : performance.now();
    this._lastChordUpdateTs = t;

    // 1) infer chord
    const pcs = this.activePitchClassesWithinWindow(t);
    const chord = inferChordFromPitchClasses(pcs, {
      pcNames: PC_NAMES_SHARP,
      minPcs: 2
    });
    this.chord = chord;

    // 2) infer tonic from harmonic center-of-gravity
    const tonicPc = this._inferTonicPcFromCenter();
    this.tonicPc = tonicPc;

    // 3) infer function
    this.function = this._inferFunctionBadge(tonicPc, chord);
  }

  _inferTonicPcFromCenter() {
    const v = this.computeHarmonicCenterVec();
    if (!v || v.mag <= 0.08) return null;

    const ang = Math.atan2(v.uy, v.ux);
    let a = ang < 0 ? ang + Math.PI * 2 : ang;

    // invert render mapping
    let idxF = 12 * ((a + Math.PI / 2) / (Math.PI * 2));
    idxF = ((idxF % 12) + 12) % 12;
    const idx = Math.round(idxF) % 12;

    for (let pc = 0; pc < 12; pc++) {
      if (PC_TO_INDEX.get(pc) === idx) return pc;
    }
    return null;
  }

  _inferFunctionBadge(tonicPc, chord) {
    if (tonicPc == null || !chord) return null;

    const tonicIdx = pcToIndex(tonicPc);
    const rootIdx  = pcToIndex(chord.rootPc);
    if (tonicIdx == null || rootIdx == null) return null;

    let d = (rootIdx - tonicIdx);
    d = ((d + 6) % 12) - 6;   // wrap to [-6..+6]

    let badge = "X";
    if (Math.abs(d) <= 1) badge = "T";
    else if (d >= 2 && d <= 4) badge = "D";
    else if (d <= -2 && d >= -4) badge = "S";

    return {
      badge,
      tonicPc,
      distFifths: d,
      confidence: chord.confidence
    };
  }
}
