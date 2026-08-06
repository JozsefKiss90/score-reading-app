"""Bass-line dictation — ticket 11 / plan A1 level 5 (with G4's bass grading).

A ``cadence`` experiment with ``dictation: "bass"`` plays the FULL progression
(notation and playback keep every chord tone) but grades a bass-only response:
each measure's target collapses to its single bass pitch class, the payload is
presented ``echo`` (veiled notation + host auto-play, tickets 05+07), and the
finish reveal shows the complete chords for review.

Run from the project root::

    .venv/Scripts/python.exe -m unittest tests.test_bass_dictation
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from theory.diatonic_harmony import note_pc  # noqa: E402
from harmony.lab import compile_lab  # noqa: E402
from harmony.lab_spec import LabExperimentSpec  # noqa: E402
from harmony.lab_musicxml import build_lab_payload  # noqa: E402
from harmony.playback_plan import build_playback_plan  # noqa: E402


def _dictation(pattern=("ii6", "V", "I"), key="C major", mode="major",
               concept="cadence", render="block", value="bass"):
    return LabExperimentSpec(
        "t_dict", "t", concept=concept, key=key, mode=mode, render=render,
        parameters={"pattern": list(pattern), "dictation": value})


class TestDictationValidation(unittest.TestCase):
    def test_bass_dictation_validates(self):
        _dictation().validate()
        _dictation(pattern=("V65", "I", "V42", "I6")).validate()

    def test_unknown_dictation_value_rejected(self):
        with self.assertRaises(ValueError):
            _dictation(value="alto").validate()

    def test_soprano_dictation_needs_the_satb_render(self):
        # "soprano" is a real dictation mode (ticket 16), but only the
        # voice_leading render has a soprano line to dictate.
        with self.assertRaises(ValueError):
            _dictation(value="soprano").validate()

    def test_dictation_requires_block_render(self):
        with self.assertRaises(ValueError):
            _dictation(render="voice_leading").validate()

    def test_dictation_is_cadence_only(self):
        with self.assertRaises(ValueError):
            _dictation(concept="voice_leading",
                       render="voice_leading").validate()


class TestDictationGradesTheBassOnly(unittest.TestCase):
    """Each measure's graded target is exactly its (possibly figured) bass."""

    def test_targets_collapse_to_the_bass_line(self):
        exp = compile_lab(_dictation())
        # ii6–V–I in C walks F–G–C in the bass (the figure selects F).
        self.assertEqual([m.target_pitch_classes for m in exp.measures],
                         [(note_pc("F"),), (note_pc("G"),), (note_pc("C"),)])
        for m in exp.measures:
            self.assertTrue(m.strict_bass, m.index)
            self.assertEqual(m.target_pitch_classes, (m.bass_pitch_class,))

    def test_notation_keeps_the_full_chords(self):
        # The learner hears (and later sees) complete chords; only the
        # GRADING is bass-only.  Every measure still sounds >= 4 notes
        # (3 treble chord tones + the bass staff note).
        for m in compile_lab(_dictation()).measures:
            self.assertGreaterEqual(len(m.sounding_midis()), 4, m.index)

    def test_seventh_figures_dictate_their_demanded_bass(self):
        exp = compile_lab(_dictation(pattern=("V65", "I", "V42", "I6")))
        self.assertEqual(
            [m.target_pitch_classes[0] for m in exp.measures],
            [note_pc("B"), note_pc("C"), note_pc("F"), note_pc("E")])

    def test_plain_cadence_grading_unchanged(self):
        # Without the dictation knob nothing moves: full-chord targets.
        exp = compile_lab(LabExperimentSpec(
            "t_plain", "t", concept="cadence", key="C major", render="block",
            parameters={"pattern": ["ii6", "V", "I"]}))
        self.assertEqual([len(m.target_pitch_classes) for m in exp.measures],
                         [3, 3, 3])


class TestDictationPayload(unittest.TestCase):
    def setUp(self):
        self.payload = build_lab_payload(compile_lab(_dictation()))

    def test_presented_echo_with_dictation_flag(self):
        # PRESENTATION drives the JS veil + the host auto-play; DICTATION
        # switches the veiled prompt to "play only the bass line".
        self.assertEqual(self.payload["PRESENTATION"], "echo")
        self.assertEqual(self.payload["DICTATION"], "bass")

    def test_non_dictation_lab_payloads_stay_visual(self):
        plain = build_lab_payload(compile_lab(LabExperimentSpec(
            "t_plain", "t", concept="cadence", key="C major", render="block",
            parameters={"pattern": ["V", "I"]})))
        self.assertEqual(plain["PRESENTATION"], "visual")
        self.assertNotIn("DICTATION", plain)

    def test_expected_map_is_the_bass_line(self):
        expected = self.payload["EXPECTED_MIDI_BY_MEASURE_OR_BEAT"]
        self.assertEqual([expected[str(i)] for i in range(3)],
                         [[note_pc("F")], [note_pc("G")], [note_pc("C")]])

    def test_targets_keep_full_chord_sound_but_graded_bass(self):
        for t in self.payload["TARGET_CHORDS"]:
            self.assertEqual(len(t["pitchClasses"]), 1, t["absMeasure"])
            self.assertTrue(t["strictBass"], t["absMeasure"])
            self.assertGreaterEqual(len(t["midiPitches"]), 4, t["absMeasure"])
            self.assertIsNotNone(t["bassMidi"], t["absMeasure"])

    def test_playback_plays_the_full_progression(self):
        # Ticket checkbox 3: the drill PLAYS a progression (all chord tones),
        # while grading only the bass response.
        plan = build_playback_plan(self.payload)
        self.assertEqual(len(plan.events), 3)
        for ev in plan.events:
            self.assertGreaterEqual(len(ev.midis), 4)


class TestBassDictationLeaves(unittest.TestCase):
    """Nine dictation leaves under a live bass-dictation lesson (Inversions)."""

    @classmethod
    def setUpClass(cls):
        from harmony.curriculum import build_curriculum
        cls.root = build_curriculum()

    def test_lesson_lives_under_inversions(self):
        lesson = self.root.find("lesson:bass_dictation")
        self.assertIsNotNone(lesson)
        self.assertFalse(lesson.reserved)
        inv = self.root.find("cat:inversions")
        self.assertIn(lesson, inv.children)

    def test_three_progressions_in_three_keys(self):
        grp = self.root.find("group:bass_dictation_drills")
        self.assertIsNotNone(grp)
        leaves = list(grp.leaves())
        self.assertEqual(len(leaves), 9)
        patterns = set()
        keys = set()
        for lf in leaves:
            spec = lf.lab_spec
            self.assertEqual(spec.concept, "cadence", lf.id)
            self.assertEqual(spec.parameters.get("dictation"), "bass", lf.id)
            patterns.add(tuple(spec.parameters["pattern"]))
            keys.add(spec.key.split()[0])
        self.assertEqual(len(patterns), 3)
        self.assertEqual(keys, {"C", "G", "Eb"})
        # the vocabulary spans root bass lines, a triad figure and V7 figures
        self.assertIn(("I", "IV", "V", "I"), patterns)
        self.assertTrue(any("ii6" in p for p in patterns))
        self.assertTrue(any("V65" in p or "V42" in p for p in patterns))

    def test_every_leaf_is_ear_first_and_bass_graded(self):
        for lf in self.root.find("group:bass_dictation_drills").leaves():
            payload = build_lab_payload(compile_lab(lf.lab_spec))
            self.assertEqual(payload["PRESENTATION"], "echo", lf.id)
            self.assertEqual(payload["DICTATION"], "bass", lf.id)
            for t in payload["TARGET_CHORDS"]:
                self.assertEqual(len(t["pitchClasses"]), 1, lf.id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
