"""Unit tests for theory.diatonic_harmony.

Run from the project root::

    .venv/Scripts/python.exe -m unittest discover -s tests -t .

These tests encode the pedagogical contract verbatim (the exact expected
spellings, qualities, interval layers, and transpositions from the spec).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from theory.diatonic_harmony import (  # noqa: E402
    build_dominant_seventh,
    build_seventh_chord,
    generate_scale,
    generate_diatonic_triads,
    transpose_degree_pattern,
    identify_triad_from_pitches,
    key_signature_fifths,
    note_to_midi,
    parse_key,
    seventh_tokens_for_mode,
)


def triad_tuples(key, mode):
    """(root, chord_symbol, quality, [pitches]) for each diatonic triad."""
    return [
        (t.root, t.chord_symbol, t.chord_quality, list(t.pitches))
        for t in generate_diatonic_triads(key, mode)
    ]


def symbols(key, mode):
    return [t.chord_symbol for t in generate_diatonic_triads(key, mode)]


def romans(key, mode):
    return [t.roman for t in generate_diatonic_triads(key, mode)]


class TestScaleSpelling(unittest.TestCase):
    def test_c_major_scale(self):
        s = generate_scale("C", "major")
        self.assertEqual(s.scale_pitches, ["C", "D", "E", "F", "G", "A", "B"])
        self.assertEqual(s.fifths, 0)

    def test_g_major_has_fsharp(self):
        s = generate_scale("G", "major")
        self.assertEqual(s.scale_pitches, ["G", "A", "B", "C", "D", "E", "F#"])
        self.assertEqual(s.fifths, 1)

    def test_eb_major_uses_flats(self):
        s = generate_scale("Eb", "major")
        self.assertEqual(s.scale_pitches, ["Eb", "F", "G", "Ab", "Bb", "C", "D"])
        self.assertEqual(s.fifths, -3)

    def test_fsharp_major_spells_esharp(self):
        s = generate_scale("F#", "major")
        self.assertEqual(
            s.scale_pitches, ["F#", "G#", "A#", "B", "C#", "D#", "E#"]
        )
        self.assertEqual(s.fifths, 6)

    def test_a_natural_minor_scale(self):
        s = generate_scale("A", "natural_minor")
        self.assertEqual(s.scale_pitches, ["A", "B", "C", "D", "E", "F", "G"])
        self.assertEqual(s.fifths, 0)

    def test_mode_aliases(self):
        self.assertEqual(
            generate_scale("A", "minor").scale_pitches,
            generate_scale("A", "natural_minor").scale_pitches,
        )

    def test_all_12_major_keys_are_letter_complete(self):
        # Every major scale must use each of the 7 letters exactly once.
        for key in ["C", "Db", "D", "Eb", "E", "F",
                    "Gb", "G", "Ab", "A", "Bb", "B"]:
            letters = [p[0] for p in generate_scale(key, "major").scale_pitches]
            self.assertEqual(sorted(letters), list("ABCDEFG"),
                             f"{key} major has duplicate/missing letters")


class TestCMajorTriads(unittest.TestCase):
    def test_c_major_exact(self):
        self.assertEqual(symbols("C", "major"),
                         ["C", "Dm", "Em", "F", "G", "Am", "B°"])

    def test_c_major_romans(self):
        self.assertEqual(romans("C", "major"),
                         ["I", "ii", "iii", "IV", "V", "vi", "vii°"])

    def test_c_major_ii_is_d_f_a_not_fsharp(self):
        ii = generate_diatonic_triads("C", "major")[1]
        self.assertEqual(ii.pitches, ["D", "F", "A"])
        self.assertEqual(ii.chord_quality, "minor")
        self.assertEqual(ii.interval_layer, "m3+M3")


class TestGMajorTriads(unittest.TestCase):
    def test_g_major_v_is_d_fsharp_a(self):
        v = generate_diatonic_triads("G", "major")[4]
        self.assertEqual(v.root, "D")
        self.assertEqual(v.pitches, ["D", "F#", "A"])
        self.assertEqual(v.chord_quality, "major")
        self.assertEqual(v.chord_symbol, "D")
        self.assertEqual(v.roman, "V")
        self.assertEqual(v.function_label, "dominant")

    def test_g_major_includes_fsharp_chord(self):
        symbols_g = symbols("G", "major")
        self.assertEqual(symbols_g, ["G", "Am", "Bm", "C", "D", "Em", "F#°"])


class TestANaturalMinorTriads(unittest.TestCase):
    def test_a_natural_minor_exact(self):
        self.assertEqual(symbols("A", "natural_minor"),
                         ["Am", "B°", "C", "Dm", "Em", "F", "G"])

    def test_a_natural_minor_romans(self):
        self.assertEqual(romans("A", "natural_minor"),
                         ["i", "ii°", "III", "iv", "v", "VI", "VII"])

    def test_a_natural_minor_qualities(self):
        quals = [t.chord_quality for t in generate_diatonic_triads("A", "natural_minor")]
        self.assertEqual(
            quals,
            ["minor", "diminished", "major", "minor", "minor", "major", "major"],
        )

    def test_a_natural_minor_spelled_pitches(self):
        triads = generate_diatonic_triads("A", "natural_minor")
        self.assertEqual([t.pitches for t in triads], [
            ["A", "C", "E"],   # i
            ["B", "D", "F"],   # ii°
            ["C", "E", "G"],   # III
            ["D", "F", "A"],   # iv
            ["E", "G", "B"],   # v
            ["F", "A", "C"],   # VI
            ["G", "B", "D"],   # VII
        ])

    def test_c_natural_minor_spelled_pitches(self):
        # Flat-key minor: guards accidental spelling on the minor path.
        triads = generate_diatonic_triads("C", "natural_minor")
        self.assertEqual([t.pitches for t in triads], [
            ["C", "Eb", "G"],   # i
            ["D", "F", "Ab"],   # ii°
            ["Eb", "G", "Bb"],  # III
            ["F", "Ab", "C"],   # iv
            ["G", "Bb", "D"],   # v
            ["Ab", "C", "Eb"],  # VI
            ["Bb", "D", "F"],   # VII
        ])


class TestHarmonicMinor(unittest.TestCase):
    """Ticket 13 / plan G2a: the harmonic minor mode (raised leading tone)."""

    def test_a_harmonic_minor_scale(self):
        s = generate_scale("A", "harmonic_minor")
        self.assertEqual(s.scale_pitches, ["A", "B", "C", "D", "E", "F", "G#"])
        self.assertEqual(s.fifths, 0)  # raised 7th is an accidental, not in the signature

    def test_c_harmonic_minor_scale(self):
        s = generate_scale("C", "harmonic_minor")
        self.assertEqual(s.scale_pitches, ["C", "D", "Eb", "F", "G", "Ab", "B"])
        self.assertEqual(s.fifths, -3)

    def test_gsharp_harmonic_minor_needs_double_sharp(self):
        s = generate_scale("G#", "harmonic_minor")
        self.assertEqual(
            s.scale_pitches, ["G#", "A#", "B", "C#", "D#", "E", "F##"])

    def test_mode_alias_with_space(self):
        self.assertEqual(
            generate_scale("A", "harmonic minor").scale_pitches,
            generate_scale("A", "harmonic_minor").scale_pitches,
        )

    def test_plain_minor_alias_still_natural(self):
        self.assertEqual(
            generate_scale("A", "minor").scale_pitches,
            ["A", "B", "C", "D", "E", "F", "G"],
        )

    def test_parse_key_harmonic_minor(self):
        self.assertEqual(parse_key("A harmonic minor"), ("A", "harmonic_minor"))
        self.assertEqual(parse_key("A minor"), ("A", "natural_minor"))

    def test_a_harmonic_minor_symbols(self):
        self.assertEqual(symbols("A", "harmonic_minor"),
                         ["Am", "B°", "C+", "Dm", "E", "F", "G#°"])

    def test_a_harmonic_minor_romans(self):
        self.assertEqual(romans("A", "harmonic_minor"),
                         ["i", "ii°", "III+", "iv", "V", "VI", "vii°"])

    def test_a_harmonic_minor_qualities(self):
        quals = [t.chord_quality
                 for t in generate_diatonic_triads("A", "harmonic_minor")]
        self.assertEqual(
            quals,
            ["minor", "diminished", "augmented", "minor",
             "major", "major", "diminished"],
        )

    def test_v_is_a_real_major_dominant(self):
        v = generate_diatonic_triads("A", "harmonic_minor")[4]
        self.assertEqual(v.pitches, ["E", "G#", "B"])
        self.assertEqual(v.chord_quality, "major")
        self.assertEqual(v.roman, "V")
        self.assertEqual(v.function_label, "dominant")

    def test_vii_is_leading_tone_diminished(self):
        vii = generate_diatonic_triads("A", "harmonic_minor")[6]
        self.assertEqual(vii.pitches, ["G#", "B", "D"])
        self.assertEqual(vii.chord_quality, "diminished")
        self.assertEqual(vii.roman, "vii°")
        self.assertEqual(vii.scale_degree_name, "leading-tone")
        self.assertEqual(vii.function_label, "dominant")

    def test_function_labels_harmonic_minor(self):
        labels = [t.function_label
                  for t in generate_diatonic_triads("A", "harmonic_minor")]
        self.assertEqual(
            labels,
            ["tonic", "predominant", "mediant", "subdominant",
             "dominant", "tonic", "dominant"],
        )

    def test_i_iv_v_i_pattern_in_all_12_minor_keys(self):
        for key in ["A", "E", "B", "F#", "C#", "G#",
                    "Eb", "Bb", "F", "C", "G", "D"]:
            chords = transpose_degree_pattern(
                ["i", "iv", "V", "i"], key, "harmonic_minor")
            self.assertEqual(
                [c.chord_quality for c in chords],
                ["minor", "minor", "major", "minor"],
                f"{key} harmonic minor i–iv–V–i has wrong qualities")
            self.assertEqual([c.roman for c in chords], ["i", "iv", "V", "i"])

    def test_i_iv_v_i_in_a(self):
        chords = transpose_degree_pattern(["i", "iv", "V", "i"], "A", "harmonic_minor")
        self.assertEqual([c.chord_symbol for c in chords], ["Am", "Dm", "E", "Am"])

    def test_natural_minor_unchanged(self):
        self.assertEqual(romans("A", "natural_minor"),
                         ["i", "ii°", "III", "iv", "v", "VI", "VII"])

    def test_key_signature_fifths_harmonic_minor(self):
        self.assertEqual(key_signature_fifths("A", "harmonic_minor"), 0)
        self.assertEqual(key_signature_fifths("C", "harmonic_minor"), -3)


class TestHarmonicMinorSevenths(unittest.TestCase):
    def test_v7_builds_in_harmonic_minor(self):
        chord = build_seventh_chord("V7", "A", "harmonic_minor")
        self.assertEqual(chord.pitches, ["E", "G#", "B", "D"])
        self.assertEqual(chord.chord_quality, "dominant_seventh")
        self.assertEqual(chord.roman, "V7")

    def test_build_dominant_seventh_harmonic_minor(self):
        chord = build_dominant_seventh("C", "harmonic_minor")
        self.assertEqual(chord.pitches, ["G", "B", "D", "F"])
        self.assertEqual(chord.chord_symbol, "G7")

    def test_v7_still_refuses_natural_minor(self):
        with self.assertRaises(ValueError):
            build_seventh_chord("V7", "A", "natural_minor")

    def test_vii_dim7_builds_in_harmonic_minor(self):
        chord = build_seventh_chord("vii°7", "A", "harmonic_minor")
        self.assertEqual(chord.pitches, ["G#", "B", "D", "F"])
        self.assertEqual(chord.chord_quality, "diminished_seventh")
        self.assertEqual(chord.roman, "vii°7")

    def test_vii_dim7_refuses_major_and_natural_minor(self):
        with self.assertRaises(ValueError):
            build_seventh_chord("vii°7", "C", "major")       # viiø7, not °7
        with self.assertRaises(ValueError):
            build_seventh_chord("vii°7", "A", "natural_minor")  # VII7

    def test_seventh_tokens_for_harmonic_minor_are_honest(self):
        # Degrees 1/3/4/5/6 classify cleanly; the tonic (minor-major 7th) and
        # mediant (augmented-major 7th) tetrads have no supported quality and
        # therefore no token -- the vocabulary never lists a chord the engine
        # would refuse to build.
        self.assertEqual(seventh_tokens_for_mode("harmonic_minor"),
                         ["iiø7", "iv7", "V7", "VImaj7", "vii°7"])

    def test_seventh_tokens_other_modes_unchanged(self):
        self.assertEqual(
            seventh_tokens_for_mode("major"),
            ["Imaj7", "ii7", "iii7", "IVmaj7", "V7", "vi7", "viiø7"])
        self.assertEqual(
            seventh_tokens_for_mode("natural_minor"),
            ["i7", "iiø7", "IIImaj7", "iv7", "v7", "VImaj7", "VII7"])


class TestIntervalLayers(unittest.TestCase):
    def test_major_layer(self):
        a = identify_triad_from_pitches(["C", "E", "G"])
        self.assertEqual(a.chord_quality, "major")
        self.assertEqual(a.interval_layer, "M3+m3")
        self.assertEqual(a.root, "C")

    def test_minor_layer(self):
        a = identify_triad_from_pitches(["D", "F", "A"])
        self.assertEqual(a.chord_quality, "minor")
        self.assertEqual(a.interval_layer, "m3+M3")

    def test_diminished_layer(self):
        a = identify_triad_from_pitches(["B", "D", "F"])
        self.assertEqual(a.chord_quality, "diminished")
        self.assertEqual(a.interval_layer, "m3+m3")

    def test_augmented_layer(self):
        a = identify_triad_from_pitches(["C", "E", "G#"])
        self.assertEqual(a.chord_quality, "augmented")
        self.assertEqual(a.interval_layer, "M3+M3")

    def test_diatonic_layers_match_quality_table(self):
        expected = {
            "major": "M3+m3", "minor": "m3+M3",
            "diminished": "m3+m3", "augmented": "M3+M3",
        }
        for t in generate_diatonic_triads("C", "major"):
            self.assertEqual(t.interval_layer, expected[t.chord_quality])

    def test_identify_inversion_finds_root(self):
        # First inversion of C major (E-G-C) should still identify C as root.
        a = identify_triad_from_pitches(["E", "G", "C"])
        self.assertEqual(a.root, "C")
        self.assertEqual(a.chord_quality, "major")

    def test_identify_with_octaves(self):
        a = identify_triad_from_pitches(["G3", "B3", "D4"])
        self.assertEqual(a.root, "G")
        self.assertEqual(a.chord_quality, "major")

    def test_identify_with_context(self):
        a = identify_triad_from_pitches(["D", "F#", "A"], key="G major")
        self.assertEqual(a.roman, "V")
        self.assertEqual(a.function_label, "dominant")
        self.assertEqual(a.degree_index, 4)

    def test_identify_chromatic_chord_not_mislabelled(self):
        # D major in C major shares a root with ii (D minor) but is NOT ii.
        a = identify_triad_from_pitches(["D", "F#", "A"], key="C major")
        self.assertEqual(a.chord_quality, "major")
        self.assertEqual(a.chord_symbol, "D")
        self.assertIsNone(a.roman)            # not labelled "ii"
        self.assertNotIn("minor", a.explanation_text)

    def test_identify_enharmonic_explanation_consistent(self):
        # Db major == V in F# major (which spells it C#); explanation must use
        # the input's spelling, not contradict the reported root.
        a = identify_triad_from_pitches(["Db", "F", "Ab"], key="F# major")
        self.assertEqual(a.roman, "V")
        self.assertEqual(a.root, "Db")
        self.assertIn("Db", a.explanation_text)
        self.assertIn("enharmonic to C#", a.explanation_text)

    def test_identify_enharmonic_duplicate_is_unknown(self):
        # C and B# are the same pitch class -> only 2 distinct tones.
        a = identify_triad_from_pitches(["C", "B#", "E"])
        self.assertEqual(a.chord_quality, "unknown")
        self.assertIsNone(a.root)


class TestTransposition(unittest.TestCase):
    def test_ii_v_i_in_c(self):
        chords = transpose_degree_pattern(["ii", "V", "I"], "C", "major")
        self.assertEqual([c.chord_symbol for c in chords], ["Dm", "G", "C"])

    def test_ii_v_i_in_g(self):
        chords = transpose_degree_pattern(["ii", "V", "I"], "G", "major")
        self.assertEqual([c.chord_symbol for c in chords], ["Am", "D", "G"])

    def test_ii_v_i_in_d(self):
        chords = transpose_degree_pattern(["ii", "V", "I"], "D", "major")
        self.assertEqual([c.chord_symbol for c in chords], ["Em", "A", "D"])

    def test_i_iv_v_i_in_eb(self):
        chords = transpose_degree_pattern(["I", "IV", "V", "I"], "Eb", "major")
        self.assertEqual([c.chord_symbol for c in chords], ["Eb", "Ab", "Bb", "Eb"])

    def test_vii_token_with_symbol(self):
        chords = transpose_degree_pattern(["vii°"], "C", "major")
        self.assertEqual(chords[0].chord_symbol, "B°")


class TestMidiAndFunctions(unittest.TestCase):
    def test_midi_root_position_ascending(self):
        v = generate_diatonic_triads("G", "major")[4]  # D-F#-A
        self.assertEqual(v.midi_pitches, [62, 66, 69])

    def test_midi_helper(self):
        self.assertEqual(note_to_midi("C4"), 60)
        self.assertEqual(note_to_midi("A4"), 69)
        self.assertEqual(note_to_midi("E#4"), 65)  # enharmonic of F4

    def test_function_labels_major(self):
        labels = [t.function_label for t in generate_diatonic_triads("C", "major")]
        self.assertEqual(
            labels,
            ["tonic", "predominant", "mediant", "subdominant",
             "dominant", "tonic", "dominant"],
        )

    def test_function_labels_minor(self):
        labels = [t.function_label
                  for t in generate_diatonic_triads("A", "natural_minor")]
        self.assertEqual(
            labels,
            ["tonic", "predominant", "tonic", "subdominant",
             "dominant", "tonic", "dominant"],
        )

    def test_key_signature_fifths(self):
        self.assertEqual(key_signature_fifths("C", "major"), 0)
        self.assertEqual(key_signature_fifths("F#", "major"), 6)
        self.assertEqual(key_signature_fifths("Db", "major"), -5)
        self.assertEqual(key_signature_fifths("A", "natural_minor"), 0)
        self.assertEqual(key_signature_fifths("C", "natural_minor"), -3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
