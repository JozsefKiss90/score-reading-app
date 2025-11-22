# widget.py — Python-only BeatSelector (no HTML/JS/web engine)
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Set
import json
import xml.etree.ElementTree as ET
from PyQt6.QtCore import QSizeF  # add at top with other imports
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPen
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSplitter, QListWidget, QListWidgetItem, QGraphicsView, QGraphicsScene,
    QGraphicsRectItem, QGraphicsEllipseItem, QMessageBox
)
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtSvgWidgets import QGraphicsSvgItem
import verovio

# timing / pitches / paging (reuse project helpers)
try:
    from model.score_loader import load_notes_from_mxl  # not strictly required here
except Exception:
    from score_loader import load_notes_from_mxl

from .data import Measure, build_measures, build_onsets, build_pitch_map
from .paging import discover_pages_by_numbers

HL_BEAT_FILL = QColor(2, 132, 199, int(255 * 0.18))
HL_BEAT_STROKE = QColor(2, 132, 199, int(255 * 0.85))
HL_NOTE_FILL = QColor(37, 99, 235, int(255 * 0.85))
HL_NOTE_STROKE = QColor(30, 64, 175, 255)

def dlog(*a): print("[BeatSelectorPY]", *a, flush=True)


@dataclass
class _PageState:
    renderer: QSvgRenderer
    svg_item: Optional[QGraphicsSvgItem]  # allow None
    abs_indexes: List[int]
    note_bounds_by_abs: Dict[int, List[Tuple[str, QRectF]]]

class BeatSelector(QWidget):
    """Static Beat Selector implemented purely with PyQt (QtSvg + QGraphicsView)."""
    selectionChanged = pyqtSignal(list)  # emits ['absIdx-beat', …]

    def __init__(self, mxl_path: str, xml_path: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.mxl_path = str(mxl_path)
        self.xml_path = str(xml_path or mxl_path)
        self.setWindowTitle("Beat Selector — Python")

        # ---------- Top bar ----------
        top = QHBoxLayout(); top.setContentsMargins(6, 6, 6, 6)
        self.lbl = QLabel("Page 1")
        self.btn_prev = QPushButton("◀ Prev Page")
        self.btn_next = QPushButton("Next Page ▶")
        self.btn_clear = QPushButton("Clear")
        top.addWidget(self.lbl); top.addStretch(1)
        top.addWidget(self.btn_prev); top.addWidget(self.btn_next); top.addWidget(self.btn_clear)

        # ---------- Graphics / Sidebar ----------
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        
        self.view.setRenderHints(self.view.renderHints())  # default (no AA for crisp staff lines)
        self.view.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        
        self.sidebar = QListWidget()    
        self.sidebar.setMinimumWidth(260)
        self.sidebar_label = QLabel("Selected beats")
        side_col = QVBoxLayout(); side_col.setContentsMargins(6, 6, 6, 6)
        side_col.addWidget(self.sidebar_label); side_col.addWidget(self.sidebar, 1)
        side_wrap = QWidget(); side_wrap.setLayout(side_col)

        split = QSplitter(Qt.Orientation.Horizontal, self)
        split.addWidget(self.view)
        split.addWidget(side_wrap)
        split.setStretchFactor(0, 1)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(split, 1)

        # ---------- Verovio render ----------
        self._tk = verovio.toolkit()
        self._tk.setOptions({
            "pageHeight": 1800, "pageWidth": 1200, "scale": 40,
            "breaks": "auto", "adjustPageHeight": 1, "svgViewBox": 1,
            # keep pitch attrs inside SVG (useful if you later want fine labels)
            "svgAdditionalAttribute": "pname,accid,oct,midi"
        })
        self._tk.loadFile(self.mxl_path)
        self._tk.redoLayout()
        self._page_count = int(self._tk.getPageCount() or 1)

        # ---------- Musical structure ----------
        self.measures, _, self.tempo_segments = build_measures(self.mxl_path)     # timings per measure
        # Optional: raw notes if you want to augment pitch labels from MusicXML
        self.notes_raw, _bpm = load_notes_from_mxl(self.mxl_path, self.xml_path)
        self.onsets_by_index = build_onsets(self.measures, self.tempo_segments, self.notes_raw)
        self.pitch_map = build_pitch_map(self.measures, self.notes_raw)

        # ---------- Per-page SVG + measure mapping ----------
        self._page_svgs, self._page_abs_indexes = discover_pages_by_numbers(self._tk, self.measures)

        # ---------- State ----------
        self._current_page = -1
        self._page_state: Optional[_PageState] = None
        self._beat_items: Dict[str, QGraphicsRectItem] = {}  # key "abs-beat" -> rect item
        self._note_markers: List[QGraphicsEllipseItem] = []  # transient note highlights
        self._selected: Set[str] = set()

        # ---------- Wire ----------
        self.btn_prev.clicked.connect(lambda: self._load_page(self._current_page - 1))
        self.btn_next.clicked.connect(lambda: self._load_page(self._current_page + 1))
        self.btn_clear.clicked.connect(self._clear_selection)
        self.sidebar.itemClicked.connect(self._on_sidebar_click)

        # initial
        self._load_page(0)

    # === Page loading & analysis ===

    def _load_page(self, page: int):
        page = max(0, min(self._page_count - 1, int(page)))
        self.scene.clear()
        self._beat_items.clear()
        self._note_markers.clear()

        svg = self._page_svgs[page]
        abs_indexes = self._page_abs_indexes[page]
        renderer = QSvgRenderer(bytearray(svg, "utf-8"), self)
        if not renderer.isValid():
            QMessageBox.critical(self, "SVG error", "Failed to load page SVG")
            return

        # --- rasterize SVG to pixmap and add to scene ---
        sz = renderer.defaultSize()
        w, h = int(max(1, sz.width())), int(max(1, sz.height()))
        img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0x00FFFFFF)  # transparent background

        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        renderer.render(p)
        p.end()

        pix = QPixmap.fromImage(img)
        pix_item = self.scene.addPixmap(pix)
        pix_item.setZValue(0)

        # scene rect + fit
        self.scene.setSceneRect(0, 0, w, h)
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

        note_bounds_by_abs = self._collect_note_bounds(svg, renderer, abs_indexes)
        self._page_state = _PageState(
            renderer=renderer,
            svg_item=None,  # if your dataclass allows Optional; otherwise remove the field
            abs_indexes=abs_indexes,
            note_bounds_by_abs=note_bounds_by_abs,
        )
        self._current_page = page
        self.lbl.setText(f"Page {page + 1}/{self._page_count} — selected: {len(self._selected)} beats")

        self._build_beat_boxes()
        self._rebuild_sidebar()


    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self.scene.items():
            self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    # === SVG parsing helpers ===

    def _collect_note_bounds(
        self, svg_text: str, renderer: QSvgRenderer, abs_indexes: List[int]
    ) -> Dict[int, List[Tuple[str, QRectF]]]:
        """
        Parse SVG, find each measure <g data-vrv-type="measure">, then grab child <g> with notes/chords
        that have id=...; compute bounds via renderer.boundsOnElement(id).
        """
        out: Dict[int, List[Tuple[str, QRectF]]] = {a: [] for a in abs_indexes}
        try:
            root = ET.fromstring(svg_text)
        except Exception as e:
            dlog("SVG parse failed:", e)
            return out

        # Build quick index: for each visual measure on this page, find its group id and absolute index
        vis_measure_nodes: List[Tuple[int, str, ET.Element]] = []  # (absIdx, id, node)
        for g in root.iter():
            tag = g.tag.split('}')[-1]
            if tag != 'g':
                continue
            typ = g.attrib.get('data-vrv-type') or g.attrib.get('data-type') or ''
            if typ != 'measure' and 'measure' not in g.attrib.get('class', ''):
                continue
            # Verovio groups have an id
            gid = g.attrib.get('id')
            # Visual index maps to abs index by position on page
            vi = len(vis_measure_nodes)
            if vi < len(abs_indexes):
                vis_measure_nodes.append((abs_indexes[vi], gid, g))

        for abs_idx, gid, node in vis_measure_nodes:
            # note-like child <g> groups: data-vrv-type="note" or class "note"
            for ch in node.iter():
                tag = ch.tag.split('}')[-1]
                if tag != 'g':
                    continue
                if (ch.attrib.get('data-vrv-type') == 'note') or ('note' in ch.attrib.get('class', '')):
                    nid = ch.attrib.get('id')
                    if not nid:
                        continue
                    r = renderer.boundsOnElement(nid)
                    if r.isValid():
                        out[abs_idx].append((nid, r))

        # Ensure stable left-to-right order
        for a in out:
            out[a].sort(key=lambda t: (t[1].x() + t[1].right()) * 0.5)
        return out

    # === Beat box construction & selection ===

    def _beats_for_measure(self, m: Measure) -> int:
        # mirror build_pitch_map's logic so UI matches labels :contentReference[oaicite:2]{index=2}
        span_ql = (m.end_ql - m.start_ql) or 4.0
        if abs(span_ql - round(span_ql)) < 1e-6:
            return max(1, min(12, round(span_ql)))
        return 4  # fallback when span is not an integer

    def _measure_box(self, abs_idx: int) -> Optional[QRectF]:
        """Get the tight bounding box of a measure by union of its notes; fallback to equal slice."""
        if not self._page_state:
            return None
        notes = self._page_state.note_bounds_by_abs.get(abs_idx, [])
        if notes:
            rect = QRectF()
            for _, r in notes:
                rect = r if rect.isNull() else rect.united(r)
            # pad a bit vertically to cover stems/beams
            rect.adjust(-6, -12, +6, +12)
            return rect

        # Fallback: equal slice across the page width if no note bounds were detected
        page_rect = self.scene.sceneRect()
        abs_indexes = self._page_state.abs_indexes
        n = len(abs_indexes)
        i = abs_indexes.index(abs_idx) if abs_idx in abs_indexes else 0
        w = page_rect.width() / max(1, n)
        return QRectF(page_rect.left() + i * w, page_rect.top(), w, page_rect.height())

    def _build_beat_boxes(self):
        if not self._page_state:
            return
        for abs_idx in self._page_state.abs_indexes:
            m = self.measures[abs_idx]
            beats = self._beats_for_measure(m)
            mbox = self._measure_box(abs_idx)
            if not mbox:
                continue

            for b in range(beats):
                key = f"{abs_idx}-{b+1}"
                left = mbox.left() + (b / beats) * mbox.width()
                right = mbox.left() + ((b + 1) / beats) * mbox.width()
                rect = QRectF(left, mbox.top(), max(0.0, right - left), mbox.height())

                it = QGraphicsRectItem(rect)
                it.setBrush(QBrush(QColor(2, 132, 199, int(255 * 0.10))))
                pen = QPen(HL_BEAT_STROKE); pen.setCosmetic(True); pen.setWidth(0)
                it.setPen(pen)
                it.setZValue(20)
                it.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, False)
                it.setData(0, key)
                it.setToolTip(f"m{abs_idx} • beat {b+1}/{beats}")
                self.scene.addItem(it)

                # Click handler via view's mousePressEvent: simplest is to override item change
                it.mousePressEvent = self._make_click_handler(it)  # type: ignore
                self._beat_items[key] = it

                # If pre-selected (e.g., when paging), reflect
                self._set_rect_selected(it, key in self._selected)

    def _make_click_handler(self, it: QGraphicsRectItem):
        def _on_press(ev):
            key = it.data(0)
            if key in self._selected:
                self._selected.remove(key)
                self._set_rect_selected(it, False)
            else:
                self._selected.add(key)
                self._set_rect_selected(it, True)
            self._rebuild_sidebar()
            self._emit_selection()
            ev.accept()
        return _on_press

    def _set_rect_selected(self, it: QGraphicsRectItem, on: bool):
        it.setBrush(QBrush(HL_BEAT_FILL if on else QColor(2, 132, 199, int(255 * 0.10))))
        pen = QPen(HL_BEAT_STROKE); pen.setCosmetic(True); pen.setWidth(2 if on else 0)
        it.setPen(pen)

    # === Sidebar ===

    def _rebuild_sidebar(self):
        # keep sidebar order stable
        items = sorted(self._selected, key=lambda s: tuple(map(int, s.split('-'))))
        self.sidebar.clear()
        for key in items:
            abs_idx, beat_no = map(int, key.split('-'))
            labels = (self.pitch_map.get(abs_idx, {}) or {}).get(beat_no, [])
            title = f"m{abs_idx} • beat {beat_no}"
            block = QListWidgetItem(title)
            block.setFlags(Qt.ItemFlag.ItemIsEnabled)
            block.setData(Qt.ItemDataRole.UserRole, json.dumps({"abs": abs_idx, "beat": beat_no, "i": -1}))
            self.sidebar.addItem(block)

            for i, lab in enumerate(labels or []):
                li = QListWidgetItem(f"  • {lab}")
                li.setData(Qt.ItemDataRole.UserRole, json.dumps({"abs": abs_idx, "beat": beat_no, "i": i}))
                self.sidebar.addItem(li)

        self.lbl.setText(f"Page {self._current_page + 1}/{self._page_count} — selected: {len(self._selected)} beats")

    def _on_sidebar_click(self, item: QListWidgetItem):
        try:
            data = json.loads(item.data(Qt.ItemDataRole.UserRole))
        except Exception:
            return
        abs_idx, beat_no, i = data["abs"], data["beat"], data["i"]
        # highlight beat region and (optionally) the i-th note in that beat
        self._highlight_beat(abs_idx, beat_no, note_index=i)

    # === Highlight helpers ===

    def _clear_note_markers(self):
        for it in self._note_markers:
            self.scene.removeItem(it)
        self._note_markers.clear()

    def _highlight_beat(self, abs_idx: int, beat_no: int, note_index: int = -1):
        # toggle selection if user clicked title line in sidebar
        key = f"{abs_idx}-{beat_no}"
        if key not in self._selected:
            self._selected.add(key)
            it = self._beat_items.get(key)
            if it:
                self._set_rect_selected(it, True)
            self._emit_selection()
            self._rebuild_sidebar()

        self._clear_note_markers()

        # Beat rect overlay pulse (thin outline)
        it = self._beat_items.get(key)
        if it:
            pen = QPen(QColor(14, 165, 233, 220)); pen.setCosmetic(True); pen.setWidth(3)
            it.setPen(pen)

        if note_index >= 0:
            # Find i-th note within this beat via note bounds
            notes = self._page_state.note_bounds_by_abs.get(abs_idx, []) if self._page_state else []
            if notes:
                # restrict to notes whose center lies within the beat rect
                beat_rect = it.rect() if it else self._measure_box(abs_idx)
                if beat_rect:
                    within = [r for (_nid, r) in notes
                              if beat_rect.left() <= (r.center().x()) <= beat_rect.right()]
                    if 0 <= note_index < len(within):
                        r = within[note_index]
                        marker = QGraphicsEllipseItem(QRectF(r.center().x() - 6, r.center().y() - 6, 12, 12))
                        marker.setBrush(QBrush(HL_NOTE_FILL))
                        pen = QPen(HL_NOTE_STROKE); pen.setCosmetic(True); pen.setWidth(1)
                        marker.setPen(pen); marker.setZValue(30)
                        self.scene.addItem(marker)
                        self._note_markers.append(marker)

    # === Actions ===

    def _emit_selection(self):
        ordered = sorted(self._selected, key=lambda s: tuple(map(int, s.split('-'))))
        self.selectionChanged.emit(ordered)

    def _clear_selection(self):
        self._selected.clear()
        for it in self._beat_items.values():
            self._set_rect_selected(it, False)
        self._clear_note_markers()
        self._rebuild_sidebar()
        self._emit_selection()
