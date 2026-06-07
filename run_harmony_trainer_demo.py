"""Diatonic Harmony Trainer -- playable demo.

Run::

    .venv/Scripts/python.exe run_harmony_trainer_demo.py
    .venv/Scripts/python.exe run_harmony_trainer_demo.py path/to/specs.json

What it does
------------
For each exercise it compiles the spec into a deterministic chord stream
(``harmony.exercise_spec``), renders playable MusicXML with staff annotations
(``harmony.musicxml_builder``), shows it in the existing ScoreViewBeats /
Verovio viewer, and injects the harmony-trainer controller
(``beat_selector/harmony_trainer.js``) which:

  * highlights the current target chord (green = correct pitch, red = wrong)
    using the existing MIDI keyboard-colouring machinery,
  * advances chord-by-chord (block: all tones; arpeggio: tones in order),
  * shows a guide panel (key, mode, scale, degree, Roman numeral, chord
    symbol, chord tones, interval layer, function, explanation).

The first demo offers: all seven triads in C major, all seven in G major,
ii-V-I in C/G/D major, the dominant across all 12 major keys, and an
arpeggiated A natural-minor run.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt, QCoreApplication, QTimer
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox,
    QLabel,
)

from harmony.exercise_spec import (
    HarmonyExerciseSpec, compile_exercise, default_demo_specs, load_specs,
)
from harmony.musicxml_builder import build_exercise


# --- imports matching the existing framework (mirrors run_sight_notes_demo) ---

def _import_score_view_beats():
    try:
        from beat_selector.view import ScoreViewBeats  # type: ignore
        return ScoreViewBeats
    except Exception:
        from view import ScoreViewBeats  # type: ignore
        return ScoreViewBeats


def _import_midi_service():
    for path in ("audio.midi_service", "midi_service"):
        try:
            module = __import__(path, fromlist=["MidiService"])
            return getattr(module, "MidiService")
        except Exception:
            continue
    return None


ScoreViewBeats = _import_score_view_beats()
MidiService = _import_midi_service()

_TRAINER_JS_PATH = Path(__file__).resolve().parent / "beat_selector" / "harmony_trainer.js"


class HarmonyTrainerWindow(QWidget):
    def __init__(self, specs: List[HarmonyExerciseSpec], midi_service=None):
        super().__init__()
        self._specs = specs
        self._midi_service = midi_service
        self._current_idx = 0
        self._score_widget: Optional[ScoreViewBeats] = None
        self._tmp_paths: List[Path] = []
        self._trainer_js = _TRAINER_JS_PATH.read_text(encoding="utf-8")

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)

        top = QHBoxLayout()
        top.addWidget(QLabel("Exercise:"))
        self.cmb = QComboBox()
        for s in specs:
            self.cmb.addItem(s.title)
        self.cmb.currentIndexChanged.connect(self.load_index)
        top.addWidget(self.cmb, 1)

        self.btnPrev = QPushButton("◀ Prev")
        self.btnPrev.clicked.connect(lambda: self.load_index(self._current_idx - 1))
        top.addWidget(self.btnPrev)

        self.btnNext = QPushButton("Next ▶")
        self.btnNext.clicked.connect(lambda: self.load_index(self._current_idx + 1))
        top.addWidget(self.btnNext)
        root.addLayout(top)

        self._score_container = QVBoxLayout()
        self._score_container.setContentsMargins(0, 0, 0, 0)
        root.addLayout(self._score_container, 1)

        self.load_index(0)

    # ------------------------------------------------------------------
    def _remove_current_score(self):
        if self._score_widget is None:
            return
        w = self._score_widget
        self._score_container.removeWidget(w)
        w.setParent(None)
        w.deleteLater()
        self._score_widget = None

    def _make_temp_score(self, spec: HarmonyExerciseSpec) -> Tuple[Path, dict]:
        compiled = compile_exercise(spec)
        musicxml, payload = build_exercise(compiled)

        tmp = tempfile.NamedTemporaryFile(
            prefix="harmony_", suffix=".xml", delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()
        tmp_path.write_text(musicxml, encoding="utf-8")
        self._tmp_paths.append(tmp_path)
        return tmp_path, payload

    def load_index(self, idx: int):
        if not self._specs:
            return
        idx = idx % len(self._specs)
        self._current_idx = idx
        spec = self._specs[idx]

        self.cmb.blockSignals(True)
        self.cmb.setCurrentIndex(idx)
        self.cmb.blockSignals(False)

        self.setWindowTitle(f"Harmony Trainer — {spec.title}")

        self._remove_current_score()
        mxl_path, payload = self._make_temp_score(spec)

        self._score_widget = ScoreViewBeats(str(mxl_path), midi_service=self._midi_service)
        self._score_container.addWidget(self._score_widget, 1)

        self._inject_trainer(self._score_widget, payload)

    def _inject_trainer(self, widget, payload: dict):
        def try_inject():
            w = self._score_widget
            if w is None or w is not widget:
                return  # exercise was switched again
            if not getattr(w, "_html_ready", False):
                QTimer.singleShot(60, try_inject)
                return
            # 1) define window.HarmonyTrainer, 2) initialise it with the payload.
            w._run_js_safe(self._trainer_js, label="harmony_trainer_js")
            init_js = "window.HarmonyTrainer && window.HarmonyTrainer.init(%s);" % (
                json.dumps(payload),
            )
            w._run_js_safe(init_js, label="harmony_trainer_init")

        QTimer.singleShot(60, try_inject)


def _load_specs(argv: List[str]) -> List[HarmonyExerciseSpec]:
    if len(argv) > 1 and argv[1] and Path(argv[1]).exists():
        return load_specs(argv[1])
    return default_demo_specs()


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    app = QApplication(argv)

    specs = _load_specs(argv)

    midi_service = None
    if MidiService is None:
        print("[HARMONY] MidiService import failed. MIDI will NOT work.")
    else:
        try:
            midi_service = MidiService()
            print("[HARMONY] MidiService active:",
                  getattr(midi_service, "port_name", None))
        except Exception as e:
            print("[HARMONY] MidiService init failed:", e)
            midi_service = None

    win = HarmonyTrainerWindow(specs, midi_service=midi_service)
    win.resize(1100, 800)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
