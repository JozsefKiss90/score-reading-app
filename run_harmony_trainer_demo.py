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

    def _cleanup_temp(self):
        """Delete generated temp MusicXML files (best-effort)."""
        for p in self._tmp_paths:
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
        self._tmp_paths.clear()

    def _make_temp_score(self, spec: HarmonyExerciseSpec) -> Tuple[Path, dict]:
        compiled = compile_exercise(spec)
        musicxml, payload = build_exercise(compiled)

        # Only one score is shown at a time; drop the previous temp file.
        self._cleanup_temp()

        tmp = tempfile.NamedTemporaryFile(
            prefix="harmony_", suffix=".xml", delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()
        tmp_path.write_text(musicxml, encoding="utf-8")
        self._tmp_paths.append(tmp_path)
        return tmp_path, payload

    def closeEvent(self, event):
        self._cleanup_temp()
        super().closeEvent(event)

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

        # The trainer owns the MIDI-highlight state and uses single-page scores,
        # so hide the viewer's beat-selector toggle (which would fight over
        # selNotesByMidi) and the page-nav buttons (the trainer navigates by
        # chord in its own panel).
        for attr in ("btnBeats", "btnPrev", "btnNext"):
            btn = getattr(self._score_widget, attr, None)
            if btn is not None:
                btn.hide()

        self._ensure_trainer(self._score_widget, payload)

    def _ensure_trainer(self, widget, payload: dict):
        """(Re)inject the controller whenever it is missing.

        ScoreViewBeats reloads the QWebEngine page on page navigation, which
        wipes the injected controller. A light poll re-injects it on the initial
        load and after any such reload, without modifying the shared viewer.
        """
        init_js = "window.HarmonyTrainer && window.HarmonyTrainer.init(%s);" % (
            json.dumps(payload),
        )

        def tick():
            w = self._score_widget
            if w is None or w is not widget:
                return  # exercise switched -> stop this watcher
            if not getattr(w, "_html_ready", False):
                QTimer.singleShot(120, tick)
                return

            def on_check(installed):
                ww = self._score_widget
                if ww is None or ww is not widget:
                    return
                if not installed:
                    ww._run_js_safe(self._trainer_js, label="harmony_trainer_js")
                    ww._run_js_safe(init_js, label="harmony_trainer_init")
                QTimer.singleShot(600, tick)

            try:
                w.web.page().runJavaScript(
                    "!!(window.HarmonyTrainer && window.HarmonyTrainer.state)",
                    on_check,
                )
            except Exception:
                QTimer.singleShot(600, tick)

        QTimer.singleShot(80, tick)


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
