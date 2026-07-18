"""Headless tests for audio.target_playback (ticket 05 / plan U1).

Drives the transport deterministically: instead of waiting on the QTimer, each
step rewinds ``_last_tick`` and invokes ``_tick()`` directly, so wall-clock
timing never flakes.  The score widget, synth, and JS bridge are duck-typed
fakes that record every call.

Covered:

* play sounds the first chord (synth noteons + notehead flash JS);
* the beat clock advances chords at the chosen tempo, and tempo scales it;
* pause silences but holds position; resume re-attacks the held notes;
* stop rewinds, silences, and hands the display back (playbackClear);
* loop wraps back to the first chord instead of stopping;
* idle transport makes no synth/JS calls (learner monitoring untouched);
* the cursor sweep maps playback progress onto notated measure seconds.
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QCoreApplication  # noqa: E402

from audio.target_playback import (  # noqa: E402
    TargetTransport, STOPPED, PLAYING, PAUSED,
)

_app = QCoreApplication.instance() or QCoreApplication([])


class FakeSynth:
    def __init__(self):
        self.calls = []

    def noteon(self, chan, midi, vel):
        self.calls.append(("on", midi))

    def noteoff(self, chan, midi):
        self.calls.append(("off", midi))


class FakePlayer:
    def __init__(self):
        self.fs = FakeSynth()


class FakeMeasure:
    def __init__(self, start_sec, end_sec):
        self.start_sec = start_sec
        self.end_sec = end_sec


class FakeWidget:
    def __init__(self, n_measures=2, measure_sec=3.0):
        self._midi_player = FakePlayer()
        self.js = []
        self.measures = [FakeMeasure(i * measure_sec, (i + 1) * measure_sec)
                         for i in range(n_measures)]

    def _run_js_safe(self, code, label=None):
        self.js.append(code)


def _payload():
    """Two block chords: C major over C3, G major over G3."""
    return {
        "TARGET_CHORDS": [
            {"absMeasure": 0, "render": "block", "pitchClasses": [0, 4, 7],
             "midiPitches": [60, 64, 67], "bassMidi": 48},
            {"absMeasure": 1, "render": "block", "pitchClasses": [7, 11, 2],
             "midiPitches": [67, 71, 74], "bassMidi": 55},
        ],
    }


class TransportCase(unittest.TestCase):
    def setUp(self):
        self.widget = FakeWidget()
        self.transport = TargetTransport()
        self.transport.attach(self.widget, _payload())

    def step(self, dt_sec):
        """Advance the transport's clock by dt and run one tick."""
        self.transport._last_tick = time.monotonic() - dt_sec
        self.transport._tick()

    @property
    def synth_calls(self):
        return self.widget._midi_player.fs.calls

    def ons(self):
        return [m for kind, m in self.synth_calls if kind == "on"]


class TestPlay(TransportCase):
    def test_idle_transport_touches_nothing(self):
        self.assertEqual(self.synth_calls, [])
        self.assertEqual(self.widget.js, [])
        self.assertEqual(self.transport.state, STOPPED)
        self.assertFalse(self.transport._timer.isActive())

    def test_play_sounds_first_chord_and_flashes(self):
        self.transport.play()
        self.assertEqual(self.transport.state, PLAYING)
        self.step(0.01)
        self.assertEqual(set(self.ons()), {48, 60, 64, 67})
        flashes = [c for c in self.widget.js if "playbackFlash" in c]
        self.assertEqual(len(flashes), 1)
        self.assertIn("playbackFlash(0,", flashes[0].replace(" ", ""))

    def test_clock_advances_to_second_chord(self):
        self.transport.set_bpm(120)          # 0.5 s/beat -> measure = 2 s
        self.transport.play()
        self.step(0.01)
        self.step(2.05)                       # past beat 4 -> chord 2 due
        self.assertIn(("off", 60), self.synth_calls)
        self.assertIn(("on", 55), self.synth_calls)
        self.assertIn(("on", 71), self.synth_calls)

    def test_sequence_end_stops_without_loop(self):
        self.transport.set_bpm(240)
        self.transport.play()
        self.step(0.01)
        self.step(10.0)                       # far past both measures
        self.assertEqual(self.transport.state, STOPPED)
        self.assertFalse(self.transport._timer.isActive())
        clears = [c for c in self.widget.js if "playbackClear" in c]
        self.assertEqual(len(clears), 1)

    def test_loop_wraps_to_first_chord(self):
        self.transport.set_bpm(240)           # 0.25 s/beat -> measure = 1 s
        self.transport.set_loop(True)
        self.transport.play()
        self.step(0.01)
        self.step(2.05)                       # past the whole 2-measure plan
        self.assertEqual(self.transport.state, PLAYING)
        self.step(0.05)                       # first tick of the new pass
        self.assertGreaterEqual(self.ons().count(60), 2, "chord 1 re-fired")


class TestPauseStop(TransportCase):
    def test_pause_silences_but_holds_position(self):
        self.transport.play()
        self.step(0.01)
        clock = self.transport._clock
        self.transport.pause()
        self.assertEqual(self.transport.state, PAUSED)
        for midi in (48, 60, 64, 67):
            self.assertIn(("off", midi), self.synth_calls)
        self.assertAlmostEqual(self.transport._clock, clock)
        self.assertFalse(self.transport._timer.isActive())

    def test_resume_reattacks_held_notes(self):
        self.transport.play()
        self.step(0.01)
        self.transport.pause()
        self.widget._midi_player.fs.calls = []
        self.transport.play()                 # resume
        self.assertEqual(self.transport.state, PLAYING)
        self.assertEqual(set(self.ons()), {48, 60, 64, 67})

    def test_resume_reflashes_held_notes(self):
        # Flash timers expire on wall clock during a pause; resume must
        # re-light the notes it re-attacks.
        self.transport.play()
        self.step(0.01)
        self.transport.pause()
        self.widget.js = []
        self.transport.play()
        flashes = [c for c in self.widget.js if "playbackFlash" in c]
        self.assertEqual(len(flashes), 4)     # one per held note

    def test_tempo_change_reflashes_while_playing(self):
        self.transport.play()
        self.step(0.01)
        self.widget.js = []
        self.transport.set_bpm(60)            # slower: spans now last longer
        self.assertTrue(any("playbackFlash" in c for c in self.widget.js))
        self.widget.js = []
        self.transport.stop()
        self.transport.set_bpm(90)            # idle: no JS traffic
        self.assertEqual(
            [c for c in self.widget.js if "playbackFlash" in c], [])

    def test_stop_rewinds_and_clears(self):
        self.transport.play()
        self.step(0.01)
        self.transport.stop()
        self.assertEqual(self.transport.state, STOPPED)
        self.assertEqual(self.transport._clock, 0.0)
        for midi in (48, 60, 64, 67):
            self.assertIn(("off", midi), self.synth_calls)
        self.assertTrue(any("playbackClear" in c for c in self.widget.js))

    def test_attach_stops_running_playback(self):
        self.transport.play()
        self.step(0.01)
        other = FakeWidget()
        self.transport.attach(other, _payload())
        self.assertEqual(self.transport.state, STOPPED)
        self.assertEqual(other.js, [])        # nothing leaked into the new page


class TestCursorSweep(TransportCase):
    def test_sweep_maps_progress_onto_measure_seconds(self):
        self.transport.set_bpm(120)           # measure = 2 s of playback
        self.transport.play()
        self.step(1.0)                        # halfway through measure 0
        sweeps = [c for c in self.widget.js if "jsSetCursorAbs" in c]
        self.assertTrue(sweeps)
        last = sweeps[-1]
        self.assertIn("jsSetCursorAbs(0,", last.replace(" ", ""))
        # halfway through a 3-second notated measure ~ 1.5 s
        args = last[last.index("(") + 1:last.index(")")].split(",")
        self.assertAlmostEqual(float(args[1]), 1.5, delta=0.15)
        self.assertAlmostEqual(float(args[2]), 3.0, delta=0.001)

    def test_no_synth_still_sweeps(self):
        self.widget._midi_player = None       # soundfont missing -> silent
        self.transport.play()
        self.step(0.01)
        self.assertEqual(self.transport.state, PLAYING)
        self.assertTrue(any("jsSetCursorAbs" in c for c in self.widget.js))


if __name__ == "__main__":
    unittest.main()
