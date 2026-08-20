"""Ticket 17 (G5a) — applied chords: "Spot the intruder".

The platform's first chromatic chords: the theory engine builds applied
dominants (``V/x``, ``V7/x``) with correct chromatic spelling, the Lab's
roman gate widens from diatonic-only to a supported-roman allowlist, and
the flagship spot/resolve drill ships in C major with live curriculum
leaves under the previously reserved secondary-dominants stub.
"""

import unittest

from theory.diatonic_harmony import (
    applied_tokens_for_mode,
    build_applied_dominant,
    parse_applied_token,
    transpose_degree_pattern,
)
from harmony.exercise_spec import (
    HarmonyExerciseSpec,
    compile_exercise,
    normalise_pattern,
)


class TestParseAppliedToken(unittest.TestCase):
    def test_applied_dominant_tokens_parse(self):
        self.assertEqual(parse_applied_token("V7/V"), ("V7", "V"))
        self.assertEqual(parse_applied_token("V/V"), ("V", "V"))
        self.assertEqual(parse_applied_token(" V7/IV "), ("V7", "IV"))
        self.assertEqual(parse_applied_token("V7/ii"), ("V7", "ii"))

    def test_non_applied_tokens_return_none(self):
        # (vii°7/x joined the vocabulary with ticket 19 — tests/test_applied_ramps.py)
        for tok in ("V7", "V", "ii", "viiø7", "V7/", "/V", "V7/V/V",
                    "ii7/V", "V9/V", "V7/bII", "V7/2", ""):
            self.assertIsNone(parse_applied_token(tok), tok)


class TestBuildAppliedDominant(unittest.TestCase):
    def test_all_major_mode_targets_in_c(self):
        # Worked examples: the applied chord is the dominant seventh of the
        # tonicised degree, spelled from that degree's own scale.
        expected = {
            "V7/ii": ["A", "C#", "E", "G"],
            "V7/iii": ["B", "D#", "F#", "A"],
            "V7/IV": ["C", "E", "G", "Bb"],
            "V7/V": ["D", "F#", "A", "C"],
            "V7/vi": ["E", "G#", "B", "D"],
        }
        for token, pitches in expected.items():
            chord = build_applied_dominant(token, "C", "major")
            self.assertEqual(chord.pitches, pitches, token)
            self.assertEqual(chord.roman, token)
            self.assertEqual(chord.chord_quality, "dominant_seventh", token)

    def test_applied_triad_head(self):
        chord = build_applied_dominant("V/V", "C", "major")
        self.assertEqual(chord.pitches, ["D", "F#", "A"])
        self.assertEqual(chord.roman, "V/V")
        self.assertEqual(chord.chord_quality, "major")
        self.assertEqual(chord.chord_symbol, "D")

    def test_flat_side_spelling(self):
        # V7/IV in Ab major tonicises Db: Ab7 = Ab C Eb Gb (never F#).
        chord = build_applied_dominant("V7/IV", "Ab", "major")
        self.assertEqual(chord.pitches, ["Ab", "C", "Eb", "Gb"])

    def test_tonic_target_refused(self):
        # V7/I is just the home dominant seventh.
        with self.assertRaises(ValueError):
            build_applied_dominant("V7/I", "C", "major")

    def test_diminished_target_refused(self):
        # A diminished triad cannot act as a momentary tonic.
        with self.assertRaises(ValueError):
            build_applied_dominant("V7/vii°", "C", "major")

    def test_target_roman_must_match_mode_exactly(self):
        # Natural minor's degree-5 triad is v, so V7/V refuses there --
        # same exact-match honesty as the seventh-token gate.
        with self.assertRaises(ValueError) as ctx:
            build_applied_dominant("V7/V", "A", "natural_minor")
        self.assertIn("V7/v", str(ctx.exception))

    def test_minor_mode_applied_dominant(self):
        # V7/iv in A minor: the dominant of D minor is A7 (with C#, the
        # raised leading tone of D).
        chord = build_applied_dominant("V7/iv", "A", "natural_minor")
        self.assertEqual(chord.pitches, ["A", "C#", "E", "G"])

    def test_explanation_names_the_chromatic_intruder(self):
        chord = build_applied_dominant("V7/V", "C", "major")
        self.assertIn("F#", chord.explanation_text)
        self.assertIn("leading tone of G", chord.explanation_text)
        self.assertIn("dominant of the dominant", chord.explanation_text)

    def test_v7_of_v_in_c_major_is_d7(self):
        chord = build_applied_dominant("V7/V", "C", "major")
        self.assertEqual(chord.pitches, ["D", "F#", "A", "C"])
        self.assertEqual(chord.roman, "V7/V")
        self.assertEqual(chord.chord_symbol, "D7")
        self.assertEqual(chord.chord_quality, "dominant_seventh")
        self.assertEqual(chord.interval_layer, "M3+m3+m3")
        self.assertEqual(chord.key, "C major")
        # ascending root-position voicing
        self.assertEqual(chord.midi_pitches, sorted(chord.midi_pitches))


class TestAppliedTokensForMode(unittest.TestCase):
    def test_major_vocabulary_is_derived_from_the_builder(self):
        # Five tonicisable degrees (ii iii IV V vi), two dominant heads each;
        # I is the home dominant and vii° cannot be a momentary tonic.  (The
        # applied leading-tone head arrived with ticket 19.)
        from theory.diatonic_harmony import APPLIED_DOMINANT_HEADS
        toks = applied_tokens_for_mode("major", heads=APPLIED_DOMINANT_HEADS)
        self.assertEqual(len(toks), 10)
        self.assertIn("V7/V", toks)
        self.assertIn("V/ii", toks)
        self.assertNotIn("V7/I", toks)
        self.assertNotIn("V7/vii°", toks)

    def test_natural_minor_uses_its_own_spellings(self):
        toks = applied_tokens_for_mode("natural_minor")
        self.assertIn("V7/iv", toks)
        self.assertIn("V7/v", toks)
        self.assertNotIn("V7/V", toks)
        self.assertNotIn("V7/ii°", toks)


class TestTrainerPatternGate(unittest.TestCase):
    """normalise_pattern accepts applied tokens; everything else still refuses."""

    def test_normalise_accepts_applied_tokens(self):
        pattern = ["I", "vi", "V7/V", "V", "I"]
        self.assertEqual(normalise_pattern(pattern), pattern)

    def test_normalise_still_rejects_unsupported_slash_tokens(self):
        for bad in ("V9/V", "V65/V", "viiø7/V", "ii7/V", "V7/bII", "V7/V/V"):
            with self.assertRaises(ValueError, msg=bad):
                normalise_pattern([bad])

    def test_function_drill_with_applied_compiles(self):
        spec = HarmonyExerciseSpec(
            exercise_id="t_applied", title="Spot", drill="function",
            mode="major", pattern=["I", "vi", "V7/V", "V", "I"], keys=["C"])
        compiled = compile_exercise(spec)
        self.assertEqual(len(compiled), 5)
        self.assertEqual(compiled.chords[2].triad.pitches,
                         ["D", "F#", "A", "C"])
        self.assertEqual(compiled.chords[2].triad.roman, "V7/V")

    def test_function_drill_applied_mode_dishonesty_refused_at_validate(self):
        # V7/V is not honest in natural minor (its dominant triad is v);
        # validate refuses before any key is compiled.
        with self.assertRaises(ValueError) as ctx:
            HarmonyExerciseSpec(
                exercise_id="t_bad", title="Bad", drill="function",
                mode="natural_minor", pattern=["i", "V7/V", "v"], keys=["A"])\
                .validate()
        self.assertIn("V7/v", str(ctx.exception))


class TestLabRomanGate(unittest.TestCase):
    """The Lab gate widens from diatonic-only to a supported-roman allowlist."""

    def test_supported_roman_accepts_applied_tokens(self):
        from harmony.lab_spec import is_supported_roman
        for tok in ("V7/V", "V7/IV", "V/ii", "V7/vi"):
            self.assertTrue(is_supported_roman(tok), tok)

    def test_supported_roman_keeps_the_diatonic_vocabulary(self):
        from harmony.lab_spec import is_supported_roman
        for tok in ("I", "ii", "vii°", "III+", "V7", "viiø7", "vii°7"):
            self.assertTrue(is_supported_roman(tok), tok)

    def test_supported_roman_still_rejects_chromatic_tokens(self):
        from harmony.lab_spec import is_supported_roman
        for bad in ("bII", "#iv", "N6", "Ger65", "V9/V", "viiø7/V",
                    "V7/bII", "V9", "ii65"):
            self.assertFalse(is_supported_roman(bad), bad)

    def test_cadence_concept_still_refuses_applied_tokens_for_now(self):
        # The SATB / cadence render paths have no applied voicing yet: the
        # cadence concept refuses loudly and names the applied_chord concept.
        from harmony.lab_spec import LabExperimentSpec
        spec = LabExperimentSpec(
            experiment_id="t_cad_applied", title="Cadence with applied",
            concept="cadence", key="C", mode="major", render="block",
            parameters={"pattern": ["I", "V7/V", "V", "I"]})
        with self.assertRaises(ValueError) as ctx:
            spec.validate()
        self.assertIn("applied_chord", str(ctx.exception))


class TestTransposePatternWithApplied(unittest.TestCase):
    def test_flagship_progression_builds(self):
        # The ticket's worked example: I–vi–V7/V–V–I in C major.
        chords = transpose_degree_pattern(
            ["I", "vi", "V7/V", "V", "I"], "C", "major")
        self.assertEqual([c.roman for c in chords],
                         ["I", "vi", "V7/V", "V", "I"])
        self.assertEqual(chords[2].pitches, ["D", "F#", "A", "C"])
        # the resolution target follows the intruder
        self.assertEqual(chords[3].root, "G")

    def test_dishonest_applied_token_still_refused(self):
        with self.assertRaises(ValueError):
            transpose_degree_pattern(["I", "V7/vii°", "I"], "C", "major")


def _applied_spec(stages, render="block", progression=None, mode="major",
                  key="C major"):
    from harmony.lab_spec import LabExperimentSpec
    return LabExperimentSpec(
        experiment_id="t_applied_lab", title="Spot the intruder",
        concept="applied_chord", key=key, mode=mode, render=render,
        parameters={
            "progression": progression or ["I", "vi", "V7/V", "V", "I"],
            "stages": list(stages),
        })


class TestAppliedChordConcept(unittest.TestCase):
    def test_ticket_spec_shape_validates(self):
        _applied_spec(["spot", "resolve"]).validate()

    def test_all_three_stages_validate(self):
        # The ear stage was reserved by this ticket and landed with 19 / G5c
        # (its own coverage lives in tests/test_applied_ramps.py).
        _applied_spec(["spot", "resolve", "ear"]).validate()

    def test_unknown_stage_refused(self):
        with self.assertRaises(ValueError):
            _applied_spec(["listen"]).validate()

    def test_progression_needs_exactly_one_applied_token(self):
        with self.assertRaises(ValueError):
            _applied_spec(["spot"],
                          progression=["I", "IV", "V", "I"]).validate()
        with self.assertRaises(ValueError):
            _applied_spec(
                ["spot"],
                progression=["I", "V7/IV", "IV", "V7/V", "V"]).validate()

    def test_applied_token_must_resolve_to_its_target(self):
        # The chord after the intruder must be the tonicised degree: the
        # spot explanation and the resolve stage both promise it.
        with self.assertRaises(ValueError):
            _applied_spec(["spot"],
                          progression=["I", "V7/V", "vi", "V", "I"]).validate()
        with self.assertRaises(ValueError):
            _applied_spec(["spot"],
                          progression=["I", "vi", "V", "I", "V7/V"]).validate()

    def test_spot_stage_emits_a_spot_drill(self):
        specs = _applied_spec(["spot"]).to_exercise_specs()
        self.assertEqual(len(specs), 1)
        s = specs[0]
        self.assertEqual(s.answer_mode, "spot")
        self.assertEqual(s.pattern, ["I", "vi", "V7/V", "V", "I"])
        self.assertEqual(s.keys, ["C"])
        self.assertEqual(s.render, "block")
        self.assertEqual(s.drill, "function")

    def test_resolve_stage_emits_the_intruder_pair(self):
        specs = _applied_spec(["resolve"]).to_exercise_specs()
        self.assertEqual(len(specs), 1)
        s = specs[0]
        self.assertEqual(s.answer_mode, "midi")
        self.assertEqual(s.pattern, ["V7/V", "V"])
        self.assertEqual(s.render, "block")

    def test_resolve_arpeggio_variant(self):
        specs = _applied_spec(["resolve"], render="arpeggio").to_exercise_specs()
        self.assertEqual(specs[0].render, "arpeggio")

    def test_spot_refuses_arpeggio_render(self):
        with self.assertRaises(ValueError):
            _applied_spec(["spot"], render="arpeggio").validate()

    def test_both_stages_emit_in_order(self):
        specs = _applied_spec(["spot", "resolve"]).to_exercise_specs()
        self.assertEqual([s.answer_mode for s in specs], ["spot", "midi"])
        self.assertNotEqual(specs[0].exercise_id, specs[1].exercise_id)


class TestSpotAnswerModeSpec(unittest.TestCase):
    def _spot(self, **kw):
        base = dict(
            exercise_id="t_spot", title="Spot", drill="function",
            mode="major", pattern=["I", "vi", "V7/V", "V", "I"], keys=["C"],
            answer_mode="spot")
        base.update(kw)
        return HarmonyExerciseSpec(**base)

    def test_valid_spot_spec(self):
        self._spot().validate()

    def test_spot_requires_an_applied_intruder(self):
        with self.assertRaises(ValueError):
            self._spot(pattern=["I", "IV", "V", "I"]).validate()

    def test_spot_requires_a_single_key(self):
        with self.assertRaises(ValueError):
            self._spot(keys=["C", "G"]).validate()

    def test_spot_can_be_echoed_as_the_ear_stage(self):
        # Ticket 17 refused it (no veiled answer surface existed); ticket 19
        # gave the hunt a bar-position strip, so the veil is now legal —
        # unlike the card list, which still is not.
        self._spot(presentation="echo").validate()


class TestSpotPayload(unittest.TestCase):
    def setUp(self):
        from harmony.musicxml_builder import build_exercise
        spec = _applied_spec(["spot"]).to_exercise_specs()[0]
        self.xml, self.payload = build_exercise(compile_exercise(spec))

    def test_payload_marks_the_intruder(self):
        self.assertEqual(self.payload["ANSWER_MODE"], "spot")
        self.assertEqual(self.payload["SPOT_INDEX"], 2)
        targets = self.payload["TARGET_CHORDS"]
        self.assertTrue(targets[2].get("intruder"))
        self.assertEqual(targets[2].get("chromaticPcs"), [6])   # F#
        self.assertTrue(targets[2].get("romanHidden"))
        for i in (0, 1, 3, 4):
            self.assertFalse(targets[i].get("intruder"), i)
            self.assertFalse(targets[i].get("romanHidden"), i)

    def test_musicxml_hides_the_intruder_roman_only(self):
        # The intruder measure shows its chord symbol (D7) but no Roman
        # numeral — the roman IS the answer; diatonic measures keep theirs.
        self.assertNotIn('text="V7/V"', self.xml)
        self.assertIn('text="vi"', self.xml)
        self.assertIn("<root-step>D</root-step>", self.xml)


class TestResolvePayload(unittest.TestCase):
    def setUp(self):
        from harmony.musicxml_builder import build_trainer_payload
        spec = _applied_spec(["resolve"]).to_exercise_specs()[0]
        self.payload = build_trainer_payload(compile_exercise(spec))

    def test_applied_target_carries_the_tritone(self):
        t = self.payload["TARGET_CHORDS"][0]
        self.assertEqual(t.get("tritonePcs"), [6, 0])           # F# + C

    def test_resolution_target_carries_the_resolution(self):
        res = self.payload["TARGET_CHORDS"][1].get("tritoneResolution")
        self.assertIsNotNone(res)
        self.assertEqual(res["fromPcs"], [6, 0])                # F# + C
        self.assertEqual(res["fromMeasure"], 0)                 # in the D7 bar
        self.assertEqual(res["toPcs"], [7, 11])                 # G + B
        self.assertIn("F#→G", res["text"])

    def test_diatonic_drills_carry_no_tritone_fields(self):
        from harmony.musicxml_builder import build_trainer_payload
        spec = HarmonyExerciseSpec(
            exercise_id="t_plain", title="Plain", drill="function",
            mode="major", pattern=["ii", "V7", "I"], keys=["C"])
        payload = build_trainer_payload(compile_exercise(spec))
        for t in payload["TARGET_CHORDS"]:
            self.assertNotIn("tritoneResolution", t)
            self.assertNotIn("intruder", t)
        self.assertNotIn("SPOT_INDEX", payload)


class TestAppliedSceneRouting(unittest.TestCase):
    """Applied chords claim their own scene — and refuse every diatonic one.

    Ticket 17 shipped the drills with the router failing closed; ticket 18
    (plan G5b) gave them the secondary-dominant scene.  What must never change
    is the second half: projecting D7 onto a diatonic graph would land it on a
    node it does not match, so no other scene may claim it.  The scene's own
    contract is covered in ``tests/test_secondary_dominant_network.py``.
    """

    def test_applied_lab_spec_routes_to_the_secondary_dominant_scene(self):
        from harmony.graph_scene_router import (
            GraphSceneRequest, decide_graph_scene)
        decision = decide_graph_scene(
            GraphSceneRequest(lab_spec=_applied_spec(["spot"])))
        self.assertEqual(decision.status, "supported")
        self.assertEqual(decision.scene_type, "secondary_dominant_path")

    def test_native_applied_function_drill_routes_too(self):
        from harmony.graph_scene_router import (
            GraphSceneRequest, decide_graph_scene)
        spec = HarmonyExerciseSpec(
            exercise_id="t_applied_fn", title="Applied", drill="function",
            mode="major", pattern=["V7/V", "V"], keys=["C"])
        decision = decide_graph_scene(GraphSceneRequest(exercise_spec=spec))
        self.assertEqual(decision.scene_type, "secondary_dominant_path")

    def test_no_diatonic_scene_may_claim_an_applied_chord(self):
        from harmony.graph_scene_router import (
            GraphSceneRequest, decide_graph_scene)
        spec = HarmonyExerciseSpec(
            exercise_id="t_applied_fn2", title="Applied", drill="function",
            mode="major", pattern=["V7/V", "V"], keys=["C"])
        for hint in ("functional_progression", "diatonic_key_field",
                     "cadence_resolution"):
            decision = decide_graph_scene(GraphSceneRequest(
                exercise_spec=spec, source_metadata={"graph_scene_type": hint}))
            self.assertEqual(decision.scene_type, "secondary_dominant_path", hint)

    def test_build_returns_the_applied_scene(self):
        from harmony.graph_scene_router import (
            GraphSceneRequest, build_graph_scene)
        scene = build_graph_scene(
            GraphSceneRequest(lab_spec=_applied_spec(["spot"])))
        self.assertIsNotNone(scene)
        self.assertEqual(scene.scene_type, "secondary_dominant_path")

    def test_diatonic_function_drills_still_route(self):
        from harmony.graph_scene_router import (
            GraphSceneRequest, decide_graph_scene)
        spec = HarmonyExerciseSpec(
            exercise_id="t_plain_fn", title="Plain", drill="function",
            mode="major", pattern=["ii", "V", "I"], keys=["C"])
        decision = decide_graph_scene(GraphSceneRequest(exercise_spec=spec))
        self.assertEqual(decision.status, "supported")
        self.assertEqual(decision.scene_type, "functional_progression")


class TestAppliedCurriculum(unittest.TestCase):
    """The reserved secondary-dominants stub goes live (12 G5a leaves)."""

    @classmethod
    def setUpClass(cls):
        from harmony.curriculum import build_curriculum
        cls.root = build_curriculum()
        cls.lesson = cls.root.find("lesson:adv_secondary")

    def test_secondary_lesson_is_live(self):
        self.assertIsNotNone(self.lesson)
        self.assertEqual(self.lesson.kind, "lesson")
        self.assertFalse(self.lesson.reserved)
        self.assertEqual(self.lesson.exercise_count, 12)

    def test_advanced_category_is_no_longer_reserved(self):
        cat = self.root.find("cat:advanced")
        self.assertFalse(cat.reserved)
        self.assertEqual(cat.kind, "category")
        # its other topics stay honestly reserved
        for lid in ("lesson:adv_modal", "lesson:adv_jazz"):
            node = self.root.find(lid)
            self.assertTrue(node.reserved, lid)

    def test_flagship_leaf_matches_the_plan(self):
        leaf = self.root.find("ex:applied_spot_v7_of_v_c")
        self.assertIsNotNone(leaf)
        spec = leaf.lab_spec
        self.assertEqual(spec.concept, "applied_chord")
        self.assertEqual(list(spec.parameters["progression"]),
                         ["I", "vi", "V7/V", "V", "I"])
        inner = spec.to_exercise_specs()[0]
        self.assertEqual(inner.answer_mode, "spot")

    def test_every_leaf_compiles_and_stages_split(self):
        leaves = [n for n in self.lesson.walk() if n.kind == "exercise"]
        self.assertEqual(len(leaves), 12)
        spot = resolve = arp = 0
        for leaf in leaves:
            specs = leaf.lab_spec.to_exercise_specs()
            self.assertEqual(len(specs), 1, leaf.id)   # one stage per leaf
            s = specs[0]
            if s.answer_mode == "spot":
                spot += 1
            elif s.render == "arpeggio":
                arp += 1
            else:
                resolve += 1
        self.assertEqual((spot, resolve, arp), (4, 4, 4))

    def test_leaf_pages_build_without_error(self):
        from harmony.curriculum_explanations import exercise_page
        leaf = self.root.find("ex:applied_spot_v7_of_v_c")
        page = exercise_page(leaf)
        self.assertTrue(page["musicTheory"])
        self.assertTrue(page["practiceAdvice"])
        self.assertTrue(page["commonMistakes"])

    def test_leaf_count_fingerprint(self):
        # 351 (ticket 16) + 12 applied leaves (this ticket) = 363, + 17 ramp
        # leaves (ticket 19, pinned in tests/test_applied_ramps.py) = 380,
        # + 1 technique tracer (piano-technique ticket 01, pinned in
        # tests/test_technique.py) = 381, + 24 arpeggio runs (piano-technique
        # ticket 06, pinned in tests/test_technique_arpeggio.py) = 405,
        # + 7 Chord Progression Foundations leaves (pinned in
        # tests/test_progression_foundations.py) = 412; the JS mirror is
        # pinned in tests/curriculum_node_test.js.
        self.assertEqual(self.root.exercise_count, 412)


if __name__ == "__main__":
    unittest.main()
