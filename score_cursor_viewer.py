from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path
from typing import Optional

# ---- Qt ----
from PyQt6.QtCore import Qt, QTimer, QElapsedTimer, pyqtSlot
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFileDialog, QDoubleSpinBox, QMessageBox
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

# ---- Optional libs from your requirements ----
# verovio renders MEI / MusicXML -> SVG
try:
    import verovio
except Exception as e:
    verovio = None
    _verovio_err = e

# mido gives accurate duration from MIDI (tempo-aware)
try:
    import mido
except Exception:
    mido = None

# music21 can estimate length from MusicXML tempo + durations
try:
    from music21 import converter
except Exception:
    converter = None


HTML_SHELL = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  html, body { margin:0; padding:0; height:100%; background:#fff; }
  #wrap { position: relative; display: inline-block; }
  #cursor {
    position: absolute; top: 0; bottom: 0; width: 2px;
    background: rgba(220,0,0,0.9); pointer-events: none;
    transform: translateX(-1px);
  }
  svg { display:block; }
</style>
</head>
<body>
  <div id="wrap">
    <div id="cursor"></div>
    <!-- SVG PAGE WILL BE INJECTED HERE -->
    {SVG}
  </div>

  <script>
    function svgElem(){ return document.querySelector('svg'); }
    function svgWidth(){ let s = svgElem(); return s ? s.getBoundingClientRect().width : 0; }
    function setCursorAt(percent){
      const w = svgWidth();
      const x = Math.max(0, Math.min(1, percent)) * w;
      document.getElementById('cursor').style.left = x + 'px';
    }
  </script>
</body>
</html>
"""


def human_err(msg: str):
    mbox = QMessageBox(QMessageBox.Icon.Warning, "Score Cursor Viewer", msg)
    mbox.exec()


def estimate_duration_seconds(score_path: Path, midi_path: Optional[Path]) -> float:
    """
    Duration heuristic:
    1) If MIDI provided and mido is available, use mido length (tempo-aware).
    2) Else if MusicXML and music21 present, use highestTime + metronome marks.
    3) Else fallback to 180s.
    """
    # 1) MIDI best
    if midi_path and mido:
        try:
            mf = mido.MidiFile(midi_path.as_posix())
            return float(mf.length)  # seconds
        except Exception:
            pass

    # 2) MusicXML via music21
    if converter and score_path.suffix.lower() in {".xml", ".mxl", ".musicxml"}:
        try:
            sc = converter.parse(score_path.as_posix())
            highest_q = float(sc.flat.highestTime)
            # Try to get initial BPM
            bpm = 60.0
            mmarks = sc.metronomeMarkBoundaries()
            if mmarks:
                mm = mmarks[0][2]
                if getattr(mm, "number", None):
                    bpm = float(mm.number)
                else:
                    qpm = mm.getQuarterBPM()
                    if qpm:
                        bpm = float(qpm)
            # seconds = quarters * (60 / bpm)
            return max(1.0, highest_q * (60.0 / max(1e-6, bpm)))
        except Exception:
            pass

    # 3) Fallback
    return 180.0


class ScoreCursorWindow(QWidget):
    """
    Separate GUI window:
    - Renders score pages with verovio -> SVG
    - Shows an overlaid vertical line (cursor) moving left->right
    - Timing from MIDI if provided, otherwise estimated from score
    - Transport: Pause/Resume, Restart, Rewind, Forward, Speed (0.25×–2.00×)
    """
    def __init__(self, score_path: Path, midi_path: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Score Cursor Viewer (prototype)")
        self.resize(1000, 1200)

        if verovio is None:
            human_err(f"verovio is required but failed to import.\n\n{_verovio_err}")
            raise SystemExit(1)

        self.score_path = score_path
        self.midi_path = midi_path
        self.tk = verovio.toolkit()

        # Layout
        self.web = QWebEngineView()
        self.info = QLabel("—")
        self.info.setStyleSheet("color:white; background:#333; padding:6px;")

        # Transport
        bar = QHBoxLayout()
        self.btn_rewind = QPushButton("⟲ Rewind")
        self.btn_restart = QPushButton("↻ Restart")
        self.btn_forward = QPushButton("Forward ⟳")
        self.btn_pause = QPushButton("Pause")
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.25, 2.00)
        self.speed.setSingleStep(0.05)
        self.speed.setDecimals(2)
        self.speed.setValue(1.00)
        self.speed.setSuffix("×")

        bar.addWidget(self.btn_rewind)
        bar.addWidget(self.btn_restart)
        bar.addWidget(self.btn_forward)
        bar.addStretch(1)
        bar.addWidget(QLabel("Speed"))
        bar.addWidget(self.speed)
        bar.addWidget(self.btn_pause)

        root = QVBoxLayout(self)
        root.addWidget(self.info)
        root.addLayout(bar)
        root.addWidget(self.web)

        # Timing state
        self.clock = QElapsedTimer()
        self.clock.start()
        self.playback_rate = 1.0
        self.offset = 0.0  # music_time = wall * rate + offset
        self.total_duration = estimate_duration_seconds(score_path, midi_path)
        self.page_count = 0
        self.page_idx = 0
        self._page_loaded = False

        # Render score pages (simple layout)
        self._load_score()

        # Frame loop
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._tick)
        self.timer.start(int(1000 / 60))

        # Wire UI
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_restart.clicked.connect(self._restart)
        self.btn_rewind.clicked.connect(lambda: self._seek_by(-5.0))
        self.btn_forward.clicked.connect(lambda: self._seek_by(+5.0))
        self.speed.valueChanged.connect(self._on_speed_change)

        self._update_info()

    # -------- score rendering --------
    def _load_score(self):
        # Basic options; feel free to tweak pageWidth/pageHeight/scale
        opts = {
            "pageWidth": 2100,      # roughly A4 width in tenths of mm @ scale
            "pageHeight": 2970,     # A4 height
            "scale": 50,            # visual scale
            "adjustPageHeight": 1,  # let verovio adapt height to content if needed
            "breaks": "auto",
        }
        self.tk.setOptions(opts)

        # Verovio can load MEI, MusicXML or compressed MXL directly
        if not self.tk.loadFile(self.score_path.as_posix()):
            human_err(f"Could not load score file:\n{self.score_path}")
            raise SystemExit(2)

        self.tk.redoLayout()
        self.page_count = int(self.tk.getPageCount() or 1)
        self.page_idx = 0
        self._load_page(self.page_idx)

    def _svg_for_page(self, page: int) -> str:
        # Verovio pages are 1-based. Do NOT pass a dict here.
        return self.tk.renderToSVG(page + 1)


    def _load_page(self, page: int):
        page = max(0, min(self.page_count - 1, page))
        svg = self._svg_for_page(page)
        html = HTML_SHELL.replace("{SVG}", svg)
        self._page_loaded = False
        self.web.setHtml(html)
        # setHtml loads async; small delay before first JS calls is OK
        self.page_idx = page

    # -------- transport --------
    def music_now(self) -> float:
        return (self.clock.elapsed() / 1000.0) * self.playback_rate + self.offset

    def _toggle_pause(self):
        if self.playback_rate == 0.0:
            self._set_rate(max(0.25, float(self.speed.value())))
            self.btn_pause.setText("Pause")
        else:
            self._set_rate(0.0)
            self.btn_pause.setText("Resume")

    def _restart(self):
        self._seek_to(0.0)
        if self.playback_rate == 0.0:
            self._toggle_pause()

    def _seek_by(self, delta: float):
        self._seek_to(self.music_now() + float(delta))

    def _seek_to(self, new_t: float):
        new_t = max(0.0, min(self.total_duration, float(new_t)))
        wall = self.clock.elapsed() / 1000.0
        self.offset = new_t - wall * self.playback_rate
        # swap page if needed
        self._maybe_change_page(new_t)
        self._update_cursor(new_t)
        self._update_info()

    def _set_rate(self, r: float):
        # keep music time continuous
        r = 0.0 if r == 0.0 else max(0.25, min(2.0, float(r)))
        wall = self.clock.elapsed() / 1000.0
        t_now = self.music_now()
        self.playback_rate = r
        self.offset = t_now - wall * self.playback_rate
        if self.playback_rate != 0.0 and abs(self.speed.value() - self.playback_rate) > 1e-6:
            self.speed.blockSignals(True)
            self.speed.setValue(self.playback_rate)
            self.speed.blockSignals(False)
        self._update_info()

    def _on_speed_change(self, val: float):
        if self.playback_rate == 0.0:
            # paused: don't force rate change; resume will pick this up
            return
        self._set_rate(val)

    # -------- mapping time -> page/percent --------
    def _page_duration(self) -> float:
        # Simple: split total duration evenly across pages (prototype).
        # (We can upgrade to verovio time map later.)
        return max(1e-3, self.total_duration / max(1, self.page_count))

    def _page_times(self, page_index: int) -> tuple[float, float]:
        per = self._page_duration()
        start = page_index * per
        end = min(self.total_duration, (page_index + 1) * per)
        return start, end

    def _maybe_change_page(self, t: float):
        per = self._page_duration()
        idx = int(t // per)
        idx = max(0, min(self.page_count - 1, idx))
        if idx != self.page_idx:
            self._load_page(idx)

    def _percent_in_page(self, t: float) -> float:
        start, end = self._page_times(self.page_idx)
        if end <= start:
            return 0.0
        return (t - start) / (end - start)

    # -------- UI updates --------
    def _update_cursor(self, t: float):
        # after setHtml the page loads asynchronously; calling JS repeatedly is fine
        pct = self._percent_in_page(t)
        self.web.page().runJavaScript(f"setCursorAt({pct});")

    def _update_info(self):
        t = self.music_now()
        t = max(0.0, min(self.total_duration, t))
        mins = int(t // 60); secs = int(t % 60)
        total_m = int(self.total_duration // 60); total_s = int(self.total_duration % 60)
        self.info.setText(
            f"Page {self.page_idx + 1}/{self.page_count}   "
            f"Time {mins:02d}:{secs:02d} / {total_m:02d}:{total_s:02d}   "
            f"Speed {self.playback_rate:.2f}×"
        )

    # -------- frame --------
    @pyqtSlot()
    def _tick(self):
        t = self.music_now()
        if t >= self.total_duration:
            # stop at end
            self._set_rate(0.0)
            self._seek_to(self.total_duration)
            self.btn_pause.setText("Restart")
            return

        self._maybe_change_page(t)
        self._update_cursor(t)
        self._update_info()


def main():
    ap = argparse.ArgumentParser(description="Score Cursor Viewer (prototype)")
    ap.add_argument("--score", type=str, required=False,
                    help="Path to MEI / MusicXML / MXL score file to render.")
    ap.add_argument("--midi", type=str, required=False,
                    help="Optional MIDI file for accurate timing.")
    args = ap.parse_args()

    # Pick a default score if none given
    score_path = None
    if args.score:
        score_path = Path(args.score)
    else:
        # Try some common names in CWD
        for cand in ["Gymnopdie_No._1__Satie.mxl", "Gymnopdie_No.mei", "score.xml"]:
            p = Path(cand)
            if p.exists():
                score_path = p
                break
    if not score_path or not score_path.exists():
        print("Please provide --score pointing to an MEI/MusicXML/MXL file.")
        sys.exit(1)

    midi_path = Path(args.midi) if args.midi else None
    if midi_path and not midi_path.exists():
        print(f"MIDI file not found: {midi_path}")
        midi_path = None

    app = QApplication(sys.argv)
    win = ScoreCursorWindow(score_path, midi_path)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
