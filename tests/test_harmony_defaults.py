"""Tests for the comprehensive default exercise sets (all 12 major + 12
natural-minor keys, block + arpeggio), the launcher grouping, and the
trainer payload they produce.

Run from the project root::

    .venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -t .

These verify the acceptance criteria for the expanded trainer:
  * every default spec validates and round-trips through JSON;
  * every default spec compiles to a non-empty chord stream within the
    readability cap;
  * every default spec builds well-formed MusicXML (and loads under Verovio);
  * every payload target carries chordTones, pitchClasses, roman, quality,
    intervalLayer and functionLabel;
  * arpeggio payloads map expected notes by beat; block payloads by measure;
  * practical enharmonic spelling is preserved (G major F#, F major Bb, ...).
"""

import os
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harmony.exercise_spec import (  # noqa: E402
    HarmonyExerciseSpec,
    compile_exercise,
    default_exercise_groups,
    all_default_specs,
    MAX_CHORDS_PER_SPEC,
    DEFAULT_MAJOR_KEYS,
    DEFAULT_MINOR_KEYS,
    GROUP_MAJOR_FULL_KEY,
    GROUP_MINOR_FULL_KEY,
    GROUP_DEGREE,
    GROUP_QUALITY,
    GROUP_FUNCTION,
    GROUP_ARPEGGIO,
)
from harmony.musicxml_builder import (  # noqa: E402
    build_musicxml,
    build_trainer_payload,
)

REQUIRED_TARGET_FIELDS = (
    "chordTones", "pitchClasses", "roman", "quality",
    "intervalLayer", "functionLabel",
)


def _chord_tones(spec):
    return {p for ch in compile_exercise(spec).chords for p in ch.triad.pitches}


class TestGroupStructure(unittest.TestCase):
    def test_group_names_and_order(self):
        self.assertEqual(
            list(default_exercise_groups().keys()),
            [GROUP_MAJOR_FULL_KEY, GROUP_MINOR_FULL_KEY, GROUP_DEGREE,
             GROUP_QUALITY, GROUP_FUNCTION, GROUP_ARPEGGIO],
        )

    def test_group_counts(self):
        g = default_exercise_groups()
        self.assertEqual(len(g[GROUP_MAJOR_FULL_KEY]), 12)   # 12 major keys
        self.assertEqual(len(g[GROUP_MINOR_FULL_KEY]), 12)   # 12 minor keys
        self.assertEqual(len(g[GROUP_DEGREE]), 14)           # 7 degrees x 2 modes
        # arpeggio = 12 + 12 full-key + 7 + 7 degree
        self.assertEqual(len(g[GROUP_ARPEGGIO]), 38)
        # every group is non-empty
        for name, specs in g.items():
            self.assertGreater(len(specs), 0, name)

    def test_groups_partition_with_unique_ids(self):
        # No spec appears in two groups; all ids unique.
        ids = [s.exercise_id for s in all_default_specs()]
        self.assertEqual(len(ids), len(set(ids)), "duplicate exercise ids")
        self.assertEqual(len(ids), 102)

    def test_full_key_groups_are_block_only(self):
        g = default_exercise_groups()
        for name in (GROUP_MAJOR_FULL_KEY, GROUP_MINOR_FULL_KEY, GROUP_DEGREE,
                     GROUP_QUALITY, GROUP_FUNCTION):
            for s in g[name]:
                self.assertEqual(s.render, "block", f"{name}/{s.exercise_id}")
        for s in g[GROUP_ARPEGGIO]:
            self.assertEqual(s.render, "arpeggio", s.exercise_id)


class TestAllSpecsValidateAndCompile(unittest.TestCase):
    def test_all_validate_and_round_trip(self):
        for s in all_default_specs():
            s.validate()                                   # raises on failure
            again = HarmonyExerciseSpec.from_dict(s.to_dict())
            self.assertEqual(again.exercise_id, s.exercise_id)
            self.assertEqual(again.drill, s.drill)
            self.assertEqual(again.render, s.render)

    def test_all_compile_nonempty_within_cap(self):
        for s in all_default_specs():
            compiled = compile_exercise(s)
            self.assertGreater(len(compiled), 0, s.exercise_id)
            self.assertLessEqual(
                len(compiled), MAX_CHORDS_PER_SPEC,
                f"{s.exercise_id} is {len(compiled)} chords (> cap)")

    def test_all_build_wellformed_musicxml(self):
        for s in all_default_specs():
            xml = build_musicxml(compile_exercise(s))
            ET.fromstring(xml)                             # raises if malformed


class TestPayloadContract(unittest.TestCase):
    def test_every_target_has_required_fields(self):
        for s in all_default_specs():
            payload = build_trainer_payload(compile_exercise(s))
            for t in payload["TARGET_CHORDS"]:
                for field in REQUIRED_TARGET_FIELDS:
                    self.assertIn(field, t, (s.exercise_id, field))
                    self.assertTrue(t[field], (s.exercise_id, field))
                self.assertEqual(len(t["chordTones"]), 3, s.exercise_id)
                self.assertEqual(len(t["pitchClasses"]), 3, s.exercise_id)

    def test_block_payload_maps_by_measure(self):
        block = next(s for s in all_default_specs() if s.render == "block")
        payload = build_trainer_payload(compile_exercise(block))
        expected = payload["EXPECTED_MIDI_BY_MEASURE_OR_BEAT"]
        # Block: each measure index maps to a flat list of 3 pitch classes.
        self.assertIsInstance(expected["0"], list)
        self.assertEqual(len(expected["0"]), 3)

    def test_arpeggio_payload_maps_by_beat(self):
        arp = next(s for s in all_default_specs() if s.render == "arpeggio")
        payload = build_trainer_payload(compile_exercise(arp))
        expected = payload["EXPECTED_MIDI_BY_MEASURE_OR_BEAT"]
        # Arpeggio: each measure index maps beat (1-based) -> single pitch class.
        first = expected["0"]
        self.assertIsInstance(first, dict)
        self.assertEqual(set(first.keys()), {"1", "2", "3"})
        for beat in ("1", "2", "3"):
            self.assertEqual(len(first[beat]), 1)

    def test_payload_target_count_matches_compiled(self):
        for s in all_default_specs():
            compiled = compile_exercise(s)
            payload = build_trainer_payload(compiled)
            self.assertEqual(len(payload["TARGET_CHORDS"]), len(compiled),
                             s.exercise_id)


class TestSpellingPreserved(unittest.TestCase):
    def test_g_major_uses_fsharp_not_gflat(self):
        g = default_exercise_groups()
        spec = next(s for s in g[GROUP_MAJOR_FULL_KEY] if s.key == "G major")
        tones = _chord_tones(spec)
        self.assertIn("F#", tones)
        self.assertNotIn("Gb", tones)

    def test_f_major_uses_bflat_not_asharp(self):
        g = default_exercise_groups()
        spec = next(s for s in g[GROUP_MAJOR_FULL_KEY] if s.key == "F major")
        tones = _chord_tones(spec)
        self.assertIn("Bb", tones)
        self.assertNotIn("A#", tones)

    def test_minor_full_key_uses_default_minor_spellings(self):
        g = default_exercise_groups()
        keys = sorted(parse_tonic(s.key) for s in g[GROUP_MINOR_FULL_KEY])
        self.assertEqual(keys, sorted(DEFAULT_MINOR_KEYS))

    def test_all_chord_tones_are_simple_spellings(self):
        # Diatonic major/natural-minor triads never need double accidentals.
        import re
        pat = re.compile(r"^[A-G](#|b)?$")
        for s in all_default_specs():
            for ch in compile_exercise(s).chords:
                for p in ch.triad.pitches:
                    self.assertRegex(p, pat, (s.exercise_id, p))


class TestVerovioLoadsRepresentatives(unittest.TestCase):
    def test_one_per_group_renders(self):
        try:
            import verovio
        except Exception as e:  # pragma: no cover
            self.skipTest(f"verovio not available: {e}")
        tk = verovio.toolkit()
        tk.setOptions({
            "pageHeight": 1800, "pageWidth": 1200, "scale": 40,
            "breaks": "auto", "adjustPageHeight": 1, "svgViewBox": 1,
        })
        for name, specs in default_exercise_groups().items():
            xml = build_musicxml(compile_exercise(specs[0]))
            self.assertTrue(tk.loadData(xml), f"Verovio failed to load {name}")
            svg = tk.renderToSVG(1)
            self.assertIn("<svg", svg)


def parse_tonic(key: str) -> str:
    """'Eb minor' -> 'Eb' (local helper to avoid importing private theory fns)."""
    return key.split()[0]


if __name__ == "__main__":
    unittest.main(verbosity=2)
