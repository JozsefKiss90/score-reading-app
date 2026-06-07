"""Smoke / integration tests for harmony.musicxml_builder.

These run headless (no Qt / no display).  They verify that:

* a MusicXML document is generated and is well-formed;
* the expected pitches / MIDI numbers appear in the score (the same pitches
  that flow into ``PITCH_MAP`` at runtime);
* Verovio can load and render the document;
* the trainer payload exposes the spec-mandated fields.
"""

import os
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harmony.exercise_spec import HarmonyExerciseSpec, compile_exercise  # noqa: E402
from harmony.musicxml_builder import (  # noqa: E402
    build_musicxml,
    build_trainer_payload,
    build_exercise,
)

_STEP_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _notes_by_measure(xml: str):
    """Return {measure_number: [(step, alter, octave, staff, is_chord), ...]}."""
    root = ET.fromstring(xml)
    out = {}
    for measure in root.iter("measure"):
        num = int(measure.attrib["number"])
        notes = []
        for note in measure.findall("note"):
            pitch = note.find("pitch")
            if pitch is None:
                continue
            step = pitch.findtext("step")
            alter = int(pitch.findtext("alter") or 0)
            octave = int(pitch.findtext("octave"))
            staff = int(note.findtext("staff") or 1)
            is_chord = note.find("chord") is not None
            notes.append((step, alter, octave, staff, is_chord))
        out[num] = notes
    return out


def _midi(step, alter, octave):
    return (octave + 1) * 12 + _STEP_PC[step] + alter


class TestMusicXmlGeneration(unittest.TestCase):
    def setUp(self):
        spec = HarmonyExerciseSpec(
            exercise_id="cmaj", title="C major triads",
            drill="full_key", mode="major", key="C major", render="block",
        )
        self.compiled = compile_exercise(spec)
        self.xml = build_musicxml(self.compiled)

    def test_well_formed_and_measure_count(self):
        root = ET.fromstring(self.xml)  # raises if malformed
        measures = list(root.iter("measure"))
        self.assertEqual(len(measures), 7)

    def test_first_measure_key_signature(self):
        root = ET.fromstring(self.xml)
        first = next(root.iter("measure"))
        fifths = first.find(".//key/fifths")
        self.assertIsNotNone(fifths)
        self.assertEqual(int(fifths.text), 0)

    def test_tonic_triad_pitches(self):
        notes = _notes_by_measure(self.xml)
        treble = [(s, a, o) for (s, a, o, staff, _) in notes[1] if staff == 1]
        steps = [s for (s, a, o) in treble]
        self.assertEqual(steps, ["C", "E", "G"])

    def test_dominant_triad_midi(self):
        # Measure 5 = V = G major triad (G-B-D), treble register.
        notes = _notes_by_measure(self.xml)
        treble = [(s, a, o) for (s, a, o, staff, _) in notes[5] if staff == 1]
        midis = [_midi(s, a, o) for (s, a, o) in treble]
        self.assertEqual(midis, [67, 71, 74])  # G4, B4, D5

    def test_chord_tones_marked(self):
        # Block triad: first treble note is not <chord/>, the next two are.
        notes = _notes_by_measure(self.xml)
        treble = [n for n in notes[1] if n[3] == 1]
        self.assertFalse(treble[0][4])
        self.assertTrue(treble[1][4])
        self.assertTrue(treble[2][4])

    def test_annotation_present(self):
        self.assertIn("C major | I | C | M3+m3 | tonic", self.xml)
        self.assertIn("C major | ii | Dm | m3+M3 | predominant", self.xml)


class TestArpeggioGeneration(unittest.TestCase):
    def test_arpeggio_has_three_quarters_and_rest(self):
        spec = HarmonyExerciseSpec(
            exercise_id="cmaj_arp", title="arp", drill="full_key",
            mode="major", key="C major", render="arpeggio",
        )
        xml = build_musicxml(compile_exercise(spec))
        root = ET.fromstring(xml)
        first = next(root.iter("measure"))
        # treble (staff 1, voice 1) should have 3 pitched quarters + 1 rest
        treble_pitched = 0
        treble_rests = 0
        for note in first.findall("note"):
            if note.findtext("staff") != "1":
                continue
            if note.find("rest") is not None:
                treble_rests += 1
            elif note.find("pitch") is not None:
                treble_pitched += 1
                self.assertEqual(note.findtext("type"), "quarter")
        self.assertEqual(treble_pitched, 3)
        self.assertEqual(treble_rests, 1)


class TestKeyChangesAcrossKeys(unittest.TestCase):
    def test_ii_v_i_key_signatures(self):
        spec = HarmonyExerciseSpec(
            exercise_id="iiVI", title="ii-V-I", drill="function",
            mode="major", pattern=["ii", "V", "I"], keys=["C", "G", "D"],
        )
        xml = build_musicxml(compile_exercise(spec))
        root = ET.fromstring(xml)
        # Collect the running key signature per measure.
        fifths_by_measure = {}
        current = None
        for measure in root.iter("measure"):
            ks = measure.find(".//key/fifths")
            if ks is not None:
                current = int(ks.text)
            fifths_by_measure[int(measure.attrib["number"])] = current
        # Measures 1-3 = C major (0), 4-6 = G major (1), 7-9 = D major (2).
        self.assertEqual(fifths_by_measure[1], 0)
        self.assertEqual(fifths_by_measure[4], 1)
        self.assertEqual(fifths_by_measure[7], 2)


class TestVerovioLoads(unittest.TestCase):
    def test_verovio_renders(self):
        try:
            import verovio
        except Exception as e:  # pragma: no cover
            self.skipTest(f"verovio not available: {e}")
        spec = HarmonyExerciseSpec(
            exercise_id="cmaj", title="C major", drill="full_key",
            mode="major", key="C major",
        )
        xml = build_musicxml(compile_exercise(spec))
        tk = verovio.toolkit()
        ok = tk.loadData(xml)
        self.assertTrue(ok, "Verovio failed to load generated MusicXML")
        svg = tk.renderToSVG(1)
        self.assertIn("<svg", svg)
        # Noteheads should be present in the rendered output.
        self.assertIn("note", svg)


class TestTrainerPayload(unittest.TestCase):
    def setUp(self):
        spec = HarmonyExerciseSpec(
            exercise_id="cmaj", title="C major", drill="full_key",
            mode="major", key="C major", render="block",
        )
        self.compiled = compile_exercise(spec)
        self.payload = build_trainer_payload(self.compiled)

    def test_spec_mandated_fields(self):
        for key in ("TRAINER_MODE", "TARGET_CHORDS", "TARGET_BY_MEASURE",
                    "EXPECTED_MIDI_BY_MEASURE_OR_BEAT"):
            self.assertIn(key, self.payload)
        self.assertTrue(self.payload["TRAINER_MODE"])

    def test_target_count_and_content(self):
        targets = self.payload["TARGET_CHORDS"]
        self.assertEqual(len(targets), 7)
        v = targets[4]
        self.assertEqual(v["chordSymbol"], "G")
        self.assertEqual(v["pitchClasses"], [7, 11, 2])
        self.assertEqual(v["intervalLayer"], "M3+m3")
        self.assertEqual(v["functionLabel"], "dominant")

    def test_expected_midi_block(self):
        expected = self.payload["EXPECTED_MIDI_BY_MEASURE_OR_BEAT"]
        # Block mode -> per-measure list of pitch classes.
        self.assertEqual(expected["4"], [7, 11, 2])  # measure idx 4 = V

    def test_expected_midi_arpeggio(self):
        spec = HarmonyExerciseSpec(
            exercise_id="arp", title="arp", drill="full_key",
            mode="major", key="C major", render="arpeggio",
        )
        payload = build_trainer_payload(compile_exercise(spec))
        expected = payload["EXPECTED_MIDI_BY_MEASURE_OR_BEAT"]
        # Arpeggio -> per-beat single pitch class. Measure idx 0 = I (C-E-G).
        self.assertEqual(expected["0"], {"1": [0], "2": [4], "3": [7]})

    def test_pitch_map_proxy_contains_expected_midi(self):
        # PITCH_MAP pitches are derived from these very notes; assert the
        # dominant chord's MIDI numbers are all present in the score.
        xml = build_musicxml(self.compiled)
        all_midi = set()
        for notes in _notes_by_measure(xml).values():
            for (s, a, o, staff, _) in notes:
                all_midi.add(_midi(s, a, o))
        for m in (67, 71, 74):  # G4 B4 D5
            self.assertIn(m, all_midi)


if __name__ == "__main__":
    unittest.main(verbosity=2)
