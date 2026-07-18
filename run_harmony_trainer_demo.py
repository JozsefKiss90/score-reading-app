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

By default it loads the comprehensive set (``default_exercise_groups``):
every major and natural-minor key as full-key block and arpeggio drills, each
scale degree across all 12 keys (block + arpeggio), quality-recognition drills
(major / minor / diminished), and function drills (I–IV–V–I, ii–V–I, vi–ii–V–I,
i–iv–v–i, i–VI–VII–i).  A "Group" filter narrows the exercise list to one of:
Major full-key, Minor full-key, Degree transposition, Quality recognition,
Function, or Arpeggio drills.  Pass a spec JSON file to load a custom set
instead.
"""

from __future__ import annotations

import json
import sys
import tempfile
from collections import OrderedDict
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt, QCoreApplication, QTimer, QUrl, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox,
    QLabel, QSplitter, QCheckBox, QSpinBox,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

from harmony.exercise_spec import (
    HarmonyExerciseSpec, compile_exercise, default_exercise_groups, load_specs,
)
from harmony.musicxml_builder import build_exercise
from harmony.circle_payload import build_circle_payload, spec_from_circle_request
from audio.target_playback import TargetTransport, PLAYING, MIN_BPM, MAX_BPM

#: Pseudo-group shown first in the filter: every exercise, in group order.
ALL_GROUPS = "All groups"

#: Group used by the Interactive Harmony Atlas to inject a clicked exercise.
ATLAS_GROUP = "From Atlas"


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
_CIRCLE_HTML_PATH = Path(__file__).resolve().parent / "beat_selector" / "harmony_circle.html"


class CircleView(QWidget):
    """Interactive Circle of Fifths panel (web UI) for the trainer window.

    A self-contained QWebEngineView that loads ``harmony_circle.html``, injects
    the circle payload, polls for click->exercise requests, and pushes the live
    target chord for synchronised highlighting. Mirrors the app's existing
    runJavaScript + polling bridge (no QWebChannel).
    """

    #: Emitted with a circle "click request" dict when a launch shortcut is used.
    launchRequested = pyqtSignal(dict)

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
        self.web.load(QUrl.fromLocalFile(str(_CIRCLE_HTML_PATH)))

        self._launch_timer = QTimer(self)
        self._launch_timer.setInterval(200)
        self._launch_timer.timeout.connect(self._poll_launch)

    def _on_loaded(self, ok: bool):
        if not ok:
            return
        self._run_js(
            "window.CIRCLE_DATA = %s; "
            "window.HarmonyCircle && window.HarmonyCircle.init(window.CIRCLE_DATA);"
            % json.dumps(self._payload))
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
            if isinstance(spec, dict) and spec.get("drill"):
                self.launchRequested.emit(spec)

        self._run_js(
            "(window.HarmonyCircle && window.HarmonyCircle.takeLaunch) "
            "? JSON.stringify(window.HarmonyCircle.takeLaunch() || null) : null",
            on_spec)

    def update_target(self, target: Optional[dict]):
        if self._html_ready and target is not None:
            self._run_js("window.HarmonyCircle && "
                         "window.HarmonyCircle.updateFromTrainerState(%s);"
                         % json.dumps(target))

    def set_polling(self, on: bool):
        """Pause/resume the click poll (no point polling a hidden panel)."""
        if on:
            if self._html_ready:
                self._launch_timer.start()
        else:
            self._launch_timer.stop()


class HarmonyTrainerWindow(QWidget):
    def __init__(self, groups: "OrderedDict[str, List[HarmonyExerciseSpec]]",
                 midi_service=None, with_circle: bool = True):
        super().__init__()
        self._with_circle = with_circle
        self.circle_view: Optional[CircleView] = None
        self._groups = groups
        # "All groups" first, then each named group, in insertion order.
        self._all_specs: List[HarmonyExerciseSpec] = []
        for specs in groups.values():
            self._all_specs.extend(specs)
        self._group_names = [ALL_GROUPS] + list(groups.keys())

        self._specs: List[HarmonyExerciseSpec] = self._all_specs  # current filter
        self._midi_service = midi_service
        self._current_idx = 0
        self._score_widget: Optional[ScoreViewBeats] = None
        self._tmp_paths: List[Path] = []
        self._trainer_js = _TRAINER_JS_PATH.read_text(encoding="utf-8")

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)

        top = QHBoxLayout()
        top.addWidget(QLabel("Group:"))
        self.cmbGroup = QComboBox()
        for name in self._group_names:
            count = (len(self._all_specs) if name == ALL_GROUPS
                     else len(groups[name]))
            self.cmbGroup.addItem(f"{name} ({count})")
        self.cmbGroup.currentIndexChanged.connect(self._on_group_changed)
        top.addWidget(self.cmbGroup, 1)

        top.addWidget(QLabel("Exercise:"))
        self.cmb = QComboBox()
        self.cmb.currentIndexChanged.connect(self.load_index)
        top.addWidget(self.cmb, 2)

        self.btnPrev = QPushButton("◀ Prev")
        self.btnPrev.clicked.connect(lambda: self.load_index(self._current_idx - 1))
        top.addWidget(self.btnPrev)

        self.btnNext = QPushButton("Next ▶")
        self.btnNext.clicked.connect(lambda: self.load_index(self._current_idx + 1))
        top.addWidget(self.btnNext)

        # Transport (ticket 05 / plan U1): sound the target progression
        # through the score widget's synth.  Living in this window's top bar
        # makes it available in every launcher that hosts the trainer.
        self.transport = TargetTransport(self)
        self.transport.stateChanged.connect(self._on_transport_state)

        self.btnPlay = QPushButton("▶ Play")
        self.btnPlay.setToolTip("Play the target chords (hear the answer)")
        self.btnPlay.clicked.connect(self.transport.toggle)
        top.addWidget(self.btnPlay)

        self.btnStopPlay = QPushButton("⏹")
        self.btnStopPlay.setToolTip("Stop playback and rewind")
        self.btnStopPlay.clicked.connect(self.transport.stop)
        top.addWidget(self.btnStopPlay)

        self.chkLoop = QCheckBox("Loop")
        self.chkLoop.toggled.connect(self.transport.set_loop)
        top.addWidget(self.chkLoop)

        self.spinTempo = QSpinBox()
        self.spinTempo.setRange(MIN_BPM, MAX_BPM)
        self.spinTempo.setValue(self.transport.bpm)
        self.spinTempo.setSuffix(" bpm")
        self.spinTempo.setToolTip("Playback tempo")
        self.spinTempo.valueChanged.connect(self.transport.set_bpm)
        top.addWidget(self.spinTempo)

        # Score host (left) + optional Circle-of-Fifths panel (right).
        self._score_host = QWidget()
        self._score_container = QVBoxLayout(self._score_host)
        self._score_container.setContentsMargins(0, 0, 0, 0)

        if with_circle:
            self.btnCircle = QPushButton("Circle")
            self.btnCircle.setCheckable(True)
            self.btnCircle.setChecked(True)
            self.btnCircle.toggled.connect(self._toggle_circle)
            top.addWidget(self.btnCircle)

            self.circle_view = CircleView(build_circle_payload())
            self.circle_view.launchRequested.connect(self.load_spec_from_circle)

            root.addLayout(top)
            splitter = QSplitter(Qt.Orientation.Horizontal)
            splitter.addWidget(self._score_host)
            splitter.addWidget(self.circle_view)
            splitter.setStretchFactor(0, 3)
            splitter.setStretchFactor(1, 2)
            root.addWidget(splitter, 1)

            # Keep the circle synced to the live target chord.
            self._circle_sync = QTimer(self)
            self._circle_sync.setInterval(400)
            self._circle_sync.timeout.connect(self._sync_circle)
            self._circle_sync.start()
        else:
            root.addLayout(top)
            root.addWidget(self._score_host, 1)

        self._populate_exercises(self._all_specs)  # initial: All groups

    # ------------------------------------------------------------------
    # Target playback transport
    # ------------------------------------------------------------------
    def _on_transport_state(self, state: str):
        self.btnPlay.setText("⏸ Pause" if state == PLAYING else "▶ Play")

    # ------------------------------------------------------------------
    # Circle-of-Fifths panel integration
    # ------------------------------------------------------------------
    def _toggle_circle(self, checked: bool):
        if self.circle_view is None:
            return
        self.circle_view.setVisible(checked)
        # Stop polling/sync while hidden; resume when shown (no wasted cycles).
        self.circle_view.set_polling(checked)
        if hasattr(self, "_circle_sync"):
            self._circle_sync.start() if checked else self._circle_sync.stop()

    def load_spec_from_circle(self, req: dict):
        """Bridge: turn a circle click request into a validated spec and load it.

        The circle never builds MusicXML; it sends a spec-like request which is
        converted through :func:`harmony.circle_payload.spec_from_circle_request`
        (validated) and loaded via the normal trainer flow. Invalid requests are
        logged and ignored rather than crashing the trainer.
        """
        try:
            spec = spec_from_circle_request(req)
        except Exception as exc:
            print("[CIRCLE] ignoring invalid request:", exc)
            return
        self.load_external_spec(spec)

    def _sync_circle(self):
        if self.circle_view is None or not self.circle_view.isVisible():
            return

        def on_target(target):
            if target is not None:
                self.circle_view.update_target(target)

        try:
            self.query_current_target(on_target)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _on_group_changed(self, gidx: int):
        name = self._group_names[gidx] if 0 <= gidx < len(self._group_names) else ALL_GROUPS
        specs = self._all_specs if name == ALL_GROUPS else self._groups.get(name, [])
        self._populate_exercises(specs)

    def _populate_exercises(self, specs: List[HarmonyExerciseSpec]):
        """Repopulate the exercise combo for the selected group and load its first."""
        self._specs = list(specs)
        self.cmb.blockSignals(True)
        self.cmb.clear()
        for s in self._specs:
            self.cmb.addItem(s.title)
        self.cmb.blockSignals(False)
        if self._specs:
            self.load_index(0)

    # ------------------------------------------------------------------
    # External control (used by the Interactive Harmony Atlas launcher)
    # ------------------------------------------------------------------
    def load_external_spec(self, spec: HarmonyExerciseSpec):
        """Load a single spec supplied from outside (e.g. an Atlas node click).

        The spec is placed in the ``From Atlas`` group (which the combined
        launcher includes) and shown immediately. No-op-safe if that group is
        not present.
        """
        self._groups[ATLAS_GROUP] = [spec]
        self._all_specs = [s for specs in self._groups.values() for s in specs]
        if ATLAS_GROUP in self._group_names:
            gi = self._group_names.index(ATLAS_GROUP)
            self.cmbGroup.blockSignals(True)
            self.cmbGroup.setCurrentIndex(gi)
            self.cmbGroup.blockSignals(False)
        self._populate_exercises([spec])

    def query_current_target(self, callback):
        """Async: invoke ``callback(target_dict | None)`` with the current chord.

        Reads ``window.HarmonyTrainer.currentTarget()`` from the injected
        controller so the Atlas can highlight the live playback position.
        """
        w = self._score_widget
        if w is None or not getattr(w, "_html_ready", False):
            callback(None)
            return
        js = ("(window.HarmonyTrainer && window.HarmonyTrainer.currentTarget) "
              "? JSON.stringify(window.HarmonyTrainer.currentTarget()) : null")

        def on_result(val):
            if not val:
                callback(None)
                return
            try:
                callback(json.loads(val))
            except Exception:
                callback(None)

        try:
            w.web.page().runJavaScript(js, on_result)
        except Exception:
            callback(None)

    def query_trainer_state(self, callback):
        """Async: invoke ``callback(state_dict | None)`` with the play state.

        Reads ``window.HarmonyTrainer.state()`` -> ``{idx, completed, finished,
        total, ...}`` so a host can detect when an exercise has been fully played
        (``finished``).  Read-only sibling of :meth:`query_current_target`; the
        trainer itself is unchanged.
        """
        w = self._score_widget
        if w is None or not getattr(w, "_html_ready", False):
            callback(None)
            return
        js = ("(window.HarmonyTrainer && window.HarmonyTrainer.state) "
              "? JSON.stringify(window.HarmonyTrainer.state()) : null")

        def on_result(val):
            if not val:
                callback(None)
                return
            try:
                callback(json.loads(val))
            except Exception:
                callback(None)

        try:
            w.web.page().runJavaScript(js, on_result)
        except Exception:
            callback(None)

    def seek_to_index(self, index: int):
        """Seek the RUNNING drill to chord occurrence ``index`` (not a different exercise).

        Drives the injected controller's ``window.HarmonyTrainer.goTo(i)`` (which clamps, resets
        the per-chord satisfied/completed state, re-highlights and emits ``targetchange``). This
        is the in-drill seek the Harmonic Network graph/timeline click uses; distinct from
        :meth:`load_index`, which switches between exercises.
        """
        w = self._score_widget
        if w is None or not getattr(w, "_html_ready", False):
            return
        js = ("window.HarmonyTrainer && window.HarmonyTrainer.goTo "
              "&& window.HarmonyTrainer.goTo(%d);" % int(index))
        try:
            w.web.page().runJavaScript(js)
        except Exception:
            pass

    def current_spec(self) -> "Optional[HarmonyExerciseSpec]":
        """The active :class:`HarmonyExerciseSpec` (the exercise combo's selection), or ``None``.

        Additive, read-only. Lets a host (e.g. the Harmonic Network scene launcher) detect when
        the user switches drills so it can re-route the graph scene per exercise. The trainer
        itself is unchanged."""
        try:
            i = self.cmb.currentIndex()
            if 0 <= i < len(self._specs):
                return self._specs[i]
        except Exception:
            pass
        return None

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

    def _write_temp(self, musicxml: str) -> Path:
        # Only one score is shown at a time; drop the previous temp file.
        self._cleanup_temp()
        tmp = tempfile.NamedTemporaryFile(
            prefix="harmony_", suffix=".xml", delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()
        tmp_path.write_text(musicxml, encoding="utf-8")
        self._tmp_paths.append(tmp_path)
        return tmp_path

    def _make_temp_score(self, spec: HarmonyExerciseSpec) -> Tuple[Path, dict]:
        compiled = compile_exercise(spec)
        musicxml, payload = build_exercise(compiled)
        return self._write_temp(musicxml), payload

    def _show_score(self, mxl_path: Path, payload: dict, title: str) -> None:
        """Mount a ScoreViewBeats for ``mxl_path`` and (re)inject the controller.

        Shared by the normal exercise path (:meth:`load_index`) and the prebuilt
        path (:meth:`load_external_lab`).
        """
        self.setWindowTitle(title)
        self.transport.stop()   # silence the old exercise before the swap
        self._remove_current_score()
        self._score_widget = ScoreViewBeats(
            str(mxl_path), midi_service=self._midi_service)
        self._score_container.addWidget(self._score_widget, 1)
        # The trainer owns MIDI-highlight state and uses single-page scores, so
        # hide the viewer's beat-selector toggle and page-nav buttons.
        for attr in ("btnBeats", "btnPrev", "btnNext"):
            btn = getattr(self._score_widget, attr, None)
            if btn is not None:
                btn.hide()
        self._ensure_trainer(self._score_widget, payload)
        self.transport.attach(self._score_widget, payload)

    def load_external_lab(self, musicxml: str, payload: dict) -> None:
        """Load a *prebuilt* ``(musicxml, payload)`` pair (Music Theory Lab).

        Unlike :meth:`load_external_spec` (which compiles a
        ``HarmonyExerciseSpec``), the lab renders MusicXML the trainer's own
        builder cannot produce -- a changing bass (inversions), four SATB voices,
        a melodic motive, two implied-harmony voices -- so it injects the
        prebuilt document directly.  The unchanged ``harmony_trainer.js``
        controller then drives MIDI green/red validation from ``payload`` exactly
        as for any exercise (its targets carry the same ``TARGET_CHORDS`` shape).
        """
        title = payload.get("title", "Lab experiment")
        mxl_path = self._write_temp(musicxml)
        self._show_score(mxl_path, payload, f"Music Theory Lab — {title}")

    def closeEvent(self, event):
        self.transport.stop()
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

        mxl_path, payload = self._make_temp_score(spec)
        self._show_score(mxl_path, payload, f"Harmony Trainer — {spec.title}")

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


def _load_groups(argv: List[str]) -> "OrderedDict[str, List[HarmonyExerciseSpec]]":
    """Comprehensive grouped set by default; a JSON file arg loads one flat group."""
    if len(argv) > 1 and argv[1] and Path(argv[1]).exists():
        return OrderedDict([(Path(argv[1]).name, load_specs(argv[1]))])
    return default_exercise_groups()


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    app = QApplication(argv)

    groups = _load_groups(argv)

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

    win = HarmonyTrainerWindow(groups, midi_service=midi_service)
    win.resize(1100, 800)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
