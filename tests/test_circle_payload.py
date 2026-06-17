"""Tests for the Circle-of-Fifths payload + click-to-exercise bridge
(harmony.circle_payload).

Covers Part 9 of the spec: payload structure, circle ordering, practical
spelling, and the spec bridge.  The JS rendering / trainer-sync is covered by
``tests/circle_node_test.js`` (headless Node).

Run from the project root::

    .venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -t .
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harmony.exercise_spec import compile_exercise, MAX_CHORDS_PER_SPEC  # noqa: E402
from harmony.circle_payload import (  # noqa: E402
    build_circle_payload,
    spec_from_circle_request,
    SCHEMA_VERSION,
    RESERVED_RELATIONS,
)

TRIAD_FIELDS = ("degree", "degreeNumber", "chordSymbol", "root", "quality",
                "tones", "intervalLayer", "functionLabel", "functionClass")


class TestPayloadStructure(unittest.TestCase):
    def setUp(self):
        self.p = build_circle_payload()

    def test_schema(self):
        self.assertEqual(self.p["schema"], SCHEMA_VERSION)

    def test_twelve_keys_each_mode(self):
        self.assertEqual(len(self.p["majorKeys"]), 12)
        self.assertEqual(len(self.p["minorKeys"]), 12)

    def test_every_key_has_seven_triads(self):
        for k in self.p["majorKeys"] + self.p["minorKeys"]:
            self.assertEqual(len(k["triads"]), 7, k["key"])

    def test_every_triad_has_required_fields(self):
        for k in self.p["majorKeys"] + self.p["minorKeys"]:
            for t in k["triads"]:
                for field in TRIAD_FIELDS:
                    self.assertIn(field, t, (k["key"], field))
                self.assertEqual(len(t["tones"]), 3, (k["key"], t["degree"]))
                self.assertIn(t["functionClass"], ("T", "S", "D"))

    def test_keys_have_relative_and_scale_and_fifths(self):
        for k in self.p["majorKeys"]:
            self.assertIn("relativeMinor", k)
            self.assertEqual(len(k["scale"]), 7)
            self.assertIsInstance(k["fifths"], int)
        for k in self.p["minorKeys"]:
            self.assertIn("relativeMajor", k)

    def test_reserved_relations_present(self):
        self.assertEqual(self.p["relations"], list(RESERVED_RELATIONS))
        for rel in ("relative_minor_of", "dominant_of", "resolves_to",
                    "transposes_to"):
            self.assertIn(rel, self.p["relations"])

    def test_cheatsheet_generated_from_theory(self):
        cs = self.p["cheatsheet"]
        self.assertEqual([t["degree"] for t in cs["majorPattern"]],
                         ["I", "ii", "iii", "IV", "V", "vi", "vii°"])
        self.assertEqual([t["degree"] for t in cs["minorPattern"]],
                         ["i", "ii°", "III", "iv", "v", "VI", "VII"])
        layers = {x["quality"]: x["intervalLayer"] for x in cs["intervalLayers"]}
        self.assertEqual(layers["major"], "M3+m3")
        self.assertEqual(layers["diminished"], "m3+m3")
        self.assertEqual(layers["augmented"], "M3+M3")


class TestCircleOrder(unittest.TestCase):
    def setUp(self):
        self.p = build_circle_payload()

    def test_major_order_is_fifths_based(self):
        self.assertEqual(
            self.p["circleOrderMajor"],
            ["C", "G", "D", "A", "E", "B", "Gb", "Db", "Ab", "Eb", "Bb", "F"])

    def test_minor_order_is_relative_minors(self):
        self.assertEqual(
            self.p["circleOrderMinor"],
            ["A", "E", "B", "F#", "C#", "G#", "Eb", "Bb", "F", "C", "G", "D"])

    def test_minor_order_matches_relative_of_major_order(self):
        rel = {k["key"]: k["relativeMinor"] for k in self.p["majorKeys"]}
        expected = [rel[k] for k in self.p["circleOrderMajor"]]
        self.assertEqual(self.p["circleOrderMinor"], expected)


class TestSpelling(unittest.TestCase):
    def setUp(self):
        self.major = {k["key"]: k for k in build_circle_payload()["majorKeys"]}
        self.minor = {k["key"]: k for k in build_circle_payload()["minorKeys"]}

    def test_g_major_uses_fsharp(self):
        self.assertIn("F#", self.major["G"]["scale"])
        self.assertNotIn("Gb", self.major["G"]["scale"])

    def test_f_major_uses_bflat(self):
        self.assertIn("Bb", self.major["F"]["scale"])

    def test_bflat_major_uses_eflat(self):
        self.assertIn("Eb", self.major["Bb"]["scale"])
        self.assertNotIn("D#", self.major["Bb"]["scale"])

    def test_e_major_four_sharps(self):
        self.assertTrue({"F#", "C#", "G#", "D#"}.issubset(set(self.major["E"]["scale"])))

    def test_a_minor_no_accidentals(self):
        for p in self.minor["A"]["scale"]:
            self.assertNotIn("#", p)
            self.assertNotIn("b", p)

    def test_e_minor_has_fsharp(self):
        self.assertIn("F#", self.minor["E"]["scale"])


class TestSpecBridge(unittest.TestCase):
    def test_full_key_block_c_major(self):
        spec = spec_from_circle_request(
            {"drill": "full_key", "render": "block", "mode": "major", "key": "C major"})
        self.assertEqual(spec.drill, "full_key")
        self.assertEqual(spec.render, "block")
        syms = [c.triad.chord_symbol for c in compile_exercise(spec).chords]
        self.assertEqual(syms, ["C", "Dm", "Em", "F", "G", "Am", "B°"])

    def test_horizontal_degree_arpeggio_v_major(self):
        spec = spec_from_circle_request(
            {"drill": "horizontal_degree", "render": "arpeggio", "mode": "major",
             "degree": "V"})
        self.assertEqual(spec.drill, "horizontal_degree")
        self.assertEqual(spec.render, "arpeggio")
        compiled = compile_exercise(spec)
        self.assertEqual(len(compiled), 12)                 # all 12 keys
        self.assertLessEqual(len(compiled), MAX_CHORDS_PER_SPEC)
        self.assertTrue(all(c.triad.roman == "V" for c in compiled.chords))

    def test_ids_keep_clean_render_token(self):
        # regression: _slug must not turn 'block' into 'flock'
        spec = spec_from_circle_request(
            {"drill": "full_key", "render": "block", "mode": "major", "key": "Bb major"})
        self.assertTrue(spec.exercise_id.endswith("_block"), spec.exercise_id)

    def test_quality_scoped_to_one_key_is_readable(self):
        # The circle scopes quality drills to the selected key (3 chords), so the
        # exercise stays within the cap.
        spec = spec_from_circle_request(
            {"drill": "quality", "render": "block", "mode": "major",
             "quality": "major", "keys": ["G"]})
        compiled = compile_exercise(spec)
        self.assertEqual(len(compiled), 3)                 # I, IV, V in G major
        self.assertTrue(all(c.triad.chord_quality == "major" for c in compiled.chords))

    def test_oversized_quality_request_is_rejected(self):
        # A quality drill spanning all 12 keys would be 36 chords -> rejected.
        with self.assertRaises(ValueError):
            spec_from_circle_request(
                {"drill": "quality", "render": "block", "mode": "major",
                 "quality": "major"})

    def test_oversized_function_request_is_rejected(self):
        # A 4-chord pattern across all 12 keys would be 48 chords -> rejected.
        with self.assertRaises(ValueError):
            spec_from_circle_request(
                {"drill": "function", "render": "block", "mode": "major",
                 "pattern": ["I", "IV", "V", "I"]})

    def test_scoped_function_request_is_accepted(self):
        spec = spec_from_circle_request(
            {"drill": "function", "render": "block", "mode": "major",
             "pattern": ["ii", "V", "I"], "keys": ["C", "G"]})
        self.assertEqual(len(compile_exercise(spec)), 6)   # 3 chords x 2 keys

    def test_invalid_requests_raise(self):
        for bad in (
            {"drill": "full_key", "mode": "major"},          # full_key needs key
            {"drill": "horizontal_degree", "mode": "major"},  # needs degree
            {"drill": "bogus"},                               # unknown drill
            {},                                               # no drill
            "not a dict",
        ):
            with self.assertRaises(ValueError):
                spec_from_circle_request(bad)


if __name__ == "__main__":
    unittest.main(verbosity=2)
