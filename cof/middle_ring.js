// middle_ring.js
// Build a MiddleRingModel from a KeyContext (ES module).
// This is the "diatonic function" ring (7 degrees) used to contextualize chords.
//
// MiddleRingModel shape (JS object):
// {
//   key: {tonicPc, mode, confidence, source, ts},
//   scale: {pcs, degreeToPc, pcToDegree, degreeLabels},
//   degrees: [ {degree, rootPc, roman, quality, func, chordTones} ... ],
//   byRootPc: Map(rootPc -> degreeNode),
//   ts
// }

import { clamp } from "./utils.js";

const MAJOR_SCALE_IVS = [0, 2, 4, 5, 7, 9, 11];
const MINOR_SCALE_IVS = [0, 2, 3, 5, 7, 8, 10]; // natural minor baseline

// Triad qualities per degree (1..7)
const MAJOR_TRIAD_QUAL = [null, "maj", "min", "min", "maj", "maj", "min", "dim"];
const MINOR_TRIAD_QUAL = [null, "min", "dim", "maj", "min", "min", "maj", "maj"];

// Roman labels (baseline) per degree (1..7)
const MAJOR_ROMAN = [null, "I", "ii", "iii", "IV", "V", "vi", "vii°"];
const MINOR_ROMAN = [null, "i", "ii°", "III", "iv", "v", "VI", "VII"];

// Functional buckets (baseline)
function degreeToFunc(deg) {
  // Tonic: 1,3,6  | Subdominant: 2,4 | Dominant: 5,7
  if (deg === 1 || deg === 3 || deg === 6) return "T";
  if (deg === 2 || deg === 4) return "S";
  return "D";
}

function mod12(x) { return ((x % 12) + 12) % 12; }

function triadTones(rootPc, quality) {
  // Return chord tones as pitch classes
  if (quality === "maj") return [rootPc, mod12(rootPc + 4), mod12(rootPc + 7)];
  if (quality === "min") return [rootPc, mod12(rootPc + 3), mod12(rootPc + 7)];
  if (quality === "dim") return [rootPc, mod12(rootPc + 3), mod12(rootPc + 6)];
  // fallback: treat as major
  return [rootPc, mod12(rootPc + 4), mod12(rootPc + 7)];
}

export function buildMiddleRing(keyContext) {
  const key = keyContext || {};
  const tonicPc = Number.isFinite(key.tonicPc) ? mod12(key.tonicPc) : null;
  const mode = (key.mode === "minor") ? "minor" : "major";

  if (tonicPc == null) return null;

  const ivs = (mode === "minor") ? MINOR_SCALE_IVS : MAJOR_SCALE_IVS;
  const roman = (mode === "minor") ? MINOR_ROMAN : MAJOR_ROMAN;
  const qual = (mode === "minor") ? MINOR_TRIAD_QUAL : MAJOR_TRIAD_QUAL;

  const pcs = ivs.map(iv => mod12(tonicPc + iv));

  const degreeToPc = new Array(8).fill(null);
  const pcToDegree = new Map();
  for (let d = 1; d <= 7; d++) {
    const pc = pcs[d - 1];
    degreeToPc[d] = pc;
    pcToDegree.set(pc, d);
  }

  const degrees = [];
  const byRootPc = new Map();

  for (let d = 1; d <= 7; d++) {
    const rootPc = degreeToPc[d];
    const quality = qual[d] || "maj";
    const node = {
      degree: d,
      rootPc,
      roman: roman[d] || String(d),
      quality,
      func: degreeToFunc(d),
      chordTones: triadTones(rootPc, quality),
    };
    degrees.push(node);
    byRootPc.set(rootPc, node);
  }

  return {
    key: {
      tonicPc,
      mode,
      confidence: clamp(Number(key.confidence ?? 0.5), 0, 1),
      source: String(key.source ?? "midi"),
      ts: Number(key.ts ?? performance.now()),
    },
    scale: {
      pcs,
      degreeToPc,
      pcToDegree,
      degreeLabels: degrees.map(d => d.roman),
    },
    degrees,
    byRootPc,
    ts: performance.now(),
  };
}
