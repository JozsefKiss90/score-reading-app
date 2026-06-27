"""Conservative diatonic chord inference for real scores (Phase 7).

This is the *optional* heuristic layer.  It NEVER overwrites a curated
annotation (the importer only calls it for measures the sidecar left blank) and
it NEVER invents certainty:

* a measure containing any pitch class outside the key's diatonic scale is
  marked ``status="unsupported_chromatic"`` ("requires chromatic analysis") --
  it does not try to name an applied/altered chord;
* a measure whose pitch-class set fits more than one diatonic triad (and whose
  bass does not disambiguate) is marked ``status="ambiguous"`` with no root;
* otherwise it returns the best diatonic triad, preferring root-in-the-bass
  evidence, with a confidence in ``[0,1]``.

The comparison is a plain pitch-class-set coverage test against the diatonic
triads from :mod:`theory.diatonic_harmony` -- the single source of truth.
"""

from __future__ import annotations

from typing import List, Optional, Set

from theory.diatonic_harmony import (
    DiatonicTriad,
    generate_diatonic_triads,
    generate_scale,
    note_pc,
)

from harmony.score_analysis import ScoreHarmonySlice, canon_mode

__all__ = ["CONFIDENCE_OK", "infer_slice"]

#: At/above this confidence the inference is accepted as ``status="ok"``.
CONFIDENCE_OK = 0.66


def _tonic(key: str) -> str:
    from theory.diatonic_harmony import parse_key
    t, _ = parse_key(key)
    return t


def _triad_pcs(t: DiatonicTriad) -> Set[int]:
    return {note_pc(p) for p in t.pitches}


def infer_slice(score_id: str, measure_data, key: str,
                mode: str) -> ScoreHarmonySlice:
    """Infer a conservative :class:`ScoreHarmonySlice` for one measure.

    ``measure_data`` is a :class:`harmony.score_import.MeasureData` (anything
    exposing ``number``, ``pitch_class_names``, ``bass``, ``notes``,
    ``quarter_length``).
    """
    cmode = canon_mode(mode)
    tonic = _tonic(key)
    key_label = f"{tonic} {'minor' if cmode == 'natural_minor' else 'major'}"

    pc_names: List[str] = list(getattr(measure_data, "pitch_class_names", []))
    meas_pcs: List[int] = []
    for n in pc_names:
        try:
            meas_pcs.append(note_pc(n))
        except Exception:
            continue
    meas_set: Set[int] = set(meas_pcs)

    base = ScoreHarmonySlice(
        score_id=score_id,
        measure=getattr(measure_data, "number", 0),
        beat_start=0.0,
        beat_end=float(getattr(measure_data, "quarter_length", 0.0) or 0.0),
        notes=list(getattr(measure_data, "notes", [])),
        chord_tones=list(pc_names),
        key=key_label,
        mode="minor" if cmode == "natural_minor" else "major",
        source="heuristic",
    )

    if not meas_set:
        base.status = "ambiguous"
        base.confidence = 0.0
        base.explanation = "Empty measure -- no pitches to analyse."
        return base

    scale = generate_scale(tonic, cmode)
    scale_pcs = {note_pc(p) for p in scale.scale_pitches}
    chromatic = sorted({n for n, pc in zip(pc_names, meas_pcs)
                        if pc not in scale_pcs})
    if chromatic:
        base.status = "unsupported_chromatic"
        base.confidence = 0.0
        base.explanation = (
            f"Contains chromatic pitch class(es) {', '.join(chromatic)} -- "
            f"requires chromatic analysis (secondary dominant / borrowed / "
            f"applied diminished). Outside the diatonic triad engine.")
        return base

    bass_pc: Optional[int] = None
    bass = getattr(measure_data, "bass", None)
    if bass:
        try:
            bass_pc = note_pc(bass)
        except Exception:
            bass_pc = None

    triads = generate_diatonic_triads(tonic, cmode)
    full = [t for t in triads if _triad_pcs(t) <= meas_set]
    root_in_bass = [t for t in full if bass_pc is not None
                    and note_pc(t.root) == bass_pc]

    chosen: Optional[DiatonicTriad] = None
    confidence = 0.0
    status = "ok"

    if not full:
        # No complete diatonic triad -- report the best partial, stay ambiguous.
        best = max(triads, key=lambda t: len(_triad_pcs(t) & meas_set))
        cov = len(_triad_pcs(best) & meas_set)
        base.status = "ambiguous"
        base.confidence = round(cov / 3.0 * 0.5, 2)
        base.explanation = (
            f"No complete diatonic triad covers this measure; the best partial "
            f"fit is {best.roman} ({cov}/3 tones). Marked ambiguous.")
        return base

    if len(root_in_bass) == 1:
        chosen, confidence, status = root_in_bass[0], 0.9, "ok"
    elif len(full) == 1:
        chosen, confidence, status = full[0], 0.7, "ok"  # an inversion
    elif root_in_bass:
        # several full triads but the bass picks one
        chosen, confidence, status = root_in_bass[0], 0.75, "ok"
    else:
        # the pitch-class set genuinely fits >1 triad and the bass is shared
        cands = ", ".join(t.roman for t in full)
        base.status = "ambiguous"
        base.confidence = 0.4
        base.explanation = (
            f"Ambiguous: the pitch-class set fits more than one diatonic triad "
            f"({cands}) and the bass does not disambiguate.")
        return base

    extras = sorted({n for n, pc in zip(pc_names, meas_pcs)
                     if pc not in _triad_pcs(chosen)})
    added = (f" Added non-triad tone(s): {', '.join(extras)}."
             if extras else "")
    inv = "" if (bass_pc is not None and note_pc(chosen.root) == bass_pc) \
        else " (inverted: root not in the bass)"

    base.inferred_root = chosen.root
    base.chord_symbol = chosen.chord_symbol
    base.roman = chosen.roman
    base.base_roman = chosen.roman
    base.function_label = chosen.function_label
    base.interval_layer = chosen.interval_layer
    base.confidence = confidence
    base.status = status if confidence >= CONFIDENCE_OK else "ambiguous"
    base.explanation = (
        f"Heuristic: best diatonic fit is {chosen.roman} "
        f"({chosen.chord_symbol}){inv}.{added} "
        f"Confidence {confidence:.2f} (curated annotations override this).")
    return base
