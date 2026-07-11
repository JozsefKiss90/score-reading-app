"""Phase 1 contract tests for harmony/harmonic_flow.py.

Covers serialisation round trips, deterministic IDs, and the DrillGraphProjection validation
invariants (duplicate occurrences, non-contiguous indices, invalid transitions, group-boundary
theory edges, mapping-status honesty). Pure/headless -- no Qt, no JS, no I/O.
"""

import unittest

from harmony.harmonic_flow import (
    DrillGraphProjection,
    GraphDrillRequest,
    HarmonicPath,
    HarmonicStep,
    HarmonicTransition,
    LaunchAction,
    ProjectionEdge,
    ProjectionNode,
    ProjectionValidationError,
    PROJECTION_SCHEMA,
    default_group_for_drill,
    default_sequence_semantics_for_drill,
    is_proxy_node_id,
    occurrence_id,
    proxy_triad_id,
    proxy_voicing_id,
    sequence_relation_for_drill,
    transition_id,
)


def _step(seq, group_index=0, index_in_group=0, *, node="hn:triad:C:major:0",
          status="exact", mapping_type="chord_instance", roman="I", visual=None,
          source_id="ex1"):
    visual = visual if visual is not None else node
    return HarmonicStep(
        occurrence_id=occurrence_id(source_id, group_index, index_in_group, seq),
        sequence_index=seq,
        group_index=group_index,
        index_in_group=index_in_group,
        source_kind="harmony_exercise",
        source_id=source_id,
        drill_family="full_key",
        key_context="C major",
        tonic="C",
        mode="major",
        roman=roman,
        degree_index=0,
        chord_symbol="C",
        root="C",
        quality="major",
        function_label="tonic",
        interval_layer="M3+m3",
        pitch_classes=(0, 4, 7),
        chord_tones=("C", "E", "G"),
        semantic_group="tonal_field",
        sequence_semantics="pedagogical_enumeration",
        atlas_refs=("triad:C:major:0",),
        primary_network_node=None if is_proxy_node_id(node) else node,
        context_network_nodes=("hn:major:C",),
        visual_node_id=visual,
        mapping_type=mapping_type,
        mapping_status=status,
        mapping_reason="test",
    )


def _projection(steps, transitions=None, **kw):
    kw.setdefault("projection_id", "proj:test")
    kw.setdefault("template_id", "core_triad_function_network_v1")
    kw.setdefault("source_kind", "harmony_exercise")
    kw.setdefault("source_id", "ex1")
    kw.setdefault("title", "Test")
    kw.setdefault("drill_family", "full_key")
    kw.setdefault("semantic_group", "tonal_field")
    kw.setdefault("sequence_semantics", "pedagogical_enumeration")
    return DrillGraphProjection(steps=list(steps), transitions=list(transitions or []), **kw)


class TestIdHelpers(unittest.TestCase):
    def test_occurrence_id_is_positional_not_node(self):
        a = occurrence_id("ex", 0, 0, 0)
        b = occurrence_id("ex", 0, 3, 3)
        self.assertNotEqual(a, b)
        self.assertEqual(a, "occ:ex:0:0:0")

    def test_proxy_ids(self):
        self.assertEqual(proxy_triad_id("C", "major", 1), "overlay:triad:C:major:1")
        self.assertTrue(is_proxy_node_id(proxy_triad_id("C", "major", 1)))
        self.assertEqual(proxy_voicing_id("C", "major", 0, 1), "overlay:inversion:C:major:0:1")
        self.assertTrue(is_proxy_node_id(proxy_voicing_id("C", "major", 0, 2)))
        self.assertFalse(is_proxy_node_id("hn:triad:C:major:0"))

    def test_transition_id_deterministic(self):
        a = transition_id("occ:ex:0:0:0", "occ:ex:0:1:1", "drill_next")
        b = transition_id("occ:ex:0:0:0", "occ:ex:0:1:1", "drill_next")
        self.assertEqual(a, b)

    def test_drill_family_defaults(self):
        self.assertEqual(default_group_for_drill("full_key"), "tonal_field")
        self.assertEqual(default_sequence_semantics_for_drill("full_key"),
                         "pedagogical_enumeration")
        self.assertEqual(default_group_for_drill("horizontal_degree"), "transposition_orbit")
        self.assertEqual(sequence_relation_for_drill("horizontal_degree"), "transpose_next")
        self.assertEqual(sequence_relation_for_drill("function"), "drill_next")
        self.assertEqual(sequence_relation_for_drill("inversion"), "voicing_next")


class TestRoundTrips(unittest.TestCase):
    def test_step_round_trip(self):
        s = _step(0)
        self.assertEqual(HarmonicStep.from_dict(s.to_dict()), s)

    def test_step_round_trip_with_optionals(self):
        s = HarmonicStep.from_dict(_step(0).to_dict())
        s2 = HarmonicStep(**{**s.__dict__, "bass_pitch_class": 4, "inversion": 1,
                             "figured_bass": "6"})
        self.assertEqual(HarmonicStep.from_dict(s2.to_dict()), s2)

    def test_transition_round_trip(self):
        t = HarmonicTransition(
            id="t1", from_occurrence="occ:ex:0:0:0", to_occurrence="occ:ex:0:1:1",
            sequence_relation="drill_next", theory_relation="resolves_to",
            canonical_edge_id="e1", is_group_boundary=False, relation_status="exact",
            explanation="V resolves to I",
        )
        self.assertEqual(HarmonicTransition.from_dict(t.to_dict()), t)

    def test_projection_node_edge_round_trip(self):
        n = ProjectionNode(
            id=proxy_triad_id("C", "major", 1), label="Dm", kind="proxy_triad",
            canonical_ref="triad:C:major:1", atlas_refs=("triad:C:major:1",),
            anchor_node_id="hn:major:C", x=1.5, y=-2.5, visual_class="proxy",
            mapping_status="contextual", data={"degree": 1},
        )
        self.assertEqual(ProjectionNode.from_dict(n.to_dict()), n)
        e = ProjectionEdge(
            id="pe1", source="a", target="b", relation="enumerate_next",
            canonical_edge_id=None, visual_class="overlay-enumerate", explanation="",
        )
        self.assertEqual(ProjectionEdge.from_dict(e.to_dict()), e)

    def test_projection_round_trip(self):
        proj = _projection([_step(0), _step(1, index_in_group=1, node="hn:triad:C:major:1",
                                            roman="ii")])
        proj.validate()
        back = DrillGraphProjection.from_dict(proj.to_dict())
        self.assertEqual(back.steps, proj.steps)
        self.assertEqual(back.schema, PROJECTION_SCHEMA)
        back.validate()

    def test_request_round_trip(self):
        r = GraphDrillRequest(
            template_id="core", interaction_kind="node",
            selected_node_ids=("hn:major:C",), thematic_group="node_identity",
            key_context="C major", mode="major", options={"play": "tonic"},
        )
        r.validate()
        self.assertEqual(GraphDrillRequest.from_dict(r.to_dict()), r)

    def test_launch_action_round_trip(self):
        a = LaunchAction(
            id="a1", label="Play tonic chord", target="trainer", status="launchable",
            semantic_group="node_identity", interaction_kind="node",
            spec_type="harmony_exercise", spec={"drill": "full_key"}, reason="",
            preview_projection={"schema": PROJECTION_SCHEMA},
        )
        a.validate()
        self.assertEqual(LaunchAction.from_dict(a.to_dict()), a)

    def test_harmonic_path_round_trip(self):
        p = HarmonicPath(
            id="path:ii_V_I:C:major", label="ii-V-I in C major", key_context="C major",
            mode="major", node_ids=("hn:triad:C:major:1", "hn:triad:C:major:4",
                                     "hn:triad:C:major:0"),
            edge_ids=("e1", "e2"), romans=("ii", "V", "I"), cadence_type="authentic",
            semantic_group="functional_path", launch_action_ids=("a1",),
        )
        self.assertEqual(HarmonicPath.from_dict(p.to_dict()), p)


class TestProjectionValidation(unittest.TestCase):
    def test_valid_projection_passes(self):
        _projection([_step(0)]).validate()

    def test_duplicate_occurrence_rejected(self):
        s = _step(0)
        # two steps with the SAME occurrence id but different sequence index slots
        dup = HarmonicStep(**{**s.__dict__, "sequence_index": 1})
        proj = _projection([s, dup])
        with self.assertRaises(ProjectionValidationError):
            proj.validate()

    def test_non_contiguous_indices_rejected(self):
        proj = _projection([_step(0), _step(2, index_in_group=2)])
        with self.assertRaises(ProjectionValidationError):
            proj.validate()

    def test_transition_unknown_occurrence_rejected(self):
        proj = _projection(
            [_step(0)],
            [HarmonicTransition(id="t", from_occurrence="occ:ex:0:0:0",
                                to_occurrence="occ:nope", sequence_relation="enumerate_next",
                                theory_relation=None, canonical_edge_id=None,
                                is_group_boundary=False, relation_status="sequence_only")],
        )
        with self.assertRaises(ProjectionValidationError):
            proj.validate()

    def test_theory_edge_across_group_boundary_rejected(self):
        s0 = _step(0, group_index=0, index_in_group=0)
        s1 = _step(1, group_index=1, index_in_group=0, roman="ii")
        tr = HarmonicTransition(
            id="t", from_occurrence=s0.occurrence_id, to_occurrence=s1.occurrence_id,
            sequence_relation="transpose_next", theory_relation="resolves_to",
            canonical_edge_id=None, is_group_boundary=True, relation_status="inferred",
        )
        with self.assertRaises(ProjectionValidationError):
            _projection([s0, s1], [tr]).validate()

    def test_group_boundary_sequence_only_ok(self):
        s0 = _step(0, group_index=0, index_in_group=0)
        s1 = _step(1, group_index=1, index_in_group=0, roman="ii")
        tr = HarmonicTransition(
            id="t", from_occurrence=s0.occurrence_id, to_occurrence=s1.occurrence_id,
            sequence_relation="transpose_next", theory_relation=None,
            canonical_edge_id=None, is_group_boundary=True, relation_status="sequence_only",
        )
        _projection([s0, s1], [tr]).validate()  # should not raise

    def test_exact_mapping_requires_canonical_node(self):
        # a step declared exact but rendered on a proxy is dishonest -> rejected
        bad = _step(0, node=proxy_triad_id("C", "major", 1), status="exact",
                    visual=proxy_triad_id("C", "major", 1))
        with self.assertRaises(ProjectionValidationError):
            _projection([bad]).validate()

    def test_proxy_step_must_be_non_exact(self):
        proxy = proxy_triad_id("C", "major", 1)
        s = _step(0, node=proxy, status="contextual", visual=proxy,
                  mapping_type="chord_instance")
        # contextual proxy is allowed
        _projection([s]).validate()

    def test_invalid_mapping_status_rejected(self):
        s = _step(0)
        bad = HarmonicStep(**{**s.__dict__, "mapping_status": "sorta"})
        with self.assertRaises(ProjectionValidationError):
            _projection([bad]).validate()

    def test_counts(self):
        proj = _projection([
            _step(0, node="hn:triad:C:major:0"),
            _step(1, index_in_group=1, node=proxy_triad_id("C", "major", 1),
                  status="contextual", visual=proxy_triad_id("C", "major", 1), roman="ii"),
        ])
        proj.validate()
        c = proj.counts()
        self.assertEqual(c["steps"], 2)
        self.assertEqual(c["byMappingStatus"]["exact"], 1)
        self.assertEqual(c["byMappingStatus"]["contextual"], 1)

    def test_lookups(self):
        proj = _projection([_step(0), _step(1, index_in_group=1, roman="ii",
                                            node="hn:triad:C:major:1")])
        self.assertEqual(proj.step_at_index(1).roman, "ii")
        self.assertIsNotNone(proj.step_by_occurrence(proj.steps[0].occurrence_id))
        self.assertIn("hn:triad:C:major:0", proj.canonical_nodes())


class TestReviewRegressions(unittest.TestCase):
    """Regressions for the adversarial-review findings on harmonic_flow.py."""

    def test_theory_edge_under_enumeration_rejected(self):
        # a pedagogical-enumeration projection must never carry a theory relation (plan 4.1)
        s0 = _step(0)
        s1 = _step(1, index_in_group=1, node="hn:triad:C:major:1", roman="ii")
        tr = HarmonicTransition(
            id="t", from_occurrence=s0.occurrence_id, to_occurrence=s1.occurrence_id,
            sequence_relation="enumerate_next", theory_relation="resolves_to",
            canonical_edge_id="e", is_group_boundary=False, relation_status="exact")
        proj = _projection([s0, s1], [tr])  # defaults: sequence_semantics=pedagogical_enumeration
        with self.assertRaises(ProjectionValidationError):
            proj.validate()

    def test_theory_edge_derived_group_boundary_rejected(self):
        # even under harmonic_motion, a theory edge whose steps are in different groups is rejected
        # (derived from group_index, not just the self-reported flag)
        s0 = _step(0, group_index=0)
        s1 = _step(1, group_index=1, roman="ii", node="hn:triad:C:major:1")
        tr = HarmonicTransition(
            id="t", from_occurrence=s0.occurrence_id, to_occurrence=s1.occurrence_id,
            sequence_relation="drill_next", theory_relation="resolves_to",
            canonical_edge_id="e", is_group_boundary=False, relation_status="exact")
        proj = _projection([s0, s1], [tr], drill_family="function",
                           semantic_group="functional_path", sequence_semantics="harmonic_motion")
        with self.assertRaises(ProjectionValidationError):
            proj.validate()

    def test_theory_edge_under_motion_ok(self):
        s0 = _step(0, group_index=0, roman="V", node="hn:triad:C:major:4")
        s1 = _step(1, index_in_group=1, group_index=0, roman="I", node="hn:triad:C:major:0")
        tr = HarmonicTransition(
            id="t", from_occurrence=s0.occurrence_id, to_occurrence=s1.occurrence_id,
            sequence_relation="drill_next", theory_relation="resolves_to",
            canonical_edge_id="e", is_group_boundary=False, relation_status="exact")
        _projection([s0, s1], [tr], drill_family="function", semantic_group="functional_path",
                    sequence_semantics="harmonic_motion").validate()  # must not raise

    def test_proxy_node_round_trips_with_messy_floats(self):
        n = ProjectionNode(
            id=proxy_triad_id("C", "major", 1), label="Dm", kind="proxy_triad",
            canonical_ref="triad:C:major:1", atlas_refs=("triad:C:major:1",),
            anchor_node_id="hn:major:C", x=171.60087784288996, y=-53.13724312,
            visual_class="proxy", mapping_status="contextual", data={"degree": 1})
        self.assertEqual(ProjectionNode.from_dict(n.to_dict()), n)

    def test_frozen_value_objects_are_hashable(self):
        # frozen dataclasses with Dict fields must not crash hash() (dict fields excluded)
        n = ProjectionNode(id="p", label="x", kind="proxy_triad", canonical_ref=None,
                           atlas_refs=(), anchor_node_id=None, x=1.0, y=2.0,
                           visual_class="proxy", mapping_status="contextual", data={"a": 1})
        r = GraphDrillRequest(template_id="t", interaction_kind="node",
                              selected_node_ids=("n",), options={"k": "v"})
        a = LaunchAction(id="a", label="l", target="trainer", status="launchable",
                         semantic_group="node_identity", interaction_kind="node",
                         spec={"drill": "full_key"})
        for obj in (n, r, a):
            hash(obj)                 # must not raise
            self.assertIn(obj, {obj})

    def test_projection_edge_validation(self):
        s = _step(0)
        bad = ProjectionEdge(id="pe", source="ghost", target="ghost",
                             relation="drill_next", canonical_edge_id=None,
                             visual_class="overlay-drill")
        proj = _projection([s])
        proj.projection_edges = [bad]
        with self.assertRaises(ProjectionValidationError):
            proj.validate()

    def test_projection_edge_bad_relation_rejected(self):
        s0 = _step(0)
        s1 = _step(1, index_in_group=1, node="hn:triad:C:major:1", roman="ii")
        bad = ProjectionEdge(id="pe", source=s0.visual_node_id, target=s1.visual_node_id,
                             relation="not_a_relation", canonical_edge_id=None,
                             visual_class="overlay-drill")
        proj = _projection([s0, s1])
        proj.projection_edges = [bad]
        with self.assertRaises(ProjectionValidationError):
            proj.validate()


class TestRequestAndActionValidation(unittest.TestCase):
    def test_node_request_requires_nodes(self):
        with self.assertRaises(ValueError):
            GraphDrillRequest(template_id="t", interaction_kind="node").validate()

    def test_edge_request_requires_edges(self):
        with self.assertRaises(ValueError):
            GraphDrillRequest(template_id="t", interaction_kind="edge").validate()

    def test_launchable_action_requires_spec(self):
        with self.assertRaises(ValueError):
            LaunchAction(id="a", label="x", target="trainer", status="launchable",
                         semantic_group="node_identity", interaction_kind="node").validate()

    def test_reserved_action_needs_no_spec(self):
        LaunchAction(id="a", label="Seventh chord (reserved)", target="trainer",
                     status="reserved", semantic_group="functional_equivalence",
                     interaction_kind="node", reason="engine is triad-based").validate()


if __name__ == "__main__":
    unittest.main()
