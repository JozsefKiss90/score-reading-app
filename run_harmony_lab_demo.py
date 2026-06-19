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

from harmony.atlas import build_atlas
from harmony.circle_payload import build_circle_payload
from harmony.lab_spec import LabExperimentSpec, spec_from_lab_request
from harmony.lab import compile_lab, lab_demo_specs
from harmony.lab_musicxml import build_lab_exercise
from harmony.lab_explanations import (
    get_concept_explanation, get_experiment_explanation, get_measure_explanation,
    mapping_from_target,
)
from run_harmony_trainer_demo import HarmonyTrainerWindow, MidiService, CircleView
from run_harmony_atlas_demo import AtlasView

_BEAT = Path(__file__).resolve().parent / "beat_selector"
_LAB_HTML = _BEAT / "harmony_lab.html"
_CHEAT_HTML = _BEAT / "lab_cheatsheet.html"
_MAP_HTML = _BEAT / "lab_mapping.html"

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
        self._experiment = None              # the compiled LabExperiment in play
        self._cadence_node_id: Optional[str] = None

        # The trainer is the score + MIDI host; the Lab/Atlas/Circle drive it, so
        # it needs no built-in exercise groups or its own Circle panel.
        self.trainer = HarmonyTrainerWindow(
            OrderedDict(), midi_service=midi_service, with_circle=False)

        # LEFT: lab concept/theory/example UI.
        self.lab_view = LabView(build_lab_catalog())

        # RIGHT: tabbed analytical dashboard.
        circle_payload = build_circle_payload()
        self.atlas_view = AtlasView(self._atlas.to_json())
        self.circle_view = LabCircleView(circle_payload)
        self.cheatsheet_view = LabCheatsheetView(circle_payload.get("cheatsheet", {}))
        self.mapping_view = LabMappingView()

        self.right_tabs = QTabWidget()
        self.right_tabs.addTab(self.atlas_view, "Atlas")
        self.right_tabs.addTab(self.circle_view, "Circle of Fifths")
        self.right_tabs.addTab(self.cheatsheet_view, "Cheatsheet")
        self.right_tabs.addTab(self.mapping_view, "Current Mapping")

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.lab_view)
        splitter.addWidget(self.trainer)
        splitter.addWidget(self.right_tabs)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 4)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(splitter, 1)

        # Wire the three launch sources into the middle trainer.
        self.lab_view.launchRequested.connect(self._on_lab_launch)
        self.circle_view.launchRequested.connect(self.trainer.load_spec_from_circle)
        self.circle_view.labLaunchRequested.connect(self._on_circle_lab_launch)
        self.atlas_view.launchRequested.connect(self._on_atlas_launch)

        # Follow the trainer's current chord -> explanation + Atlas/Circle/Mapping.
        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(400)
        self._sync_timer.timeout.connect(self._poll_sync)
        self._sync_timer.start()

        # Auto-load the first experiment so the workspace is not blank.
        self._demo_specs = {s.experiment_id: s for s in lab_demo_specs()}
        first = lab_demo_specs()[0]
        QTimer.singleShot(700, lambda: self._launch_spec(first))

    # -- launch handlers -------------------------------------------------
    def _on_lab_launch(self, spec_dict: dict):
        try:
            spec = LabExperimentSpec.from_dict(spec_dict)
        except Exception as exc:  # malformed payload -> ignore, keep running
            print("[LAB] ignoring invalid experiment:", exc)
            return
        self._launch_spec(spec)

    def _on_circle_lab_launch(self, req: dict):
        try:
            spec = spec_from_lab_request(req)
        except Exception as exc:
            print("[LAB] ignoring invalid circle->lab request:", exc)
            return
        self._launch_spec(spec)

    def _on_atlas_launch(self, spec_dict: dict):
        """An Atlas element click -> a plain trainer drill (no lab experiment)."""
        from harmony.exercise_spec import HarmonyExerciseSpec
        from harmony.atlas import level_for_spec
        try:
            spec = HarmonyExerciseSpec.from_dict(spec_dict)
        except Exception as exc:
            print("[LAB] ignoring invalid atlas spec:", exc)
            return
        self._experiment = None
        self._cadence_node_id = None
        self.trainer.load_external_spec(spec)
        self.atlas_view.set_current_level(level_for_spec(spec))

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
        self._experiment = experiment
        # Cadence node to co-highlight in the Atlas (best effort).
        self._cadence_node_id = None
        if spec.concept in ("cadence", "voice_leading"):
            from harmony.exercise_spec import normalise_pattern
            tokens = normalise_pattern(list(spec.parameters.get("pattern", [])))
            self._cadence_node_id = self._atlas.cadence_node_id(tokens, spec.mode)
        self.trainer.load_external_lab(musicxml, payload)
        try:
            self.lab_view.set_experiment_explanation(
                get_experiment_explanation(spec, experiment))
        except Exception as exc:
            print("[LAB] explanation failed:", exc)

    # -- live sync -------------------------------------------------------
    def _poll_sync(self):
        def on_target(target):
            if not target:
                return
            # Left: live "Now playing" guide.
            self.lab_view.update_explanation(target)

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
            self.lab_view.set_sync(active)

            # Circle highlight.
            self.circle_view.update_target(target)

            # Current Mapping panel.
            self.mapping_view.update(self._mapping_for(target))

        try:
            self.trainer.query_current_target(on_target)
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
