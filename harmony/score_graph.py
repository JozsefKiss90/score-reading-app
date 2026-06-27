"""Score-specific harmonic graph -- the piece's "soul graph" / mandala (Phase 4).

Builds a radial graph from a :class:`harmony.score_analysis.ScoreAnalysisResult`.
This is NOT the general Harmonic Network (the tonal *universe*): it is ONE
piece's *path* through that universe -- its measures, its recurring harmonies,
its cadences, and the bridges (``maps_to_atlas`` / ``maps_to_network``) back to
the universal Atlas / Network nodes.

Layout (all geometry computed here in Python; the JS renderer does zero layout
math, exactly like :mod:`harmony.harmonic_network`):

* the SCORE sits at the centre;
* MEASURES are ordered clockwise around the outer ring (a clock face of the
  piece in time), starting at 12 o'clock;
* FORM SECTIONS are large arcs on the outermost ring;
* recurring harmonies (CHORD / ROMAN / FUNCTION / KEY-AREA nodes) cluster
  *inward* at the angular centroid of the measures that use them -- so a chord
  heard many times becomes a hub;
* FUNCTION nodes occupy fixed regions so the tonic and dominant areas are
  visually distinguishable (tonic up, dominant down, pre-dominant left,
  mediant/colour right);
* CADENCES are drawn as directional ``resolves_to`` paths plus
  ``cadential_member_of`` spokes.

Node types: ``score form_section measure harmony_slice chord roman function
cadence key_area atlas_ref network_ref``.
Edge relations: ``occurs_in follows prolongs resolves_to prepares
cadential_member_of maps_to_atlas maps_to_network belongs_to_section``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from harmony.score_analysis import ScoreAnalysisResult, ScoreHarmonySlice, canon_mode

__all__ = [
    "SCORE_GRAPH_SCHEMA",
    "NODE_TYPES",
    "EDGE_RELATIONS",
    "ScoreGraphNode",
    "ScoreGraphEdge",
    "ScoreGraph",
    "build_score_graph",
]

SCORE_GRAPH_SCHEMA = "score-graph/v1"

NODE_TYPES = (
    "score", "form_section", "measure", "harmony_slice", "chord", "roman",
    "function", "cadence", "key_area", "atlas_ref", "network_ref",
)

EDGE_RELATIONS = (
    "occurs_in", "follows", "prolongs", "resolves_to", "prepares",
    "cadential_member_of", "maps_to_atlas", "maps_to_network",
    "belongs_to_section",
)

#: Ring radii (px) from the centre outward.
_R_FUNCTION = 120.0
_R_ROMAN = 210.0
_R_CHORD = 300.0
_R_KEY = 360.0
_R_SLICE = 430.0
_R_MEASURE = 520.0
_R_SECTION = 600.0
_R_ATLAS = 670.0
_R_NETWORK = 740.0
_MARGIN = 70.0

#: Fixed angle (degrees, 0 = 3 o'clock, CCW positive in math space but we render
#: clockwise) per broad function, so tonic/dominant regions are distinguishable.
_FUNCTION_ANGLE = {
    "tonic": -90.0,         # top
    "dominant": 90.0,       # bottom
    "predominant": 180.0,   # left
    "subdominant": 200.0,   # left-ish
    "mediant": 0.0,         # right
    "submediant": 20.0,     # right-ish
    "subtonic": 60.0,
}

_FUNCTION_VISUAL = {
    "tonic": "tonic",
    "dominant": "dominant",
    "predominant": "predominant",
    "subdominant": "predominant",
    "mediant": "mediant",
    "submediant": "mediant",
    "subtonic": "dominant",
}

#: Function-family labels treated as dominant / pre-dominant / tonic for the
#: harmonic-motion edges.
_DOMINANT_FUNCS = {"dominant", "subtonic"}
_PREDOMINANT_FUNCS = {"predominant", "subdominant"}
_TONIC_FUNCS = {"tonic", "mediant", "submediant"}


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _measure_angle(measure: int, count: int) -> float:
    """Clockwise angle (degrees) for a measure on the clock face (12 o'clock=top)."""
    if count <= 0:
        return -90.0
    return -90.0 + 360.0 * (measure - 1) / count


def _polar(cx: float, cy: float, radius: float, angle_deg: float) -> Tuple[float, float]:
    a = math.radians(angle_deg)
    return (round(cx + radius * math.cos(a), 2),
            round(cy + radius * math.sin(a), 2))


def _circular_mean(angles_deg: List[float]) -> float:
    if not angles_deg:
        return -90.0
    sx = sum(math.cos(math.radians(a)) for a in angles_deg)
    sy = sum(math.sin(math.radians(a)) for a in angles_deg)
    if abs(sx) < 1e-9 and abs(sy) < 1e-9:
        return angles_deg[0]
    return math.degrees(math.atan2(sy, sx))


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

@dataclass
class ScoreGraphNode:
    id: str
    type: str
    label: str
    x: float = 0.0
    y: float = 0.0
    radius: float = 10.0
    visual_class: str = "default"
    measure: Optional[int] = None
    data: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "x": self.x,
            "y": self.y,
            "radius": self.radius,
            "visualClass": self.visual_class,
            "measure": self.measure,
            "data": self.data,
        }


@dataclass
class ScoreGraphEdge:
    source: str
    target: str
    relation: str
    direction: str = "directed"
    label: str = ""

    @property
    def id(self) -> str:
        return f"{self.source}|{self.relation}|{self.target}"

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "direction": self.direction,
            "label": self.label,
        }


@dataclass
class ScoreGraph:
    score_id: str
    title: str
    nodes: List[ScoreGraphNode] = field(default_factory=list)
    edges: List[ScoreGraphEdge] = field(default_factory=list)
    width: float = 1600.0
    height: float = 1600.0
    center: Tuple[float, float] = (800.0, 800.0)

    # -- access ---------------------------------------------------------
    def node(self, node_id: str) -> Optional[ScoreGraphNode]:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def nodes_of_type(self, t: str) -> List[ScoreGraphNode]:
        return [n for n in self.nodes if n.type == t]

    def edges_of_relation(self, r: str) -> List[ScoreGraphEdge]:
        return [e for e in self.edges if e.relation == r]

    def measure_nodes(self) -> List[ScoreGraphNode]:
        return sorted(self.nodes_of_type("measure"),
                      key=lambda n: n.measure or 0)

    # -- counts / payload ----------------------------------------------
    def counts(self) -> Dict:
        by_type: Dict[str, int] = {}
        for n in self.nodes:
            by_type[n.type] = by_type.get(n.type, 0) + 1
        by_rel: Dict[str, int] = {}
        for e in self.edges:
            by_rel[e.relation] = by_rel.get(e.relation, 0) + 1
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "nodesByType": by_type,
            "edgesByRelation": by_rel,
        }

    def legend(self) -> Dict:
        return {
            "nodeTypes": [
                {"type": "score", "label": "Score", "visualClass": "score"},
                {"type": "form_section", "label": "Form section", "visualClass": "section"},
                {"type": "measure", "label": "Measure", "visualClass": "measure"},
                {"type": "harmony_slice", "label": "Harmony slice", "visualClass": "slice"},
                {"type": "chord", "label": "Chord", "visualClass": "chord"},
                {"type": "roman", "label": "Roman numeral", "visualClass": "roman"},
                {"type": "function", "label": "Function", "visualClass": "function"},
                {"type": "cadence", "label": "Cadence", "visualClass": "cadence"},
                {"type": "key_area", "label": "Key area", "visualClass": "key"},
                {"type": "atlas_ref", "label": "Atlas node", "visualClass": "atlas"},
                {"type": "network_ref", "label": "Network node", "visualClass": "network"},
            ],
            "edgeRelations": [
                {"relation": r, "label": r.replace("_", " ")}
                for r in EDGE_RELATIONS
            ],
            "regions": [
                {"visualClass": "tonic", "label": "Tonic region (top)"},
                {"visualClass": "dominant", "label": "Dominant region (bottom)"},
                {"visualClass": "predominant", "label": "Pre-dominant (left)"},
                {"visualClass": "mediant", "label": "Colour/mediant (right)"},
                {"visualClass": "chromatic", "label": "Chromatic / unsupported"},
                {"visualClass": "ambiguous", "label": "Ambiguous"},
            ],
        }

    def to_payload(self) -> Dict:
        return {
            "schema": SCORE_GRAPH_SCHEMA,
            "scoreId": self.score_id,
            "title": self.title,
            "width": self.width,
            "height": self.height,
            "center": {"x": self.center[0], "y": self.center[1]},
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "counts": self.counts(),
            "legend": self.legend(),
        }


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def _slice_visual(sl: ScoreHarmonySlice) -> str:
    if sl.status == "unsupported_chromatic":
        return "chromatic"
    if sl.status == "ambiguous":
        return "ambiguous"
    return _FUNCTION_VISUAL.get((sl.function_label or "").lower(), "tonic")


def build_score_graph(result: ScoreAnalysisResult) -> ScoreGraph:
    """Build the radial "soul graph" for a curated score analysis."""
    outer = _R_NETWORK + _MARGIN
    size = 2 * outer
    cx = cy = outer
    g = ScoreGraph(score_id=result.score_id,
                   title=result.title or result.score_id,
                   width=round(size, 1), height=round(size, 1),
                   center=(round(cx, 1), round(cy, 1)))

    slices = sorted(result.slices, key=lambda s: s.measure)
    count = result.measure_count or (len(slices) or 1)

    # -- centre: the score --------------------------------------------
    score_id = f"score:{result.score_id}"
    g.nodes.append(ScoreGraphNode(
        id=score_id, type="score", label=result.title or result.score_id,
        x=round(cx, 2), y=round(cy, 2), radius=26.0, visual_class="score",
        data={"key": result.key, "mode": result.mode,
              "composer": result.composer,
              "summary": result.global_summary,
              "measureCount": count}))

    # angle per measure (for centroid clustering of inner nodes)
    angle_of_measure = {s.measure: _measure_angle(s.measure, count) for s in slices}

    # -- inner identity hubs (function / roman / chord / key_area) -----
    def _hub(prefix: str, key: str, label: str, radius_ring: float,
             visual: str, members: List[int], data: Dict) -> str:
        nid = f"{prefix}:{key}"
        if g.node(nid) is None:
            ang = _circular_mean([angle_of_measure[m] for m in members
                                  if m in angle_of_measure])
            x, y = _polar(cx, cy, radius_ring, ang)
            g.nodes.append(ScoreGraphNode(
                id=nid, type=prefix if prefix in NODE_TYPES else "chord",
                label=label, x=x, y=y, radius=14.0, visual_class=visual,
                data=data))
        return nid

    # group measures by chord / roman / function
    by_chord: Dict[str, List[int]] = {}
    by_roman: Dict[str, List[int]] = {}
    by_function: Dict[str, List[int]] = {}
    for s in slices:
        if s.chord_symbol:
            by_chord.setdefault(s.chord_symbol, []).append(s.measure)
        if s.roman:
            by_roman.setdefault(s.roman, []).append(s.measure)
        if s.function_label:
            by_function.setdefault(s.function_label.lower(), []).append(s.measure)

    for func, members in by_function.items():
        ang = _FUNCTION_ANGLE.get(func, _circular_mean(
            [angle_of_measure[m] for m in members]))
        x, y = _polar(cx, cy, _R_FUNCTION, ang)
        nid = f"function:{func}"
        g.nodes.append(ScoreGraphNode(
            id=nid, type="function", label=func, x=x, y=y, radius=18.0,
            visual_class=_FUNCTION_VISUAL.get(func, "tonic"),
            data={"function": func, "measures": sorted(members)}))

    for roman, members in by_roman.items():
        fl = next((s.function_label for s in slices if s.roman == roman), "")
        _hub("roman", roman, roman, _R_ROMAN,
             _FUNCTION_VISUAL.get((fl or "").lower(), "tonic"),
             members, {"roman": roman, "measures": sorted(members)})

    for chord, members in by_chord.items():
        fl = next((s.function_label for s in slices if s.chord_symbol == chord), "")
        _hub("chord", chord, chord, _R_CHORD,
             _FUNCTION_VISUAL.get((fl or "").lower(), "tonic"),
             members, {"chordSymbol": chord, "measures": sorted(members)})

    # -- key areas (one per section tonal area, + the global key) ------
    key_area_ids: Dict[str, str] = {}
    global_area = f"{result.key} {result.mode}"
    for sec in result.sections:
        area = sec.tonal_area or global_area
        if area in key_area_ids:
            continue
        members = [s.measure for s in slices
                   if sec.start_measure <= s.measure <= sec.end_measure]
        nid = _hub("key_area", area.replace(" ", "_"), area, _R_KEY, "key",
                   members or [sec.start_measure],
                   {"tonalArea": area})
        key_area_ids[area] = nid
    if not key_area_ids:
        nid = _hub("key_area", global_area.replace(" ", "_"), global_area,
                   _R_KEY, "key", [s.measure for s in slices], {"tonalArea": global_area})
        key_area_ids[global_area] = nid
    for nid in key_area_ids.values():
        g.edges.append(ScoreGraphEdge(nid, score_id, "occurs_in"))

    # -- form sections (outer arcs) -----------------------------------
    section_ids: List[Tuple[str, "object"]] = []
    for i, sec in enumerate(result.sections):
        mid = (sec.start_measure + sec.end_measure) / 2.0
        ang = _measure_angle(mid, count)
        x, y = _polar(cx, cy, _R_SECTION, ang)
        nid = f"section:{i}"
        g.nodes.append(ScoreGraphNode(
            id=nid, type="form_section", label=sec.label, x=x, y=y,
            radius=20.0, visual_class="section",
            measure=sec.start_measure,
            data={"startMeasure": sec.start_measure,
                  "endMeasure": sec.end_measure,
                  "tonalArea": sec.tonal_area,
                  "description": sec.description}))
        section_ids.append((nid, sec))
        g.edges.append(ScoreGraphEdge(nid, score_id, "occurs_in"))

    def _section_for(measure: int) -> Optional[str]:
        for nid, sec in section_ids:
            if sec.contains(measure):
                return nid
        return None

    # -- measures + slices --------------------------------------------
    slice_node_by_measure: Dict[int, str] = {}
    for s in slices:
        ang = angle_of_measure[s.measure]
        mx, my = _polar(cx, cy, _R_MEASURE, ang)
        m_nid = f"measure:{s.measure}"
        g.nodes.append(ScoreGraphNode(
            id=m_nid, type="measure", label=f"m{s.measure}", x=mx, y=my,
            radius=16.0, visual_class=_slice_visual(s), measure=s.measure,
            data={"roman": s.roman, "chordSymbol": s.chord_symbol,
                  "status": s.status, "function": s.function_label}))

        sx, sy = _polar(cx, cy, _R_SLICE, ang)
        s_nid = f"slice:{s.measure}"
        slice_node_by_measure[s.measure] = s_nid
        g.nodes.append(ScoreGraphNode(
            id=s_nid, type="harmony_slice", label=s.roman or s.chord_symbol or "?",
            x=sx, y=sy, radius=12.0, visual_class=_slice_visual(s),
            measure=s.measure,
            data={"roman": s.roman, "baseRoman": s.base_roman,
                  "chordSymbol": s.chord_symbol, "root": s.inferred_root,
                  "function": s.function_label, "status": s.status,
                  "confidence": s.confidence, "explanation": s.explanation,
                  "notes": list(s.notes), "chordTones": list(s.chord_tones),
                  "atlasRefs": list(s.atlas_refs),
                  "networkRefs": list(s.network_refs)}))

        # containment edges
        g.edges.append(ScoreGraphEdge(s_nid, m_nid, "occurs_in"))
        sec_nid = _section_for(s.measure)
        if sec_nid:
            g.edges.append(ScoreGraphEdge(m_nid, sec_nid, "belongs_to_section"))
        sec = result.section_for_measure(s.measure)
        area = (sec.tonal_area if sec and sec.tonal_area else global_area)
        if area in key_area_ids:
            g.edges.append(ScoreGraphEdge(s_nid, key_area_ids[area], "occurs_in"))

        # identity edges (chord/roman/function -> slice)
        if s.chord_symbol:
            g.edges.append(ScoreGraphEdge(
                f"chord:{s.chord_symbol}", s_nid, "occurs_in"))
        if s.roman:
            g.edges.append(ScoreGraphEdge(f"roman:{s.roman}", s_nid, "occurs_in"))
        if s.function_label:
            g.edges.append(ScoreGraphEdge(
                f"function:{s.function_label.lower()}", s_nid, "occurs_in"))

        # external bridges
        for ref in s.atlas_refs:
            nid = f"atlas_ref:{ref}"
            if g.node(nid) is None:
                rx, ry = _polar(cx, cy, _R_ATLAS, ang)
                g.nodes.append(ScoreGraphNode(
                    id=nid, type="atlas_ref", label=ref, x=rx, y=ry,
                    radius=9.0, visual_class="atlas", data={"atlasId": ref}))
            g.edges.append(ScoreGraphEdge(s_nid, nid, "maps_to_atlas"))
        for ref in s.network_refs:
            nid = f"network_ref:{ref}"
            if g.node(nid) is None:
                rx, ry = _polar(cx, cy, _R_NETWORK, ang)
                g.nodes.append(ScoreGraphNode(
                    id=nid, type="network_ref", label=ref, x=rx, y=ry,
                    radius=9.0, visual_class="network", data={"networkId": ref}))
            g.edges.append(ScoreGraphEdge(s_nid, nid, "maps_to_network"))

    # -- timeline + harmonic-motion edges between measures ------------
    for a, b in zip(slices, slices[1:]):
        g.edges.append(ScoreGraphEdge(
            f"measure:{a.measure}", f"measure:{b.measure}", "follows"))
        fa = (a.function_label or "").lower()
        fb = (b.function_label or "").lower()
        if fa in _DOMINANT_FUNCS and fb in _TONIC_FUNCS:
            g.edges.append(ScoreGraphEdge(
                f"measure:{a.measure}", f"measure:{b.measure}", "resolves_to"))
        elif fa in _PREDOMINANT_FUNCS and fb in _DOMINANT_FUNCS:
            g.edges.append(ScoreGraphEdge(
                f"measure:{a.measure}", f"measure:{b.measure}", "prepares"))

    # prolongation: a chord recurring -> link each occurrence to its next
    for chord, members in by_chord.items():
        ms = sorted(members)
        for a, b in zip(ms, ms[1:]):
            g.edges.append(ScoreGraphEdge(
                f"measure:{a}", f"measure:{b}", "prolongs",
                label=chord))

    # -- cadences ------------------------------------------------------
    for i, cad in enumerate(result.cadences):
        mid = (cad.start_measure + cad.end_measure) / 2.0
        ang = _measure_angle(mid, count)
        x, y = _polar(cx, cy, _R_SLICE - 40.0, ang)
        nid = f"cadence:{i}"
        g.nodes.append(ScoreGraphNode(
            id=nid, type="cadence",
            label=cad.cadence_type or "-".join(cad.pattern),
            x=x, y=y, radius=15.0, visual_class="cadence",
            measure=cad.start_measure,
            data={"cadenceType": cad.cadence_type, "pattern": list(cad.pattern),
                  "romans": list(cad.romans), "startMeasure": cad.start_measure,
                  "endMeasure": cad.end_measure, "explanation": cad.explanation,
                  "atlasRef": cad.atlas_cadence_ref(result.mode)}))
        for m in range(cad.start_measure, cad.end_measure + 1):
            if g.node(f"measure:{m}") is not None:
                g.edges.append(ScoreGraphEdge(
                    f"measure:{m}", nid, "cadential_member_of"))

    return g
