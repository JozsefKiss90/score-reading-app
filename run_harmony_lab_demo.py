"""Music Theory Laboratory -- combined launcher (three-pane learning workspace).

Run::

    .venv/Scripts/python.exe run_harmony_lab_demo.py

This wires the **Music Theory Laboratory** into a complete learning workspace
around the existing **Harmony Trainer**, the **Interactive Harmony Atlas**, and
the **Interactive Circle of Fifths** -- integrating them, not rewriting them:

  * **LEFT** (``beat_selector/harmony_lab.html`` / ``.js``): the Concept
    Catalogue, a rich Concept-Theory explanation (from
    :mod:`harmony.lab_explanations`), and a dynamically generated Example
    Explanation of the selected experiment.
  * **MIDDLE**: the reused :class:`HarmonyTrainerWindow` (score + MIDI keyboard +
    green/red validation), driven by the unchanged ``ScoreViewBeats`` +
    ``harmony_trainer.js`` via the additive ``load_external_lab``.
  * **RIGHT**: a tabbed analytical dashboard -- the **full Interactive Harmony
    Atlas** (reused :class:`AtlasView`), the **Circle of Fifths** (reused
    :class:`CircleView`, here with "Open ... lab" affordances), a **Cheatsheet**,
    and a live **Current Mapping** of the playing measure.

When an experiment plays, the workspace follows the trainer's current chord and
highlights the corresponding key / mode / degree / triad / quality / interval
layer / function / cadence in the Atlas and the Circle, refreshes the Current
Mapping, and explains the current measure.

JS<->Python uses the same ``runJavaScript`` + polling bridge as the Atlas /
Circle integrations (no QWebChannel).  The existing trainer, atlas, and circle
launchers are left working: this module only *reuses* their widgets.
"""

from __future__ import annotations

import json
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QCoreApplication, QTimer, QUrl, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSplitter, QTabWidget,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

from datetime import datetime, timezone

from harmony.atlas import build_atlas
from harmony.circle_payload import build_circle_payload, spec_from_circle_request
from harmony.lab_spec import LabExperimentSpec, spec_from_lab_request
from harmony.lab import compile_lab, lab_demo_specs
from harmony.lab_musicxml import build_lab_exercise
from harmony.lab_explanations import (
    get_concept_explanation, get_experiment_explanation, get_measure_explanation,
    mapping_from_target,
)
from harmony.exercise_spec import HarmonyExerciseSpec
from harmony.curriculum import get_curriculum
from harmony.curriculum_explanations import build_curriculum_payload
from harmony.progress_service import ProgressService
from harmony.echo_drills import echo_variant, echo_unlocked, is_echo_eligible
from harmony.graph_scene_router import GraphSceneRequest, build_graph_scene
from harmony.graph_scene_generators import (
    build_legacy_scene, build_functional_progression_scene, progression_group_map,
)
from run_harmony_trainer_demo import HarmonyTrainerWindow, MidiService, CircleView
from run_harmony_atlas_demo import AtlasView
from run_harmonic_network_demo import HarmonicNetworkView
from run_dashboard_demo import DashboardView

_BEAT = Path(__file__).resolve().parent / "beat_selector"
_LAB_HTML = _BEAT / "harmony_lab.html"               # legacy flat catalogue (kept)
_CURRICULUM_HTML = _BEAT / "curriculum.html"          # canonical curriculum browser
_CHEAT_HTML = _BEAT / "lab_cheatsheet.html"
_MAP_HTML = _BEAT / "lab_mapping.html"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

#: The concept selector catalog (presentational; the experiments come from
#: harmony.lab.lab_demo_specs()).  ``real_score_analysis`` is the reserved
#: placeholder for Phase 6 (no experiments yet).  Each entry is enriched with its
#: structured theory explanation (harmony.lab_explanations) at build time.
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
    """The ``window.LAB_DATA`` payload: concept catalog (+ theory) + experiments."""
    concepts = []
    for c in CONCEPT_CATALOG:
        entry = dict(c)
        try:
            entry["explanation"] = get_concept_explanation(c["id"])
        except ValueError:
            entry["explanation"] = None
        concepts.append(entry)
    return {
        "schema": "harmony-lab/v1",
        "concepts": concepts,
        "experiments": [s.to_dict() for s in lab_demo_specs()],
    }


# ---------------------------------------------------------------------------
# Left panel: the Lab concept/theory/example web UI
# ---------------------------------------------------------------------------

class LabView(QWidget):
    """The Lab web UI (catalogue + concept theory + example explanation)."""

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

    def set_experiment_explanation(self, expl: dict):
        if self._html_ready:
            self._run_js("window.HarmonyLab && "
                         "window.HarmonyLab.setExperimentExplanation(%s);"
                         % json.dumps(expl))

    def set_sync(self, active: dict):
        if self._html_ready:
            self._run_js("window.HarmonyLab && window.HarmonyLab.setSync(%s);"
                         % json.dumps(active))


# ---------------------------------------------------------------------------
# Left panel (canonical): the curriculum tree browser
# ---------------------------------------------------------------------------

class CurriculumView(QWidget):
    """The canonical curriculum browser (replaces the flat Concept Catalogue).

    Renders ``beat_selector/curriculum.html`` + ``curriculum.js`` and bridges via
    the same ``runJavaScript`` polling pattern as the Atlas / Circle panels:

    * polls ``Curriculum.takeLaunch()`` -> ``launchRequested`` (a clicked
      LabExperimentSpec, ready for the trainer);
    * polls ``Curriculum.takeSelection()`` -> ``selectionRequested`` (a selected
      node id, for curriculum -> Atlas / Circle highlighting);
    * pushes the live guide, the Atlas sync strip, and the progress overlay.
    """

    launchRequested = pyqtSignal(dict)        # a clicked LabExperimentSpec dict
    selectionRequested = pyqtSignal(str)      # a selected curriculum node id

    def __init__(self, payload: dict, parent=None):
        super().__init__(parent)
        self._payload = payload
        self._html_ready = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.web = QWebEngineView(self)
        self.web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        layout.addWidget(self.web, 1)

        self.web.loadFinished.connect(self._on_loaded)
        self.web.load(QUrl.fromLocalFile(str(_CURRICULUM_HTML)))

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(200)
        self._poll_timer.timeout.connect(self._poll)

    def _on_loaded(self, ok: bool):
        if not ok:
            return
        self._run_js(
            "window.CURRICULUM = %s; "
            "window.Curriculum && window.Curriculum.init(window.CURRICULUM);"
            % json.dumps(self._payload))
        self._html_ready = True
        self._poll_timer.start()

    def _run_js(self, code: str, cb=None):
        try:
            if cb is None:
                self.web.page().runJavaScript(code)
            else:
                self.web.page().runJavaScript(code, cb)
        except Exception:
            pass

    def _poll(self):
        if not self._html_ready:
            return

        def on_launch(val):
            if not val:
                return
            try:
                spec = json.loads(val)
            except Exception:
                return
            if isinstance(spec, dict) and spec.get("concept"):
                self.launchRequested.emit(spec)

        def on_selection(val):
            if not val:
                return
            try:
                node_id = json.loads(val)
            except Exception:
                return
            if isinstance(node_id, str) and node_id:
                self.selectionRequested.emit(node_id)

        self._run_js(
            "(window.Curriculum && window.Curriculum.takeLaunch) "
            "? JSON.stringify(window.Curriculum.takeLaunch() || null) : null",
            on_launch)
        self._run_js(
            "(window.Curriculum && window.Curriculum.takeSelection) "
            "? JSON.stringify(window.Curriculum.takeSelection() || null) : null",
            on_selection)

    # -- host -> UI pushes ----------------------------------------------
    def update_explanation(self, target):
        if self._html_ready and target is not None:
            self._run_js("window.Curriculum && "
                         "window.Curriculum.updateExplanation(%s);"
                         % json.dumps(target))

    def set_sync(self, active: dict):
        if self._html_ready:
            self._run_js("window.Curriculum && window.Curriculum.setSync(%s);"
                         % json.dumps(active))

    def set_progress(self, payload: dict):
        if self._html_ready:
            self._run_js("window.Curriculum && window.Curriculum.setProgress(%s);"
                         % json.dumps(payload))

    def select_by_exercise(self, exercise_id: str):
        if self._html_ready:
            self._run_js("window.Curriculum && "
                         "window.Curriculum.selectByExerciseId(%s);"
                         % json.dumps(exercise_id))

    def select(self, node_id: str):
        if self._html_ready:
            self._run_js("window.Curriculum && window.Curriculum.select(%s);"
                         % json.dumps(node_id))


# ---------------------------------------------------------------------------
# Right panel: reused Circle (with lab launches) + cheatsheet + current mapping
# ---------------------------------------------------------------------------

class LabCircleView(CircleView):
    """The reused Circle of Fifths, with "Open ... lab" click affordances.

    Subclasses :class:`CircleView` (so the trainer's circle is untouched): it
    passes ``labLaunch: true`` in the payload -- which makes ``harmony_circle.js``
    render the extra lab buttons -- and polls ``HarmonyCircle.takeLabLaunch()`` to
    surface those as a ``labLaunchRequested`` signal.
    """

    #: Emitted with a lab "click request" dict ({labConcept, key, mode, ...}).
    labLaunchRequested = pyqtSignal(dict)

    def __init__(self, payload: dict, parent=None):
        payload = dict(payload)
        payload["labLaunch"] = True
        super().__init__(payload, parent)
        self._lab_timer = QTimer(self)
        self._lab_timer.setInterval(200)
        self._lab_timer.timeout.connect(self._poll_lab_launch)
        # Start once the page is ready (CircleView sets _html_ready in _on_loaded).
        self.web.loadFinished.connect(
            lambda ok: self._lab_timer.start() if ok else None)

    def _poll_lab_launch(self):
        if not self._html_ready:
            return

        def on_req(val):
            if not val:
                return
            try:
                req = json.loads(val)
            except Exception:
                return
            if isinstance(req, dict) and req.get("labConcept"):
                self.labLaunchRequested.emit(req)

        self._run_js(
            "(window.HarmonyCircle && window.HarmonyCircle.takeLabLaunch) "
            "? JSON.stringify(window.HarmonyCircle.takeLabLaunch() || null) : null",
            on_req)

    def set_polling(self, on: bool):
        super().set_polling(on)
        if on:
            if self._html_ready:
                self._lab_timer.start()
        else:
            self._lab_timer.stop()


class LabCheatsheetView(QWidget):
    """Static reference panel rendering the circle payload's cheatsheet."""

    def __init__(self, cheatsheet: dict, parent=None):
        super().__init__(parent)
        self._cheatsheet = cheatsheet
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.web = QWebEngineView(self)
        self.web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        layout.addWidget(self.web, 1)
        self.web.loadFinished.connect(self._on_loaded)
        self.web.load(QUrl.fromLocalFile(str(_CHEAT_HTML)))

    def _on_loaded(self, ok: bool):
        if not ok:
            return
        try:
            self.web.page().runJavaScript(
                "window.CHEATSHEET_DATA = %s; "
                "window.LabCheatsheet && window.LabCheatsheet.init(window.CHEATSHEET_DATA);"
                % json.dumps(self._cheatsheet))
        except Exception:
            pass


class LabMappingView(QWidget):
    """Live "Current Mapping" panel (updated on every sync tick)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._html_ready = False
        self._pending: Optional[dict] = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.web = QWebEngineView(self)
        self.web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        layout.addWidget(self.web, 1)
        self.web.loadFinished.connect(self._on_loaded)
        self.web.load(QUrl.fromLocalFile(str(_MAP_HTML)))

    def _on_loaded(self, ok: bool):
        if not ok:
            return
        self._html_ready = True
        if self._pending is not None:
            self.update(self._pending)

    def update(self, mapping: Optional[dict]):
        if not self._html_ready:
            self._pending = mapping
            return
        try:
            self.web.page().runJavaScript(
                "window.LabMapping && window.LabMapping.update(%s);"
                % json.dumps(mapping))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Top-level workspace window
# ---------------------------------------------------------------------------

class HarmonyLabWindow(QWidget):
    """Three-pane workspace: Lab (left) + Trainer (middle) + dashboard (right)."""

    def __init__(self, midi_service=None):
        super().__init__()
        self.setWindowTitle("Music Theory Laboratory")

        self._atlas = build_atlas()
        self._curriculum = get_curriculum()
        self._experiment = None              # the compiled LabExperiment in play
        self._cadence_node_id: Optional[str] = None
        self._current_node_id: Optional[str] = None   # the playing curriculum leaf
        self._completed_nodes: set = set()            # leaves recorded this session

        # Harmonic Scene state: the routed scene + its running occurrence position (with cross-key
        # functional-progression group switching, mirroring the standalone network window).
        self._scene_active = None
        self._scene_active_ex = None                  # the HarmonyExerciseSpec driving the scene
        self._scene_last_idx: Optional[int] = None
        self._scene_prog_groups = None                # cross-key progression group map, or None
        self._scene_shown_group = 0
        # Echo drills (ticket 07) withhold the routed scene until completion:
        # (node_id, spec) of the pending reveal, or None.
        self._echo_scene_pending = None

        # Semantic index: a trainer drill's signature -> the owning curriculum
        # leaf id, so an Atlas / Circle click filters the curriculum even though
        # those panels synthesise their own exercise ids.
        self._spec_index = self._build_spec_index()

        # Unified progress service (ticket 08): the single reader/writer over
        # BOTH persisted stores (curriculum leaves + functional journey).
        self._progress = ProgressService()   # default project-root store paths

        # The trainer is the score + MIDI host; the Lab/Atlas/Circle drive it, so
        # it needs no built-in exercise groups or its own Circle panel.
        self.trainer = HarmonyTrainerWindow(
            OrderedDict(), midi_service=midi_service, with_circle=False)

        # LEFT: the canonical curriculum tree browser.
        self.curriculum_view = CurriculumView(build_curriculum_payload())

        # RIGHT: tabbed analytical dashboard.
        circle_payload = build_circle_payload()
        self.atlas_view = AtlasView(self._atlas.to_json())
        self.circle_view = LabCircleView(circle_payload)
        self.cheatsheet_view = LabCheatsheetView(circle_payload.get("cheatsheet", {}))
        self.mapping_view = LabMappingView()
        # The curriculum-driven Harmonic Scene pane: the graph is routed + rebuilt per selected
        # exercise (setScene), not one fixed graph. Starts on the Explore key-relation scene.
        self.scene_view = HarmonicNetworkView(initial_scene=build_legacy_scene().to_dict())

        # The Home dashboard (ticket 08): streak + due-today strip + mastery
        # heatmap over the whole curriculum, refreshed with every progress push.
        self.dashboard_view = DashboardView(
            self._progress.dashboard_payload(datetime.now(timezone.utc)))

        self.right_tabs = QTabWidget()
        self.right_tabs.addTab(self.dashboard_view, "Home")
        self.right_tabs.addTab(self.atlas_view, "Atlas")
        self.right_tabs.addTab(self.scene_view, "Harmonic Scene")
        self.right_tabs.addTab(self.circle_view, "Circle of Fifths")
        self.right_tabs.addTab(self.cheatsheet_view, "Cheatsheet")
        self.right_tabs.addTab(self.mapping_view, "Current Mapping")

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.curriculum_view)
        splitter.addWidget(self.trainer)
        splitter.addWidget(self.right_tabs)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 4)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(splitter, 1)

        # Wire the launch sources into the middle trainer.
        self.curriculum_view.launchRequested.connect(self._on_curriculum_launch)
        self.curriculum_view.selectionRequested.connect(self._on_curriculum_selection)
        self.dashboard_view.launchRequested.connect(self._on_dashboard_launch)
        self.circle_view.launchRequested.connect(self._on_circle_launch)
        self.circle_view.labLaunchRequested.connect(self._on_circle_lab_launch)
        self.atlas_view.launchRequested.connect(self._on_atlas_launch)

        # Follow the trainer's current chord -> explanation + Atlas/Circle/Mapping,
        # and its play state -> progress completion.
        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(400)
        self._sync_timer.timeout.connect(self._poll_sync)
        self._sync_timer.start()

        # Push the persisted progress + auto-load the first curriculum exercise.
        QTimer.singleShot(600, self._push_progress)
        first = self._curriculum.leaves()[0]
        QTimer.singleShot(
            800, lambda: self._launch_node(first.id, first.lab_spec))

    # -- launch handlers -------------------------------------------------
    def _on_curriculum_launch(self, spec_dict: dict):
        """A curriculum exercise click -> launch its owning LabExperimentSpec."""
        echo = bool(spec_dict.get("echo"))   # the echo button (ticket 07)
        try:
            spec = LabExperimentSpec.from_dict(spec_dict)  # drops the flag
        except Exception as exc:  # malformed payload -> ignore, keep running
            print("[LAB] ignoring invalid curriculum experiment:", exc)
            return
        self._launch_node(f"ex:{spec.experiment_id}", spec, echo=echo)

    def _on_curriculum_selection(self, node_id: str):
        """A curriculum node selection -> highlight its Atlas / Circle nodes."""
        node = self._curriculum.find(node_id)
        if node is None:
            return
        active = self._active_from_atlas_nodes(node.atlas_nodes)
        if active:
            self.atlas_view.set_sync(active)
            self.curriculum_view.set_sync(active)
        target = self._circle_target_from_node(node)
        if target:
            self.circle_view.update_target(target)

    def _on_dashboard_launch(self, node_id: str):
        """A Home-dashboard click (due card / heatmap cell) -> launch that leaf."""
        node = self._curriculum.find(node_id)
        if node is None or node.kind != "exercise" or node.lab_spec is None:
            print("[LAB] dashboard node not launchable:", node_id)
            return
        self.curriculum_view.select(node.id)
        self._launch_node(node.id, node.lab_spec)

    def _on_circle_launch(self, req: dict):
        """A circle drill click -> trainer drill + select the owning curriculum leaf."""
        self.trainer.load_spec_from_circle(req)
        try:
            spec = spec_from_circle_request(req)
        except Exception:
            return
        self._select_curriculum_for_spec(spec)

    def _on_circle_lab_launch(self, req: dict):
        try:
            spec = spec_from_lab_request(req)
        except Exception as exc:
            print("[LAB] ignoring invalid circle->lab request:", exc)
            return
        self._launch_node(f"ex:{spec.experiment_id}", spec)

    def _on_atlas_launch(self, spec_dict: dict):
        """An Atlas element click -> a plain trainer drill + curriculum filter."""
        from harmony.atlas import level_for_spec
        try:
            spec = HarmonyExerciseSpec.from_dict(spec_dict)
        except Exception as exc:
            print("[LAB] ignoring invalid atlas spec:", exc)
            return
        self._experiment = None
        self._cadence_node_id = None
        self._current_node_id = None
        self.trainer.load_external_spec(spec)
        self.atlas_view.set_current_level(level_for_spec(spec))
        self._select_curriculum_for_spec(spec)

    # -- the single launch entry point (drill vs synthetic concept) ------
    def _launch_node(self, node_id: str, spec: LabExperimentSpec,
                     echo: bool = False):
        if echo:
            # Echo twins (ticket 07) are gated: native drill leaves only, and
            # only once the visual leaf is started.  The JS disables the
            # button; this enforces the same rule against stale payloads.
            record = self._progress.progress.get(node_id)
            if not is_echo_eligible(spec) or not echo_unlocked(
                    record.state if record else None):
                print("[LAB] echo drill locked (start the visual leaf first):",
                      node_id)
                return
        if spec.concept == "drill":
            self._launch_drill(node_id, spec, echo=echo)
        else:
            self._launch_experiment(node_id, spec)
        if echo:
            # No scene during the listen phase: the routed graph names the
            # very chords the learner must find by ear.  The reveal loads it
            # at completion (_record_completion).
            self._echo_scene_pending = (node_id, spec)
            self._scene_active = None
            self.scene_view.clear_scene("echo drill — listen first")
        else:
            # Route the selected exercise to its bounded harmonic scene + push it to the graph pane.
            self._echo_scene_pending = None
            self._load_scene(node_id, spec)
        # Mark the exercise as started + refresh the progress overlay.
        self._current_node_id = node_id
        self._completed_nodes.discard(node_id)
        self._progress.started(node_id, _now_iso())
        self._push_progress()

    def _launch_drill(self, node_id: str, spec: LabExperimentSpec,
                      echo: bool = False):
        """A native trainer drill (passthrough concept) -> load straight into the trainer."""
        from harmony.atlas import level_for_spec
        try:
            inner = HarmonyExerciseSpec.from_dict(spec.parameters["exercise"])
        except Exception as exc:
            print("[LAB] invalid drill exercise:", exc)
            return
        if echo:
            inner = echo_variant(inner)   # same chords, ear-first presentation
        self._experiment = None
        self._cadence_node_id = None
        self.trainer.load_external_spec(inner)
        self.atlas_view.set_current_level(level_for_spec(inner))

    def _launch_experiment(self, node_id: str, spec: LabExperimentSpec):
        """A synthetic lab concept -> compile + render through the lab pipeline."""
        try:
            experiment = compile_lab(spec)
            musicxml, payload = build_lab_exercise(experiment)
        except NotImplementedError as exc:
            print("[LAB] reserved experiment:", exc)
            return
        except Exception as exc:
            print("[LAB] failed to compile experiment:", exc)
            return
        self._experiment = experiment
        # Cadence node to co-highlight in the Atlas (best effort).
        self._cadence_node_id = None
        if spec.concept in ("cadence", "voice_leading"):
            from harmony.exercise_spec import normalise_pattern
            tokens = normalise_pattern(list(spec.parameters.get("pattern", [])))
            self._cadence_node_id = self._atlas.cadence_node_id(tokens, spec.mode)
        self.trainer.load_external_lab(musicxml, payload)

    # -- curriculum -> Harmonic Scene routing ----------------------------
    def _load_scene(self, node_id: str, spec: LabExperimentSpec):
        """Route the selected curriculum exercise to a bounded scene and push it to the pane."""
        node = self._curriculum.find(node_id)
        meta = {}
        if node is not None and getattr(node, "graph_scene_type", None):
            meta["graph_scene_type"] = node.graph_scene_type
        inner = None
        if spec.concept == "drill":
            try:
                inner = HarmonyExerciseSpec.from_dict(spec.parameters["exercise"])
            except Exception:
                inner = None
            req = GraphSceneRequest(curriculum_node_id=node_id, exercise_spec=inner,
                                    source_metadata=meta)
        else:
            req = GraphSceneRequest(curriculum_node_id=node_id, lab_spec=spec, source_metadata=meta)
        try:
            scene = build_graph_scene(req)
        except Exception as exc:  # never let scene routing disturb the trainer
            print("[LAB] scene routing failed (trainer keeps running):", exc)
            self.scene_view.clear_scene("scene routing failed")
            self._scene_active = None
            return
        self._scene_active = scene
        self._scene_active_ex = inner
        self._scene_last_idx = None
        self._scene_shown_group = 0
        self._scene_prog_groups = None
        if (scene.scene_type == "functional_progression"
                and scene.metadata.get("totalGroups", 1) > 1 and inner is not None):
            try:
                self._scene_prog_groups = progression_group_map(inner)
            except Exception:
                self._scene_prog_groups = None
        self.scene_view.set_scene(scene.to_dict())

    def _scene_group_of(self, idx: int):
        for g in (self._scene_prog_groups or []):
            if g["globalStart"] <= idx < g["globalStart"] + g["count"]:
                return g["groupIndex"]
        return None

    def _drive_scene(self, state: dict):
        """Push the trainer's running position onto the active scene (cross-key aware)."""
        if self._scene_active is None or not state:
            return
        idx = state.get("idx")
        if idx is None:
            return
        local = idx
        if self._scene_prog_groups:
            gi = self._scene_group_of(idx)
            if gi is not None:
                if gi != self._scene_shown_group and self._scene_active_ex is not None:
                    self._scene_shown_group = gi
                    self._scene_last_idx = None
                    try:
                        sc = build_functional_progression_scene(
                            self._scene_active_ex, group_index=gi)
                        self._scene_active = sc
                        self.scene_view.set_scene(sc.to_dict())
                    except Exception as exc:
                        print("[LAB] local-key scene switch failed:", exc)
                local = idx - self._scene_prog_groups[gi]["globalStart"]
        completed = bool(state.get("completed"))
        if local == self._scene_last_idx and not completed:
            return
        self._scene_last_idx = local
        # Stable per-tick payload (plan section 7.4): sceneId + occurrenceId + groupIndex, not a
        # bare index (ambiguous across scene switches / repeated occurrences).
        sc = self._scene_active
        occ = sc.occurrence_at(local) if sc is not None else None
        payload = {
            "sceneId": (sc.scene_id if sc is not None else None),
            "occurrenceId": (occ.occurrence_id if occ is not None else None),
            "sequenceIndex": local,
            "groupIndex": (self._scene_shown_group if self._scene_prog_groups else 0),
            "completed": completed,
            "correct": (True if completed else None),
        }
        self.scene_view.update_occurrence_state(payload)

    # -- semantic spec <-> curriculum-leaf index -------------------------
    @staticmethod
    def _signature(hs: HarmonyExerciseSpec):
        """A drill's identity independent of its synthesised exercise_id."""
        return (
            hs.drill, hs.mode, hs.render, hs.key or "", hs.degree or "",
            hs.quality or "", tuple(hs.pattern or ()), tuple(hs.keys or ()),
        )

    def _build_spec_index(self) -> dict:
        index: dict = {}
        for leaf in self._curriculum.leaves():
            spec = leaf.lab_spec
            if spec.concept != "drill":
                continue
            try:
                inner = HarmonyExerciseSpec.from_dict(spec.parameters["exercise"])
            except Exception:
                continue
            index.setdefault(self._signature(inner), leaf.id)
        return index

    def _select_curriculum_for_spec(self, spec: HarmonyExerciseSpec):
        node_id = self._spec_index.get(self._signature(spec))
        if node_id:
            self.curriculum_view.select(node_id)

    # -- progress --------------------------------------------------------
    def _push_progress(self):
        try:
            self.curriculum_view.set_progress(
                self._progress.payload(self._curriculum))
            self._progress.save()
            self.dashboard_view.set_payload(self._progress.dashboard_payload(
                datetime.now(timezone.utc), self._curriculum))
        except Exception as exc:
            print("[LAB] progress push failed:", exc)

    def _record_completion(self):
        node_id = self._current_node_id
        if not node_id or node_id in self._completed_nodes:
            return
        self._completed_nodes.add(node_id)
        # Finishing requires playing every chord correctly (green/red gating), so
        # a finished exercise is recorded as a full-accuracy completion.
        self._progress.record(node_id, accuracy=1.0, score=100.0,
                              timestamp=_now_iso())
        self._push_progress()
        # Echo reveal: the trainer just unveiled the notation; bring in the
        # routed scene that was withheld during the listen phase.
        if self._echo_scene_pending and self._echo_scene_pending[0] == node_id:
            pending_id, pending_spec = self._echo_scene_pending
            self._echo_scene_pending = None
            self._load_scene(pending_id, pending_spec)

    # -- Atlas / Circle highlight helpers --------------------------------
    def _active_from_atlas_nodes(self, atlas_nodes) -> dict:
        """First node id of each kind, for the Atlas highlight ``active`` dict."""
        active: dict = {}
        for nid in atlas_nodes or []:
            kind = nid.split(":", 1)[0]
            if kind in ("scale", "degree", "triad", "quality", "layer",
                        "function", "cadence") and kind not in active:
                active[kind] = nid
        return active

    def _circle_target_from_node(self, node) -> Optional[dict]:
        scale_ids = [n for n in node.atlas_nodes if n.startswith("scale:")]
        if not scale_ids:
            return None
        parts = scale_ids[0].split(":")
        if len(parts) < 3:
            return None
        _, key, mode = parts[0], parts[1], parts[2]
        word = "major" if mode == "major" else "minor"
        target = {"key": f"{key} {word}", "mode": mode}
        degs = [n for n in node.atlas_nodes if n.startswith("degree:")]
        if degs:
            d = degs[0].split(":")
            if len(d) >= 3:
                target["roman"] = d[2]
        return target

    # -- live sync -------------------------------------------------------
    def _poll_sync(self):
        def on_target(target):
            if not target:
                return
            # Left: live "Now playing" guide.
            self.curriculum_view.update_explanation(target)

            # Atlas highlight (+ cadence node when applicable).
            active = self._atlas.sync(target).get("active", {})
            if target.get("concept") == "melody":
                # A monophonic motive implies no triad/degree — keep only the
                # scale chip (its first degree must not surface as a tonic triad).
                active = {"scale": active.get("scale")}
            elif self._cadence_node_id:
                active = dict(active)
                active["cadence"] = self._cadence_node_id
            active = {k: v for k, v in active.items() if v}
            self.atlas_view.set_sync(active)
            self.curriculum_view.set_sync(active)

            # Circle highlight.
            self.circle_view.update_target(target)

            # Current Mapping panel.
            self.mapping_view.update(self._mapping_for(target))

        def on_state(state):
            if not state:
                return
            if state.get("finished"):
                self._record_completion()
            self._drive_scene(state)          # push the running position onto the Harmonic Scene

        try:
            self.trainer.query_current_target(on_target)
            self.trainer.query_trainer_state(on_state)
        except Exception:
            pass

    def _mapping_for(self, target: dict) -> dict:
        """The Current-Mapping payload for the live target (lab-derived if possible)."""
        idx = target.get("absMeasure")
        if (self._experiment is not None and isinstance(idx, int)
                and 0 <= idx < len(self._experiment.measures)):
            return get_measure_explanation(
                self._experiment.measures[idx], atlas=self._atlas,
                experiment_title=self._experiment.title)
        # Fallback: derive from the target dict (e.g. a raw Atlas/Circle drill).
        mapping = mapping_from_target(target, atlas=self._atlas)
        if not mapping["atlasNodeIds"]:
            active = self._atlas.sync(target).get("active", {})
            ids = {k: active.get(k) for k in ("scale", "degree", "triad")}
            ids = {k: v for k, v in ids.items() if v}
            mapping["atlasNodeIds"] = ids
            if ids:
                mapping["atlasEdges"] = self._atlas.edges_for(list(ids.values()))
        return mapping


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
    win.resize(1700, 900)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
