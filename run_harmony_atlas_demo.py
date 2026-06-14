"""Interactive Harmony Atlas -- combined launcher.

Run::

    .venv/Scripts/python.exe run_harmony_atlas_demo.py

This wires the **Interactive Harmony Atlas** (the central theoretical map,
``harmony.atlas`` -> ``beat_selector/atlas.html``) next to the existing
**Harmony Trainer**:

  * The Atlas (left) renders the whole invariant tonal system as clickable
    tabs -- global diatonic map, transposition matrix, quality matrix, function
    map, interval-layer map, cadence map, learning path, progress, and the
    ontology graph.  Every element is derived from the theory engine and
    resolves to a playable ``HarmonyExerciseSpec``.
  * Clicking any Atlas element loads that exercise into the Harmony Trainer
    (right), which plays / validates it via MIDI exactly as before.
  * While an exercise runs, the Atlas follows the trainer's current chord,
    highlighting the live key / degree / triad / quality / interval-layer /
    function (Atlas spec, Part VII).

The Atlas is a pure QWebEngine view (no MIDI of its own); JS<->Python uses the
same ``runJavaScript`` + polling pattern the rest of the app uses (no
QWebChannel).  The existing ``run_harmony_trainer_demo.py`` is left untouched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QCoreApplication, QTimer, QUrl, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSplitter,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

from harmony.atlas import build_atlas, level_for_spec
from harmony.exercise_spec import (
    HarmonyExerciseSpec, default_exercise_groups,
)
from run_harmony_trainer_demo import (
    HarmonyTrainerWindow, MidiService, ATLAS_GROUP,
)

_ATLAS_HTML = Path(__file__).resolve().parent / "beat_selector" / "atlas.html"


class AtlasView(QWidget):
    """The Atlas web UI in a QWebEngineView, with host integration hooks."""

    #: Emitted with a HarmonyExerciseSpec dict when an Atlas element is clicked.
    launchRequested = pyqtSignal(dict)

    def __init__(self, atlas_payload: dict, parent=None):
        super().__init__(parent)
        self._payload = atlas_payload
        self._html_ready = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        top.setContentsMargins(6, 6, 6, 6)
        top.addWidget(QLabel("Interactive Harmony Atlas"))
        top.addStretch(1)
        layout.addLayout(top)

        self.web = QWebEngineView(self)
        self.web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        layout.addWidget(self.web, 1)

        self.web.loadFinished.connect(self._on_loaded)
        self.web.load(QUrl.fromLocalFile(str(_ATLAS_HTML)))

        # Poll the page for clicked exercises (mirrors the trainer's polling).
        self._launch_timer = QTimer(self)
        self._launch_timer.setInterval(200)
        self._launch_timer.timeout.connect(self._poll_launch)

    # -- lifecycle -------------------------------------------------------
    def _on_loaded(self, ok: bool):
        if not ok:
            return
        data_js = json.dumps(self._payload)
        self._run_js(
            "window.ATLAS_DATA = %s; "
            "window.AtlasUI && window.AtlasUI.init(window.ATLAS_DATA);" % data_js)
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

    # -- click -> launch -------------------------------------------------
    def _poll_launch(self):
        if not self._html_ready:
            return

        def on_spec(val):
            # Match the trainer's bridge: stringify in JS, json.loads here, rather
            # than rely on implicit QWebEngine JS-object -> Python-dict conversion.
            if not val:
                return
            try:
                spec = json.loads(val)
            except Exception:
                return
            if isinstance(spec, dict) and spec.get("drill"):
                self.launchRequested.emit(spec)

        self._run_js(
            "(window.AtlasUI && window.AtlasUI.takeLaunch) "
            "? JSON.stringify(window.AtlasUI.takeLaunch() || null) : null",
            on_spec)

    # -- Part VII: sync --------------------------------------------------
    def set_sync(self, active: dict):
        if self._html_ready:
            self._run_js("window.AtlasUI && window.AtlasUI.setSync(%s);"
                         % json.dumps(active))

    def set_current_level(self, level: Optional[str]):
        if self._html_ready and level:
            self._run_js("window.AtlasUI && window.AtlasUI.setCurrentLevel(%s);"
                         % json.dumps(level))


class HarmonyAtlasWindow(QWidget):
    """Top-level window: Atlas (left) + Harmony Trainer (right)."""

    def __init__(self, midi_service=None):
        super().__init__()
        self.setWindowTitle("Interactive Harmony Atlas")

        self._atlas = build_atlas()

        # Trainer with the full default groups plus an (empty) Atlas group.
        groups = default_exercise_groups()
        groups[ATLAS_GROUP] = []
        self.trainer = HarmonyTrainerWindow(groups, midi_service=midi_service)

        self.atlas_view = AtlasView(self._atlas.to_json())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.atlas_view)
        splitter.addWidget(self.trainer)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(splitter, 1)

        self.atlas_view.launchRequested.connect(self._on_launch)

        # Follow the trainer's current chord and highlight it in the Atlas.
        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(400)
        self._sync_timer.timeout.connect(self._poll_sync)
        self._sync_timer.start()

    def _on_launch(self, spec_dict: dict):
        try:
            spec = HarmonyExerciseSpec.from_dict(spec_dict)
        except Exception as exc:  # malformed payload -> ignore, keep running
            print("[ATLAS] ignoring invalid spec:", exc)
            return
        self.trainer.load_external_spec(spec)
        self.atlas_view.set_current_level(level_for_spec(spec))

    def _poll_sync(self):
        def on_target(target):
            if not target:
                return
            active = self._atlas.sync(target).get("active", {})
            # Drop None values so only real ids are sent.
            self.atlas_view.set_sync({k: v for k, v in active.items() if v})

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
        print("[ATLAS] MidiService import failed. MIDI will NOT work.")
    else:
        try:
            midi_service = MidiService()
            print("[ATLAS] MidiService active:",
                  getattr(midi_service, "port_name", None))
        except Exception as exc:
            print("[ATLAS] MidiService init failed:", exc)
            midi_service = None

    win = HarmonyAtlasWindow(midi_service=midi_service)
    win.resize(1500, 860)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
