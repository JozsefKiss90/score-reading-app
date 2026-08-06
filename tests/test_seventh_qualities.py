"""Ticket 10 (G1b) — all five diatonic seventh qualities.

The engine builds and spells every diatonic seventh chord in the supported
modes (major and natural minor), the quality drill widens to seventh
qualities, ii7–V7–I lands in all 12 major keys, and a hear-a-seventh
quality-ID drill answers by MCQ (Mm7 / mm7 / MM7 / ø7 / °7).

The fully diminished seventh (°7) is *classified* (label, interval layer)
but no diatonic scale in the supported modes contains one — it arrives with
harmonic minor (plan G2), so nothing here ever builds or sounds it.
"""

import unittest

from theory.diatonic_harmony import (
    build_dominant_seventh,
    build_seventh_chord,
    generate_diatonic_sevenths,
    parse_seventh_token,
    seventh_tokens_for_mode,
    transpose_degree_pattern,
    QUALITY_TO_INTERVAL_LAYER,
    SEVENTH_DEGREE_TOKENS,
    SEVENTH_QUALITY_LABELS,
)


class TestSeventhTokenVocabulary(unittest.TestCase):
    """14 tokens: one per degree per mode, spelled as the engine builds them."""

    def test_major_tokens(self):
        self.assertEqual(
            seventh_tokens_for_mode("major"),
            ["Imaj7", "ii7", "iii7", "IVmaj7", "V7", "vi7", "viiø7"])

    def test_minor_tokens(self):
        self.assertEqual(
            seventh_tokens_for_mode("natural_minor"),
            ["i7", "iiø7", "IIImaj7", "iv7", "v7", "VImaj7", "VII7"])

    def test_every_token_parses_to_its_degree(self):
        for mode in ("major", "natural_minor"):
            for i, tok in enumerate(seventh_tokens_for_mode(mode)):
                self.assertEqual(parse_seventh_token(tok), i, tok)

    def test_table_carries_exactly_the_fourteen_tokens(self):
        expected = set(seventh_tokens_for_mode("major")) | set(
            seventh_tokens_for_mode("natural_minor"))
        self.assertEqual(set(SEVENTH_DEGREE_TOKENS), expected)

    def test_unsupported_tokens_still_rejected(self):
        # I7 would claim a dominant quality the tonic seventh does not have;
        # vii°7 would mislabel the HALF-diminished leading-tone seventh.
        for bad in ("I7", "IV7", "vii°7", "ii°7", "V9", "V65", "ii6",
                    "V7/V", "Imaj", "maj7", "7", ""):
            self.assertIsNone(parse_seventh_token(bad), bad)


class TestGenerateDiatonicSevenths(unittest.TestCase):
    def test_c_major_all_seven(self):
        chords = generate_diatonic_sevenths("C", "major")
        self.assertEqual([c.roman for c in chords],
                         ["Imaj7", "ii7", "iii7", "IVmaj7", "V7", "vi7", "viiø7"])
        self.assertEqual([c.chord_quality for c in chords],
                         ["major_seventh", "minor_seventh", "minor_seventh",
                          "major_seventh", "dominant_seventh", "minor_seventh",
                          "half_diminished_seventh"])
        self.assertEqual([c.chord_symbol for c in chords],
                         ["Cmaj7", "Dm7", "Em7", "Fmaj7", "G7", "Am7", "Bø7"])
        self.assertEqual(chords[0].pitches, ["C", "E", "G", "B"])
        self.assertEqual(chords[6].pitches, ["B", "D", "F", "A"])
        for c in chords:
            self.assertEqual(len(c.pitches), 4, c.roman)
            self.assertEqual(len(c.midi_pitches), 4, c.roman)
            self.assertEqual(c.midi_pitches, sorted(c.midi_pitches), c.roman)

    def test_a_natural_minor_all_seven(self):
        chords = generate_diatonic_sevenths("A", "natural_minor")
        self.assertEqual([c.roman for c in chords],
                         ["i7", "iiø7", "IIImaj7", "iv7", "v7", "VImaj7", "VII7"])
        self.assertEqual([c.chord_quality for c in chords],
                         ["minor_seventh", "half_diminished_seventh",
                          "major_seventh", "minor_seventh", "minor_seventh",
                          "major_seventh", "dominant_seventh"])
        # the subtonic seventh genuinely IS a dominant seventh (G7)
        self.assertEqual(chords[6].pitches, ["G", "B", "D", "F"])
        self.assertEqual(chords[6].chord_symbol, "G7")

    def test_interval_layers(self):
        chords = generate_diatonic_sevenths("C", "major")
        self.assertEqual(chords[0].interval_layer, "M3+m3+M3")   # Imaj7
        self.assertEqual(chords[1].interval_layer, "m3+M3+m3")   # ii7
        self.assertEqual(chords[4].interval_layer, "M3+m3+m3")   # V7
        self.assertEqual(chords[6].interval_layer, "m3+m3+M3")   # viiø7

    def test_flat_side_spelling(self):
        # Gb major's IVmaj7 is built on Cb: Cb Eb Gb Bb (never B natural).
        chords = generate_diatonic_sevenths("Gb", "major")
        self.assertEqual(chords[3].pitches, ["Cb", "Eb", "Gb", "Bb"])
        self.assertEqual(chords[3].chord_symbol, "Cbmaj7")

    def test_sharp_side_spelling(self):
        # F# major's leading-tone seventh is built on E#: E# G# B D#.
        chords = generate_diatonic_sevenths("F#", "major")
        self.assertEqual(chords[6].pitches, ["E#", "G#", "B", "D#"])
        self.assertEqual(chords[6].chord_symbol, "E#ø7")

    def test_quality_registry_complete(self):
        self.assertEqual(QUALITY_TO_INTERVAL_LAYER["major_seventh"], "M3+m3+M3")
        self.assertEqual(QUALITY_TO_INTERVAL_LAYER["minor_seventh"], "m3+M3+m3")
        self.assertEqual(QUALITY_TO_INTERVAL_LAYER["half_diminished_seventh"],
                         "m3+m3+M3")
        self.assertEqual(QUALITY_TO_INTERVAL_LAYER["diminished_seventh"],
                         "m3+m3+m3")

    def test_mcq_labels(self):
        self.assertEqual(SEVENTH_QUALITY_LABELS, {
            "dominant_seventh": "Mm7",
            "minor_seventh": "mm7",
            "major_seventh": "MM7",
            "half_diminished_seventh": "ø7",
            "diminished_seventh": "°7",
        })


class TestBuildSeventhChord(unittest.TestCase):
    def test_ii7_in_c_major(self):
        chord = build_seventh_chord("ii7", "C", "major")
        self.assertEqual(chord.pitches, ["D", "F", "A", "C"])
        self.assertEqual(chord.chord_symbol, "Dm7")
        self.assertEqual(chord.chord_quality, "minor_seventh")
        self.assertEqual(chord.function_label, "predominant")

    def test_v7_matches_build_dominant_seventh(self):
        self.assertEqual(build_seventh_chord("V7", "Eb", "major"),
                         build_dominant_seventh("Eb", "major"))

    def test_unknown_token_raises(self):
        with self.assertRaises(ValueError):
            build_seventh_chord("I7", "C", "major")

    def test_wrong_mode_raises(self):
        # The token names a chord the OTHER mode owns: never hand back a
        # different chord under the requested label.
        for tok, key, mode in (("V7", "A", "natural_minor"),
                               ("v7", "C", "major"),
                               ("ii7", "A", "natural_minor"),
                               ("iiø7", "C", "major"),
                               ("Imaj7", "A", "natural_minor")):
            with self.assertRaises(ValueError, msg=(tok, mode)):
                build_seventh_chord(tok, key, mode)

    def test_every_token_builds_in_all_twelve_keys_of_its_mode(self):
        from harmony.exercise_spec import DEFAULT_MAJOR_KEYS, DEFAULT_MINOR_KEYS
        for mode, keys in (("major", DEFAULT_MAJOR_KEYS),
                           ("natural_minor", DEFAULT_MINOR_KEYS)):
            for tok in seventh_tokens_for_mode(mode):
                for key in keys:
                    chord = build_seventh_chord(tok, key, mode)
                    self.assertEqual(chord.roman, tok, (tok, key))
                    self.assertNotEqual(chord.chord_quality, "unknown", (tok, key))


class TestTransposePatternWithSevenths(unittest.TestCase):
    def test_ii7_v7_i_in_c(self):
        chords = transpose_degree_pattern(["ii7", "V7", "I"], "C", "major")
        self.assertEqual([c.chord_symbol for c in chords], ["Dm7", "G7", "C"])
        self.assertEqual([len(c.pitches) for c in chords], [4, 4, 3])

    def test_minor_tokens_transpose_in_minor(self):
        chords = transpose_degree_pattern(["iiø7", "v7", "i"], "A", "natural_minor")
        self.assertEqual([c.chord_symbol for c in chords], ["Bø7", "Em7", "Am"])

    def test_major_token_refused_in_minor(self):
        with self.assertRaises(ValueError):
            transpose_degree_pattern(["ii7", "V7", "I"], "A", "natural_minor")


class TestSeventhQualityDrill(unittest.TestCase):
    """drill="quality" widened to seventh qualities (mirrors the triad drill)."""

    def _spec(self, quality, keys, mode="major"):
        from harmony.exercise_spec import HarmonyExerciseSpec
        return HarmonyExerciseSpec(
            exercise_id=f"t_q_{quality}", title=quality, drill="quality",
            mode=mode, quality=quality, keys=keys)

    def test_dominant_seventh_drill_all_keys(self):
        from harmony.exercise_spec import compile_exercise, DEFAULT_MAJOR_KEYS
        compiled = compile_exercise(self._spec("dominant_seventh",
                                               DEFAULT_MAJOR_KEYS))
        self.assertEqual(len(compiled), 12)
        for c in compiled.chords:
            self.assertEqual(c.triad.roman, "V7")
            self.assertEqual(len(c.triad.pitches), 4)

    def test_minor_seventh_drill_three_per_key(self):
        from harmony.exercise_spec import compile_exercise
        compiled = compile_exercise(self._spec("minor_seventh",
                                               ["C", "G", "D", "A"]))
        self.assertEqual(len(compiled), 12)
        self.assertEqual([c.triad.roman for c in compiled.chords[:3]],
                         ["ii7", "iii7", "vi7"])

    def test_half_diminished_drill_in_minor(self):
        from harmony.exercise_spec import compile_exercise
        compiled = compile_exercise(self._spec(
            "half_diminished_seventh", ["A", "E"], mode="natural_minor"))
        self.assertEqual([c.triad.roman for c in compiled.chords],
                         ["iiø7", "iiø7"])
        self.assertEqual(compiled.chords[0].triad.chord_symbol, "Bø7")

    def test_diminished_seventh_drill_refused(self):
        # No diatonic °7 exists in the supported modes (harmonic minor, G2).
        with self.assertRaises(ValueError):
            self._spec("diminished_seventh", ["C"]).validate()

    def test_augmented_still_refused(self):
        with self.assertRaises(ValueError):
            self._spec("augmented", ["C"]).validate()


class TestFunctionDrillModeHonesty(unittest.TestCase):
    def _spec(self, pattern, mode, keys):
        from harmony.exercise_spec import HarmonyExerciseSpec
        return HarmonyExerciseSpec(
            exercise_id="t_fn", title="t", drill="function",
            mode=mode, pattern=pattern, keys=keys)

    def test_ii7_v7_i_compiles_in_major(self):
        from harmony.exercise_spec import compile_exercise
        compiled = compile_exercise(self._spec(["ii7", "V7", "I"], "major", ["C"]))
        self.assertEqual([c.triad.chord_symbol for c in compiled.chords],
                         ["Dm7", "G7", "C"])

    def test_minor_vocabulary_compiles_in_minor(self):
        from harmony.exercise_spec import compile_exercise
        compiled = compile_exercise(
            self._spec(["iiø7", "VII7", "i"], "natural_minor", ["A"]))
        self.assertEqual([c.triad.chord_symbol for c in compiled.chords],
                         ["Bø7", "G7", "Am"])

    def test_major_tokens_refused_in_minor(self):
        with self.assertRaises(ValueError):
            self._spec(["ii7", "V7", "I"], "natural_minor", ["A"]).validate()

    def test_minor_tokens_refused_in_major(self):
        with self.assertRaises(ValueError):
            self._spec(["v7", "i7"], "major", ["C"]).validate()


class TestEchoMcqSpec(unittest.TestCase):
    """The aural quality-ID drill: presentation="echo" + answer_mode="mcq"."""

    def _spec(self, **kw):
        from harmony.exercise_spec import HarmonyExerciseSpec
        base = dict(exercise_id="t_ear", title="t", drill="function",
                    mode="major", pattern=["ii7", "V7", "I"], keys=["C"])
        base.update(kw)
        return HarmonyExerciseSpec(**base)

    def test_echo_with_mcq_now_validates(self):
        self._spec(presentation="echo", answer_mode="mcq").validate()

    def test_echo_with_card_still_refused(self):
        with self.assertRaises(ValueError):
            self._spec(presentation="echo", answer_mode="card").validate()

    def test_mcq_focus_quality_requires_mcq(self):
        self._spec(answer_mode="mcq", mcq_focus="quality").validate()
        with self.assertRaises(ValueError):
            self._spec(answer_mode="midi", mcq_focus="quality").validate()

    def test_unknown_mcq_focus_refused(self):
        with self.assertRaises(ValueError):
            self._spec(answer_mode="mcq", mcq_focus="colour").validate()

    def test_echo_variant_still_refuses_id_answer_modes(self):
        from harmony.echo_drills import echo_variant
        with self.assertRaises(ValueError):
            echo_variant(self._spec(answer_mode="mcq"))


class TestQualityMcqPayload(unittest.TestCase):
    def _payload(self, pattern, mode="major", keys=("C",), **kw):
        from harmony.exercise_spec import HarmonyExerciseSpec, compile_exercise
        from harmony.musicxml_builder import build_trainer_payload
        spec = HarmonyExerciseSpec(
            exercise_id="t_mcq_q", title="t", drill="function", mode=mode,
            pattern=list(pattern), keys=list(keys), answer_mode="mcq", **kw)
        return build_trainer_payload(compile_exercise(spec))

    def test_seventh_targets_offer_the_five_quality_labels(self):
        payload = self._payload(
            ["Imaj7", "ii7", "iii7", "IVmaj7", "V7", "vi7", "viiø7"],
            mcq_focus="quality", presentation="echo")
        self.assertEqual(payload["ANSWER_MODE"], "mcq")
        self.assertEqual(payload["PRESENTATION"], "echo")
        answers = set()
        for t in payload["TARGET_CHORDS"]:
            block = t["mcq"]
            self.assertEqual(block["options"], ["Mm7", "mm7", "MM7", "ø7", "°7"])
            self.assertIn(block["answer"], block["options"])
            answers.add(block["answer"])
        # the four diatonic qualities all occur; °7 is only ever a distractor
        self.assertEqual(answers, {"Mm7", "mm7", "MM7", "ø7"})

    def test_triad_targets_offer_triad_qualities(self):
        payload = self._payload(["ii", "V", "I"], mcq_focus="quality")
        for t in payload["TARGET_CHORDS"]:
            self.assertEqual(t["mcq"]["options"],
                             ["major", "minor", "diminished", "augmented"])
            self.assertEqual(t["mcq"]["answer"], t["quality"])

    def test_default_focus_still_asks_the_roman(self):
        payload = self._payload(["ii7", "V7", "I"])
        for t in payload["TARGET_CHORDS"]:
            self.assertEqual(t["mcq"]["answer"], t["roman"])


class TestMusicXMLSeventhKinds(unittest.TestCase):
    def test_kinds_for_each_quality(self):
        from harmony.exercise_spec import HarmonyExerciseSpec, compile_exercise
        from harmony.musicxml_builder import build_musicxml
        spec = HarmonyExerciseSpec(
            exercise_id="t_kinds", title="t", drill="function", mode="major",
            pattern=["Imaj7", "ii7", "V7", "viiø7"], keys=["C"])
        xml = build_musicxml(compile_exercise(spec))
        self.assertIn('<kind text="maj7">major-seventh</kind>', xml)
        self.assertIn('<kind text="m7">minor-seventh</kind>', xml)
        self.assertIn('<kind text="7">dominant</kind>', xml)
        self.assertIn('<kind text="ø7">half-diminished</kind>', xml)


class TestLabSpecSeventhTokens(unittest.TestCase):
    def _spec(self, pattern, mode="major", key="C major"):
        from harmony.lab_spec import LabExperimentSpec
        return LabExperimentSpec(
            experiment_id="t_lab_7", title="t", concept="cadence",
            mode=mode, key=key, render="block",
            parameters={"pattern": pattern})

    def test_cadence_accepts_ii7_v7_i_block(self):
        spec = self._spec(["ii7", "V7", "I"])
        spec.validate()
        self.assertEqual(spec.to_exercise_specs()[0].pattern, ["ii7", "V7", "I"])

    def test_cadence_accepts_minor_vocabulary_in_minor(self):
        self._spec(["iiø7", "VII7", "i"], mode="natural_minor",
                   key="A minor").validate()

    def test_cadence_rejects_major_tokens_in_minor(self):
        with self.assertRaises(ValueError):
            self._spec(["ii7", "V7", "i"], mode="natural_minor",
                       key="A minor").validate()

    def test_satb_render_still_refuses_sevenths(self):
        from harmony.lab_spec import LabExperimentSpec
        spec = LabExperimentSpec(
            experiment_id="t_lab_7_satb", title="t", concept="cadence",
            mode="major", key="C major", render="voice_leading",
            parameters={"pattern": ["ii7", "V7", "I"]})
        with self.assertRaises(ValueError):
            spec.validate()


class TestCurriculumG1b(unittest.TestCase):
    """The G1b leaves: quality drills, ii7–V7–I in 12 keys, ear quality-ID."""

    @classmethod
    def setUpClass(cls):
        from harmony.curriculum import build_curriculum
        cls.root = build_curriculum()
        cls.cat = cls.root.find("cat:sevenths")

    def test_category_grew_with_g1b_leaves(self):
        self.assertIsNotNone(self.cat)
        self.assertFalse(self.cat.reserved)
        # 16 (G1a) + 16 (G1b: 7 quality + 6 ii7–V7–I + 3 ear) + 24 (G1c,
        # ticket 11 — pinned in tests/test_figured_sevenths.py)
        self.assertEqual(self.cat.exercise_count, 56)

    def test_g1b_lessons_live(self):
        for lid in ("lesson:seventh_qualities", "lesson:sevenths_ii_v_i"):
            node = self.root.find(lid)
            self.assertIsNotNone(node, lid)
            self.assertFalse(node.reserved, lid)

    def test_quality_group_covers_the_four_diatonic_qualities(self):
        grp = self.root.find("group:sevenths_quality")
        self.assertIsNotNone(grp)
        qualities = set()
        keys_by_quality = {}
        for lf in grp.leaves():
            for es in lf.lab_spec.to_exercise_specs():
                self.assertEqual(es.drill, "quality")
                qualities.add(es.quality)
                keys_by_quality.setdefault(es.quality, set()).update(es.keys)
        self.assertEqual(qualities,
                         {"dominant_seventh", "major_seventh",
                          "minor_seventh", "half_diminished_seventh"})
        for q, keys in keys_by_quality.items():
            self.assertEqual(len(keys), 12, q)

    def test_ii7_v7_i_in_all_twelve_keys_both_renders(self):
        for gid, render in (("group:sevenths_ii7_v7_i_block", "block"),
                            ("group:sevenths_ii7_v7_i_arp", "arpeggio")):
            grp = self.root.find(gid)
            self.assertIsNotNone(grp, gid)
            keys = set()
            for lf in grp.leaves():
                for es in lf.lab_spec.to_exercise_specs():
                    self.assertEqual(es.render, render, gid)
                    self.assertEqual(es.pattern, ["ii7", "V7", "I"], gid)
                    keys.update(es.keys)
            self.assertEqual(len(keys), 12, gid)

    def test_ear_leaves_are_echo_mcq_quality(self):
        grp = self.root.find("group:sevenths_quality_ear")
        self.assertIsNotNone(grp)
        leaves = list(grp.leaves())
        self.assertEqual(len(leaves), 3)
        for lf in leaves:
            for es in lf.lab_spec.to_exercise_specs():
                self.assertEqual(es.presentation, "echo", lf.id)
                self.assertEqual(es.answer_mode, "mcq", lf.id)
                self.assertEqual(es.mcq_focus, "quality", lf.id)
                # all seven diatonic sevenths of one key: every hearable
                # quality occurs, and no answer repeats trivially forever
                self.assertEqual(len(es.pattern), 7, lf.id)

    def test_every_new_leaf_compiles_renders_and_grades(self):
        from harmony.exercise_spec import compile_exercise
        from harmony.musicxml_builder import build_exercise
        for gid in ("group:sevenths_quality", "group:sevenths_quality_ear",
                    "group:sevenths_ii7_v7_i_block",
                    "group:sevenths_ii7_v7_i_arp"):
            for lf in self.root.find(gid).leaves():
                for es in lf.lab_spec.to_exercise_specs():
                    compiled = compile_exercise(es)
                    xml, payload = build_exercise(compiled)
                    self.assertIn("score-partwise", xml, lf.id)
                    for t in payload["TARGET_CHORDS"]:
                        if any(ch.isdigit() for ch in t["roman"]):
                            self.assertEqual(len(t["pitchClasses"]), 4, lf.id)

    def test_atlas_refs_valid_and_never_claim_triads_for_tetrads(self):
        from harmony.atlas import build_atlas, triad_id
        atlas = build_atlas()
        # pure-tetrad drills (quality / ear): no triad node at all
        for gid in ("group:sevenths_quality", "group:sevenths_quality_ear"):
            for lf in self.root.find(gid).leaves():
                for nid in lf.atlas_nodes:
                    self.assertIsNotNone(atlas.node(nid), (lf.id, nid))
                    self.assertFalse(nid.startswith("triad:"), (lf.id, nid))
        # ii7–V7–I: the resolution I is a real triad and may claim its node;
        # the ii and V TRIAD nodes (which merely share the tetrads' roots)
        # must never be claimed.
        for lf in self.root.find("group:sevenths_ii7_v7_i_block").leaves():
            for nid in lf.atlas_nodes:
                self.assertIsNotNone(atlas.node(nid), (lf.id, nid))
            for es in lf.lab_spec.to_exercise_specs():
                for key in (es.keys or []):
                    self.assertNotIn(triad_id(key, "major", 1),
                                     lf.atlas_nodes, (lf.id, key))
                    self.assertNotIn(triad_id(key, "major", 4),
                                     lf.atlas_nodes, (lf.id, key))

    def test_half_diminished_leaf_claims_the_leading_tone_degree(self):
        # viiø7 projects onto the vii° DEGREE node (the degree it is built
        # on), never a triad/quality node — the _degree_roman honesty rule.
        grp = self.root.find("group:sevenths_quality")
        half_dim = [lf for lf in grp.leaves()
                    if any(es.quality == "half_diminished_seventh"
                           for es in lf.lab_spec.to_exercise_specs())]
        self.assertTrue(half_dim)
        from harmony.atlas import degree_id
        for lf in half_dim:
            self.assertIn(degree_id("major", "vii°"), lf.atlas_nodes, lf.id)


class TestQualityClassSceneHonesty(unittest.TestCase):
    """A seventh-quality drill's scene: `seventh` entities, no triad claims."""

    def _scene(self, quality="minor_seventh", keys=("C", "G", "D", "A")):
        from harmony.exercise_spec import HarmonyExerciseSpec
        from harmony.graph_scene_generators import build_quality_class_scene
        spec = HarmonyExerciseSpec(
            exercise_id="t_scene_q7", title="mm7 drill", drill="quality",
            mode="major", quality=quality, keys=list(keys))
        return build_quality_class_scene(spec)

    def test_instances_are_seventh_entities_without_canonical_refs(self):
        scene = self._scene()
        scene.validate()
        instances = [n for n in scene.nodes if n.entity_role == "instance"]
        self.assertTrue(instances)
        for n in instances:
            self.assertEqual(n.entity_type, "seventh", n.id)
            self.assertEqual(n.quality, "minor_seventh", n.id)
            self.assertEqual(len(n.chord_tones), 4, n.id)
            self.assertEqual(n.canonical_refs, (), n.id)

    def test_anchor_never_claims_the_triad_quality_atlas_node(self):
        # The Atlas has quality nodes for TRIAD qualities only; a seventh
        # quality anchor must not borrow one, and must not say "triads".
        scene = self._scene()
        anchor = next(n for n in scene.nodes if n.entity_role == "reference")
        self.assertEqual(anchor.canonical_refs, ())
        self.assertNotIn("triad", anchor.label.lower())
        self.assertNotIn("_", anchor.label)

    def test_triad_quality_scene_unchanged(self):
        scene = self._scene(quality="major", keys=("C", "G", "D", "A"))
        anchor = next(n for n in scene.nodes if n.entity_role == "reference")
        self.assertTrue(anchor.canonical_refs)    # triad quality node exists
        instances = [n for n in scene.nodes if n.entity_role == "instance"]
        self.assertTrue(all(n.entity_type == "triad" for n in instances))

    def test_router_supports_seventh_quality_drills(self):
        from harmony.exercise_spec import HarmonyExerciseSpec
        from harmony.graph_scene_router import (GraphSceneRequest,
                                                decide_graph_scene)
        spec = HarmonyExerciseSpec(
            exercise_id="t_route_q7", title="t", drill="quality",
            mode="major", quality="dominant_seventh", keys=["C", "G"])
        decision = decide_graph_scene(GraphSceneRequest(exercise_spec=spec))
        self.assertEqual(decision.status, "supported")
        self.assertEqual(decision.scene_type, "triad_quality_class")


if __name__ == "__main__":
    unittest.main()
