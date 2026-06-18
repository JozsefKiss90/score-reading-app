"""Music Theory Laboratory -- combined launcher.

Run::

    .venv/Scripts/python.exe run_harmony_lab_demo.py

This wires the **Music Theory Laboratory** (``harmony.lab`` ->
``beat_selector/harmony_lab.html``) next to the existing **Harmony Trainer**:

  * The Lab (left) lists experiments by concept -- inversions, voice-leading
    cadences, motive transposition, polyphonic harmony, and a reserved
    real-score-analysis placeholder.  Each is a
    :class:`~harmony.lab_spec.LabExperimentSpec`.
  * Clicking an experiment compiles it (``compile_lab``), renders playable
    MusicXML + a trainer payload (``build_lab_exercise``), and loads it into the
    Harmony Trainer (middle) via the additive
    :meth:`HarmonyTrainerWindow.load_external_lab` -- which plays / MIDI-validates
    it through the unchanged ``ScoreViewBeats`` + ``harmony_trainer.js``.
  * While an experiment plays, the Lab follows the trainer's current chord,
    explaining it on the right (inversion / figured bass / voice leading /
    implied harmony) and highlighting the live Atlas mapping at the bottom.

JS<->Python uses the same ``runJavaScript`` + polling pattern as the Atlas /
Circle integrations (no QWebChannel).  The existing trainer and atlas demos are
left working; ``run_harmony_trainer_demo.py`` only gained the additive
``load_external_lab`` method.
"""

from __future__ import annotations

import json
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QCoreApplication, QTimer, QUrl, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSplitter,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

from harmony.atlas import build_atlas
from harmony.lab_spec import LabExperimentSpec
from harmony.lab import compile_lab, lab_demo_specs
from harmony.lab_musicxml import build_lab_exercise
from run_harmony_trainer_demo import HarmonyTrainerWindow, MidiService

_LAB_HTML = Path(__file__).resolve().parent / "beat_selector" / "harmony_lab.html"

#: The concept selector catalog (presentational; the experiments come from
#: harmony.lab.lab_demo_specs()).  ``real_score_analysis`` is the reserved
#: placeholder for Phase 6 (no experiments yet).
CONCEPT_CATALOG = [
    {"id": "inversion", "label": "Inversions",
     "detail": "The same chord tones stay; only the bass changes (5/3 · 6 · 6/4)."},
    {"id": "voice_leading_cadence", "label": "Voice-leading cadences",
     "detail": "V–I, IV–I, V–vi, ii–V–I and minor cadences as SATB voice leading."},
    {"id": "motive", "label": "Motive transposition",
     "detail": "A scale-degree cell transposed through every key."},
    {"id": "polyphonic_harmony", "label": "Polyphonic harmony",
     "detail": "Two independent voices whose vertical slices imply a triad."},
    {"id": "real_score_analysis", "label": "Real score analysis",
     "detail": "Reserved — map an imported score's chords onto the Atlas.",
     "reserved": True},
]


def build_lab_catalog() -> dict:
    """The ``window.LAB_DATA`` payload: concept catalog + serialised experiments."""
    return {
        "schema": "harmony-lab/v1",
        "concepts": [dict(c) for c in CONCEPT_CATALOG],
        "experiments": [s.to_dict() for s in lab_demo_specs()],
    }


class LabView(QWidget):
    """The Lab web UI (concept selector + explanation) in a QWebEngineView."""

    #: Emitted with a LabExperimentSpec dict when an experiment is clicked.
    launchRequested = pyqtSignal(dict)

    def __init__(self, catalog: dict, parent=None):
        super().__init__(parent)
        self._catalog = catalog
        self._html_ready = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.web = QWebEngineView(self)
        self.web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        layout.addWidget(self.web, 1)

        self.web.loadFinished.connect(self._on_loaded)
        self.web.load(QUrl.fromLocalFile(str(_LAB_HTML)))

        self._launch_timer = QTimer(self)
        self._launch_timer.setInterval(200)
        self._launch_timer.timeout.connect(self._poll_launch)

    def _on_loaded(self, ok: bool):
        if not ok:
            return
        self._run_js(
            "window.LAB_DATA = %s; "
            "window.HarmonyLab && window.HarmonyLab.init(window.LAB_DATA);"
            % json.dumps(self._catalog))
        self._html_ready = True
        self._launch_timer.start()

    def _run_js(self, code: str, cb=None):
        try:
            if cb is None:
                self.web.page().runJavaScript(code)
            else:
                self.web.page().runJavaScript(code, cb)
        except Exception:
            pass

    def _poll_launch(self):
        if not self._html_ready:
            return

        def on_spec(val):
            if not val:
                return
            try:
                spec = json.loads(val)
            except Exception:
                return
            if isinstance(spec, dict) and spec.get("concept"):
                self.launchRequested.emit(spec)

        self._run_js(
            "(window.HarmonyLab && window.HarmonyLab.takeLaunch) "
            "? JSON.stringify(window.HarmonyLab.takeLaunch() || null) : null",
            on_spec)

    def update_explanation(self, target: Optional[dict]):
        if self._html_ready and target is not None:
            self._run_js("window.HarmonyLab && "
                         "window.HarmonyLab.updateExplanation(%s);"
                         % json.dumps(target))

    def set_sync(self, active: dict):
        if self._html_ready:
            self._run_js("window.HarmonyLab && window.HarmonyLab.setSync(%s);"
                         % json.dumps(active))


class HarmonyLabWindow(QWidget):
    """Top-level window: Lab selector/explanation (left) + Harmony Trainer (middle)."""

    def __init__(self, midi_service=None):
        super().__init__()
        self.setWindowTitle("Music Theory Laboratory")

        self._atlas = build_atlas()

        # The trainer is the score + MIDI host; the Lab drives it, so it needs no
        # built-in exercise groups or Circle panel.
        self.trainer = HarmonyTrainerWindow(
            OrderedDict(), midi_service=midi_service, with_circle=False)

        self.lab_view = LabView(build_lab_catalog())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.lab_view)
        splitter.addWidget(self.trainer)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(splitter, 1)

        self.lab_view.launchRequested.connect(self._on_launch)

        # Follow the trainer's current chord -> explanation + Atlas highlight.
        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(400)
        self._sync_timer.timeout.connect(self._poll_sync)
        self._sync_timer.start()

        # Auto-load the first experiment so the window is not blank.
        self._demo_specs = {s.experiment_id: s for s in lab_demo_specs()}
        first = lab_demo_specs()[0]
        QTimer.singleShot(700, lambda: self._launch_spec(first))

    def _on_launch(self, spec_dict: dict):
        try:
            spec = LabExperimentSpec.from_dict(spec_dict)
        except Exception as exc:  # malformed payload -> ignore, keep running
            print("[LAB] ignoring invalid experiment:", exc)
            return
        self._launch_spec(spec)

    def _launch_spec(self, spec: LabExperimentSpec):
        try:
            experiment = compile_lab(spec)
            musicxml, payload = build_lab_exercise(experiment)
        except NotImplementedError as exc:
            print("[LAB] reserved experiment:", exc)
            return
        except Exception as exc:
            print("[LAB] failed to compile experiment:", exc)
            return
        self.trainer.load_external_lab(musicxml, payload)

    def _poll_sync(self):
        def on_target(target):
            if not target:
                return
            self.lab_view.update_explanation(target)
            active = self._atlas.sync(target).get("active", {})
            if target.get("concept") == "melody":
                # A monophonic motive implies no triad/degree — keep only the
                # scale chip (its first degree must not surface as a tonic-triad).
                active = {"scale": active.get("scale")}
            self.lab_view.set_sync({k: v for k, v in active.items() if v})

        try:
            self.trainer.query_current_target(on_target)
        except Exception:
            pass


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    app = QApplication(argv)

    midi_service = None
    if MidiService is None:
        print("[LAB] MidiService import failed. MIDI will NOT work.")
    else:
        try:
            midi_service = MidiService()
            print("[LAB] MidiService active:", getattr(midi_service, "port_name", None))
        except Exception as exc:
            print("[LAB] MidiService init failed:", exc)
            midi_service = None

    win = HarmonyLabWindow(midi_service=midi_service)
    win.resize(1500, 860)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
