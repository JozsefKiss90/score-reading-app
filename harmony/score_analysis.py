"""Real-score harmonic analysis contract (Score Soul Graph, Phase 1).

This module is the *data contract* for the "Score Soul Graph" / "Live Harmonic
Network Analysis" feature: a controlled, curated, measure-level harmonic reading
of ONE real score at a time (the pilot scores are BWV 846 and BWV 999).

It is intentionally **separate** from the reserved
:class:`harmony.atlas.ScoreAnalysis` placeholder (which stays unimplemented).
Where that placeholder reserved the *interface*, this module supplies the
*concrete model* that the importer (:mod:`harmony.score_import`), the score graph
(:mod:`harmony.score_graph`) and the live launcher consume.

Design rules (consistent with the rest of the harmony layer):

* Pure Python, standard library only -- no Qt / Verovio / MIDI / music21 here so
  it unit-tests headless.  The few helpers that need the Atlas or the Harmonic
  Network import them **lazily** (function-local) to keep this module cheap to
  import and free of import cycles.
* Every chord/Roman/function value is *derived from* and *resolved against* the
  single source of truth (``theory.diatonic_harmony`` + the Atlas / Network node
  sets) -- this module never hard-codes a chord table.
* The model is honest: a slice that is not a clean diatonic triad in the score's
  key is marked (``status="unsupported_chromatic"`` or ``"ambiguous"``) rather
  than faked into a triad.  Curated annotations are always the source of truth;
  heuristics never overwrite them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from theory.diatonic_harmony import (
    DiatonicTriad,
    generate_diatonic_triads,
    note_pc,
    parse_key,
)

__all__ = [
    "SCORE_ANALYSIS_SCHEMA",
    "VALID_SOURCES",
    "VALID_STATUS",
    "ScoreHarmonySlice",
    "ScoreCadenceSpan",
    "ScoreFormSection",
    "ScoreAnalysisResult",
    "canon_mode",
    "diatonic_triad_match",
    "atlas_refs_for",
    "network_target_for",
    "network_refs_for",
    "resolve_slice_refs",
    "slice_to_atlas_annotation",
]

SCORE_ANALYSIS_SCHEMA = "score-analysis/v1"

#: Provenance of a slice's harmonic reading.
VALID_SOURCES = ("manual", "heuristic", "confirmed")

#: Honesty marker.  ``ok`` = clean diatonic triad in the score key;
#: ``unsupported_chromatic`` = contains non-diatonic pitch classes / needs a
#: harmonic-minor / secondary-dominant / diminished-7th layer the pilot does not
#: implement; ``ambiguous`` = no single triad can be assigned with confidence.
VALID_STATUS = ("ok", "ambiguous", "unsupported_chromatic")


# ---------------------------------------------------------------------------
# Mode / key canonicalisation
# ---------------------------------------------------------------------------

def canon_mode(mode: Optional[str]) -> str:
    """Canonicalise a mode word to the theory/Atlas token.

    The model and sidecars use the human ``"major"``/``"minor"``; the theory
    engine and the Atlas node ids use ``"major"``/``"natural_minor"``.  This is
    the single place that bridges the two so the rest of the module can store
    the human form.
    """
    m = (mode or "").strip().lower().replace("-", "_").replace(" ", "_")
    if m in ("major", "maj", "ionian", ""):
        return "major"
    if m in ("minor", "natural_minor", "min", "aeolian", "natural"):
        return "natural_minor"
    # Harmonic / melodic minor are not modelled by the triad engine; treat them
    # as natural minor for node resolution (the slice's status carries the
    # honesty caveat).
    if "minor" in m:
        return "natural_minor"
    return "major"


def _tonic_of(key: Optional[str]) -> str:
    """Spelled tonic pitch class of a key string (``"C major" -> "C"``)."""
    if not key:
        return ""
    tonic, _ = parse_key(key)
    return tonic


import re as _re


def _quality_from_symbol(chord_symbol: Optional[str],
                         roman: Optional[str] = None) -> Optional[str]:
    """Underlying *triad* quality of a chord symbol (or roman fallback).

    Returns ``"major" | "minor" | "diminished" | "augmented"`` or ``None`` when
    nothing usable is given.  A dominant-7th symbol like ``"G7"`` resolves to
    ``"major"`` (its triad is major), which is exactly what keeps a secondary
    dominant from masquerading as a diatonic minor degree.
    """
    sym = (chord_symbol or "").strip()
    if sym:
        low = sym.lower()
        if "°" in sym or "o7" in low or "dim" in low or "ø" in sym:
            return "diminished"
        if "+" in sym or "aug" in low:
            return "augmented"
        if _re.search(r"m(?!aj)", low):   # an 'm' not part of 'maj'
            return "minor"
        return "major"
    rom = (roman or "").strip()
    if rom:
        if "°" in rom or "ø" in rom:
            return "diminished"
        if "+" in rom:
            return "augmented"
        bare = rom.split("/")[0]          # drop applied-chord suffix
        letters = _re.sub(r"[^IiVv]", "", bare)
        if letters and letters == letters.lower():
            return "minor"
        if letters:
            return "major"
    return None


# ---------------------------------------------------------------------------
# The slice
# ---------------------------------------------------------------------------

@dataclass
class ScoreHarmonySlice:
    """One analysed harmonic unit of a real score (usually one measure).

    The fields mirror :class:`harmony.atlas.HarmonyAnnotation` /
    :class:`harmony.atlas.HarmonySlice` so a slice maps straight onto Atlas
    triad/function/scale nodes and Harmonic-Network nodes.

    ``roman`` is the analyst's *functional* Roman numeral (e.g. ``"ii7"``,
    ``"V6/5"``, ``"V7/V"``).  ``base_roman`` is the bare diatonic-triad numeral
    used for Atlas triad-node resolution (one of ``I ii iii IV V vi vii°`` /
    ``i ii° III iv v VI VII``), or ``None`` when the chord has no diatonic-triad
    reading in the score key.
    """

    score_id: str
    measure: int
    beat_start: float = 0.0
    beat_end: float = 0.0
    notes: List[str] = field(default_factory=list)          # spelled, low->high
    inferred_root: Optional[str] = None
    chord_symbol: Optional[str] = None
    chord_tones: List[str] = field(default_factory=list)    # spelled pitch classes
    roman: Optional[str] = None                             # functional roman
    base_roman: Optional[str] = None                       # bare triad roman
    key: Optional[str] = None                              # e.g. "C major"
    mode: Optional[str] = None                             # "major" | "minor"
    function_label: Optional[str] = None                  # tonic/predominant/...
    interval_layer: Optional[str] = None                  # e.g. "M3+m3"
    confidence: float = 1.0
    explanation: str = ""
    atlas_refs: List[str] = field(default_factory=list)    # atlas node ids
    network_refs: List[str] = field(default_factory=list)  # hn node ids
    source: str = "manual"
    status: str = "ok"

    # -- derived --------------------------------------------------------
    @property
    def key_tonic(self) -> str:
        return _tonic_of(self.key)

    @property
    def is_chromatic(self) -> bool:
        return self.status == "unsupported_chromatic"

    def validate(self) -> None:
        if not self.score_id:
            raise ValueError("ScoreHarmonySlice.score_id is required")
        if not isinstance(self.measure, int) or self.measure < 0:
            raise ValueError(
                f"ScoreHarmonySlice.measure must be a non-negative int "
                f"(got {self.measure!r})")
        if self.source not in VALID_SOURCES:
            raise ValueError(
                f"ScoreHarmonySlice.source must be one of {VALID_SOURCES} "
                f"(got {self.source!r})")
        if self.status not in VALID_STATUS:
            raise ValueError(
                f"ScoreHarmonySlice.status must be one of {VALID_STATUS} "
                f"(got {self.status!r})")
        if not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError(
                f"ScoreHarmonySlice.confidence must be in [0,1] "
                f"(got {self.confidence!r})")

    def to_dict(self) -> Dict:
        return {
            "scoreId": self.score_id,
            "measure": self.measure,
            "beatStart": self.beat_start,
            "beatEnd": self.beat_end,
            "notes": list(self.notes),
            "inferredRoot": self.inferred_root,
            "chordSymbol": self.chord_symbol,
            "chordTones": list(self.chord_tones),
            "roman": self.roman,
            "baseRoman": self.base_roman,
            "key": self.key,
            "mode": self.mode,
            "functionLabel": self.function_label,
            "intervalLayer": self.interval_layer,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "atlasRefs": list(self.atlas_refs),
            "networkRefs": list(self.network_refs),
            "source": self.source,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: Dict, score_id: Optional[str] = None) -> "ScoreHarmonySlice":
        return cls(
            score_id=d.get("scoreId") or d.get("score_id") or score_id or "",
            measure=int(d["measure"]),
            beat_start=float(d.get("beatStart", d.get("beat_start", 0.0)) or 0.0),
            beat_end=float(d.get("beatEnd", d.get("beat_end", 0.0)) or 0.0),
            notes=list(d.get("notes", []) or []),
            inferred_root=d.get("inferredRoot", d.get("inferred_root")),
            chord_symbol=d.get("chordSymbol", d.get("chord_symbol")),
            chord_tones=list(d.get("chordTones", d.get("chord_tones", [])) or []),
            roman=d.get("roman"),
            base_roman=d.get("baseRoman", d.get("base_roman")),
            key=d.get("key"),
            mode=d.get("mode"),
            function_label=d.get("functionLabel", d.get("function_label")),
            interval_layer=d.get("intervalLayer", d.get("interval_layer")),
            confidence=float(d.get("confidence", 1.0)),
            explanation=d.get("explanation", "") or "",
            atlas_refs=list(d.get("atlasRefs", d.get("atlas_refs", [])) or []),
            network_refs=list(d.get("networkRefs", d.get("network_refs", [])) or []),
            source=d.get("source", "manual") or "manual",
            status=d.get("status", "ok") or "ok",
        )

    def chord_quality_hint(self) -> Optional[str]:
        """The chord's underlying *triad* quality, read from its symbol/roman.

        ``"D7" -> major`` (dominant 7th = major triad + m7), ``"Dm7" -> minor``,
        ``"B°7" -> diminished``.  This is what lets a secondary dominant (a
        *major* triad on a non-diatonic root) correctly fail to match a diatonic
        minor ``ii`` -- it is NOT a root-only lookup.
        """
        return _quality_from_symbol(self.chord_symbol, self.roman or self.base_roman)

    def quality_or_none(self) -> Optional[str]:
        """The triad quality if this slice IS a diatonic triad of its key, else
        ``None`` (kept for the Atlas annotation bridge)."""
        t = diatonic_triad_match(self.key, self.mode, self.inferred_root,
                                 self.chord_quality_hint())
        return t.chord_quality if t else None

    def network_target(self) -> Dict:
        """The ``{key,mode,roman,root,quality}`` object the Harmonic Network's
        ``highlightFromTrainerTarget`` consumes."""
        return network_target_for(self)


# ---------------------------------------------------------------------------
# Cadences and form sections
# ---------------------------------------------------------------------------

@dataclass
class ScoreCadenceSpan:
    """A detected cadence in the score (a small span of measures)."""

    score_id: str
    start_measure: int
    end_measure: int
    pattern: List[str] = field(default_factory=list)        # ["V","I"] etc.
    cadence_type: str = ""                                   # authentic/half/...
    chord_symbols: List[str] = field(default_factory=list)
    romans: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    confidence: float = 1.0
    explanation: str = ""

    def validate(self) -> None:
        if self.end_measure < self.start_measure:
            raise ValueError(
                f"cadence end_measure {self.end_measure} < start_measure "
                f"{self.start_measure}")

    def to_dict(self) -> Dict:
        return {
            "scoreId": self.score_id,
            "startMeasure": self.start_measure,
            "endMeasure": self.end_measure,
            "pattern": list(self.pattern),
            "cadenceType": self.cadence_type,
            "chordSymbols": list(self.chord_symbols),
            "romans": list(self.romans),
            "functions": list(self.functions),
            "confidence": self.confidence,
            "explanation": self.explanation,
        }

    @classmethod
    def from_dict(cls, d: Dict, score_id: Optional[str] = None) -> "ScoreCadenceSpan":
        return cls(
            score_id=d.get("scoreId") or d.get("score_id") or score_id or "",
            start_measure=int(d.get("startMeasure", d.get("start_measure"))),
            end_measure=int(d.get("endMeasure", d.get("end_measure"))),
            pattern=list(d.get("pattern", []) or []),
            cadence_type=d.get("cadenceType", d.get("cadence_type", "")) or "",
            chord_symbols=list(d.get("chordSymbols", d.get("chord_symbols", [])) or []),
            romans=list(d.get("romans", []) or []),
            functions=list(d.get("functions", []) or []),
            confidence=float(d.get("confidence", 1.0)),
            explanation=d.get("explanation", "") or "",
        )

    def atlas_cadence_ref(self, mode: str) -> Optional[str]:
        """Resolve this cadence onto an existing Atlas cadence node id, if any."""
        from harmony.atlas import build_atlas  # lazy
        atlas = build_atlas()
        return atlas.cadence_node_id(list(self.pattern), canon_mode(mode))


@dataclass
class ScoreFormSection:
    """A structural / tonal section of the score (large-scale grouping)."""

    label: str
    start_measure: int
    end_measure: int
    tonal_area: str = ""
    description: str = ""

    def validate(self) -> None:
        if self.end_measure < self.start_measure:
            raise ValueError(
                f"section {self.label!r} end_measure {self.end_measure} < "
                f"start_measure {self.start_measure}")

    def to_dict(self) -> Dict:
        return {
            "label": self.label,
            "startMeasure": self.start_measure,
            "endMeasure": self.end_measure,
            "tonalArea": self.tonal_area,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "ScoreFormSection":
        return cls(
            label=d.get("label", ""),
            start_measure=int(d.get("startMeasure", d.get("start_measure"))),
            end_measure=int(d.get("endMeasure", d.get("end_measure"))),
            tonal_area=d.get("tonalArea", d.get("tonal_area", "")) or "",
            description=d.get("description", "") or "",
        )

    def contains(self, measure: int) -> bool:
        return self.start_measure <= measure <= self.end_measure


# ---------------------------------------------------------------------------
# The whole analysis
# ---------------------------------------------------------------------------

@dataclass
class ScoreAnalysisResult:
    """The full curated harmonic analysis of one score."""

    score_id: str
    title: str = ""
    composer: str = ""
    key: str = "C"
    mode: str = "major"
    slices: List[ScoreHarmonySlice] = field(default_factory=list)
    cadences: List[ScoreCadenceSpan] = field(default_factory=list)
    sections: List[ScoreFormSection] = field(default_factory=list)
    global_summary: str = ""
    score_graph_template_id: str = "score_soul_radial_v1"

    # -- access ---------------------------------------------------------
    @property
    def measure_count(self) -> int:
        if not self.slices:
            return 0
        return max(s.measure for s in self.slices)

    def slice_for_measure(self, measure: int) -> Optional[ScoreHarmonySlice]:
        for s in self.slices:
            if s.measure == measure:
                return s
        return None

    def section_for_measure(self, measure: int) -> Optional[ScoreFormSection]:
        for sec in self.sections:
            if sec.contains(measure):
                return sec
        return None

    def cadences_for_measure(self, measure: int) -> List[ScoreCadenceSpan]:
        return [c for c in self.cadences
                if c.start_measure <= measure <= c.end_measure]

    def annotated_measures(self) -> List[int]:
        return sorted(s.measure for s in self.slices)

    def chromatic_measures(self) -> List[int]:
        return sorted(s.measure for s in self.slices if s.is_chromatic)

    # -- validation -----------------------------------------------------
    def validate(self) -> None:
        if not self.score_id:
            raise ValueError("ScoreAnalysisResult.score_id is required")
        canon_mode(self.mode)  # raises nothing, normalises; key parse below
        if self.key:
            parse_key(self.key)
        seen = set()
        for s in self.slices:
            s.validate()
            if s.score_id and s.score_id != self.score_id:
                raise ValueError(
                    f"slice score_id {s.score_id!r} != result score_id "
                    f"{self.score_id!r}")
            if s.measure in seen:
                raise ValueError(f"duplicate slice for measure {s.measure}")
            seen.add(s.measure)
        for c in self.cadences:
            c.validate()
        for sec in self.sections:
            sec.validate()

    # -- serialisation --------------------------------------------------
    def to_dict(self) -> Dict:
        return {
            "schema": SCORE_ANALYSIS_SCHEMA,
            "scoreId": self.score_id,
            "title": self.title,
            "composer": self.composer,
            "key": self.key,
            "mode": self.mode,
            "measureCount": self.measure_count,
            "slices": [s.to_dict() for s in self.slices],
            "cadences": [c.to_dict() for c in self.cadences],
            "sections": [sec.to_dict() for sec in self.sections],
            "globalSummary": self.global_summary,
            "scoreGraphTemplateId": self.score_graph_template_id,
            "annotatedMeasures": self.annotated_measures(),
            "chromaticMeasures": self.chromatic_measures(),
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "ScoreAnalysisResult":
        sid = d.get("scoreId") or d.get("score_id") or ""
        return cls(
            score_id=sid,
            title=d.get("title", "") or "",
            composer=d.get("composer", "") or "",
            key=d.get("key", "C") or "C",
            mode=d.get("mode", "major") or "major",
            slices=[ScoreHarmonySlice.from_dict(s, sid)
                    for s in d.get("slices", [])],
            cadences=[ScoreCadenceSpan.from_dict(c, sid)
                      for c in d.get("cadences", [])],
            sections=[ScoreFormSection.from_dict(s)
                      for s in d.get("sections", [])],
            global_summary=d.get("globalSummary", d.get("global_summary", "")) or "",
            score_graph_template_id=d.get(
                "scoreGraphTemplateId",
                d.get("score_graph_template_id", "score_soul_radial_v1"))
            or "score_soul_radial_v1",
        )

    def resolve_refs(self) -> "ScoreAnalysisResult":
        """Fill every slice's ``atlas_refs`` / ``network_refs`` in place.

        Idempotent: a slice that already carries refs (curated) is left as-is.
        Returns ``self`` for chaining.
        """
        for s in self.slices:
            resolve_slice_refs(s)
        return self


# ---------------------------------------------------------------------------
# Bridge: slice -> Atlas / Harmonic Network
# ---------------------------------------------------------------------------

def diatonic_triad_match(key: str, mode: str, root: Optional[str],
                         quality: Optional[str]) -> Optional[DiatonicTriad]:
    """Find the diatonic triad of ``key``/``mode`` matching ``root`` pc + quality.

    Matching is by pitch class (enharmonic-tolerant) and, when given, quality.
    Returns ``None`` for a chord with no diatonic-triad reading (e.g. a
    secondary dominant or an applied diminished 7th in the score key).
    """
    if not (key and root):
        return None
    cmode = canon_mode(mode)
    tonic = _tonic_of(key)
    try:
        triads = generate_diatonic_triads(tonic, cmode)
        root_pc = note_pc(root)
    except Exception:
        return None
    q = (quality or "").strip().lower()
    for t in triads:
        if note_pc(t.root) != root_pc:
            continue
        if q and t.chord_quality != q:
            # A chord that merely shares the degree root but has a different
            # quality (e.g. a D-major chord on the ii degree of C) is NOT that
            # diatonic triad.
            continue
        return t
    return None


def slice_to_atlas_annotation(sl: ScoreHarmonySlice):
    """Build a :class:`harmony.atlas.HarmonyAnnotation` from a slice.

    Uses ``base_roman`` (the bare triad numeral) so the existing
    :meth:`Atlas.node_for_annotation` (exact-roman match) resolves it.
    """
    from harmony.atlas import HarmonyAnnotation  # lazy
    cmode = canon_mode(sl.mode)
    return HarmonyAnnotation(
        offset=sl.beat_start,
        measure=sl.measure,
        key=f"{_tonic_of(sl.key)} {('minor' if cmode == 'natural_minor' else 'major')}",
        mode=cmode,
        roman=sl.base_roman,
        chord_symbol=sl.chord_symbol,
        quality=sl.quality_or_none(),
        chord_tones=list(sl.chord_tones),
        function_label=sl.function_label,
        interval_layer=sl.interval_layer,
    )


def _triad_for_roman(key: str, mode: str,
                     base_roman: Optional[str]) -> Optional[DiatonicTriad]:
    """The diatonic triad whose bare roman == ``base_roman`` (exact match).

    Mirrors how :meth:`Atlas.node_for_annotation` resolves a roman, so a curated
    ``base_roman`` lands on exactly the Atlas triad node it intends.
    """
    if not (key and base_roman):
        return None
    tonic = _tonic_of(key)
    try:
        triads = generate_diatonic_triads(tonic, canon_mode(mode))
    except Exception:
        return None
    for t in triads:
        if t.roman == base_roman:
            return t
    return None


def atlas_refs_for(key: str, mode: str, root: Optional[str], quality: Optional[str],
                   base_roman: Optional[str] = None,
                   function_label: Optional[str] = None) -> List[str]:
    """Atlas node ids a chord maps to (only ids that actually exist).

    Always includes the score key's ``scale`` node.  A ``triad``/``function``/
    ``quality``/``layer`` mapping is added **only when the curator supplies a
    ``base_roman``** that resolves to a diatonic triad -- this is the explicit,
    honest switch: a chromatic chord whose triad merely *coincides* with a
    diatonic one (e.g. ``C7`` = V7/IV, triad = C major = I) is left ``base_roman
    = None`` and never claims the tonic node.
    """
    from harmony.atlas import (  # lazy
        build_atlas, scale_id, triad_id, function_id, quality_id, layer_id,
    )
    atlas = build_atlas()
    cmode = canon_mode(mode)
    tonic = _tonic_of(key)
    refs: List[str] = []

    def add(nid: Optional[str]) -> None:
        if nid and atlas.node(nid) is not None and nid not in refs:
            refs.append(nid)

    add(scale_id(tonic, cmode))

    triad = _triad_for_roman(key, mode, base_roman)
    if triad is not None:
        add(triad_id(tonic, cmode, triad.degree_index))
        add(function_id(cmode, triad.function_label))
        add(quality_id(triad.chord_quality))
        add(layer_id(triad.interval_layer))
    else:
        if quality:
            add(quality_id(quality))
        if function_label:
            add(function_id(cmode, function_label))
    return refs


# -- Harmonic Network ------------------------------------------------------

_NETWORK_PC_INDEX: Optional[Dict[int, Dict[str, str]]] = None


def _network_pc_index() -> Dict[int, Dict[str, str]]:
    """``{pitch_class: {kind: node_id}}`` over the live Harmonic Network.

    Mirrors the JS ``pcIndex`` the network UI builds, so Python-resolved
    ``network_refs`` match exactly what ``highlightFromTrainerTarget`` lights up.
    """
    global _NETWORK_PC_INDEX
    if _NETWORK_PC_INDEX is not None:
        return _NETWORK_PC_INDEX
    from harmony.harmonic_network import build_network  # lazy
    from harmony.network_template import get_template
    payload = build_network(get_template(
        "dominant_diminished_relative_network_v1")).to_payload()
    idx: Dict[int, Dict[str, str]] = {}
    for n in payload["nodes"]:
        pc = n.get("pitchClass")
        if pc is None:
            continue
        idx.setdefault(int(pc), {})[n["kind"]] = n["id"]
    _NETWORK_PC_INDEX = idx
    return idx


def network_target_for(sl: ScoreHarmonySlice) -> Dict:
    """The ``{key,mode,roman,root,quality}`` object for the Network highlight."""
    cmode = canon_mode(sl.mode)
    return {
        "key": f"{_tonic_of(sl.key)} {('minor' if cmode == 'natural_minor' else 'major')}",
        "mode": "minor" if cmode == "natural_minor" else "major",
        "roman": sl.roman or sl.base_roman or "",
        "root": sl.inferred_root or "",
        "quality": sl.chord_quality_hint() or "",
    }


def network_refs_for(key: str, mode: str, roman: Optional[str],
                     root: Optional[str], quality: Optional[str]) -> List[str]:
    """Harmonic-Network node ids a chord highlights.

    Re-implements the JS ``highlightFromTrainerTarget`` resolution in Python so
    the stored refs equal the live highlight set: the most-specific chord node
    (``dom7``/``dim``) first, then the mode-aware key-context node.
    """
    idx = _network_pc_index()
    tonic = _tonic_of(key)
    try:
        key_pc = note_pc(tonic)
    except Exception:
        return []
    cmode = canon_mode(mode)
    minor = cmode == "natural_minor"
    key_slot = idx.get(key_pc, {})
    key_node = (key_slot.get("minor_key") if minor and key_slot.get("minor_key")
                else key_slot.get("major_key"))

    root_pc: Optional[int]
    try:
        root_pc = note_pc(root) if root else None
    except Exception:
        root_pc = None

    rl = (roman or "").lower()
    q = (quality or "").lower()
    is_dim = (q == "diminished") or (not q and "°" in rl)
    is_dom = rl[:1] == "v" and rl[1:2] != "i"

    primary: Optional[str] = None
    if is_dim:
        dim_pc = root_pc if root_pc is not None else (key_pc + 11) % 12
        primary = idx.get(dim_pc, {}).get("diminished_triad")
    elif is_dom:
        dom_pc = root_pc if root_pc is not None else (key_pc + 7) % 12
        primary = idx.get(dom_pc, {}).get("dominant_seventh")

    ids: List[str] = []
    if primary:
        ids.append(primary)
    if key_node and key_node not in ids:
        ids.append(key_node)
    if not ids:
        slot = idx.get(key_pc, {})
        first = (slot.get("major_key") or slot.get("minor_key")
                 or slot.get("dominant_seventh") or slot.get("diminished_triad"))
        if first:
            ids.append(first)
    return ids


def atlas_sync_target(sl: ScoreHarmonySlice) -> Dict:
    """A target dict for :meth:`harmony.atlas.Atlas.sync` (drives Atlas highlight).

    Carries the fields ``Atlas.sync`` reads (key/mode/roman/quality/
    intervalLayer/functionLabel/degreeNumber).  For a diatonic slice these come
    from the matched triad so the Atlas lights scale+degree+triad+quality+layer+
    function; for a chromatic slice only scale (+function) light up -- honest.
    """
    cmode = canon_mode(sl.mode)
    tonic = _tonic_of(sl.key)
    triad = _triad_for_roman(sl.key or "", sl.mode or "major", sl.base_roman)
    return {
        "key": f"{tonic} {('minor' if cmode == 'natural_minor' else 'major')}",
        "mode": cmode,
        "roman": (sl.base_roman if triad is not None else None),
        "quality": (triad.chord_quality if triad is not None else None),
        "intervalLayer": (triad.interval_layer if triad is not None else None),
        "functionLabel": (triad.function_label if triad is not None
                          else sl.function_label),
        "degreeNumber": (triad.degree_number if triad is not None else None),
    }


def resolve_slice_refs(sl: ScoreHarmonySlice) -> ScoreHarmonySlice:
    """Populate a slice's atlas/network refs (idempotent; never clobbers curated).

    A slice that already has refs is left untouched -- curated refs win.
    """
    if not sl.atlas_refs:
        sl.atlas_refs = atlas_refs_for(
            sl.key or "", sl.mode or "major", sl.inferred_root,
            sl.chord_quality_hint(), sl.base_roman, sl.function_label)
    if not sl.network_refs:
        tgt = network_target_for(sl)
        sl.network_refs = network_refs_for(
            tgt["key"], tgt["mode"], tgt["roman"], tgt["root"], tgt["quality"])
    return sl
