// cofmm_es/cof.js

// Circle of Fifths order (pitch classes) starting at C:
// C, G, D, A, E, B, F#, C#, G#, D#, A#, F
export const COF_PCS = [0, 7, 2, 9, 4, 11, 6, 1, 8, 3, 10, 5];
export const COF_LABELS = ["C", "G", "D", "A", "E", "B", "F#", "C#", "G#", "D#", "A#", "F"];

export const PC_TO_INDEX = (() => {
  const m = new Map();
  for (let i = 0; i < COF_PCS.length; i++) m.set(COF_PCS[i], i);
  return m;
})();

export function idxToAngle(idx) {
  return (idx / 12) * Math.PI * 2 - Math.PI / 2;
}

export function pcToIndex(pc) {
  return PC_TO_INDEX.get(pc);
}

export function pcToAngle(pc) {
  const idx = pcToIndex(pc);
  if (idx == null) return null;
  return idxToAngle(idx);
}
