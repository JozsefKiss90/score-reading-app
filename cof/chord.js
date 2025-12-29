// chord.js
// MIDI chord inference utilities (ES module).
// Input: a pitch-class set (array of 0..11) and optional options.
// Output: best-fit chord hypothesis with confidence.
//
// Lightweight and deterministic for real-time UI feedback.

import { clamp } from "./utils.js";

export const PC_NAMES_SHARP = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"];

// Templates expressed as semitone intervals from root.
const TEMPLATES = [
  { id:"maj",   name:"",      intervals:[0,4,7] },
  { id:"min",   name:"m",     intervals:[0,3,7] },
  { id:"dim",   name:"dim",   intervals:[0,3,6] },
  { id:"aug",   name:"aug",   intervals:[0,4,8] },
  { id:"sus2",  name:"sus2",  intervals:[0,2,7] },
  { id:"sus4",  name:"sus4",  intervals:[0,5,7] },

  { id:"7",     name:"7",     intervals:[0,4,7,10] },
  { id:"maj7",  name:"maj7",  intervals:[0,4,7,11] },
  { id:"m7",    name:"m7",    intervals:[0,3,7,10] },
  { id:"mMaj7", name:"mMaj7", intervals:[0,3,7,11] },
  { id:"hdim7", name:"ø7",    intervals:[0,3,6,10] },
  { id:"dim7",  name:"dim7",  intervals:[0,3,6,9] },
];

function mod12(x){ return ((x % 12) + 12) % 12; }

function asSet(arr){
  const s = new Set();
  for (const x of arr) s.add(mod12(x));
  return s;
}

function scoreCandidate(pcSet, rootPc, tmpl) {
  const tmplPcs = tmpl.intervals.map(iv => mod12(rootPc + iv));
  const tmplSet = asSet(tmplPcs);

  let matched = 0;
  for (const pc of tmplSet) if (pcSet.has(pc)) matched += 1;

  const missing = tmplSet.size - matched;

  let extra = 0;
  for (const pc of pcSet) if (!tmplSet.has(pc)) extra += 1;

  const rootPresent = pcSet.has(rootPc) ? 1 : 0;

  // Score design (heuristic):
  // - matched dominates
  // - missing hurts more than extra
  // - extra hurts to avoid naming clusters as 7ths
  // - root present slightly helps
  const s = (matched * 1.35) - (missing * 1.15) - (extra * 0.55) + (rootPresent * 0.35);

  // Normalize to a confidence-like value [0..1]
  const conf = clamp((s + 1.0) / 6.0, 0, 1);
  return { score: s, matched, missing, extra, conf, tmplPcs };
}

export function inferChordFromPitchClasses(pcs, opts = {}) {
  const uniq = [...new Set((pcs || []).map(mod12))].sort((a,b)=>a-b);
  if (uniq.length === 0) return null;

  const pcSet = asSet(uniq);

  const minPcs = Number.isFinite(opts.minPcs) ? opts.minPcs : 2;
  if (uniq.length < minPcs) return null;

  let best = null;
  for (let root = 0; root < 12; root++) {
    for (const tmpl of TEMPLATES) {
      if (uniq.length <= 2 && tmpl.intervals.length >= 4) continue;
      const r = scoreCandidate(pcSet, root, tmpl);
      if (!best || r.score > best.score) {
        best = { rootPc: root, quality: tmpl.id, qualityName: tmpl.name, ...r };
      }
    }
  }
  if (!best) return null;

  const chordTones = new Set(best.tmplPcs.map(mod12));
  const extras = uniq.filter(pc => !chordTones.has(pc));

  const names = opts.pcNames || PC_NAMES_SHARP;
  const rootName = names[best.rootPc];
  const name = `${rootName}${best.qualityName}`;

  const damp = clamp(1 - Math.max(0, uniq.length - 5) * 0.08, 0.6, 1);
  const confidence = clamp(best.conf * damp, 0, 1);

  return {
    rootPc: best.rootPc,
    name,
    quality: best.quality,
    confidence,
    chordTones: [...chordTones],
    extras,
    matched: best.matched,
    missing: best.missing,
    pcSet: uniq,
  };
}
