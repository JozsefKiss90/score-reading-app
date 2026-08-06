"""Strict-bass (lowest-note) grading for inversion drills — ticket 04 / plan G4, F4.

The Lab payload now *demands* the bass it has always displayed: every block
inversion measure carries ``strictBass: true`` next to its ``bassPitchClass``,
so the shared trainer controller (beat_selector/harmony_trainer.js) requires
the demanded chord member as the lowest sounding note.  The whole 97-leaf
inversion grid gains this at the generator — no leaf is re-authored — while
every non-inversion drill keeps its octave-agnostic grading.

Run from the project root::

    .venv/Scripts/python.exe -m unittest tests.test_strict_bass_grading

The JS half (the actual lowest-note check + named-bass feedback) is pinned by
``node tests/harmony_trainer_bass_test.js``.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from theory.diatonic_harmony import note_pc  # noqa: E402
from harmony.lab import compile_lab  # noqa: E402
from harmony.lab_spec import LabExperimentSpec  # noqa: E402
from harmony.lab_musicxml import build_lab_payload  # noqa: E402
from harmony.exercise_spec import compile_exercise, default_demo_specs  # noqa: E402
from harmony.musicxml_builder import build_trainer_payload  # noqa: E402
from harmony.curriculum import build_curriculum, _inversion_spec  # noqa: E402


class TestInversionPayloadsDemandTheBass(unittest.TestCase):
    """Every block inversion target carries strictBass + its bassPitchClass."""

    def test_block_inversion_targets_carry_strict_bass_and_bass_pc(self):
        payload = build_lab_payload(compile_lab(_inversion_spec("major", "C", "I")))
        targets = payload["TARGET_CHORDS"]
        self.assertEqual([t["strictBass"] for t in targets], [True, True, True])
        self.assertEqual([t["bassPitchClass"] for t in targets],
                         [note_pc("C"), note_pc("E"), note_pc("G")])
        self.assertEqual([t["bassNote"] for t in targets], ["C", "E", "G"])

    def test_every_inversion_grid_leaf_grades_the_bass(self):
        # The whole grid gains bass grading from the generator alone (no
        # per-leaf re-authoring): every block inversion leaf in the curriculum
        # compiles to strict-bass targets.
        inv = build_curriculum().find("cat:inversions")
        block_leaves = [lf for lf in inv.leaves()
                        if lf.lab_spec.concept == "inversion"
                        and lf.lab_spec.render == "block"]
        self.assertGreaterEqual(len(block_leaves), 96)
        for lf in block_leaves:
            payload = build_lab_payload(compile_lab(lf.lab_spec))
            for t in payload["TARGET_CHORDS"]:
                self.assertTrue(t.get("strictBass"), (lf.id, t["absMeasure"]))
                self.assertIsNotNone(t["bassPitchClass"], lf.id)


class TestNonInversionGradingUnchanged(unittest.TestCase):
    """Root-position and non-inversion drills keep octave-agnostic grading."""

    def test_native_trainer_targets_have_no_strict_bass(self):
        for spec in default_demo_specs():
            payload = build_trainer_payload(compile_exercise(spec))
            for t in payload["TARGET_CHORDS"]:
                self.assertFalse(t.get("strictBass"), spec.exercise_id)

    def test_root_position_lab_cadence_is_not_strict(self):
        cad = LabExperimentSpec(
            "t_cad", "t", concept="cadence", key="C major", render="block",
            parameters={"pattern": ["ii", "V", "I"]})
        for t in build_lab_payload(compile_lab(cad))["TARGET_CHORDS"]:
            self.assertFalse(t.get("strictBass"), t["roman"])
            self.assertIsNotNone(t["bassPitchClass"])   # displayed, not demanded

    def test_arpeggio_inversion_stays_ordered_not_strict(self):
        arp = LabExperimentSpec(
            "t_arp", "t", concept="inversion", key="C major", render="arpeggio",
            parameters={"degree": "V", "inversions": [0, 1, 2]})
        for t in build_lab_payload(compile_lab(arp))["TARGET_CHORDS"]:
            self.assertFalse(t.get("strictBass"))

    def test_legacy_strict_bass_param_keeps_ordered_demand_without_flag(self):
        # The strict_bass *parameter* encodes its demand as a bass-first
        # ordered walk; it must not also claim the lowest-note check.
        spec = LabExperimentSpec(
            "t_legacy", "t", concept="inversion", key="C major", render="block",
            parameters={"degree": "I", "inversions": [0, 1, 2],
                        "strict_bass": True})
        for t in build_lab_payload(compile_lab(spec))["TARGET_CHORDS"]:
            self.assertFalse(t.get("strictBass"))
            self.assertEqual(t["pitchClasses"][0], t["bassPitchClass"])


class TestFiguredCadenceTokens(unittest.TestCase):
    """Figured tokens ('ii6') are assessed performance instructions (block only)."""

    def _spec(self, render="block", pattern=("ii6", "V", "I")):
        return LabExperimentSpec(
            "t_ii6", "t", concept="cadence", key="C major", render=render,
            parameters={"pattern": list(pattern), "cadence_type": "authentic"})

    def test_ii6_measure_demands_the_third_in_the_bass(self):
        m0, m1, m2 = compile_lab(self._spec()).measures
        # ii in C is D-F-A; the figure 6 puts F in the bass, and only that
        # measure is graded strictly.
        self.assertEqual(m0.annotation.bass_note, "F")
        self.assertEqual(m0.bass_pitch_class, note_pc("F"))
        self.assertEqual(m0.annotation.figured_bass, "6")
        self.assertEqual(m0.annotation.inversion, 1)
        self.assertTrue(m0.strict_bass)
        self.assertEqual(m1.bass_pitch_class, note_pc("G"))
        self.assertEqual(m2.bass_pitch_class, note_pc("C"))
        self.assertFalse(m1.strict_bass)
        self.assertFalse(m2.strict_bass)

    def test_ii6_payload_targets_thread_the_demand(self):
        t0, t1, t2 = build_lab_payload(
            compile_lab(self._spec()))["TARGET_CHORDS"]
        self.assertTrue(t0["strictBass"])
        self.assertEqual(t0["bassPitchClass"], note_pc("F"))
        self.assertEqual(t0["bassNote"], "F")
        self.assertEqual(t0["figuredBass"], "6")
        self.assertFalse(t1["strictBass"])
        self.assertFalse(t2["strictBass"])

    def test_bass_motion_names_the_actual_bass(self):
        # ii6 -> V walks F -> G in the bass (not the root D -> G).
        measures = compile_lab(self._spec()).measures
        self.assertEqual(measures[1].annotation.bass_motion, "F → G")
        self.assertEqual(measures[2].annotation.bass_motion, "G → C")

    def test_root_position_cadences_are_byte_identical_to_before(self):
        # No figures -> the generator's output is unchanged (regression).
        plain = compile_lab(LabExperimentSpec(
            "t_plain", "t", concept="cadence", key="C major", render="block",
            parameters={"pattern": ["ii", "V", "I"]}))
        self.assertEqual([m.annotation.bass_motion for m in plain.measures],
                         [None, "D → G", "G → C"])
        self.assertFalse(any(m.strict_bass for m in plain.measures))
        self.assertFalse(any(m.annotation.inversion for m in plain.measures))

    def test_figured_tokens_rejected_for_satb_render(self):
        with self.assertRaises(ValueError):
            self._spec(render="voice_leading").validate()

    def test_unknown_figure_rejected(self):
        with self.assertRaises(ValueError):
            self._spec(pattern=("ii9", "V", "I")).validate()

    def test_bridge_spec_strips_figures_to_root_position(self):
        specs = self._spec().to_exercise_specs()
        self.assertEqual(specs[0].pattern, ["ii", "V", "I"])
        self.assertEqual(len(compile_exercise(specs[0])), 3)


class TestIi6CadenceBridgeLeaf(unittest.TestCase):
    """A cadence drill demanding ii6 links the inversions and cadences categories."""

    def setUp(self):
        self.root = build_curriculum()

    def _ii6_leaves(self):
        # Bass-line dictation leaves (ticket 11) may also carry ii6 in their
        # patterns; the bridge leaf is the unique VISUAL ii6 cadence drill.
        return [lf for lf in self.root.find("cat:inversions").leaves()
                if lf.lab_spec.concept == "cadence"
                and "ii6" in (lf.lab_spec.parameters.get("pattern") or [])
                and not lf.lab_spec.parameters.get("dictation")]

    def test_leaf_exists_once_under_inversions(self):
        self.assertEqual(len(self._ii6_leaves()), 1)

    def test_leaf_demands_f_in_the_bass_on_the_ii6_measure(self):
        exp = compile_lab(self._ii6_leaves()[0].lab_spec)
        self.assertEqual(len(exp.measures), 3)
        self.assertTrue(exp.measures[0].strict_bass)
        self.assertEqual(exp.measures[0].annotation.bass_note, "F")
        self.assertEqual(exp.measures[0].annotation.figured_bass, "6")
        self.assertFalse(exp.measures[1].strict_bass)
        self.assertFalse(exp.measures[2].strict_bass)

    def test_lessons_cross_link_the_two_categories(self):
        bridge = self.root.find("lesson:inversion_cadence_bridge")
        self.assertIsNotNone(bridge)
        self.assertIn("lesson:cadence_progressions", bridge.related)
        prog = self.root.find("lesson:cadence_progressions")
        self.assertIn("lesson:inversion_cadence_bridge", prog.related)


if __name__ == "__main__":
    unittest.main(verbosity=2)
