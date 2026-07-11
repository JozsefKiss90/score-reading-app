"""Drill -> Graph projection: compile a running exercise onto the canonical network.

This is the pure engine behind *Drill -> Graph* (plan sections 9, 15). Given a
:class:`~harmony.exercise_spec.HarmonyExerciseSpec` (or a compiled Lab experiment, section 9.2)
and a built :class:`~harmony.harmonic_network.HarmonicNetwork`, it produces a deterministic
:class:`~harmony.harmonic_flow.DrillGraphProjection`:

    * every drill chord becomes a visible occurrence -- an exact canonical node when the active
      template has one, otherwise an honest overlay proxy anchored to its key context;
    * ``full_key`` / ``horizontal_degree`` / ``quality`` drills get *sequence-only* overlays
      (enumerate/transpose), never asserted harmonic-resolution edges;
    * ``function`` drills additionally get canonical theory edges where -- and only where -- the
      network independently contains one, and never across a transposition-group boundary.

No Qt / JS / MusicXML / file I/O. Theory is never re-encoded: chords come from
``compile_exercise``; atlas refs and enharmonic resolution reuse the existing helpers.
"""

from __future__ import annotations

import itertools
from typing import Dict, List, Optional, Tuple

from harmony.exercise_spec import (
    HarmonyExerciseSpec,
    MAX_CHORDS_PER_SPEC,
    compile_exercise,
)
from harmony.harmonic_flow import (
    DrillGraphProjection,
    HarmonicStep,
    HarmonicTransition,
    ProjectionEdge,
    ProjectionNode,
    default_group_for_drill,
    default_sequence_semantics_for_drill,
    is_proxy_node_id,
    occurrence_id,
    proxy_triad_id,
    proxy_voicing_id,
    sequence_relation_for_drill,
    transition_id,
)
from harmony.harmonic_network import (
    HarmonicNetwork,
    _present,
    _resolve_scale_ref,
    _resolve_triad_ref,
    _spoke_xy,
)
from harmony.atlas import (
    build_atlas,
    degree_id,
    function_id,
    layer_id,
    quality_id,
)
from theory.diatonic_harmony import note_pc


# Local-orbit radius for overlay proxy nodes placed around their key anchor (plan section 18).
PROXY_ORBIT_RADIUS = 66.0

# Canonical relations that count as genuine harmonic *motion* (eligible to become a theory edge on
# a transition). Key-relations (fifth_relation, relative_minor_of) and equivalences
# (same_pitch_class, same_function, shares_scale_with) are deliberately excluded (plan section 4).
HARMONIC_MOTION_RELATIONS = frozenset({
    "resolves_to", "prepares", "prolongs", "leading_tone_to", "dominant_of", "substitutes_for",
})

# Overlay edge visual classes by sequence relation (mirrored by CSS .edge.edge--overlay-*).
_OVERLAY_VISUAL_CLASS = {
    "drill_next": "overlay-drill",
    "transpose_next": "overlay-transpose",
    "enumerate_next": "overlay-enumerate",
    "voicing_next": "overlay-voicing",
}


# --------------------------------------------------------------------------------------------- #
# Network index (built once per projection; never mutates the network)
# --------------------------------------------------------------------------------------------- #

class NetworkIndex:
    """Cheap lookup structures over a built :class:`HarmonicNetwork`.

    Tolerant of templates that predate the Phase-4 semantic fields (``semantic_level`` /
    ``canonical_ref``) -- everything is read with ``getattr(..., default)``.
    """

    def __init__(self, network: HarmonicNetwork):
        self.network = network
        self.by_id: Dict[str, object] = {}
        self.key_by_pc: Dict[Tuple[int, str], object] = {}     # (pc, mode) -> key node
        self.dim_by_pc: Dict[int, object] = {}
        self.dom7_by_pc: Dict[int, object] = {}
        self.triad_by_ref: Dict[str, object] = {}              # atlas triad ref -> exact node
        self.function_by_key: Dict[Tuple[str, str], object] = {}  # (mode, function_label) -> node
        self._edge_by_pair: Dict[Tuple[str, str], List[object]] = {}

        for n in network.nodes:
            self.by_id[n.id] = n
            kind = n.kind
            level = getattr(n, "semantic_level", "") or ""
            pc = getattr(n, "pitch_class", None)

            # key anchors -- legacy (major_key/minor_key) and core (key_center / semantic key)
            if kind in ("major_key", "key_center") or level == "key":
                if pc is not None and kind != "minor_key":
                    self.key_by_pc.setdefault((pc, "major"), n)
            if kind in ("minor_key", "key_center") or level == "key":
                if pc is not None and kind != "major_key":
                    self.key_by_pc.setdefault((pc, "natural_minor"), n)

            if kind == "diminished_triad" and pc is not None:
                self.dim_by_pc.setdefault(pc, n)
            if kind == "dominant_seventh" and pc is not None:
                self.dom7_by_pc.setdefault(pc, n)

            # exact diatonic-triad nodes (core template) keyed by their atlas triad ref.
            # Restricted to the dedicated triad kind: legacy key/dom7/dim nodes also carry
            # triad atlas_refs, and indexing those would collapse a chord onto its key node.
            if kind == "diatonic_triad":
                ref = getattr(n, "canonical_ref", "") or ""
                if ref.startswith("triad:"):
                    self.triad_by_ref.setdefault(ref, n)
                for aref in getattr(n, "atlas_refs", []) or []:
                    if isinstance(aref, str) and aref.startswith("triad:"):
                        self.triad_by_ref.setdefault(aref, n)

            if kind == "function_family":
                data = getattr(n, "data", {}) or {}
                fmode = data.get("mode")
                flabel = data.get("functionLabel") or data.get("function_label")
                if fmode and flabel:
                    self.function_by_key.setdefault((fmode, flabel), n)

        for e in network.edges:
            self._edge_by_pair.setdefault((e.source, e.target), []).append(e)

    def key_anchor(self, tonic: str, mode: str):
        return self.key_by_pc.get((note_pc(tonic), mode))

    def edges_between(self, source_id: str, target_id: str) -> List[object]:
        return self._edge_by_pair.get((source_id, target_id), [])


# --------------------------------------------------------------------------------------------- #
# Mapping resolution (plan section 8: exact / contextual / approximate honesty)
# --------------------------------------------------------------------------------------------- #

class _Resolution:
    __slots__ = ("node_id", "status", "mapping_type", "reason", "is_proxy",
                 "proxy_label", "proxy_ref", "degree_index")

    def __init__(self, node_id, status, mapping_type, reason, *, is_proxy=False,
                 proxy_label="", proxy_ref=None, degree_index=None):
        self.node_id = node_id
        self.status = status
        self.mapping_type = mapping_type
        self.reason = reason
        self.is_proxy = is_proxy
        self.proxy_label = proxy_label
        self.proxy_ref = proxy_ref
        self.degree_index = degree_index


def _tonic_of(key: str) -> str:
    return key.split()[0] if key else ""


def _resolve_chord(triad, index: NetworkIndex, atlas) -> _Resolution:
    """Map one compiled ``DiatonicTriad`` onto a canonical node or an honest proxy."""
    tonic = _tonic_of(triad.key)
    mode = triad.mode
    degree = triad.degree_index
    root_pc = note_pc(triad.root)

    atlas_triad_ref = _resolve_triad_ref(atlas, tonic, mode, degree)

    # 1. exact diatonic-triad node (core template): match by atlas triad ref
    if atlas_triad_ref and atlas_triad_ref in index.triad_by_ref:
        node = index.triad_by_ref[atlas_triad_ref]
        return _Resolution(node.id, "exact", "chord_instance",
                           f"exact diatonic triad node for {triad.chord_symbol} "
                           f"({triad.roman} in {triad.key})")

    # 2. exact diminished node (legacy): a real vii-degree diminished chord
    if triad.chord_quality == "diminished" and root_pc in index.dim_by_pc:
        node = index.dim_by_pc[root_pc]
        return _Resolution(node.id, "exact", "chord_instance",
                           f"exact diminished node for {triad.chord_symbol}")

    # 3. approximate dominant-family: the genuine major V triad shown on its V7 node (never
    #    exact). Gated on the dominant *degree* (index 4) + major quality, so the natural-minor
    #    subtonic VII (also labelled function 'dominant' by the engine) is NOT mis-approximated.
    if (triad.degree_index == 4 and triad.chord_quality == "major"
            and root_pc in index.dom7_by_pc):
        node = index.dom7_by_pc[root_pc]
        return _Resolution(node.id, "approximate", "chord_instance",
                           f"{triad.chord_symbol} triad shown on the "
                           f"{node.spelling}7 node — the V triad approximates the "
                           f"dominant seventh")

    # 4. contextual proxy: exact chord known via key/Atlas context, absent from active template
    return _Resolution(
        proxy_triad_id(tonic, mode, degree), "contextual", "chord_instance",
        f"{triad.chord_symbol} ({triad.roman}) has no exact node in this template; "
        f"shown as an overlay anchored to {triad.key}",
        is_proxy=True, proxy_label=triad.chord_symbol, proxy_ref=atlas_triad_ref,
        degree_index=degree,
    )


def _atlas_refs_for(triad, atlas) -> Tuple[str, ...]:
    """Deduped Atlas node ids a chord highlights (enharmonic-tolerant, existence-checked)."""
    tonic = _tonic_of(triad.key)
    refs: List[str] = []
    for r in (
        _resolve_scale_ref(atlas, tonic, triad.mode),
        _resolve_triad_ref(atlas, tonic, triad.mode, triad.degree_index),
        _present(atlas, degree_id(triad.mode, triad.roman)),
        _present(atlas, quality_id(triad.chord_quality)),
        _present(atlas, function_id(triad.mode, triad.function_label)),
        _present(atlas, layer_id(triad.interval_layer)),
    ):
        if r and r not in refs:
            refs.append(r)
    return tuple(refs)


# --------------------------------------------------------------------------------------------- #
# Theory-relation resolver (plan section 9.1)
# --------------------------------------------------------------------------------------------- #

def resolve_theory_relation(prev_step: HarmonicStep, next_step: HarmonicStep,
                            index: NetworkIndex) -> Tuple[Optional[str], Optional[str], str]:
    """Return ``(theory_relation, canonical_edge_id, relation_status)`` for an ordered pair.

    Precedence (section 9.1): (1) an exact canonical harmonic-motion edge between the two steps'
    canonical nodes; otherwise ``None``. Template-path / cadence-rule resolution is layered on by
    ``network_launch`` for path launches; this base resolver does not invent relations.
    """
    a = prev_step.primary_network_node
    b = next_step.primary_network_node
    if not a or not b or is_proxy_node_id(a) or is_proxy_node_id(b):
        return None, None, "sequence_only"
    for e in index.edges_between(a, b):
        if e.relation in HARMONIC_MOTION_RELATIONS:
            return e.relation, e.id, "exact"
    return None, None, "sequence_only"


# --------------------------------------------------------------------------------------------- #
# Public entry: project a HarmonyExerciseSpec
# --------------------------------------------------------------------------------------------- #

def project_harmony_exercise(
    spec: HarmonyExerciseSpec,
    network: HarmonicNetwork,
    *,
    semantic_override: Optional[Dict] = None,
) -> DrillGraphProjection:
    """Compile ``spec`` against ``network`` into a deterministic :class:`DrillGraphProjection`.

    ``semantic_override`` may carry ``thematic_group`` (when the exercise was generated from a
    graph node/edge/path action, section 9 step 3) and a ``title`` override.
    """
    compiled = compile_exercise(spec)          # also (re)validates + canonicalises mode
    atlas = build_atlas()
    index = NetworkIndex(network)

    family = spec.drill
    override = semantic_override or {}
    semantic_group = override.get("thematic_group") or default_group_for_drill(family)
    sequence_semantics = default_sequence_semantics_for_drill(family)
    title = override.get("title") or spec.title
    source_id = spec.exercise_id

    steps: List[HarmonicStep] = []
    proxies: Dict[str, ProjectionNode] = {}
    anchor_ids: List[str] = []
    constellation: List[str] = []
    warnings: List[str] = []

    if len(compiled.chords) > MAX_CHORDS_PER_SPEC:
        warnings.append(
            f"exercise compiles to {len(compiled.chords)} chords "
            f"(> readability cap {MAX_CHORDS_PER_SPEC})"
        )

    def _remember(node_id: Optional[str]):
        if node_id and node_id not in constellation:
            constellation.append(node_id)

    # --- per group (run-length over CompiledChord.group) ------------------------------------- #
    group_index = -1
    for group_label, group_iter in itertools.groupby(compiled.chords, key=lambda c: c.group):
        group_index += 1
        group_chords = list(group_iter)
        for index_in_group, chord in enumerate(group_chords):
            triad = chord.triad
            tonic = _tonic_of(triad.key)
            seq = chord.index

            res = _resolve_chord(triad, index, atlas)
            atlas_refs = _atlas_refs_for(triad, atlas)

            # key anchor / context
            anchor = index.key_anchor(tonic, triad.mode)
            context_nodes: List[str] = []
            if anchor is not None:
                if anchor.id not in anchor_ids:
                    anchor_ids.append(anchor.id)
                context_nodes.append(anchor.id)
                _remember(anchor.id)

            primary = None if res.is_proxy else res.node_id
            visual = res.node_id
            _remember(res.node_id)

            if res.is_proxy:
                _ensure_proxy(proxies, res, triad, anchor, index)

            steps.append(HarmonicStep(
                occurrence_id=occurrence_id(source_id, group_index, index_in_group, seq),
                sequence_index=seq,
                group_index=group_index,
                index_in_group=index_in_group,
                source_kind="harmony_exercise",
                source_id=source_id,
                drill_family=family,
                key_context=triad.key,
                tonic=tonic,
                mode=triad.mode,
                roman=triad.roman,
                degree_index=triad.degree_index,
                chord_symbol=triad.chord_symbol,
                root=triad.root,
                quality=triad.chord_quality,
                function_label=triad.function_label,
                interval_layer=triad.interval_layer,
                pitch_classes=tuple(triad.pitch_classes),
                chord_tones=tuple(triad.pitches),
                semantic_group=semantic_group,
                sequence_semantics=sequence_semantics,
                atlas_refs=atlas_refs,
                primary_network_node=primary,
                context_network_nodes=tuple(context_nodes),
                visual_node_id=visual,
                mapping_type=res.mapping_type,
                mapping_status=res.status,
                mapping_reason=res.reason,
            ))

            if res.status == "approximate":
                warnings.append(f"{triad.chord_symbol}: {res.reason}")

    transitions, proj_edges = _build_transitions(
        steps, family, sequence_semantics, index
    )

    projection = DrillGraphProjection(
        projection_id=f"proj:{source_id}",
        template_id=network.template.template_id,
        source_kind="harmony_exercise",
        source_id=source_id,
        title=title,
        drill_family=family,
        semantic_group=semantic_group,
        sequence_semantics=sequence_semantics,
        anchor_node_ids=anchor_ids,
        constellation_node_ids=constellation,
        steps=steps,
        transitions=transitions,
        projection_nodes=list(proxies.values()),
        projection_edges=proj_edges,
        warnings=warnings,
        metadata={
            "drill": family,
            "render": spec.render,
            "keyContext": override.get("key_context"),
        },
    )
    projection.validate()
    return projection


def _ensure_proxy(proxies: Dict[str, ProjectionNode], res: _Resolution, triad,
                  anchor, index: NetworkIndex) -> None:
    """Create (once) an overlay proxy node placed on a small local orbit around its anchor."""
    if res.node_id in proxies:
        return
    ax = getattr(anchor, "x", 0.0) if anchor is not None else 0.0
    ay = getattr(anchor, "y", 0.0) if anchor is not None else 0.0
    dx, dy = _spoke_xy(res.degree_index or 0, 7, PROXY_ORBIT_RADIUS, 0.0)
    proxies[res.node_id] = ProjectionNode(
        id=res.node_id,
        label=res.proxy_label or triad.chord_symbol,
        kind="proxy_triad",
        canonical_ref=res.proxy_ref,
        atlas_refs=tuple(a for a in _proxy_atlas_refs(res) if a),
        anchor_node_id=(anchor.id if anchor is not None else None),
        x=ax + dx,
        y=ay + dy,
        visual_class="proxy",
        mapping_status=res.status,
        data={
            "roman": triad.roman,
            "degreeIndex": triad.degree_index,
            "quality": triad.chord_quality,
            "key": triad.key,
        },
    )


def _proxy_atlas_refs(res: _Resolution) -> Tuple[str, ...]:
    return (res.proxy_ref,) if res.proxy_ref else ()


def _build_transitions(steps: List[HarmonicStep], family: str, sequence_semantics: str,
                       index: NetworkIndex) -> Tuple[List[HarmonicTransition], List[ProjectionEdge]]:
    """Sequence overlays between consecutive occurrences + theory edges where supported."""
    transitions: List[HarmonicTransition] = []
    proj_edges: List[ProjectionEdge] = []
    family_relation = sequence_relation_for_drill(family)

    for a, b in zip(steps, steps[1:]):
        boundary = a.group_index != b.group_index
        # cross-group steps are a key change -> transpose_next; within-group -> family relation
        relation = "transpose_next" if boundary else family_relation

        theory_relation = None
        canonical_edge_id = None
        relation_status = "sequence_only"
        if not boundary and sequence_semantics == "harmonic_motion":
            theory_relation, canonical_edge_id, relation_status = resolve_theory_relation(
                a, b, index
            )

        explanation = _transition_explanation(relation, theory_relation, boundary)
        tr = HarmonicTransition(
            id=transition_id(a.occurrence_id, b.occurrence_id, relation),
            from_occurrence=a.occurrence_id,
            to_occurrence=b.occurrence_id,
            sequence_relation=relation,
            theory_relation=theory_relation,
            canonical_edge_id=canonical_edge_id,
            is_group_boundary=boundary,
            relation_status=relation_status,
            explanation=explanation,
        )
        transitions.append(tr)
        proj_edges.append(ProjectionEdge(
            id=f"pe:{tr.id}",
            source=a.visual_node_id,
            target=b.visual_node_id,
            relation=relation,
            canonical_edge_id=canonical_edge_id,
            visual_class=_OVERLAY_VISUAL_CLASS.get(relation, "overlay-drill"),
            explanation=explanation,
        ))
    return transitions, proj_edges


def _transition_explanation(relation: str, theory_relation: Optional[str],
                            boundary: bool) -> str:
    if boundary:
        return "group boundary (key change) — sequence only, not a harmonic motion"
    if theory_relation:
        return f"{relation} (canonical {theory_relation})"
    if relation == "enumerate_next":
        return "pedagogical enumeration — not a harmonic progression"
    if relation == "transpose_next":
        return "same pattern transposed — not a modulation"
    return "next drill item"


# --------------------------------------------------------------------------------------------- #
# Public entry: project a Lab experiment (inversion / voice-leading) -- plan section 9.2
# --------------------------------------------------------------------------------------------- #

def project_lab_experiment(spec, network: HarmonicNetwork) -> DrillGraphProjection:
    """Compile a :class:`~harmony.lab_spec.LabExperimentSpec` onto the network.

    For an ``inversion`` experiment all steps share the same chord anchor and each voicing maps to
    an ``inversion_state`` node (or an honest ``proxy_voicing`` when the active template lacks
    one).  ``bass_pitch_class`` / ``inversion`` / ``figured_bass`` are populated; overlay
    transitions use ``voicing_next`` and light up the canonical ``voice_leads_to`` edge where the
    network has one.  The chord function never changes across states.
    """
    from harmony.lab import compile_lab              # lazy: avoids loading MusicXML at import

    experiment = compile_lab(spec)
    atlas = build_atlas()
    concept = spec.concept
    family = concept
    semantic_group = default_group_for_drill(family)
    sequence_semantics = default_sequence_semantics_for_drill(family)
    source_id = spec.experiment_id

    # index voicing-state nodes by inversion, and find the identity anchor
    state_by_inv: Dict[int, object] = {}
    for n in network.nodes:
        if n.kind == "inversion_state":
            inv = (n.data or {}).get("inversion")
            if inv is not None:
                state_by_inv.setdefault(int(inv), n)
    anchors = [n for n in network.nodes
               if n.kind == "diatonic_triad" and getattr(n, "entity_role", "") == "reference"]
    anchor = anchors[0] if anchors else None
    anchor_ids = [anchor.id] if anchor else []

    edge_lookup = {(e.source, e.target, e.relation): e for e in network.edges}
    steps: List[HarmonicStep] = []
    proxies: Dict[str, ProjectionNode] = {}
    constellation: List[str] = list(anchor_ids)
    warnings: List[str] = []

    for i, measure in enumerate(experiment.measures):
        ann = measure.annotation
        triad = measure.underlying
        inv = ann.inversion if ann.inversion is not None else 0
        tonic = measure.tonic
        mode = measure.mode
        degree_index = (triad.degree_index if triad is not None
                        else ((ann.degree_number or 1) - 1))

        state_node = state_by_inv.get(inv)
        if state_node is not None:
            visual = primary = state_node.id
            status, reason = "exact", f"voicing state (inversion {inv}) of the chord identity"
            if state_node.id not in constellation:
                constellation.append(state_node.id)
        else:
            visual = proxy_voicing_id(tonic, mode, degree_index, inv)
            primary = None
            status = "contextual"
            reason = f"inversion {inv} has no state node in this template; shown as an overlay"
            _ensure_voicing_proxy(proxies, visual, ann, anchor, inv)

        atlas_refs = _atlas_refs_for(triad, atlas) if triad is not None else ()
        steps.append(HarmonicStep(
            occurrence_id=occurrence_id(source_id, 0, i, i),
            sequence_index=i, group_index=0, index_in_group=i,
            source_kind="lab", source_id=source_id, drill_family=family,
            key_context=measure.key_display, tonic=tonic, mode=mode,
            roman=ann.roman or (triad.roman if triad else ""),
            degree_index=degree_index,
            chord_symbol=ann.chord_symbol or (triad.chord_symbol if triad else ""),
            root=ann.root or (triad.root if triad else ""),
            quality=ann.quality or (triad.chord_quality if triad else ""),
            function_label=ann.function_label or (triad.function_label if triad else ""),
            interval_layer=ann.interval_layer or (triad.interval_layer if triad else ""),
            pitch_classes=tuple(triad.pitch_classes) if triad else tuple(measure.target_pitch_classes),
            chord_tones=tuple(ann.chord_tones) if ann.chord_tones else (
                tuple(triad.pitches) if triad else ()),
            semantic_group=semantic_group, sequence_semantics=sequence_semantics,
            atlas_refs=atlas_refs, primary_network_node=primary,
            context_network_nodes=tuple(anchor_ids), visual_node_id=visual,
            mapping_type="voicing_state", mapping_status=status, mapping_reason=reason,
            bass_pitch_class=measure.bass_pitch_class, inversion=inv,
            figured_bass=ann.figured_bass,
        ))

    transitions: List[HarmonicTransition] = []
    proj_edges: List[ProjectionEdge] = []
    for a, b in zip(steps, steps[1:]):
        canonical = edge_lookup.get((a.visual_node_id, b.visual_node_id, "voice_leads_to"))
        theory_relation = "voice_leads_to" if canonical else None
        relation_status = "exact" if canonical else "sequence_only"
        tr = HarmonicTransition(
            id=transition_id(a.occurrence_id, b.occurrence_id, "voicing_next"),
            from_occurrence=a.occurrence_id, to_occurrence=b.occurrence_id,
            sequence_relation="voicing_next", theory_relation=theory_relation,
            canonical_edge_id=(canonical.id if canonical else None),
            is_group_boundary=False, relation_status=relation_status,
            explanation="voice-leading to the next inversion",
        )
        transitions.append(tr)
        proj_edges.append(ProjectionEdge(
            id=f"pe:{tr.id}", source=a.visual_node_id, target=b.visual_node_id,
            relation="voicing_next", canonical_edge_id=(canonical.id if canonical else None),
            visual_class=_OVERLAY_VISUAL_CLASS["voicing_next"],
            explanation="voicing change"))

    projection = DrillGraphProjection(
        projection_id=f"proj:{source_id}", template_id=network.template.template_id,
        source_kind="lab", source_id=source_id, title=spec.title, drill_family=family,
        semantic_group=semantic_group, sequence_semantics=sequence_semantics,
        anchor_node_ids=anchor_ids, constellation_node_ids=constellation,
        steps=steps, transitions=transitions, projection_nodes=list(proxies.values()),
        projection_edges=proj_edges, warnings=warnings,
        metadata={"concept": concept, "render": spec.render},
    )
    projection.validate()
    return projection


def _ensure_voicing_proxy(proxies, node_id, ann, anchor, inv) -> None:
    if node_id in proxies:
        return
    ax = getattr(anchor, "x", 0.0) if anchor is not None else 0.0
    ay = getattr(anchor, "y", 0.0) if anchor is not None else 0.0
    dx, dy = _spoke_xy(inv, 3, PROXY_ORBIT_RADIUS, 0.0)
    label = ann.chord_symbol or ""
    if inv and ann.bass_note:
        label = f"{label}/{ann.bass_note}"
    proxies[node_id] = ProjectionNode(
        id=node_id, label=label, kind="proxy_voicing", canonical_ref=None,
        atlas_refs=(), anchor_node_id=(anchor.id if anchor is not None else None),
        x=ax + dx, y=ay + dy, visual_class="proxy", mapping_status="contextual",
        data={"inversion": inv, "figuredBass": ann.figured_bass, "bassNote": ann.bass_note},
    )


# --------------------------------------------------------------------------------------------- #
# Public entry: project a curated score analysis (plan sections 9 phase 9, 8.4)
# --------------------------------------------------------------------------------------------- #

def harmonic_step_from_score_slice(sl, network: HarmonicNetwork, *, sequence_index: int,
                                   group_index: int, index_in_group: int,
                                   index: Optional[NetworkIndex] = None,
                                   atlas=None) -> Tuple[HarmonicStep, Optional[ProjectionNode]]:
    """Map one :class:`~harmony.score_analysis.ScoreHarmonySlice` onto a :class:`HarmonicStep`.

    Reuses ``score_analysis`` (``canon_mode`` / ``diatonic_triad_match`` / the slice's already
    resolved ``atlas_refs``) rather than forking a second mapper.  The honesty gate is the
    curator's ``base_roman``: a chromatic chord whose triad merely *coincides* with a diatonic one
    (``base_roman=None``) is marked ``unsupported`` and never claims a diatonic node -- automatic
    harmonic certainty is never invented.  Returns ``(step, optional_proxy_node)``.
    """
    from harmony.score_analysis import canon_mode, diatonic_triad_match  # lazy: avoids cycle

    if index is None:
        index = NetworkIndex(network)
    if atlas is None:
        atlas = build_atlas()

    # Parse defensively: a slice may carry an unparseable key/mode from a curated sidecar
    # (e.g. German 'H' for B). Degrade that slice to an honest 'unsupported' marker rather than
    # crashing the whole projection.
    try:
        mode = canon_mode(sl.mode or "major")
    except Exception:
        mode = "major"
    try:
        tonic = sl.key_tonic
    except Exception:
        tonic = ""
    mode_word = "minor" if mode == "natural_minor" else "major"
    key_context = sl.key or (f"{tonic} {mode_word}" if tonic else "")
    anchor = index.key_anchor(tonic, mode) if tonic else None
    context_nodes = [anchor.id] if anchor is not None else []

    # diatonic reading only when the curator supplied a base_roman AND the slice is not chromatic
    diatonic = (not sl.is_chromatic) and bool(sl.base_roman) and bool(sl.key)
    triad = None
    if diatonic:
        try:
            triad = diatonic_triad_match(sl.key, sl.mode, sl.inferred_root,
                                         sl.chord_quality_hint())
        except Exception:
            triad = None

    proxy_node: Optional[ProjectionNode] = None
    if triad is not None:
        res = _resolve_chord(triad, index, atlas)
        primary = None if res.is_proxy else res.node_id
        visual = res.node_id
        status, mapping_type, reason = res.status, res.mapping_type, res.reason
        if res.is_proxy:
            bucket: Dict[str, ProjectionNode] = {}
            _ensure_proxy(bucket, res, triad, anchor, index)
            proxy_node = bucket[res.node_id]
        degree_index = triad.degree_index
        pitch_classes = tuple(triad.pitch_classes)
        chord_tones = tuple(sl.chord_tones) if sl.chord_tones else tuple(triad.pitches)
        quality = triad.chord_quality
        interval_layer = sl.interval_layer or triad.interval_layer
        function_label = sl.function_label or triad.function_label
    else:
        visual = f"overlay:score:{sl.score_id}:{sequence_index}"
        primary = None
        status, mapping_type = "unsupported", "chord_instance"
        reason = (f"{sl.chord_symbol or sl.roman or 'chord'} is not a diatonic triad of "
                  f"{key_context or 'the key'}")
        proxy_node = _score_unsupported_proxy(visual, sl, anchor, sequence_index)
        degree_index = None
        pitch_classes = ()
        chord_tones = tuple(sl.chord_tones)
        quality = sl.chord_quality_hint() or ""
        interval_layer = sl.interval_layer or ""
        function_label = sl.function_label or ""

    conf = "" if sl.confidence >= 1.0 else f" (confidence {sl.confidence:g})"
    step = HarmonicStep(
        occurrence_id=occurrence_id(sl.score_id, group_index, index_in_group, sequence_index),
        sequence_index=sequence_index, group_index=group_index, index_in_group=index_in_group,
        source_kind="score", source_id=sl.score_id, drill_family="score",
        key_context=key_context, tonic=tonic, mode=mode,
        roman=sl.roman or sl.base_roman or "", degree_index=degree_index,
        chord_symbol=sl.chord_symbol or "", root=sl.inferred_root or "",
        quality=quality, function_label=function_label, interval_layer=interval_layer,
        pitch_classes=pitch_classes, chord_tones=chord_tones,
        semantic_group=default_group_for_drill("score"),
        sequence_semantics=default_sequence_semantics_for_drill("score"),
        atlas_refs=tuple(sl.atlas_refs), primary_network_node=primary,
        context_network_nodes=tuple(context_nodes), visual_node_id=visual,
        mapping_type=mapping_type, mapping_status=status,
        mapping_reason=f"[{sl.status}] {reason}{conf}",
    )
    return step, proxy_node


def _score_unsupported_proxy(pid: str, sl, anchor, seq: int) -> ProjectionNode:
    ax = getattr(anchor, "x", 0.0) if anchor is not None else 0.0
    ay = getattr(anchor, "y", 0.0) if anchor is not None else 0.0
    dx, dy = _spoke_xy(seq % 12, 12, PROXY_ORBIT_RADIUS, 0.0)
    return ProjectionNode(
        id=pid, label=(sl.chord_symbol or sl.roman or "?"), kind="occurrence_marker",
        canonical_ref=None, atlas_refs=tuple(sl.atlas_refs),
        anchor_node_id=(anchor.id if anchor is not None else None),
        x=ax + dx, y=ay + dy, visual_class="proxy", mapping_status="unsupported",
        data={"chromatic": True, "roman": sl.roman, "measure": sl.measure,
              "chordSymbol": sl.chord_symbol},
    )


def project_score_analysis(result, network: HarmonicNetwork, *, resolve: bool = True) -> DrillGraphProjection:
    """Project a curated :class:`~harmony.score_analysis.ScoreAnalysisResult` onto the network.

    Slices become ordered occurrences in ``score_time`` semantics; every slice is visible (exact
    canonical node, diatonic proxy, or an honest ``unsupported`` marker for chromatic chords).
    Group boundaries fall at key changes (a real modulation in the piece). No theory edges are
    asserted between slices -- the curated/heuristic status is preserved, not upgraded.
    """
    if resolve:
        try:
            result.resolve_refs()          # idempotent; fills atlas/network refs, never clobbers
        except Exception:
            pass
    atlas = build_atlas()
    index = NetworkIndex(network)

    steps: List[HarmonicStep] = []
    proxies: Dict[str, ProjectionNode] = {}
    anchor_ids: List[str] = []
    constellation: List[str] = []
    warnings: List[str] = []

    slices = sorted(result.slices, key=lambda s: s.measure)
    prev_key = object()
    group_index = -1
    index_in_group = 0
    for seq, sl in enumerate(slices):
        if sl.key != prev_key:
            group_index += 1
            index_in_group = 0
            prev_key = sl.key
        else:
            index_in_group += 1
        step, proxy = harmonic_step_from_score_slice(
            sl, network, sequence_index=seq, group_index=group_index,
            index_in_group=index_in_group, index=index, atlas=atlas)
        steps.append(step)
        if proxy is not None and proxy.id not in proxies:
            proxies[proxy.id] = proxy
        for cid in step.context_network_nodes:
            if cid not in anchor_ids:
                anchor_ids.append(cid)
            if cid not in constellation:
                constellation.append(cid)
        if step.primary_network_node and step.primary_network_node not in constellation:
            constellation.append(step.primary_network_node)
        if step.visual_node_id not in constellation:
            constellation.append(step.visual_node_id)
        if step.mapping_status == "unsupported":
            warnings.append(f"m{sl.measure}: {step.mapping_reason}")

    transitions: List[HarmonicTransition] = []
    proj_edges: List[ProjectionEdge] = []
    for a, b in zip(steps, steps[1:]):
        boundary = a.group_index != b.group_index
        tr = HarmonicTransition(
            id=transition_id(a.occurrence_id, b.occurrence_id, "drill_next"),
            from_occurrence=a.occurrence_id, to_occurrence=b.occurrence_id,
            sequence_relation="drill_next", theory_relation=None, canonical_edge_id=None,
            is_group_boundary=boundary, relation_status="sequence_only",
            explanation=("key change (modulation in the score)" if boundary
                         else "the next chord in the score"))
        transitions.append(tr)
        proj_edges.append(ProjectionEdge(
            id=f"pe:{tr.id}", source=a.visual_node_id, target=b.visual_node_id,
            relation="drill_next", canonical_edge_id=None,
            visual_class=_OVERLAY_VISUAL_CLASS["drill_next"], explanation=tr.explanation))

    projection = DrillGraphProjection(
        projection_id=f"proj:{result.score_id}", template_id=network.template.template_id,
        source_kind="score", source_id=result.score_id,
        title=result.title or result.score_id, drill_family="score",
        semantic_group=default_group_for_drill("score"),
        sequence_semantics=default_sequence_semantics_for_drill("score"),
        anchor_node_ids=anchor_ids, constellation_node_ids=constellation,
        steps=steps, transitions=transitions, projection_nodes=list(proxies.values()),
        projection_edges=proj_edges, warnings=warnings,
        metadata={"scoreId": result.score_id, "composer": result.composer,
                  "measures": result.measure_count})
    projection.validate()
    return projection


__all__ = [
    "NetworkIndex",
    "PROXY_ORBIT_RADIUS",
    "HARMONIC_MOTION_RELATIONS",
    "project_harmony_exercise",
    "project_lab_experiment",
    "project_score_analysis",
    "harmonic_step_from_score_slice",
    "resolve_theory_relation",
]
