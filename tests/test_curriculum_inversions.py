"""Regression tests for the inversion correctness fix + expanded grid (Bug 3).

Phase A (correctness): C major I really is C / C/E / C/G with the bass climbing
root -> third -> fifth, agreeing across bass note, figured bass, pitch classes,
MusicXML and strict-bass ordering.

Phase B (coverage): the systematic grid (I/ii/IV/V x 12 major + i/iv/v/VII x 12
minor) is present, every drill is a 3-measure block inversion whose per-measure
bass is the inversion chord tone, every drill renders MusicXML, and the bridge
ids are unique (regression for the enharmonic '#'-stripping collision the audit
caught -- C minor i and C# minor i must NOT share a bridge id).

Run from the project root::

    .venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -t .
"""

import os
import sys
import unittest
import xml.etree.ElementTree as ET
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from theory.diatonic_harmony import note_pc  # noqa: E402
from harmony.lab import compile_lab  # noqa: E402
from harmony.lab_spec import LabExperimentSpec  # noqa: E402
from harmony.lab_musicxml import build_lab_musicxml, build_lab_payload  # noqa: E402
from harmony.curriculum import (  # noqa: E402
    build_curriculum, _inversion_spec, _inversion_curriculum_specs,
    _MAJOR_INV_DEGREES, _MINOR_INV_DEGREES,
)
from harmony.exercise_spec import DEFAULT_MAJOR_KEYS, DEFAULT_MINOR_KEYS  # noqa: E402


def _slash(symbol, root, bass):
    """The displayed slash chord: 'C' in root position, else 'C/E'."""
    return symbol if bass == root else f"{symbol}/{bass}"


class TestInversionCorrectness(unittest.TestCase):
    """Phase A: C major I is C, C/E, C/G with everything agreeing."""

    def setUp(self):
        self.exp = compile_lab(_inversion_spec("major", "C", "I"))

    def test_c_major_one_basses_are_C_E_G(self):
        self.assertEqual([m.annotation.bass_note for m in self.exp.measures],
                         ["C", "E", "G"])
        self.assertEqual([m.bass_pitch_class for m in self.exp.measures],
                         [note_pc("C"), note_pc("E"), note_pc("G")])

    def test_figured_bass_and_slash_chords(self):
        self.assertEqual([m.annotation.figured_bass for m in self.exp.measures],
                         ["5/3", "6", "6/4"])
        slashes = [_slash(m.annotation.chord_symbol, m.annotation.root,
                          m.annotation.bass_note) for m in self.exp.measures]
        self.assertEqual(slashes, ["C", "C/E", "C/G"])

    def test_g3_is_only_the_second_inversion(self):
        # The bass note G appears ONLY in the second-inversion measure (6/4),
        # never tied to the root-position / first-inversion task.
        g_measures = [m.index for m in self.exp.measures
                      if m.annotation.bass_note == "G"]
        self.assertEqual(g_measures, [2])

    def test_invariant_tones_and_musicxml_bass_agree(self):
        xml = build_lab_musicxml(self.exp)
        root = ET.fromstring(xml)
        measures = list(root.iter("measure"))
        for i, expected_bass_pc in enumerate((note_pc("C"), note_pc("E"),
                                              note_pc("G"))):
            self.assertEqual(set(self.exp.measures[i].target_pitch_classes),
                             {note_pc("C"), note_pc("E"), note_pc("G")})
            bass = [n for n in measures[i].findall("note")
                    if (n.findtext("staff") or "1") == "2" and n.find("pitch") is not None]
            self.assertEqual(len(bass), 1)
            p = bass[0].find("pitch")
            from theory.diatonic_harmony import LETTER_BASE_PC
            pc = (LETTER_BASE_PC[p.findtext("step")]
                  + int(p.findtext("alter") or 0)) % 12
            self.assertEqual(pc, expected_bass_pc)

    def test_strict_bass_orders_bass_pitch_class_first(self):
        spec = LabExperimentSpec(
            "s", "s", concept="inversion", key="C major", render="block",
            parameters={"degree": "I", "inversions": [0, 1, 2], "strict_bass": True})
        payload = build_lab_payload(compile_lab(spec))
        for t, bass_pc in zip(payload["TARGET_CHORDS"],
                              (note_pc("C"), note_pc("E"), note_pc("G"))):
            self.assertEqual(t["pitchClasses"][0], t["bassPitchClass"])
            self.assertEqual(t["pitchClasses"][0], bass_pc)


class TestInversionGrid(unittest.TestCase):
    """Phase B: the systematic 96-cell grid + per-measure correctness."""

    def setUp(self):
        self.root = build_curriculum()
        self.inv = self.root.find("cat:inversions")
        self.grid = [lf for lf in self.inv.leaves()
                     if lf.lab_spec.render == "block"
                     and lf.lab_spec.concept == "inversion"]

    def test_curriculum_count_matches_expected_minimum(self):
        # 96 block grid cells (4 major degrees + 4 minor degrees) x 12 keys.
        self.assertEqual(len(self.grid), 96)
        self.assertGreaterEqual(self.inv.exercise_count, 96)

    def test_grid_covers_required_degrees_in_all_keys(self):
        present = {(lf.lab_spec.mode, lf.lab_spec.key.split()[0],
                    str(lf.lab_spec.parameters["degree"])) for lf in self.grid}
        for deg in _MAJOR_INV_DEGREES:
            for k in DEFAULT_MAJOR_KEYS:
                self.assertIn(("major", k, deg), present)
        for deg in _MINOR_INV_DEGREES:
            for k in DEFAULT_MINOR_KEYS:
                self.assertIn(("natural_minor", k, deg), present)

    def test_every_inversion_has_exactly_three_measures(self):
        for lf in self.grid:
            exp = compile_lab(lf.lab_spec)
            self.assertEqual(len(exp.measures), 3, lf.id)
            self.assertEqual([m.annotation.figured_bass for m in exp.measures],
                             ["5/3", "6", "6/4"], lf.id)

    def test_every_measure_bass_is_the_inversion_chord_tone(self):
        for lf in self.grid:
            exp = compile_lab(lf.lab_spec)
            tones = exp.measures[0].annotation.chord_tones   # [root, third, fifth]
            for inv, m in enumerate(exp.measures):
                self.assertEqual(m.annotation.bass_note, tones[inv], (lf.id, inv))

    def test_no_duplicate_experiment_or_bridge_ids(self):
        exp_ids = [lf.lab_spec.experiment_id for lf in self.inv.leaves()]
        self.assertEqual([i for i, c in Counter(exp_ids).items() if c > 1], [])
        bridge_ids = [lf.lab_spec.to_exercise_specs()[0].exercise_id
                      for lf in self.inv.leaves()]
        self.assertEqual([i for i, c in Counter(bridge_ids).items() if c > 1], [])

    def test_enharmonic_keys_get_distinct_bridge_ids(self):
        # Regression: _ident used to strip '#', collapsing C# minor onto C minor.
        c_min = _inversion_spec("natural_minor", "C", "i").to_exercise_specs()[0]
        cs_min = _inversion_spec("natural_minor", "C#", "i").to_exercise_specs()[0]
        self.assertNotEqual(c_min.exercise_id, cs_min.exercise_id)

    def test_all_inversions_render_wellformed_musicxml(self):
        for lf in self.grid:
            xml = build_lab_musicxml(compile_lab(lf.lab_spec))
            root = ET.fromstring(xml)                     # raises if malformed
            self.assertEqual(len(list(root.iter("measure"))), 3, lf.id)

    def test_inversion_specs_helper_reuses_demo_for_c_major_one(self):
        specs = _inversion_curriculum_specs("major", "I")
        self.assertEqual(len(specs), 12)
        self.assertIn("inv_C_I", {s.experiment_id for s in specs})


if __name__ == "__main__":
    unittest.main(verbosity=2)
