"""Validation hardening for hand-authored / bridge-supplied exercise specs.

Plan F5/F6 (docs/curriculum_expansion_plan.md §1.2, ticket 03): a spec can no
longer crash the renderer or silently overflow the visible page.

  * F5 — an augmented-quality spec fails ``validate()`` with an explanatory
    error instead of compiling to zero chords and crashing the score builder
    (augmented triads are not diatonic to major or natural minor; they arrive
    legitimately with harmonic minor's III+).
  * F6 — a spec that would compile past :data:`MAX_CHORDS_PER_SPEC` fails
    ``validate()``; chords past the cap would render on a hidden second
    Verovio page.  No override flag exists yet (that arrives with ticket 31).

Both gates are exercised at every arrival path: direct ``validate()``, custom
JSON files (``load_specs``), and the Circle-of-Fifths click bridge
(``spec_from_circle_request``).

Run from the project root::

    .venv/Scripts/python.exe -m unittest tests.test_spec_validation
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harmony.exercise_spec import (  # noqa: E402
    HarmonyExerciseSpec,
    compile_exercise,
    load_specs,
    MAX_CHORDS_PER_SPEC,
)
from harmony.circle_payload import spec_from_circle_request  # noqa: E402


def _quality_spec(quality, keys=None):
    return HarmonyExerciseSpec(
        exercise_id=f"t_quality_{quality}", title="t", drill="quality",
        mode="major", quality=quality, keys=keys)


class TestAugmentedRejected(unittest.TestCase):
    """F5: augmented specs are rejected at validate(), with an explanation."""

    def test_augmented_fails_validation_with_explanatory_error(self):
        with self.assertRaises(ValueError) as ctx:
            _quality_spec("augmented", keys=["C"]).validate()
        msg = str(ctx.exception)
        self.assertIn("augmented", msg)
        self.assertIn("zero chords", msg)      # says *why*, not just "invalid"

    def test_augmented_rejected_in_minor_mode_too(self):
        spec = HarmonyExerciseSpec(
            exercise_id="t_aug_minor", title="t", drill="quality",
            mode="natural_minor", quality="augmented", keys=["A"])
        with self.assertRaises(ValueError):
            spec.validate()

    def test_other_qualities_still_validate(self):
        for quality in ("major", "minor", "diminished"):
            _quality_spec(quality, keys=["C"]).validate()   # must not raise

    def test_unknown_quality_still_rejected(self):
        with self.assertRaises(ValueError):
            _quality_spec("half_diminished", keys=["C"]).validate()


class TestCapEnforced(unittest.TestCase):
    """F6: specs past MAX_CHORDS_PER_SPEC fail validate(); 12 exactly is fine."""

    def test_thirteen_chord_spec_fails_validation(self):
        spec = HarmonyExerciseSpec(
            exercise_id="t_13", title="t", drill="function", mode="major",
            pattern=["I"] * (MAX_CHORDS_PER_SPEC + 1), keys=["C"])
        with self.assertRaises(ValueError) as ctx:
            spec.validate()
        msg = str(ctx.exception)
        self.assertIn(f"{MAX_CHORDS_PER_SPEC + 1} chords", msg)
        self.assertIn(str(MAX_CHORDS_PER_SPEC), msg)   # names the cap

    def test_unscoped_quality_drill_fails_validation(self):
        # Three major triads per key x 12 default keys = 36 chords.
        with self.assertRaises(ValueError):
            _quality_spec("major").validate()

    def test_unscoped_function_pattern_fails_validation(self):
        # Four chords x 12 default keys = 48 chords.
        spec = HarmonyExerciseSpec(
            exercise_id="t_unscoped_fn", title="t", drill="function",
            mode="major", pattern=["I", "IV", "V", "I"])
        with self.assertRaises(ValueError):
            spec.validate()

    def test_exactly_twelve_chord_function_spec_passes(self):
        spec = HarmonyExerciseSpec(
            exercise_id="t_12_fn", title="t", drill="function", mode="major",
            pattern=["I"] * MAX_CHORDS_PER_SPEC, keys=["C"])
        spec.validate()                                    # must not raise
        self.assertEqual(len(compile_exercise(spec)), MAX_CHORDS_PER_SPEC)

    def test_exactly_twelve_chord_degree_spec_passes(self):
        spec = HarmonyExerciseSpec(
            exercise_id="t_12_deg", title="t", drill="horizontal_degree",
            mode="major", degree="V")                      # all 12 default keys
        spec.validate()                                    # must not raise
        self.assertEqual(len(compile_exercise(spec)), MAX_CHORDS_PER_SPEC)

    def test_exactly_twelve_chord_quality_spec_passes(self):
        # Three major triads per key x 4 keys = 12 chords exactly.
        spec = _quality_spec("major", keys=["C", "G", "D", "A"])
        spec.validate()                                    # must not raise
        self.assertEqual(len(compile_exercise(spec)), MAX_CHORDS_PER_SPEC)


class TestEnforcedCountMirrorsCompiler(unittest.TestCase):
    """Drift test: the chord count validate() enforces must be the count the
    compiler actually emits, for every drill family in both modes/renders.
    If a compiler change (sevenths, cadences, ...) alters expansion, this
    fails rather than silently reopening the hidden-second-page hole (F6)."""

    def test_every_default_spec_count_matches_compiled_length(self):
        from harmony.exercise_spec import all_default_specs
        for s in all_default_specs():
            self.assertEqual(s._expected_chord_count(),
                             len(compile_exercise(s)), s.exercise_id)


def _spec_json(**fields):
    return {"exercise_id": "t_json", "title": "t", **fields}


def _load_from_json(obj):
    """Round a spec dict through a real custom-JSON file via load_specs."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "specs.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"exercises": [obj]}, fh)
        return load_specs(path)


class TestCustomJsonPath(unittest.TestCase):
    """Both gates fire for specs arriving from a custom JSON file."""

    def test_augmented_json_spec_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            _load_from_json(_spec_json(
                drill="quality", mode="major", quality="augmented",
                keys=["C"]))
        self.assertIn("augmented", str(ctx.exception))

    def test_oversized_json_spec_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            _load_from_json(_spec_json(
                drill="function", mode="major",
                pattern=["I"] * (MAX_CHORDS_PER_SPEC + 1), keys=["C"]))
        self.assertIn(str(MAX_CHORDS_PER_SPEC), str(ctx.exception))

    def test_exactly_twelve_chord_json_spec_loads(self):
        specs = _load_from_json(_spec_json(
            drill="function", mode="major",
            pattern=["I"] * MAX_CHORDS_PER_SPEC, keys=["C"]))
        self.assertEqual(len(specs), 1)
        self.assertEqual(len(compile_exercise(specs[0])), MAX_CHORDS_PER_SPEC)


class TestCircleInputPath(unittest.TestCase):
    """Both gates fire for specs arriving from a circle click request."""

    def test_augmented_circle_request_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            spec_from_circle_request(
                {"drill": "quality", "render": "block", "mode": "major",
                 "quality": "augmented", "keys": ["C"]})
        self.assertIn("augmented", str(ctx.exception))

    def test_oversized_circle_request_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            spec_from_circle_request(
                {"drill": "function", "render": "block", "mode": "major",
                 "pattern": ["I"] * (MAX_CHORDS_PER_SPEC + 1), "keys": ["C"]})
        self.assertIn(str(MAX_CHORDS_PER_SPEC), str(ctx.exception))

    def test_exactly_twelve_chord_circle_request_is_accepted(self):
        spec = spec_from_circle_request(
            {"drill": "horizontal_degree", "render": "block", "mode": "major",
             "degree": "V"})                           # all 12 default keys
        self.assertEqual(len(compile_exercise(spec)), MAX_CHORDS_PER_SPEC)


if __name__ == "__main__":
    unittest.main(verbosity=2)
