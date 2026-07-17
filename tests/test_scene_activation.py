"""Scene activation + two-level role tests on REAL generator output (plan sections 11.2-11.6).

Complements test_harmonic_roles.py (the pure model) by asserting the built GraphScenes carry the
role fields, the honest activation maps (family / context / structure-edge per occurrence), the
scene-type-aware layer defaults, and that the Network's broad family never overwrites the Atlas's
specific scale-degree role.
"""

import unittest

from harmony.atlas import full_key_spec, function_spec, degree_spec
from harmony.graph_scene_generators import build_exercise_scene


def _layers(scene):
    return {l.id: l for l in scene.layer_definitions}


class TestFullKeyActivation(unittest.TestCase):
    """Plan section 11.2: per sequence index, the right chord + the right broad family light."""

    # (sequence index -> (roman, expected broad family, internal family key for the family node id))
    EXPECT = {
        0: ("I", "tonic_related", "tonic"),
        1: ("ii", "predominant", "predominant"),
        2: ("iii", "tonic_related", "tonic"),
        3: ("IV", "predominant", "predominant"),
        4: ("V", "dominant", "dominant"),
        5: ("vi", "tonic_related", "tonic"),
        6: ("vii°", "dominant", "dominant"),
    }

    def setUp(self):
        self.scene = build_exercise_scene("diatonic_key_field", full_key_spec("C", "major"))
        self.by_id = {n.id: n for n in self.scene.nodes}

    def test_current_chord_and_active_family_per_index(self):
        for idx, (roman, broad, internal) in self.EXPECT.items():
            occ = self.scene.occurrence_at(idx)
            self.assertIsNotNone(occ, f"occurrence {idx} present")
            self.assertEqual(occ.roman, roman, f"index {idx} roman")
            node = self.by_id[occ.node_id]
            # the concrete chord carries the two-level role as SEPARATE fields (they may coincide
            # in value for ii/V, but specific_role and broad_function_family are distinct fields).
            self.assertEqual(node.broad_function_family, broad, f"index {idx} broad family")
            self.assertTrue(node.specific_role, f"index {idx} has a specific role")
            # the activation lights the RIGHT family node (from the member_of_function edge)
            fam_id = f"hn:function:major:{internal}"
            self.assertIsNotNone(occ.activation)
            self.assertIn(fam_id, occ.activation.family_node_ids,
                          f"index {idx}: family {fam_id} must be active")

    def test_membership_edge_and_key_context_activate(self):
        occ = self.scene.occurrence_at(2)          # Em / iii
        act = occ.activation
        # the member_of_function edge is a STRUCTURE-edge activation (not theory motion)
        self.assertTrue(act.structure_edge_ids)
        for eid in act.structure_edge_ids:
            edge = next(e for e in self.scene.edges if e.id == eid)
            self.assertEqual(edge.relation, "member_of_function")
        # the key anchor is a CONTEXT activation, and it is a key node (never a chord)
        self.assertTrue(act.context_node_ids)
        for cid in act.context_node_ids:
            self.assertEqual(self.by_id[cid].entity_type, "key")

    def test_family_node_is_not_a_chord_occurrence(self):
        # the family node must never carry an occurrence (it is secondary context, not the chord)
        fam_ids = {n.id for n in self.scene.nodes if n.entity_type == "function"}
        for occ in self.scene.occurrence_map:
            self.assertNotIn(occ.node_id, fam_ids)

    def test_family_nodes_are_renamed(self):
        labels = {n.broad_function_family: n.label
                  for n in self.scene.nodes if n.entity_type == "function"}
        self.assertEqual(labels["tonic_related"], "Tonic-related family")
        self.assertEqual(labels["predominant"], "Predominant family")
        self.assertEqual(labels["dominant"], "Dominant family")


class TestLayerDefaults(unittest.TestCase):
    """Plan section 11.3: scene-type-aware layer labels + defaults."""

    def test_diatonic_key_field_layers(self):
        scene = build_exercise_scene("diatonic_key_field", full_key_spec("C", "major"))
        ls = _layers(scene)
        self.assertTrue(ls["context"].default_visible)
        self.assertTrue(ls["structure"].default_visible)
        self.assertTrue(ls["sequence"].default_visible)
        self.assertEqual(ls["sequence"].label, "Drill order")
        # the theory layer is the honest "possible functional motions", OFF by default
        self.assertIn("theory", ls)
        self.assertFalse(ls["theory"].default_visible)
        self.assertEqual(ls["theory"].label, "Possible functional motions")

    def test_functional_progression_layers(self):
        scene = build_exercise_scene(
            "functional_progression", function_spec(["I", "IV", "V", "I"], "cad", "major", ["C"]))
        ls = _layers(scene)
        self.assertTrue(ls["context"].default_visible)
        self.assertTrue(ls["sequence"].default_visible)
        self.assertIn("theory", ls)
        self.assertTrue(ls["theory"].default_visible)
        self.assertEqual(ls["theory"].label, "Active harmonic motion")

    def test_degree_and_quality_have_no_theory_layer(self):
        deg = build_exercise_scene("degree_transposition", degree_spec("V", "major"))
        self.assertNotIn("theory", _layers(deg))
        self.assertEqual(_layers(deg)["sequence"].label, "Transposition order")
        # a quality drill (same-quality triads across keys)
        from harmony.exercise_spec import _quality_specs
        qspec = next(s for s in _quality_specs("major") if s.quality == "major")
        qual = build_exercise_scene("triad_quality_class", qspec)
        self.assertNotIn("theory", _layers(qual))
        self.assertEqual(_layers(qual)["sequence"].label, "Classification order")


class TestDetailFollow(unittest.TestCase):
    """Plan section 11.4: the detail payload distinguishes specific role from broad family."""

    def test_em_detail_is_mediant_not_tonic(self):
        scene = build_exercise_scene("diatonic_key_field", full_key_spec("C", "major"))
        d = scene.occurrence_at(2).detail
        self.assertEqual(d["specificRole"], "mediant")
        self.assertEqual(d["broadFamily"], "tonic_related")
        self.assertEqual(d["broadFamilyLabel"], "Tonic-related family")

    def test_f_detail_is_subdominant_predominant(self):
        scene = build_exercise_scene("diatonic_key_field", full_key_spec("C", "major"))
        d = scene.occurrence_at(3).detail
        self.assertEqual(d["specificRole"], "subdominant")
        self.assertEqual(d["broadFamily"], "predominant")

    def test_g_resolves_to_next_in_progression(self):
        scene = build_exercise_scene(
            "functional_progression", function_spec(["I", "IV", "V", "I"], "cad", "major", ["C"]))
        g = next(o for o in scene.occurrence_map if o.roman == "V")
        self.assertEqual(g.next_theory_relation, "resolves_to")
        # and the opening vs. arrival tonic are distinguished (plan section 9)
        tonics = [o for o in scene.occurrence_map if o.roman == "I"]
        self.assertEqual(tonics[0].occurrence_role, "opening")
        self.assertEqual(tonics[-1].occurrence_role, "arrival")


class TestAtlasConsistency(unittest.TestCase):
    """Plan section 11.6: the Network adds a broad family WITHOUT overwriting the specific role."""

    def test_specific_role_preserved_alongside_broad_family(self):
        scene = build_exercise_scene("diatonic_key_field", full_key_spec("C", "major"))
        by_roman = {n.roman: n for n in scene.nodes if n.entity_type in ("triad", "diminished")}
        # iii: Atlas-specific role stays the mediant; Network ADDS the tonic-related family
        self.assertEqual(by_roman["iii"].scale_degree_name, "mediant")
        self.assertEqual(by_roman["iii"].specific_role, "mediant")
        self.assertEqual(by_roman["iii"].broad_function_family, "tonic_related")
        self.assertNotEqual(by_roman["iii"].specific_role, by_roman["iii"].broad_function_family)
        # IV: subdominant is NOT overwritten by "predominant"
        self.assertEqual(by_roman["IV"].scale_degree_name, "subdominant")
        self.assertEqual(by_roman["IV"].specific_role, "subdominant")
        self.assertEqual(by_roman["IV"].broad_function_family, "predominant")


if __name__ == "__main__":
    unittest.main()
