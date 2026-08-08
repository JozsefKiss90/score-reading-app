"""Ticket 19 (G5c) — applied-chord ramps + the ear stage.

Ticket 17 shipped one rung of plan §7's difficulty ramp: ``V7/x`` in C major,
fixed positions, visual only.  This slice ships the whole ramp —

* **position**: the intruder is placed anywhere in a derived progression;
* **target set**: the applied *leading-tone* chords (``vii°7/x``) join the
  applied dominants;
* **key distance**: leaves step outward by circle-of-fifths distance;
* **visual → ear**: the ear stage plays the progression with the notation
  veiled; the learner clicks the *position* of the chromatic chord and then
  names the degree it tonicised (the follow-up MCQ);

plus the "dominant chains" performance drill (E7–A7–D7–G7–C).
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

from theory.diatonic_harmony import (
    APPLIED_HEADS,
    APPLIED_DOMINANT_HEADS,
    applied_target_options,
    applied_tokens_for_mode,
    build_applied_chord,
    build_applied_dominant,
    note_pc,
    parse_applied_token,
    transpose_degree_pattern,
)
from harmony.applied_ramp import (
    applied_progression,
    dominant_chain,
    keys_by_fifths_distance,
)
from harmony.echo_drills import echo_variant, is_echo_eligible
from harmony.exercise_spec import HarmonyExerciseSpec, compile_exercise
from harmony.graph_scene_router import (
    GraphSceneRequest,
    build_graph_scene,
    decide_graph_scene,
)
from harmony.lab_spec import APPLIED_STAGES, LabExperimentSpec
from harmony.musicxml_builder import build_trainer_payload


# ---------------------------------------------------------------------------
# 1. Theory — applied leading-tone chords (vii°7/x)
# ---------------------------------------------------------------------------

class TestAppliedLeadingToneChords(unittest.TestCase):
    """``vii°7/x``: the fully diminished seventh on the target's leading tone."""

    def test_head_lexes(self):
        self.assertEqual(parse_applied_token("vii°7/V"), ("vii°7", "V"))
        self.assertEqual(parse_applied_token(" vii°7/ii "), ("vii°7", "ii"))
        self.assertIn("vii°7", APPLIED_HEADS)
        self.assertNotIn("vii°7", APPLIED_DOMINANT_HEADS)

    def test_corpus_examples_build(self):
        # The two BWV 846 rows of the plan's corpus-gap table (§1.3).
        expected = {
            "vii°7/V": ["F#", "A", "C", "Eb"],
            "vii°7/ii": ["C#", "E", "G", "Bb"],
            "vii°7/IV": ["E", "G", "Bb", "Db"],
            "vii°7/vi": ["G#", "B", "D", "F"],
            "vii°7/iii": ["D#", "F#", "A", "C"],
        }
        for token, pitches in expected.items():
            chord = build_applied_chord(token, "C", "major")
            self.assertEqual(chord.pitches, pitches, token)
            self.assertEqual(chord.roman, token, token)
            self.assertEqual(chord.chord_quality, "diminished_seventh", token)
            self.assertEqual(chord.interval_layer, "m3+m3+m3", token)

    def test_root_is_the_targets_leading_tone(self):
        chord = build_applied_chord("vii°7/V", "C", "major")
        self.assertEqual(chord.root, "F#")
        self.assertEqual(chord.chord_symbol, "F#°7")
        self.assertIn("leading", chord.function_label)

    def test_explanation_names_the_chromatic_tones_and_target(self):
        text = build_applied_chord("vii°7/V", "C", "major").explanation_text
        self.assertIn("F#", text)
        self.assertIn("G", text)          # the tonicised root
        self.assertIn("C major", text)

    def test_same_honesty_gates_as_the_dominants(self):
        for token, why in (("vii°7/I", "tonic target"),
                           ("vii°7/vii°", "diminished target"),
                           ("vii°7/V", "natural minor has no V")):
            mode = "natural_minor" if "minor" in why else "major"
            with self.assertRaises(ValueError, msg=why):
                build_applied_chord(token, "C" if mode == "major" else "A", mode)

    def test_build_applied_dominant_stays_dominants_only(self):
        with self.assertRaises(ValueError):
            build_applied_dominant("vii°7/V", "C", "major")

    def test_vocabulary_includes_both_families(self):
        major = applied_tokens_for_mode("major")
        self.assertIn("V7/V", major)
        self.assertIn("vii°7/V", major)
        self.assertEqual(len([t for t in major if t.startswith("vii°7/")]), 5)
        # ...and can be filtered back to the dominants (the secondary-dominant
        # network draws applied DOMINANTS).
        doms = applied_tokens_for_mode("major", heads=APPLIED_DOMINANT_HEADS)
        self.assertEqual(doms, [t for t in major if not t.startswith("vii°7/")])

    def test_minor_vocabulary_is_spelled_for_its_own_mode(self):
        minor = applied_tokens_for_mode("natural_minor")
        self.assertIn("vii°7/v", minor)
        self.assertNotIn("vii°7/V", minor)

    def test_pattern_transposition_builds_the_applied_leading_tone(self):
        chords = transpose_degree_pattern(["I", "vii°7/V", "V"], "C", "major")
        self.assertEqual([c.roman for c in chords], ["I", "vii°7/V", "V"])
        self.assertEqual(chords[1].chord_symbol, "F#°7")


# ---------------------------------------------------------------------------
# 2. The ramp itself (harmony/applied_ramp.py) — pure content derivation
# ---------------------------------------------------------------------------

class TestAppliedProgression(unittest.TestCase):
    """The position axis: the intruder lands anywhere, always resolving."""

    def test_flagship_shape_is_reproduced(self):
        self.assertEqual(applied_progression("V7/V", 2),
                         ["I", "vi", "V7/V", "V", "I"])

    def test_position_moves_the_intruder(self):
        for pos in (1, 2, 3, 4):
            prog = applied_progression("V7/V", pos)
            self.assertEqual(prog.index("V7/V"), pos, prog)
            self.assertEqual(prog[pos + 1], "V", prog)   # always resolves
            self.assertEqual(prog[0], "I", prog)         # opens in the key
            self.assertEqual(prog[-1], "I", prog)        # closes in the key

    def test_exactly_one_chromatic_chord(self):
        for token in ("V7/ii", "V7/IV", "vii°7/V", "V/vi"):
            prog = applied_progression(token, 2)
            applied = [t for t in prog if parse_applied_token(t)]
            self.assertEqual(applied, [token], prog)

    def test_no_immediate_repeats(self):
        for token in ("V7/ii", "V7/iii", "V7/IV", "V7/V", "V7/vi"):
            for pos in (1, 2, 3):
                prog = applied_progression(token, pos)
                self.assertTrue(all(a != b for a, b in zip(prog, prog[1:])),
                                prog)

    def test_minor_mode_uses_its_own_degree_spellings(self):
        prog = applied_progression("V7/iv", 2, mode="natural_minor")
        self.assertEqual(prog[0], "i")
        self.assertEqual(prog[3], "iv")
        self.assertNotIn("V", prog)      # natural minor's dominant is v

    def test_progression_compiles_in_its_key(self):
        prog = applied_progression("vii°7/ii", 3)
        chords = transpose_degree_pattern(prog, "G", "major")
        self.assertEqual([c.roman for c in chords], prog)

    def test_position_must_leave_room_to_resolve(self):
        for bad in (0, -1, 9):
            with self.assertRaises(ValueError):
                applied_progression("V7/V", bad)


class TestKeyRamp(unittest.TestCase):
    """The key axis: outward by circle-of-fifths distance, derived from the
    key signature (never a hand-kept list)."""

    def test_distance_zero_is_the_home_key(self):
        self.assertEqual(keys_by_fifths_distance("major", 0), ["C"])
        self.assertEqual(keys_by_fifths_distance("natural_minor", 0), ["A"])

    def test_first_ring_is_one_accidental_each_way(self):
        self.assertEqual(keys_by_fifths_distance("major", 1), ["C", "G", "F"])

    def test_second_ring_adds_two_accidentals(self):
        self.assertEqual(keys_by_fifths_distance("major", 2),
                         ["C", "G", "F", "D", "Bb"])

    def test_ordering_is_by_distance_then_sharp_side_first(self):
        keys = keys_by_fifths_distance("major", 3)
        self.assertEqual(keys[-2:], ["A", "Eb"])


class TestDominantChain(unittest.TestCase):
    """The circle-of-fifths performance drill: V/V/V... as a chain of
    dominants, each resolving down a fifth into the next."""

    def test_chain_is_derived_by_descending_fifths(self):
        self.assertEqual(dominant_chain(3),
                         ["I", "V7/ii", "V7/V", "V7", "I"])

    def test_longest_major_chain_stops_at_the_diminished_degree(self):
        chain = dominant_chain(5)
        self.assertEqual(chain, ["I", "V7/iii", "V7/vi", "V7/ii", "V7/V",
                                 "V7", "I"])
        with self.assertRaises(ValueError):
            dominant_chain(6)      # vii° cannot be tonicised — the chain ends

    def test_each_link_resolves_a_fifth_into_the_next(self):
        chords = transpose_degree_pattern(dominant_chain(4), "C", "major")
        self.assertEqual([c.chord_symbol for c in chords],
                         ["C", "E7", "A7", "D7", "G7", "C"])

    def test_harmonic_minor_chains_use_its_raised_leading_tone(self):
        chain = dominant_chain(2, mode="harmonic_minor")
        chords = transpose_degree_pattern(chain, "A", "harmonic_minor")
        self.assertEqual(chords[0].roman, "i")
        self.assertEqual(chords[-1].roman, "i")
        self.assertEqual(chords[-2].roman, "V7")

    def test_natural_minor_refuses(self):
        # No V7 without a raised leading tone: the chain has no engine.
        with self.assertRaises(ValueError):
            dominant_chain(2, mode="natural_minor")


# ---------------------------------------------------------------------------
# 3. The ear stage — hear the progression, click the position, name the target
# ---------------------------------------------------------------------------

def _ear_spec(token="V7/V", position=2, key="C major"):
    return LabExperimentSpec(
        experiment_id="t_applied_ear",
        title="Ear: spot the intruder",
        concept="applied_chord", mode="major", key=key, render="block",
        parameters={"progression": applied_progression(token, position),
                    "stages": ["ear"]},
    )


class TestEarStage(unittest.TestCase):
    def test_ear_is_a_stage_now(self):
        self.assertEqual(APPLIED_STAGES, ("spot", "resolve", "ear"))

    def test_ear_stage_compiles_to_a_veiled_spot_drill(self):
        (inner,) = _ear_spec().to_exercise_specs()
        self.assertEqual(inner.answer_mode, "spot")
        self.assertEqual(inner.presentation, "echo")
        self.assertEqual(inner.render, "block")
        self.assertEqual(len(compile_exercise(inner)), 5)

    def test_ear_stage_needs_the_block_render(self):
        spec = _ear_spec()
        spec.render = "arpeggio"
        with self.assertRaises(ValueError):
            spec.validate()

    def test_echo_plus_spot_is_legal_but_echo_plus_card_is_not(self):
        (inner,) = _ear_spec().to_exercise_specs()
        inner.validate()                       # does not raise
        inner.answer_mode = "card"
        with self.assertRaises(ValueError):
            inner.validate()

    def test_stages_still_reject_unknown_names(self):
        spec = _ear_spec()
        spec.parameters["stages"] = ["listen"]
        with self.assertRaises(ValueError):
            spec.validate()


class TestEarPayload(unittest.TestCase):
    """The veiled spot payload asks two questions: *where* and *what for*."""

    def payload(self, token="V7/V", position=2):
        (inner,) = _ear_spec(token, position).to_exercise_specs()
        return build_trainer_payload(compile_exercise(inner))

    def test_position_question_is_the_plain_spot_contract(self):
        p = self.payload()
        self.assertEqual(p["ANSWER_MODE"], "spot")
        self.assertEqual(p["PRESENTATION"], "echo")
        self.assertEqual(p["SPOT_INDEX"], 2)

    def test_followup_asks_which_degree_was_tonicised(self):
        f = self.payload()["SPOT_FOLLOWUP"]
        self.assertEqual(f["answer"], "V")
        self.assertIn("V", f["options"])
        self.assertEqual(f["options"], applied_target_options("major"))
        self.assertNotIn("I", f["options"])       # the tonic is never tonicised
        self.assertIn("tonicise", f["prompt"].lower())

    def test_followup_answer_tracks_the_token(self):
        self.assertEqual(self.payload("vii°7/ii", 1)["SPOT_FOLLOWUP"]["answer"],
                         "ii")

    def test_visual_spot_drills_ask_only_the_position_question(self):
        spec = LabExperimentSpec(
            experiment_id="t_applied_spot", title="Spot",
            concept="applied_chord", mode="major", key="C major",
            render="block",
            parameters={"progression": applied_progression("V7/V", 2),
                        "stages": ["spot"]})
        (inner,) = spec.to_exercise_specs()
        payload = build_trainer_payload(compile_exercise(inner))
        self.assertNotIn("SPOT_FOLLOWUP", payload)


class TestEarSharesTheVisualLeafsRecord(unittest.TestCase):
    """The ear rung is the spot leaf's 🎧 twin — one mastery record per leaf
    (the ticket-07 rule), not a second leaf with its own progress."""

    def spot_leaf(self):
        return LabExperimentSpec(
            experiment_id="t_applied_spot", title="Spot",
            concept="applied_chord", mode="major", key="C major",
            render="block",
            parameters={"progression": applied_progression("V7/V", 2),
                        "stages": ["spot"]})

    def test_spot_leaves_own_an_echo_twin(self):
        self.assertTrue(is_echo_eligible(self.spot_leaf()))

    def test_resolve_leaves_do_not(self):
        spec = self.spot_leaf()
        spec.parameters["stages"] = ["resolve"]
        self.assertFalse(is_echo_eligible(spec))

    def test_the_twin_is_exactly_the_ear_stage(self):
        (spot,) = self.spot_leaf().to_exercise_specs()
        twin = echo_variant(spot)
        (ear,) = _ear_spec().to_exercise_specs()
        self.assertEqual(twin.answer_mode, ear.answer_mode)
        self.assertEqual(twin.presentation, ear.presentation)
        self.assertEqual(twin.pattern, ear.pattern)
        self.assertEqual(
            build_trainer_payload(compile_exercise(twin))["SPOT_FOLLOWUP"],
            build_trainer_payload(compile_exercise(ear))["SPOT_FOLLOWUP"])


# ---------------------------------------------------------------------------
# 4. The scene draws the applied leading-tone chord honestly
# ---------------------------------------------------------------------------

class TestAppliedLeadingToneScene(unittest.TestCase):
    """``vii°7/x`` routes to the same secondary-dominant scene, is drawn as
    the tetrad it is, and is never *described* as a dominant."""

    def scene(self, token="vii°7/V"):
        spec = HarmonyExerciseSpec(
            exercise_id="t_scene_applied_lt", title="vii°7/V",
            drill="function", mode="major",
            pattern=applied_progression(token, 2), keys=["C"])
        decision = decide_graph_scene(GraphSceneRequest(exercise_spec=spec))
        self.assertEqual(decision.scene_type, "secondary_dominant_path")
        return build_graph_scene(GraphSceneRequest(exercise_spec=spec))

    def test_the_intruder_is_typed_as_a_seventh_not_a_triad(self):
        node = [n for n in self.scene().nodes if n.roman == "vii°7/V"][0]
        self.assertEqual(node.entity_type, "seventh")
        self.assertEqual(node.chord_symbol, "F#°7")
        self.assertEqual(node.canonical_refs, ())   # no diatonic node claimed

    def test_role_labels_say_leading_tone_not_dominant(self):
        node = [n for n in self.scene().nodes if n.roman == "vii°7/V"][0]
        self.assertEqual(node.specific_role, "applied leading-tone chord")
        self.assertNotIn("dominant of", node.family_membership_explanation)

    def test_the_tonicisation_arrow_is_drawn_under_its_own_relation(self):
        # The relation id is learner-visible (the scene detail panel prints it),
        # so a diminished seventh's arrow must not be called a secondary
        # DOMINANT — the same mislabel that keeps vii°7/x out of the network.
        scene = self.scene()
        arrows = [e for e in scene.edges if e.visual_class == "applied"]
        self.assertEqual(len(arrows), 1)
        self.assertEqual(arrows[0].relation, "applied_leading_tone_of")
        self.assertEqual(
            [n.roman for n in scene.nodes if n.id == arrows[0].target], ["V"])
        self.assertNotIn("does not support", " ".join(scene.warnings))
        occ = [o for o in scene.occurrence_map if o.roman == "vii°7/V"][0]
        self.assertEqual(occ.next_theory_relation, "applied_leading_tone_of")

    def test_applied_dominants_are_still_described_as_dominants(self):
        scene = self.scene("V7/V")
        node = [n for n in scene.nodes if n.roman == "V7/V"][0]
        self.assertEqual(node.specific_role, "applied dominant")
        self.assertEqual([e.relation for e in scene.edges
                          if e.visual_class == "applied"],
                         ["secondary_dominant_of"])

    def test_the_resolving_tritone_is_flagged_for_both_families(self):
        # Plan §7 stage 2: "the tritone (F#+C → G+B) flagged green as it
        # resolves" — a °7 has that same tritone, from root + diminished fifth.
        for token in ("V7/V", "vii°7/V"):
            spec = HarmonyExerciseSpec(
                exercise_id=f"t_resolve_{token}", title=token, drill="function",
                mode="major", pattern=[token, "V"], keys=["C"])
            payload = build_trainer_payload(compile_exercise(spec))
            applied, target = payload["TARGET_CHORDS"]
            self.assertEqual(applied["tritonePcs"], [6, 0], token)   # F# + C
            self.assertEqual(target["tritoneResolution"]["text"],
                             "F#→G, C→B", token)


# ---------------------------------------------------------------------------
# 5. The curriculum rungs
# ---------------------------------------------------------------------------

class TestRampCurriculum(unittest.TestCase):
    """One lesson, one group per ramp axis — and the ear axis as twins."""

    @classmethod
    def setUpClass(cls):
        from harmony.curriculum import build_curriculum
        cls.root = build_curriculum()
        cls.lesson = cls.root.find("lesson:adv_applied_ramp")

    def leaves(self, group_id=None):
        node = self.root.find(group_id) if group_id else self.lesson
        return [n for n in node.walk() if n.kind == "exercise"]

    def test_lesson_is_live_under_advanced(self):
        self.assertIsNotNone(self.lesson)
        self.assertFalse(self.lesson.reserved)
        self.assertEqual(self.lesson.parent, "cat:advanced")
        self.assertEqual(self.lesson.exercise_count, 17)

    def test_position_axis_moves_the_intruder(self):
        positions = []
        for leaf in self.leaves("group:applied_positions"):
            prog = list(leaf.lab_spec.parameters["progression"])
            positions.append(prog.index("V7/V"))
        self.assertEqual(sorted(positions), [1, 3, 4])   # 2 is the flagship

    def test_target_axis_ships_live_leading_tone_drills(self):
        spots = self.leaves("group:applied_leading_tone")
        resolves = self.leaves("group:applied_leading_tone_resolve")
        self.assertEqual(len(spots), 3)
        self.assertEqual(len(resolves), 3)
        for leaf in spots + resolves:
            (inner,) = leaf.lab_spec.to_exercise_specs()
            chords = compile_exercise(inner).chords
            tetrads = [c.triad for c in chords
                       if c.triad.chord_quality == "diminished_seventh"]
            self.assertEqual(len(tetrads), 1, leaf.id)
            self.assertTrue(tetrads[0].roman.startswith("vii°7/"), leaf.id)

    def test_key_axis_steps_outward_on_the_circle(self):
        keys = [leaf.lab_spec.key for leaf in self.leaves("group:applied_keys")]
        self.assertEqual(keys, ["G major", "F major", "D major", "Bb major"])

    def test_chain_axis_is_a_playable_run_of_dominants(self):
        leaves = self.leaves("group:applied_chains")
        self.assertEqual(len(leaves), 4)
        for leaf in leaves:
            inner = HarmonyExerciseSpec.from_dict(
                leaf.lab_spec.parameters["exercise"])
            self.assertEqual(inner.answer_mode, "midi")   # a performance drill
            chords = [c.triad for c in compile_exercise(inner).chords]
            applied = [c for c in chords if parse_applied_token(c.roman)]
            self.assertGreaterEqual(len(applied), 2, leaf.id)
            # each dominant's root is a fifth above the next chord's root
            for i, c in enumerate(chords[:-1]):
                if parse_applied_token(c.roman) is None:
                    continue
                self.assertEqual(
                    (note_pc(chords[i + 1].root) - note_pc(c.root)) % 12, 5,
                    f"{leaf.id}: {c.roman} does not fall a fifth")

    def test_every_ramp_leaf_compiles_inside_the_page_cap(self):
        for leaf in self.leaves():
            for inner in leaf.lab_spec.to_exercise_specs():
                self.assertLessEqual(len(compile_exercise(inner)), 12, leaf.id)

    def test_every_spot_leaf_owns_an_ear_twin(self):
        spots = [leaf for leaf in self.leaves()
                 + [n for n in self.root.find("lesson:adv_secondary").walk()
                    if n.kind == "exercise"]
                 if leaf.lab_spec.concept == "applied_chord"
                 and tuple(leaf.lab_spec.parameters["stages"]) == ("spot",)]
        self.assertEqual(len(spots), 14)     # 4 (ticket 17) + 10 (this one)
        for leaf in spots:
            self.assertTrue(is_echo_eligible(leaf.lab_spec), leaf.id)
            self.assertTrue(leaf.to_payload()["echoEligible"], leaf.id)

    def test_applied_leaves_claim_no_diatonic_atlas_or_circle_node(self):
        # An applied chord shares a root with a diatonic degree; claiming that
        # node would be the base_roman dishonesty.  Key context only.
        for leaf in self.leaves():
            if leaf.lab_spec.concept != "applied_chord":
                continue
            for ref in leaf.atlas_nodes:
                self.assertTrue(ref.startswith("scale:"), f"{leaf.id}: {ref}")
            for ref in leaf.circle_nodes:
                self.assertIn("key", ref, f"{leaf.id}: {ref}")

    def test_chain_leaves_claim_only_their_diatonic_chords(self):
        # The chain is a NATIVE drill, so its diatonic chords do claim their
        # Atlas degrees — but E7/A7/D7 must not claim iii/vi/ii, the degrees
        # they merely share a root with.
        leaf = self.root.find("ex:drill_chain_dominants_5_C")
        for degree in ("iii", "vi", "ii"):
            self.assertNotIn(f"degree:major:{degree}", leaf.atlas_nodes)
        self.assertIn("degree:major:I", leaf.atlas_nodes)


class CrossLanguageEarStageContract(unittest.TestCase):
    """The executable form of the ticket's third checkbox: a REAL Python-built
    ear payload is completed *without notation* in the REAL trainer JS
    (tests/ear_spot_contract_check.js drives beat_selector/harmony_trainer.js)."""

    def test_real_payload_completes_by_ear_in_trainer_js(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for token, position in (("V7/V", 2), ("vii°7/ii", 1)):
            (inner,) = _ear_spec(token, position).to_exercise_specs()
            payload = build_trainer_payload(compile_exercise(inner))
            with tempfile.TemporaryDirectory() as td:
                pj = os.path.join(td, "payload.json")
                with open(pj, "w", encoding="utf-8") as f:
                    json.dump(payload, f)
                out = subprocess.run(
                    [node, os.path.join(root, "tests",
                                        "ear_spot_contract_check.js"), pj],
                    capture_output=True, text=True, cwd=root)
            self.assertEqual(out.returncode, 0,
                             f"{token}: {out.stdout}\n{out.stderr}")
            self.assertIn("CONTRACT OK", out.stdout, token)


if __name__ == "__main__":
    unittest.main()
