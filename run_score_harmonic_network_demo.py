"""Score Soul Graph / Live Harmonic Network Analysis -- BWV 846 pilot launcher.

Renders ONE real score (BWV 846, Bach's C-major Prelude) and walks it measure by
measure.  On every measure change the launcher:

  * moves the score playback cursor (centre, the real Verovio render);
  * highlights the matching Harmonic Network nodes/edges (right-top);
  * highlights the matching Atlas scale/degree/triad/function nodes (right-bottom);
  * updates the trainer-style chord card + the score "mandala" (left).

Layout (3 columns, ``QSplitter``):
  LEFT   -- ScoreSoulView (form sections / measures / cadences / chord card /
            radial harmonic mandala = the score-specific graph)
  CENTRE -- ScoreViewBeats (the real score) + a Prev / Next / Play transport
  RIGHT  -- HarmonicNetworkView over AtlasView

It REUSES the existing view widgets (HarmonicNetworkView, AtlasView,
ScoreViewBeats) and the established ``runJavaScript`` + poll bridge; no rendering
logic is duplicated.  The data layer (analysis + score graph) is pure and is
exposed via :func:`build_demo_payloads` so it can be smoke-tested headless.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from harmony.score_analysis import ScoreAnalysisResult, atlas_sync_target
from harmony.score_graph import build_score_graph
from harmony.score_import import (
    load_bwv846_analysis,
    load_analysis_from_sidecar,
    score_file_path,
    ensure_local_bwv846,
)

_HTML = Path(__file__).resolve().parent / "beat_selector" / "score_soul.html"
_DEFAULT_SCORE_ID = "bwv846_prelude_c_major"


# ---------------------------------------------------------------------------
# Pure data layer (no Qt -- importable + testable headless)
# ---------------------------------------------------------------------------

def build_analysis(score_id: str = _DEFAULT_SCORE_ID) -> ScoreAnalysisResult:
    """Curated analysis for ``score_id`` (BWV 846 uses the bundled score)."""
    if score_id == _DEFAULT_SCORE_ID:
        return load_bwv846_analysis()
    return load_analysis_from_sidecar(score_id)


def build_demo_payloads(score_id: str = _DEFAULT_SCORE_ID) -> Dict:
    """Everything the UI needs, as plain JSON-serialisable dicts.

    Returns ``{analysis, graph, network, atlas, scoreFile}`` -- no Qt involved.
    """
    from harmony.harmonic_network import build_network
    from harmony.network_template import get_template
    from harmony.atlas import build_atlas

    result = build_analysis(score_id)
    graph = build_score_graph(result)
    network = build_network(
        get_template("dominant_diminished_relative_network_v1")).to_payload()
    atlas = build_atlas().to_json()
    score_file = score_file_path(score_id)
    return {
        "analysis": result.to_dict(),
        "graph": graph.to_payload(),
        "network": network,
        "atlas": atlas,
        "scoreFile": str(score_file) if score_file else None,
        "result": result,            # the live object (for the host)
        "graphObj": graph,
    }


# ---------------------------------------------------------------------------
# Qt UI
# ---------------------------------------------------------------------------

def _build_qt():  # imported lazily so the module is importable without a display
    from PyQt6.QtCore import Qt, QCoreApplication, QTimer, QUrl, pyqtSignal
    from PyQt6.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSplitter,
        QPushButton,
    )
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    from run_harmonic_network_demo import HarmonicNetworkView
    from run_harmony_atlas_demo import AtlasView
    from beat_selector.view import ScoreViewBeats
    from harmony.atlas import build_atlas

    try:
        from run_harmony_trainer_demo import MidiService
    except Exception:  # pragma: no cover
        MidiService = None

    # ---- LEFT: the Score Soul navigator + mandala -----------------------
    class ScoreSoulView(QWidget):
        measureSelected = pyqtSignal(int)

        def __init__(self, payload: dict, parent=None):
            super().__init__(parent)
            self._payload = payload
            self._ready = False

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            top = QHBoxLayout()
            top.setContentsMargins(6, 6, 6, 6)
            top.addWidget(QLabel("Score Soul Graph"))
            top.addStretch(1)
            layout.addLayout(top)

            self.web = QWebEngineView(self)
            self.web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            layout.addWidget(self.web, 1)
            self.web.loadFinished.connect(self._on_loaded)
            self.web.load(QUrl.fromLocalFile(str(_HTML)))

            self._poll = QTimer(self)
            self._poll.setInterval(200)
            self._poll.timeout.connect(self._poll_selection)

        def _run_js(self, code, cb=None):
            try:
                if cb is None:
                    self.web.page().runJavaScript(code)
                else:
                    self.web.page().runJavaScript(code, cb)
            except Exception:
                pass

        def _on_loaded(self, ok: bool):
            if not ok:
                return
            data_js = json.dumps(self._payload)
            self._run_js(
                "window.SCORE_SOUL_DATA = %s; "
                "window.ScoreSoul && window.ScoreSoul.init(window.SCORE_SOUL_DATA);"
                % data_js)
            self._ready = True
            self._poll.start()

        def _poll_selection(self):
            if not self._ready:
                return

            def on_sel(val):
                if not val:
                    return
                try:
                    sel = json.loads(val)
                except Exception:
                    return
                if isinstance(sel, dict) and "measure" in sel:
                    self.measureSelected.emit(int(sel["measure"]))

            self._run_js(
                "(window.ScoreSoul && window.ScoreSoul.takeSelection) "
                "? JSON.stringify(window.ScoreSoul.takeSelection() || null) : null",
                on_sel)

        def set_current_measure(self, measure: int):
            if self._ready:
                self._run_js(
                    "window.ScoreSoul && window.ScoreSoul.setCurrentMeasure(%d);"
                    % int(measure))

    # ---- CENTRE: real score + transport --------------------------------
    class ScoreCenterWidget(QWidget):
        prevRequested = pyqtSignal()
        nextRequested = pyqtSignal()
        playToggled = pyqtSignal(bool)

        def __init__(self, mxl_path: str, midi_service=None, parent=None):
            super().__init__(parent)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)

            bar = QHBoxLayout()
            bar.setContentsMargins(6, 6, 6, 2)
            self.btnPrev = QPushButton("◀ Prev measure")
            self.btnNext = QPushButton("Next measure ▶")
            self.btnPlay = QPushButton("⏵ Play")
            self.btnPlay.setCheckable(True)
            self.lbl = QLabel("m1")
            self.lbl.setMinimumWidth(120)
            bar.addWidget(self.btnPrev)
            bar.addWidget(self.btnNext)
            bar.addWidget(self.btnPlay)
            bar.addStretch(1)
            bar.addWidget(self.lbl)
            layout.addLayout(bar)

            self.score = None
            self._by_number = {}
            if mxl_path:
                self.score = ScoreViewBeats(mxl_path, midi_service=midi_service)
                layout.addWidget(self.score, 1)
                for m in getattr(self.score, "measures", []) or []:
                    self._by_number[int(m.number)] = m
            else:
                # No score file for this piece (e.g. BWV 999 is not bundled).
                # NEVER render a different piece here -- show a placeholder so
                # the centre pane stays honest about "one real score at a time".
                ph = QLabel(
                    "Score file pending.\n\nDrop a MusicXML / MXL into "
                    "data/scores/ to enable live rendering.\nThe analysis "
                    "(left) and the Atlas / Network mapping (right) still work.")
                ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
                ph.setWordWrap(True)
                layout.addWidget(ph, 1)
                for b in (self.btnPrev, self.btnNext, self.btnPlay):
                    b.setEnabled(False)

            self.btnPrev.clicked.connect(lambda: self.prevRequested.emit())
            self.btnNext.clicked.connect(lambda: self.nextRequested.emit())
            self.btnPlay.toggled.connect(lambda on: self.playToggled.emit(on))

        def go_to_measure(self, measure: int):
            self.lbl.setText("m%d" % measure)
            if self.score is None:
                return  # no-op: do not map this piece's measures onto another
            m = self._by_number.get(int(measure))
            if m is None:
                return
            try:
                self.score.set_music_time(float(m.start_sec))
            except Exception:
                pass

    # ---- the window ----------------------------------------------------
    class ScoreSoulWindow(QWidget):
        def __init__(self, score_id: str = _DEFAULT_SCORE_ID, midi_service=None,
                     parent=None):
            super().__init__(parent)
            self.setWindowTitle("Score Soul Graph -- Live Harmonic Network Analysis")

            payloads = build_demo_payloads(score_id)
            self._result = payloads["result"]
            self._atlas = build_atlas()
            self._measures = sorted(s.measure for s in self._result.slices)
            self._current = self._measures[0] if self._measures else 1

            soul_payload = {"analysis": payloads["analysis"],
                            "graph": payloads["graph"]}
            self.soul = ScoreSoulView(soul_payload)

            mxl = payloads["scoreFile"]
            if not mxl and score_id == _DEFAULT_SCORE_ID:
                mxl = str(ensure_local_bwv846() or "")
            self.center = ScoreCenterWidget(mxl or None, midi_service=midi_service)

            self.net = HarmonicNetworkView(payloads["network"])
            self.atlas_view = AtlasView(payloads["atlas"])

            right = QSplitter(Qt.Orientation.Vertical)
            right.addWidget(self.net)
            right.addWidget(self.atlas_view)
            right.setStretchFactor(0, 3)
            right.setStretchFactor(1, 2)

            split = QSplitter(Qt.Orientation.Horizontal)
            split.addWidget(self.soul)
            split.addWidget(self.center)
            split.addWidget(right)
            split.setStretchFactor(0, 2)
            split.setStretchFactor(1, 3)
            split.setStretchFactor(2, 3)

            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.addWidget(split, 1)

            # wiring
            self.soul.measureSelected.connect(self.set_measure)
            self.center.prevRequested.connect(self._prev)
            self.center.nextRequested.connect(self._next)
            self.center.playToggled.connect(self._toggle_play)
            self.net.launchRequested.connect(self._on_launch_ignored)
            self.atlas_view.launchRequested.connect(self._on_launch_ignored)

            self._play_timer = QTimer(self)
            self._play_timer.setInterval(1100)
            self._play_timer.timeout.connect(self._advance_play)

            # set the opening measure once the views are up
            QTimer.singleShot(900, lambda: self.set_measure(self._current))

        # -- the one sync entry point ------------------------------------
        def set_measure(self, measure: int):
            measure = int(measure)
            self._current = measure
            self.center.go_to_measure(measure)
            self.soul.set_current_measure(measure)
            sl = self._result.slice_for_measure(measure)
            if sl is None:
                return
            try:
                self.net.highlight_from_trainer(sl.network_target())
            except Exception:
                pass
            try:
                active = self._atlas.sync(atlas_sync_target(sl)).get("active", {})
                self.atlas_view.set_sync({k: v for k, v in active.items() if v})
            except Exception:
                pass

        def _step(self, delta: int):
            if not self._measures:
                return
            cur = self._current
            ms = self._measures
            try:
                i = ms.index(cur)
            except ValueError:
                i = 0
            i = max(0, min(len(ms) - 1, i + delta))
            self.set_measure(ms[i])

        def _prev(self):
            self._step(-1)

        def _next(self):
            self._step(1)

        def _toggle_play(self, on: bool):
            if on:
                self._play_timer.start()
            else:
                self._play_timer.stop()

        def _advance_play(self):
            if self._measures and self._current >= self._measures[-1]:
                self._play_timer.stop()
                self.center.btnPlay.setChecked(False)
                return
            self._step(1)

        def _on_launch_ignored(self, spec_dict: dict):
            drill = (spec_dict or {}).get("drill")
            print("[SCORE] launch ignored (no trainer in the score demo):", drill)

    return (QApplication, QCoreApplication, Qt, QTimer, ScoreSoulWindow,
            MidiService)


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    (QApplication, QCoreApplication, Qt, QTimer, ScoreSoulWindow,
     MidiService) = _build_qt()

    QCoreApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    app = QApplication(argv)

    midi_service = None
    if MidiService is not None:
        try:
            midi_service = MidiService()
        except Exception as exc:
            print("[SCORE] MidiService init failed:", exc)
            midi_service = None

    score_id = _DEFAULT_SCORE_ID
    for a in argv[1:]:
        if a and not a.startswith("-"):
            score_id = a

    ensure_local_bwv846()
    win = ScoreSoulWindow(score_id=score_id, midi_service=midi_service)
    win.resize(1820, 960)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
