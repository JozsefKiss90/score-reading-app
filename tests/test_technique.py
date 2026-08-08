"""Piano-technique ticket 01 — the ``technique`` Lab concept + phrase engine.

The concept compiles a multi-measure, single-key melodic phrase (the missing
shape between ``motive`` and the ten daily technique exercises).  These tests
pin, in order:

  * the validation edges (measure cap, degree range, note values, hand,
    fingering shape);
  * the compile shape (measure count, per-slot single-pc ``expected_by_beat``
    -- exactly ``_gen_motive``'s ordered-walk contract -- staff choice per
    hand, rest padding, honest guide text with the coach line);
  * the render/payload path (MusicXML + ordered ``arpeggio`` targets);
  * echo ineligibility (no 🎧 twin for technique leaves);
  * the ``cat:technique`` tracer leaf wired through the curriculum.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harmony.atlas import scale_id  # noqa: E402
from harmony.echo_drills import is_echo_eligible  # noqa: E402
from harmony.lab import compile_lab  # noqa: E402
from harmony.lab_musicxml import build_lab_musicxml, build_lab_payload  # noqa: E402
from harmony.lab_spec import LabExperimentSpec  # noqa: E402


TRACER_LEAF = "ex:tech_warmup_five_finger_c_rh"

#: C major degrees 1..5 -> pitch classes (the five-finger position).
_C_PCS = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7}


def _spec(**kw) -> LabExperimentSpec:
    params = dict(
        phrase=[[1, 2, 3, 4, 5, 4, 3, 2], [1]],
        note_value="eighth",
        hand="rh",
    )
    params.update(kw.pop("parameters", {}))
    base = dict(
        experiment_id="tech_test", title="Technique test",
        concept="technique", mode="major", key="C major", render="melody",
        parameters=params,
    )
    base.update(kw)
    return LabExperimentSpec(**base)


class TestValidation(unittest.TestCase):
    """The spec-surface edges the ticket pins."""

    def test_valid_spec_validates(self):
        _spec().validate()   # must not raise

    def test_round_trips_through_dict(self):
        spec = _spec()
        spec.validate()
        again = LabExperimentSpec.from_dict(spec.to_dict())
        self.assertEqual(again.parameters["phrase"], spec.parameters["phrase"])

    def test_thirteen_measures_refused(self):
        with self.assertRaisesRegex(ValueError, "13"):
            _spec(parameters={"phrase": [[1]] * 13}).validate()

    def test_twelve_measures_accepted(self):
        _spec(parameters={"phrase": [[1]] * 12}).validate()

    def test_degree_30_refused(self):
        with self.assertRaisesRegex(ValueError, "1..29"):
            _spec(parameters={"phrase": [[1, 30]]}).validate()

    def test_degree_0_refused(self):
        with self.assertRaisesRegex(ValueError, "1..29"):
            _spec(parameters={"phrase": [[0, 1]]}).validate()

    def test_degree_29_accepted(self):
        _spec(parameters={"phrase": [[1, 29]]}).validate()

    def test_empty_phrase_refused(self):
        with self.assertRaisesRegex(ValueError, "phrase"):
            _spec(parameters={"phrase": []}).validate()

    def test_empty_measure_refused(self):
        with self.assertRaisesRegex(ValueError, "measure"):
            _spec(parameters={"phrase": [[1, 2], []]}).validate()

    def test_sixteenths_refused_until_ticket_02(self):
        with self.assertRaisesRegex(ValueError, "note_value"):
            _spec(parameters={"note_value": "16th"}).validate()

    def test_measure_overflowing_its_slots_refused(self):
        # 5 quarters cannot fit a 4/4 bar; 9 eighths cannot either.
        with self.assertRaises(ValueError):
            _spec(parameters={"phrase": [[1, 2, 3, 4, 5]],
                              "note_value": "quarter"}).validate()
        with self.assertRaises(ValueError):
            _spec(parameters={"phrase": [[1, 2, 3, 4, 5, 4, 3, 2, 1]]}).validate()

    def test_unknown_hand_refused(self):
        with self.assertRaisesRegex(ValueError, "hand"):
            _spec(parameters={"hand": "both"}).validate()

    def test_fingering_shape_mismatch_refused(self):
        # one tuple per measure and one label per note -- both directions.
        with self.assertRaisesRegex(ValueError, "fingering"):
            _spec(parameters={"fingering": [["1", "2"]]}).validate()
        with self.assertRaisesRegex(ValueError, "fingering"):
            _spec(parameters={
                "fingering": [["1", "2", "3", "4", "5", "4", "3"], ["1"]],
            }).validate()

    def test_fingering_labels_restricted(self):
        with self.assertRaisesRegex(ValueError, "fingering"):
            _spec(parameters={
                "fingering": [["1", "2", "3", "4", "5", "4", "3", "6"], ["1"]],
            }).validate()

    def test_matching_fingering_accepted(self):
        _spec(parameters={
            "fingering": [["1", "2", "3", "4", "5", "4", "3", "2"], ["1"]],
        }).validate()

    def test_block_render_refused(self):
        with self.assertRaisesRegex(ValueError, "render"):
            _spec(render="block").validate()

    def test_melodic_minor_refused(self):
        # melodic minor stays motive-only (its scale form is direction-bound).
        with self.assertRaisesRegex(ValueError, "motive"):
            _spec(mode="melodic_minor", key="A minor").validate()

    def test_no_chord_drill_representation(self):
        self.assertEqual(_spec().to_exercise_specs(), [])


class TestCompile(unittest.TestCase):
    """The phrase engine's compile shape (the _gen_motive grading contract)."""

    def test_measure_count_matches_phrase(self):
        exp = compile_lab(_spec())
        self.assertEqual(len(exp.measures), 2)

    def test_expected_by_beat_single_ordered_pcs(self):
        exp = compile_lab(_spec())
        m0 = exp.measures[0]
        want = [_C_PCS[d] for d in (1, 2, 3, 4, 5, 4, 3, 2)]
        self.assertEqual(m0.expected_by_beat,
                         {i + 1: [pc] for i, pc in enumerate(want)})
        self.assertEqual(list(m0.target_pitch_classes), want)
        for pcs in m0.expected_by_beat.values():
            self.assertEqual(len(pcs), 1)
        self.assertEqual(exp.measures[1].expected_by_beat, {1: [0]})

    def test_rh_line_on_treble_staff(self):
        m0 = compile_lab(_spec()).measures[0]
        self.assertEqual(len([n for n in m0.staff1 if not n.is_rest]), 8)
        self.assertEqual(len(m0.staff2), 1)
        self.assertTrue(m0.staff2[0].is_rest)
        self.assertEqual(m0.staff2[0].note_type, "whole")
        # octave 4-centred: degree 1 in C major is C4
        self.assertEqual(m0.staff1[0].octave, 4)

    def test_lh_line_on_bass_staff_octaves_2_3(self):
        m0 = compile_lab(_spec(parameters={"hand": "lh"})).measures[0]
        self.assertEqual(len([n for n in m0.staff2 if not n.is_rest]), 8)
        self.assertEqual(len(m0.staff1), 1)
        self.assertTrue(m0.staff1[0].is_rest)
        # the same degrees two octaves down: degree 1 -> C2
        self.assertEqual(m0.staff2[0].octave, 2)
        # grading is octave-agnostic: same pitch classes as the RH line
        self.assertEqual(m0.expected_by_beat[1], [0])

    def test_short_measure_rest_padded(self):
        m1 = compile_lab(_spec()).measures[1]
        self.assertEqual(len(m1.staff1), 8)          # 1 note + 7 eighth rests
        self.assertEqual(len([n for n in m1.staff1 if n.is_rest]), 7)
        self.assertTrue(all(n.note_type == "eighth" for n in m1.staff1))

    def test_quarter_note_value_uses_four_slots(self):
        exp = compile_lab(_spec(parameters={"phrase": [[1, 2, 3]],
                                            "note_value": "quarter"}))
        m0 = exp.measures[0]
        self.assertEqual(len(m0.staff1), 4)          # 3 quarters + 1 rest
        self.assertTrue(all(n.note_type == "quarter" for n in m0.staff1))

    def test_degrees_wrap_into_higher_octaves(self):
        exp = compile_lab(_spec(parameters={"phrase": [[1, 8, 15, 29]],
                                            "note_value": "quarter"}))
        notes = [n for n in exp.measures[0].staff1 if not n.is_rest]
        self.assertEqual([n.octave for n in notes], [4, 5, 6, 8])
        self.assertTrue(all(n.step == "C" for n in notes))

    def test_measures_are_melody_with_no_underlying_chord(self):
        for m in compile_lab(_spec()).measures:
            self.assertEqual(m.render, "melody")
            self.assertIsNone(m.underlying)
            self.assertIsNone(m.bass_pitch_class)

    def test_annotation_carries_key_fingering_and_coach(self):
        spec = _spec(parameters={
            "fingering": [["1", "2", "3", "4", "5", "4", "3", "2"], ["1"]],
            "coach": "Even, relaxed tone; let the wrist float.",
        })
        m0 = compile_lab(spec).measures[0]
        self.assertEqual(m0.annotation.atlas_scale_id, scale_id("C", "major"))
        self.assertIn("measure 1/2", m0.annotation.lab_note)
        self.assertIn("1 2 3 4 5 4 3 2", m0.annotation.lab_note)
        self.assertIn("let the wrist float", m0.annotation.lab_note)

    def test_musicxml_and_payload_render(self):
        exp = compile_lab(_spec())
        xml = build_lab_musicxml(exp)
        self.assertIn("<work-title>", xml)
        self.assertEqual(xml.count("<measure number="), 2)
        payload = build_lab_payload(exp)
        self.assertEqual(payload["render"], "arpeggio")   # the ordered walk
        self.assertEqual(payload["concept"], "technique")
        for t in payload["TARGET_CHORDS"]:
            self.assertEqual(t["render"], "arpeggio")
        self.assertEqual(payload["EXPECTED_MIDI_BY_MEASURE_OR_BEAT"]["0"]["1"],
                         [0])

    def test_harmonic_minor_phrase_compiles(self):
        exp = compile_lab(_spec(mode="harmonic_minor", key="A minor",
                                parameters={"phrase": [[5, 6, 7, 8]],
                                            "note_value": "quarter"}))
        notes = [n for n in exp.measures[0].staff1 if not n.is_rest]
        # harmonic minor's raised 7th: G# -> pc 8
        self.assertEqual([n.pitch_class for n in notes], [4, 5, 8, 9])


class TestEchoIneligibility(unittest.TestCase):
    def test_technique_is_not_echo_eligible(self):
        self.assertFalse(is_echo_eligible(_spec()))


class TestCurriculumTracer(unittest.TestCase):
    """The cat:technique category + the one tracer leaf, wired end to end."""

    @classmethod
    def setUpClass(cls):
        from harmony.curriculum import build_curriculum
        cls.root = build_curriculum()

    def test_category_present(self):
        node = self.root.find("cat:technique")
        self.assertIsNotNone(node)
        self.assertEqual(node.title, "Piano Technique")
        self.assertFalse(node.reserved)

    def test_tracer_leaf_launchable(self):
        leaf = self.root.find(TRACER_LEAF)
        self.assertIsNotNone(leaf)
        self.assertEqual(leaf.kind, "exercise")
        spec = leaf.lab_spec
        self.assertEqual(spec.concept, "technique")
        spec.validate()
        exp = compile_lab(spec)                       # curriculum -> lab compile
        self.assertEqual(len(exp.measures), 2)
        build_lab_musicxml(exp)                        # -> render
        payload = build_lab_payload(exp)               # -> ordered MIDI grading
        self.assertEqual(payload["render"], "arpeggio")

    def test_tracer_leaf_has_no_echo_button(self):
        # the JS gates the 🎧 button on the payload's echoEligible flag
        leaf = self.root.find(TRACER_LEAF)
        self.assertFalse(is_echo_eligible(leaf.lab_spec))
        self.assertFalse(leaf.to_payload()["echoEligible"])

    def test_tracer_coach_line_shown_in_description(self):
        leaf = self.root.find(TRACER_LEAF)
        self.assertIn("wrist", leaf.description)

    def test_leaf_page_has_theory_and_advice(self):
        from harmony.curriculum_explanations import exercise_page
        leaf = self.root.find(TRACER_LEAF)
        page = exercise_page(leaf)
        self.assertTrue(page["musicTheory"].strip())
        self.assertTrue(page["practiceAdvice"])
        self.assertTrue(page["commonMistakes"])

    def test_objective_and_keywords_not_blank(self):
        leaf = self.root.find(TRACER_LEAF)
        self.assertTrue(leaf.learning_objective.strip())
        self.assertIn("technique", leaf.keywords)

    def test_progress_service_records_completion(self):
        import tempfile
        from pathlib import Path
        from harmony.progress_service import ProgressService
        with tempfile.TemporaryDirectory() as td:
            svc = ProgressService(curriculum_path=Path(td) / "cur.json",
                                  journey_path=Path(td) / "journey.json")
            svc.started(TRACER_LEAF, "2026-08-08T00:00:00+00:00")
            rec = svc.record(TRACER_LEAF, accuracy=1.0,
                             timestamp="2026-08-08T00:01:00+00:00")
            self.assertIn(rec.state, ("completed", "mastered"))
            self.assertIs(svc.progress.get(TRACER_LEAF), rec)


class TestConceptExplanation(unittest.TestCase):
    """The honest theory page (what technique drills grade and cannot)."""

    def test_explanation_registered_with_required_fields(self):
        from harmony.lab_explanations import (
            get_concept_explanation, _REQUIRED_CONCEPT_FIELDS)
        page = get_concept_explanation("technique")
        for field in _REQUIRED_CONCEPT_FIELDS:
            self.assertTrue(page[field], field)

    def test_explanation_states_grading_limits(self):
        from harmony.lab_explanations import get_concept_explanation
        page = get_concept_explanation("technique")
        text = " ".join([page["core_idea"]] + page["common_misconceptions"])
        self.assertIn("octave", text.lower())        # octaves indistinguishable
        self.assertIn("order", text.lower())         # the ordered walk


if __name__ == "__main__":
    unittest.main(verbosity=2)
