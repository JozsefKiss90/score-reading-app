# ui/practice_window.py
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QSplitter
from PyQt6.QtCore import Qt
from config import LIVE_VELOCITY_SCALE
from .pianoroll import PianoRoll
from .score_view import ScoreView
from audio.midi_input import MidiInput

class PracticeWindow(QWidget):
    """
    Two-pane practice UI: PianoRoll on the left, ScoreView on the right.
    Score cursor follows the same music time as the piano roll.
    """
    def __init__(self, mxl_path: str, xml_path: str, soundfont: str | None, score_path: str | None = None):
        super().__init__()
        self.setWindowTitle("Score Reading App — Practice")
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # Left: existing piano roll
        self.roll = PianoRoll(mxl_path, xml_path, soundfont=soundfont)

        # Right: score view (use the MXL by default)
        self.score = ScoreView(score_path or mxl_path, xml_path)
        # Wire the clock
        self.roll.musicTimeChanged.connect(self.score.set_music_time)

        # Share total duration so the score cursor maps time->page consistently
        #if getattr(self.roll, "total_duration_sec", 0.0) and self.roll.total_duration_sec > 0:
        #    self.score.set_total_duration(self.roll.total_duration_sec)

        self.splitter.addWidget(self.roll)
        self.splitter.addWidget(self.score)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)

        layout = QHBoxLayout(self)
        layout.addWidget(self.splitter)

        self.midi_in = MidiInput()
        self.midi_in.noteOn.connect(self._on_note_on)
        self.midi_in.noteOff.connect(self._on_note_off)
        self.midi_in.control.connect(self._on_control)
        

    def closeEvent(self, event):
        if hasattr(self, "midi_in"):
            self.midi_in.close()
        super().closeEvent(event)

    def _on_note_on(self, pitch: int, velocity: int, ts: float):
        print(f"NOTE ON {pitch} vel={velocity}")
        self.roll.on_note_on(pitch, velocity, ts)

        # Apply scaling to match score playback volume
        scaled_vel = int(min(127, velocity * LIVE_VELOCITY_SCALE))
        self.roll.player.play_note(pitch, velocity=scaled_vel, duration=1.0)

    def _on_note_off(self, pitch: int, ts: float):
        self.roll.on_note_off(pitch, ts)
        # optionally call noteoff explicitly if you want sustain accuracy


    def _on_control(self, cc: int, val: int, ts: float):
        if cc == 64:  # sustain pedal
            print("Sustain", "ON" if val >= 64 else "OFF", ts)