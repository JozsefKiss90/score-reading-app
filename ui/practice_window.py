# ui/practice_window.py
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QSplitter
from PyQt6.QtCore import Qt

from config import LIVE_VELOCITY_SCALE
from .pianoroll import PianoRoll
from .score_view import ScoreView
from app_context import AppContext
from audio.midi_service import MidiService


class PracticeWindow(QWidget):
    """
    Two-pane practice UI: PianoRoll on the left, ScoreView on the right.
    Score cursor follows the same music time as the piano roll.

    MIDI input is provided by a shared MidiService owned by AppContext,
    so multiple windows can listen to the same keyboard.
    """

    def __init__(
        self,
        ctx: AppContext,
        mxl_path: str,
        xml_path: str,
        score_path: str | None = None,
    ) -> None:
        super().__init__()
        self._ctx = ctx
        self.setWindowTitle("Score Reading App — Practice")

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # Left: piano roll (uses Fluidsynth via MidiPlayer)
        soundfont = ctx.soundfont_path
        self.roll = PianoRoll(mxl_path, xml_path, soundfont=soundfont)

        # Right: score view (use the MXL by default)
        self.score = ScoreView(score_path or mxl_path, xml_path)

        # Wire the clock: piano-roll drives the score cursor
        self.roll.musicTimeChanged.connect(self.score.set_music_time)

        self.splitter.addWidget(self.roll)
        self.splitter.addWidget(self.score)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)

        layout = QHBoxLayout(self)
        layout.addWidget(self.splitter)

        # Shared MIDI service from the app context
        self._midi: MidiService | None = getattr(ctx, "midi", None)
        if self._midi is not None:
            self._midi.noteOn.connect(self._on_note_on)
            self._midi.noteOff.connect(self._on_note_off)
            self._midi.control.connect(self._on_control)

    # ------------------------------------------------------------------ #
    # MIDI handlers
    # ------------------------------------------------------------------ #
    def _on_note_on(self, pitch: int, velocity: int, ts: float) -> None:
        print(f"NOTE ON {pitch} vel={velocity}")
        # Drive the visual piano roll
        self.roll.on_note_on(pitch, velocity, ts)

        # And sound via Fluidsynth
        scaled_vel = int(min(127, velocity * LIVE_VELOCITY_SCALE))
        # Don't schedule noteoff here — start it and stop later
        self.roll.player.fs.noteon(0, pitch, scaled_vel)

    def _on_note_off(self, pitch: int, ts: float) -> None:
        self.roll.on_note_off(pitch, ts)
        self.roll.player.fs.noteoff(0, pitch)

    def _on_control(self, cc: int, val: int, ts: float) -> None:
        # Sustain pedal; forward directly to Fluidsynth
        if cc == 64:
            self.roll.player.fs.cc(0, 64, val)
