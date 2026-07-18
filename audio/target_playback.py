"""Target-playback transport for the Harmony Trainer (ticket 05 / plan U1).

Sequences a loaded exercise's target chords through the score widget's
already-loaded FluidSynth monitor (``audio.midi_player.MidiPlayer``) on a
QTimer beat clock, and mirrors every onset into the injected trainer
controller so the notated noteheads flash while they sound
(``HarmonyTrainer.playbackFlash``) and the score cursor sweeps in time
(the page-global ``jsSetCursorAbs``, the same call the score-reading host
uses).

What sounds when comes from the pure :mod:`harmony.playback_plan`; this class
only owns transport state (play/pause/stop, tempo, loop) and the Qt/JS
plumbing.  While *idle* it runs no timers and makes no synth or JS calls, so
the learner's own MIDI monitoring is untouched; while playing it never writes
the grading state either (the flash path in ``harmony_trainer.js`` is
display-only).
"""

from __future__ import annotations

import json
import time
from typing import List, NamedTuple, Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from harmony.playback_plan import (
    PlaybackPlan, build_playback_plan, seconds_per_beat,
)


class _ActiveNote(NamedTuple):
    """A note currently sounding: when it ends and where it is notated."""

    end_beat: float
    midi: int
    abs_measure: int


#: Tick interval; ~2 ticks per 16th at the fastest supported tempo.
_TICK_MS = 35

#: Playback velocity: audible but below a firm learner keystroke.
_VELOCITY = 88

STOPPED = "stopped"
PLAYING = "playing"
PAUSED = "paused"

MIN_BPM = 30
MAX_BPM = 240
DEFAULT_BPM = 80


class TargetTransport(QObject):
    """Play/pause/stop/loop/tempo engine over one attached exercise."""

    stateChanged = pyqtSignal(str)      # STOPPED | PLAYING | PAUSED

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._widget = None             # the mounted ScoreViewBeats
        self._payload: dict = {}
        self._plan: Optional[PlaybackPlan] = None
        self._bpm = DEFAULT_BPM
        self._loop = False
        self._state = STOPPED
        self._clock = 0.0               # position on the plan's beat clock
        self._next_event = 0            # first plan event not yet fired
        self._active: List[_ActiveNote] = []
        self._last_tick: Optional[float] = None
        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------
    # Host wiring
    # ------------------------------------------------------------------
    def attach(self, widget, payload: Optional[dict]) -> None:
        """Bind to a freshly mounted score widget + its trainer payload.

        Always stops first: the previous exercise's playback must not keep
        sounding into the new score.
        """
        self.stop()
        self._widget = widget
        self._payload = payload or {}
        self._plan = None               # rebuilt lazily on the next play()

    # ------------------------------------------------------------------
    # Transport controls
    # ------------------------------------------------------------------
    @property
    def state(self) -> str:
        return self._state

    @property
    def bpm(self) -> int:
        return self._bpm

    @property
    def loop(self) -> bool:
        return self._loop

    def set_bpm(self, bpm: int) -> None:
        self._bpm = max(MIN_BPM, min(MAX_BPM, int(bpm)))
        if self._state == PLAYING:
            # Pending flash timers were scheduled at the old tempo; re-issue
            # them so noteheads stay lit as long as their notes now sound.
            self._reflash_active()

    def set_loop(self, on: bool) -> None:
        self._loop = bool(on)

    def toggle(self) -> None:
        if self._state == PLAYING:
            self.pause()
        else:
            self.play()

    def play(self) -> None:
        if self._state == PLAYING or self._widget is None:
            return
        if self._plan is None:
            self._plan = build_playback_plan(self._payload)
        if not self._plan.events:
            return
        if self._state == PAUSED:
            # Re-attack the notes that were sounding when pause silenced them
            # (their flash timers expired on wall clock, so re-light them too).
            self._active = [n for n in self._active if n.end_beat > self._clock]
            for note in self._active:
                self._note_on(note.midi)
            self._reflash_active()
        self._last_tick = time.monotonic()
        self._timer.start()
        self._set_state(PLAYING)

    def pause(self) -> None:
        """Silence but hold position; play() resumes from here."""
        if self._state != PLAYING:
            return
        self._timer.stop()
        for note in self._active:              # keep bookkeeping for resume
            self._note_off(note.midi)
        self._set_state(PAUSED)

    def stop(self) -> None:
        """Silence, rewind, and hand the score display back to the learner."""
        was_running = self._state != STOPPED
        self._timer.stop()
        self._silence()
        self._clock = 0.0
        self._next_event = 0
        self._last_tick = None
        self._set_state(STOPPED)
        if was_running:
            self._run_js("window.HarmonyTrainer && "
                         "window.HarmonyTrainer.playbackClear();")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.stateChanged.emit(state)

    def _synth(self):
        player = getattr(self._widget, "_midi_player", None)
        return getattr(player, "fs", None)

    def _run_js(self, code: str) -> None:
        run = getattr(self._widget, "_run_js_safe", None)
        if run is None:
            return
        try:
            run(code)
        except Exception:
            pass

    def _note_on(self, midi: int) -> None:
        fs = self._synth()
        if fs is None:
            return
        try:
            fs.noteon(0, int(midi), _VELOCITY)
        except Exception:
            pass

    def _note_off(self, midi: int) -> None:
        fs = self._synth()
        if fs is None:
            return
        try:
            fs.noteoff(0, int(midi))
        except Exception:
            pass

    def _silence(self) -> None:
        for note in self._active:
            self._note_off(note.midi)
        self._active = []

    def _flash(self, abs_measure: int, midis: List[int], dur_ms: int) -> None:
        self._run_js(
            "window.HarmonyTrainer && window.HarmonyTrainer.playbackFlash"
            f"({int(abs_measure)}, {json.dumps(list(midis))}, {int(dur_ms)});")

    def _reflash_active(self) -> None:
        """Re-light the sounding notes for their remaining span at the
        current tempo (used on resume and on live tempo changes)."""
        spb = seconds_per_beat(self._bpm)
        for note in self._active:
            remaining_ms = int(max(1.0, (note.end_beat - self._clock)
                                   * spb * 1000))
            self._flash(note.abs_measure, [note.midi], remaining_ms)

    def _tick(self) -> None:
        plan = self._plan
        if plan is None or self._widget is None:
            self.stop()
            return

        now = time.monotonic()
        dt = now - (self._last_tick if self._last_tick is not None else now)
        self._last_tick = now
        spb = seconds_per_beat(self._bpm)
        self._clock += dt / spb

        # Release notes whose span ended.
        still: List[_ActiveNote] = []
        for note in self._active:
            if self._clock >= note.end_beat:
                self._note_off(note.midi)
            else:
                still.append(note)
        self._active = still

        # Fire every event now due: sound it and flash its noteheads.
        events = plan.events
        while (self._next_event < len(events)
               and events[self._next_event].start_beat <= self._clock):
            ev = events[self._next_event]
            self._next_event += 1
            end_beat = ev.start_beat + ev.dur_beats
            if end_beat <= self._clock:     # a stall skipped the whole span
                continue
            for midi in ev.midis:
                self._note_on(midi)
                self._active.append(_ActiveNote(end_beat, midi, ev.abs_measure))
            dur_ms = int(max(1.0, (end_beat - self._clock) * spb * 1000))
            self._flash(ev.abs_measure, list(ev.midis), dur_ms)

        self._sweep_cursor()

        if self._clock >= plan.total_beats:
            if self._loop and plan.total_beats > 0:
                self._silence()
                self._clock = 0.0
                self._next_event = 0
            else:
                self.stop()

    def _sweep_cursor(self) -> None:
        """Move the score cursor to the playback position, in score time.

        The generated score is notated at a fixed tempo, so the widget's
        measure table gives each measure's start/end seconds; the sweep maps
        playback progress (a measure fraction) onto that span, keeping the
        cursor snapped to the same notehead x-positions the score-reading
        host uses.
        """
        plan = self._plan
        if plan is None or plan.total_beats <= 0:
            return
        clock = min(self._clock, plan.total_beats - 1e-6)
        i = int(clock // plan.beats_per_measure)
        frac = (clock - i * plan.beats_per_measure) / plan.beats_per_measure

        targets = self._payload.get("TARGET_CHORDS") or []
        abs_measure = int(targets[i].get("absMeasure", i)) if i < len(targets) else i

        t_in, dur = frac, 1.0
        measures = getattr(self._widget, "measures", None)
        if measures and 0 <= abs_measure < len(measures):
            m = measures[abs_measure]
            dur = max(1e-6, float(m.end_sec) - float(m.start_sec))
            t_in = frac * dur
        self._run_js(f"jsSetCursorAbs({int(abs_measure)}, {float(t_in)}, "
                     f"{float(dur)});")
