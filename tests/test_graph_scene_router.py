"""Phase 1 tests for harmony/graph_scene_router.py + graph_scene_generators.py.

Asserts the section-6 routing table (semantic routing, NEVER by root pitch class), the
native-drill unwrap, the manual-override warning, fail-closed behaviour, and the *content* of the
built scenes (the semantics a green-but-misleading suite previously missed, plan section 10).
"""

import unittest

from harmony.atlas import full_key_spec, degree_spec, function_spec, quality_drills
from harmony.exercise_spec import HarmonyExerciseSpec
from harmony.lab import lab_demo_specs
from harmony.lab_spec import LabExperimentSpec, spec_from_lab_request
from harmony.graph_scene_router import (
    GraphSceneRequest, decide_graph_scene, build_graph_scene,
)


def _req(**kw):
    return GraphSceneRequest(**kw)


def _decide(**kw):
    return decide_graph_scene(_req(**kw))


class TestRoutingTable(unittest.TestCase):
    """The section-6 explicit routing table."""

    def test_full_key_routes_to_diatonic_key_field(self):
        d = _decide(exercise_spec=full_key_spec("C", "major"))
        self.assertEqual(d.status, "supported")
        self.assertEqual(d.scene_type, "diatonic_key_field")

    def test_horizontal_degree_routes_to_degree_transposition(self):
        self.assertEqual(_decide(exercise_spec=degree_spec("V", "major")).scene_type,
                         "degree_transposition")

    def test_quality_routes_to_triad_quality_class(self):
        qspec = quality_drills("major")["major"][0]
        self.assertEqual(_decide(exercise_spec=qspec).scene_type, "triad_quality_class")

    def test_function_progression_routes_to_functional_progression(self):
        d = _decide(exercise_spec=function_spec(["I", "IV", "V", "I"], "I-IV-V-I", "major", ["C"]))
        self.assertEqual(d.scene_type, "functional_progression")

    def test_one_chord_function_routes_to_key_field(self):
        d = _decide(exercise_spec=function_spec(["I"], "tonic", "major", ["C"]))
        self.assertEqual(d.scene_type, "diatonic_key_field")

    def test_lab_inversion_routes_to_inversion_space(self):
        lab = LabExperimentSpec(experiment_id="inv", title="inv", concept="inversion")
        self.assertEqual(_decide(lab_spec=lab).scene_type, "inversion_space")

    def test_lab_voice_leading_routes_to_voice_leading_path(self):
        lab = LabExperimentSpec(experiment_id="vl", title="vl", concept="voice_leading",
                                render="voice_leading")
        self.assertEqual(_decide(lab_spec=lab).scene_type, "voice_leading_path")

    def test_lab_cadence_routes_by_render(self):
        block = LabExperimentSpec(experiment_id="c", title="c", concept="cadence", render="block")
        vl = LabExperimentSpec(experiment_id="c", title="c", concept="cadence",
                               render="voice_leading")
        self.assertEqual(_decide(lab_spec=block).scene_type, "cadence_resolution")
        self.assertEqual(_decide(lab_spec=vl).scene_type, "voice_leading_path")

    def test_lab_polyphonic_routes_to_polyphonic_path(self):
        lab = LabExperimentSpec(experiment_id="p", title="p", concept="polyphonic_harmony",
                                render="polyphonic")
        self.assertEqual(_decide(lab_spec=lab).scene_type, "polyphonic_harmony_path")

    def test_lab_motive_is_unsupported(self):
        lab = LabExperimentSpec(experiment_id="m", title="m", concept="motive", render="melody")
        d = _decide(lab_spec=lab)
        self.assertEqual(d.status, "unsupported")
        self.assertEqual(d.scene_type, "unsupported")

    def test_lab_technique_is_unsupported(self):
        # Piano-technique ticket 01: the Harmonic Scene pane shows the honest
        # refusal for technique leaves (a melodic phrase claims no chord graph).
        lab = LabExperimentSpec(experiment_id="t", title="t", concept="technique",
                                render="melody")
        d = _decide(lab_spec=lab)
        self.assertEqual(d.status, "unsupported")
        self.assertEqual(d.scene_type, "unsupported")
        self.assertIn("no harmonic-graph scene", d.reason)

    def test_explore_routes_to_legacy_key_relation(self):
        self.assertEqual(_decide().scene_type, "legacy_key_relation")
        self.assertEqual(_decide(source_metadata={"explore": True}).scene_type,
                         "legacy_key_relation")

    def test_never_routes_from_root_pitch_class(self):
        # Am chord (root A) must route as vi-in-C, never to an A-minor key scene: the drill's
        # semantics (a full C-major field) decide, not the root.
        d = _decide(exercise_spec=full_key_spec("C", "major"))
        self.assertEqual(d.scene_type, "diatonic_key_field")
        self.assertEqual(d.required_context.get("key"), "C")


class TestNativeDrillUnwrap(unittest.TestCase):
    """The curriculum wraps native drills as concept='drill'; they must route by drill family."""

    def test_drill_wrapper_unwraps_and_routes_by_family(self):
        wrapped = LabExperimentSpec(
            experiment_id="drill_fk_C", title="C major all triads", concept="drill",
            parameters={"exercise": full_key_spec("C", "major").to_dict()})
        d = _decide(lab_spec=wrapped)
        self.assertEqual(d.scene_type, "diatonic_key_field")   # NOT a Lab concept route

    def test_wrapped_degree_drill_routes_to_transposition(self):
        wrapped = LabExperimentSpec(
            experiment_id="drill_deg_V", title="V across keys", concept="drill",
            parameters={"exercise": degree_spec("V", "major").to_dict()})
        self.assertEqual(_decide(lab_spec=wrapped).scene_type, "degree_transposition")


class TestOverrideAndMetadata(unittest.TestCase):
    def test_curriculum_metadata_overrides(self):
        d = _decide(exercise_spec=full_key_spec("C", "major"),
                    source_metadata={"graph_scene_type": "legacy_key_relation"})
        self.assertEqual(d.scene_type, "legacy_key_relation")
        self.assertEqual(d.reason, "curriculum graph metadata")

    def test_incompatible_manual_override_warns_not_silently_mismaps(self):
        d = _decide(exercise_spec=full_key_spec("C", "major"),
                    preferred_scene_type="degree_transposition")
        self.assertEqual(d.status, "ambiguous")
        self.assertEqual(d.scene_type, "degree_transposition")
        self.assertIn("diatonic_key_field", d.alternatives)

    def test_matching_preferred_is_not_ambiguous(self):
        d = _decide(exercise_spec=full_key_spec("C", "major"),
                    preferred_scene_type="diatonic_key_field")
        self.assertEqual(d.status, "supported")


class TestBuildDiatonicKeyField(unittest.TestCase):
    """The C-major full-key visual gate (plan section 10)."""

    def setUp(self):
        self.scene = build_graph_scene(_req(exercise_spec=full_key_spec("C", "major")))
        self.scene.validate()

    def test_scene_type_and_anchor(self):
        self.assertEqual(self.scene.scene_type, "diatonic_key_field")
        keys = self.scene.nodes_of_type("key")
        self.assertEqual([n.label for n in keys], ["C major"])
        # the key anchor carries no chord symbol (a key is not a chord)
        self.assertEqual(keys[0].chord_symbol, "")

    def test_seven_exact_triads_including_dm_and_g_not_g7(self):
        # six triads + the honestly-diminished vii°
        chords = {n.roman: n for n in (self.scene.nodes_of_type("triad")
                                       + self.scene.nodes_of_type("diminished"))}
        self.assertEqual(set(chords), {"I", "ii", "iii", "IV", "V", "vi", "vii°"})
        self.assertEqual(chords["ii"].chord_symbol, "Dm")           # Dm present
        self.assertEqual(chords["V"].chord_symbol, "G")             # V is the G major triad
        self.assertEqual(chords["V"].quality, "major")
        self.assertEqual(chords["V"].entity_type, "triad")          # a plain triad ...
        self.assertEqual(self.scene.nodes_of_type("seventh"), [])   # ... NOT a G7 node
        self.assertEqual(chords["vii°"].entity_type, "diminished")  # B° honestly diminished

    def test_am_is_a_triad_not_the_a_minor_key(self):
        am = self.scene.occurrence_at(5)
        self.assertEqual(am.chord_symbol, "Am")
        self.assertEqual(am.entity_type, "triad")
        self.assertEqual(self.scene.node(am.node_id).entity_type, "triad")
        # no A-minor key node exists in this scene at all
        self.assertFalse(any(n.entity_type == "key" and n.roman not in ("", "I")
                             for n in self.scene.nodes))

    def test_seven_occurrences_light_triads_never_the_key(self):
        self.assertEqual(len(self.scene.occurrence_map), 7)
        key_ids = set(self.scene.key_anchor_ids())
        for o in self.scene.occurrence_map:
            self.assertEqual(o.mapping_status, "exact", o.roman)
            self.assertNotIn(o.node_id, key_ids)
            self.assertIn(self.scene.node(o.node_id).entity_type, ("triad", "diminished"))

    def test_index_positions(self):
        self.assertEqual(self.scene.node(self.scene.occurrence_at(4).node_id).roman, "V")
        self.assertEqual(self.scene.occurrence_at(5).chord_symbol, "Am")
        self.assertEqual(self.scene.occurrence_at(6).chord_symbol, "B°")

    def test_enumeration_carries_no_theory_relation(self):
        for o in self.scene.occurrence_map:
            self.assertIsNone(o.next_theory_relation)
            if o.next_sequence_relation is not None:
                self.assertEqual(o.next_sequence_relation, "enumerate_next")
        # theory edges DO exist as a separate, default-off optional layer
        theory = [l for l in self.scene.layer_definitions if l.id == "theory"]
        self.assertTrue(theory and not theory[0].default_visible)


class TestBuildDegreeTransposition(unittest.TestCase):
    def setUp(self):
        self.scene = build_graph_scene(_req(exercise_spec=degree_spec("V", "major")))
        self.scene.validate()

    def test_one_degree_node_and_twelve_instances(self):
        self.assertEqual(self.scene.scene_type, "degree_transposition")
        degs = self.scene.nodes_of_type("degree")
        self.assertEqual(len(degs), 1)
        self.assertEqual(degs[0].label, "V")
        self.assertEqual(len(self.scene.nodes_of_type("triad")), 12)
        self.assertEqual(len(self.scene.occurrence_map), 12)

    def test_transposition_not_modulation(self):
        # every transition is a transposition, and NO theory (harmonic-motion) edge exists
        for o in self.scene.occurrence_map:
            self.assertIsNone(o.next_theory_relation)
            if o.next_sequence_relation is not None:
                self.assertEqual(o.next_sequence_relation, "transpose_next")
        self.assertNotIn("theory", self.scene.counts()["edgesByLayer"])
        # the central degree node is the invariant concept, never a current occurrence
        deg_id = self.scene.nodes_of_type("degree")[0].id
        self.assertFalse(any(o.node_id == deg_id for o in self.scene.occurrence_map))


class TestBuildFunctionalProgression(unittest.TestCase):
    """The bounded, path-shaped progression scene (plan section 5.E)."""

    def setUp(self):
        self.scene = build_graph_scene(
            _req(exercise_spec=function_spec(["I", "IV", "V", "I"], "I-IV-V-I", "major", ["C"])))
        self.scene.validate()

    def test_bounded_path_not_seven_triad_field(self):
        self.assertEqual(self.scene.scene_type, "functional_progression")
        # exactly the four progression chords as markers -- NOT the whole seven-triad field
        self.assertEqual(len(self.scene.nodes_of_type("triad")), 4)
        self.assertEqual(len(self.scene.nodes_of_type("function")), 3)   # function lanes
        self.assertEqual(len(self.scene.nodes_of_type("key")), 1)

    def test_four_occurrences_repeated_tonic_distinct_markers_one_identity(self):
        occ = self.scene.occurrence_map
        self.assertEqual(len(occ), 4)
        self.assertEqual([o.roman for o in occ], ["I", "IV", "V", "I"])
        # distinct occurrence MARKERS for the repeated chord ...
        self.assertNotEqual(occ[0].node_id, occ[3].node_id)
        self.assertNotEqual(occ[0].occurrence_id, occ[3].occurrence_id)
        # ... of ONE chord identity
        n0, n3 = self.scene.node(occ[0].node_id), self.scene.node(occ[3].node_id)
        self.assertEqual(n0.chord_symbol, n3.chord_symbol)
        self.assertEqual(n0.data.get("chordIdentity"), n3.data.get("chordIdentity"))

    def test_v_is_g_triad_not_g7(self):
        v = self.scene.occurrence_at(2)
        self.assertEqual(v.chord_symbol, "G")
        self.assertEqual(self.scene.node(v.node_id).entity_type, "triad")
        self.assertEqual(self.scene.nodes_of_type("seventh"), [])

    def test_function_lanes_and_theory_motion(self):
        by_roman = {o.roman: o for o in self.scene.occurrence_map}
        # broad-function lanes are assigned
        self.assertEqual(self.scene.node(by_roman["IV"].node_id).data["broadFunction"], "predominant")
        self.assertEqual(self.scene.node(by_roman["V"].node_id).data["broadFunction"], "dominant")
        # V -> I lights a real theory relation (resolution), in its own theory layer
        self.assertEqual(by_roman["V"].next_theory_relation, "resolves_to")
        self.assertIn("theory", self.scene.counts()["edgesByLayer"])
        self.assertIn("sequence", self.scene.counts()["edgesByLayer"])

    def test_cross_key_shows_one_local_key(self):
        multi = build_graph_scene(_req(exercise_spec=function_spec(
            ["ii", "V", "I"], "ii-V-I across keys", "major", ["C", "G", "D"])))
        multi.validate()
        self.assertEqual(multi.metadata["shownGroup"], 0)
        self.assertEqual(multi.metadata["totalGroups"], 3)
        # only the first local key's chords are drawn (bounded), not one giant all-key graph
        self.assertEqual(len(multi.occurrence_map), 3)
        self.assertTrue(any("transposes" in w for w in multi.warnings))


class TestBuildQualityClass(unittest.TestCase):
    """A quality drill -> one quality anchor + exact instances, no cross-key proxies (5.D)."""

    def setUp(self):
        self.scene = build_graph_scene(_req(exercise_spec=quality_drills("major")["major"][0]))
        self.scene.validate()

    def test_quality_anchor_and_exact_instances(self):
        self.assertEqual(self.scene.scene_type, "triad_quality_class")
        self.assertEqual(len(self.scene.nodes_of_type("quality")), 1)
        # every drilled chord is an EXACT instance -- no honest-but-ugly cross-key proxies
        self.assertTrue(self.scene.occurrence_map)
        self.assertTrue(all(o.mapping_status == "exact" for o in self.scene.occurrence_map))
        self.assertEqual(self.scene.nodes_of_type("occurrence"), [])

    def test_classification_never_a_progression(self):
        # enumerate_next only, and NO theory edge anywhere (a classification, not motion)
        self.assertNotIn("theory", self.scene.counts()["edgesByLayer"])
        for o in self.scene.occurrence_map:
            self.assertIsNone(o.next_theory_relation)
            if o.next_sequence_relation is not None:
                self.assertEqual(o.next_sequence_relation, "enumerate_next")
        # the quality anchor is the invariant concept, never a current occurrence
        qid = self.scene.nodes_of_type("quality")[0].id
        self.assertFalse(any(o.node_id == qid for o in self.scene.occurrence_map))


class TestBuildCadence(unittest.TestCase):
    """A block-render Lab cadence -> a cadence_resolution scene (5.F)."""

    def _cad(self, render="block"):
        return LabExperimentSpec(experiment_id="cad", title="V-I authentic cadence",
                                 concept="cadence", mode="major", key="C major", render=render,
                                 parameters={"pattern": ["V", "I"]})

    def test_block_cadence_routes_and_builds(self):
        scene = build_graph_scene(_req(lab_spec=self._cad("block")))
        scene.validate()
        self.assertEqual(scene.scene_type, "cadence_resolution")
        self.assertEqual([o.roman for o in scene.occurrence_map], ["V", "I"])
        self.assertEqual(scene.occurrence_at(0).chord_symbol, "G")           # V triad, not G7
        self.assertEqual(scene.occurrence_at(0).next_theory_relation, "resolves_to")
        # A bare V–I is the authentic FAMILY: without a controlled soprano the
        # scene may not claim "perfect" (ticket 16 / plan F9).
        self.assertEqual(scene.metadata.get("cadenceType"), "authentic")

    def test_voice_leading_render_defers_to_phase6(self):
        self.assertEqual(decide_graph_scene(_req(lab_spec=self._cad("voice_leading"))).scene_type,
                         "voice_leading_path")


class TestBuildVoiceLeading(unittest.TestCase):
    """A Lab voice_leading experiment -> the harmonic path + a voice-motion layer (5.H)."""

    def setUp(self):
        vl = spec_from_lab_request({"labConcept": "voice_leading", "key": "C major",
                                    "mode": "major", "pattern": ["ii", "V", "I"]})
        self.scene = build_graph_scene(_req(lab_spec=vl))
        self.scene.validate()

    def test_two_layers_harmonic_and_voice(self):
        self.assertEqual(self.scene.scene_type, "voice_leading_path")
        layers = self.scene.counts()["edgesByLayer"]
        self.assertIn("theory", layers)           # the harmonic path (resolves_to / prepares)
        self.assertIn("voice_leading", layers)     # the separate voice-motion layer
        # V -> I lights the resolution on the harmonic layer
        by_roman = {o.roman: o for o in self.scene.occurrence_map}
        self.assertEqual(by_roman["V"].next_theory_relation, "resolves_to")

    def test_chord_markers_carry_satb_voices_never_key(self):
        for o in self.scene.occurrence_map:
            self.assertNotEqual(self.scene.node(o.node_id).entity_type, "key")
            self.assertTrue(o.detail.get("voices"))            # the SATB pitches
            self.assertIn("voiceMotion", o.detail)


class TestBuildPolyphonic(unittest.TestCase):
    """A Lab polyphonic_harmony experiment -> implied-chord slices + voice lanes (5.I)."""

    def setUp(self):
        poly = [s for s in lab_demo_specs() if s.concept == "polyphonic_harmony"][0]
        self.scene = build_graph_scene(_req(lab_spec=poly))
        self.scene.validate()

    def test_slices_and_voice_lanes_no_asserted_motion(self):
        self.assertEqual(self.scene.scene_type, "polyphonic_harmony_path")
        self.assertTrue(self.scene.occurrence_map)
        # independent voices -> NO asserted harmonic-motion (theory) edges between slices
        self.assertNotIn("theory", self.scene.counts()["edgesByLayer"])
        self.assertIn("voice_leading", self.scene.counts()["edgesByLayer"])
        # each slice is an implied chord with its two sounding voices, never a key node
        for o in self.scene.occurrence_map:
            self.assertNotEqual(self.scene.node(o.node_id).entity_type, "key")
            self.assertTrue(o.detail.get("voices"))


class TestBuildLabAndFailClosed(unittest.TestCase):
    def test_inversion_builds_inversion_space(self):
        lab = spec_from_lab_request({"labConcept": "inversion", "key": "C major", "mode": "major",
                                     "degree": "I", "inversions": [0, 1, 2]})
        scene = build_graph_scene(_req(lab_spec=lab))
        scene.validate()
        self.assertEqual(scene.scene_type, "inversion_space")
        self.assertTrue(scene.occurrence_map)
        # a voicing occurrence is never a key node
        for o in scene.occurrence_map:
            self.assertNotEqual(scene.node(o.node_id).entity_type, "key")

    def test_motive_fails_closed_to_unsupported(self):
        lab = LabExperimentSpec(experiment_id="m", title="m", concept="motive", render="melody")
        scene = build_graph_scene(_req(lab_spec=lab))
        scene.validate()
        self.assertEqual(scene.scene_type, "unsupported")
        self.assertEqual(len(scene.nodes), 0)
        self.assertTrue(scene.warnings)

    def test_unroutable_concept_fails_closed_not_to_legacy(self):
        # a concept with no honest harmonic scene (reduction) -> unsupported, NEVER a silent
        # fall-back to the legacy graph.
        lab = LabExperimentSpec(experiment_id="r", title="r", concept="reduction", render="block")
        scene = build_graph_scene(_req(lab_spec=lab))
        scene.validate()
        self.assertEqual(scene.scene_type, "unsupported")
        self.assertNotEqual(scene.generator_id, "dominant_diminished_relative_network_v1")

    def test_explore_builds_legacy_scene(self):
        scene = build_graph_scene(_req())
        scene.validate()
        self.assertEqual(scene.scene_type, "legacy_key_relation")
        self.assertEqual(len(scene.occurrence_map), 0)
        self.assertTrue(len(scene.nodes) > 0)


class TestAuditFixes(unittest.TestCase):
    """Regression tests for the Phase-9 adversarial-audit findings."""

    def test_diminished_diatonic_triad_is_typed_diminished(self):
        # the generic netnode adapter must type a diminished diatonic triad (vii°) as 'diminished',
        # not 'triad' (musical-honesty finding #1).
        field = build_graph_scene(_req(exercise_spec=full_key_spec("C", "major")))
        b = [n for n in field.nodes if n.roman == "vii°"][0]
        self.assertEqual(b.chord_symbol, "B°")
        self.assertEqual(b.entity_type, "diminished")
        self.assertNotEqual(b.visual_class, "teal")     # visually distinct from ordinary triads
        # and the degree-transposition instances of vii° are diminished too
        deg = build_graph_scene(_req(exercise_spec=degree_spec("vii°", "major")))
        self.assertEqual(len(deg.nodes_of_type("diminished")), 12)

    def test_metadata_override_with_missing_input_falls_through_not_unsupported(self):
        # curriculum metadata naming a lab scene with no lab must NOT be claimed 'supported' then
        # silently degrade to unsupported at build time (routing finding #1/#2).
        req = _req(exercise_spec=full_key_spec("C", "major"),
                   source_metadata={"graph_scene_type": "inversion_space"})
        d = decide_graph_scene(req)
        self.assertEqual(d.status, "supported")
        self.assertEqual(d.scene_type, "diatonic_key_field")
        self.assertEqual(build_graph_scene(req).scene_type, "diatonic_key_field")

    def test_unsupported_is_not_a_valid_override_target(self):
        d = decide_graph_scene(_req(exercise_spec=full_key_spec("C", "major"),
                                    source_metadata={"graph_scene_type": "unsupported"}))
        self.assertEqual(d.scene_type, "diatonic_key_field")

    def test_incompatible_preferred_override_is_refused_when_unbuildable(self):
        d = decide_graph_scene(_req(exercise_spec=full_key_spec("C", "major"),
                                    preferred_scene_type="voice_leading_path"))  # needs a lab
        self.assertEqual(d.status, "supported")             # not 'ambiguous' -- can't build it
        self.assertEqual(d.scene_type, "diatonic_key_field")

    def test_drill_wrapper_unwrap_failure_fails_closed_not_legacy(self):
        bad = LabExperimentSpec(experiment_id="d", title="d", concept="drill", parameters={})
        scene = build_graph_scene(_req(lab_spec=bad, source_metadata={"explore": True}))
        self.assertEqual(scene.scene_type, "unsupported")

    def test_malformed_spec_never_crashes(self):
        class _Bad:
            pass
        scene = build_graph_scene(_req(exercise_spec=_Bad()))
        self.assertEqual(scene.scene_type, "unsupported")


class TestScoreScene(unittest.TestCase):
    """Score stays score-specific: generated from the score, never from the drill router (5.J/8)."""

    def setUp(self):
        from harmony.score_import import load_bwv846_analysis
        from harmony.graph_scene_generators import build_score_scene
        self.scene = build_score_scene(load_bwv846_analysis())
        self.scene.validate()

    def test_score_scene_from_the_score_itself(self):
        self.assertEqual(self.scene.scene_type, "score_harmonic_path")
        self.assertEqual(self.scene.semantic_scope, "score")
        self.assertTrue(self.scene.occurrence_map)
        # every slice is a score_slice marker, never a key node
        for o in self.scene.occurrence_map:
            self.assertEqual(o.entity_type, "score_slice")
            self.assertNotEqual(self.scene.node(o.node_id).entity_type, "key")
        # no asserted harmonic-motion between slices (score order only)
        self.assertNotIn("theory", self.scene.counts()["edgesByLayer"])

    def test_drill_router_never_produces_a_score_scene(self):
        # no GraphSceneRequest field carries a score, so the ordinary router can never emit one
        for spec in (full_key_spec("C", "major"), degree_spec("V", "major")):
            self.assertNotEqual(build_graph_scene(_req(exercise_spec=spec)).scene_type,
                                "score_harmonic_path")
        # even an explicit metadata request for it is refused (not router-buildable)
        d = decide_graph_scene(_req(exercise_spec=full_key_spec("C", "major"),
                                    source_metadata={"graph_scene_type": "score_harmonic_path"}))
        self.assertNotEqual(d.scene_type, "score_harmonic_path")


if __name__ == "__main__":
    unittest.main()
