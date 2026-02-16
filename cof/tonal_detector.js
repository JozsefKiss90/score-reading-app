// tonal_detector.js
// Pure logic: tonicization vs modulation state machine.
// Consumes a "state-like" object with:
// - computeHarmonicCenterVec() -> {ux, uy, mag}
// - _inferTonicPcFromCenter() -> pc (0..11) or null
// - chord?.rootPc
//
// Produces/updates state.tonal.
//
// Call updateTonalState(state, nowTs, dtMs) from your animation tick.

import { clamp } from "./utils.js";
import { pcToIndex } from "./cof.js";

function smoothstep(edge0, edge1, x) {
  const t = clamp((x - edge0) / (edge1 - edge0), 0, 1);
  return t * t * (3 - 2 * t);
}

function mod12(x) { return ((x % 12) + 12) % 12; }

// wrap signed to [-6..+6]
function wrapSigned12(x) { return ((x + 6) % 12) - 6; }

export const DEFAULT_TONAL_PARAMS = {
  T1_TONICIZE_MS: 900,
  T2_MODULATE_MS: 2600,
  HYSTERESIS_MS: 1400,

  MIN_FOCUS_TONICIZE: 0.28,
  MIN_FOCUS_MODULATE: 0.42,

  PREV_FADE_MS: 1800,
};

export function ensureTonalState(state) {
  if (state.tonal) return state.tonal;
  state.tonal = {
    globalTonicPc: null,
    globalStrength: 0,

    candidatePc: null,
    candidateStrength: 0,
    candidateHoldMs: 0,
    globalHoldMs: 0,

    prevGlobalPc: null,
    prevGlobalStrength: 0,
    switchTs: 0,

    tonicizeTargetPc: null,
    tonicizeStrength: 0,

    // informational (optional)
    domPressure: 0,
    focus: 0,
  };
  return state.tonal;
}

export function updateTonalState(state, nowTs, dtMs, params = {}) {
  const P = { ...DEFAULT_TONAL_PARAMS, ...params };
  const t = Number.isFinite(nowTs) ? nowTs : performance.now();
  const dt = Number.isFinite(dtMs) ? dtMs : 16.7;

  const tonal = ensureTonalState(state);

  // Focus from center-of-gravity magnitude
  const C = state.computeHarmonicCenterVec ? state.computeHarmonicCenterVec() : null;
  const focus = clamp(C?.mag ?? 0, 0, 1);

  // Candidate tonic from center vector
  const infer = params.inferTonicPcFromCenter
    ? params.inferTonicPcFromCenter
    : (state._inferTonicPcFromCenter ? state._inferTonicPcFromCenter.bind(state) : null);

  const candPcRaw = infer ? infer() : null;
  const candPc = (candPcRaw == null) ? null : mod12(candPcRaw);

  const candStrength = smoothstep(0.18, 0.55, focus);

  // Candidate tracking
  if (candPc != null && candPc === tonal.candidatePc) {
    tonal.candidateHoldMs += dt;
    tonal.candidateStrength = tonal.candidateStrength + (candStrength - tonal.candidateStrength) * 0.08;
  } else {
    tonal.candidatePc = candPc;
    tonal.candidateHoldMs = 0;
    tonal.candidateStrength = candStrength;
  }

  tonal.globalHoldMs += dt;

  const globalPc = tonal.globalTonicPc;
  const canCommit = (tonal.globalHoldMs >= P.HYSTERESIS_MS);

  const wantCommit =
    tonal.candidatePc != null &&
    tonal.candidatePc !== globalPc &&
    tonal.candidateHoldMs > P.T2_MODULATE_MS &&
    focus > P.MIN_FOCUS_MODULATE &&
    canCommit;

  if (wantCommit) {
    tonal.prevGlobalPc = globalPc;
    tonal.prevGlobalStrength = tonal.globalStrength || 0.6;
    tonal.switchTs = t;

    tonal.globalTonicPc = tonal.candidatePc;
    tonal.globalStrength = clamp(0.65 + 0.35 * tonal.candidateStrength, 0, 1);

    tonal.globalHoldMs = 0;

    tonal.tonicizeTargetPc = null;
    tonal.tonicizeStrength = 0;
  } else {
    // Bootstrap: adopt first stable candidate modestly
    if (tonal.globalTonicPc == null && tonal.candidatePc != null && tonal.candidateHoldMs > 450 && focus > 0.25) {
      tonal.globalTonicPc = tonal.candidatePc;
      tonal.globalStrength = clamp(0.45 + 0.35 * tonal.candidateStrength, 0, 0.8);
      tonal.globalHoldMs = 0;
    } else if (tonal.globalTonicPc != null) {
      // Update global strength slowly (avoid flapping)
      const target = clamp(0.35 + 0.55 * smoothstep(0.20, 0.55, focus), 0, 1);
      tonal.globalStrength = tonal.globalStrength + (target - tonal.globalStrength) * 0.02;
    }

    // Tonicization: candidate focus before commitment window
    const tonicizeActive =
      tonal.candidatePc != null &&
      tonal.candidatePc !== tonal.globalTonicPc &&
      tonal.candidateHoldMs > P.T1_TONICIZE_MS &&
      tonal.candidateHoldMs < P.T2_MODULATE_MS &&
      focus > P.MIN_FOCUS_TONICIZE;

    if (tonicizeActive) {
      tonal.tonicizeTargetPc = tonal.candidatePc;
      const s = smoothstep(P.T1_TONICIZE_MS, P.T2_MODULATE_MS, tonal.candidateHoldMs);
      tonal.tonicizeStrength = clamp(0.15 + 0.75 * s, 0, 0.90);
    } else {
      tonal.tonicizeStrength *= Math.exp(-dt / 600);
      if (tonal.tonicizeStrength < 0.02) {
        tonal.tonicizeStrength = 0;
        tonal.tonicizeTargetPc = null;
      }
    }
  }

  // Fade previous tonic glow
  if (tonal.prevGlobalPc != null && tonal.switchTs) {
    const age = t - tonal.switchTs;
    const a = (age <= 0) ? 1 : Math.exp(-age / P.PREV_FADE_MS);
    if (a < 0.02) {
      tonal.prevGlobalPc = null;
      tonal.prevGlobalStrength = 0;
      tonal.switchTs = 0;
    } else {
      tonal.prevGlobalStrength = (tonal.prevGlobalStrength || 0) * a;
    }
  }

  // Optional: dominant pressure hint (for future V/x logic)
  let domPressure = 0;
  if (state.chord && tonal.globalTonicPc != null) {
    const ti = pcToIndex(tonal.globalTonicPc);
    const ri = pcToIndex(state.chord.rootPc);
    if (ti != null && ri != null) {
      const d = wrapSigned12(ri - ti);
      if (d >= 2 && d <= 4) domPressure = 1;
    }
  }

  tonal.domPressure = domPressure;
  tonal.focus = focus;

  return tonal;
}
