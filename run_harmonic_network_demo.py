"""Harmonic Network / Tonal Graph -- standalone launcher.

Run::

    .venv/Scripts/python.exe run_harmonic_network_demo.py

Opens a **separate** window for the Harmonic Network layer (it is deliberately
NOT embedded in the already-crowded Music Theory Laboratory):

  * LEFT/CENTER/RIGHT -- the network web UI (``harmony.harmonic_network`` ->
    ``beat_selector/harmonic_network.html``): graph controls + node/edge toggles
    + search on the left, the SVG harmonic network in the centre, and the
    selected node/edge explanation + related Atlas/Trainer/Lab actions + launch
    buttons on the right.
  * A small embedded **Harmony Trainer** (right of the splitter) so a launched
    drill actually plays/validates via MIDI -- reusing the exact
    ``HarmonyTrainerWindow`` + ``runJavaScript`` + polling pattern of
    ``run_harmony_atlas_demo.py`` (no QWebChannel).

The network only ever hands the trainer a real, triad-based
``HarmonyExerciseSpec`` (dominant-seventh nodes expose a *reserved* drill, never
a launchable one).  The existing Atlas / Circle / Trainer / Lab / Curriculum
launchers are untouched.
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

from harmony.harmonic_network import build_network
from harmony.network_template import get_template
from harmony.exercise_spec import HarmonyExerciseSpec, default_exercise_groups
from run_harmony_trainer_demo import (
    HarmonyTrainerWindow, MidiService, ATLAS_GROUP,
)

_HTML = Path(__file__).resolve().parent / "beat_selector" / "harmonic_network.html"


class HarmonicNetworkView(QWidget):
    """The Harmonic Network web UI in a QWebEngineView, with host hooks."""

    #: Emitted with a HarmonyExerciseSpec dict when a launch button is clicked.
    launchRequested = pyqtSignal(dict)

    def __init__(self, payload: dict, parent=None):
        super().__init__(parent)
        self._payload = payload
        self._ready = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        top.setContentsMargins(6, 6, 6, 6)
        top.addWidget(QLabel("Harmonic Network / Tonal Graph"))
        top.addStretch(1)
        layout.addLayout(top)

        self.web = QWebEngineView(self)
        self.web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        layout.addWidget(self.web, 1)

        self.web.loadFinished.connect(self._on_loaded)
        self.web.load(QUrl.fromLocalFile(str(_HTML)))

        self._launch_timer = QTimer(self)
        self._launch_timer.setInterval(200)
        self._launch_timer.timeout.connect(self._poll_launch)

    # -- lifecycle -------------------------------------------------------
    def _on_loaded(self, ok: bool):
        if not ok:
            return
        data_js = json.dumps(self._payload)
        self._run_js(
            "window.HARMONIC_NETWORK_DATA = %s; "
            "window.HarmonicNetwork && "
            "window.HarmonicNetwork.init(window.HARMONIC_NETWORK_DATA);" % data_js)
        self._ready = True
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
        if not self._ready:
            return

        def on_spec(val):
            if not val:
                return
            try:
                spec = json.loads(val)
            except Exception:
                return
            if isinstance(spec, dict) and spec.get("drill"):
                self.launchRequested.emit(spec)

        self._run_js(
            "(window.HarmonicNetwork && window.HarmonicNetwork.takeLaunch) "
            "? JSON.stringify(window.HarmonicNetwork.takeLaunch() || null) : null",
            on_spec)

    # -- sync from the trainer's current chord ---------------------------
    def highlight_from_trainer(self, target: dict):
        if self._ready and target:
            self._run_js(
                "window.HarmonicNetwork && "
                "window.HarmonicNetwork.highlightFromTrainerTarget(%s);"
                % json.dumps(target))


class HarmonicNetworkWindow(QWidget):
    """Top-level window: network web UI (left) + Harmony Trainer (right)."""

    def __init__(self, midi_service=None, template_id: Optional[str] = None):
        super().__init__()
        self.setWindowTitle("Harmonic Network / Tonal Graph")

        template = get_template(template_id)
        self._network = build_network(template)

        # A trainer with the full default groups plus an (empty) launch group.
        groups = default_exercise_groups()
        groups[ATLAS_GROUP] = []
        self.trainer = HarmonyTrainerWindow(
            groups, midi_service=midi_service, with_circle=False)

        self.net_view = HarmonicNetworkView(self._network.to_payload())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.net_view)
        splitter.addWidget(self.trainer)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(splitter, 1)

        self.net_view.launchRequested.connect(self._on_launch)

        # Follow the trainer's current chord and highlight it in the network.
        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(400)
        self._sync_timer.timeout.connect(self._poll_sync)
        self._sync_timer.start()

    def _on_launch(self, spec_dict: dict):
        try:
            spec = HarmonyExerciseSpec.from_dict(spec_dict)
        except Exception as exc:  # malformed payload -> ignore, keep running
            print("[NETWORK] ignoring invalid spec:", exc)
            return
        self.trainer.load_external_spec(spec)

    def _poll_sync(self):
        def on_target(target):
            if target:
                self.net_view.highlight_from_trainer(target)

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
        print("[NETWORK] MidiService import failed. MIDI will NOT work.")
    else:
        try:
            midi_service = MidiService()
            print("[NETWORK] MidiService active:",
                  getattr(midi_service, "port_name", None))
        except Exception as exc:
            print("[NETWORK] MidiService init failed:", exc)
            midi_service = None

    win = HarmonicNetworkWindow(midi_service=midi_service)
    win.resize(1560, 880)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
