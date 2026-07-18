"""Tests for harmony.playback_plan (ticket 05 / plan U1: target playback).

The plan builder is the pure seam under the trainer's transport: it turns a
trainer/lab payload into beat-timed note events.  These run headless (no Qt).

Covered:

* trainer targets carry ``bassMidi`` (the notated bass whole note);
* block targets become one 4-beat event sounding treble voicing + bass;
* arpeggio targets become a held bass + one tone per beat (beat 4 silent);
* lab strict-bass measures (graded as ordered walks, notated as block) play
  by *notation* -- ``concept`` overrides the grading ``render``;
* pitch-class -> midi mapping falls back octave-4 when a pc has no notated midi;
* lab targets carry ``bassMidi`` (lowest staff-2 sounding note, None for rests);
* seconds_per_beat converts bpm.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harmony.exercise_spec import HarmonyExerciseSpec, compile_exercise  # noqa: E402
from harmony.musicxml_builder import build_trainer_payload  # noqa: E402
from harmony.lab import compile_lab  # noqa: E402
from harmony.lab_spec import LabExperimentSpec  # noqa: E402
from harmony.lab_musicxml import build_lab_payload  # noqa: E402
from harmony.playback_plan import (  # noqa: E402
    BEATS_PER_MEASURE,
    PlaybackPlan,
    build_playback_plan,
    seconds_per_beat,
)


def _trainer_payload(render: str) -> dict:
    spec = HarmonyExerciseSpec(
        exercise_id="cmaj", title="C major triads",
        drill="full_key", mode="major", key="C major", render=render,
    )
    return build_trainer_payload(compile_exercise(spec))


def _events_for_measure(plan: PlaybackPlan, i: int):
    return [e for e in plan.events if e.target_index == i]


class TestTrainerBlockPlan(unittest.TestCase):
    def setUp(self):
        self.payload = _trainer_payload("block")
        self.plan = build_playback_plan(self.payload)

    def test_target_carries_bass_midi(self):
        t0 = self.payload["TARGET_CHORDS"][0]
        self.assertEqual(t0["bassMidi"], 48)      # C3 under the C-major tonic

    def test_one_event_per_chord_full_measure(self):
        targets = self.payload["TARGET_CHORDS"]
        self.assertEqual(len(self.plan.events), len(targets))
        for i, ev in enumerate(self.plan.events):
            self.assertEqual(ev.start_beat, BEATS_PER_MEASURE * i)
            self.assertEqual(ev.dur_beats, BEATS_PER_MEASURE)

    def test_block_event_sounds_voicing_plus_bass(self):
        t0 = self.payload["TARGET_CHORDS"][0]
        ev = self.plan.events[0]
        for m in t0["midiPitches"]:
            self.assertIn(m, ev.midis)
        self.assertIn(t0["bassMidi"], ev.midis)
        self.assertEqual(len(ev.midis), len(set(ev.midis)))  # deduplicated

    def test_total_beats_and_measure_mapping(self):
        targets = self.payload["TARGET_CHORDS"]
        self.assertEqual(self.plan.total_beats,
                         BEATS_PER_MEASURE * len(targets))
        for ev in self.plan.events:
            self.assertEqual(ev.abs_measure,
                             targets[ev.target_index]["absMeasure"])


class TestTrainerArpeggioPlan(unittest.TestCase):
    def setUp(self):
        self.payload = _trainer_payload("arpeggio")
        self.plan = build_playback_plan(self.payload)

    def test_bass_held_and_one_tone_per_beat(self):
        t0 = self.payload["TARGET_CHORDS"][0]
        evs = _events_for_measure(self.plan, 0)
        # 1 held bass + 3 quarter tones (beat 4 is the notated rest).
        self.assertEqual(len(evs), 4)
        bass = [e for e in evs if e.dur_beats == BEATS_PER_MEASURE]
        self.assertEqual(len(bass), 1)
        self.assertEqual(bass[0].midis, (t0["bassMidi"],))
        tones = sorted((e for e in evs if e is not bass[0]),
                       key=lambda e: e.start_beat)
        self.assertEqual([e.start_beat for e in tones], [0.0, 1.0, 2.0])
        self.assertTrue(all(e.dur_beats == 1.0 for e in tones))
        self.assertEqual([e.midis for e in tones],
                         [(m,) for m in t0["midiPitches"]])

    def test_second_measure_offsets(self):
        evs = _events_for_measure(self.plan, 1)
        starts = sorted(e.start_beat for e in evs)
        self.assertEqual(starts[0], BEATS_PER_MEASURE)


class TestNotationOverridesGrading(unittest.TestCase):
    """Lab strict-bass block measures grade as ordered walks (render='arpeggio')
    but are notated as whole-note blocks (concept='block'): playback follows
    the notation."""

    def _payload(self, concept=None, expected=None, bass=None):
        target = {
            "absMeasure": 0, "render": "arpeggio",
            "pitchClasses": [0, 4, 7], "midiPitches": [60, 64, 67],
            "bassMidi": bass,
        }
        if concept is not None:
            target["concept"] = concept
        payload = {"TARGET_CHORDS": [target]}
        if expected is not None:
            payload["EXPECTED_MIDI_BY_MEASURE_OR_BEAT"] = {"0": expected}
        return payload

    def test_block_concept_plays_block(self):
        plan = build_playback_plan(self._payload(
            concept="block", expected={"1": [4], "2": [0], "3": [7]}, bass=52))
        self.assertEqual(len(plan.events), 1)
        ev = plan.events[0]
        self.assertEqual(ev.dur_beats, BEATS_PER_MEASURE)
        self.assertEqual(set(ev.midis), {52, 60, 64, 67})

    def test_expected_beats_drive_sequencing(self):
        plan = build_playback_plan(self._payload(
            expected={"1": [7], "2": [4], "3": [0]}))
        self.assertEqual([e.midis for e in plan.events],
                         [(67,), (64,), (60,)])

    def test_unknown_pc_falls_back_to_octave_4(self):
        plan = build_playback_plan(self._payload(expected={"1": [1]}))
        self.assertEqual(plan.events[0].midis, (61,))

    def test_arpeggio_without_expected_sequences_midis(self):
        plan = build_playback_plan(self._payload())
        self.assertEqual([e.midis for e in plan.events],
                         [(60,), (64,), (67,)])
        self.assertEqual([e.start_beat for e in plan.events],
                         [0.0, 1.0, 2.0])

    def test_empty_payload_yields_empty_plan(self):
        plan = build_playback_plan({})
        self.assertEqual(plan.events, ())
        self.assertEqual(plan.total_beats, 0.0)


class TestEighthNoteMotives(unittest.TestCase):
    """Motives with 5-8 degrees notate as eighths in 8 slots keyed 1..8; the
    plan must keep every slot and halve the slot duration -- not clamp to 4
    quarters (which silently dropped the tail of 5–4–3–2–1)."""

    def _plan_for(self, degrees):
        spec = LabExperimentSpec(
            "mot", "Motive", concept="motive", key="C major",
            render="melody", parameters={"degrees": degrees, "keys": ["C"]})
        payload = build_lab_payload(compile_lab(spec))
        return payload, build_playback_plan(payload)

    def test_five_degree_motive_keeps_every_tone(self):
        payload, plan = self._plan_for([5, 4, 3, 2, 1])
        t0 = payload["TARGET_CHORDS"][0]
        self.assertEqual(len(plan.events), 5)
        self.assertEqual([e.start_beat for e in plan.events],
                         [0.0, 0.5, 1.0, 1.5, 2.0])
        self.assertTrue(all(e.dur_beats == 0.5 for e in plan.events))
        played_pcs = [e.midis[0] % 12 for e in plan.events]
        self.assertEqual(played_pcs, list(t0["pitchClasses"]))

    def test_four_degree_motive_keeps_quarter_slots(self):
        _payload, plan = self._plan_for([1, 3, 5, 3])
        self.assertEqual([e.start_beat for e in plan.events],
                         [0.0, 1.0, 2.0, 3.0])
        self.assertTrue(all(e.dur_beats == 1.0 for e in plan.events))


class TestLabPayloadBassMidi(unittest.TestCase):
    def test_inversion_bass_midi_tracks_the_changing_bass(self):
        spec = LabExperimentSpec(
            "inv", "Inversions", concept="inversion", key="C major",
            render="block", parameters={"degree": "I",
                                        "inversions": [0, 1, 2]})
        payload = build_lab_payload(compile_lab(spec))
        targets = payload["TARGET_CHORDS"]
        bass_pcs = [t["bassMidi"] % 12 for t in targets]
        self.assertEqual(bass_pcs, [0, 4, 7])     # C, E, G under I, I6, I64

    def test_melody_measures_have_no_bass(self):
        spec = LabExperimentSpec(
            "mot", "Motive", concept="motive", key="C major",
            render="melody", parameters={"degrees": [1, 3, 5, 3],
                                         "keys": ["C"]})
        payload = build_lab_payload(compile_lab(spec))
        self.assertIsNone(payload["TARGET_CHORDS"][0]["bassMidi"])


class TestSecondsPerBeat(unittest.TestCase):
    def test_conversion(self):
        self.assertAlmostEqual(seconds_per_beat(80), 0.75)
        self.assertAlmostEqual(seconds_per_beat(120), 0.5)

    def test_rejects_nonpositive(self):
        with self.assertRaises(ValueError):
            seconds_per_beat(0)
        with self.assertRaises(ValueError):
            seconds_per_beat(-60)


if __name__ == "__main__":
    unittest.main()
