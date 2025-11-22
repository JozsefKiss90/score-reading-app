#!/usr/bin/env python3
# score_viewer_pyside6.py
# Minimal MusicXML/MXL viewer using PySide6 + Verovio

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QFileDialog, QSpinBox
)
from PySide6.QtWebEngineWidgets import QWebEngineView

# Verovio Python bindings
import verovio


def human_name(p: str) -> str:
    p = os.path.basename(p)
    return p if len(p) < 80 else "…" + p[-79:]


class ScoreViewer(QWidget):
    def __init__(self, initial_path: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MusicXML/MXL Viewer — PySide6 + Verovio")
        self.resize(1100, 900)

        # UI
        top = QHBoxLayout()
        self.lbl = QLabel("No score loaded")
        self.lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.btn_open = QPushButton("Open…")
        self.btn_prev = QPushButton("← Prev")
        self.btn_next = QPushButton("Next →")
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(1)
        self.page_spin.setPrefix("Page ")
        self.page_spin.setEnabled(False)

        top.addWidget(self.lbl, 1)
        top.addWidget(self.btn_open)
        top.addSpacing(12)
        top.addWidget(self.btn_prev)
        top.addWidget(self.page_spin)
        top.addWidget(self.btn_next)

        self.web = QWebEngineView()
        self.web.setContextMenuPolicy(Qt.NoContextMenu)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.web, 1)

        # Verovio setup
        self.tk = verovio.toolkit()
        # Sensible defaults; tweak scale/page size as you like
        self.tk.setOptions({
            "pageHeight": 1800,
            "pageWidth": 1200,
            "scale": 38,
            "breaks": "auto",
            "svgViewBox": 1,
            "adjustPageHeight": 1
        })

        self.page_count = 0
        self.current_path: str | None = None

        # Signals
        self.btn_open.clicked.connect(self.open_file_dialog)
        self.btn_prev.clicked.connect(self.prev_page)
        self.btn_next.clicked.connect(self.next_page)
        self.page_spin.valueChanged.connect(self.goto_page)

        # Load initial file if provided
        if initial_path:
            self.load_score(initial_path)

    # ---------- File handling ----------
    def open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open MusicXML/MXL",
            os.getcwd(),
            "Scores (*.mxl *.xml *.musicxml);;All files (*.*)",
        )
        if path:
            self.load_score(path)

    def load_score(self, path: str):
        try:
            self.tk.loadFile(path)
            self.tk.redoLayout()
        except Exception as e:
            self.lbl.setText(f"Failed to load: {human_name(path)} — {e}")
            self.page_count = 0
            self.update_controls(enabled=False)
            self.web.setHtml("<h3 style='font-family:system-ui'>Failed to load file.</h3>")
            return

        self.current_path = path
        self.page_count = int(self.tk.getPageCount() or 1)
        self.lbl.setText(f"{human_name(path)}  •  {self.page_count} page(s)")
        self.update_controls(enabled=True)
        self.render_page(1)

    # ---------- Paging ----------
    def update_controls(self, enabled: bool):
        self.btn_prev.setEnabled(enabled)
        self.btn_next.setEnabled(enabled)
        self.page_spin.setEnabled(enabled)
        if enabled:
            self.page_spin.blockSignals(True)
            self.page_spin.setMaximum(max(1, self.page_count))
            self.page_spin.setValue(1)
            self.page_spin.blockSignals(False)
        else:
            self.page_spin.blockSignals(True)
            self.page_spin.setMaximum(1)
            self.page_spin.setValue(1)
            self.page_spin.blockSignals(False)

    # --- replace your render_page() with this ---
    def render_page(self, page: int):
        page = max(1, min(self.page_count or 1, int(page)))
        try:
            svg = self._render_svg_cross_version(page)
        except Exception as e:
            self.web.setHtml(f"<h3 style='font-family:system-ui'>Render error: {e}</h3>")
            return

        self.web.setHtml(svg, baseUrl=QUrl.fromLocalFile(self.current_path or os.getcwd()))
        if self.page_spin.value() != page:
            self.page_spin.blockSignals(True)
            self.page_spin.setValue(page)
            self.page_spin.blockSignals(False)

    def _render_svg_cross_version(self, page: int) -> str:
        # Newer bindings: renderToSVG(int)
        try:
            return self.tk.renderToSVG(page)
        except TypeError:
            pass
        # Some builds: renderToSVG(int, bool)
        try:
            return self.tk.renderToSVG(page, False)
        except TypeError:
            pass
        # Legacy: set page first, then renderToSVG()
        self.tk.setPage(page)
        return self.tk.renderToSVG()


    def prev_page(self):
        if self.page_count:
            self.render_page(self.page_spin.value() - 1)

    def next_page(self):
        if self.page_count:
            self.render_page(self.page_spin.value() + 1)

    def goto_page(self, page: int):
        self.render_page(page)


def pick_default_score() -> str | None:
    # Prefer your uploaded files if present
    candidates = [
        "chopin-prelude-in-e-minor-opus-28-no-4.mxl",
        "score.xml",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    # Otherwise try a CLI arg
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        return sys.argv[1]
    return None


def main():
    # NOTE: On some platforms, importing QtWebEngine *before* QApplication helps initialization.
    app = QApplication(sys.argv)
    initial = pick_default_score()
    w = ScoreViewer(initial)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()