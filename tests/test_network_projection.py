"""Phase 2 tests for harmony/network_projection.py (Drill -> Graph projection).

Exercised against the legacy ``dominant_diminished_relative_network_v1`` template (the core
exact-triad template is tested in tests/test_network_templates.py once it exists). Covers the
plan's section 20.2 cases that do not require exact triad nodes: full-key, multi-key groups,
transposition orbit, quality, legacy proxies, enharmonic spelling, repeated chords, natural minor.
"""

import unittest

from harmony.harmonic_network import build_network
from harmony.network_template import get_template
from harmony.exercise_spec import HarmonyExerciseSpec
from harmony.network_projection import project_harmony_exercise
from harmony.atlas import full_key_spec, degree_spec, function_spec, quality_drills


def _legacy():
    return build_network(get_template("dominant_diminished_relative_network_v1"))


class TestFullKey(unittest.TestCase):
    def setUp(self):
        self.net = _legacy()

    def test_c_major_full_key_seven_steps_enumeration(self):
        proj = project_harmony_exercise(full_key_spec("C", "major"), self.net)
        proj.validate()
        self.assertEqual(len(proj.steps), 7)
        self.assertEqual(proj.semantic_group, "tonal_field")
        self.assertEqual(proj.sequence_semantics, "pedagogical_enumeration")
        # a single pedagogical group, no boundaries
        self.assertEqual(proj.counts()["groups"], 1)
        # CRITICAL: enumeration never asserts a theoretical resolution edge
        self.assertEqual(proj.counts()["theoryEdges"], 0)
        self.assertTrue(all(t.theory_relation is None for t in proj.transitions))
        self.assertTrue(all(t.sequence_relation == "enumerate_next" for t in proj.transitions))

    def test_key_node_never_masquerades_as_tonic_chord(self):
        proj = project_harmony_exercise(full_key_spec("C", "major"), self.net)
        tonic = proj.step_at_index(0)
        # the I chord is NOT the C key node; it is an honest overlay proxy
        self.assertTrue(tonic.visual_node_id.startswith("overlay:triad:C:major:0"))
        self.assertEqual(tonic.mapping_status, "contextual")
        self.assertIn("hn:major:C", tonic.context_network_nodes)

    def test_legacy_proxies_dim_exact_v_approximate(self):
        proj = project_harmony_exercise(full_key_spec("C", "major"), self.net)
        by_roman = {s.roman: s for s in proj.steps}
        # missing triads -> contextual proxies anchored to the key
        for roman in ("I", "ii", "iii", "IV", "vi"):
            self.assertEqual(by_roman[roman].mapping_status, "contextual", roman)
            self.assertTrue(by_roman[roman].visual_node_id.startswith("overlay:"))
        # exact diminished node reused
        self.assertEqual(by_roman["vii°"].mapping_status, "exact")
        self.assertEqual(by_roman["vii°"].visual_node_id, "hn:dim:B")
        # V triad shown on the V7 node -> approximate, NEVER exact
        self.assertEqual(by_roman["V"].mapping_status, "approximate")
        self.assertEqual(by_roman["V"].visual_node_id, "hn:dom7:G")
        self.assertTrue(any("approximate" in w or "V triad" in w for w in proj.warnings))

    def test_proxy_nodes_exist_and_are_anchored(self):
        proj = project_harmony_exercise(full_key_spec("C", "major"), self.net)
        self.assertTrue(proj.projection_nodes)
        for pn in proj.projection_nodes:
            self.assertEqual(pn.kind, "proxy_triad")
            self.assertEqual(pn.anchor_node_id, "hn:major:C")
            self.assertNotEqual((pn.x, pn.y), (0.0, 0.0))


class TestMultiKeyGroups(unittest.TestCase):
    def test_ii_v_i_in_three_keys_no_theory_across_boundary(self):
        net = _legacy()
        spec = function_spec(["ii", "V", "I"], "ii-V-I", "major", ["C", "G", "D"])
        proj = project_harmony_exercise(spec, net)
        proj.validate()
        self.assertEqual(len(proj.steps), 9)
        self.assertEqual(proj.counts()["groups"], 3)
        # two boundaries (C|G and G|D), each transpose_next with NO theory relation
        boundaries = [t for t in proj.transitions if t.is_group_boundary]
        self.assertEqual(len(boundaries), 2)
        for t in boundaries:
            self.assertEqual(t.sequence_relation, "transpose_next")
            self.assertIsNone(t.theory_relation)
        # no theory edge ever crosses a group boundary (validate() also enforces this)
        self.assertEqual(proj.counts()["theoryEdges"], 0)

    def test_group_indices_contiguous_and_reset(self):
        net = _legacy()
        spec = function_spec(["ii", "V", "I"], "ii-V-I", "major", ["C", "G"])
        proj = project_harmony_exercise(spec, net)
        groups = [s.group_index for s in proj.steps]
        self.assertEqual(groups, [0, 0, 0, 1, 1, 1])
        in_group = [s.index_in_group for s in proj.steps]
        self.assertEqual(in_group, [0, 1, 2, 0, 1, 2])


class TestTranspositionOrbit(unittest.TestCase):
    def test_degree_v_orbit_is_transposition_not_modulation(self):
        net = _legacy()
        proj = project_harmony_exercise(degree_spec("V", "major"), net)
        proj.validate()
        self.assertEqual(len(proj.steps), 12)
        self.assertEqual(proj.semantic_group, "transposition_orbit")
        self.assertEqual(proj.sequence_semantics, "transposition")
        self.assertTrue(all(t.sequence_relation == "transpose_next" for t in proj.transitions))
        # no modulation / resolution claim anywhere
        self.assertTrue(all(t.theory_relation is None for t in proj.transitions))


class TestQuality(unittest.TestCase):
    def test_major_quality_class_enumeration(self):
        net = _legacy()
        spec = quality_drills("major")["major"][0]
        proj = project_harmony_exercise(spec, net)
        proj.validate()
        self.assertEqual(proj.semantic_group, "quality_class")
        self.assertEqual(proj.sequence_semantics, "class_enumeration")
        self.assertTrue(all(t.theory_relation is None for t in proj.transitions))
        # every chord is a major triad
        self.assertTrue(all(s.quality == "major" for s in proj.steps))


class TestEnharmonic(unittest.TestCase):
    def test_fsharp_major_preserves_spelling_and_resolves_atlas_by_pc(self):
        net = _legacy()
        proj = project_harmony_exercise(full_key_spec("F#", "major"), net)
        proj.validate()
        self.assertIn("hn:major:F#", proj.anchor_node_ids)
        tonic = proj.step_at_index(0)
        # source spelling preserved in labels (F#, not Gb)
        self.assertEqual(tonic.tonic, "F#")
        self.assertTrue(tonic.visual_node_id.startswith("overlay:triad:F#:major:0"))
        # atlas refs resolve enharmonically (F# major -> scale:Gb:major)
        self.assertTrue(any("Gb" in r for r in tonic.atlas_refs),
                        f"expected an enharmonic Gb atlas ref, got {tonic.atlas_refs}")


class TestRepeatedChord(unittest.TestCase):
    def test_repeated_i_is_two_occurrences_one_node(self):
        net = _legacy()
        spec = function_spec(["I", "IV", "V", "I"], "I-IV-V-I", "major", ["C"])
        proj = project_harmony_exercise(spec, net)
        proj.validate()
        i_steps = [s for s in proj.steps if s.roman == "I"]
        self.assertEqual(len(i_steps), 2)
        # distinct occurrence ids...
        self.assertNotEqual(i_steps[0].occurrence_id, i_steps[1].occurrence_id)
        # ...pointing at the SAME canonical/proxy node
        self.assertEqual(i_steps[0].visual_node_id, i_steps[1].visual_node_id)
        # and only one proxy node for that identity
        proxy_ids = [n.id for n in proj.projection_nodes]
        self.assertEqual(proxy_ids.count(i_steps[0].visual_node_id), 1)


class TestNaturalMinor(unittest.TestCase):
    def test_a_minor_modes_and_functions(self):
        net = _legacy()
        proj = project_harmony_exercise(full_key_spec("A", "natural_minor"), net)
        proj.validate()
        self.assertIn("hn:minor:A", proj.anchor_node_ids)
        by_roman = {s.roman: s for s in proj.steps}
        # ii° diminished -> exact dim node
        self.assertEqual(by_roman["ii°"].mapping_status, "exact")
        self.assertEqual(by_roman["ii°"].visual_node_id, "hn:dim:B")
        # the natural-minor v (E minor) and subtonic VII (G major) are NOT dominant approximations
        self.assertEqual(by_roman["v"].mapping_status, "contextual")
        self.assertEqual(by_roman["VII"].mapping_status, "contextual")
        # modes carried through
        self.assertTrue(all(s.mode == "natural_minor" for s in proj.steps))


class TestSemanticOverride(unittest.TestCase):
    def test_override_thematic_group(self):
        net = _legacy()
        spec = function_spec(["I", "iii", "vi"], "tonic family", "major", ["C"])
        proj = project_harmony_exercise(
            spec, net, semantic_override={"thematic_group": "functional_neighbourhood",
                                          "title": "Tonic family (enumeration)"})
        proj.validate()
        self.assertEqual(proj.semantic_group, "functional_neighbourhood")
        self.assertEqual(proj.title, "Tonic family (enumeration)")


if __name__ == "__main__":
    unittest.main()
