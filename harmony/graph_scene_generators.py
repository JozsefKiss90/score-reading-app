"""Scene generators: adapt the existing network + projection into a :class:`GraphScene`.

Each generator is a thin, deterministic adapter that

  1. builds the *right* :class:`~harmony.harmonic_network.HarmonicNetwork` -- the topic-specific
     template, parameterised by a :class:`~harmony.harmonic_network.NetworkBuildContext` derived
     from the running spec (so a G-major drill builds a G-major graph, never a stale C-major one);
  2. projects the exercise onto it with the already-tested
     :func:`~harmony.network_projection.project_harmony_exercise` /
     :func:`~harmony.network_projection.project_lab_experiment`;
  3. adapts the canonical nodes/edges/paths + the projection's occurrences into the pure
     :class:`~harmony.graph_scene.GraphScene` contract, tagging every edge with its
     :data:`~harmony.graph_scene.EDGE_LAYERS` layer so the enumeration/sequence overlay is kept
     strictly separate from asserted harmonic theory.

The existing templates thereby become *internal scene generators* (plan section 8): no theory is
re-encoded, and the honesty rules already enforced by the projector + reasserted by
:meth:`GraphScene.validate` guarantee a chord never lands on a key node.

Pure / headless: no Qt, JS, MusicXML, or file I/O.  The router (:mod:`harmony.graph_scene_router`)
decides *which* generator to call; this module knows *how* to build each scene.
"""

from __future__ import annotations

import itertools
from typing import Dict, List, Optional, Tuple

from harmony.exercise_spec import HarmonyExerciseSpec, compile_exercise
from harmony.harmonic_network import (
    BROAD_FUNCTION,
    HarmonicNetwork,
    NetworkBuildContext,
    build_network,
)
from harmony.network_template import get_template
from harmony.network_projection import project_harmony_exercise, project_lab_experiment
from harmony.harmonic_flow import DrillGraphProjection, occurrence_id
from harmony.atlas import build_atlas, quality_id
from harmony.harmonic_network import _resolve_triad_ref, _spoke_xy, _present
from theory.diatonic_harmony import note_pc
from harmony.graph_scene import (
    GraphScene,
    GraphSceneEdge,
    GraphSceneNode,
    GraphScenePath,
    KIND_TO_ENTITY_TYPE,
    SceneLayer,
    SceneOccurrence,
    unsupported_scene,
)


# --------------------------------------------------------------------------------------------- #
# Scene-type -> generator wiring
# --------------------------------------------------------------------------------------------- #

#: Which internal template each scene type is generated from.
SCENE_TEMPLATE: Dict[str, str] = {
    "legacy_key_relation": "dominant_diminished_relative_network_v1",
    "diatonic_key_field": "core_triad_function_network_v1",
    "degree_transposition": "transposition_orbit_network_v1",
    "triad_quality_class": "quality_class_network_v1",
    "functional_progression": "cadence_resolution_network_v1",
    "cadence_resolution": "cadence_resolution_network_v1",
    "inversion_space": "inversion_space_network_v1",
}

#: The musical scope each scene spans (GraphScene.semantic_scope).
SCENE_SCOPE: Dict[str, str] = {
    "legacy_key_relation": "relations",
    "diatonic_key_field": "local_key",
    "degree_transposition": "cross_key",
    "triad_quality_class": "class",
    "functional_progression": "progression",
    "cadence_resolution": "progression",
    "inversion_space": "voicing",
    "voice_leading_path": "voicing",
    "polyphonic_harmony_path": "progression",
    "score_harmonic_path": "score",
}

#: The pedagogical goal string surfaced in the scene header.
SCENE_GOAL: Dict[str, str] = {
    "legacy_key_relation": "Explore how whole keys, relative minors, dominant sevenths and "
                           "leading-tone diminished triads are wired by fifths and functional pull.",
    "diatonic_key_field": "Enumerate the seven exact diatonic triads of one key, clustered by "
                          "broad function. Scale-order is enumeration, not a progression.",
    "degree_transposition": "See one invariant scale degree realised as an exact chord in every "
                            "key -- a transposition, never a modulation.",
    "triad_quality_class": "Classify a key's diatonic triads by chord quality. A classification, "
                           "not a progression.",
    "functional_progression": "Follow a bounded functional route: tonic -> predominant -> dominant "
                              "-> tonic, with the active harmonic motion shown honestly.",
    "cadence_resolution": "Study a cadence: the source chord, its tendency/common tones and the "
                          "arrival chord.",
    "inversion_space": "One chord identity across its inversion voicings -- same chord, changing "
                       "bass. The function never changes.",
    "voice_leading_path": "Follow the harmonic path AND the individual SATB voices: common tones "
                          "held, tendency tones resolved.",
    "polyphonic_harmony_path": "Two independent voices imply a chord on each slice; follow the "
                               "voice lanes and the harmony they outline.",
    "score_harmonic_path": "Walk a real score's harmony chord by chord, honestly: diatonic chords "
                           "as exact markers, chromatic ones as honest markers, key areas grouped.",
}

#: Relation -> the scene layer it belongs to.  The runtime sequence overlay is added separately
#: (always layer ``sequence``); these are the *canonical* network relations.
RELATION_TO_LAYER: Dict[str, str] = {
    # context: a chord's link to its key anchor
    "belongs_to_key": "context",
    "atlas_node_available": "context",
    # structure: membership / instance / inversion skeleton + key-relation topology
    "member_of_function": "structure",
    "instance_of": "structure",
    "inversion_of": "structure",
    "fifth_relation": "structure",
    "relative_minor_of": "structure",
    "relative_major_of": "structure",
    "same_pitch_class": "structure",
    "shares_scale_with": "structure",
    "same_function": "structure",
    "substitutes_for": "structure",
    # theory: asserted harmonic motion
    "resolves_to": "theory",
    "prepares": "theory",
    "prolongs": "theory",
    "leading_tone_to": "theory",
    "dominant_of": "theory",
    # voice-leading: individual-voice motion
    "voice_leads_to": "voice_leading",
}

#: Canonical relations that are host-integration hints, not pedagogy -- dropped from the scene.
_SKIP_EDGE_RELATIONS = frozenset({"trainer_drill_available"})

_LAYER_LABELS = {
    "context": "Key context", "structure": "Structure", "theory": "Theory (harmonic motion)",
    "sequence": "Drill order", "voice_leading": "Voice leading",
}
_LAYER_DESC = {
    "context": "Each chord's link to its key-context anchor.",
    "structure": "Membership / instance / relation skeleton of the scene.",
    "theory": "Asserted harmonic relations (resolution, preparation, ...). Optional layer.",
    "sequence": "The order the drill visits its items. Pedagogical, not asserted harmony.",
    "voice_leading": "Individual-voice motion between chords.",
}
#: Scene types whose theory layer is ON by default (a real progression / relation graph).  For
#: enumeration / class / voicing scenes the theory layer is an optional, default-off overlay so
#: scale-order is never mistaken for progression (plan sections 1, 5.A/B).
_THEORY_DEFAULT_ON = frozenset({
    "functional_progression", "cadence_resolution", "legacy_key_relation", "voice_leading_path",
})


# --------------------------------------------------------------------------------------------- #
# Build-context derivation (from the running spec) -- never from a root pitch class
# --------------------------------------------------------------------------------------------- #

def _tonic_of(key: str) -> str:
    return key.split()[0] if key else "C"


def _keys_from_compiled(spec: HarmonyExerciseSpec) -> Tuple[str, ...]:
    """Distinct key tonics the drill actually visits, in order (matches the drill exactly)."""
    seen: List[str] = []
    for c in compile_exercise(spec).chords:
        k = _tonic_of(c.triad.key)
        if k not in seen:
            seen.append(k)
    return tuple(seen)


def context_from_spec(spec: HarmonyExerciseSpec) -> NetworkBuildContext:
    """Derive the :class:`NetworkBuildContext` a topic template must build against.

    Keys come from the *compiled* chords (what the drill really contains), not from a guessed
    root pitch class -- this is what makes a G-major full-key drill build a G-major graph.
    """
    mode = spec.mode
    if spec.drill == "full_key":
        return NetworkBuildContext(key=_tonic_of(spec.key), mode=mode)
    if spec.drill == "horizontal_degree":
        keys = _keys_from_compiled(spec)
        return NetworkBuildContext(degree=spec.degree, mode=mode, keys=keys)
    if spec.drill == "quality":
        keys = _keys_from_compiled(spec)
        return NetworkBuildContext(key=(keys[0] if keys else "C"), mode=mode,
                                   quality=spec.quality, keys=keys)
    if spec.drill == "function":
        keys = tuple(spec.keys) if spec.keys else _keys_from_compiled(spec)
        first = _tonic_of(keys[0]) if keys else "C"
        return NetworkBuildContext(key=first, mode=mode, pattern=tuple(spec.pattern), keys=keys)
    return NetworkBuildContext(key=_tonic_of(spec.key or "C"), mode=mode)


def _key_label(ctx: NetworkBuildContext) -> str:
    return f"{ctx.key} {'minor' if ctx.mode != 'major' else 'major'}"


# --------------------------------------------------------------------------------------------- #
# Adapter: NetNode / NetEdge / ProjectionNode / HarmonicStep -> scene primitives
# --------------------------------------------------------------------------------------------- #

def _dedupe(seq) -> Tuple[str, ...]:
    out: List[str] = []
    for s in seq:
        if s and s not in out:
            out.append(s)
    return tuple(out)


def _scene_node_from_netnode(n) -> GraphSceneNode:
    data = dict(n.data or {})
    etype = KIND_TO_ENTITY_TYPE.get(n.kind, "occurrence")
    quality = (n.quality or data.get("quality", "") or "")
    # A diatonic-triad node whose quality is diminished (vii° / ii°) is a DIMINISHED entity, not an
    # ordinary triad -- the builder emits all seven degrees as kind 'diatonic_triad', so the generic
    # kind->type map alone would mistype the leading-tone triad (matches the hand-built generators).
    visual_class = n.visual_class
    if n.kind == "diatonic_triad" and str(quality).startswith("dim"):
        etype = "diminished"
        visual_class = "purple"
    refs = _dedupe(list(n.atlas_refs or []) + ([n.canonical_ref] if n.canonical_ref else []))
    is_chord = etype in ("triad", "seventh", "diminished", "inversion")
    return GraphSceneNode(
        id=n.id, label=n.label, entity_type=etype,
        sublabel=str(data.get("sublabel", "") or (data.get("roman", "") if is_chord else "")),
        semantic_level=n.semantic_level, entity_role=n.entity_role,
        key_context=(data.get("key", "") or (n.key_contexts[0] if n.key_contexts else "")),
        roman=data.get("roman", ""),
        chord_symbol=(data.get("chordSymbol", "") or (n.label if is_chord else "")),
        chord_tones=tuple(data.get("chordTones", ()) or ()),
        quality=quality,
        function_label=(data.get("functionLabel", "") or data.get("function_label", "")),
        degree_index=data.get("degreeIndex"),
        x=n.x, y=n.y, radius=n.radius, visual_class=visual_class,
        canonical_refs=refs, explanation=n.explanation, data=data)


def _scene_node_from_proxy(pn) -> GraphSceneNode:
    data = dict(pn.data or {})
    return GraphSceneNode(
        id=pn.id, label=pn.label, entity_type="occurrence",
        sublabel=str(data.get("roman", "") or ""), semantic_level="chord", entity_role="instance",
        key_context=data.get("key", ""), roman=data.get("roman", ""),
        chord_symbol=data.get("chordSymbol", pn.label), quality=data.get("quality", ""),
        degree_index=data.get("degreeIndex"), x=pn.x, y=pn.y, radius=16.0,
        visual_class=pn.visual_class, canonical_refs=tuple(pn.atlas_refs or ()),
        explanation="Overlay: this chord has no exact node in this scene's template.", data=data)


def _scene_edge_from_netedge(e) -> Optional[GraphSceneEdge]:
    if e.relation in _SKIP_EDGE_RELATIONS:
        return None
    layer = RELATION_TO_LAYER.get(e.relation, "structure")
    return GraphSceneEdge(
        id=e.id, source=e.source, target=e.target, relation=e.relation, layer=layer,
        directed=(e.direction == "directed"), explanation=e.explanation,
        visual_class=e.visual_class,
        data={"defaultVisible": e.default_visible, "strength": e.strength})


def _scene_edge_from_projedge(pe) -> Optional[GraphSceneEdge]:
    if pe.source == pe.target:
        return None
    return GraphSceneEdge(
        id=pe.id, source=pe.source, target=pe.target, relation=pe.relation, layer="sequence",
        directed=True, explanation=pe.explanation, visual_class=pe.visual_class,
        data={"canonicalEdgeId": pe.canonical_edge_id})


def _occurrence_entity_type(step) -> str:
    if step.source_kind == "score":
        return "score_slice"
    if step.inversion is not None and step.drill_family == "inversion":
        return "inversion"
    if (step.quality or "").startswith("dim"):
        return "diminished"
    return "triad"


def _edge_type_word(tr) -> str:
    if tr is None:
        return ""
    if tr.theory_relation:
        return "theory"
    if tr.sequence_relation == "transpose_next":
        return "transposition"
    if tr.sequence_relation == "voicing_next":
        return "voice leading"
    if tr.sequence_relation == "enumerate_next":
        return "sequence only (enumeration)"
    return "sequence only"


def _detail_for(step, tr) -> Dict:
    return {
        "keyContext": step.key_context,
        "roman": step.roman,
        "chordSymbol": step.chord_symbol,
        "chordTones": list(step.chord_tones),
        "quality": step.quality,
        "intervalLayer": step.interval_layer,
        "broadFunction": BROAD_FUNCTION.get(step.function_label, ""),
        "functionLabel": step.function_label,
        "whyBelongs": step.mapping_reason,
        "relationToNext": (tr.explanation if tr else ""),
        "edgeType": _edge_type_word(tr),
        "sequenceSemantics": step.sequence_semantics,
    }


def _occurrences(projection: DrillGraphProjection) -> List[SceneOccurrence]:
    tr_by_from = {t.from_occurrence: t for t in projection.transitions}
    out: List[SceneOccurrence] = []
    for step in projection.steps:
        tr = tr_by_from.get(step.occurrence_id)
        out.append(SceneOccurrence(
            occurrence_id=step.occurrence_id, sequence_index=step.sequence_index,
            node_id=step.visual_node_id, entity_type=_occurrence_entity_type(step),
            mapping_status=step.mapping_status, group_index=step.group_index,
            index_in_group=step.index_in_group, primary_node_id=step.primary_network_node,
            context_node_ids=tuple(step.context_network_nodes), roman=step.roman,
            chord_symbol=step.chord_symbol, key_context=step.key_context, quality=step.quality,
            mapping_reason=step.mapping_reason,
            next_sequence_relation=(tr.sequence_relation if tr else None),
            next_theory_relation=(tr.theory_relation if tr else None),
            next_relation_status=(tr.relation_status if tr else None),
            next_is_group_boundary=(tr.is_group_boundary if tr else False),
            next_explanation=(tr.explanation if tr else ""),
            detail=_detail_for(step, tr)))
    return out


def _layer_defs(edges: List[GraphSceneEdge], scene_type: str) -> List[SceneLayer]:
    present = _dedupe(e.layer for e in edges)
    theory_on = scene_type in _THEORY_DEFAULT_ON
    defs: List[SceneLayer] = []
    for layer in ("context", "structure", "theory", "sequence", "voice_leading"):
        if layer in present:
            defs.append(SceneLayer(
                id=layer, label=_LAYER_LABELS[layer], kind=layer,
                default_visible=(theory_on if layer == "theory" else True),
                description=_LAYER_DESC[layer]))
    return defs


# --------------------------------------------------------------------------------------------- #
# The assembler
# --------------------------------------------------------------------------------------------- #

def assemble_scene(*, scene_type: str, network: HarmonicNetwork,
                   projection: Optional[DrillGraphProjection], scene_id: str, title: str,
                   subtitle: str, source_kind: str, source_id: str, pedagogical_goal: str,
                   semantic_scope: str, key_context: Optional[str], mode: Optional[str],
                   generator_id: str = "", extra_warnings: Optional[List[str]] = None,
                   metadata: Optional[Dict] = None) -> GraphScene:
    """Compose a built network + optional projection into a validated :class:`GraphScene`."""
    nodes = [_scene_node_from_netnode(n) for n in network.nodes]
    edges: List[GraphSceneEdge] = []
    for e in network.edges:
        se = _scene_edge_from_netedge(e)
        if se is not None:
            edges.append(se)

    occurrence_map: List[SceneOccurrence] = []
    warnings: List[str] = list(extra_warnings or [])
    if projection is not None:
        for pn in projection.projection_nodes:
            nodes.append(_scene_node_from_proxy(pn))
        for pe in projection.projection_edges:
            se = _scene_edge_from_projedge(pe)
            if se is not None:
                edges.append(se)
        occurrence_map = _occurrences(projection)
        warnings.extend(projection.warnings)

    paths = [GraphScenePath(
        id=p.id, label=p.label, node_ids=tuple(p.node_ids), edge_ids=tuple(p.edge_ids),
        romans=tuple(p.romans), key_context=p.key_context, mode=p.mode,
        cadence_type=p.cadence_type) for p in getattr(network, "paths", [])]

    scene = GraphScene(
        scene_id=scene_id, scene_type=scene_type, title=title, subtitle=subtitle,
        source_kind=source_kind, source_id=source_id, pedagogical_goal=pedagogical_goal,
        semantic_scope=semantic_scope, key_context=key_context, mode=mode,
        nodes=nodes, edges=edges, paths=paths, occurrence_map=occurrence_map,
        layer_definitions=_layer_defs(edges, scene_type), supported_actions=[],
        warnings=warnings, metadata=dict(metadata or {}), generator_id=generator_id)
    scene.validate()
    return scene


# --------------------------------------------------------------------------------------------- #
# Public generators (called by the router)
# --------------------------------------------------------------------------------------------- #

def build_exercise_scene(scene_type: str, spec: HarmonyExerciseSpec, *, source_kind: str = "harmony_exercise",
                         source_id: Optional[str] = None, scene_id: Optional[str] = None,
                         extra_warnings: Optional[List[str]] = None) -> GraphScene:
    """Build a scene for a native trainer :class:`HarmonyExerciseSpec` (scenes B/C/D/E/F)."""
    # E: a bounded, path-shaped progression scene (NOT the seven-triad field) with distinct
    # occurrence markers for repeated chords (plan section 5.E).
    if scene_type == "functional_progression":
        return build_functional_progression_scene(
            spec, source_kind=source_kind, source_id=source_id, scene_id=scene_id,
            extra_warnings=extra_warnings)
    # D: one quality anchor + the drill's exact same-quality instances (no cross-key proxies).
    if scene_type == "triad_quality_class":
        return build_quality_class_scene(
            spec, source_kind=source_kind, source_id=source_id, scene_id=scene_id,
            extra_warnings=extra_warnings)
    template_id = SCENE_TEMPLATE[scene_type]
    ctx = context_from_spec(spec)
    network = build_network(get_template(template_id), context=ctx)
    projection = project_harmony_exercise(spec, network)
    sid = source_id or spec.exercise_id
    return assemble_scene(
        scene_type=scene_type, network=network, projection=projection,
        scene_id=(scene_id or f"scene:{scene_type}:{sid}"), title=spec.title,
        subtitle=_key_label(ctx), source_kind=source_kind, source_id=sid,
        pedagogical_goal=SCENE_GOAL.get(scene_type, ""), semantic_scope=SCENE_SCOPE[scene_type],
        key_context=_key_label(ctx), mode=ctx.mode, generator_id=template_id,
        extra_warnings=extra_warnings, metadata={"drill": spec.drill, "render": spec.render})


# --------------------------------------------------------------------------------------------- #
# E. functional_progression -- a BOUNDED, path-shaped progression scene (plan section 5.E)
# --------------------------------------------------------------------------------------------- #

#: Vertical band per broad function (the "function lanes"): predominant up, tonic mid, dominant down.
_FUNC_BAND = {"predominant": -150.0, "tonic": 0.0, "dominant": 150.0}
#: Canonical relations that count as harmonic motion along a progression (reused from the core net).
_PROGRESSION_THEORY_RELS = frozenset({"resolves_to", "prepares", "prolongs", "leading_tone_to"})
_THEORY_VC = {"resolves_to": "resolve", "prepares": "prepare", "prolongs": "prolong",
              "leading_tone_to": "leading"}
_ROOT_MOTION_NAME = {
    0: "stays", 1: "up a semitone", 2: "up a step", 3: "up a minor third", 4: "up a major third",
    5: "up a fourth", 6: "up a tritone", 7: "up a fifth", 8: "down a major third",
    9: "down a minor third", 10: "down a step", 11: "down a semitone",
}


def _progression_groups(compiled) -> List[list]:
    """The compiled chords split into runs by their ``group`` (a key group in a cross-key drill)."""
    return [list(g) for _, g in itertools.groupby(compiled.chords, key=lambda c: c.group)]


def progression_group_map(spec: HarmonyExerciseSpec) -> List[Dict]:
    """Group metadata for a function drill: ``[{groupIndex, key, globalStart, count}]``.

    The host uses this to switch the bounded local-key scene at a group boundary and to translate
    the trainer's global chord index into the shown group's local index (plan section 5.E cross-key
    rule: one local key at a time, rebuild at boundaries, never one giant all-key graph)."""
    groups = _progression_groups(compile_exercise(spec))
    out: List[Dict] = []
    for gi, gch in enumerate(groups):
        out.append({"groupIndex": gi, "key": gch[0].triad.key,
                    "globalStart": gch[0].index, "count": len(gch)})
    return out


def _progression_expl(a, b, rel: Optional[str], common: int, root_motion: Optional[int]) -> str:
    parts = [f"{a.roman} → {b.roman}"]
    if rel == "resolves_to":
        parts.append("dominant resolves to tonic")
    elif rel == "prepares":
        parts.append("predominant prepares the dominant")
    elif rel == "leading_tone_to":
        parts.append("leading tone resolves up to the tonic")
    elif rel == "prolongs":
        parts.append("prolongs the function")
    else:
        parts.append("progression step")
    if common:
        parts.append(f"{common} common tone{'s' if common != 1 else ''}")
    if root_motion is not None:
        parts.append(f"root {_ROOT_MOTION_NAME.get(root_motion, f'+{root_motion} st')}")
    return "; ".join(parts)


def build_functional_progression_scene(
        spec: HarmonyExerciseSpec, *, group_index: int = 0,
        source_kind: str = "harmony_exercise", source_id: Optional[str] = None,
        scene_id: Optional[str] = None, extra_warnings: Optional[List[str]] = None,
        scene_type: str = "functional_progression", cadence_type: Optional[str] = None,
        title: Optional[str] = None) -> GraphScene:
    """A bounded, path-shaped functional progression for ONE local key (plan section 5.E).

    Only the chords in the progression appear -- each occurrence is its OWN marker node (so the two
    ``I`` chords in ``I-IV-V-I`` are two distinct markers of one chord identity), laid out left->right
    by sequence and banded by broad function (predominant / tonic / dominant lanes).  Sequence edges
    trace the drill order; theory edges (a separate layer) light only where the core network
    independently supports the motion.  For a cross-key drill this builds ONE local key at a time
    (``group_index``); the invariant Roman pattern travels in the subtitle + metadata so the host can
    switch scenes at a group boundary instead of drawing a giant all-key graph."""
    compiled = compile_exercise(spec)
    groups = _progression_groups(compiled)
    sid = source_id or spec.exercise_id
    mode = spec.mode
    if not groups:
        return build_unsupported(source_kind=source_kind, source_id=sid,
                                 reason="the progression compiled to no chords")
    n_groups = len(groups)
    gi = max(0, min(int(group_index), n_groups - 1))
    group = groups[gi]
    n = len(group)
    tonic = _tonic_of(group[0].triad.key)
    key_label = group[0].triad.key
    romans = [c.triad.roman for c in group]
    invariant = "–".join(romans)
    atlas = build_atlas()

    # Reuse the core network's SUPPORTED functional-motion edges for this key (no theory re-encoded).
    core = build_network(get_template("core_triad_function_network_v1"),
                         context=NetworkBuildContext(key=tonic, mode=mode))
    core_rel = {(e.source, e.target): e.relation for e in core.edges
                if e.relation in _PROGRESSION_THEORY_RELS}

    def _core_id(deg: int) -> str:
        return f"hn:triad:{tonic}:{mode}:{deg}"

    nodes: List[GraphSceneNode] = []
    edges: List[GraphSceneEdge] = []
    occurrences: List[SceneOccurrence] = []

    # key context anchor (secondary, persistent)
    key_id = f"prog:key:{tonic}:{mode}"
    nodes.append(GraphSceneNode(
        id=key_id, label=key_label, entity_type="key", entity_role="anchor",
        semantic_level="key", key_context=key_label, visual_class="slate",
        x=0.0, y=-300.0, radius=24.0, explanation=f"The key context: {key_label}."))

    # function-lane anchors (context regions)
    lane_id: Dict[str, str] = {}
    for fam, band in _FUNC_BAND.items():
        fid = f"prog:fn:{fam}"
        lane_id[fam] = fid
        nodes.append(GraphSceneNode(
            id=fid, label=fam.title(), entity_type="function", entity_role="family",
            semantic_level="function", function_label=fam, visual_class="amber",
            sublabel="lane", x=-360.0, y=band, radius=20.0,
            explanation=f"The {fam} function lane."))

    # one MARKER per occurrence (distinct markers for repeats)
    per: List[Dict] = []
    for i, c in enumerate(group):
        t = c.triad
        broad = BROAD_FUNCTION.get(t.function_label, "tonic")
        etype = "diminished" if str(t.chord_quality).startswith("dim") else "triad"
        x = -260.0 + (520.0 * (i / (n - 1)) if n > 1 else 0.0)
        mid = f"prog:{sid}:{gi}:{i}"
        ref = _resolve_triad_ref(atlas, tonic, mode, t.degree_index)
        nodes.append(GraphSceneNode(
            id=mid, label=t.chord_symbol, entity_type=etype, sublabel=t.roman,
            semantic_level="chord", entity_role="instance", key_context=t.key, roman=t.roman,
            chord_symbol=t.chord_symbol, chord_tones=tuple(t.pitches), quality=t.chord_quality,
            function_label=t.function_label, degree_index=t.degree_index,
            visual_class=("purple" if etype == "diminished" else "teal"),
            x=x, y=_FUNC_BAND.get(broad, 0.0), radius=20.0,
            canonical_refs=((ref,) if ref else ()),
            data={"key": t.key, "roman": t.roman, "degreeIndex": t.degree_index,
                  "chordIdentity": f"{t.roman}@{tonic}", "broadFunction": broad,
                  "globalIndex": c.index},
            explanation=f"{t.chord_symbol} is {t.roman} in {t.key} ({broad} function)."))
        # faint membership edge marker -> its function lane
        edges.append(GraphSceneEdge(
            id=f"prog:mem:{gi}:{i}", source=mid, target=lane_id[broad],
            relation="member_of_function", layer="context", directed=True,
            explanation=f"{t.roman} is a {broad}-function chord.", visual_class="membership"))
        per.append({"id": mid, "etype": etype, "broad": broad, "triad": t, "global": c.index})

    # sequence + theory edges + occurrences
    for i in range(n):
        t = per[i]["triad"]
        rel = None
        common = 0
        root_motion = None
        expl = ""
        if i < n - 1:
            b = per[i + 1]["triad"]
            rel = core_rel.get((_core_id(t.degree_index), _core_id(b.degree_index)))
            common = len(set(t.pitch_classes) & set(b.pitch_classes))
            root_motion = (note_pc(b.root) - note_pc(t.root)) % 12
            expl = _progression_expl(t, b, rel, common, root_motion)
            edges.append(GraphSceneEdge(
                id=f"prog:seq:{gi}:{i}", source=per[i]["id"], target=per[i + 1]["id"],
                relation="drill_next", layer="sequence", directed=True,
                explanation=expl, visual_class="overlay-drill"))
            if rel:
                edges.append(GraphSceneEdge(
                    id=f"prog:th:{gi}:{i}", source=per[i]["id"], target=per[i + 1]["id"],
                    relation=rel, layer="theory", directed=True,
                    explanation=f"{t.roman} {rel.replace('_', ' ')} {b.roman}",
                    visual_class=_THEORY_VC.get(rel, "resolve")))
        occurrences.append(SceneOccurrence(
            occurrence_id=occurrence_id(sid, gi, i, i), sequence_index=i, node_id=per[i]["id"],
            entity_type=per[i]["etype"], mapping_status="exact", group_index=gi, index_in_group=i,
            primary_node_id=per[i]["id"], context_node_ids=(key_id, lane_id[per[i]["broad"]]),
            roman=t.roman, chord_symbol=t.chord_symbol, key_context=t.key, quality=t.chord_quality,
            mapping_reason=f"exact {t.chord_symbol} ({t.roman}) marker in the {key_label} progression",
            next_sequence_relation=("drill_next" if i < n - 1 else None),
            next_theory_relation=rel,
            next_relation_status=("exact" if rel else ("sequence_only" if i < n - 1 else None)),
            next_is_group_boundary=False, next_explanation=expl,
            detail={"keyContext": t.key, "roman": t.roman, "chordSymbol": t.chord_symbol,
                    "chordTones": list(t.pitches), "quality": t.chord_quality,
                    "intervalLayer": t.interval_layer, "broadFunction": per[i]["broad"],
                    "functionLabel": t.function_label,
                    "whyBelongs": f"a {per[i]['broad']}-function chord in the {key_label} progression",
                    "relationToNext": expl, "edgeType": ("theory" if rel else "sequence only"),
                    "commonTones": common, "rootMotion": root_motion,
                    "globalIndex": per[i]["global"]}))

    groups_meta = [{"groupIndex": k, "key": g[0].triad.key, "globalStart": g[0].index,
                    "count": len(g)} for k, g in enumerate(groups)]
    warnings = list(extra_warnings or [])
    if n_groups > 1:
        warnings.append(
            f"cross-key drill: showing key {gi + 1} of {n_groups} ({key_label}); the pattern "
            f"{invariant} transposes across the other keys (not a modulation).")
    subtitle = f"{key_label} · {invariant}"
    if cadence_type:
        subtitle += f"  ·  {cadence_type} cadence"
    if n_groups > 1:
        subtitle += f"  ·  key {gi + 1}/{n_groups}"

    scene = GraphScene(
        scene_id=(scene_id or f"scene:{scene_type}:{sid}:{gi}"),
        scene_type=scene_type, title=(title or spec.title), subtitle=subtitle,
        source_kind=source_kind, source_id=sid,
        pedagogical_goal=SCENE_GOAL.get(scene_type, SCENE_GOAL["functional_progression"]),
        semantic_scope="progression",
        key_context=key_label, mode=mode, nodes=nodes, edges=edges, paths=[],
        occurrence_map=occurrences, layer_definitions=_layer_defs(edges, scene_type),
        supported_actions=[], warnings=warnings,
        metadata={"drill": "function", "invariantRomans": romans, "groups": groups_meta,
                  "shownGroup": gi, "totalGroups": n_groups, "cadenceType": cadence_type},
        generator_id=scene_type)
    scene.validate()
    return scene


# --------------------------------------------------------------------------------------------- #
# D. triad_quality_class -- one quality anchor + the drill's concrete instances (plan section 5.D)
# --------------------------------------------------------------------------------------------- #

_QUALITY_INTERVALS = {"major": "M3 + m3", "minor": "m3 + M3", "diminished": "m3 + m3",
                      "augmented": "M3 + M3"}


def build_quality_class_scene(spec: HarmonyExerciseSpec, *, source_kind: str = "harmony_exercise",
                              source_id: Optional[str] = None, scene_id: Optional[str] = None,
                              extra_warnings: Optional[List[str]] = None) -> GraphScene:
    """A quality class: one quality anchor orbited by the drill's exact same-quality triads (5.D).

    A ``quality`` drill enumerates triads of ONE quality across several keys (e.g. C, F, G, Db, ...
    major triads); each is an EXACT instance around the quality anchor with its own key/Roman
    context -- no cross-key proxies (the earlier single-key template mismatched this).  The overlay
    is ``enumerate_next`` -- a classification, never a progression (no theory edges)."""
    compiled = compile_exercise(spec)
    chords = compiled.chords
    sid = source_id or spec.exercise_id
    mode = spec.mode
    if not chords:
        return build_unsupported(source_kind=source_kind, source_id=sid,
                                 reason="the quality drill compiled to no chords")
    quality = spec.quality or chords[0].triad.chord_quality
    interval = _QUALITY_INTERVALS.get(quality, chords[0].triad.interval_layer or "")
    atlas = build_atlas()
    is_dim = quality == "diminished"

    qid = f"qcls:quality:{quality}"
    q_ref = _present(atlas, quality_id(quality))
    nodes: List[GraphSceneNode] = [GraphSceneNode(
        id=qid, label=f"{quality.title()} triads", entity_type="quality", entity_role="reference",
        semantic_level="class", quality=quality, sublabel=interval,
        visual_class=("purple" if is_dim else "amber"), x=0.0, y=0.0, radius=26.0,
        canonical_refs=((q_ref,) if q_ref else ()),
        data={"quality": quality, "intervalLayer": interval},
        explanation=(f"The {quality} triad class (interval structure {interval}). A quality "
                     f"classification, not a progression."))]
    edges: List[GraphSceneEdge] = []
    occurrences: List[SceneOccurrence] = []
    n = len(chords)
    ids = [f"qcls:{sid}:{i}" for i in range(n)]
    for i, c in enumerate(chords):
        t = c.triad
        x, y = _spoke_xy(i, n, 300.0, 0.0)
        etype = "diminished" if str(t.chord_quality).startswith("dim") else "triad"
        ref = _resolve_triad_ref(atlas, _tonic_of(t.key), t.mode, t.degree_index)
        nodes.append(GraphSceneNode(
            id=ids[i], label=t.chord_symbol, entity_type=etype,
            sublabel=f"{t.roman} in {_tonic_of(t.key)}", semantic_level="chord",
            entity_role="instance", key_context=t.key, roman=t.roman, chord_symbol=t.chord_symbol,
            chord_tones=tuple(t.pitches), quality=t.chord_quality, degree_index=t.degree_index,
            visual_class=("purple" if etype == "diminished" else "teal"), x=x, y=y, radius=19.0,
            canonical_refs=((ref,) if ref else ()),
            data={"key": t.key, "roman": t.roman, "quality": t.chord_quality,
                  "intervalLayer": t.interval_layer, "globalIndex": c.index},
            explanation=f"{t.chord_symbol} is a {quality} triad ({t.roman} in {t.key})."))
        edges.append(GraphSceneEdge(
            id=f"qcls:mem:{i}", source=ids[i], target=qid, relation="instance_of",
            layer="structure", directed=True,
            explanation=f"{t.chord_symbol} is an instance of the {quality} class.",
            visual_class="membership"))
        if i < n - 1:
            edges.append(GraphSceneEdge(
                id=f"qcls:seq:{i}", source=ids[i], target=ids[i + 1], relation="enumerate_next",
                layer="sequence", directed=True,
                explanation="next item in the quality enumeration (a classification, not motion)",
                visual_class="overlay-enumerate"))
        occurrences.append(SceneOccurrence(
            occurrence_id=occurrence_id(sid, 0, i, i), sequence_index=i, node_id=ids[i],
            entity_type=etype, mapping_status="exact", group_index=0, index_in_group=i,
            primary_node_id=ids[i], context_node_ids=(qid,), roman=t.roman,
            chord_symbol=t.chord_symbol, key_context=t.key, quality=t.chord_quality,
            mapping_reason=f"exact {quality} triad {t.chord_symbol} ({t.roman} in {t.key})",
            next_sequence_relation=("enumerate_next" if i < n - 1 else None),
            next_theory_relation=None,          # NEVER a theory edge: this is a classification
            next_relation_status=("sequence_only" if i < n - 1 else None),
            next_is_group_boundary=False,
            next_explanation=("classification enumeration, not a progression" if i < n - 1 else ""),
            detail={"keyContext": t.key, "roman": t.roman, "chordSymbol": t.chord_symbol,
                    "chordTones": list(t.pitches), "quality": t.chord_quality,
                    "intervalLayer": t.interval_layer, "broadFunction": "", "functionLabel": "",
                    "whyBelongs": f"an instance of the {quality} triad class ({interval})",
                    "relationToNext": "classification, not a progression",
                    "edgeType": "sequence only (enumeration)", "globalIndex": c.index}))

    scene = GraphScene(
        scene_id=(scene_id or f"scene:triad_quality_class:{sid}"),
        scene_type="triad_quality_class", title=spec.title,
        subtitle=f"{quality.title()} triads · {interval}", source_kind=source_kind, source_id=sid,
        pedagogical_goal=SCENE_GOAL["triad_quality_class"], semantic_scope="class",
        key_context=None, mode=mode, nodes=nodes, edges=edges, paths=[],
        occurrence_map=occurrences, layer_definitions=_layer_defs(edges, "triad_quality_class"),
        supported_actions=[], warnings=list(extra_warnings or []),
        metadata={"drill": "quality", "quality": quality, "intervalLayer": interval},
        generator_id="triad_quality_class")
    scene.validate()
    return scene


# --------------------------------------------------------------------------------------------- #
# F. cadence_resolution -- a two/three-chord cadence (source -> arrival) (plan section 5.F)
# --------------------------------------------------------------------------------------------- #

_CADENCE_NAMES = {
    ("V", "I"): "authentic (perfect)", ("V", "i"): "authentic (minor)",
    ("vii°", "I"): "authentic (leading-tone)", ("V", "vi"): "deceptive", ("V", "VI"): "deceptive",
    ("IV", "I"): "plagal", ("iv", "i"): "plagal (minor)", ("I", "V"): "half", ("i", "V"): "half",
    ("i", "v"): "half (minor)", ("VII", "i"): "subtonic", ("♭VII", "i"): "subtonic",
    ("ii°", "i"): "phrygian-approach",
}


def _cadence_label(romans: List[str]) -> str:
    return _CADENCE_NAMES.get(tuple(romans), "cadence")


def build_cadence_scene(lab_spec, *, source_kind: str = "lab", source_id: Optional[str] = None,
                        scene_id: Optional[str] = None,
                        extra_warnings: Optional[List[str]] = None) -> GraphScene:
    """A cadence scene for a Lab ``cadence`` experiment: source -> arrival with the cadence type.

    Reuses the bounded functional-path layout (function lanes + resolves_to/prepares theory edges +
    common-tone/root-motion explanations) from the cadence's underlying diatonic function spec, and
    labels it with the cadence type.  A cadence with a ``voice_leading`` render routes to the
    voice-leading scene instead (handled by the router)."""
    sid = source_id or getattr(lab_spec, "experiment_id", "cadence")
    try:
        exs = [e for e in lab_spec.to_exercise_specs() if e.drill == "function"]
    except Exception:
        exs = []
    if not exs:
        return build_unsupported(
            source_kind=source_kind, source_id=sid,
            reason=(f"the cadence {getattr(lab_spec, 'title', '')!r} has no diatonic function "
                    f"realisation to draw as a resolution"))
    fspec = exs[0]
    cad = (lab_spec.parameters or {}).get("cadence_type") or _cadence_label(list(fspec.pattern))
    return build_functional_progression_scene(
        fspec, scene_type="cadence_resolution", cadence_type=cad, source_kind=source_kind,
        source_id=sid, scene_id=scene_id, extra_warnings=extra_warnings,
        title=getattr(lab_spec, "title", None) or fspec.title)


# --------------------------------------------------------------------------------------------- #
# H/I. voice_leading_path + polyphonic_harmony_path -- a harmonic path + a voice-motion layer
# (plan sections 5.H, 5.I)
# --------------------------------------------------------------------------------------------- #

_VOICE_ORDER = ["Soprano", "Alto", "Tenor", "Bass", "Upper", "Lower"]


def _extract_voices(measure, poly: bool) -> List[Tuple[str, object]]:
    """SATB (or 2-part) voices of a Lab measure, low->high per staff.

    voice_leading: staff2 = [bass, tenor], staff1 = [alto, soprano].
    polyphonic:    staff1 = upper voice, staff2 = lower voice."""
    s1 = [n for n in (getattr(measure, "staff1", None) or []) if not getattr(n, "is_rest", False)]
    s2 = [n for n in (getattr(measure, "staff2", None) or []) if not getattr(n, "is_rest", False)]
    out: List[Tuple[str, object]] = []
    if poly:
        if s1:
            out.append(("Upper", s1[-1]))
        if s2:
            out.append(("Lower", s2[0]))
    else:
        if len(s2) >= 1:
            out.append(("Bass", s2[0]))
        if len(s2) >= 2:
            out.append(("Tenor", s2[1]))
        if len(s1) >= 1:
            out.append(("Alto", s1[0]))
        if len(s1) >= 2:
            out.append(("Soprano", s1[1]))
    return out


def _voice_motion(prev_voices, cur_voices, tonic_pc: int, mode: str) -> Tuple[List[str], bool]:
    """Per-voice motion summary + whether a leading tone resolves to the tonic (major only)."""
    prevd = {name: nt for name, nt in prev_voices}
    curd = {name: nt for name, nt in cur_voices}
    lt_pc = (tonic_pc - 1) % 12
    moves: List[str] = []
    lt_resolves = False
    for name in _VOICE_ORDER:
        if name in prevd and name in curd:
            a = int(getattr(prevd[name], "midi", 0))
            b = int(getattr(curd[name], "midi", 0))
            d = b - a
            arrow = "=" if d == 0 else ("↑" if d > 0 else "↓")
            moves.append(f"{name[0]}{arrow}{'' if d == 0 else abs(d)}")
            if (mode == "major" and int(getattr(prevd[name], "pitch_class", -9)) % 12 == lt_pc
                    and int(getattr(curd[name], "pitch_class", -9)) % 12 == tonic_pc):
                lt_resolves = True
    return moves, lt_resolves


def _voice_edge_expl(prev_ann, cur_ann, moves: List[str], common: int, lt: bool) -> str:
    parts = [f"{prev_ann.roman or prev_ann.chord_symbol} → {cur_ann.roman or cur_ann.chord_symbol}"]
    if moves:
        parts.append("voices " + " ".join(moves))
    if common:
        parts.append(f"{common} common tone{'s' if common != 1 else ''}")
    if lt:
        parts.append("leading tone resolves to the tonic")
    return "; ".join(parts)


def build_voice_leading_scene(lab_spec, *, source_kind: str = "lab", source_id: Optional[str] = None,
                              scene_id: Optional[str] = None,
                              extra_warnings: Optional[List[str]] = None,
                              poly: bool = False) -> GraphScene:
    """Scene H/I: the chord/function path PLUS a voice-motion layer (common + tendency tones).

    ``voice_leading`` (SATB) bands the chord markers by broad function and lights the canonical
    harmonic-motion edges (resolves_to / prepares) as one layer, with a separate ``voice_leading``
    layer carrying the per-voice motion.  ``polyphonic`` (2 parts, ``poly=True``) instead shows the
    ordered slices with their implied chord and two compact voice lanes.  Bounded to the current
    progression (plan sections 5.H, 5.I)."""
    from harmony.lab import compile_lab            # lazy: avoids loading Lab at module import
    exp = compile_lab(lab_spec)
    measures = list(exp.measures)
    sid = source_id or getattr(lab_spec, "experiment_id", "voice")
    scene_type = "polyphonic_harmony_path" if poly else "voice_leading_path"
    if not measures:
        return build_unsupported(source_kind=source_kind, source_id=sid,
                                 reason="the experiment compiled to no measures")
    m0 = measures[0]
    tonic, mode, key_label = m0.tonic, m0.mode, m0.key_display
    tonic_pc = note_pc(tonic)
    n = len(measures)
    atlas = build_atlas()

    # canonical harmonic-motion edges for the key (voice_leading lights them; polyphonic does not
    # assert harmonic motion between independent-voice slices).
    core_rel: Dict[Tuple[str, str], str] = {}
    if not poly:
        core = build_network(get_template("core_triad_function_network_v1"),
                             context=NetworkBuildContext(key=tonic, mode=mode))
        core_rel = {(e.source, e.target): e.relation for e in core.edges
                    if e.relation in _PROGRESSION_THEORY_RELS}

    def _core_id(deg) -> str:
        return f"hn:triad:{tonic}:{mode}:{deg}"

    nodes: List[GraphSceneNode] = []
    edges: List[GraphSceneEdge] = []
    occurrences: List[SceneOccurrence] = []

    key_id = f"voice:key:{sid}"
    nodes.append(GraphSceneNode(
        id=key_id, label=key_label, entity_type="key", entity_role="anchor", semantic_level="key",
        key_context=key_label, visual_class="slate", x=0.0, y=-300.0, radius=24.0,
        explanation=f"The key context: {key_label}."))

    # voice-lane anchors (compact lanes on the left) + optional function lanes for SATB
    voices0 = _extract_voices(m0, poly)
    voice_names = [nm for nm, _ in voices0]
    lane_ids: Dict[str, str] = {}
    vlanes = voice_names
    for j, vn in enumerate(vlanes):
        y = -120.0 + (240.0 * (j / (len(vlanes) - 1)) if len(vlanes) > 1 else 0.0)
        vid = f"voice:lane:{vn}"
        lane_ids[vn] = vid
        nodes.append(GraphSceneNode(
            id=vid, label=vn, entity_type="function", entity_role="family", semantic_level="voicing",
            visual_class="rose", sublabel="voice", x=-360.0, y=y, radius=17.0,
            explanation=f"The {vn} voice lane."))

    ids = [f"voice:{sid}:{i}" for i in range(n)]
    per: List[Dict] = []
    for i, m in enumerate(measures):
        ann = m.annotation
        vs = _extract_voices(m, poly)
        broad = BROAD_FUNCTION.get(ann.function_label, "tonic")
        etype = "diminished" if str(ann.quality or "").startswith("dim") else "triad"
        x = -240.0 + (480.0 * (i / (n - 1)) if n > 1 else 0.0)
        y = (_FUNC_BAND.get(broad, 0.0) if not poly else 0.0)
        voice_pitches = " ".join(f"{nm[0]}:{getattr(nt, 'step', '')}{getattr(nt, 'octave', '')}"
                                 for nm, nt in vs)
        deg = getattr(getattr(m, "underlying", None), "degree_index", None)
        ref = (_resolve_triad_ref(atlas, tonic, mode, deg) if deg is not None else None)
        label = ann.chord_symbol or ann.roman or "?"
        nodes.append(GraphSceneNode(
            id=ids[i], label=label, entity_type=etype, sublabel=(ann.roman or ""),
            semantic_level="chord", entity_role="instance", key_context=key_label,
            roman=(ann.roman or ""), chord_symbol=(ann.chord_symbol or ""),
            chord_tones=tuple(ann.chord_tones or ()), quality=(ann.quality or ""),
            degree_index=deg, visual_class=("purple" if etype == "diminished" else "teal"),
            x=x, y=y, radius=20.0, canonical_refs=((ref,) if ref else ()),
            data={"key": key_label, "roman": ann.roman, "voices": voice_pitches,
                  "implied": poly, "globalIndex": i},
            explanation=(f"Slice {i + 1}: {label}"
                         + (f" implied by {voice_pitches}" if poly else f" ({ann.roman})"))))
        # faint membership edge marker -> each of its voice lanes
        for nm, _ in vs:
            if nm in lane_ids:
                edges.append(GraphSceneEdge(
                    id=f"voice:mem:{i}:{nm}", source=ids[i], target=lane_ids[nm],
                    relation="belongs_to_key", layer="context", directed=False,
                    explanation=f"{label} sounds in the {nm} voice.", visual_class="membership"))
        per.append({"ann": ann, "voices": vs, "etype": etype, "deg": deg, "broad": broad})

    for i in range(n):
        ann = per[i]["ann"]
        rel = None
        common = 0
        lt = False
        moves: List[str] = []
        vexpl = ""
        if i < n - 1:
            nann = per[i + 1]["ann"]
            if not poly and per[i]["deg"] is not None and per[i + 1]["deg"] is not None:
                rel = core_rel.get((_core_id(per[i]["deg"]), _core_id(per[i + 1]["deg"])))
            common = len(set(ann.chord_tones or ()) & set(nann.chord_tones or ()))
            moves, lt = _voice_motion(per[i]["voices"], per[i + 1]["voices"], tonic_pc, mode)
            vexpl = _voice_edge_expl(ann, nann, moves, common, lt)
            edges.append(GraphSceneEdge(
                id=f"voice:seq:{i}", source=ids[i], target=ids[i + 1],
                relation=("drill_next"), layer="sequence", directed=True,
                explanation=(f"{ann.roman or ann.chord_symbol} → {nann.roman or nann.chord_symbol}"),
                visual_class="overlay-drill"))
            edges.append(GraphSceneEdge(
                id=f"voice:vl:{i}", source=ids[i], target=ids[i + 1],
                relation="voice_leads_to", layer="voice_leading", directed=True,
                explanation=vexpl, visual_class="voicing",
                data={"voiceMotion": moves, "commonTones": common, "leadingToneResolves": lt}))
            if rel:
                edges.append(GraphSceneEdge(
                    id=f"voice:th:{i}", source=ids[i], target=ids[i + 1], relation=rel,
                    layer="theory", directed=True,
                    explanation=f"{ann.roman} {rel.replace('_', ' ')} {nann.roman}",
                    visual_class=_THEORY_VC.get(rel, "resolve")))
        ctx = (key_id,) + tuple(lane_ids[nm] for nm, _ in per[i]["voices"] if nm in lane_ids)
        occurrences.append(SceneOccurrence(
            occurrence_id=occurrence_id(sid, 0, i, i), sequence_index=i, node_id=ids[i],
            entity_type=per[i]["etype"], mapping_status="exact", group_index=0, index_in_group=i,
            primary_node_id=ids[i], context_node_ids=ctx, roman=(ann.roman or ""),
            chord_symbol=(ann.chord_symbol or ""), key_context=key_label, quality=(ann.quality or ""),
            mapping_reason=(f"{'implied ' if poly else ''}chord {ann.chord_symbol or ann.roman} "
                            f"in {key_label}"),
            next_sequence_relation=("drill_next" if i < n - 1 else None),
            next_theory_relation=rel,
            next_relation_status=("exact" if rel else ("sequence_only" if i < n - 1 else None)),
            next_is_group_boundary=False, next_explanation=vexpl,
            detail={"keyContext": key_label, "roman": ann.roman, "chordSymbol": ann.chord_symbol,
                    "chordTones": list(ann.chord_tones or ()), "quality": ann.quality,
                    "broadFunction": per[i]["broad"], "functionLabel": ann.function_label,
                    "voices": per[i]["voices"] and " ".join(
                        f"{nm}:{getattr(nt, 'step', '')}{getattr(nt, 'octave', '')}"
                        for nm, nt in per[i]["voices"]),
                    "whyBelongs": (f"an implied chord from {len(per[i]['voices'])} voices"
                                   if poly else f"a {per[i]['broad']}-function chord"),
                    "relationToNext": vexpl, "voiceMotion": moves, "commonTones": common,
                    "leadingToneResolves": lt,
                    "edgeType": "voice leading", "globalIndex": i}))

    title = getattr(lab_spec, "title", None) or scene_type
    subtitle = (f"{key_label} · {' – '.join(m.annotation.roman or '?' for m in measures)}"
                + ("  ·  implied harmony (2 voices)" if poly else "  ·  SATB voice leading"))
    scene = GraphScene(
        scene_id=(scene_id or f"scene:{scene_type}:{sid}"), scene_type=scene_type, title=title,
        subtitle=subtitle, source_kind=source_kind, source_id=sid,
        pedagogical_goal=SCENE_GOAL.get(scene_type, ""),
        semantic_scope=("progression" if poly else "voicing"),
        key_context=key_label, mode=mode, nodes=nodes, edges=edges, paths=[],
        occurrence_map=occurrences, layer_definitions=_layer_defs(edges, scene_type),
        supported_actions=[], warnings=list(extra_warnings or []),
        metadata={"concept": lab_spec.concept, "voices": voice_names, "poly": poly},
        generator_id=scene_type)
    scene.validate()
    return scene


def build_polyphonic_scene(lab_spec, *, source_kind: str = "lab", source_id: Optional[str] = None,
                           scene_id: Optional[str] = None,
                           extra_warnings: Optional[List[str]] = None) -> GraphScene:
    """Scene I: ordered implied-chord slices with two compact voice lanes (plan section 5.I)."""
    return build_voice_leading_scene(
        lab_spec, source_kind=source_kind, source_id=source_id, scene_id=scene_id,
        extra_warnings=extra_warnings, poly=True)


# --------------------------------------------------------------------------------------------- #
# J. score_harmonic_path -- a curated real-score analysis, generated FROM the score (5.J)
# --------------------------------------------------------------------------------------------- #

def build_score_scene(result, *, source_kind: str = "score", source_id: Optional[str] = None,
                      scene_id: Optional[str] = None,
                      extra_warnings: Optional[List[str]] = None) -> GraphScene:
    """Scene J: a curated :class:`ScoreAnalysisResult` as a bounded score path (plan section 5.J).

    Generated from the SCORE ITSELF -- each analysed slice becomes an ordered marker (its own
    ``score_slice`` node), grouped by key area, with the curator's honesty preserved: a chromatic
    chord whose triad merely coincides with a diatonic one is an honest ``unsupported`` marker, not
    forced onto a diatonic node.  Group boundaries fall at real key changes; no theory motion is
    asserted between slices.  The Score Soul Graph mandala stays the primary score-specific view;
    this is the network-pane counterpart.  Score content is NEVER produced by the ordinary drill
    router -- only by an explicit score source."""
    slices = sorted(getattr(result, "slices", []) or [], key=lambda s: s.measure)
    sid = source_id or getattr(result, "score_id", "score")
    if not slices:
        return build_unsupported(source_kind="score", source_id=sid,
                                 reason="the score analysis has no slices to draw")
    n = len(slices)
    half = max(300.0, n * 26.0)          # widen the row so a long score's slices don't overlap
    ids = [f"score:{sid}:{i}" for i in range(n)]
    nodes: List[GraphSceneNode] = []
    edges: List[GraphSceneEdge] = []
    occurrences: List[SceneOccurrence] = []
    warnings: List[str] = list(extra_warnings or [])

    key_anchor: Dict[str, str] = {}
    per: List[Dict] = []
    prev_key = object()
    group_index = -1
    index_in_group = 0
    for i, sl in enumerate(slices):
        key = sl.key or ""
        if key != prev_key:
            group_index += 1
            index_in_group = 0
            prev_key = key
            if key and key not in key_anchor:
                kid = f"score:key:{group_index}:{sid}"
                key_anchor[key] = kid
                nodes.append(GraphSceneNode(
                    id=kid, label=key, entity_type="key", entity_role="anchor",
                    semantic_level="key", key_context=key, visual_class="slate",
                    x=-360.0, y=-260.0 + 64.0 * group_index, radius=20.0,
                    explanation=f"Key area: {key}."))
        else:
            index_in_group += 1
        diatonic = ((not getattr(sl, "is_chromatic", False))
                    and bool(getattr(sl, "base_roman", None)) and bool(key))
        status = "exact" if diatonic else "unsupported"
        x = -half + (2 * half * (i / (n - 1)) if n > 1 else 0.0)
        label = sl.chord_symbol or sl.roman or "?"
        nodes.append(GraphSceneNode(
            id=ids[i], label=label, entity_type="score_slice", sublabel=(sl.roman or ""),
            semantic_level="chord", entity_role="instance", key_context=key, roman=(sl.roman or ""),
            chord_symbol=(sl.chord_symbol or ""),
            chord_tones=tuple(getattr(sl, "chord_tones", ()) or ()),
            visual_class=("teal" if diatonic else "rose"), x=x, y=0.0, radius=18.0,
            canonical_refs=tuple(getattr(sl, "atlas_refs", ()) or ()),
            data={"measure": sl.measure, "key": key, "roman": sl.roman,
                  "chromatic": not diatonic, "globalIndex": i},
            explanation=(f"m{sl.measure}: {label}"
                         + ("" if diatonic else " — chromatic (no diatonic node)"))))
        if key in key_anchor:
            edges.append(GraphSceneEdge(
                id=f"score:ctx:{i}", source=ids[i], target=key_anchor[key],
                relation="belongs_to_key", layer="context", directed=False,
                explanation=f"{label} is in {key}.", visual_class="membership"))
        if not diatonic:
            warnings.append(f"m{sl.measure}: {label} is chromatic (shown as an honest marker)")
        per.append({"sl": sl, "status": status, "group": group_index, "ig": index_in_group})

    for i in range(n):
        boundary = i < n - 1 and per[i]["group"] != per[i + 1]["group"]
        if i < n - 1:
            edges.append(GraphSceneEdge(
                id=f"score:seq:{i}", source=ids[i], target=ids[i + 1], relation="drill_next",
                layer="sequence", directed=True,
                explanation=("key change (modulation in the score)" if boundary
                             else "the next chord in the score"), visual_class="overlay-drill"))
        sl = per[i]["sl"]
        kctx = key_anchor.get(sl.key or "")
        occurrences.append(SceneOccurrence(
            occurrence_id=occurrence_id(sid, per[i]["group"], per[i]["ig"], i), sequence_index=i,
            node_id=ids[i], entity_type="score_slice", mapping_status=per[i]["status"],
            group_index=per[i]["group"], index_in_group=per[i]["ig"],
            primary_node_id=(ids[i] if per[i]["status"] == "exact" else None),
            context_node_ids=((kctx,) if kctx else ()), roman=(sl.roman or ""),
            chord_symbol=(sl.chord_symbol or ""), key_context=(sl.key or ""),
            mapping_reason=("diatonic slice" if per[i]["status"] == "exact"
                            else "chromatic slice (no diatonic node) — honest marker"),
            next_sequence_relation=("drill_next" if i < n - 1 else None), next_theory_relation=None,
            next_relation_status=("sequence_only" if i < n - 1 else None),
            next_is_group_boundary=boundary,
            next_explanation=("key change (modulation)" if boundary
                              else ("the next chord in the score" if i < n - 1 else "")),
            detail={"measure": sl.measure, "keyContext": sl.key, "roman": sl.roman,
                    "chordSymbol": sl.chord_symbol, "chromatic": per[i]["status"] != "exact",
                    "edgeType": "score order", "globalIndex": i}))

    title = getattr(result, "title", None) or sid
    composer = getattr(result, "composer", "") or ""
    return _finalise(GraphScene(
        scene_id=(scene_id or f"scene:score_harmonic_path:{sid}"),
        scene_type="score_harmonic_path", title=title,
        subtitle=(f"{composer} · {n} chords".strip(" ·")), source_kind="score", source_id=sid,
        pedagogical_goal=SCENE_GOAL["score_harmonic_path"], semantic_scope="score",
        key_context=None, mode=None, nodes=nodes, edges=edges, paths=[],
        occurrence_map=occurrences, layer_definitions=_layer_defs(edges, "score_harmonic_path"),
        supported_actions=[], warnings=warnings,
        metadata={"scoreId": sid, "composer": composer, "measures": n},
        generator_id="score_harmonic_path"))


def _finalise(scene: GraphScene) -> GraphScene:
    scene.validate()
    return scene


def build_inversion_scene(lab_spec, *, source_kind: str = "lab", source_id: Optional[str] = None,
                          scene_id: Optional[str] = None,
                          extra_warnings: Optional[List[str]] = None) -> GraphScene:
    """Build the inversion-space scene (G) for a Lab ``inversion`` experiment."""
    params = lab_spec.parameters or {}
    key = getattr(lab_spec, "key", None) or params.get("key", "C major")
    mode = lab_spec.mode
    degree = params.get("degree") or params.get("roman") or ("I" if mode == "major" else "i")
    ctx = NetworkBuildContext(key=_tonic_of(key), mode=mode, degree=degree)
    network = build_network(get_template("inversion_space_network_v1"), context=ctx)
    projection = project_lab_experiment(lab_spec, network)
    sid = source_id or lab_spec.experiment_id
    return assemble_scene(
        scene_type="inversion_space", network=network, projection=projection,
        scene_id=(scene_id or f"scene:inversion_space:{sid}"), title=lab_spec.title,
        subtitle=f"{key} — inversions", source_kind=source_kind, source_id=sid,
        pedagogical_goal=SCENE_GOAL["inversion_space"], semantic_scope="voicing",
        key_context=key, mode=mode, generator_id="inversion_space_network_v1",
        extra_warnings=extra_warnings, metadata={"concept": "inversion"})


def build_legacy_scene(*, source_kind: str = "explore", source_id: str = "explore",
                       scene_id: Optional[str] = None, title: str = "Harmonic network (Explore)",
                       extra_warnings: Optional[List[str]] = None) -> GraphScene:
    """Build the legacy key-relation scene (A) -- Explore mode / suitable relation topics.

    No active drill: the scene shows the fifths / relative / V7->I / vii°->I topology with an empty
    occurrence map.  When an exercise genuinely lives in this ontology the caller may project it.
    """
    network = build_network(get_template("dominant_diminished_relative_network_v1"))
    return assemble_scene(
        scene_type="legacy_key_relation", network=network, projection=None,
        scene_id=(scene_id or f"scene:legacy_key_relation:{source_id}"), title=title,
        subtitle="Whole keys, relative minors, dominant sevenths and leading-tone diminished triads",
        source_kind=source_kind, source_id=source_id,
        pedagogical_goal=SCENE_GOAL["legacy_key_relation"], semantic_scope="relations",
        key_context=None, mode=None, generator_id="dominant_diminished_relative_network_v1",
        extra_warnings=extra_warnings)


def build_unsupported(*, source_kind: str, source_id: str, reason: str,
                      title: str = "No harmonic graph for this exercise",
                      scene_id: Optional[str] = None) -> GraphScene:
    """The honest fail-closed scene."""
    return unsupported_scene(
        scene_id=(scene_id or f"scene:unsupported:{source_id}"), title=title,
        source_kind=source_kind, source_id=source_id, reason=reason)


__all__ = [
    "SCENE_TEMPLATE", "SCENE_SCOPE", "SCENE_GOAL", "RELATION_TO_LAYER",
    "context_from_spec", "assemble_scene",
    "build_exercise_scene", "build_functional_progression_scene", "progression_group_map",
    "build_quality_class_scene", "build_cadence_scene",
    "build_voice_leading_scene", "build_polyphonic_scene", "build_score_scene",
    "build_inversion_scene", "build_legacy_scene", "build_unsupported",
]
