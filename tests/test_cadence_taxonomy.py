"""Cadence taxonomy repair + the cadential 6/4 — ticket 16 / plan G3 (F8, F9).

Four seams:

* ``soprano_degrees`` on cadence/voice_leading specs — the SATB voicing puts a
  demanded scale degree in the soprano, which is what distinguishes a perfect
  authentic cadence (soprano ends on 1̂) from an imperfect one (3̂ / 5̂).
* ``dictation: "soprano"`` — the aural twin of ticket 11's bass dictation:
  hear the full SATB cadence, answer with only its top line.
* the Phrygian half cadence iv6–V (harmonic minor; the figure grades ♭6̂ in
  the bass falling to 5̂).
* the cadential 6/4: a tonic-spelled 6/4 before a dominant is annotated as
  dominant function, never plain tonic (fixes plan F3 at the engine level).

Run from the project root::

    .venv/Scripts/python.exe -m unittest tests.test_cadence_taxonomy
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from theory.diatonic_harmony import note_pc  # noqa: E402
from harmony.harmonic_roles import CADENCE_TYPES  # noqa: E402
from harmony.lab import compile_lab  # noqa: E402
from harmony.lab_spec import LabExperimentSpec  # noqa: E402
from harmony.lab_musicxml import build_lab_payload  # noqa: E402


def _spec(pattern, key="C major", mode="major", concept="cadence",
          render="voice_leading", **params):
    p = {"pattern": list(pattern)}
    p.update(params)
    return LabExperimentSpec(
        "t_cad_tax", "t", concept=concept, key=key, mode=mode, render=render,
        parameters=p)


def _soprano_line(exp):
    """The spelled soprano of each SATB measure (e.g. ['B4', 'C5'])."""
    return [dict(m.annotation.voices)["soprano"] for m in exp.measures]


def _pc_of(spelled):
    """'C5' / 'G#4' -> pitch class."""
    return note_pc(spelled.rstrip("0123456789"))


class TestCadenceTypeEnumG3(unittest.TestCase):
    def test_new_types_are_canonical(self):
        for t in ("perfect_authentic", "imperfect_authentic", "phrygian"):
            self.assertIn(t, CADENCE_TYPES, t)

    def test_new_types_accepted_by_lab_validate(self):
        _spec(("V", "I"), cadence_type="perfect_authentic",
              soprano_degrees=[7, 1]).validate()


class TestSopranoDegreesValidation(unittest.TestCase):
    def test_wrong_length_rejected(self):
        with self.assertRaises(ValueError):
            _spec(("V", "I"), soprano_degrees=[1]).validate()

    def test_out_of_range_degree_rejected(self):
        with self.assertRaises(ValueError):
            _spec(("V", "I"), soprano_degrees=[8, 1]).validate()

    def test_non_chord_tone_rejected(self):
        # 1̂ (C) is not a tone of V (G–B–D): demanding it would be dishonest.
        with self.assertRaises(ValueError):
            _spec(("V", "I"), soprano_degrees=[1, 1]).validate()

    def test_requires_voice_leading_render(self):
        # A block stack has no designated soprano.
        with self.assertRaises(ValueError):
            _spec(("V", "I"), render="block",
                  soprano_degrees=[7, 1]).validate()


class TestSopranoControl(unittest.TestCase):
    """PAC vs IAC: the same V–I, distinguished only by the demanded soprano."""

    def test_pac_soprano_ends_on_the_tonic(self):
        exp = compile_lab(_spec(("V", "I"), soprano_degrees=[7, 1],
                                cadence_type="perfect_authentic"))
        self.assertEqual(_soprano_line(exp), ["B4", "C5"])

    def test_iac_soprano_ends_on_the_third(self):
        exp = compile_lab(_spec(("V", "I"), soprano_degrees=[2, 3],
                                cadence_type="imperfect_authentic"))
        line = _soprano_line(exp)
        self.assertEqual(_pc_of(line[-1]), note_pc("E"))

    def test_iac_soprano_common_tone_fifth(self):
        # 5̂–5̂: the demanded rotation may octave-shift so the soprano is a
        # held common tone, not a register leap.
        exp = compile_lab(_spec(("V", "I"), soprano_degrees=[5, 5],
                                cadence_type="imperfect_authentic"))
        line = _soprano_line(exp)
        self.assertEqual(line[0], line[1])
        self.assertEqual(_pc_of(line[0]), note_pc("G"))

    def test_unconstrained_voicing_unchanged(self):
        # No soprano_degrees -> the classic smooth voicing is byte-stable
        # (existing catalogue VL leaves must not shift under this ticket).
        exp = compile_lab(_spec(("V", "I")))
        self.assertEqual(_soprano_line(exp), ["B4", "C5"])


class TestSopranoDictation(unittest.TestCase):
    def _dict_spec(self):
        return _spec(("V", "I"), soprano_degrees=[7, 1],
                     cadence_type="perfect_authentic", dictation="soprano")

    def test_validates_and_requires_voice_leading(self):
        self._dict_spec().validate()
        with self.assertRaises(ValueError):
            _spec(("V", "I"), render="block", dictation="soprano").validate()

    def test_unknown_dictation_still_rejected(self):
        with self.assertRaises(ValueError):
            _spec(("V", "I"), dictation="alto").validate()

    def test_targets_collapse_to_the_soprano_line(self):
        exp = compile_lab(self._dict_spec())
        self.assertEqual([m.target_pitch_classes for m in exp.measures],
                         [(note_pc("B"),), (note_pc("C"),)])
        for m in exp.measures:
            # soprano dictation never demands a *lowest*-note check
            self.assertFalse(m.strict_bass, m.index)

    def test_notation_keeps_the_full_chords(self):
        for m in compile_lab(self._dict_spec()).measures:
            self.assertGreaterEqual(len(m.sounding_midis()), 4, m.index)

    def test_payload_is_echo_with_dictation_flag(self):
        payload = build_lab_payload(compile_lab(self._dict_spec()))
        self.assertEqual(payload["PRESENTATION"], "echo")
        self.assertEqual(payload["DICTATION"], "soprano")


class TestPhrygianHalf(unittest.TestCase):
    def _phrygian(self, key="A minor"):
        return _spec(("iv6", "V"), key=key, mode="harmonic_minor",
                     render="block", cadence_type="phrygian")

    def test_validates(self):
        self._phrygian().validate()

    def test_bass_falls_a_semitone_to_the_dominant(self):
        # In A minor: iv6 puts F (♭6̂) in the bass, resolving down to E (5̂).
        exp = compile_lab(self._phrygian())
        basses = [m.bass_pitch_class for m in exp.measures]
        self.assertEqual(basses, [note_pc("F"), note_pc("E")])
        self.assertTrue(exp.measures[0].strict_bass)

    def test_phrygian_needs_the_real_minor_v(self):
        # Natural minor's dominant is v (minor): the Phrygian half needs
        # harmonic minor, and validate must not silently accept "V" there.
        with self.assertRaises(ValueError):
            _spec(("iv6", "V7"), key="A minor", mode="natural_minor",
                  render="block").validate()


class TestCadential64Annotation(unittest.TestCase):
    def _c64(self):
        return _spec(("IV", "I64", "V7", "I"), render="block",
                     cadence_type="authentic")

    def test_tonic_64_before_dominant_annotated_as_dominant_function(self):
        exp = compile_lab(self._c64())
        note = exp.measures[1].annotation.lab_note
        self.assertIn("Cadential 6/4", note)
        self.assertIn("dominant", note)

    def test_bass_holds_the_dominant_under_the_64(self):
        exp = compile_lab(self._c64())
        self.assertEqual(exp.measures[1].bass_pitch_class, note_pc("G"))
        self.assertEqual(exp.measures[2].bass_pitch_class, note_pc("G"))

    def test_plain_second_inversion_not_mislabelled(self):
        # I64 NOT followed by a dominant keeps its ordinary inversion note.
        exp = compile_lab(_spec(("I64", "IV"), render="block"))
        self.assertNotIn("Cadential 6/4",
                         exp.measures[0].annotation.lab_note)

    def test_measure_bit_carries_the_honest_function_word(self):
        # The 6/4 measure's leading annotation bit must not say plain
        # "tonic" — the whole point of the lesson.
        note = compile_lab(self._c64()).measures[1].annotation.lab_note
        self.assertIn("dominant (cadential 6/4)", note)


class TestCadential64Relabel(unittest.TestCase):
    """The relabel drill: identical sounds, honest display tokens."""

    def _relabel(self):
        return _spec(("IV", "I64", "V7", "I"), render="block",
                     cadence_type="authentic",
                     relabel=["IV", "V(6–4)", "V7(5–3)", "I"])

    def test_relabel_length_must_match_pattern(self):
        with self.assertRaises(ValueError):
            _spec(("V", "I"), render="block", relabel=["V"]).validate()

    def test_relabel_changes_annotation_not_sound(self):
        plain = compile_lab(_spec(("IV", "I64", "V7", "I"), render="block",
                                  cadence_type="authentic"))
        rel = compile_lab(self._relabel())
        # Identical sounds and grading …
        for a, b in zip(plain.measures, rel.measures):
            self.assertEqual(a.sounding_midis(), b.sounding_midis())
            self.assertEqual(a.target_pitch_classes, b.target_pitch_classes)
        # … but the 6/4 measure is now CALLED what it is.
        self.assertIn("V(6–4)", rel.measures[1].annotation.lab_note)
        self.assertIn("V7(5–3)", rel.measures[2].annotation.lab_note)

    def test_relabel_leaves_bridge_ids_unchanged(self):
        self.assertEqual(
            [s.exercise_id for s in self._relabel().to_exercise_specs()],
            [s.exercise_id for s in
             _spec(("IV", "I64", "V7", "I"), render="block",
                   cadence_type="authentic").to_exercise_specs()])


class TestCurriculumG3(unittest.TestCase):
    """The G3 lessons and leaves as wired into the Cadences category."""

    @classmethod
    def setUpClass(cls):
        from harmony.curriculum import build_curriculum
        cls.root = build_curriculum()
        cls.cadences = cls.root.find("cat:cadences")

    def _leaf(self, lid):
        n = self.root.find(lid)
        self.assertIsNotNone(n, lid)
        return n

    def test_pac_iac_leaves_and_ear_twins(self):
        for slug, ctype in (("pac", "perfect_authentic"),
                            ("iac3", "imperfect_authentic"),
                            ("iac5", "imperfect_authentic")):
            eye = self._leaf(f"ex:cad_{slug}_C")
            ear = self._leaf(f"ex:cad_{slug}_eardict_C")
            self.assertEqual(eye.lab_spec.parameters["cadence_type"], ctype)
            self.assertEqual(ear.lab_spec.parameters["dictation"], "soprano")
            self.assertIn(ear.id, eye.related)
            self.assertIn(eye.id, ear.related)

    def test_half_family_catalogue_members_exist(self):
        # ii–V and IV–V are catalogue entries: block + SATB variants each.
        for exp_id in ("drill_atlas_function_ii_V_major_C",
                       "drill_atlas_function_IV_V_major_C",
                       "cad_ii_V_C", "cad_IV_V_C"):
            self._leaf(f"ex:{exp_id}")

    def test_minor_halves_and_phrygian(self):
        for i in (1, 2):
            lf = self._leaf(f"ex:drill_halfcad_i_V_{i}")
            es = lf.lab_spec.to_exercise_specs()[0]
            self.assertEqual(es.mode, "harmonic_minor")
            self.assertEqual(es.pattern, ["i", "V"])
        for k in ("A", "E", "D"):
            lf = self._leaf(f"ex:cad_phrygian_iv6_V_{k}")
            self.assertEqual(lf.lab_spec.parameters["cadence_type"],
                             "phrygian")

    def test_cadential_64_pairs_cross_link(self):
        for k in ("C", "G", "F"):
            a = self._leaf(f"ex:cad_c64_{k}")
            b = self._leaf(f"ex:cad_c64_relabel_{k}")
            self.assertEqual(a.lab_spec.parameters["pattern"],
                             b.lab_spec.parameters["pattern"])
            self.assertIn(b.id, a.related)
            self.assertIn(a.id, b.related)

    def test_cadential_64_lesson_explains_the_relabel(self):
        lesson = self._leaf("lesson:cadential_64")
        self.assertIn("suspension", lesson.theory)
        self.assertIn("DOMINANT", lesson.theory)

    def test_reflex_drills_are_echo_mcq(self):
        for slug in ("v_i", "v_vi"):
            lf = self._leaf(f"ex:drill_cadence_ear_{slug}")
            es = lf.lab_spec.to_exercise_specs()[0]
            self.assertEqual(es.presentation, "echo")
            self.assertEqual(es.answer_mode, "mcq")
            self.assertEqual(es.mcq_focus, "roman")

    def test_orbits_cover_every_two_chord_type(self):
        orbit = self._leaf("lesson:cadence_orbits")
        leaves = list(orbit.leaves())
        self.assertEqual(len(leaves), 16)   # (6 major + 2 minor types) x 2 sets
        keys_seen = set()
        for lf in leaves:
            es = lf.lab_spec.to_exercise_specs()[0]
            keys_seen.update(es.keys or ())
        self.assertGreaterEqual(len(keys_seen), 12)

    def test_new_atlas_half_nodes_are_mapped(self):
        # The new catalogue entries resolve to real Atlas cadence nodes.
        for exp_id, node in (("drill_atlas_function_ii_V_major_C",
                              "cadence:ii_V_major"),
                             ("drill_atlas_function_IV_V_major_C",
                              "cadence:IV_V_major")):
            self.assertIn(node, self._leaf(f"ex:{exp_id}").atlas_nodes)


if __name__ == "__main__":
    unittest.main()
