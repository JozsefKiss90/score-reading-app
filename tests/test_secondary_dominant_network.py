"""Ticket 18 (G5b) — the secondary-dominant network template + scene.

The planned stub graduates: ``secondary_dominant_network_v1`` registers for
real, the ``secondary_dominant_of`` relation flips reserved -> implemented,
and applied-chord drills stop failing closed — they route to the new
``secondary_dominant_path`` scene, which lights the applied edge (D7 -> G)
while the intruder is the current chord.

The honesty gate this ticket must not break: a relation is only implemented
where a *launchable* drill exists, and an applied chord never lands on a
diatonic node that merely shares its root.
"""

import unittest

from harmony.exercise_spec import HarmonyExerciseSpec
from harmony.graph_scene_router import (
    GraphSceneRequest,
    build_graph_scene,
    decide_graph_scene,
)
from harmony.harmonic_network import NetworkBuildContext, build_network
from harmony.lab_spec import LabExperimentSpec
from harmony.network_template import (
    IMPLEMENTED_RELATIONS,
    PLANNED_TEMPLATES,
    RESERVED_RELATIONS,
    TEMPLATES,
    get_template,
    list_templates,
)
from theory.diatonic_harmony import (
    APPLIED_DOMINANT_HEADS,
    applied_tokens_for_mode,
    parse_applied_token,
)


def _applied_lab(stages=("spot",), progression=("I", "vi", "V7/V", "V", "I"),
                 render="block", mode="major", key="C major"):
    return LabExperimentSpec(
        experiment_id="t18_applied", title="Spot the intruder",
        concept="applied_chord", mode=mode, key=key, render=render,
        parameters={"progression": list(progression), "stages": list(stages)})


def _applied_drill(pattern=("I", "vi", "V7/V", "V", "I"), keys=("C",), mode="major"):
    return HarmonyExerciseSpec(
        exercise_id="t18_applied_fn", title="Applied", drill="function",
        mode=mode, pattern=list(pattern), keys=list(keys))


# --------------------------------------------------------------------------- #
# 1. The vocabulary flip
# --------------------------------------------------------------------------- #

class TestRelationFlip(unittest.TestCase):
    def test_secondary_dominant_of_is_implemented(self):
        self.assertIn("secondary_dominant_of", IMPLEMENTED_RELATIONS)
        self.assertNotIn("secondary_dominant_of", RESERVED_RELATIONS)

    def test_other_relations_stay_reserved(self):
        for rel in ("borrowed_from_parallel", "tritone_substitute_of",
                    "common_tone_diminished", "enharmonic_equivalent_of",
                    "modulation_path_to"):
            self.assertIn(rel, RESERVED_RELATIONS, rel)

    def test_template_graduated_out_of_the_planned_stubs(self):
        planned = {pt.template_id for pt in PLANNED_TEMPLATES}
        self.assertNotIn("secondary_dominant_network_v1", planned)
        self.assertIn("modulation_path_network_v1", planned)
        self.assertIn("secondary_dominant_network_v1", TEMPLATES)
        statuses = {t["template_id"]: t["status"] for t in list_templates()}
        self.assertEqual(statuses["secondary_dominant_network_v1"], "implemented")

    def test_the_no_relation_without_content_gate_survived_the_flip(self):
        """Leaving ``RESERVED_RELATIONS`` must not lose the gate it provided.

        A template may only implement ``secondary_dominant_of`` if it also runs the rules
        that emit applied nodes — and those are emitted only where a launchable drill
        exists (plan section 9.2 invariant 2).
        """
        from harmony.network_template import EdgeClass, secondary_dominant_network_v1

        stray = EdgeClass("secondary_dominant_of", "Secondary dominant of")
        for mutate, needle in (
            # (checked before validate's layout-rule pass, so this is the relation gate
            #  talking, not the missing layout rule)
            (lambda t: t.node_classes.pop(2), "must declare the 'applied_dominant' node class"),
            (lambda t: t.node_generation_rules.remove("secondary_dominant_nodes"),
             "secondary_dominant_nodes"),
            (lambda t: t.generation_rules.remove("secondary_dominant_edges"),
             "secondary_dominant_edges"),
        ):
            tpl = secondary_dominant_network_v1()
            mutate(tpl)
            with self.assertRaises(ValueError) as ctx:
                tpl.validate()
            self.assertIn(needle, str(ctx.exception))

        # ...and a template that merely names the relation without generating it is refused
        tpl = get_template("core_triad_function_network_v1")
        tpl.edge_classes.append(stray)
        with self.assertRaises(ValueError):
            tpl.validate()

    def test_legacy_circle_template_no_longer_names_it_reserved(self):
        # The circle template's reserved list is its own honest vocabulary: a
        # relation it does not generate AND that nothing else implements.
        tpl = get_template("dominant_diminished_relative_network_v1")
        self.assertNotIn("secondary_dominant_of", tpl.relations())


# --------------------------------------------------------------------------- #
# 2. The template + its builder
# --------------------------------------------------------------------------- #

class TestSecondaryDominantTemplate(unittest.TestCase):
    def setUp(self):
        self.tpl = get_template("secondary_dominant_network_v1")
        self.net = build_network(self.tpl,
                                 context=NetworkBuildContext(key="C", mode="major"))

    def test_registered_and_validates(self):
        self.tpl.validate()
        self.assertEqual(self.tpl.template_id, "secondary_dominant_network_v1")
        self.assertIn("secondary_dominant_of", self.tpl.implemented_relations())

    def test_node_inventory(self):
        kinds = self.net.counts()["nodesByKind"]
        self.assertEqual(kinds["key_center"], 1)
        self.assertEqual(kinds["diatonic_triad"], 7)
        # Every buildable applied DOMINANT of the mode gets a node (V/x + V7/x
        # for the five tonicisable degrees of a major key).  The applied
        # leading-tone chords (vii°7/x, ticket 19) are deliberately not here:
        # this template's chromatic node class is the applied dominant, and a
        # node class it does not declare is never smuggled in under it.
        self.assertEqual(kinds["applied_dominant"],
                         len(applied_tokens_for_mode(
                             "major", heads=APPLIED_DOMINANT_HEADS)))

    def test_applied_nodes_are_the_engine_vocabulary(self):
        romans = sorted(n.data["roman"] for n in self.net.nodes_of_kind("applied_dominant"))
        self.assertEqual(romans, sorted(applied_tokens_for_mode(
            "major", heads=APPLIED_DOMINANT_HEADS)))
        self.assertTrue(all(not r.startswith("vii°7/") for r in romans))
        # the tonic and the diminished degree can never be tonicised
        for roman in romans:
            self.assertNotIn(parse_applied_token(roman)[1], ("I", "vii°"))

    def test_every_applied_node_points_at_its_target_triad(self):
        by_id = {n.id: n for n in self.net.nodes}
        edges = [e for e in self.net.edges if e.relation == "secondary_dominant_of"]
        self.assertEqual(len(edges), len(self.net.nodes_of_kind("applied_dominant")))
        for e in edges:
            src, tgt = by_id[e.source], by_id[e.target]
            self.assertEqual(src.kind, "applied_dominant")
            self.assertEqual(tgt.kind, "diatonic_triad")
            self.assertEqual(parse_applied_token(src.data["roman"])[1], tgt.data["roman"])

    def test_the_honesty_gate_every_applied_edge_has_a_launchable_drill(self):
        by_id = {n.id: n for n in self.net.nodes}
        for e in self.net.edges:
            if e.relation != "secondary_dominant_of":
                continue
            entries = by_id[e.source].trainer_specs
            self.assertTrue(entries, e.source)
            self.assertTrue(all(x["status"] == "launchable" for x in entries), e.source)
        self.assertEqual(self.net.counts()["reservedDrills"], 0)

    def test_applied_nodes_are_not_diatonic(self):
        # An applied chord belongs to no key node: only the diatonic triads do.
        ctx_sources = {e.source for e in self.net.edges if e.relation == "belongs_to_key"}
        applied_ids = {n.id for n in self.net.nodes_of_kind("applied_dominant")}
        self.assertFalse(ctx_sources & applied_ids)
        self.assertEqual(len(ctx_sources), 7)

    def test_deterministic(self):
        a = build_network(self.tpl, context=NetworkBuildContext(key="C", mode="major"))
        b = build_network(self.tpl, context=NetworkBuildContext(key="C", mode="major"))
        self.assertEqual(a.to_payload(), b.to_payload())

    def test_other_key_context(self):
        net = build_network(self.tpl, context=NetworkBuildContext(key="Ab", mode="major"))
        applied = {n.data["roman"]: n for n in net.nodes_of_kind("applied_dominant")}
        self.assertIn("V7/V", applied)
        self.assertEqual(applied["V7/V"].label, "Bb7")

    def test_harmonic_minor_context(self):
        net = build_network(self.tpl,
                            context=NetworkBuildContext(key="A", mode="harmonic_minor"))
        romans = sorted(n.data["roman"] for n in net.nodes_of_kind("applied_dominant"))
        self.assertEqual(romans, sorted(applied_tokens_for_mode(
            "harmonic_minor", heads=APPLIED_DOMINANT_HEADS)))
        self.assertIn("V7/iv", romans)

    def test_payload_round_trips(self):
        payload = self.net.to_payload()
        self.assertEqual(payload["template"]["template_id"],
                         "secondary_dominant_network_v1")
        self.assertTrue(payload["launchables"])
        self.assertTrue(all(item["status"] == "launchable"
                            for item in payload["launchables"]))


# --------------------------------------------------------------------------- #
# 3. Graph -> drill: what an applied node / edge launches
# --------------------------------------------------------------------------- #

class TestAppliedLaunchActions(unittest.TestCase):
    TEMPLATE = "secondary_dominant_network_v1"

    @classmethod
    def setUpClass(cls):
        from harmony.harmonic_flow import GraphDrillRequest
        cls.request_cls = GraphDrillRequest
        cls.net = build_network(get_template(cls.TEMPLATE),
                                context=NetworkBuildContext(key="C", mode="major"))
        cls.node_id = "hn:applied:C:major:V7_of_V"

    def _actions(self, **kw):
        from harmony.network_launch import actions_for_selection
        return actions_for_selection(
            self.request_cls(template_id=self.TEMPLATE, **kw), self.net)

    def test_applied_node_offers_the_chord_and_its_resolution(self):
        acts = self._actions(interaction_kind="node", selected_node_ids=[self.node_id])
        self.assertTrue(acts)
        self.assertTrue(all(a.status == "launchable" for a in acts))
        patterns = [tuple(a.spec["pattern"]) for a in acts]
        self.assertIn(("V7/V",), patterns)
        self.assertIn(("V7/V", "V"), patterns)

    def test_applied_node_is_never_offered_a_diatonic_family_or_inversion(self):
        acts = self._actions(interaction_kind="node", selected_node_ids=[self.node_id])
        # no "tonic family neighbours" (D7 has no family in C major) and no Lab inversion
        self.assertEqual([a for a in acts if a.target != "trainer"], [])
        self.assertEqual([a for a in acts
                          if a.semantic_group == "functional_neighbourhood"], [])

    def test_the_applied_edge_launches_the_resolution_drill(self):
        edge = next(e for e in self.net.edges
                    if e.relation == "secondary_dominant_of" and e.source == self.node_id)
        acts = self._actions(interaction_kind="edge", selected_edge_ids=[edge.id])
        self.assertEqual(len(acts), 1)
        self.assertEqual(acts[0].status, "launchable")
        self.assertEqual(tuple(acts[0].spec["pattern"]), ("V7/V", "V"))


# --------------------------------------------------------------------------- #
# 4. Projection honesty: an applied chord never lands on a diatonic node
# --------------------------------------------------------------------------- #

class TestAppliedProjectionHonesty(unittest.TestCase):
    """``V7/V``'s ``degree_index`` is a letter offset (D is the 2nd letter of C major),
    so a naive diatonic match would put D7 on the ``Dm`` node.  It must not."""

    def setUp(self):
        from harmony.network_projection import project_harmony_exercise
        self.project = project_harmony_exercise
        self.spec = _applied_drill()

    def _step(self, template_id):
        net = build_network(get_template(template_id),
                            context=NetworkBuildContext(key="C", mode="major"))
        proj = self.project(self.spec, net)
        return next(s for s in proj.steps if s.roman == "V7/V")

    def test_exact_on_its_own_applied_node(self):
        step = self._step("secondary_dominant_network_v1")
        self.assertEqual(step.mapping_status, "exact")
        self.assertEqual(step.primary_network_node, "hn:applied:C:major:V7_of_V")

    def test_honest_overlay_where_the_template_has_no_applied_node(self):
        step = self._step("core_triad_function_network_v1")
        self.assertEqual(step.mapping_status, "contextual")
        self.assertIsNone(step.primary_network_node)
        self.assertTrue(step.visual_node_id.startswith("overlay:applied:"))
        # never the Dm node that merely shares its root
        self.assertNotEqual(step.visual_node_id, "hn:triad:C:major:1")


# --------------------------------------------------------------------------- #
# 5. Routing: applied chords stop failing closed
# --------------------------------------------------------------------------- #

class TestAppliedRouting(unittest.TestCase):
    def test_lab_applied_spec_routes_to_the_new_scene(self):
        d = decide_graph_scene(GraphSceneRequest(lab_spec=_applied_lab()))
        self.assertEqual(d.status, "supported")
        self.assertEqual(d.scene_type, "secondary_dominant_path")

    def test_native_applied_drill_routes_to_the_new_scene(self):
        d = decide_graph_scene(GraphSceneRequest(exercise_spec=_applied_drill()))
        self.assertEqual(d.status, "supported")
        self.assertEqual(d.scene_type, "secondary_dominant_path")

    def test_resolve_stage_routes_too(self):
        d = decide_graph_scene(
            GraphSceneRequest(lab_spec=_applied_lab(stages=("resolve",),
                                                    render="arpeggio")))
        self.assertEqual(d.scene_type, "secondary_dominant_path")

    def test_metadata_cannot_route_an_applied_drill_onto_a_diatonic_scene(self):
        d = decide_graph_scene(GraphSceneRequest(
            exercise_spec=_applied_drill(),
            source_metadata={"graph_scene_type": "functional_progression"}))
        self.assertEqual(d.scene_type, "secondary_dominant_path")

    def test_manual_override_cannot_claim_an_applied_drill_either(self):
        d = decide_graph_scene(GraphSceneRequest(
            exercise_spec=_applied_drill(),
            preferred_scene_type="diatonic_key_field"))
        self.assertEqual(d.scene_type, "secondary_dominant_path")

    def test_diatonic_drills_are_untouched(self):
        d = decide_graph_scene(GraphSceneRequest(exercise_spec=HarmonyExerciseSpec(
            exercise_id="t18_plain", title="Plain", drill="function", mode="major",
            pattern=["ii", "V", "I"], keys=["C"])))
        self.assertEqual(d.scene_type, "functional_progression")

    def test_a_diatonic_drill_never_gets_the_applied_scene(self):
        d = decide_graph_scene(GraphSceneRequest(
            exercise_spec=HarmonyExerciseSpec(
                exercise_id="t18_plain2", title="Plain", drill="function",
                mode="major", pattern=["ii", "V", "I"], keys=["C"]),
            preferred_scene_type="secondary_dominant_path"))
        self.assertNotEqual(d.scene_type, "secondary_dominant_path")


# --------------------------------------------------------------------------- #
# 6. The scene itself
# --------------------------------------------------------------------------- #

class TestSecondaryDominantScene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene = build_graph_scene(GraphSceneRequest(lab_spec=_applied_lab()))

    def _applied_occurrence(self, scene=None):
        scene = scene or self.scene
        return next(o for o in scene.occurrence_map
                    if parse_applied_token(o.roman) is not None)

    def test_scene_type_and_validity(self):
        self.assertEqual(self.scene.scene_type, "secondary_dominant_path")
        self.scene.validate()
        self.assertEqual(len(self.scene.occurrence_map), 5)

    def test_the_intruder_is_a_seventh_chord_of_its_own(self):
        occ = self._applied_occurrence()
        self.assertEqual(occ.roman, "V7/V")
        self.assertEqual(occ.chord_symbol, "D7")
        self.assertEqual(occ.entity_type, "seventh")
        self.assertEqual(occ.mapping_status, "exact")
        node = self.scene.node(occ.node_id)
        self.assertEqual(node.chord_tones, ("D", "F#", "A", "C"))

    def test_applied_edge_exists_and_names_the_target(self):
        occ = self._applied_occurrence()
        target = self.scene.occurrence_at(occ.sequence_index + 1)
        self.assertEqual(target.roman, "V")
        edges = [e for e in self.scene.edges if e.relation == "secondary_dominant_of"]
        self.assertEqual(len(edges), 1)
        self.assertEqual((edges[0].source, edges[0].target),
                         (occ.node_id, target.node_id))
        self.assertEqual(edges[0].layer, "theory")

    def test_the_applied_edge_lights_while_the_intruder_plays(self):
        occ = self._applied_occurrence()
        edge = next(e for e in self.scene.edges
                    if e.relation == "secondary_dominant_of")
        self.assertIn(edge.id, occ.activation.theory_edge_ids)

    def test_the_intruder_has_no_key_context_edge(self):
        occ = self._applied_occurrence()
        ctx = [e for e in self.scene.edges
               if e.relation == "belongs_to_key" and e.source == occ.node_id]
        self.assertEqual(ctx, [])
        self.assertEqual(occ.activation.context_node_ids, ())
        # the diatonic chords DO sit in the key
        diatonic = self.scene.occurrence_at(0)
        self.assertTrue(diatonic.activation.context_node_ids)

    def test_no_chord_lands_on_a_key_node(self):
        key_ids = set(self.scene.key_anchor_ids())
        self.assertTrue(key_ids)
        for o in self.scene.occurrence_map:
            self.assertNotIn(o.node_id, key_ids)

    def test_detail_explains_the_tonicisation(self):
        occ = self._applied_occurrence()
        self.assertEqual(occ.detail["appliedTarget"], "V")
        self.assertIn("F#", occ.detail["chromaticTones"])
        self.assertTrue(occ.detail["whyBelongs"])

    def test_resolve_stage_scene(self):
        scene = build_graph_scene(GraphSceneRequest(
            lab_spec=_applied_lab(stages=("resolve",))))
        self.assertEqual(scene.scene_type, "secondary_dominant_path")
        self.assertEqual(len(scene.occurrence_map), 2)
        self.assertEqual([o.roman for o in scene.occurrence_map], ["V7/V", "V"])
        self.assertEqual(len([e for e in scene.edges
                              if e.relation == "secondary_dominant_of"]), 1)

    def test_a_delayed_resolution_is_never_claimed_as_the_next_relation(self):
        # The arrow still points at the real target two chords away, but the step to the
        # chord in between is sequence-only — claiming it would mis-describe the motion.
        scene = build_graph_scene(GraphSceneRequest(
            exercise_spec=_applied_drill(pattern=("V7/V", "I", "V"))))
        occ = self._applied_occurrence(scene)
        self.assertIsNone(occ.next_theory_relation)
        self.assertEqual(occ.next_relation_status, "sequence_only")
        self.assertEqual(occ.activation.theory_edge_ids, ())
        edge = next(e for e in scene.edges if e.relation == "secondary_dominant_of")
        self.assertEqual(edge.target, scene.occurrence_at(2).node_id)

    def test_cross_key_drill_keeps_every_chord_and_its_own_key_anchor(self):
        # No group map exists for this scene, so sequence indices must stay 1:1 with the
        # trainer's: every chord is drawn, each under the key anchor it actually belongs to.
        scene = build_graph_scene(GraphSceneRequest(
            exercise_spec=_applied_drill(pattern=("V7/V", "V"), keys=("C", "G"))))
        self.assertEqual(len(scene.occurrence_map), 4)
        self.assertEqual(len(scene.nodes_of_type("key")), 2)
        self.assertEqual(len([e for e in scene.edges
                              if e.relation == "secondary_dominant_of"]), 2)
        self.assertTrue(any("cross-key" in w for w in scene.warnings))
        for o in scene.occurrence_map:
            node = scene.node(o.node_id)
            self.assertEqual(node.key_context, o.key_context)

    def test_every_shipped_applied_leaf_builds_a_scene(self):
        from harmony.curriculum import build_curriculum
        lesson = build_curriculum().find("lesson:adv_secondary")
        leaves = [n for n in lesson.walk() if n.kind == "exercise"]
        self.assertEqual(len(leaves), 12)
        for leaf in leaves:
            scene = build_graph_scene(GraphSceneRequest(
                curriculum_node_id=leaf.id, lab_spec=leaf.lab_spec))
            self.assertEqual(scene.scene_type, "secondary_dominant_path", leaf.id)
            self.assertEqual(
                len([e for e in scene.edges
                     if e.relation == "secondary_dominant_of"]), 1, leaf.id)
            occ = self._applied_occurrence(scene)
            applied_edges = [e.id for e in scene.edges
                             if e.relation == "secondary_dominant_of"]
            self.assertEqual(list(occ.activation.theory_edge_ids), applied_edges, leaf.id)


if __name__ == "__main__":
    unittest.main()
