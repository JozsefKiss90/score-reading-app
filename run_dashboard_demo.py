"""Home dashboard -- standalone launcher (ticket 08, U3).

Run::

    .venv/Scripts/python.exe run_dashboard_demo.py

The platform's landing surface: one window rendering
``beat_selector/dashboard.html`` from a single
:class:`harmony.progress_service.ProgressService` payload --

  * the practice streak + overall completion,
  * the SM-2-lite "due today" review strip,
  * the functional-journey summary,
  * the full-curriculum mastery heatmap (one cell per exercise leaf).

Standalone it is a *read-only* landing surface (the trainer lives in the Lab
workspace): clicking a cell prints where to practise it.  The view refreshes
from the progress files periodically, so a Lab / Functional Network session
running alongside shows up live.  The same :class:`DashboardView` is mounted
as the "Home" tab inside ``run_harmony_lab_demo.py``, where clicks DO launch.

JS<->Python uses the same ``runJavaScript`` + polling bridge as every other
panel (no QWebChannel).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtCore import Qt, QCoreApplication, QTimer, QUrl, pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout
from PyQt6.QtWebEngineWidgets import QWebEngineView

from harmony.progress_service import ProgressService

_BEAT = Path(__file__).resolve().parent / "beat_selector"
_DASHBOARD_HTML = _BEAT / "dashboard.html"

#: Standalone refresh cadence (ms): re-read both progress files so sessions
#: running in the other launchers show up without a restart.
_REFRESH_MS = 5000


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DashboardView(QWidget):
    """The Home dashboard web panel (heatmap + due strip + streaks).

    Bridges via the usual ``runJavaScript`` polling pattern:

    * polls ``Dashboard.takeLaunch()`` -> ``launchRequested`` (a clicked
      leaf's curriculum node id -- the Lab host launches it);
    * ``set_payload`` pushes a fresh dashboard payload (host-side clock).
    """

    launchRequested = pyqtSignal(str)      # a clicked curriculum leaf node id

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
        self.web.load(QUrl.fromLocalFile(str(_DASHBOARD_HTML)))

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(200)
        self._poll_timer.timeout.connect(self._poll)

    def _on_loaded(self, ok: bool):
        if not ok:
            return
        self._run_js(
            "window.DASHBOARD_DATA = %s; "
            "window.Dashboard && window.Dashboard.init(window.DASHBOARD_DATA);"
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
                node_id = json.loads(val)
            except Exception:
                return
            if isinstance(node_id, str) and node_id:
                self.launchRequested.emit(node_id)

        self._run_js(
            "(window.Dashboard && window.Dashboard.takeLaunch) "
            "? JSON.stringify(window.Dashboard.takeLaunch() || null) : null",
            on_launch)

    def set_payload(self, payload: dict):
        self._payload = payload
        if self._html_ready:
            self._run_js("window.Dashboard && window.Dashboard.setPayload(%s);"
                         % json.dumps(payload))


class DashboardWindow(QWidget):
    """Standalone shell: the view + a periodic re-read of the progress files."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Music Theory Laboratory — Home dashboard")
        self.view = DashboardView(self._fresh_payload())
        self.view.launchRequested.connect(self._on_launch)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 1)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(_REFRESH_MS)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start()

    @staticmethod
    def _fresh_payload() -> dict:
        # A fresh service each time = a fresh read of both files (they are
        # owned/written by whichever Lab / Network session is running).
        return ProgressService().dashboard_payload(_now())

    def _refresh(self):
        try:
            self.view.set_payload(self._fresh_payload())
        except Exception as exc:
            print("[DASH] refresh failed:", exc)

    @staticmethod
    def _on_launch(node_id: str):
        print(f"[DASH] {node_id}: open run_harmony_lab_demo.py to practise "
              f"(the standalone dashboard is read-only)")


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    QCoreApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    app = QApplication(argv)
    win = DashboardWindow()
    win.resize(1100, 800)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
