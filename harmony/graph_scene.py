"""The GraphScene contract -- one bounded, topic-specific harmonic graph scene.

A :class:`GraphScene` is the *single serialisable object the UI renders for one active learning
objective*.  It replaces the old runtime assumption ("one fixed graph, project every drill onto
it") with a scene that is **selected/generated per exercise** (see
:mod:`harmony.graph_scene_router`) from the curriculum node / Lab experiment / exercise spec.

Design (plan section 3):

    active curriculum exercise
            -> classify musical / pedagogical semantics   (graph_scene_router.decide_graph_scene)
            -> select a suitable scene generator           (graph_scene_generators)
            -> build a bounded topic-specific scene         (this contract)
            -> map every drill occurrence exactly           (occurrence_map)
            -> navigate trainer and graph bidirectionally   (supported_actions + host)

This module owns ONLY the pure data contract + its honesty invariants.  It is deliberately thin:
the actual nodes/edges/occurrences are *adapted* from the already-built
:class:`~harmony.harmonic_network.HarmonicNetwork` (canonical topology) and
:class:`~harmony.harmonic_flow.DrillGraphProjection` (running occurrences) by the generators, so no
theory is re-encoded and the existing, tested builders/projectors become internal scene generators.

No Qt / JS / MusicXML / file I/O.  Deterministic: no ``random``, no wall-clock time.  Payload keys
are camelCase (the scene is shipped to the JS graph).

The crux invariant this file enforces (plan sections 1, 10): **a chord occurrence never maps onto a
key-context node, and node identity carries a semantic ``entity_type`` -- a plain V triad is not a
V7, an ``Am`` chord is not the A-minor key, a ``C`` major key is not the C major triad.**
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple

from harmony.harmonic_flow import LaunchAction, is_proxy_node_id


SCENE_SCHEMA = "harmony-graph-scene/v1"


# --------------------------------------------------------------------------------------------- #
# Controlled vocabularies (the scene contract's closed sets)
# --------------------------------------------------------------------------------------------- #

#: Every scene type in the catalogue (plan section 5).  ``unsupported`` is the honest fail-closed
#: scene shown when no suitable graph exists for an exercise (plan section 1 "Fail closed").
SCENE_TYPES = frozenset({
    "legacy_key_relation",       # A: circle / relative / V7->I / vii°->I (Explore + relations)
    "diatonic_key_field",        # B: full_key -- the seven exact diatonic triads of one key
    "degree_transposition",      # C: horizontal_degree -- one degree across 12 keys
    "triad_quality_class",       # D: quality -- a key's triads grouped by quality
    "functional_progression",    # E: function -- a bounded progression path
    "cadence_resolution",        # F: two-chord cadence drills
    "inversion_space",           # G: one chord identity + its inversion voicings
    "voice_leading_path",        # H: harmonic path + voice-motion layer
    "polyphonic_harmony_path",   # I: implied-harmony slices with voice lanes
    "score_harmonic_path",       # J: curated real-score analysis
    "unsupported",               # honest "no suitable harmonic graph" scene
})

#: Where a scene's active exercise came from (plan section 3 GraphScene.source_kind).
SCENE_SOURCE_KINDS = frozenset({"curriculum", "harmony_exercise", "lab", "score", "explore"})

#: The musical scope a scene spans (plan section 3 GraphScene.semantic_scope).
SEMANTIC_SCOPES = frozenset({
    "local_key",     # one key's field / class / progression
    "cross_key",     # one degree across keys / a cross-key relation
    "progression",   # a bounded functional route
    "class",         # a quality / degree classification
    "voicing",       # inversion / voice-leading of one chord
    "score",         # a real-score slice stream
    "relations",     # legacy key-relation topology (Explore)
    "none",          # the unsupported scene
})

#: Semantic type of a *node* -- root pitch class alone is never enough to identify a node (plan
#: section 1 "Same-root entities must remain distinct").
ENTITY_TYPES = frozenset({
    "key",           # a tonal centre / key context (NOT a chord)
    "triad",         # an exact diatonic triad
    "seventh",       # a dominant seventh (live since ticket 09's V7 tracer)
    "diminished",    # a leading-tone diminished triad
    "degree",        # an abstract, key-invariant scale degree
    "function",      # a broad function family (tonic / predominant / dominant)
    "quality",       # a chord-quality class
    "inversion",     # one voicing state of a chord identity
    "occurrence",    # a projection-only overlay occurrence (proxy)
    "score_slice",   # a real-score slice
})

#: The visual/semantic layer an *edge* belongs to (plan section 3 GraphSceneEdge.layer).  The
#: enumeration/transposition ``sequence`` layer is kept strictly separate from the ``theory`` layer
#: so pedagogical ordering is never drawn as asserted harmonic motion (plan sections 1, 5.A).
EDGE_LAYERS = frozenset({
    "structure",     # membership / instance_of / inversion_of (the scene's skeleton)
    "theory",        # asserted harmonic relations (resolves_to, prepares, leading_tone_to, ...)
    "sequence",      # runtime "next drill item" overlay (enumerate/transpose/drill/voicing _next)
    "voice_leading", # individual-voice motion layer
    "context",       # a chord's link to its key-context anchor
})

#: Node ``entity_type`` values that are chords (may carry an occurrence) -- and must NEVER be
#: allowed to map onto a ``key`` node.  This is the honesty gate at the heart of the rework.
_CHORD_ENTITY_TYPES = frozenset({"triad", "seventh", "diminished", "inversion", "score_slice"})

#: Map a canonical :class:`~harmony.harmonic_network.NetNode` ``kind`` (or projection node kind) to
#: a scene ``entity_type``.  Used by the generators' adapter.
KIND_TO_ENTITY_TYPE: Dict[str, str] = {
    "major_key": "key",
    "minor_key": "key",
    "key_center": "key",
    "diatonic_triad": "triad",
    "dominant_seventh": "seventh",
    "diminished_triad": "diminished",
    "degree_class": "degree",
    "function_family": "function",
    "quality_class": "quality",
    "inversion_state": "inversion",
    # projection-only overlay kinds
    "proxy_triad": "occurrence",
    "proxy_voicing": "occurrence",
    "occurrence_marker": "occurrence",
}


class SceneValidationError(ValueError):
    """Raised when a :class:`GraphScene` violates a contract invariant."""


# --------------------------------------------------------------------------------------------- #
# GraphSceneNode -- one node in the scene (plan section 3 node fields)
# --------------------------------------------------------------------------------------------- #

@dataclass(frozen=True)
class GraphSceneNode:
    """A node in a topic-specific scene.

    ``entity_type`` + ``key_context`` + ``roman`` + ``quality`` + ``chord_tones`` jointly identify
    the node -- never the root pitch class alone (plan section 1).
    """

    id: str
    label: str
    entity_type: str                       # ENTITY_TYPES
    sublabel: str = ""
    semantic_level: str = ""               # key | chord | function | class | voicing | path
    entity_role: str = ""                  # anchor | instance | family | state | reference
    key_context: str = ""
    roman: str = ""
    chord_symbol: str = ""
    chord_tones: Tuple[str, ...] = ()
    quality: str = ""
    #: LEGACY fine label from the theory engine (tonic/mediant/predominant/subdominant/dominant).
    #: Kept for backward compatibility; the explicit two-level role fields below supersede it for
    #: display (plan sections 3.2, 4.1). Do NOT present this as the chord's complete identity.
    function_label: str = ""
    # -- explicit two-level role model (plan sections 1-4): SPECIFIC scale-degree role vs. BROAD
    #    function family. Additive; ``function_label`` above is retained unchanged. --
    scale_degree_name: str = ""            # tonic / supertonic / mediant / ... (specific level)
    specific_role: str = ""               # e.g. mediant / subdominant / leading-tone diminished
    specific_role_label: str = ""
    broad_function_family: str = ""       # tonic_related / predominant / dominant / modal_or_contextual
    broad_function_family_label: str = ""
    family_membership_type: str = ""      # primary / related / substitute / preparatory / ...
    family_membership_strength: str = ""  # strong / medium / weak / context_dependent
    family_membership_explanation: str = ""
    degree_index: Optional[int] = None
    x: float = 0.0
    y: float = 0.0
    radius: float = 18.0
    visual_class: str = "slate"
    canonical_refs: Tuple[str, ...] = ()   # atlas / canonical ids this node mirrors
    explanation: str = ""
    data: Dict = field(default_factory=dict, hash=False)

    def __post_init__(self):
        object.__setattr__(self, "x", round(float(self.x), 2))
        object.__setattr__(self, "y", round(float(self.y), 2))

    @property
    def is_key(self) -> bool:
        return self.entity_type == "key"

    @property
    def is_chord(self) -> bool:
        return self.entity_type in _CHORD_ENTITY_TYPES

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "label": self.label,
            "sublabel": self.sublabel,
            "entityType": self.entity_type,
            "semanticLevel": self.semantic_level,
            "entityRole": self.entity_role,
            "keyContext": self.key_context,
            "roman": self.roman,
            "chordSymbol": self.chord_symbol,
            "chordTones": list(self.chord_tones),
            "quality": self.quality,
            "functionLabel": self.function_label,
            "scaleDegreeName": self.scale_degree_name,
            "specificRole": self.specific_role,
            "specificRoleLabel": self.specific_role_label,
            "broadFunctionFamily": self.broad_function_family,
            "broadFunctionFamilyLabel": self.broad_function_family_label,
            "familyMembershipType": self.family_membership_type,
            "familyMembershipStrength": self.family_membership_strength,
            "familyMembershipExplanation": self.family_membership_explanation,
            "degreeIndex": self.degree_index,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "radius": self.radius,
            "visualClass": self.visual_class,
            "canonicalRefs": list(self.canonical_refs),
            "explanation": self.explanation,
            "data": dict(self.data),
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "GraphSceneNode":
        return cls(
            id=d["id"],
            label=d["label"],
            entity_type=d["entityType"],
            sublabel=d.get("sublabel", ""),
            semantic_level=d.get("semanticLevel", ""),
            entity_role=d.get("entityRole", ""),
            key_context=d.get("keyContext", ""),
            roman=d.get("roman", ""),
            chord_symbol=d.get("chordSymbol", ""),
            chord_tones=tuple(d.get("chordTones", ()) or ()),
            quality=d.get("quality", ""),
            function_label=d.get("functionLabel", ""),
            scale_degree_name=d.get("scaleDegreeName", ""),
            specific_role=d.get("specificRole", ""),
            specific_role_label=d.get("specificRoleLabel", ""),
            broad_function_family=d.get("broadFunctionFamily", ""),
            broad_function_family_label=d.get("broadFunctionFamilyLabel", ""),
            family_membership_type=d.get("familyMembershipType", ""),
            family_membership_strength=d.get("familyMembershipStrength", ""),
            family_membership_explanation=d.get("familyMembershipExplanation", ""),
            degree_index=d.get("degreeIndex"),
            x=round(float(d.get("x", 0.0)), 2),
            y=round(float(d.get("y", 0.0)), 2),
            radius=float(d.get("radius", 18.0)),
            visual_class=d.get("visualClass", "slate"),
            canonical_refs=tuple(d.get("canonicalRefs", ()) or ()),
            explanation=d.get("explanation", ""),
            data=dict(d.get("data", {})),
        )


# --------------------------------------------------------------------------------------------- #
# GraphSceneEdge -- one edge, tagged with the layer it belongs to (plan section 3 edge fields)
# --------------------------------------------------------------------------------------------- #

@dataclass(frozen=True)
class GraphSceneEdge:
    """A scene edge.  ``layer`` keeps enumeration/sequence overlays out of the theory layer."""

    id: str
    source: str
    target: str
    relation: str
    layer: str                              # EDGE_LAYERS
    directed: bool = True
    explanation: str = ""
    visual_class: str = "default"
    data: Dict = field(default_factory=dict, hash=False)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "layer": self.layer,
            "directed": self.directed,
            "explanation": self.explanation,
            "visualClass": self.visual_class,
            "data": dict(self.data),
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "GraphSceneEdge":
        return cls(
            id=d["id"],
            source=d["source"],
            target=d["target"],
            relation=d["relation"],
            layer=d["layer"],
            directed=bool(d.get("directed", True)),
            explanation=d.get("explanation", ""),
            visual_class=d.get("visualClass", "default"),
            data=dict(d.get("data", {})),
        )


# --------------------------------------------------------------------------------------------- #
# GraphScenePath -- a first-class ordered arc (mirrors HarmonicPath) (plan section 3)
# --------------------------------------------------------------------------------------------- #

@dataclass(frozen=True)
class GraphScenePath:
    """An ordered, single-key route over scene nodes (e.g. a cadence path)."""

    id: str
    label: str
    node_ids: Tuple[str, ...]
    edge_ids: Tuple[str, ...] = ()
    romans: Tuple[str, ...] = ()
    key_context: str = ""
    mode: str = ""
    cadence_type: Optional[str] = None
    data: Dict = field(default_factory=dict, hash=False)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "label": self.label,
            "nodeIds": list(self.node_ids),
            "edgeIds": list(self.edge_ids),
            "romans": list(self.romans),
            "keyContext": self.key_context,
            "mode": self.mode,
            "cadenceType": self.cadence_type,
            "data": dict(self.data),
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "GraphScenePath":
        return cls(
            id=d["id"],
            label=d["label"],
            node_ids=tuple(d.get("nodeIds", ()) or ()),
            edge_ids=tuple(d.get("edgeIds", ()) or ()),
            romans=tuple(d.get("romans", ()) or ()),
            key_context=d.get("keyContext", ""),
            mode=d.get("mode", ""),
            cadence_type=d.get("cadenceType"),
            data=dict(d.get("data", {})),
        )


# --------------------------------------------------------------------------------------------- #
# SceneActivation -- the explicit "what lights up right now" map for one occurrence (plan §4.2)
# --------------------------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SceneActivation:
    """Everything that should visually respond when this occurrence is the current drill step.

    The runtime must NOT infer family context from node colour or label (plan section 4.2): this
    map is derived from the scene's *edge graph* (membership edges -> family; belongs_to_key ->
    context; sequence/theory edges -> the motion to the next occurrence) so highlighting is honest
    and structural.  Ids reference nodes/edges already present in the scene.
    """

    current_node_id: str
    family_node_ids: Tuple[str, ...] = ()          # the broad-function family node(s) to halo
    context_node_ids: Tuple[str, ...] = ()         # the key-context anchor(s) to keep lit low
    structure_edge_ids: Tuple[str, ...] = ()       # membership edge(s): chord -> family (structure)
    sequence_edge_ids: Tuple[str, ...] = ()        # drill-order edge to the next occurrence
    theory_edge_ids: Tuple[str, ...] = ()          # asserted harmonic-motion edge to the next occ
    previous_occurrence_id: Optional[str] = None
    next_occurrence_id: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "currentNodeId": self.current_node_id,
            "familyNodeIds": list(self.family_node_ids),
            "contextNodeIds": list(self.context_node_ids),
            "structureEdgeIds": list(self.structure_edge_ids),
            "sequenceEdgeIds": list(self.sequence_edge_ids),
            "theoryEdgeIds": list(self.theory_edge_ids),
            "previousOccurrenceId": self.previous_occurrence_id,
            "nextOccurrenceId": self.next_occurrence_id,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "SceneActivation":
        return cls(
            current_node_id=d["currentNodeId"],
            family_node_ids=tuple(d.get("familyNodeIds", ()) or ()),
            context_node_ids=tuple(d.get("contextNodeIds", ()) or ()),
            structure_edge_ids=tuple(d.get("structureEdgeIds", ()) or ()),
            sequence_edge_ids=tuple(d.get("sequenceEdgeIds", ()) or ()),
            theory_edge_ids=tuple(d.get("theoryEdgeIds", ()) or ()),
            previous_occurrence_id=d.get("previousOccurrenceId"),
            next_occurrence_id=d.get("nextOccurrenceId"),
        )


# --------------------------------------------------------------------------------------------- #
# SceneOccurrence -- one drill occurrence mapped exactly onto a scene node (plan section 3)
# --------------------------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SceneOccurrence:
    """One position of a chord in the running drill, mapped to a scene node.

    The same node may occur more than once (repeated ``I`` in ``I-IV-V-I``); ``occurrence_id``
    encodes position, ``node_id`` the (exact or proxy) node it lights.  ``primary_node_id`` is the
    *canonical* node (``None`` for a proxy/unsupported occurrence).  Fields for the pedagogical
    detail panel (plan section 9) travel in ``detail``.
    """

    occurrence_id: str
    sequence_index: int
    node_id: str                            # the scene node this occurrence lights (may be a proxy)
    entity_type: str
    mapping_status: str                     # exact | contextual | approximate | unsupported
    group_index: int = 0
    index_in_group: int = 0
    primary_node_id: Optional[str] = None   # canonical node id (None if proxy/unsupported)
    context_node_ids: Tuple[str, ...] = ()
    roman: str = ""
    chord_symbol: str = ""
    key_context: str = ""
    quality: str = ""
    mapping_reason: str = ""
    # relation to the NEXT occurrence (drives the active edge + the detail panel's "relation to next")
    next_sequence_relation: Optional[str] = None
    next_theory_relation: Optional[str] = None
    next_relation_status: Optional[str] = None
    next_is_group_boundary: bool = False
    next_explanation: str = ""
    #: opening | intermediate | arrival -- distinguishes e.g. the opening vs. arrival tonic of a
    #: I-IV-V-I progression (plan section 9). Empty for non-progression (enumeration/class) scenes.
    occurrence_role: str = ""
    #: The explicit "what lights up now" map (plan section 4.2). Filled by
    #: :func:`compute_activations`; ``None`` until then.
    activation: Optional[SceneActivation] = None
    detail: Dict = field(default_factory=dict, hash=False)

    def to_dict(self) -> Dict:
        return {
            "occurrenceId": self.occurrence_id,
            "sequenceIndex": self.sequence_index,
            "nodeId": self.node_id,
            "entityType": self.entity_type,
            "mappingStatus": self.mapping_status,
            "groupIndex": self.group_index,
            "indexInGroup": self.index_in_group,
            "primaryNodeId": self.primary_node_id,
            "contextNodeIds": list(self.context_node_ids),
            "roman": self.roman,
            "chordSymbol": self.chord_symbol,
            "keyContext": self.key_context,
            "quality": self.quality,
            "mappingReason": self.mapping_reason,
            "nextSequenceRelation": self.next_sequence_relation,
            "nextTheoryRelation": self.next_theory_relation,
            "nextRelationStatus": self.next_relation_status,
            "nextIsGroupBoundary": self.next_is_group_boundary,
            "nextExplanation": self.next_explanation,
            "occurrenceRole": self.occurrence_role,
            "activation": (self.activation.to_dict() if self.activation else None),
            "detail": dict(self.detail),
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "SceneOccurrence":
        return cls(
            occurrence_id=d["occurrenceId"],
            sequence_index=int(d["sequenceIndex"]),
            node_id=d["nodeId"],
            entity_type=d["entityType"],
            mapping_status=d["mappingStatus"],
            group_index=int(d.get("groupIndex", 0)),
            index_in_group=int(d.get("indexInGroup", 0)),
            primary_node_id=d.get("primaryNodeId"),
            context_node_ids=tuple(d.get("contextNodeIds", ()) or ()),
            roman=d.get("roman", ""),
            chord_symbol=d.get("chordSymbol", ""),
            key_context=d.get("keyContext", ""),
            quality=d.get("quality", ""),
            mapping_reason=d.get("mappingReason", ""),
            next_sequence_relation=d.get("nextSequenceRelation"),
            next_theory_relation=d.get("nextTheoryRelation"),
            next_relation_status=d.get("nextRelationStatus"),
            next_is_group_boundary=bool(d.get("nextIsGroupBoundary", False)),
            next_explanation=d.get("nextExplanation", ""),
            occurrence_role=d.get("occurrenceRole", ""),
            activation=(SceneActivation.from_dict(d["activation"])
                        if d.get("activation") else None),
            detail=dict(d.get("detail", {})),
        )


# --------------------------------------------------------------------------------------------- #
# SceneLayer -- a toggleable visual layer definition (plan section 3)
# --------------------------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SceneLayer:
    """One toggleable layer the scene declares (structure / theory / sequence / ...)."""

    id: str                                 # an EDGE_LAYERS value or a node-group id
    label: str
    kind: str                               # EDGE_LAYERS or "nodes"
    default_visible: bool = True
    description: str = ""

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "defaultVisible": self.default_visible,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "SceneLayer":
        return cls(
            id=d["id"],
            label=d["label"],
            kind=d.get("kind", "nodes"),
            default_visible=bool(d.get("defaultVisible", True)),
            description=d.get("description", ""),
        )


# --------------------------------------------------------------------------------------------- #
# GraphScene -- the whole bounded, topic-specific scene (plan section 3)
# --------------------------------------------------------------------------------------------- #

@dataclass
class GraphScene:
    """One bounded harmonic graph scene, selected/generated for a single learning objective."""

    scene_id: str
    scene_type: str                         # SCENE_TYPES
    title: str
    subtitle: str
    source_kind: str                        # SCENE_SOURCE_KINDS
    source_id: str
    pedagogical_goal: str
    semantic_scope: str                     # SEMANTIC_SCOPES

    key_context: Optional[str] = None
    mode: Optional[str] = None

    nodes: List[GraphSceneNode] = field(default_factory=list)
    edges: List[GraphSceneEdge] = field(default_factory=list)
    paths: List[GraphScenePath] = field(default_factory=list)
    occurrence_map: List[SceneOccurrence] = field(default_factory=list)
    layer_definitions: List[SceneLayer] = field(default_factory=list)
    supported_actions: List[LaunchAction] = field(default_factory=list)

    warnings: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    #: The template this scene was generated from (for debug / manual-override warnings). Not the
    #: routing key -- routing is by semantics, never by template id.
    generator_id: str = ""
    schema: str = SCENE_SCHEMA

    # -- lookups ------------------------------------------------------------------------------ #

    def node(self, node_id: str) -> Optional[GraphSceneNode]:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def occurrence_at(self, sequence_index: int) -> Optional[SceneOccurrence]:
        for o in self.occurrence_map:
            if o.sequence_index == sequence_index:
                return o
        return None

    def nodes_of_type(self, entity_type: str) -> List[GraphSceneNode]:
        return [n for n in self.nodes if n.entity_type == entity_type]

    def key_anchor_ids(self) -> List[str]:
        return [n.id for n in self.nodes if n.entity_type == "key"]

    def counts(self) -> Dict:
        by_type: Dict[str, int] = {}
        for n in self.nodes:
            by_type[n.entity_type] = by_type.get(n.entity_type, 0) + 1
        by_layer: Dict[str, int] = {}
        for e in self.edges:
            by_layer[e.layer] = by_layer.get(e.layer, 0) + 1
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "paths": len(self.paths),
            "occurrences": len(self.occurrence_map),
            "actions": len(self.supported_actions),
            "nodesByType": by_type,
            "edgesByLayer": by_layer,
        }

    # -- validation (the honesty gate) -------------------------------------------------------- #

    def validate(self) -> None:
        """Raise :class:`SceneValidationError` on any structural or honesty violation.

        The honesty gate (plan sections 1, 10) is enforced here so a mis-generated scene fails at
        build time, not silently in the UI:

          * a chord occurrence NEVER maps onto a ``key`` node (``Am`` != A-minor key,
            ``C`` triad != C major key);
          * exact occurrences point at a real, present, non-proxy node of a *chord* type;
          * the ``unsupported`` scene carries no occurrences and states why in ``warnings``.
        """
        if self.schema != SCENE_SCHEMA:
            raise SceneValidationError(f"unexpected schema {self.schema!r}")
        if self.scene_type not in SCENE_TYPES:
            raise SceneValidationError(f"invalid scene_type {self.scene_type!r}")
        if self.source_kind not in SCENE_SOURCE_KINDS:
            raise SceneValidationError(f"invalid source_kind {self.source_kind!r}")
        if self.semantic_scope not in SEMANTIC_SCOPES:
            raise SceneValidationError(f"invalid semantic_scope {self.semantic_scope!r}")
        if not self.scene_id or not self.title:
            raise SceneValidationError("scene requires a non-empty scene_id and title")

        node_ids = [n.id for n in self.nodes]
        node_by_id = {n.id: n for n in self.nodes}
        if len(set(node_ids)) != len(node_ids):
            raise SceneValidationError("duplicate scene-node ids")
        for n in self.nodes:
            if n.entity_type not in ENTITY_TYPES:
                raise SceneValidationError(f"node {n.id}: invalid entity_type {n.entity_type!r}")

        for e in self.edges:
            if e.layer not in EDGE_LAYERS:
                raise SceneValidationError(f"edge {e.id}: invalid layer {e.layer!r}")
            if e.source not in node_by_id or e.target not in node_by_id:
                raise SceneValidationError(f"edge {e.id} references an unknown node")

        for p in self.paths:
            for nid in p.node_ids:
                if nid not in node_by_id:
                    raise SceneValidationError(f"path {p.id} references unknown node {nid!r}")

        # --- the unsupported scene: honest and empty ---
        if self.scene_type == "unsupported":
            if self.occurrence_map:
                raise SceneValidationError("unsupported scene must carry no occurrences")
            if not self.warnings:
                raise SceneValidationError("unsupported scene must explain why in warnings")
            return

        # --- occurrence invariants ---
        occ_ids = [o.occurrence_id for o in self.occurrence_map]
        if len(set(occ_ids)) != len(occ_ids):
            raise SceneValidationError("duplicate occurrence ids")
        if self.occurrence_map:
            indices = sorted(o.sequence_index for o in self.occurrence_map)
            if indices != list(range(len(self.occurrence_map))):
                raise SceneValidationError(
                    f"occurrence sequence indices must be contiguous 0..N-1, got {indices}")

        for o in self.occurrence_map:
            if o.mapping_status not in ("exact", "contextual", "approximate", "unsupported"):
                raise SceneValidationError(
                    f"occurrence {o.occurrence_id}: invalid mapping_status {o.mapping_status!r}")
            node = node_by_id.get(o.node_id)
            if node is None:
                raise SceneValidationError(
                    f"occurrence {o.occurrence_id}: node {o.node_id!r} not in scene")

            # THE honesty gate: a chord occurrence must not light a key node.
            if node.entity_type == "key" and o.entity_type in _CHORD_ENTITY_TYPES:
                raise SceneValidationError(
                    f"occurrence {o.occurrence_id}: chord ({o.chord_symbol or o.roman}) mapped "
                    f"onto key node {o.node_id!r} -- a chord is never its key context")

            if o.mapping_status == "exact":
                if not o.primary_node_id:
                    raise SceneValidationError(
                        f"occurrence {o.occurrence_id}: exact mapping needs a canonical node")
                if is_proxy_node_id(o.primary_node_id) or is_proxy_node_id(o.node_id):
                    raise SceneValidationError(
                        f"occurrence {o.occurrence_id}: exact mapping cannot use a proxy node")
                prim = node_by_id.get(o.primary_node_id)
                if prim is not None and prim.entity_type == "key":
                    raise SceneValidationError(
                        f"occurrence {o.occurrence_id}: exact mapping points at a key node")

    # -- activation ---------------------------------------------------------------------------- #

    def attach_activations(self) -> None:
        """Populate every occurrence's :class:`SceneActivation` from the edge graph (plan §4.2).

        Idempotent; call after nodes/edges/occurrences are built and before :meth:`validate`."""
        self.occurrence_map = compute_activations(self)

    # -- serialisation ------------------------------------------------------------------------ #

    def to_dict(self) -> Dict:
        return {
            "schema": self.schema,
            "sceneId": self.scene_id,
            "sceneType": self.scene_type,
            "title": self.title,
            "subtitle": self.subtitle,
            "sourceKind": self.source_kind,
            "sourceId": self.source_id,
            "pedagogicalGoal": self.pedagogical_goal,
            "semanticScope": self.semantic_scope,
            "keyContext": self.key_context,
            "mode": self.mode,
            "generatorId": self.generator_id,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "paths": [p.to_dict() for p in self.paths],
            "occurrenceMap": [o.to_dict() for o in self.occurrence_map],
            "layerDefinitions": [l.to_dict() for l in self.layer_definitions],
            "supportedActions": [a.to_dict() for a in self.supported_actions],
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "counts": self.counts(),
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "GraphScene":
        return cls(
            scene_id=d["sceneId"],
            scene_type=d["sceneType"],
            title=d["title"],
            subtitle=d.get("subtitle", ""),
            source_kind=d["sourceKind"],
            source_id=d.get("sourceId", ""),
            pedagogical_goal=d.get("pedagogicalGoal", ""),
            semantic_scope=d["semanticScope"],
            key_context=d.get("keyContext"),
            mode=d.get("mode"),
            generator_id=d.get("generatorId", ""),
            nodes=[GraphSceneNode.from_dict(n) for n in d.get("nodes", [])],
            edges=[GraphSceneEdge.from_dict(e) for e in d.get("edges", [])],
            paths=[GraphScenePath.from_dict(p) for p in d.get("paths", [])],
            occurrence_map=[SceneOccurrence.from_dict(o) for o in d.get("occurrenceMap", [])],
            layer_definitions=[SceneLayer.from_dict(l) for l in d.get("layerDefinitions", [])],
            supported_actions=[LaunchAction.from_dict(a) for a in d.get("supportedActions", [])],
            warnings=list(d.get("warnings", [])),
            metadata=dict(d.get("metadata", {})),
            schema=d.get("schema", SCENE_SCHEMA),
        )


# --------------------------------------------------------------------------------------------- #
# Activation derivation (graph-structural, never colour/label) (plan section 4.2)
# --------------------------------------------------------------------------------------------- #

#: Membership relations that link a chord node to its broad-function-family (or class) node.
_MEMBERSHIP_RELATIONS = frozenset({
    "member_of_function", "instance_of", "inversion_of", "same_function", "substitutes_for",
})
#: Relations that link a chord node to its key-context anchor.
_CONTEXT_RELATIONS = frozenset({"belongs_to_key", "atlas_node_available"})
#: Entity types that count as a "family" node (the secondary halo, not the current chord).
_FAMILY_ENTITY_TYPES = frozenset({"function", "quality"})
#: Scene types where opening/intermediate/arrival occurrence roles are meaningful (a route that
#: goes somewhere), as opposed to a flat enumeration/classification.
_PROGRESSION_SCENE_TYPES = frozenset({
    "functional_progression", "cadence_resolution", "voice_leading_path",
    "polyphonic_harmony_path", "score_harmonic_path",
})


def compute_activations(scene: "GraphScene") -> List[SceneOccurrence]:
    """Derive each occurrence's :class:`SceneActivation` from the scene's edge graph (plan §4.2).

    Family membership is read from membership edges (plus any function/quality node the occurrence
    already lists as context); key context from ``belongs_to_key`` edges / listed key anchors; and
    the active motion from the sequence/theory edges to the *next* occurrence.  Nothing is inferred
    from node colour or label.  Returns a NEW occurrence list (frozen dataclasses replaced), leaving
    the input untouched; callers assign it back to ``scene.occurrence_map``.
    """
    occs = sorted(scene.occurrence_map, key=lambda o: o.sequence_index)
    node_by_id = {n.id: n for n in scene.nodes}
    edges_by_source: Dict[str, List[GraphSceneEdge]] = {}
    for e in scene.edges:
        edges_by_source.setdefault(e.source, []).append(e)
    is_progression = scene.scene_type in _PROGRESSION_SCENE_TYPES
    n = len(occs)
    out: List[SceneOccurrence] = []
    for i, o in enumerate(occs):
        prev = occs[i - 1] if i > 0 else None
        nxt = occs[i + 1] if i + 1 < n else None
        fam_ids: List[str] = []
        struct_ids: List[str] = []
        key_ctx: List[str] = []
        outgoing = edges_by_source.get(o.node_id, ())
        for e in outgoing:
            tgt = node_by_id.get(e.target)
            if tgt is None:
                continue
            # membership edge -> a family node lights as STRUCTURE (never as harmonic motion), even
            # if a generator tagged the edge's own layer 'context' (plan sections 4, 5, 15.4).
            if e.relation in _MEMBERSHIP_RELATIONS and tgt.entity_type in _FAMILY_ENTITY_TYPES:
                if e.target not in fam_ids:
                    fam_ids.append(e.target)
                if e.id not in struct_ids:
                    struct_ids.append(e.id)
            elif e.relation in _CONTEXT_RELATIONS and tgt.entity_type == "key":
                if e.target not in key_ctx:
                    key_ctx.append(e.target)
        # fold in any family / key node the occurrence already names as context
        for cid in o.context_node_ids:
            cn = node_by_id.get(cid)
            if cn is None:
                continue
            if cn.entity_type in _FAMILY_ENTITY_TYPES and cid not in fam_ids:
                fam_ids.append(cid)
            elif cn.entity_type == "key" and cid not in key_ctx:
                key_ctx.append(cid)
        seq_ids: List[str] = []
        th_ids: List[str] = []
        if nxt is not None:
            for e in outgoing:
                if e.target != nxt.node_id:
                    continue
                if e.layer == "sequence" and e.id not in seq_ids:
                    seq_ids.append(e.id)
                elif e.layer == "theory" and e.id not in th_ids:
                    th_ids.append(e.id)
        activation = SceneActivation(
            current_node_id=o.node_id,
            family_node_ids=tuple(fam_ids),
            context_node_ids=tuple(key_ctx),
            structure_edge_ids=tuple(struct_ids),
            sequence_edge_ids=tuple(seq_ids),
            theory_edge_ids=tuple(th_ids),
            previous_occurrence_id=(prev.occurrence_id if prev else None),
            next_occurrence_id=(nxt.occurrence_id if nxt else None),
        )
        role = o.occurrence_role
        if not role and is_progression:
            role = "opening" if i == 0 else ("arrival" if i == n - 1 else "intermediate")
        out.append(replace(o, activation=activation, occurrence_role=role))
    return out


def unsupported_scene(*, scene_id: str, title: str, source_kind: str, source_id: str,
                      reason: str, subtitle: str = "",
                      metadata: Optional[Dict] = None) -> GraphScene:
    """Build the honest fail-closed scene (plan section 1 "Fail closed").

    No nodes, no occurrences -- the trainer/Lab keeps running while the graph states plainly that
    no suitable harmonic graph exists for this exercise yet.
    """
    scene = GraphScene(
        scene_id=scene_id,
        scene_type="unsupported",
        title=title,
        subtitle=subtitle or "No suitable harmonic graph is available for this exercise yet",
        source_kind=source_kind,
        source_id=source_id,
        pedagogical_goal="",
        semantic_scope="none",
        warnings=[reason],
        metadata=dict(metadata or {}),
    )
    scene.validate()
    return scene


__all__ = [
    "SCENE_SCHEMA",
    "SCENE_TYPES",
    "SCENE_SOURCE_KINDS",
    "SEMANTIC_SCOPES",
    "ENTITY_TYPES",
    "EDGE_LAYERS",
    "KIND_TO_ENTITY_TYPE",
    "SceneValidationError",
    "GraphSceneNode",
    "GraphSceneEdge",
    "GraphScenePath",
    "SceneActivation",
    "SceneOccurrence",
    "SceneLayer",
    "GraphScene",
    "compute_activations",
    "unsupported_scene",
]
