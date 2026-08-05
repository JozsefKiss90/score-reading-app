"""Ticket 09 (G1a) — the V7 tracer bullet.

The platform's first seventh chord, end to end: the theory engine builds the
dominant-seventh tetrad, the score builder voices it, the Lab's roman gate
accepts ``V7`` (and still rejects every other not-yet-supported token), and
three drill families ship in all 12 major keys with live curriculum leaves.
"""

import unittest

from theory.diatonic_harmony import (
    build_dominant_seventh,
    generate_scale,
    note_pc,
    parse_seventh_token,
    transpose_degree_pattern,
    QUALITY_TO_INTERVAL_LAYER,
)
from harmony.exercise_spec import (
    DEFAULT_MAJOR_KEYS,
    HarmonyExerciseSpec,
    compile_exercise,
    normalise_pattern,
)


class TestSeventhToken(unittest.TestCase):
    def test_v7_is_the_only_supported_token(self):
        self.assertEqual(parse_seventh_token("V7"), 4)
        self.assertEqual(parse_seventh_token(" V7 "), 4)
        for bad in ("v7", "ii7", "V9", "V65", "V7/V", "I7", "VII7", "7", ""):
            self.assertIsNone(parse_seventh_token(bad), bad)


class TestBuildDominantSeventh(unittest.TestCase):
    def test_c_major_v7_is_g7(self):
        chord = build_dominant_seventh("C", "major")
        self.assertEqual(chord.pitches, ["G", "B", "D", "F"])
        self.assertEqual(chord.roman, "V7")
        self.assertEqual(chord.chord_symbol, "G7")
        self.assertEqual(chord.chord_quality, "dominant_seventh")
        self.assertEqual(chord.interval_layer, "M3+m3+m3")
        self.assertEqual(chord.function_label, "dominant")
        self.assertEqual(chord.degree_number, 5)

    def test_flat_side_spelling_gb_major(self):
        # Gb major spells its subdominant as Cb: Db7 = Db F Ab Cb (never B).
        chord = build_dominant_seventh("Gb", "major")
        self.assertEqual(chord.pitches, ["Db", "F", "Ab", "Cb"])
        self.assertEqual(chord.chord_symbol, "Db7")

    def test_all_twelve_major_keys(self):
        for key in DEFAULT_MAJOR_KEYS:
            chord = build_dominant_seventh(key, "major")
            self.assertEqual(chord.chord_quality, "dominant_seventh", key)
            self.assertEqual(len(chord.pitches), 4, key)
            self.assertEqual(len(chord.midi_pitches), 4, key)
            # ascending voicing
            self.assertEqual(chord.midi_pitches, sorted(chord.midi_pitches), key)
            # the seventh is a minor seventh above the root
            root_pc, seventh_pc = note_pc(chord.pitches[0]), note_pc(chord.pitches[3])
            self.assertEqual((seventh_pc - root_pc) % 12, 10, key)
            # root is scale degree 5
            scale = generate_scale(key, "major")
            self.assertEqual(note_pc(chord.pitches[0]), note_pc(scale.scale_pitches[4]), key)

    def test_natural_minor_refuses(self):
        # Natural minor's diatonic seventh on degree 5 is a minor seventh (v7),
        # not a dominant seventh; V7 in minor arrives with harmonic minor (G2).
        with self.assertRaises(ValueError):
            build_dominant_seventh("A", "natural_minor")

    def test_interval_layer_registered(self):
        self.assertEqual(QUALITY_TO_INTERVAL_LAYER["dominant_seventh"], "M3+m3+m3")

    def test_explanation_mentions_the_seventh(self):
        chord = build_dominant_seventh("C", "major")
        self.assertIn("seventh", chord.explanation_text.lower())
        self.assertIn("tritone", chord.explanation_text.lower())


class TestTransposePatternWithV7(unittest.TestCase):
    def test_v7_token_builds_the_tetrad(self):
        chords = transpose_degree_pattern(["V", "V7", "I"], "C", "major")
        self.assertEqual([len(c.pitches) for c in chords], [3, 4, 3])
        self.assertEqual(chords[0].root, chords[1].root)   # same dominant root
        self.assertEqual(chords[1].roman, "V7")

    def test_v7_token_refused_in_minor(self):
        with self.assertRaises(ValueError):
            transpose_degree_pattern(["V7", "i"], "A", "natural_minor")


class TestPatternHonesty(unittest.TestCase):
    """The trainer never silently strips a figure/seventh down to a triad."""

    def test_normalise_accepts_v7(self):
        self.assertEqual(normalise_pattern(["ii", "V7", "I"]), ["ii", "V7", "I"])

    def test_normalise_rejects_unsupported_digit_tokens(self):
        for bad in ("ii7", "V9", "I64", "ii6", "v7"):
            with self.assertRaises(ValueError, msg=bad):
                normalise_pattern([bad])

    def test_function_drill_with_v7_compiles(self):
        spec = HarmonyExerciseSpec(
            exercise_id="t_v7_i", title="V7-I", drill="function",
            mode="major", pattern=["V7", "I"], keys=["C", "G"])
        compiled = compile_exercise(spec)
        self.assertEqual(len(compiled), 4)
        self.assertEqual(len(compiled.chords[0].triad.pitches), 4)
        self.assertEqual(compiled.chords[0].triad.roman, "V7")
        self.assertEqual(len(compiled.chords[1].triad.pitches), 3)

    def test_function_drill_v7_refused_in_minor(self):
        spec = HarmonyExerciseSpec(
            exercise_id="t_v7_minor", title="bad", drill="function",
            mode="natural_minor", pattern=["V7", "i"], keys=["A"])
        with self.assertRaises(ValueError):
            spec.validate()

    def test_horizontal_degree_rejects_seventh_tokens(self):
        spec = HarmonyExerciseSpec(
            exercise_id="t_deg_v7", title="bad", drill="horizontal_degree",
            mode="major", degree="V7")
        with self.assertRaises(ValueError):
            spec.validate()


class TestMusicXMLAndPayload(unittest.TestCase):
    """The score builder voices the tetrad; grading carries 4 pitch classes."""

    def _compiled(self, render="block"):
        from harmony.exercise_spec import compile_exercise
        spec = HarmonyExerciseSpec(
            exercise_id=f"t_v7_i_{render}", title="V7-I in C", drill="function",
            render=render, mode="major", pattern=["V7", "I"], keys=["C"])
        return compile_exercise(spec)

    def test_block_measure_has_four_treble_notes_and_dominant_kind(self):
        from harmony.musicxml_builder import build_musicxml
        xml = build_musicxml(self._compiled())
        m1 = xml.split('<measure number="1">')[1].split("</measure>")[0]
        treble = m1.split("<backup>")[0]
        self.assertEqual(treble.count("<note>"), 4)
        self.assertEqual(treble.count("<chord/>"), 3)
        self.assertIn('<kind text="7">dominant</kind>', m1)
        self.assertIn('text="V7"', m1)

    def test_arpeggio_measure_has_four_quarters_and_no_rest(self):
        from harmony.musicxml_builder import build_musicxml
        xml = build_musicxml(self._compiled("arpeggio"))
        m1 = xml.split('<measure number="1">')[1].split("</measure>")[0]
        treble = m1.split("<backup>")[0]
        self.assertEqual(treble.count("<type>quarter</type>"), 4)
        self.assertNotIn("<rest/>", treble)
        # the triad measure still pads its fourth beat with a rest
        m2 = xml.split('<measure number="2">')[1].split("</measure>")[0]
        self.assertIn("<rest/>", m2.split("<backup>")[0])

    def test_payload_carries_four_pitch_classes(self):
        from harmony.musicxml_builder import build_trainer_payload
        payload = build_trainer_payload(self._compiled())
        t = payload["TARGET_CHORDS"][0]
        self.assertEqual(t["roman"], "V7")
        self.assertEqual(t["pitchClasses"], [7, 11, 2, 5])   # G B D F
        self.assertEqual(len(t["midiPitches"]), 4)
        self.assertEqual(t["quality"], "dominant_seventh")
        self.assertEqual(payload["EXPECTED_MIDI_BY_MEASURE_OR_BEAT"]["0"],
                         [7, 11, 2, 5])

    def test_arpeggio_expected_maps_four_beats(self):
        from harmony.musicxml_builder import build_trainer_payload
        payload = build_trainer_payload(self._compiled("arpeggio"))
        expected = payload["EXPECTED_MIDI_BY_MEASURE_OR_BEAT"]["0"]
        self.assertEqual(expected,
                         {"1": [7], "2": [11], "3": [2], "4": [5]})


class TestLabRomanGate(unittest.TestCase):
    """The gate accepts V7 while still rejecting every not-yet-supported token."""

    def test_gate_accepts_v7(self):
        from harmony.lab_spec import is_diatonic_roman
        self.assertTrue(is_diatonic_roman("V7"))

    def test_gate_still_rejects_unsupported_tokens(self):
        from harmony.lab_spec import is_diatonic_roman
        for bad in ("v7", "ii7", "V9", "V7/V", "V/V", "bII", "#iv", "IV7",
                    "vii°7", "I64", "Imaj7"):
            self.assertFalse(is_diatonic_roman(bad), bad)

    def test_cadence_concept_accepts_v7_block(self):
        from harmony.lab_spec import LabExperimentSpec
        spec = LabExperimentSpec(
            experiment_id="t_cad_v7", title="V7-I cadence", concept="cadence",
            mode="major", key="C major", render="block",
            parameters={"pattern": ["V7", "I"]})
        spec.validate()
        specs = spec.to_exercise_specs()
        self.assertEqual(specs[0].pattern, ["V7", "I"])

    def test_cadence_concept_rejects_v7_satb(self):
        from harmony.lab_spec import LabExperimentSpec
        spec = LabExperimentSpec(
            experiment_id="t_cad_v7_satb", title="bad", concept="cadence",
            mode="major", key="C major", render="voice_leading",
            parameters={"pattern": ["V7", "I"]})
        with self.assertRaises(ValueError):
            spec.validate()

    def test_cadence_concept_rejects_v7_in_minor(self):
        from harmony.lab_spec import LabExperimentSpec
        spec = LabExperimentSpec(
            experiment_id="t_cad_v7_min", title="bad", concept="cadence",
            mode="natural_minor", key="A minor", render="block",
            parameters={"pattern": ["V7", "i"]})
        with self.assertRaises(ValueError):
            spec.validate()


class TestTritonePolyphonicDrill(unittest.TestCase):
    """The two-voice tritone frame: bass 7̂→1̂ under upper 4̂→3̂."""

    def _spec(self):
        from harmony.curriculum import _tritone_resolution_spec
        return _tritone_resolution_spec("C")

    def test_spec_validates_and_bridges(self):
        spec = self._spec()
        spec.validate()
        inner = spec.to_exercise_specs()
        self.assertEqual(inner[0].pattern, ["V7", "I"])

    def test_measures_are_the_tritone_frame(self):
        from harmony.lab import compile_lab
        exp = compile_lab(self._spec())
        self.assertEqual(len(exp.measures), 2)
        m1, m2 = exp.measures
        # slice 1: B (7̂) + F (4̂) -- V7's tritone
        self.assertEqual(set(m1.target_pitch_classes), {11, 5})
        self.assertEqual(m1.annotation.roman, "V7")
        # slice 2: C (1̂) + E (3̂) -- resolution into I
        self.assertEqual(set(m2.target_pitch_classes), {0, 4})
        self.assertEqual(m2.annotation.roman, "I")
        # the bass rises 7̂ -> 1̂ (B3 -> C4), never falls a seventh
        self.assertEqual([n.midi for n in m1.staff2], [59])
        self.assertEqual([n.midi for n in m2.staff2], [60])

    def test_annotation_never_claims_an_atlas_triad_for_v7(self):
        from harmony.lab import compile_lab
        exp = compile_lab(self._spec())
        ann = exp.measures[0].annotation
        self.assertFalse(ann.atlas_triad_id)
        self.assertFalse(ann.atlas_degree_id)
        # the resolution measure (a plain I triad) keeps its atlas ids
        self.assertTrue(exp.measures[1].annotation.atlas_triad_id)


class TestCurriculumLeaves(unittest.TestCase):
    """Three live drill families in all 12 major keys, launchable end to end."""

    @classmethod
    def setUpClass(cls):
        from harmony.curriculum import build_curriculum
        cls.root = build_curriculum()
        cls.cat = cls.root.find("cat:sevenths")

    def test_category_exists_and_is_live(self):
        self.assertIsNotNone(self.cat)
        self.assertFalse(self.cat.reserved)
        self.assertEqual(self.cat.exercise_count, 16)   # 2 + 12 + 2

    def test_reserved_seam_named(self):
        more = self.root.find("lesson:sevenths_more")
        self.assertIsNotNone(more)
        self.assertTrue(more.reserved)

    def test_all_twelve_keys_covered_per_family(self):
        for gid, expect_lab in (("group:sevenths_add7", False),
                                ("group:sevenths_tritone", True),
                                ("group:sevenths_v7_i", False)):
            grp = self.root.find(gid)
            self.assertIsNotNone(grp, gid)
            keys = set()
            for lf in grp.leaves():
                for es in lf.lab_spec.to_exercise_specs():
                    keys.update(es.keys or [es.key.split()[0]])
            self.assertEqual(len(keys), 12, gid)

    def test_every_leaf_compiles_renders_and_grades(self):
        from harmony.exercise_spec import compile_exercise
        from harmony.musicxml_builder import build_exercise
        for lf in self.cat.leaves():
            for es in lf.lab_spec.to_exercise_specs():
                compiled = compile_exercise(es)
                xml, payload = build_exercise(compiled)
                self.assertIn("score-partwise", xml, lf.id)
                self.assertTrue(payload["TARGET_CHORDS"], lf.id)
                # every V7 target grades four pitch classes via MIDI
                for t in payload["TARGET_CHORDS"]:
                    if t["roman"] == "V7":
                        self.assertEqual(len(t["pitchClasses"]), 4, lf.id)

    def test_atlas_refs_never_claim_a_triad_for_v7(self):
        from harmony.atlas import build_atlas, triad_id
        atlas = build_atlas()
        v7_group = self.root.find("group:sevenths_v7_i")
        for lf in v7_group.leaves():
            for nid in lf.atlas_nodes:
                self.assertIsNotNone(atlas.node(nid), (lf.id, nid))
            # V7 must not land on the V TRIAD node that merely shares its root
            # (only I's triad node is claimed, via the resolution chord).
            for es in lf.lab_spec.to_exercise_specs():
                for key in (es.keys or []):
                    self.assertNotIn(triad_id(key, "major", 4),
                                     lf.atlas_nodes, (lf.id, key))


class TestGraphSceneHonesty(unittest.TestCase):
    """A V7 marker is a `seventh` entity and never claims a triad node."""

    def _v7_scene(self):
        from harmony.graph_scene_generators import build_functional_progression_scene
        spec = HarmonyExerciseSpec(
            exercise_id="t_scene_v7", title="V7-I in G", drill="function",
            mode="major", pattern=["V7", "I"], keys=["G"])
        return build_functional_progression_scene(spec)

    def test_progression_scene_types_v7_as_seventh(self):
        scene = self._v7_scene()
        scene.validate()
        v7_nodes = [n for n in scene.nodes if n.roman == "V7"]
        self.assertEqual(len(v7_nodes), 1)
        node = v7_nodes[0]
        self.assertEqual(node.entity_type, "seventh")
        self.assertEqual(node.quality, "dominant_seventh")
        self.assertEqual(len(node.chord_tones), 4)
        self.assertEqual(node.canonical_refs, ())    # no Atlas triad claimed
        # the resolution I keeps its canonical triad ref
        i_node = next(n for n in scene.nodes if n.roman == "I")
        self.assertTrue(i_node.canonical_refs)

    def test_progression_occurrence_carries_seventh(self):
        scene = self._v7_scene()
        occ = scene.occurrence_at(0)
        self.assertEqual(occ.entity_type, "seventh")
        self.assertEqual(occ.roman, "V7")

    def test_polyphonic_tritone_scene_is_honest(self):
        from harmony.curriculum import _tritone_resolution_spec
        from harmony.graph_scene_generators import build_voice_leading_scene
        scene = build_voice_leading_scene(_tritone_resolution_spec("C"), poly=True)
        scene.validate()
        v7 = next(n for n in scene.nodes if n.roman == "V7")
        self.assertEqual(v7.entity_type, "seventh")
        self.assertEqual(v7.canonical_refs, ())

    def test_router_routes_v7_drills(self):
        from harmony.graph_scene_router import GraphSceneRequest, decide_graph_scene
        spec = HarmonyExerciseSpec(
            exercise_id="t_route_v7", title="V7-I in C", drill="function",
            mode="major", pattern=["V7", "I"], keys=["C"])
        decision = decide_graph_scene(GraphSceneRequest(exercise_spec=spec))
        self.assertEqual(decision.status, "supported")
        self.assertEqual(decision.scene_type, "functional_progression")


if __name__ == "__main__":
    unittest.main()
