"""Harmonic Network / Tonal Graph -- standalone launcher (scene-driven).

Run::

    .venv/Scripts/python.exe run_harmonic_network_demo.py

Opens a **separate** window for the Harmonic Network layer:

  * LEFT/CENTER/RIGHT -- the network web UI (``beat_selector/harmonic_network.html``).
  * A small embedded **Harmony Trainer** (right of the splitter) so a launched drill actually
    plays/validates via MIDI.

**The graph is now chosen per exercise, automatically.**  Instead of building one fixed graph at
startup and projecting every drill onto it (which mis-mapped a G triad onto a G7 node, hid the
diatonic triads behind proxies, and conflated an Am chord with the A-minor key), the window:

  1. watches the embedded trainer's current exercise (``current_spec``);
  2. routes it through :func:`harmony.graph_scene_router.build_graph_scene` -- classifying the
     musical/pedagogical semantics (never the root pitch class) into a bounded, topic-specific
     :class:`~harmony.graph_scene.GraphScene`;
  3. pushes the whole scene to the graph with ``setScene`` (stale nodes dropped, no legacy
     pitch-class highlight running in parallel);
  4. drives the running occurrence position with ``updateOccurrenceState`` and routes graph/timeline
     seeks back to the trainer.

With no active exercise it shows the legacy key-relation graph as the **Explore** scene; an exercise
type with no honest graph yet (e.g. a melodic motive) shows a plain "no suitable harmonic graph"
message while the trainer keeps running.  A debug ``--scene=<type>`` override may pin a scene type;
an incompatible override warns rather than silently mis-mapping.
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

from harmony.exercise_spec import default_exercise_groups
from harmony.graph_scene_router import GraphSceneRequest, build_graph_scene
from harmony.graph_scene_generators import (
    build_legacy_scene, build_functional_progression_scene, progression_group_map,
)
from run_harmony_trainer_demo import (
    HarmonyTrainerWindow, MidiService, ATLAS_GROUP,
)

_HTML = Path(__file__).resolve().parent / "beat_selector" / "harmonic_network.html"


class HarmonicNetworkView(QWidget):
    """The Harmonic Network web UI in a QWebEngineView. **Dual-mode**:

      * SCENE mode (the primary, scene-routed path): construct with
        ``initial_scene=<GraphScene dict>`` and drive with ``set_scene`` /
        ``update_occurrence_state`` / ``clear_scene``.
      * LEGACY mode (backward compatibility): construct with a network payload
        (positional) and drive with the network + projection API
        (``send_projection`` / ``update_flow_state`` / ``highlight_from_trainer``
        + the ``launchRequested`` signal).  The Functional Degree Network launcher
        and the Score Soul demo use their own non-scene graph models, so they keep
        this API.

    Both modes poll ``takeLaunch`` (-> ``launchRequested``) and ``takeHostRequest``
    (-> ``hostRequested``), so a seek from the scene timeline and a legacy launch
    both reach the host.
    """

    #: Emitted with a raw HarmonyExerciseSpec dict when a legacy launch is clicked.
    launchRequested = pyqtSignal(dict)
    #: Emitted with a typed host request from the graph (e.g. {"type":"seek", ...}).
    hostRequested = pyqtSignal(dict)

    def __init__(self, payload: Optional[dict] = None, parent=None, *,
                 initial_scene: Optional[dict] = None):
        super().__init__(parent)
        self._ready = False
        self._network_payload = payload          # legacy network dict (or None)
        self._pending_scene = initial_scene      # scene dict (or None)

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

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(200)
        self._poll_timer.timeout.connect(self._poll)

    # -- lifecycle -------------------------------------------------------
    def _on_loaded(self, ok: bool):
        if not ok:
            return
        self._ready = True
        if self._pending_scene is not None:
            self._push_scene(self._pending_scene)
            self._pending_scene = None
        elif self._network_payload is not None:
            self._run_js(
                "window.HARMONIC_NETWORK_DATA = %s; window.HarmonicNetwork && "
                "window.HarmonicNetwork.init(window.HARMONIC_NETWORK_DATA);"
                % json.dumps(self._network_payload))
        self._poll_timer.start()

    def _run_js(self, code: str, cb=None):
        try:
            if cb is None:
                self.web.page().runJavaScript(code)
            else:
                self.web.page().runJavaScript(code, cb)
        except Exception:
            pass

    # -- scene control (the primary API) ---------------------------------
    def set_scene(self, scene_dict: dict):
        if not self._ready:
            self._pending_scene = scene_dict
            return
        self._push_scene(scene_dict)

    def _push_scene(self, scene_dict: dict):
        self._run_js("window.HarmonicNetwork && window.HarmonicNetwork.setScene(%s);"
                     % json.dumps(scene_dict))

    def update_occurrence_state(self, state: dict):
        if self._ready and state:
            self._run_js("window.HarmonicNetwork && "
                         "window.HarmonicNetwork.updateOccurrenceState(%s);" % json.dumps(state))

    def clear_scene(self, reason: str = ""):
        if self._ready:
            self._run_js("window.HarmonicNetwork && "
                         "window.HarmonicNetwork.clearScene(%s);" % json.dumps(reason))

    # -- legacy network + projection API (Functional / Score layers) -----
    def send_projection(self, projection: dict):
        if self._ready and projection:
            self._run_js("window.HarmonicNetwork && "
                         "window.HarmonicNetwork.setProjection(%s);" % json.dumps(projection))

    def clear_projection(self):
        if self._ready:
            self._run_js("window.HarmonicNetwork && window.HarmonicNetwork.clearProjection();")

    def update_flow_state(self, state: dict):
        if self._ready and state:
            self._run_js("window.HarmonicNetwork && "
                         "window.HarmonicNetwork.updateFlowState(%s);" % json.dumps(state))

    def highlight_from_trainer(self, target: dict):
        if self._ready and target:
            self._run_js("window.HarmonicNetwork && "
                         "window.HarmonicNetwork.highlightFromTrainerTarget(%s);"
                         % json.dumps(target))

    # -- graph -> host requests (legacy launch + scene seek) -------------
    def _poll(self):
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
            "? JSON.stringify(window.HarmonicNetwork.takeLaunch() || null) : null", on_spec)

        def on_req(val):
            if not val:
                return
            try:
                req = json.loads(val)
            except Exception:
                return
            if isinstance(req, dict) and req.get("type"):
                self.hostRequested.emit(req)

        self._run_js(
            "(window.HarmonicNetwork && window.HarmonicNetwork.takeHostRequest) "
            "? JSON.stringify(window.HarmonicNetwork.takeHostRequest() || null) : null", on_req)


class HarmonicNetworkWindow(QWidget):
    """Top-level window: scene graph (left) + Harmony Trainer (right), scene chosen per exercise."""

    def __init__(self, midi_service=None, preferred_scene_type: Optional[str] = None):
        super().__init__()
        self.setWindowTitle("Harmonic Network / Tonal Graph")
        self._preferred_scene_type = preferred_scene_type

        # The embedded trainer offers the full canonical drill set, so switching drills in its
        # dropdown re-routes the graph scene. (Plus an empty From-Atlas group for external loads.)
        groups = default_exercise_groups()
        groups[ATLAS_GROUP] = []
        self.trainer = HarmonyTrainerWindow(
            groups, midi_service=midi_service, with_circle=False)

        # Start on the Explore scene (the legacy key-relation graph); the first poll routes the
        # trainer's initial exercise to its own scene.
        self.net_view = HarmonicNetworkView(initial_scene=build_legacy_scene().to_dict())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.net_view)
        splitter.addWidget(self.trainer)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(splitter, 1)

        self.net_view.hostRequested.connect(self._on_host_request)

        #: exercise_id of the scene currently on the graph (detects drill switches).
        self._active_scene_spec_id: Optional[str] = None
        self._last_seq_index: Optional[int] = None
        self._active_scene = None
        self._active_spec = None
        #: cross-key functional progressions show one local key at a time; these track the group
        #: structure + which local key is on screen so the host can switch at a group boundary.
        self._prog_groups = None            # [{groupIndex, key, globalStart, count}] or None
        self._shown_group = 0

        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(350)
        self._sync_timer.timeout.connect(self._poll_sync)
        self._sync_timer.start()

    # -- the section-7 host entry point ----------------------------------
    def load_graph_scene_for_exercise(self, *, curriculum_node_id=None, lab_spec=None,
                                      exercise_spec=None):
        """Route the active exercise to a bounded scene and push it to the graph."""
        req = GraphSceneRequest(
            curriculum_node_id=curriculum_node_id, lab_spec=lab_spec, exercise_spec=exercise_spec,
            preferred_scene_type=self._preferred_scene_type)
        try:
            scene = build_graph_scene(req)
        except Exception as exc:  # never crash the host over a routing/build error
            print("[NETWORK] scene routing failed (trainer keeps running):", exc)
            self.net_view.clear_scene("scene routing failed")
            return None
        self._active_scene = scene
        self._last_seq_index = None
        self.net_view.set_scene(scene.to_dict())
        return scene

    # -- follow the trainer: re-route on drill change, drive occurrences --
    def _poll_sync(self):
        try:
            spec = self.trainer.current_spec()
        except Exception:
            spec = None
        sid = spec.exercise_id if spec is not None else None

        if sid != self._active_scene_spec_id:
            self._active_scene_spec_id = sid
            self._active_spec = spec
            self._last_seq_index = None
            self._shown_group = 0
            self._prog_groups = None
            if spec is not None:
                scene = self.load_graph_scene_for_exercise(exercise_spec=spec)
                # cache the group structure for cross-key functional switching
                if (scene is not None and scene.scene_type == "functional_progression"
                        and scene.metadata.get("totalGroups", 1) > 1):
                    try:
                        self._prog_groups = progression_group_map(spec)
                    except Exception:
                        self._prog_groups = None
            else:
                self._active_scene = None
                self.net_view.set_scene(build_legacy_scene().to_dict())

        if spec is None:
            return

        def on_state(state):
            if not state:
                return
            idx = state.get("idx")
            if idx is None:
                return
            completed = bool(state.get("completed"))
            local = idx
            # cross-key functional progression: switch the local-key scene at a group boundary,
            # and translate the trainer's GLOBAL chord index into the shown group's local index.
            if self._prog_groups:
                gi = self._group_of(idx)
                if gi is not None:
                    if gi != self._shown_group:
                        self._shown_group = gi
                        self._last_seq_index = None
                        try:
                            scene = build_functional_progression_scene(
                                self._active_spec, group_index=gi)
                            self._active_scene = scene
                            self.net_view.set_scene(scene.to_dict())
                        except Exception as exc:
                            print("[NETWORK] local-key scene switch failed:", exc)
                    local = idx - self._prog_groups[gi]["globalStart"]
            if local == self._last_seq_index and not completed:
                return
            self._last_seq_index = local
            payload = {"sequenceIndex": local}
            if completed:
                payload["correct"] = True
            self.net_view.update_occurrence_state(payload)

        try:
            self.trainer.query_trainer_state(on_state)
        except Exception:
            pass

    def _group_of(self, idx: int):
        """The group index containing global chord ``idx`` (cross-key progression), or None."""
        for g in (self._prog_groups or []):
            if g["globalStart"] <= idx < g["globalStart"] + g["count"]:
                return g["groupIndex"]
        return None

    def _on_host_request(self, req: dict):
        if not isinstance(req, dict):
            return
        if req.get("type") == "seek" and req.get("sequenceIndex") is not None:
            try:
                self.trainer.seek_to_index(int(req["sequenceIndex"]))
            except Exception:
                pass


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)

    # Optional debug scene override: `--scene=diatonic_key_field` (or a bare scene-type arg).
    # An incompatible override warns (the router returns 'ambiguous') rather than mis-mapping.
    preferred_scene_type = None
    for a in argv[1:]:
        if a.startswith("--scene="):
            preferred_scene_type = a.split("=", 1)[1]
        elif not a.startswith("-"):
            preferred_scene_type = a

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

    win = HarmonicNetworkWindow(
        midi_service=midi_service, preferred_scene_type=preferred_scene_type)
    win.resize(1560, 880)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
