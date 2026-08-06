"""Melodic minor + III+ (ticket 14 / plan G2b).

Two arrivals, one honesty rule:

* **Melodic minor** enters the engine as a *scale form*, not a harmony mode:
  ``generate_scale`` builds the ascending form (raised 6̂ and 7̂), the
  descending form IS natural minor, and the direction-dependent choice is the
  pure seam :func:`theory.diatonic_harmony.melodic_minor_raised`.  Chord
  generation refuses the mode outright — no single chord set is honest for a
  two-way scale — so the only launchable melodic-minor drill is the motive
  lab's ascent/descent melody.
* **III+** becomes the first *legitimate* augmented triad: the augmented
  quality drill validates and compiles in ``harmonic_minor`` mode (12 real
  III+ chords), replacing ticket 03's blanket rejection.  The °7 quality
  drill un-reserves the same way (vii°7).  Both stay clearly refused in
  major / natural minor, where they would compile to zero chords.

Run from the project root::

    .venv/Scripts/python.exe -m unittest tests.test_melodic_minor -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from theory.diatonic_harmony import (  # noqa: E402
    generate_scale,
    generate_diatonic_triads,
    generate_diatonic_sevenths,
    melodic_minor_raised,
    parse_key,
    _canon_mode,
)
from harmony.exercise_spec import (  # noqa: E402
    HarmonyExerciseSpec,
    compile_exercise,
)
from harmony.lab_spec import LabExperimentSpec  # noqa: E402
from harmony.lab import compile_lab  # noqa: E402
from harmony.curriculum import build_curriculum  # noqa: E402


# ---------------------------------------------------------------------------
# Theory: the melodic-minor scale form
# ---------------------------------------------------------------------------

class TestMelodicMinorScale(unittest.TestCase):
    def test_ascending_form_raises_6_and_7(self):
        s = generate_scale("A", "melodic_minor")
        self.assertEqual(s.scale_pitches, ["A", "B", "C", "D", "E", "F#", "G#"])

    def test_key_stays_minor_with_natural_signature(self):
        # Like harmonic minor (ticket 13): the *key* is still "A minor" and
        # the signature is natural minor's; raised notes are accidentals.
        s = generate_scale("A", "melodic_minor")
        self.assertEqual(s.key, "A minor")
        self.assertEqual(s.fifths, 0)
        self.assertEqual(generate_scale("C", "melodic_minor").fifths, -3)

    def test_parse_key_and_canon_mode(self):
        self.assertEqual(parse_key("A melodic minor"), ("A", "melodic_minor"))
        self.assertEqual(_canon_mode("melodic_minor"), "melodic_minor")
        self.assertEqual(_canon_mode("melodic"), "melodic_minor")
        # A plain "minor" NEVER implies a raised degree.
        self.assertEqual(parse_key("A minor"), ("A", "natural_minor"))

    def test_spelling_in_flat_key(self):
        # C melodic minor ascending: raised 6̂/7̂ are A-natural / B-natural.
        s = generate_scale("C", "melodic_minor")
        self.assertEqual(s.scale_pitches, ["C", "D", "Eb", "F", "G", "A", "B"])


class TestMelodicMinorRaised(unittest.TestCase):
    """The direction rule: 6̂/7̂ raised while the line ascends, natural while
    it descends; every other degree is never raised."""

    def test_full_ascent_raises_both(self):
        self.assertEqual(
            melodic_minor_raised([1, 2, 3, 4, 5, 6, 7, 8]),
            [False, False, False, False, False, True, True, False])

    def test_full_descent_raises_nothing(self):
        self.assertEqual(
            melodic_minor_raised([8, 7, 6, 5, 4, 3, 2, 1]),
            [False] * 8)

    def test_turn_cell_shows_both_forms(self):
        # 5–6–7–8–7–6–5: up raised, down natural.
        self.assertEqual(
            melodic_minor_raised([5, 6, 7, 8, 7, 6, 5]),
            [False, True, True, False, False, False, False])

    def test_leading_tone_neighbour_is_raised(self):
        # 8–7–8: the 7̂ turns back up, so it is a true leading tone.
        self.assertEqual(melodic_minor_raised([8, 7, 8]),
                         [False, True, False])

    def test_final_note_follows_direction_of_arrival(self):
        self.assertEqual(melodic_minor_raised([5, 6]), [False, True])
        self.assertEqual(melodic_minor_raised([8, 7]), [False, False])

    def test_octave_folding(self):
        # 12–13–14–15 is 5–6–7–8 an octave up.
        self.assertEqual(melodic_minor_raised([12, 13, 14, 15]),
                         [False, True, True, False])


class TestMelodicMinorHarmonyRefused(unittest.TestCase):
    """Melodic minor is a two-way scale form: no single diatonic chord set is
    honest, so chord generation refuses rather than picking a form."""

    def test_triads_refuse(self):
        with self.assertRaises(ValueError) as ctx:
            generate_diatonic_triads("A", "melodic_minor")
        self.assertIn("melodic minor", str(ctx.exception))

    def test_sevenths_refuse(self):
        with self.assertRaises(ValueError):
            generate_diatonic_sevenths("A", "melodic_minor")

    def test_trainer_spec_refuses_melodic_minor_mode(self):
        spec = HarmonyExerciseSpec(
            exercise_id="t_mm_fullkey", title="t", drill="full_key",
            mode="melodic_minor", key="A minor")
        with self.assertRaises(ValueError) as ctx:
            spec.validate()
        self.assertIn("motive", str(ctx.exception))   # points at the drill that exists

    def test_lab_spec_refuses_melodic_minor_outside_motive(self):
        spec = LabExperimentSpec(
            experiment_id="t_mm_cad", title="t", concept="cadence",
            mode="melodic_minor", key="A minor", render="block",
            parameters={"pattern": ["V", "i"]})
        with self.assertRaises(ValueError) as ctx:
            spec.validate()
        self.assertIn("motive", str(ctx.exception))


# ---------------------------------------------------------------------------
# Lab: the ascent/descent motive drill
# ---------------------------------------------------------------------------

def _motive_spec(degrees, keys=None):
    spec = LabExperimentSpec(
        experiment_id="t_mm_motive", title="t", concept="motive",
        mode="melodic_minor", key="A minor", render="melody",
        parameters={"degrees": list(degrees),
                    **({"keys": list(keys)} if keys else {})})
    spec.validate()
    return spec


class TestMelodicMinorMotive(unittest.TestCase):
    def test_ascent_sounds_raised_6_and_7(self):
        exp = compile_lab(_motive_spec([1, 2, 3, 4, 5, 6, 7, 8], keys=["A"]))
        m = exp.measures[0]
        # A B C D E F# G# A
        self.assertEqual(list(m.target_pitch_classes),
                         [9, 11, 0, 2, 4, 6, 8, 9])

    def test_descent_sounds_natural_form(self):
        exp = compile_lab(_motive_spec([8, 7, 6, 5, 4, 3, 2, 1], keys=["A"]))
        m = exp.measures[0]
        # A G F E D C B A
        self.assertEqual(list(m.target_pitch_classes),
                         [9, 7, 5, 4, 2, 0, 11, 9])

    def test_turn_cell_sounds_both_forms_in_one_bar(self):
        exp = compile_lab(_motive_spec([5, 6, 7, 8, 7, 6, 5], keys=["A"]))
        m = exp.measures[0]
        # E F# G# A G F E
        self.assertEqual(list(m.target_pitch_classes), [4, 6, 8, 9, 7, 5, 4])

    def test_key_context_stays_natural_minor(self):
        exp = compile_lab(_motive_spec([5, 6, 7, 8, 7, 6, 5], keys=["A"]))
        m = exp.measures[0]
        self.assertEqual(m.key_display, "A minor")
        self.assertEqual(m.fifths, 0)
        # The measure's scale field carries the key signature's (natural) form;
        # raised notes are per-note accidentals, and the Atlas claim is the
        # natural-minor scale node (the Atlas has no melodic-minor nodes).
        self.assertEqual(list(m.scale_pitches),
                         ["A", "B", "C", "D", "E", "F", "G"])
        self.assertEqual(m.annotation.atlas_scale_id, "scale:A:natural_minor")

    def test_default_sweep_is_the_12_minor_keys_and_no_chord_drill(self):
        spec = _motive_spec([5, 6, 7, 8, 7, 6, 5])
        exp = compile_lab(spec)
        self.assertEqual(len(exp.measures), 12)
        self.assertEqual(spec.to_exercise_specs(), [])


# ---------------------------------------------------------------------------
# III+ (and vii°7): the quality drills un-reserved for harmonic minor
# ---------------------------------------------------------------------------

def _quality_spec(quality, mode, keys):
    return HarmonyExerciseSpec(
        exercise_id=f"t_{quality}_{mode}", title="t", drill="quality",
        mode=mode, quality=quality, keys=keys)


class TestAugmentedUnreserved(unittest.TestCase):
    def test_augmented_validates_and_compiles_in_harmonic_minor(self):
        spec = _quality_spec("augmented", "harmonic_minor",
                             ["A", "Bb", "B", "C", "C#", "D", "Eb", "E", "F",
                              "F#", "G", "G#"])
        spec.validate()                       # ticket 03's rejection is lifted
        compiled = compile_exercise(spec)
        self.assertEqual(len(compiled), 12)   # exactly one III+ per key
        for c in compiled.chords:
            self.assertEqual(c.triad.chord_quality, "augmented")
            self.assertEqual(c.triad.roman, "III+")
            self.assertEqual(c.triad.interval_layer, "M3+M3")

    def test_a_minor_iii_aug_is_c_e_gsharp(self):
        compiled = compile_exercise(
            _quality_spec("augmented", "harmonic_minor", ["A"]))
        self.assertEqual(compiled.chords[0].triad.pitches, ["C", "E", "G#"])
        self.assertEqual(compiled.chords[0].triad.chord_symbol, "C+")

    def test_augmented_still_refused_in_major_and_natural_minor(self):
        for mode, key in (("major", "C"), ("natural_minor", "A")):
            with self.assertRaises(ValueError, msg=mode) as ctx:
                _quality_spec("augmented", mode, [key]).validate()
            self.assertIn("zero chords", str(ctx.exception))
            self.assertIn("harmonic_minor", str(ctx.exception))

    def test_diminished_seventh_validates_and_compiles_in_harmonic_minor(self):
        spec = _quality_spec("diminished_seventh", "harmonic_minor", ["A", "C"])
        spec.validate()
        compiled = compile_exercise(spec)
        self.assertEqual(len(compiled), 2)    # one vii°7 per key
        for c in compiled.chords:
            self.assertEqual(c.triad.roman, "vii°7")
            self.assertEqual(len(c.triad.pitches), 4)

    def test_diminished_seventh_still_refused_elsewhere(self):
        for mode, key in (("major", "C"), ("natural_minor", "A")):
            with self.assertRaises(ValueError, msg=mode):
                _quality_spec("diminished_seventh", mode, [key]).validate()

    def test_quality_scene_routes_the_augmented_drill(self):
        from harmony.graph_scene_generators import build_quality_class_scene
        spec = _quality_spec("augmented", "harmonic_minor", ["A", "E", "C"])
        spec.validate()
        scene = build_quality_class_scene(spec)
        self.assertEqual(scene.scene_type, "triad_quality_class")
        instances = [n for n in scene.nodes if n.entity_role == "instance"]
        self.assertEqual(len(instances), 3)
        self.assertTrue(all(n.quality == "augmented" for n in instances))


# ---------------------------------------------------------------------------
# Curriculum wiring
# ---------------------------------------------------------------------------

class TestCurriculumWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = build_curriculum()

    def test_melodic_minor_category_ships_three_motive_leaves(self):
        cat = self.root.find("cat:melodic_minor")
        self.assertIsNotNone(cat)
        self.assertFalse(cat.reserved)
        self.assertEqual(cat.exercise_count, 3)
        for lf in cat.leaves():
            self.assertEqual(lf.lab_spec.concept, "motive")
            self.assertEqual(lf.lab_spec.mode, "melodic_minor")

    def test_augmented_group_is_unreserved_with_a_real_drill(self):
        grp = self.root.find("group:triads_aug")
        self.assertIsNotNone(grp)
        self.assertFalse(grp.reserved)
        leaves = grp.leaves()
        self.assertEqual(len(leaves), 1)
        es = leaves[0].lab_spec.to_exercise_specs()[0]
        self.assertEqual(es.drill, "quality")
        self.assertEqual(es.quality, "augmented")
        self.assertEqual(es.mode, "harmonic_minor")
        self.assertEqual(len(compile_exercise(es)), 12)

    def test_melodic_minor_graduated_from_advanced_topics(self):
        advanced = self.root.find("cat:advanced")
        self.assertIsNotNone(advanced)
        self.assertIsNone(self.root.find("lesson:adv_melodic_minor"))
        # the remaining reserved seams are untouched
        for lid in ("lesson:adv_modal", "lesson:adv_jazz",
                    "lesson:adv_secondary"):
            self.assertIsNotNone(self.root.find(lid), lid)

    def test_motive_leaf_refs_resolve_to_natural_minor_context(self):
        cat = self.root.find("cat:melodic_minor")
        for lf in cat.leaves():
            self.assertTrue(lf.atlas_nodes, lf.id)
            for ref in lf.atlas_nodes:
                self.assertNotIn("melodic_minor", ref, lf.id)
            self.assertTrue(lf.circle_nodes, lf.id)
            for ref in lf.circle_nodes:
                self.assertNotIn("melodic_minor", ref, lf.id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
