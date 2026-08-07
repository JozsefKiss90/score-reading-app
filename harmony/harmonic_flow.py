"""Shared data contracts for the Harmonic Network bidirectional graph<->drill mapping.

This module is the pure, headless heart of the *drill projection* system described in
``HARMONIC_NETWORK_BIDIRECTIONAL_MAPPING_IMPLEMENTATION_PLAN.md``. It owns the controlled
vocabularies and the intermediate model that both directions of the mapping share:

    * **Drill -> Graph** (``harmony.network_projection``) compiles a running exercise into a
      :class:`DrillGraphProjection` of ordered :class:`HarmonicStep` occurrences plus
      :class:`HarmonicTransition` edges.
    * **Graph -> Drill** (``harmony.network_launch``) turns a graph selection into a
      :class:`LaunchAction` carrying a preview :class:`DrillGraphProjection`.

Nothing in here imports Qt, JavaScript, MusicXML, music21, or does any file I/O. Everything is
deterministic: no ``random``, no wall-clock time. IDs are stable and content-addressable so a
repeated canonical node can appear as two distinct *occurrences* pointing at one graph node.

Terminology (see plan section 23.8) -- keep these distinct:

    key anchor        a tonal-centre node (a key), never a chord instance
    chord instance    a concrete triad node in the canonical graph
    occurrence        one position of a chord in a running drill (``HarmonicStep``)
    projection proxy  a temporary overlay node for a chord the active template cannot draw
    theory edge       a canonical, asserted harmonic relation (resolves_to, prepares, ...)
    sequence edge     a runtime "this is simply the next drill item" overlay (drill_next, ...)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# --------------------------------------------------------------------------------------------- #
# Schema tags
# --------------------------------------------------------------------------------------------- #

PROJECTION_SCHEMA = "harmony-network-projection/v1"
REQUEST_SCHEMA = "harmony-graph-drill-request/v1"
LAUNCH_SCHEMA = "harmony-network-launch/v1"


# --------------------------------------------------------------------------------------------- #
# Controlled vocabularies (plan sections 3, 4, 6, 7, 8)
# --------------------------------------------------------------------------------------------- #

#: One controlled thematic vocabulary shared by both mapping directions (plan section 3).
THEMATIC_GROUPS = frozenset({
    "node_identity",
    "tonal_field",
    "functional_neighbourhood",
    "relation_pair",
    "functional_path",
    "transposition_orbit",
    "quality_class",
    "functional_equivalence",
    "inversion_space",
    "modulation_path",
})

#: Ontological level of a *canonical* node (plan section 7).
SEMANTIC_LEVELS = frozenset({"key", "chord", "function", "class", "voicing", "path"})

#: Role a node plays within its semantic level (plan section 7).
ENTITY_ROLES = frozenset({"anchor", "instance", "family", "state", "reference"})

#: Mapping confidence between a drill chord and a graph node (plan section 8.3). Never map a
#: chord to a merely similar node without declaring the status.
MAPPING_STATUS = frozenset({"exact", "contextual", "approximate", "unmapped", "unsupported"})

#: What kind of entity a step maps onto (plan section 6.1 / 9.2).
MAPPING_TYPES = frozenset({
    "chord_instance", "key_context", "class", "voicing_state", "implied_chord",
})

#: How a drill orders its items -- only some orderings are genuine harmonic motion (plan section 4).
SEQUENCE_SEMANTICS = frozenset({
    "pedagogical_enumeration",  # full_key: I ii iii ... is enumeration, NOT progression
    "transposition",            # horizontal_degree: same degree across keys
    "class_enumeration",        # quality: members of a quality class
    "harmonic_motion",          # function / cadence: real progression
    "voicing_change",           # inversion: same chord, changing bass
    "implied_harmony",          # polyphonic: implied chord per slice
    "score_time",               # real-score slice stream
})

#: The sequence semantics under which a transition may carry a canonical *theory* relation. The
#: enumeration / transposition / class orderings are pedagogical and must NEVER assert a
#: theoretical harmonic edge (plan section 4.1 "Critical rule").
MOTION_CAPABLE_SEMANTICS = frozenset({
    "harmonic_motion", "voicing_change", "implied_harmony", "score_time",
})

#: Runtime *sequence* relations on a :class:`ProjectionEdge`. These are deliberately kept OUT of
#: the canonical ``NetEdge`` relation vocabulary (plan section 13.3).
SEQUENCE_RELATIONS = frozenset({
    "drill_next", "transpose_next", "enumerate_next", "voicing_next",
})

#: Canonical *theory* relations a :class:`HarmonicTransition` may assert. A superset-compatible
#: subset of the network's ``IMPLEMENTED_RELATIONS`` plus the inversion/voice-leading relations.
THEORY_RELATIONS = frozenset({
    "resolves_to", "prepares", "prolongs", "leading_tone_to", "dominant_of",
    "substitutes_for", "inversion_of", "voice_leads_to",
})

#: Status of a transition's relation (plan section 6.2).
RELATION_STATUS = frozenset({"exact", "inferred", "sequence_only", "unsupported"})

#: Origin of a projection (plan section 6.1).
SOURCE_KINDS = frozenset({"harmony_exercise", "lab", "score"})

#: Kinds of purely-visual overlay node (plan section 6.3).
PROJECTION_NODE_KINDS = frozenset({"proxy_triad", "occurrence_marker", "proxy_voicing"})

#: Launch-action targets / statuses / interaction kinds (plan sections 6.6, 6.7).
LAUNCH_TARGETS = frozenset({"trainer", "lab"})
LAUNCH_STATUS = frozenset({"launchable", "reserved", "unavailable"})
INTERACTION_KINDS = frozenset({"node", "edge", "path", "constellation"})
SPEC_TYPES = frozenset({"harmony_exercise", "lab_experiment"})


#: Default ``(thematic_group, sequence_semantics)`` per drill family (plan section 4 table). A
#: graph-launch action may override the thematic group; the projector applies these otherwise.
DRILL_FAMILY_DEFAULTS: Dict[str, Tuple[str, str]] = {
    "full_key": ("tonal_field", "pedagogical_enumeration"),
    "horizontal_degree": ("transposition_orbit", "transposition"),
    "quality": ("quality_class", "class_enumeration"),
    "function": ("functional_path", "harmonic_motion"),
    # Lab families
    "inversion": ("inversion_space", "voicing_change"),
    "cadence": ("functional_path", "harmonic_motion"),
    "voice_leading": ("functional_path", "harmonic_motion"),
    "polyphonic_harmony": ("functional_path", "implied_harmony"),
    # Real-score slice stream
    "score": ("functional_path", "score_time"),
}

#: The runtime sequence-edge relation each drill family uses between consecutive items
#: (plan section 9 step 7). ``function``/``cadence`` also *may* carry a theory relation on top.
SEQUENCE_RELATION_BY_FAMILY: Dict[str, str] = {
    "full_key": "enumerate_next",
    "horizontal_degree": "transpose_next",
    "quality": "enumerate_next",
    "function": "drill_next",
    "cadence": "drill_next",
    "voice_leading": "drill_next",
    "polyphonic_harmony": "drill_next",
    "inversion": "voicing_next",
    "score": "drill_next",
}


def default_group_for_drill(drill_family: str) -> str:
    """Default thematic group for a drill family (falls back to ``functional_path``)."""
    return DRILL_FAMILY_DEFAULTS.get(drill_family, ("functional_path", "harmonic_motion"))[0]


def default_sequence_semantics_for_drill(drill_family: str) -> str:
    """Default sequence semantics for a drill family (falls back to ``harmonic_motion``)."""
    return DRILL_FAMILY_DEFAULTS.get(drill_family, ("functional_path", "harmonic_motion"))[1]


def sequence_relation_for_drill(drill_family: str) -> str:
    """Runtime sequence-edge relation for a drill family (falls back to ``drill_next``)."""
    return SEQUENCE_RELATION_BY_FAMILY.get(drill_family, "drill_next")


# --------------------------------------------------------------------------------------------- #
# Stable ID helpers (plan sections 6.1, 6.3, 8.1)
# --------------------------------------------------------------------------------------------- #

def occurrence_id(source_id: str, group_index: int, index_in_group: int, sequence_index: int) -> str:
    """Content-addressable id for one chord *occurrence*.

    The same canonical node may occur more than once (e.g. the two ``I`` chords in ``I-IV-V-I``),
    so an occurrence id is NOT the node id -- it encodes position (plan section 6.1).
    """
    return f"occ:{source_id}:{group_index}:{index_in_group}:{sequence_index}"


def proxy_triad_id(tonic: str, mode: str, degree_index: int) -> str:
    """Overlay proxy id for a triad the active template cannot draw (plan section 6.3)."""
    return f"overlay:triad:{tonic}:{mode}:{degree_index}"


def proxy_applied_id(tonic: str, mode: str, roman: str) -> str:
    """Overlay proxy id for an applied dominant the active template cannot draw.

    Keyed by the applied *token* (``V7/V``), never by a scale degree: an applied chord has
    no degree of the home key, and reusing the triad proxy id would collide with the very
    diatonic chord it must never be confused with (ticket 18 / plan G5b).
    """
    return f"overlay:applied:{tonic}:{mode}:{roman.replace('/', '_of_')}"


def proxy_voicing_id(tonic: str, mode: str, degree_index: int, inversion: int) -> str:
    """Overlay proxy id for a single inversion/voicing state (plan section 6.3)."""
    return f"overlay:inversion:{tonic}:{mode}:{degree_index}:{inversion}"


def transition_id(from_occurrence: str, to_occurrence: str, relation: str) -> str:
    """Deterministic id for a sequence/theory transition between two occurrences."""
    return f"{from_occurrence}>{relation}>{to_occurrence}"


def is_proxy_node_id(node_id: str) -> bool:
    """True when ``node_id`` is a projection-only overlay id (``overlay:...``)."""
    return node_id.startswith("overlay:")


# --------------------------------------------------------------------------------------------- #
# Small (de)serialisation helpers -- projections are shipped to JS, so keys are camelCase.
# --------------------------------------------------------------------------------------------- #

def _list(value) -> List:
    return list(value) if value is not None else []


def _tuple_str(value) -> Tuple[str, ...]:
    return tuple(str(v) for v in value) if value else ()


def _tuple_int(value) -> Tuple[int, ...]:
    return tuple(int(v) for v in value) if value else ()


# --------------------------------------------------------------------------------------------- #
# HarmonicStep -- one drill occurrence (plan section 6.1)
# --------------------------------------------------------------------------------------------- #

@dataclass(frozen=True)
class HarmonicStep:
    """One chord occurrence in a running drill, mapped onto a canonical node or honest proxy."""

    occurrence_id: str
    sequence_index: int
    group_index: int
    index_in_group: int

    source_kind: str              # harmony_exercise | lab | score
    source_id: str                # exercise_id / experiment_id / score_id
    drill_family: str             # full_key | function | inversion | ...

    key_context: str              # "C major"
    tonic: str                    # "C"
    mode: str                     # major | natural_minor
    roman: str
    degree_index: Optional[int]
    chord_symbol: str
    root: str
    quality: str
    function_label: str
    interval_layer: str
    pitch_classes: Tuple[int, ...]
    chord_tones: Tuple[str, ...]

    semantic_group: str
    sequence_semantics: str

    atlas_refs: Tuple[str, ...]
    primary_network_node: Optional[str]
    context_network_nodes: Tuple[str, ...]
    visual_node_id: str           # canonical node id OR projection proxy id

    mapping_type: str             # chord_instance | key_context | class | voicing_state | implied_chord
    mapping_status: str           # exact | contextual | approximate | unmapped | unsupported
    mapping_reason: str

    bass_pitch_class: Optional[int] = None
    inversion: Optional[int] = None
    figured_bass: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "occurrenceId": self.occurrence_id,
            "sequenceIndex": self.sequence_index,
            "groupIndex": self.group_index,
            "indexInGroup": self.index_in_group,
            "sourceKind": self.source_kind,
            "sourceId": self.source_id,
            "drillFamily": self.drill_family,
            "keyContext": self.key_context,
            "tonic": self.tonic,
            "mode": self.mode,
            "roman": self.roman,
            "degreeIndex": self.degree_index,
            "chordSymbol": self.chord_symbol,
            "root": self.root,
            "quality": self.quality,
            "functionLabel": self.function_label,
            "intervalLayer": self.interval_layer,
            "pitchClasses": list(self.pitch_classes),
            "chordTones": list(self.chord_tones),
            "semanticGroup": self.semantic_group,
            "sequenceSemantics": self.sequence_semantics,
            "atlasRefs": list(self.atlas_refs),
            "primaryNetworkNode": self.primary_network_node,
            "contextNetworkNodes": list(self.context_network_nodes),
            "visualNodeId": self.visual_node_id,
            "mappingType": self.mapping_type,
            "mappingStatus": self.mapping_status,
            "mappingReason": self.mapping_reason,
            "bassPitchClass": self.bass_pitch_class,
            "inversion": self.inversion,
            "figuredBass": self.figured_bass,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "HarmonicStep":
        return cls(
            occurrence_id=d["occurrenceId"],
            sequence_index=int(d["sequenceIndex"]),
            group_index=int(d["groupIndex"]),
            index_in_group=int(d["indexInGroup"]),
            source_kind=d["sourceKind"],
            source_id=d["sourceId"],
            drill_family=d["drillFamily"],
            key_context=d["keyContext"],
            tonic=d["tonic"],
            mode=d["mode"],
            roman=d["roman"],
            degree_index=None if d.get("degreeIndex") is None else int(d["degreeIndex"]),
            chord_symbol=d["chordSymbol"],
            root=d["root"],
            quality=d["quality"],
            function_label=d["functionLabel"],
            interval_layer=d["intervalLayer"],
            pitch_classes=_tuple_int(d.get("pitchClasses")),
            chord_tones=_tuple_str(d.get("chordTones")),
            semantic_group=d["semanticGroup"],
            sequence_semantics=d["sequenceSemantics"],
            atlas_refs=_tuple_str(d.get("atlasRefs")),
            primary_network_node=d.get("primaryNetworkNode"),
            context_network_nodes=_tuple_str(d.get("contextNetworkNodes")),
            visual_node_id=d["visualNodeId"],
            mapping_type=d["mappingType"],
            mapping_status=d["mappingStatus"],
            mapping_reason=d.get("mappingReason", ""),
            bass_pitch_class=None if d.get("bassPitchClass") is None else int(d["bassPitchClass"]),
            inversion=None if d.get("inversion") is None else int(d["inversion"]),
            figured_bass=d.get("figuredBass"),
        )


# --------------------------------------------------------------------------------------------- #
# HarmonicTransition -- an ordered link between two occurrences (plan section 6.2)
# --------------------------------------------------------------------------------------------- #

@dataclass(frozen=True)
class HarmonicTransition:
    """Ordered link between two occurrences.

    ``sequence_relation`` is always present (it is *the next drill item*). ``theory_relation`` is
    only set when a genuine canonical harmonic relation supports the pair -- and never across a
    group boundary (plan section 6.2).
    """

    id: str
    from_occurrence: str
    to_occurrence: str

    sequence_relation: str            # drill_next | transpose_next | enumerate_next | voicing_next
    theory_relation: Optional[str]    # prepares | resolves_to | prolongs | ...
    canonical_edge_id: Optional[str]

    is_group_boundary: bool
    relation_status: str              # exact | inferred | sequence_only | unsupported
    explanation: str = ""

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "fromOccurrence": self.from_occurrence,
            "toOccurrence": self.to_occurrence,
            "sequenceRelation": self.sequence_relation,
            "theoryRelation": self.theory_relation,
            "canonicalEdgeId": self.canonical_edge_id,
            "isGroupBoundary": self.is_group_boundary,
            "relationStatus": self.relation_status,
            "explanation": self.explanation,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "HarmonicTransition":
        return cls(
            id=d["id"],
            from_occurrence=d["fromOccurrence"],
            to_occurrence=d["toOccurrence"],
            sequence_relation=d["sequenceRelation"],
            theory_relation=d.get("theoryRelation"),
            canonical_edge_id=d.get("canonicalEdgeId"),
            is_group_boundary=bool(d.get("isGroupBoundary", False)),
            relation_status=d["relationStatus"],
            explanation=d.get("explanation", ""),
        )


# --------------------------------------------------------------------------------------------- #
# ProjectionNode / ProjectionEdge -- temporary overlay geometry (plan sections 6.3, 6.4)
# --------------------------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ProjectionNode:
    """A temporary visual node that exists ONLY inside the active projection.

    Never added to the canonical network. Required for legacy templates that lack an exact chord
    node (plan section 6.3).
    """

    id: str
    label: str
    kind: str                    # proxy_triad | occurrence_marker | proxy_voicing
    canonical_ref: Optional[str]
    atlas_refs: Tuple[str, ...]
    anchor_node_id: Optional[str]
    x: float
    y: float
    visual_class: str
    mapping_status: str
    # frozen dataclasses hash over all fields; a Dict field would crash hash(), so exclude it.
    data: Dict = field(default_factory=dict, hash=False)

    def __post_init__(self):
        # normalise coordinates to 2 dp so to_dict/from_dict round-trips exactly (the payload is
        # emitted rounded for the JS graph).
        object.__setattr__(self, "x", round(float(self.x), 2))
        object.__setattr__(self, "y", round(float(self.y), 2))

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "canonicalRef": self.canonical_ref,
            "atlasRefs": list(self.atlas_refs),
            "anchorNodeId": self.anchor_node_id,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "visualClass": self.visual_class,
            "mappingStatus": self.mapping_status,
            "data": dict(self.data),
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "ProjectionNode":
        return cls(
            id=d["id"],
            label=d["label"],
            kind=d["kind"],
            canonical_ref=d.get("canonicalRef"),
            atlas_refs=_tuple_str(d.get("atlasRefs")),
            anchor_node_id=d.get("anchorNodeId"),
            # match to_dict()'s 2-dp rounding so from_dict(to_dict(node)) == node
            x=round(float(d.get("x", 0.0)), 2),
            y=round(float(d.get("y", 0.0)), 2),
            visual_class=d.get("visualClass", "proxy"),
            mapping_status=d.get("mappingStatus", "contextual"),
            data=dict(d.get("data", {})),
        )


@dataclass(frozen=True)
class ProjectionEdge:
    """A runtime overlay edge (sequence relation) between two visual nodes (plan section 6.4)."""

    id: str
    source: str
    target: str
    relation: str                # drill_next | transpose_next | enumerate_next | voicing_next
    canonical_edge_id: Optional[str]
    visual_class: str
    explanation: str = ""

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "canonicalEdgeId": self.canonical_edge_id,
            "visualClass": self.visual_class,
            "explanation": self.explanation,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "ProjectionEdge":
        return cls(
            id=d["id"],
            source=d["source"],
            target=d["target"],
            relation=d["relation"],
            canonical_edge_id=d.get("canonicalEdgeId"),
            visual_class=d.get("visualClass", "overlay-drill"),
            explanation=d.get("explanation", ""),
        )


# --------------------------------------------------------------------------------------------- #
# DrillGraphProjection -- the full runtime overlay (plan section 6.5)
# --------------------------------------------------------------------------------------------- #

class ProjectionValidationError(ValueError):
    """Raised when a :class:`DrillGraphProjection` violates an invariant."""


@dataclass
class DrillGraphProjection:
    """How one exercise maps onto the canonical network (plan section 6.5).

    Contains ordered occurrences (:class:`HarmonicStep`), their transitions, any overlay proxy
    nodes/edges, and the anchor/constellation node sets. Pure and serialisable.
    """

    projection_id: str
    template_id: str

    source_kind: str
    source_id: str
    title: str
    drill_family: str
    semantic_group: str
    sequence_semantics: str

    anchor_node_ids: List[str] = field(default_factory=list)
    constellation_node_ids: List[str] = field(default_factory=list)
    steps: List[HarmonicStep] = field(default_factory=list)
    transitions: List[HarmonicTransition] = field(default_factory=list)
    projection_nodes: List[ProjectionNode] = field(default_factory=list)
    projection_edges: List[ProjectionEdge] = field(default_factory=list)

    warnings: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    schema: str = PROJECTION_SCHEMA

    # -- lookups ------------------------------------------------------------------------------ #

    def step_by_occurrence(self, occurrence_id: str) -> Optional[HarmonicStep]:
        for step in self.steps:
            if step.occurrence_id == occurrence_id:
                return step
        return None

    def step_at_index(self, sequence_index: int) -> Optional[HarmonicStep]:
        for step in self.steps:
            if step.sequence_index == sequence_index:
                return step
        return None

    def canonical_nodes(self) -> List[str]:
        """Distinct canonical node ids referenced by any step (order-preserving)."""
        seen: Dict[str, None] = {}
        for step in self.steps:
            if step.primary_network_node and not is_proxy_node_id(step.primary_network_node):
                seen.setdefault(step.primary_network_node, None)
            for cid in step.context_network_nodes:
                if not is_proxy_node_id(cid):
                    seen.setdefault(cid, None)
        return list(seen.keys())

    def counts(self) -> Dict:
        by_status: Dict[str, int] = {}
        for step in self.steps:
            by_status[step.mapping_status] = by_status.get(step.mapping_status, 0) + 1
        return {
            "steps": len(self.steps),
            "transitions": len(self.transitions),
            "groups": (max((s.group_index for s in self.steps), default=-1) + 1),
            "proxyNodes": len(self.projection_nodes),
            "canonicalNodes": len(self.canonical_nodes()),
            "byMappingStatus": by_status,
            "theoryEdges": sum(1 for t in self.transitions if t.theory_relation),
            "groupBoundaries": sum(1 for t in self.transitions if t.is_group_boundary),
        }

    # -- validation (plan section 6.5) -------------------------------------------------------- #

    def validate(self) -> None:
        if self.schema != PROJECTION_SCHEMA:
            raise ProjectionValidationError(f"unexpected schema {self.schema!r}")
        if self.source_kind not in SOURCE_KINDS:
            raise ProjectionValidationError(f"invalid source_kind {self.source_kind!r}")
        if self.semantic_group not in THEMATIC_GROUPS:
            raise ProjectionValidationError(f"invalid semantic_group {self.semantic_group!r}")
        if self.sequence_semantics not in SEQUENCE_SEMANTICS:
            raise ProjectionValidationError(
                f"invalid sequence_semantics {self.sequence_semantics!r}"
            )

        occ_ids = [s.occurrence_id for s in self.steps]
        # stable, unique occurrence ids
        if len(set(occ_ids)) != len(occ_ids):
            raise ProjectionValidationError("duplicate occurrence ids")

        # contiguous 0..N-1 sequence indices
        indices = sorted(s.sequence_index for s in self.steps)
        if indices != list(range(len(self.steps))):
            raise ProjectionValidationError(
                f"sequence indices must be contiguous 0..N-1, got {indices}"
            )

        occ_set = set(occ_ids)
        # per-step invariants
        for step in self.steps:
            if step.mapping_status not in MAPPING_STATUS:
                raise ProjectionValidationError(
                    f"{step.occurrence_id}: invalid mapping_status {step.mapping_status!r}"
                )
            if step.mapping_type not in MAPPING_TYPES:
                raise ProjectionValidationError(
                    f"{step.occurrence_id}: invalid mapping_type {step.mapping_type!r}"
                )
            # every step must have a visible node
            if not step.visual_node_id:
                raise ProjectionValidationError(
                    f"{step.occurrence_id}: step has no visual node"
                )
            # exact mappings must use a real canonical node (not a proxy)
            if step.mapping_status == "exact":
                if not step.primary_network_node:
                    raise ProjectionValidationError(
                        f"{step.occurrence_id}: exact mapping requires a canonical node"
                    )
                if is_proxy_node_id(step.primary_network_node):
                    raise ProjectionValidationError(
                        f"{step.occurrence_id}: exact mapping cannot point at a proxy node"
                    )
                if is_proxy_node_id(step.visual_node_id):
                    raise ProjectionValidationError(
                        f"{step.occurrence_id}: exact mapping cannot render as a proxy node"
                    )
            # proxy-rendered steps must declare a non-exact status
            if is_proxy_node_id(step.visual_node_id) and step.mapping_status == "exact":
                raise ProjectionValidationError(
                    f"{step.occurrence_id}: proxy-rendered step must not be exact"
                )

        # transition invariants
        step_by_occ = {s.occurrence_id: s for s in self.steps}
        for tr in self.transitions:
            if tr.from_occurrence not in occ_set or tr.to_occurrence not in occ_set:
                raise ProjectionValidationError(
                    f"transition {tr.id} references unknown occurrence"
                )
            if tr.sequence_relation not in SEQUENCE_RELATIONS:
                raise ProjectionValidationError(
                    f"transition {tr.id}: invalid sequence_relation {tr.sequence_relation!r}"
                )
            if tr.relation_status not in RELATION_STATUS:
                raise ProjectionValidationError(
                    f"transition {tr.id}: invalid relation_status {tr.relation_status!r}"
                )
            if tr.theory_relation:
                if tr.theory_relation not in THEORY_RELATIONS:
                    raise ProjectionValidationError(
                        f"transition {tr.id}: invalid theory_relation {tr.theory_relation!r}"
                    )
                # a theory edge may only be asserted under a motion-capable ordering: enumeration
                # / transposition / class drills are pedagogical and never a progression (4.1).
                if self.sequence_semantics not in MOTION_CAPABLE_SEMANTICS:
                    raise ProjectionValidationError(
                        f"transition {tr.id}: theory relation {tr.theory_relation!r} under "
                        f"non-motion sequence semantics {self.sequence_semantics!r}"
                    )
                # NEVER a theory edge across a group boundary -- derived from the steps' actual
                # group_index (not just the self-reported flag) so a mislabelled flag can't slip
                # a false resolution across a transposition seam.
                a = step_by_occ.get(tr.from_occurrence)
                b = step_by_occ.get(tr.to_occurrence)
                crosses = a is not None and b is not None and a.group_index != b.group_index
                if tr.is_group_boundary or crosses:
                    raise ProjectionValidationError(
                        f"transition {tr.id}: theory relation across a group boundary"
                    )

        # proxy node ids must be unique and marked
        proxy_ids = [n.id for n in self.projection_nodes]
        if len(set(proxy_ids)) != len(proxy_ids):
            raise ProjectionValidationError("duplicate projection-node ids")
        for pn in self.projection_nodes:
            if pn.kind not in PROJECTION_NODE_KINDS:
                raise ProjectionValidationError(
                    f"projection node {pn.id}: invalid kind {pn.kind!r}"
                )

        # overlay-edge invariants (mirror the transition checks: valid relation + known endpoints)
        visual_ids = {s.visual_node_id for s in self.steps}
        visual_ids.update(pn.id for pn in self.projection_nodes)
        for pe in self.projection_edges:
            if pe.relation not in SEQUENCE_RELATIONS:
                raise ProjectionValidationError(
                    f"projection edge {pe.id}: invalid relation {pe.relation!r}"
                )
            if pe.source not in visual_ids or pe.target not in visual_ids:
                raise ProjectionValidationError(
                    f"projection edge {pe.id} references an unknown visual node"
                )

    # -- serialisation ------------------------------------------------------------------------ #

    def to_dict(self) -> Dict:
        return {
            "schema": self.schema,
            "projectionId": self.projection_id,
            "templateId": self.template_id,
            "sourceKind": self.source_kind,
            "sourceId": self.source_id,
            "title": self.title,
            "drillFamily": self.drill_family,
            "semanticGroup": self.semantic_group,
            "sequenceSemantics": self.sequence_semantics,
            "anchorNodeIds": list(self.anchor_node_ids),
            "constellationNodeIds": list(self.constellation_node_ids),
            "steps": [s.to_dict() for s in self.steps],
            "transitions": [t.to_dict() for t in self.transitions],
            "projectionNodes": [n.to_dict() for n in self.projection_nodes],
            "projectionEdges": [e.to_dict() for e in self.projection_edges],
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "counts": self.counts(),
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "DrillGraphProjection":
        return cls(
            projection_id=d["projectionId"],
            template_id=d["templateId"],
            source_kind=d["sourceKind"],
            source_id=d["sourceId"],
            title=d.get("title", ""),
            drill_family=d["drillFamily"],
            semantic_group=d["semanticGroup"],
            sequence_semantics=d["sequenceSemantics"],
            anchor_node_ids=_list(d.get("anchorNodeIds")),
            constellation_node_ids=_list(d.get("constellationNodeIds")),
            steps=[HarmonicStep.from_dict(s) for s in d.get("steps", [])],
            transitions=[HarmonicTransition.from_dict(t) for t in d.get("transitions", [])],
            projection_nodes=[ProjectionNode.from_dict(n) for n in d.get("projectionNodes", [])],
            projection_edges=[ProjectionEdge.from_dict(e) for e in d.get("projectionEdges", [])],
            warnings=_list(d.get("warnings")),
            metadata=dict(d.get("metadata", {})),
            schema=d.get("schema", PROJECTION_SCHEMA),
        )


# --------------------------------------------------------------------------------------------- #
# GraphDrillRequest -- a graph selection to compile into actions (plan section 6.6)
# --------------------------------------------------------------------------------------------- #

@dataclass(frozen=True)
class GraphDrillRequest:
    """A user's graph selection to turn into launchable actions (Graph -> Drill)."""

    template_id: str
    interaction_kind: str        # node | edge | path | constellation
    selected_node_ids: Tuple[str, ...] = ()
    selected_edge_ids: Tuple[str, ...] = ()
    selected_path_id: Optional[str] = None

    thematic_group: Optional[str] = None
    key_context: Optional[str] = None
    mode: Optional[str] = None
    render: str = "block"
    options: Dict = field(default_factory=dict, hash=False)
    schema: str = REQUEST_SCHEMA

    def validate(self) -> None:
        if self.interaction_kind not in INTERACTION_KINDS:
            raise ValueError(f"invalid interaction_kind {self.interaction_kind!r}")
        if self.thematic_group is not None and self.thematic_group not in THEMATIC_GROUPS:
            raise ValueError(f"invalid thematic_group {self.thematic_group!r}")
        if self.render not in ("block", "arpeggio"):
            raise ValueError(f"invalid render {self.render!r}")
        if self.interaction_kind == "node" and not self.selected_node_ids:
            raise ValueError("node interaction requires selected_node_ids")
        if self.interaction_kind == "edge" and not self.selected_edge_ids:
            raise ValueError("edge interaction requires selected_edge_ids")
        if self.interaction_kind == "path" and not self.selected_path_id:
            raise ValueError("path interaction requires selected_path_id")

    def to_dict(self) -> Dict:
        return {
            "schema": self.schema,
            "templateId": self.template_id,
            "interactionKind": self.interaction_kind,
            "selectedNodeIds": list(self.selected_node_ids),
            "selectedEdgeIds": list(self.selected_edge_ids),
            "selectedPathId": self.selected_path_id,
            "thematicGroup": self.thematic_group,
            "keyContext": self.key_context,
            "mode": self.mode,
            "render": self.render,
            "options": dict(self.options),
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "GraphDrillRequest":
        return cls(
            template_id=d.get("templateId", ""),
            interaction_kind=d["interactionKind"],
            selected_node_ids=_tuple_str(d.get("selectedNodeIds")),
            selected_edge_ids=_tuple_str(d.get("selectedEdgeIds")),
            selected_path_id=d.get("selectedPathId"),
            thematic_group=d.get("thematicGroup"),
            key_context=d.get("keyContext"),
            mode=d.get("mode"),
            render=d.get("render", "block"),
            options=dict(d.get("options", {})),
            schema=d.get("schema", REQUEST_SCHEMA),
        )


# --------------------------------------------------------------------------------------------- #
# LaunchAction -- a unified additive launch envelope (plan section 6.7)
# --------------------------------------------------------------------------------------------- #

@dataclass(frozen=True)
class LaunchAction:
    """One thing the user can do with a graph selection.

    ``status`` distinguishes launchable actions from reserved/unavailable ones (honesty model).
    When launchable, ``spec`` carries a validated native spec dict and ``preview_projection`` the
    projection to draw before launch (plan section 10.4).
    """

    id: str
    label: str
    target: str                   # trainer | lab
    status: str                   # launchable | reserved | unavailable
    semantic_group: str
    interaction_kind: str

    spec_type: Optional[str] = None      # harmony_exercise | lab_experiment
    # Dict fields excluded from the generated __hash__ (a frozen dataclass would crash hashing them).
    spec: Optional[Dict] = field(default=None, hash=False)
    request: Optional[Dict] = field(default=None, hash=False)
    reason: str = ""
    preview_projection: Optional[Dict] = field(default=None, hash=False)

    def validate(self) -> None:
        if self.target not in LAUNCH_TARGETS:
            raise ValueError(f"invalid target {self.target!r}")
        if self.status not in LAUNCH_STATUS:
            raise ValueError(f"invalid status {self.status!r}")
        if self.semantic_group not in THEMATIC_GROUPS:
            raise ValueError(f"invalid semantic_group {self.semantic_group!r}")
        if self.interaction_kind not in INTERACTION_KINDS:
            raise ValueError(f"invalid interaction_kind {self.interaction_kind!r}")
        if self.spec_type is not None and self.spec_type not in SPEC_TYPES:
            raise ValueError(f"invalid spec_type {self.spec_type!r}")
        if self.status == "launchable" and self.spec is None:
            raise ValueError(f"launchable action {self.id!r} must carry a spec")

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "label": self.label,
            "target": self.target,
            "status": self.status,
            "semanticGroup": self.semantic_group,
            "interactionKind": self.interaction_kind,
            "specType": self.spec_type,
            "spec": self.spec,
            "request": self.request,
            "reason": self.reason,
            "previewProjection": self.preview_projection,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "LaunchAction":
        return cls(
            id=d["id"],
            label=d["label"],
            target=d["target"],
            status=d["status"],
            semantic_group=d["semanticGroup"],
            interaction_kind=d["interactionKind"],
            spec_type=d.get("specType"),
            spec=d.get("spec"),
            request=d.get("request"),
            reason=d.get("reason", ""),
            preview_projection=d.get("previewProjection"),
        )


# --------------------------------------------------------------------------------------------- #
# HarmonicPath -- a first-class ordered arc over canonical nodes (plan section 10.3)
# --------------------------------------------------------------------------------------------- #

@dataclass(frozen=True)
class HarmonicPath:
    """An ordered, contiguous, single-key route over canonical nodes (e.g. a cadence)."""

    id: str
    label: str
    key_context: str
    mode: str
    node_ids: Tuple[str, ...]
    edge_ids: Tuple[str, ...]
    romans: Tuple[str, ...]
    cadence_type: Optional[str] = None
    semantic_group: str = "functional_path"
    launch_action_ids: Tuple[str, ...] = ()

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "label": self.label,
            "keyContext": self.key_context,
            "mode": self.mode,
            "nodeIds": list(self.node_ids),
            "edgeIds": list(self.edge_ids),
            "romans": list(self.romans),
            "cadenceType": self.cadence_type,
            "semanticGroup": self.semantic_group,
            "launchActionIds": list(self.launch_action_ids),
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "HarmonicPath":
        return cls(
            id=d["id"],
            label=d["label"],
            key_context=d["keyContext"],
            mode=d["mode"],
            node_ids=_tuple_str(d.get("nodeIds")),
            edge_ids=_tuple_str(d.get("edgeIds")),
            romans=_tuple_str(d.get("romans")),
            cadence_type=d.get("cadenceType"),
            semantic_group=d.get("semanticGroup", "functional_path"),
            launch_action_ids=_tuple_str(d.get("launchActionIds")),
        )


__all__ = [
    # schemas
    "PROJECTION_SCHEMA", "REQUEST_SCHEMA", "LAUNCH_SCHEMA",
    # vocabularies
    "THEMATIC_GROUPS", "SEMANTIC_LEVELS", "ENTITY_ROLES", "MAPPING_STATUS", "MAPPING_TYPES",
    "SEQUENCE_SEMANTICS", "SEQUENCE_RELATIONS", "THEORY_RELATIONS", "RELATION_STATUS",
    "SOURCE_KINDS", "PROJECTION_NODE_KINDS", "LAUNCH_TARGETS", "LAUNCH_STATUS",
    "INTERACTION_KINDS", "SPEC_TYPES",
    "DRILL_FAMILY_DEFAULTS", "SEQUENCE_RELATION_BY_FAMILY",
    # helpers
    "default_group_for_drill", "default_sequence_semantics_for_drill",
    "sequence_relation_for_drill", "occurrence_id", "proxy_triad_id", "proxy_applied_id",
    "proxy_voicing_id",
    "transition_id", "is_proxy_node_id",
    # dataclasses
    "HarmonicStep", "HarmonicTransition", "ProjectionNode", "ProjectionEdge",
    "DrillGraphProjection", "ProjectionValidationError", "GraphDrillRequest", "LaunchAction",
    "HarmonicPath",
]
