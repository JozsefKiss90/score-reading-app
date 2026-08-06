"""Ticket 13 (G2a) — harmonic minor: a real V in minor.

The engine's harmonic-minor mode flows end to end: pattern drills with the
raised leading tone compile in all 12 minor keys, the score builder renders
the accidental, MCQ roman options match the new degree vocabulary, the role
model asserts a strong dominant, the functional-equivalence network stops
refusing minor, and the curriculum ships the A/B lesson plus V–i / vii°–i /
i–iv–V–i drills.  Natural-minor behaviour is pinned unchanged throughout.
"""

import unittest

from harmony.exercise_spec import (
    DEFAULT_MINOR_KEYS,
    HarmonyExerciseSpec,
    compile_exercise,
    degree_labels_for_mode,
)


def _function_spec(pattern, keys, mode="harmonic_minor", **kw):
    return HarmonyExerciseSpec(
        exercise_id="t_hm_" + "_".join(pattern).replace("°", "o"),
        title="t", drill="function", mode=mode,
        pattern=list(pattern), keys=list(keys), **kw)


class TestHarmonicMinorSpecs(unittest.TestCase):
    def test_v_i_compiles_with_major_dominant(self):
        compiled = compile_exercise(_function_spec(["V", "i"], ["A"]))
        self.assertEqual([c.triad.roman for c in compiled.chords], ["V", "i"])
        self.assertEqual([c.triad.chord_symbol for c in compiled.chords],
                         ["E", "Am"])
        self.assertEqual(compiled.chords[0].triad.pitches, ["E", "G#", "B"])

    def test_vii_dim_i_compiles(self):
        compiled = compile_exercise(_function_spec(["vii°", "i"], ["A"]))
        self.assertEqual([c.triad.roman for c in compiled.chords],
                         ["vii°", "i"])
        self.assertEqual(compiled.chords[0].triad.pitches, ["G#", "B", "D"])
        self.assertEqual(compiled.chords[0].triad.scale_degree_name,
                         "leading-tone")

    def test_i_iv_v_i_compiles_in_all_12_minor_keys(self):
        for key in DEFAULT_MINOR_KEYS:
            compiled = compile_exercise(
                _function_spec(["i", "iv", "V", "i"], [key]))
            self.assertEqual(
                [c.triad.chord_quality for c in compiled.chords],
                ["minor", "minor", "major", "minor"],
                f"{key}: i–iv–V–i must end through a MAJOR dominant")

    def test_natural_minor_v_still_minor(self):
        compiled = compile_exercise(
            _function_spec(["v", "i"], ["A"], mode="natural_minor"))
        self.assertEqual(compiled.chords[0].triad.roman, "v")
        self.assertEqual(compiled.chords[0].triad.chord_quality, "minor")

    def test_degree_labels_for_harmonic_minor(self):
        self.assertEqual(degree_labels_for_mode("harmonic_minor"),
                         ["i", "ii°", "III+", "iv", "V", "VI", "vii°"])
        # other modes unchanged
        self.assertEqual(degree_labels_for_mode("natural_minor"),
                         ["i", "ii°", "III", "iv", "v", "VI", "VII"])

    def test_full_key_key_string_does_not_downgrade_mode(self):
        spec = HarmonyExerciseSpec(
            exercise_id="t_hm_fullkey", title="t", drill="full_key",
            mode="harmonic_minor", key="A minor")
        compiled = compile_exercise(spec)
        self.assertEqual([c.triad.roman for c in compiled.chords],
                         ["i", "ii°", "III+", "iv", "V", "VI", "vii°"])

    def test_v7_pattern_valid_in_harmonic_minor(self):
        compiled = compile_exercise(_function_spec(["V7", "i"], ["A"]))
        self.assertEqual(compiled.chords[0].triad.pitches,
                         ["E", "G#", "B", "D"])

    def test_v7_pattern_still_refused_in_natural_minor(self):
        with self.assertRaises(ValueError):
            _function_spec(["V7", "i"], ["A"], mode="natural_minor").validate()

    def test_quality_drills_unreserved_by_g2b(self):
        # Ticket 14 (plan G2b) lifted the reservation: the III+ / vii°7
        # quality drills validate in harmonic minor (compile assertions live
        # in tests/test_melodic_minor.py) and still refuse everywhere else.
        for quality in ("augmented", "diminished_seventh"):
            spec = HarmonyExerciseSpec(
                exercise_id=f"t_hm_{quality}", title="t", drill="quality",
                mode="harmonic_minor", quality=quality, keys=["A"])
            spec.validate()   # must not raise
            for mode in ("major", "natural_minor"):
                bad = HarmonyExerciseSpec(
                    exercise_id=f"t_{mode}_{quality}", title="t",
                    drill="quality", mode=mode, quality=quality, keys=["C"])
                with self.assertRaises(ValueError, msg=f"{quality}/{mode}"):
                    bad.validate()


class TestHarmonicMinorMcqPayload(unittest.TestCase):
    def test_mcq_roman_answer_is_always_an_option(self):
        from harmony.musicxml_builder import build_trainer_payload
        spec = _function_spec(["i", "iv", "V", "i"], ["A"],
                              answer_mode="mcq")
        payload = build_trainer_payload(compile_exercise(spec))
        for t in payload["TARGET_CHORDS"]:
            self.assertIn(t["roman"], t["mcq"]["options"], t["roman"])

    def test_raised_seventh_renders_an_accidental(self):
        from harmony.musicxml_builder import build_musicxml
        compiled = compile_exercise(_function_spec(["V", "i"], ["A"]))
        xml = build_musicxml(compiled)
        self.assertIn("<accidental>sharp</accidental>", xml)
        self.assertIn("<alter>1</alter>", xml)


class TestHarmonicMinorRoles(unittest.TestCase):
    """Mode-aware dominant strength: v weak → V strong when the mode says so."""

    def test_harmonic_minor_v_is_a_strong_primary_dominant(self):
        from harmony.harmonic_roles import role_profile
        p = role_profile("harmonic_minor", 4, roman="V")
        self.assertEqual(p.broad_family, "dominant")
        self.assertEqual(p.family_membership_type, "primary")
        self.assertEqual(p.family_membership_strength, "strong")
        self.assertFalse(p.contextual)
        self.assertEqual(p.mode, "harmonic_minor")

    def test_harmonic_minor_vii_is_a_strong_leading_tone(self):
        from harmony.harmonic_roles import role_profile
        p = role_profile("harmonic_minor", 6, roman="vii°")
        self.assertEqual(p.broad_family, "dominant")
        self.assertEqual(p.family_membership_type, "leading_tone")
        self.assertEqual(p.family_membership_strength, "strong")
        self.assertEqual(p.scale_degree_name, "leading-tone")

    def test_harmonic_minor_mediant_is_contextual(self):
        from harmony.harmonic_roles import role_profile
        p = role_profile("harmonic_minor", 2, roman="III+")
        self.assertTrue(p.contextual)

    def test_natural_minor_dominant_still_weak(self):
        from harmony.harmonic_roles import role_profile
        p = role_profile("natural_minor", 4, roman="v")
        self.assertEqual(p.family_membership_type, "contextual")
        self.assertEqual(p.family_membership_strength, "context_dependent")
        self.assertTrue(p.contextual)

    def test_role_profile_for_harmonic_minor_triad(self):
        from theory.diatonic_harmony import generate_diatonic_triads
        from harmony.harmonic_roles import role_profile_for_triad
        v = generate_diatonic_triads("A", "harmonic_minor")[4]
        p = role_profile_for_triad(v)
        self.assertEqual(p.family_membership_strength, "strong")
        self.assertEqual(p.roman, "V")


class TestHarmonicMinorEcho(unittest.TestCase):
    def test_native_harmonic_minor_drill_is_echo_eligible(self):
        from harmony.echo_drills import echo_variant, is_echo_eligible
        from harmony.curriculum import _wrap_native
        spec = _function_spec(["V", "i"], ["A", "E"])
        lab = _wrap_native(spec)
        self.assertTrue(is_echo_eligible(lab))
        twin = echo_variant(spec)
        self.assertEqual(twin.presentation, "echo")


class TestHarmonicMinorScenes(unittest.TestCase):
    """Every G2a leaf routes to a scene that renders the RAISED chords honestly."""

    def test_v_i_scene_shows_a_major_dominant(self):
        from harmony.curriculum import build_curriculum
        from harmony.graph_scene_router import (
            GraphSceneRequest, build_graph_scene, decide_graph_scene)
        root = build_curriculum()
        lf = root.find("ex:drill_hminor_ab_bare_b_A")
        req = GraphSceneRequest(curriculum_node_id=lf.id, lab_spec=lf.lab_spec)
        self.assertEqual(decide_graph_scene(req).status, "supported")
        scene = build_graph_scene(req)
        scene.validate()   # includes the chord-never-on-a-key-node gate
        self.assertEqual(scene.scene_type, "functional_progression")
        by_label = {n.label: n for n in scene.nodes}
        self.assertEqual(by_label["E"].quality, "major")    # V, not v
        self.assertEqual(by_label["Am"].quality, "minor")

    def test_all_g2a_leaves_build_valid_scenes(self):
        from harmony.curriculum import build_curriculum
        from harmony.graph_scene_router import (
            GraphSceneRequest, build_graph_scene)
        root = build_curriculum()
        for lf in root.find("cat:harmonic_minor").leaves():
            scene = build_graph_scene(GraphSceneRequest(
                curriculum_node_id=lf.id, lab_spec=lf.lab_spec))
            scene.validate()
            self.assertNotEqual(scene.scene_type, "unsupported", lf.id)


class TestHarmonicMinorCurriculum(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from harmony.curriculum import build_curriculum
        cls.root = build_curriculum()

    def test_category_ships_twelve_leaves(self):
        cat = self.root.find("cat:harmonic_minor")
        self.assertIsNotNone(cat)
        self.assertFalse(cat.reserved)
        self.assertEqual(cat.exercise_count, 12)

    def test_ab_lesson_pairs_natural_then_harmonic(self):
        grp = self.root.find("group:hm_ab_bare")
        modes = [es.mode for lf in grp.leaves()
                 for es in lf.lab_spec.to_exercise_specs()]
        self.assertEqual(modes, ["natural_minor", "harmonic_minor"])
        grp2 = self.root.find("group:hm_ab_context")
        patterns = [es.pattern for lf in grp2.leaves()
                    for es in lf.lab_spec.to_exercise_specs()]
        self.assertEqual(patterns, [["i", "iv", "v", "i"],
                                    ["i", "iv", "V", "i"]])

    def test_drills_cover_all_12_minor_keys(self):
        from harmony.exercise_spec import DEFAULT_MINOR_KEYS
        for gid in ("group:hm_v_i", "group:hm_viio_i", "group:hm_i_iv_v_i"):
            keys = set()
            for lf in self.root.find(gid).leaves():
                for es in lf.lab_spec.to_exercise_specs():
                    self.assertEqual(es.mode, "harmonic_minor", lf.id)
                    keys.update(es.keys)
            self.assertEqual(keys, set(DEFAULT_MINOR_KEYS), gid)

    def test_leaves_get_echo_twins(self):
        from harmony.echo_drills import is_echo_eligible
        cat = self.root.find("cat:harmonic_minor")
        for lf in cat.leaves():
            self.assertTrue(is_echo_eligible(lf.lab_spec), lf.id)

    def test_atlas_refs_never_claim_raised_chords(self):
        # The raised-leading-tone chords (V / vii°) must not land on
        # natural-minor degree or triad nodes; i and iv may (exact match).
        cat = self.root.find("cat:harmonic_minor")
        for lf in cat.leaves():
            for ref in lf.atlas_nodes:
                self.assertNotIn(":harmonic_minor", ref, lf.id)
                if ref.startswith("degree:"):
                    self.assertNotIn(":V", ref, lf.id)
                    self.assertNotIn(":vii", ref, lf.id)

    def test_natural_minor_cadence_catalogue_unchanged(self):
        # The subtonic lesson and the modal v-i stay exactly as they were.
        from harmony.curriculum import _CADENCE_CATALOG
        minor = [(tuple(t), c) for t, _l, m, c, _f in _CADENCE_CATALOG
                 if m == "natural_minor"]
        self.assertIn((("v", "i"), "authentic"), minor)
        self.assertIn((("VII", "i"), "subtonic"), minor)
        cadences = next(c for c in self.root.children if c.title == "Cadences")
        # 26 pre-G3; ticket 16 adds 4 catalogue variants (ii–V / IV–V, block +
        # SATB) and 35 taxonomy leaves (PAC/IAC, halves, 6/4, reflex, orbits).
        self.assertEqual(cadences.exercise_count, 65)


if __name__ == "__main__":
    unittest.main(verbosity=2)
