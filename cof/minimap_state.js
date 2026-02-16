// minimap_state.js
import { clamp } from "./utils.js";
import { PC_TO_INDEX, pcToIndex } from "./cof.js";
import { inferChordFromPitchClasses, PC_NAMES_SHARP } from "./chord.js";
import { buildMiddleRing } from "./middle_ring.js";
import { analyzeChordDiatonic } from "./diatonic_analyze.js";

export class MiniMapState {
  constructor(opts = {}) {
    // Active MIDI tracking
    this.activeMidi = new Set();
    this.lastPc = null;
    this.lastVel = 0;
    this.lastTs = 0;

    // Trail for successive pitch-class arrows
    this.pcTrail = [];
    this.pcTrailMax = Number.isFinite(opts.pcTrailMax) ? opts.pcTrailMax : 18;
    this.pcTrailWindowMs = Number.isFinite(opts.pcTrailWindowMs) ? opts.pcTrailWindowMs : 4500;
    this.ignoreRepeatedPc = (opts.ignoreRepeatedPc != null) ? !!opts.ignoreRepeatedPc : true;

    // Energy for harmonic center-of-gravity
    this.pcEnergy = new Array(12).fill(0);
    this.pcEnergyLastTs = 0;
    this.pcEnergyHalfLifeMs = Number.isFinite(opts.pcEnergyHalfLifeMs) ? opts.pcEnergyHalfLifeMs : 1800;
    this.energyBaseImpulse = Number.isFinite(opts.energyBaseImpulse) ? opts.energyBaseImpulse : 0.8;
    this.energyVelImpulse = Number.isFinite(opts.energyVelImpulse) ? opts.energyVelImpulse : 1.6;

    // Chord inference windowing
    this.chordActiveWindowMs = Number.isFinite(opts.chordActiveWindowMs) ? opts.chordActiveWindowMs : 550;
    this._pcLastOnTs = new Array(12).fill(0);
    this._lastChordUpdateTs = 0;

    // IMPORTANT: default FALSE so harmony reflects ONLY currently held notes.
    this.includeRecentStrikesForChord =
      (opts.includeRecentStrikesForChord != null) ? !!opts.includeRecentStrikesForChord : false;

    // Outputs
    this.chord = null;
    this.tonicPc = null;
    this.function = null;
    this.middleRing = null;
    this.chordDiatonic = null;

    // Keep opts for reset behavior if needed later
    this._opts = { ...opts };
  }

  /**
   * Hard reset: clears held notes, trail, harmonic energy accumulator, inferred chord/tonic/function,
   * and any "recent strikes" timestamps.
   */
  reset(ts = performance.now()) {
    const t = Number(ts ?? performance.now());

    // clear held notes & recent strikes
    this.activeMidi.clear();
    this._pcLastOnTs.fill(0);

    // clear visuals / accumulators
    this.pcTrail.length = 0;
    this.pcEnergy.fill(0);
    this.pcEnergyLastTs = t;

    // clear inference outputs
    this.chord = null;
    this.tonicPc = null;
    this.function = null;
    this.middleRing = null;
    this.chordDiatonic = null;

    // clear last-event info
    this.lastPc = null;
    this.lastVel = 0;
    this.lastTs = t;

    this._lastChordUpdateTs = t;
  }

  /**
   * "Panic" is a lighter reset that at least ensures no stuck notes drive harmony.
   * Use this if you want to keep the harmonic energy history but drop all held notes.
   */
  panic(ts = performance.now()) {
    const t = Number(ts ?? performance.now());
    this.activeMidi.clear();
    this.lastTs = t;
    this._updateChordAndFunction(t);
  }

  noteOn(midi, velocity, ts) {
    const vel = Number(velocity ?? 0);
    const t = Number(ts ?? performance.now());
    if (!Number.isFinite(midi)) return;

    // MIDI: noteon with vel 0 => noteoff
    if (vel <= 0) return this.noteOff(midi, t);

    this.activeMidi.add(midi);

    const pc = ((midi % 12) + 12) % 12;
    this._pcLastOnTs[pc] = t;

    // trail update
    if (!this.ignoreRepeatedPc || this.pcTrail.length === 0 || this.pcTrail[this.pcTrail.length - 1].pc !== pc) {
      this.pcTrail.push({ pc, t });
      if (this.pcTrail.length > this.pcTrailMax) this.pcTrail.shift();
    }
    const cutoff = t - this.pcTrailWindowMs;
    while (this.pcTrail.length > 0 && this.pcTrail[0].t < cutoff) this.pcTrail.shift();

    // energy update
    this._decayPcEnergy(t);
    const w = clamp(vel / 127, 0, 1);
    this.pcEnergy[pc] += this.energyBaseImpulse + this.energyVelImpulse * w;

    this.lastPc = pc;
    this.lastVel = w;
    this.lastTs = t;

    this._updateChordAndFunction(t);
  }

  noteOff(midi, ts) {
    const t = Number(ts ?? performance.now());
    if (!Number.isFinite(midi)) return;

    this.activeMidi.delete(midi);
    this.lastTs = t;

    // Update immediately so chord/scale drop released notes right away
    this._updateChordAndFunction(t);
  }

  tick(nowTs) {
    const t = Number.isFinite(nowTs) ? nowTs : performance.now();
    this._decayPcEnergy(t);
    if (t - (this._lastChordUpdateTs || 0) > 120) {
      this._updateChordAndFunction(t);
    }
  }

  _decayPcEnergy(nowTs) {
    const t = Number.isFinite(nowTs) ? nowTs : performance.now();
    const last = (this.pcEnergyLastTs || t);
    const dt = Math.max(0, t - last);
    if (dt <= 0) { this.pcEnergyLastTs = t; return; }

    const hl = Math.max(50, this.pcEnergyHalfLifeMs || 1800);
    const k = Math.LN2 / hl;
    const factor = Math.exp(-k * dt);

    for (let i = 0; i < 12; i++) {
      const v = this.pcEnergy[i] * factor;
      this.pcEnergy[i] = (v < 1e-4) ? 0 : v;
    }
    this.pcEnergyLastTs = t;
  }

    // Backward-compatible: some UI code expects this to exist.
  // Returns currently held pitch classes (Set<int 0..11>).
activePitchClasses() {
  const pcs = new Set();
  for (const midi of this.activeMidi) pcs.add(((midi % 12) + 12) % 12);
  return pcs;
}



  // Pitch classes used for chord/scale inference:
  // - Always includes currently held notes
  // - Optionally includes recently struck PCs (disabled by default)
  pitchClassesForChord(nowTs) {
    const t = Number.isFinite(nowTs) ? nowTs : performance.now();
    const pcs = new Set();

    // Always: currently held notes only
    for (const midi of this.activeMidi) {
      pcs.add(((midi % 12) + 12) % 12);
    }

    // Optional: include recently struck pitch classes for rolled chords
    if (this.includeRecentStrikesForChord) {
      const cutoff = t - this.chordActiveWindowMs;
      for (let pc = 0; pc < 12; pc++) {
        if ((this._pcLastOnTs[pc] || 0) >= cutoff) pcs.add(pc);
      }
    }

    return [...pcs].sort((a, b) => a - b);
  }

  // Backward-compatible name (if other code calls it)
  activePitchClassesWithinWindow(nowTs) {
    return this.pitchClassesForChord(nowTs);
  }

  computeHarmonicCenterVec() {
    let sumX = 0, sumY = 0, sumW = 0;

    for (let pc = 0; pc < 12; pc++) {
      const w = this.pcEnergy[pc];
      if (!w) continue;
      const idx = PC_TO_INDEX.get(pc);
      if (idx == null) continue;

      const a = (idx / 12) * Math.PI * 2 - Math.PI / 2;
      sumX += w * Math.cos(a);
      sumY += w * Math.sin(a);
      sumW += w;
    }

    if (sumW <= 1e-6) return { ux: 0, uy: 0, mag: 0, sumW: 0 };

    const magRaw = Math.hypot(sumX, sumY);
    const mag = clamp(magRaw / sumW, 0, 1);
    const ux = (magRaw > 1e-6) ? (sumX / magRaw) : 0;
    const uy = (magRaw > 1e-6) ? (sumY / magRaw) : 0;
    return { ux, uy, mag, sumW };
  }

  pulse() {
    const now = performance.now();
    const dt = Math.max(0, now - (this.lastTs || now));
    const tt = dt / 700;
    const decay = Math.exp(-dt / 2200);
    return Math.sin(tt * Math.PI * 2) * 0.5 * decay;
  }

  _updateChordAndFunction(nowTs) {
    const t = Number.isFinite(nowTs) ? nowTs : performance.now();
    this._lastChordUpdateTs = t;

    // 1) chord inference from CURRENTLY HELD notes (plus optional recent strikes)
    const pcs = this.pitchClassesForChord(t);
    const chord = inferChordFromPitchClasses(pcs, { pcNames: PC_NAMES_SHARP, minPcs: 2 });
    this.chord = chord;

    // 2) tonic inference from harmonic center (energy), independent of held-note set
    const tonicPc = this._inferTonicPcFromCenter();
    this.tonicPc = tonicPc;

    // 3) build/update middle ring when tonic/mode changes
    const keyCtx = { tonicPc: this.tonicPc, mode: "major", confidence: 0.6, source: "midi", ts: t };
    if (
      !this.middleRing ||
      this.middleRing.key.tonicPc !== keyCtx.tonicPc ||
      this.middleRing.key.mode !== keyCtx.mode
    ) {
      this.middleRing = buildMiddleRing(keyCtx);
    }

    // 4) analyze current chord against the middle ring
    this.chordDiatonic = analyzeChordDiatonic(this.chord, this.middleRing);

    // 5) functional badge
    this.function = this._inferFunctionBadge(tonicPc, chord);
  }

  _inferTonicPcFromCenter() {
    const v = this.computeHarmonicCenterVec();
    if (!v || v.mag <= 0.08) return null;

    const ang = Math.atan2(v.uy, v.ux);
    let a = ang < 0 ? ang + Math.PI * 2 : ang;

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
    const rootIdx = pcToIndex(chord.rootPc);
    if (tonicIdx == null || rootIdx == null) return null;

    let d = (rootIdx - tonicIdx);
    d = ((d + 6) % 12) - 6;

    let badge = "X";
    if (Math.abs(d) <= 1) badge = "T";
    else if (d >= 2 && d <= 4) badge = "D";
    else if (d <= -2 && d >= -4) badge = "S";

    return { badge, tonicPc, distFifths: d, confidence: chord.confidence };
  }
}
