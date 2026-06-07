"""Unit tests for harmony.exercise_spec (the exercise compiler)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harmony.exercise_spec import (  # noqa: E402
    HarmonyExerciseSpec,
    compile_exercise,
    normalise_pattern,
    default_demo_specs,
    DEFAULT_MAJOR_KEYS,
)


def syms(compiled):
    return [c.triad.chord_symbol for c in compiled.chords]


class TestFullKeyDrill(unittest.TestCase):
    def test_c_major_full_key(self):
        spec = HarmonyExerciseSpec(
            exercise_id="x", title="C", drill="full_key",
            mode="major", key="C major",
        )
        compiled = compile_exercise(spec)
        self.assertEqual(syms(compiled), ["C", "Dm", "Em", "F", "G", "Am", "B°"])
        self.assertEqual(len(compiled), 7)
        self.assertTrue(all(c.render == "block" for c in compiled.chords))
        self.assertTrue(all(c.group == "C major" for c in compiled.chords))

    def test_full_key_infers_mode_from_key_string(self):
        spec = HarmonyExerciseSpec(
            exercise_id="x", title="Am", drill="full_key",
            mode="major", key="A minor",  # mode word in key overrides
        )
        compiled = compile_exercise(spec)
        self.assertEqual(syms(compiled), ["Am", "B°", "C", "Dm", "Em", "F", "G"])


class TestFunctionDrill(unittest.TestCase):
    def test_ii_v_i_three_keys(self):
        spec = HarmonyExerciseSpec(
            exercise_id="x", title="ii-V-I", drill="function",
            mode="major", pattern=["ii", "V", "I"], keys=["C", "G", "D"],
        )
        compiled = compile_exercise(spec)
        self.assertEqual(
            syms(compiled),
            ["Dm", "G", "C", "Am", "D", "G", "Em", "A", "D"],
        )
        # groups label the progression-in-key
        self.assertEqual(compiled.chords[0].group, "ii–V–I in C major")
        self.assertEqual(compiled.chords[3].group, "ii–V–I in G major")

    def test_function_letters_translate(self):
        self.assertEqual(normalise_pattern(["T", "S", "D", "T"]),
                         ["I", "IV", "V", "I"])

    def test_tsdt_progression(self):
        spec = HarmonyExerciseSpec(
            exercise_id="x", title="T-S-D-T", drill="function",
            mode="major", pattern=["T", "S", "D", "T"], keys=["C"],
        )
        compiled = compile_exercise(spec)
        self.assertEqual(syms(compiled), ["C", "F", "G", "C"])


class TestHorizontalAndQuality(unittest.TestCase):
    def test_all_v_major(self):
        spec = HarmonyExerciseSpec(
            exercise_id="x", title="V", drill="horizontal_degree",
            mode="major", degree="V",
        )
        compiled = compile_exercise(spec)
        self.assertEqual(len(compiled), 12)
        self.assertTrue(all(c.triad.roman == "V" for c in compiled.chords))
        self.assertTrue(all(c.triad.chord_quality == "major" for c in compiled.chords))
        # V of C major is G major.
        self.assertEqual(compiled.chords[0].triad.chord_symbol, "G")

    def test_quality_diminished_major(self):
        spec = HarmonyExerciseSpec(
            exercise_id="x", title="dim", drill="quality",
            mode="major", quality="diminished",
        )
        compiled = compile_exercise(spec)
        # Exactly one diminished triad (vii°) per major key.
        self.assertEqual(len(compiled), len(DEFAULT_MAJOR_KEYS))
        self.assertTrue(all(c.triad.chord_quality == "diminished"
                            for c in compiled.chords))


class TestRenderAndJson(unittest.TestCase):
    def test_arpeggio_flag(self):
        spec = HarmonyExerciseSpec(
            exercise_id="x", title="arp", drill="full_key",
            render="arpeggio", mode="natural_minor", key="A minor",
        )
        compiled = compile_exercise(spec)
        self.assertTrue(all(c.render == "arpeggio" for c in compiled.chords))

    def test_json_round_trip(self):
        for spec in default_demo_specs():
            d = spec.to_dict()
            again = HarmonyExerciseSpec.from_dict(d)
            self.assertEqual(again.exercise_id, spec.exercise_id)
            self.assertEqual(again.drill, spec.drill)
            self.assertEqual(again.render, spec.render)

    def test_validation_errors(self):
        with self.assertRaises(ValueError):
            HarmonyExerciseSpec(
                exercise_id="x", title="bad", drill="horizontal_degree",
            ).validate()

    def test_demo_specs_compile(self):
        for spec in default_demo_specs():
            compiled = compile_exercise(spec)
            self.assertGreater(len(compiled), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
