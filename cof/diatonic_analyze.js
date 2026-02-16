// diatonic_analyze.js
// Produce ChordDiatonicAnalysis from an inferred chord + MiddleRingModel (ES module).
//
// Chord hypothesis input is expected to be the output of inferChordFromPitchClasses (chord.js):
// { name, rootPc, chordTones, extras, confidence, quality, pcSet ... }

import { clamp } from "./utils.js";

function mod12(x) { return ((x % 12) + 12) % 12; }

function inScaleRatio(chordTones, scaleSet) {
  if (!chordTones || chordTones.length === 0) return 0;
  let inside = 0;
  for (const pc of chordTones) if (scaleSet.has(mod12(pc))) inside += 1;
  return inside / chordTones.length;
}

export function analyzeChordDiatonic(chord, middleRing) {
  if (!chord || !middleRing) return null;

  const scaleSet = new Set(middleRing.scale.pcs.map(mod12));
  const rootPc = mod12(chord.rootPc);
  const degreeNode = middleRing.byRootPc.get(rootPc) || null;

  const ratio = inScaleRatio(chord.chordTones || [], scaleSet);

  // Baseline diatonicity heuristic:
  // - If root is diatonic and ALL chord tones are in scale -> diatonic
  // - If root is diatonic but some tones are outside -> borrowed
  // - If root is non-diatonic but chord tones mostly in-scale -> borrowed
  // - Otherwise -> chromatic
  let diatonicity = "chromatic";
  if (degreeNode && ratio >= 0.999) diatonicity = "diatonic";
  else if (degreeNode && ratio >= 0.50) diatonicity = "borrowed";
  else if (!degreeNode && ratio >= 0.66) diatonicity = "borrowed";

  const confChord = clamp(Number(chord.confidence ?? 0.0), 0, 1);
  const confKey = clamp(Number(middleRing.key.confidence ?? 0.5), 0, 1);
  const confidence = clamp(confChord * (0.55 + 0.45 * confKey), 0, 1);

  return {
    chordName: String(chord.name ?? ""),
    rootPc,
    chordTones: (chord.chordTones || []).map(mod12),

    degree: degreeNode ? degreeNode.degree : null,
    roman: degreeNode ? degreeNode.roman : null,
    func: degreeNode ? degreeNode.func : null,

    diatonicity,
    inScaleRatio: ratio,
    confidence,
  };
}
