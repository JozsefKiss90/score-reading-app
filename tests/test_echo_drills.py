"""Echo-play ear drills (plan A1 level 1, ticket 07) — Python model layer.

The first aural twin: a visual chord/progression drill acquires an *echo*
variant — same compiled chords, same grading contract, but presented ear-first
(the payload's ``PRESENTATION`` is ``"echo"`` and the JS controller hides the
notation during the listen phase).  The pure seam lives in
``harmony/echo_drills.py``:

* ``echo_variant(spec)`` derives the aural twin of a visual trainer spec;
* ``is_echo_eligible(lab_spec)`` says which curriculum leaves own one
  (native ``drill``-concept leaves: the triad and cadence drill families);
* ``echo_unlocked(state)`` gates the twin on the visual leaf being *started*;
* aural and visual attempts share one mastery record because the host records
  both under the same curriculum node id.

Run from the project root::

    .venv/Scripts/python.exe -m unittest tests.test_echo_drills
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harmony.exercise_spec import (  # noqa: E402
    HarmonyExerciseSpec,
    compile_exercise,
    MAX_CHORDS_PER_SPEC,
)
from harmony.musicxml_builder import build_trainer_payload  # noqa: E402
from harmony.echo_drills import (  # noqa: E402
    GROUP_ECHO,
    echo_demo_specs,
    echo_unlocked,
    echo_variant,
    is_echo_eligible,
)
from harmony.curriculum import get_curriculum  # noqa: E402
from harmony.curriculum_progress import record_attempt  # noqa: E402


def _full_key_spec(**overrides):
    kwargs = dict(
        exercise_id="t_c_major", title="All triads of C major",
        drill="full_key", mode="major", key="C major")
    kwargs.update(overrides)
    return HarmonyExerciseSpec(**kwargs)


def _cadence_spec(**overrides):
    kwargs = dict(
        exercise_id="t_v_i", title="V–I authentic cadence in C major",
        drill="function", mode="major", pattern=["V", "I"], keys=["C"])
    kwargs.update(overrides)
    return HarmonyExerciseSpec(**kwargs)


# ---------------------------------------------------------------------------
# Spec schema: the presentation field
# ---------------------------------------------------------------------------

class PresentationSpecValidation(unittest.TestCase):
    def test_default_is_visual(self):
        spec = _full_key_spec()
        spec.validate()
        self.assertEqual(spec.presentation, "visual")

    def test_echo_accepted(self):
        spec = _full_key_spec(presentation="echo")
        spec.validate()
        self.assertEqual(spec.presentation, "echo")

    def test_unknown_presentation_rejected(self):
        spec = _full_key_spec(presentation="hologram")
        with self.assertRaises(ValueError):
            spec.validate()

    def test_echo_answer_modes(self):
        # Echo drills answer by midi (play back what you hear) or, since
        # ticket 10's aural ID drills, by mcq (identify what you hear).  The
        # card list IS the answer surface, so echo+card stays refused.
        _full_key_spec(presentation="echo", answer_mode="mcq").validate()
        spec = _full_key_spec(presentation="echo", answer_mode="card")
        with self.assertRaises(ValueError):
            spec.validate()

    def test_roundtrip_preserves_presentation(self):
        spec = _full_key_spec(presentation="echo")
        spec.validate()
        again = HarmonyExerciseSpec.from_dict(spec.to_dict())
        self.assertEqual(again.presentation, "echo")

    def test_legacy_dicts_default_to_visual(self):
        d = _full_key_spec().to_dict()
        d.pop("presentation", None)
        self.assertEqual(HarmonyExerciseSpec.from_dict(d).presentation,
                         "visual")


# ---------------------------------------------------------------------------
# The aural twin: echo_variant
# ---------------------------------------------------------------------------

class EchoVariantDerivation(unittest.TestCase):
    def test_variant_is_echo_presentation(self):
        twin = echo_variant(_full_key_spec())
        self.assertEqual(twin.presentation, "echo")

    def test_variant_id_and_title_are_distinct(self):
        base = _full_key_spec()
        twin = echo_variant(base)
        self.assertNotEqual(twin.exercise_id, base.exercise_id)
        self.assertTrue(twin.exercise_id.startswith(base.exercise_id))
        self.assertIn(base.title, twin.title)

    def test_variant_compiles_to_the_same_chords(self):
        # Same-content transfer: the aural twin drills the *same vocabulary*,
        # not a parallel curriculum.
        base = _cadence_spec()
        twin = echo_variant(base)
        base_chords = [(c.triad.key, c.triad.mode, c.triad.roman) for c in
                       compile_exercise(base).chords]
        twin_chords = [(c.triad.key, c.triad.mode, c.triad.roman) for c in
                       compile_exercise(twin).chords]
        self.assertEqual(base_chords, twin_chords)

    def test_variant_of_non_midi_spec_rejected(self):
        base = _full_key_spec(answer_mode="mcq")
        with self.assertRaises(ValueError):
            echo_variant(base)

    def test_variant_validates(self):
        echo_variant(_full_key_spec()).validate()   # must not raise


# ---------------------------------------------------------------------------
# Payload contract
# ---------------------------------------------------------------------------

class EchoPayload(unittest.TestCase):
    def test_payload_carries_presentation(self):
        twin = echo_variant(_cadence_spec())
        payload = build_trainer_payload(compile_exercise(twin))
        self.assertEqual(payload["PRESENTATION"], "echo")

    def test_visual_payload_says_visual(self):
        payload = build_trainer_payload(compile_exercise(_cadence_spec()))
        self.assertEqual(payload["PRESENTATION"], "visual")

    def test_grading_contract_identical_to_visual(self):
        """The echo payload differs ONLY in identity + presentation.

        The playback attempt must be graded exactly as in visual drills, so
        every grading-relevant field (targets, expected-MIDI maps, render,
        answer mode) is byte-identical between the twins.
        """
        base = _cadence_spec()
        visual_payload = build_trainer_payload(compile_exercise(base))
        echo_payload = build_trainer_payload(
            compile_exercise(echo_variant(base)))
        for key in visual_payload:
            if key in ("exerciseId", "title", "PRESENTATION"):
                continue
            self.assertEqual(visual_payload[key], echo_payload[key],
                             f"payload field {key!r}")


# ---------------------------------------------------------------------------
# Eligibility + unlock gating
# ---------------------------------------------------------------------------

class EchoEligibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.leaves = get_curriculum().leaves()

    def _leaves_of_concept(self, concept):
        return [l for l in self.leaves
                if l.lab_spec is not None and l.lab_spec.concept == concept]

    def test_every_visual_midi_drill_leaf_is_eligible(self):
        # A leaf owns an echo twin iff it is a visual play-it drill.  The
        # natively aural leaves (ticket 10's echo+mcq quality-ID drills) ARE
        # ear drills already — no twin.
        drills = self._leaves_of_concept("drill")
        self.assertTrue(drills)
        aural = 0
        for leaf in drills:
            inner = HarmonyExerciseSpec.from_dict(
                leaf.lab_spec.parameters["exercise"])
            expect = (inner.answer_mode == "midi"
                      and inner.presentation == "visual")
            self.assertEqual(is_echo_eligible(leaf.lab_spec), expect, leaf.id)
            aural += 0 if expect else 1
        self.assertGreater(aural, 0)   # the ear drills exist and are exempt

    def test_triad_and_cadence_families_have_echo_twins(self):
        ids = {l.id for l in self._leaves_of_concept("drill")
               if is_echo_eligible(l.lab_spec)}
        self.assertIn("ex:drill_major_fullkey_block_C", ids)          # triads
        self.assertIn("ex:drill_atlas_function_V_I_major_C", ids)     # cadence

    def test_lab_concept_leaves_are_not_eligible(self):
        for concept in ("inversion", "cadence", "voice_leading",
                        "polyphonic_harmony", "motive"):
            for leaf in self._leaves_of_concept(concept):
                self.assertFalse(is_echo_eligible(leaf.lab_spec), leaf.id)

    def test_leaf_payload_carries_echo_eligible_flag(self):
        drill = self._leaves_of_concept("drill")[0]
        other = self._leaves_of_concept("inversion")[0]
        self.assertTrue(drill.to_payload()["echoEligible"])
        self.assertFalse(other.to_payload()["echoEligible"])

    def test_malformed_drill_wrap_is_not_eligible(self):
        leaf = self._leaves_of_concept("drill")[0]
        import copy
        broken = copy.deepcopy(leaf.lab_spec)
        broken.parameters = {}
        self.assertFalse(is_echo_eligible(broken))


class EchoUnlockGating(unittest.TestCase):
    def test_locked_until_visual_leaf_started(self):
        self.assertFalse(echo_unlocked("not_started"))

    def test_unlocked_from_started_onwards(self):
        for state in ("started", "completed", "mastered"):
            self.assertTrue(echo_unlocked(state), state)

    def test_unknown_state_stays_locked(self):
        self.assertFalse(echo_unlocked(None))
        self.assertFalse(echo_unlocked(""))
        self.assertFalse(echo_unlocked("bogus"))


# ---------------------------------------------------------------------------
# Shared mastery record
# ---------------------------------------------------------------------------

class SharedMasteryRecord(unittest.TestCase):
    def test_aural_and_visual_attempts_fold_into_one_record(self):
        """The host records echo completions under the *visual leaf's* node id,
        so both forms of the skill accumulate in one ExerciseProgress."""
        node_id = "ex:drill_major_fullkey_block_C"
        p = record_attempt(None, node_id, accuracy=1.0, score=100.0,
                           timestamp="2026-07-26T10:00:00")     # visual pass
        p = record_attempt(p, node_id, accuracy=1.0, score=100.0,
                           timestamp="2026-07-26T10:05:00")     # echo pass
        self.assertEqual(p.node_id, node_id)
        self.assertEqual(p.attempts, 2)
        self.assertEqual(p.state, "completed")


# ---------------------------------------------------------------------------
# The launcher demo group
# ---------------------------------------------------------------------------

class EchoDemoGroup(unittest.TestCase):
    def test_group_name(self):
        self.assertIn("Echo", GROUP_ECHO)

    def test_demo_specs_are_valid_echo_twins(self):
        specs = echo_demo_specs()
        self.assertTrue(specs)
        ids = [s.exercise_id for s in specs]
        self.assertEqual(len(ids), len(set(ids)), "duplicate exercise ids")
        for spec in specs:
            spec.validate()
            self.assertEqual(spec.presentation, "echo")
            self.assertLessEqual(len(compile_exercise(spec)),
                                 MAX_CHORDS_PER_SPEC)

    def test_demo_group_spans_triad_and_cadence_families(self):
        drills = {s.drill for s in echo_demo_specs()}
        self.assertIn("full_key", drills)     # triad family
        self.assertIn("function", drills)     # progression / cadence family


if __name__ == "__main__":
    unittest.main()
