"""Answer modalities beyond hardware MIDI (plan U2, ticket 06) — Python side.

The spec gains an ``answer_mode`` field (``midi`` | ``mcq`` | ``card``) and the
trainer payload carries it as ``ANSWER_MODE``.  For ``mcq`` specs every target
additionally carries an ``mcq`` block — prompt, the mode's seven Roman-numeral
options, and the correct answer — so the JS trainer can render an MCQ strip and
grade identification drills entirely mouse-side.  ``identification_demo_specs``
provides launchable no-MIDI drills without touching the load-bearing
``default_exercise_groups()`` set (curriculum wraps exactly those 102 drills).

Run from the project root::

    .venv/Scripts/python.exe -m unittest tests.test_answer_modes
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harmony.exercise_spec import (  # noqa: E402
    HarmonyExerciseSpec,
    compile_exercise,
    all_default_specs,
    degree_labels_for_mode,
    identification_demo_specs,
    MAX_CHORDS_PER_SPEC,
)
from harmony.musicxml_builder import build_trainer_payload  # noqa: E402


def _full_key_spec(answer_mode=None):
    kwargs = dict(
        exercise_id="t_id_c_major", title="t", drill="full_key",
        mode="major", key="C major")
    if answer_mode is not None:
        kwargs["answer_mode"] = answer_mode
    return HarmonyExerciseSpec(**kwargs)


class AnswerModeSpecValidation(unittest.TestCase):
    def test_default_is_midi(self):
        spec = _full_key_spec()
        spec.validate()
        self.assertEqual(spec.answer_mode, "midi")

    def test_mcq_and_card_accepted(self):
        for mode in ("mcq", "card"):
            spec = _full_key_spec(mode)
            spec.validate()
            self.assertEqual(spec.answer_mode, mode)

    def test_unknown_answer_mode_rejected(self):
        spec = _full_key_spec("telepathy")
        with self.assertRaises(ValueError):
            spec.validate()

    def test_round_trips_through_dict(self):
        spec = _full_key_spec("mcq")
        back = HarmonyExerciseSpec.from_dict(spec.to_dict())
        self.assertEqual(back.answer_mode, "mcq")

    def test_dict_without_answer_mode_defaults_midi(self):
        d = _full_key_spec().to_dict()
        d.pop("answer_mode", None)
        self.assertEqual(HarmonyExerciseSpec.from_dict(d).answer_mode, "midi")


class DegreeLabels(unittest.TestCase):
    def test_major_labels(self):
        self.assertEqual(
            degree_labels_for_mode("major"),
            ["I", "ii", "iii", "IV", "V", "vi", "vii°"])

    def test_minor_labels(self):
        self.assertEqual(
            degree_labels_for_mode("natural_minor"),
            ["i", "ii°", "III", "iv", "v", "VI", "VII"])


class McqPayload(unittest.TestCase):
    def test_midi_spec_payload_unchanged_shape(self):
        payload = build_trainer_payload(compile_exercise(_full_key_spec()))
        self.assertEqual(payload["ANSWER_MODE"], "midi")
        for t in payload["TARGET_CHORDS"]:
            self.assertNotIn("mcq", t)

    def test_mcq_targets_carry_options_and_answer(self):
        payload = build_trainer_payload(compile_exercise(_full_key_spec("mcq")))
        self.assertEqual(payload["ANSWER_MODE"], "mcq")
        targets = payload["TARGET_CHORDS"]
        self.assertEqual(len(targets), 7)
        romans = []
        for t in targets:
            block = t["mcq"]
            self.assertEqual(block["options"], degree_labels_for_mode("major"))
            self.assertEqual(block["answer"], t["roman"])
            self.assertIn(block["answer"], block["options"])
            self.assertTrue(block["prompt"])
            romans.append(block["answer"])
        # A real identification drill: the answer varies across targets.
        self.assertEqual(len(set(romans)), 7)

    def test_mcq_minor_options_match_minor_vocabulary(self):
        spec = HarmonyExerciseSpec(
            exercise_id="t_id_a_minor", title="t", drill="full_key",
            mode="natural_minor", key="A minor", answer_mode="mcq")
        payload = build_trainer_payload(compile_exercise(spec))
        for t in payload["TARGET_CHORDS"]:
            self.assertEqual(
                t["mcq"]["options"], degree_labels_for_mode("natural_minor"))
            self.assertIn(t["mcq"]["answer"], t["mcq"]["options"])

    def test_card_mode_marks_payload_but_adds_no_mcq(self):
        payload = build_trainer_payload(compile_exercise(_full_key_spec("card")))
        self.assertEqual(payload["ANSWER_MODE"], "card")
        for t in payload["TARGET_CHORDS"]:
            self.assertNotIn("mcq", t)


_NODE = shutil.which("node")


@unittest.skipUnless(_NODE, "node not on PATH")
class CrossLanguageMcqContract(unittest.TestCase):
    """The executable form of acceptance criterion 1 (ticket 06): a REAL
    Python-emitted MCQ payload completes mouse-only in the REAL trainer JS
    (tests/mcq_contract_check.js drives beat_selector/harmony_trainer.js)."""

    def test_real_payload_completes_mouse_only_in_trainer_js(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for spec in identification_demo_specs():
            if spec.answer_mode != "mcq":
                continue
            payload = build_trainer_payload(compile_exercise(spec))
            with tempfile.TemporaryDirectory() as td:
                pj = os.path.join(td, "payload.json")
                with open(pj, "w", encoding="utf-8") as f:
                    json.dump(payload, f)
                out = subprocess.run(
                    [_NODE, os.path.join(root, "tests", "mcq_contract_check.js"), pj],
                    capture_output=True, text=True, cwd=root)
            self.assertEqual(
                out.returncode, 0,
                f"{spec.exercise_id}: {out.stdout}\n{out.stderr}")
            self.assertIn("CONTRACT OK", out.stdout, spec.exercise_id)


class IdentificationCatalogue(unittest.TestCase):
    def test_specs_validate_compile_and_stay_under_cap(self):
        specs = identification_demo_specs()
        self.assertTrue(specs)
        for s in specs:
            s.validate()
            self.assertNotEqual(s.answer_mode, "midi")
            compiled = compile_exercise(s)
            self.assertTrue(compiled.chords)
            self.assertLessEqual(len(compiled.chords), MAX_CHORDS_PER_SPEC)

    def test_has_both_mcq_and_card_drills(self):
        modes = {s.answer_mode for s in identification_demo_specs()}
        self.assertIn("mcq", modes)
        self.assertIn("card", modes)

    def test_ids_unique_and_disjoint_from_default_set(self):
        ids = [s.exercise_id for s in identification_demo_specs()]
        self.assertEqual(len(ids), len(set(ids)))
        native = {s.exercise_id for s in all_default_specs()}
        self.assertFalse(native.intersection(ids))

    def test_default_groups_unchanged(self):
        # The curriculum wraps exactly the native 102 drills; the ID drills
        # must not leak into that load-bearing set.
        for s in all_default_specs():
            self.assertEqual(s.answer_mode, "midi")


if __name__ == "__main__":
    unittest.main()
