# ui/practice_window.py
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QSplitter
from PyQt6.QtCore import Qt

from .pianoroll import PianoRoll
from .score_view import ScoreView

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
