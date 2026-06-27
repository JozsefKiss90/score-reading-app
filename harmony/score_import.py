"""Controlled real-score importer for the Score Soul Graph (Phase 2).

Reads a MusicXML / MXL file (via music21) into a light per-measure note model,
then merges it with a *curated* sidecar annotation file to build a
:class:`harmony.score_analysis.ScoreAnalysisResult`.

Curated annotations are the **source of truth** for the pilot.  The extracted
note data only *fills in* fields a slice leaves blank (the literal pitches, the
chord tones, the measure's beat span) and powers the conservative heuristic
cross-check (:mod:`harmony.score_heuristic`).  The importer never invents
harmonic certainty.

music21 is imported lazily so this module imports cheaply and the rest of the
package does not hard-depend on it.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from harmony.score_analysis import (
    ScoreAnalysisResult,
    ScoreCadenceSpan,
    ScoreFormSection,
    ScoreHarmonySlice,
)

__all__ = [
    "MeasureData",
    "DATA_DIR",
    "ANNOTATIONS_DIR",
    "SCORES_DIR",
    "annotation_path",
    "score_file_path",
    "load_annotations",
    "load_score",
    "extract_measures",
    "ensure_local_bwv846",
    "build_analysis",
    "load_bwv846_analysis",
    "load_analysis_from_sidecar",
]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO = Path(__file__).resolve().parent.parent
DATA_DIR = _REPO / "data"
ANNOTATIONS_DIR = DATA_DIR / "score_annotations"
SCORES_DIR = DATA_DIR / "scores"


def annotation_path(score_id: str) -> Path:
    return ANNOTATIONS_DIR / f"{score_id}.json"


def score_file_path(score_id: str) -> Optional[Path]:
    """First existing local score file for ``score_id`` (.mxl/.musicxml/.xml)."""
    for ext in (".mxl", ".musicxml", ".xml"):
        p = SCORES_DIR / f"{score_id}{ext}"
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------------------
# Per-measure note model
# ---------------------------------------------------------------------------

@dataclass
class MeasureData:
    """The raw note content of one measure (both staves flattened)."""

    number: int                                  # 1-based measure number
    notes: List[str] = field(default_factory=list)        # spelled, low->high
    pitch_class_names: List[str] = field(default_factory=list)  # distinct, low->high
    bass: Optional[str] = None                   # lowest sounding spelled pitch
    quarter_length: float = 4.0
    accidentals: List[str] = field(default_factory=list)  # non-natural pcs present

    @property
    def abs_index(self) -> int:
        """0-based absolute index used by the viewer cursor (``measures[i]``)."""
        return self.number - 1

    def to_dict(self) -> Dict:
        return {
            "number": self.number,
            "absIndex": self.abs_index,
            "notes": list(self.notes),
            "pitchClasses": list(self.pitch_class_names),
            "bass": self.bass,
            "quarterLength": self.quarter_length,
            "accidentals": list(self.accidentals),
        }


# ---------------------------------------------------------------------------
# music21 -> MeasureData
# ---------------------------------------------------------------------------

def _spell(name: str) -> str:
    """Convert a music21 pitch name to the app spelling (``E-`` -> ``Eb``)."""
    return name.replace("--", "bb").replace("-", "b")


def load_score(path):
    """Parse a MusicXML/MXL file into a music21 ``Score`` (lazy import)."""
    from music21 import converter  # lazy
    return converter.parse(str(path))


def load_bwv846_score():
    """Load BWV 846, preferring the local copy, falling back to the corpus."""
    local = score_file_path("bwv846_prelude_c_major")
    if local is not None:
        return load_score(local)
    from music21 import corpus  # lazy
    return corpus.parse("bwv846")


_NATURAL = {"C", "D", "E", "F", "G", "A", "B"}


def extract_measures(score) -> List[MeasureData]:
    """Flatten every part's measures into per-measure :class:`MeasureData`.

    Notes from all staves are merged; pitches keep Bach's spelling.  Each
    measure yields its distinct pitch classes (low -> high), bass note, and the
    set of accidental (non-natural) pitch classes present.
    """
    buckets: Dict[int, Dict] = {}
    parts = list(getattr(score, "parts", []) or [score])
    for part in parts:
        try:
            measures = part.recurse().getElementsByClass("Measure")
        except Exception:
            continue
        for m in measures:
            num = m.measureNumber
            if num is None:
                continue
            b = buckets.setdefault(
                num, {"items": [], "ql": float(m.barDuration.quarterLength or 4.0)})
            for el in m.recurse().notes:
                for p in getattr(el, "pitches", []):
                    b["items"].append((p.midi, _spell(p.nameWithOctave),
                                       _spell(p.name)))

    out: List[MeasureData] = []
    for num in sorted(buckets):
        items = buckets[num]["items"]
        if not items:
            out.append(MeasureData(number=num,
                                   quarter_length=buckets[num]["ql"]))
            continue
        items_sorted = sorted(items, key=lambda t: t[0])
        # distinct pitch classes, ordered by first (lowest) occurrence
        seen_pc: List[str] = []
        for _midi, _nwo, pcname in items_sorted:
            if pcname not in seen_pc:
                seen_pc.append(pcname)
        # distinct spelled notes (with octave) low->high
        seen_notes: List[str] = []
        for _midi, nwo, _pc in items_sorted:
            if nwo not in seen_notes:
                seen_notes.append(nwo)
        accidentals = [pc for pc in seen_pc if pc not in _NATURAL]
        out.append(MeasureData(
            number=num,
            notes=seen_notes,
            pitch_class_names=seen_pc,
            bass=items_sorted[0][1],
            quarter_length=buckets[num]["ql"],
            accidentals=accidentals,
        ))
    return out


# ---------------------------------------------------------------------------
# Local score-file bootstrap
# ---------------------------------------------------------------------------

def ensure_local_bwv846() -> Optional[Path]:
    """Ensure ``data/scores/bwv846_prelude_c_major.mxl`` exists (copy from corpus).

    Returns the local path, or ``None`` if music21's corpus copy is unavailable.
    """
    dst = SCORES_DIR / "bwv846_prelude_c_major.mxl"
    if dst.exists():
        return dst
    try:
        from music21 import corpus  # lazy
        src = corpus.getWork("bwv846")
    except Exception:
        return None
    if not src:
        return None
    SCORES_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(str(src), str(dst))
    return dst


# ---------------------------------------------------------------------------
# Sidecar -> ScoreAnalysisResult
# ---------------------------------------------------------------------------

def load_annotations(path) -> Dict:
    """Load a curated sidecar annotation file (JSON)."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _slice_key(result: ScoreAnalysisResult, sl: ScoreHarmonySlice) -> str:
    if sl.key:
        return sl.key if " " in sl.key else f"{sl.key} {sl.mode or result.mode}"
    return f"{result.key} {result.mode}"


def build_analysis(annotations: Dict,
                   measures: Optional[List[MeasureData]] = None,
                   resolve: bool = True,
                   heuristic: bool = False) -> ScoreAnalysisResult:
    """Build a :class:`ScoreAnalysisResult` from a sidecar + optional note data.

    Curated slices win; ``measures`` only fills blanks (notes / chord tones /
    beat span).  When ``heuristic`` is set, measures that the sidecar did NOT
    annotate get a conservative inferred slice (never overwriting curated ones).
    """
    sid = annotations.get("score_id") or annotations.get("scoreId") or ""
    result = ScoreAnalysisResult(
        score_id=sid,
        title=annotations.get("title", "") or "",
        composer=annotations.get("composer", "") or "",
        key=annotations.get("key", "C") or "C",
        mode=annotations.get("mode", "major") or "major",
        global_summary=annotations.get("global_summary",
                                       annotations.get("globalSummary", "")) or "",
        score_graph_template_id=annotations.get(
            "score_graph_template_id",
            annotations.get("scoreGraphTemplateId", "score_soul_radial_v1"))
        or "score_soul_radial_v1",
    )

    md_by_num: Dict[int, MeasureData] = {m.number: m for m in (measures or [])}

    for sd in annotations.get("slices", []):
        sl = ScoreHarmonySlice.from_dict(sd, sid)
        sl.key = _slice_key(result, sl)
        sl.mode = sl.mode or result.mode
        md = md_by_num.get(sl.measure)
        if md is not None:
            if not sl.notes:
                sl.notes = list(md.notes)
            if not sl.chord_tones:
                sl.chord_tones = list(md.pitch_class_names)
            if not sl.beat_end:
                sl.beat_end = md.quarter_length
        result.slices.append(sl)

    annotated = {s.measure for s in result.slices}

    if heuristic and measures:
        from harmony.score_heuristic import infer_slice  # lazy
        for md in measures:
            if md.number in annotated or not md.pitch_class_names:
                continue
            sl = infer_slice(sid, md, result.key, result.mode)
            result.slices.append(sl)

    for cd in annotations.get("cadences", []):
        result.cadences.append(ScoreCadenceSpan.from_dict(cd, sid))
    for secd in annotations.get("sections", []):
        result.sections.append(ScoreFormSection.from_dict(secd))

    result.slices.sort(key=lambda s: s.measure)

    if resolve:
        result.resolve_refs()
    result.validate()
    return result


def load_analysis_from_sidecar(score_id: str,
                               score=None,
                               resolve: bool = True,
                               heuristic: bool = False) -> ScoreAnalysisResult:
    """Load ``data/score_annotations/<score_id>.json`` and build the analysis.

    If ``score`` (a music21 score) is given, its measures fill blank slice
    fields; otherwise the analysis is built from the sidecar alone (still valid
    -- useful when the score file is not bundled, e.g. BWV 999).
    """
    annotations = load_annotations(annotation_path(score_id))
    measures = extract_measures(score) if score is not None else None
    return build_analysis(annotations, measures, resolve=resolve,
                          heuristic=heuristic)


def load_bwv846_analysis(resolve: bool = True,
                         heuristic: bool = False) -> ScoreAnalysisResult:
    """Full BWV 846 pipeline: ensure score file, parse, merge sidecar."""
    ensure_local_bwv846()
    score = load_bwv846_score()
    return load_analysis_from_sidecar("bwv846_prelude_c_major", score=score,
                                      resolve=resolve, heuristic=heuristic)
