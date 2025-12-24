from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")
os.environ.setdefault("QT_OPENGL", "software")

from PyQt6.QtCore import Qt, QUrl, pyqtSlot
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton
from PyQt6.QtWebEngineWidgets import QWebEngineView
import verovio
import xml.etree.ElementTree as ET

from model.score_loader import build_tempo_segments, build_measure_times

# Optional: keep instrumentation parity with v0
try:
    from extract_pitches import extract_pitches
except Exception:
    extract_pitches = None

from .timing import Measure, build_onsets_by_measure, build_beats_by_measure, build_pitch_events_by_measure
from .web_assets import prepare_web_assets
from .verovio_map import VerovioNoteMapper


def dlog(*args):  # keep identical prefix
    print("[ScoreViewBeats]", *args, flush=True)


class ScoreViewBeats(QWidget):
    musicTimeChanged = None

    def __init__(self, mxl_path: str, xml_path: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.mxl_path = str(mxl_path)
        self.xml_path = str(xml_path or mxl_path)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        top.setContentsMargins(6, 6, 6, 6)
        self.lbl = QLabel("Score (static beat boxes)")
        self.lbl.setStyleSheet("color:#fff;")
        top.addWidget(self.lbl)
        top.addStretch(1)

        self._beats_visible = False
        self.btnBeats = QPushButton("Show beats")
        self.btnBeats.setCheckable(True)
        self.btnBeats.setChecked(False)
        self.btnBeats.clicked.connect(self._on_toggle_beats)
        top.addWidget(self.btnBeats)

        self.btnPrev = QPushButton("◀ Prev")
        self.btnPrev.clicked.connect(self._go_prev_page)
        top.addWidget(self.btnPrev)

        self.btnNext = QPushButton("Next ▶")
        self.btnNext.clicked.connect(self._go_next_page)
        top.addWidget(self.btnNext)

        layout.addLayout(top)

        self.web = QWebEngineView(self)
        self.web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        layout.addWidget(self.web, 1)

        self._tk = verovio.toolkit()
        self._tk.setOptions({
            "pageHeight": 1800,
            "pageWidth": 1200,
            "scale": 40,
            "breaks": "auto",
            "adjustPageHeight": 1,
            "svgViewBox": 1,

            "svgAdditionalAttribute": [
                "note@pname", "note@oct",
                "note@accid", "note@accid.ges",
                "note@pnum", "note@pnum.ges",
            ],

        })

        self._tk.loadFile(self.mxl_path)
        self._tk.redoLayout()
        self._tk.renderToMIDI()
        print("pageCount =", self._tk.getPageCount())
        print("duration =", getattr(self._tk, "getDuration", lambda: None)())

        self._page_count = int(self._tk.getPageCount() or 1)

        self.tempo_segments = build_tempo_segments(self.mxl_path)
        mt = build_measure_times(self.mxl_path)
        self.measures: List[Measure] = [
            Measure(i, int(m["number"]), float(m["start_ql"]), float(m["end_ql"]), float(m["start_sec"]), float(m["end_sec"]))
            for i, m in enumerate(mt)
        ]

        self.onsets_by_index = build_onsets_by_measure(self.measures, self.tempo_segments, self.mxl_path, self.xml_path)
        self.events_by_index = build_pitch_events_by_measure(self.measures, self.tempo_segments, self.mxl_path, self.xml_path)
        self.beats_by_index = build_beats_by_measure(self.measures, self.tempo_segments)

        self._page_svgs: List[str] = []
        self._page_abs_indexes: List[List[int]] = []
        self._index_to_page: Dict[int, int] = {}
        self._discover_pages_by_numbers()

        self._assets = prepare_web_assets()
        self._current_page = -1
        self._html_ready = False
        self._pending_sec: Optional[float] = None
        self._last_logged: Tuple[int, int] | None = None

        self._mapper = VerovioNoteMapper(self._tk, self.measures, self.events_by_index, dlog=dlog)

        print("[ScoreViewBeats] about to _load_page(0)", flush=True)
        self._load_page(0)
        print("[ScoreViewBeats] _load_page(0) returned", flush=True)

    def _on_toggle_beats(self, checked: bool):
        self.set_beats_visible(checked)

    def _go_prev_page(self):
        new_page = max(0, self._current_page - 1)
        if new_page != self._current_page:
            self._load_page(new_page)

    def _go_next_page(self):
        new_page = min(self._page_count - 1, self._current_page + 1)
        if new_page != self._current_page:
            self._load_page(new_page)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Right:
            self._go_next_page()
        elif event.key() == Qt.Key_Left:
            self._go_prev_page()
        else:
            super().keyPressEvent(event)

    def set_beats_visible(self, visible: bool):
        self._beats_visible = bool(visible)
        try:
            self.web.page().runJavaScript(f"setBeatBoxesVisible({str(self._beats_visible).lower()});")
        except Exception:
            pass
        self.btnBeats.setText("Hide beats" if self._beats_visible else "Show beats")

    def _discover_pages_by_numbers(self):
        self._page_svgs.clear()
        self._page_abs_indexes.clear()
        self._index_to_page.clear()

        num_to_abs: Dict[int, int] = {}
        for m in self.measures:
            if m.number not in num_to_abs:
                num_to_abs[m.number] = m.index

        for p in range(self._page_count):
            svg = self._tk.renderToSVG(p + 1)
            self._page_svgs.append(svg)
            abs_list: List[int] = []
            try:
                root = ET.fromstring(svg)
                for g in root.iter():
                    tag = g.tag.split("}")[-1]
                    if tag != "g":
                        continue
                    typ = g.attrib.get("data-vrv-type") or g.attrib.get("data-type") or ""
                    if typ != "measure" and "measure" not in g.attrib.get("class", ""):
                        continue
                    n_attr = g.attrib.get("n") or g.attrib.get("data-n") or ""
                    num = None
                    try:
                        if n_attr:
                            num = int(str(n_attr).strip().split()[0])
                    except Exception:
                        num = None

                    if num is not None and num in num_to_abs:
                        abs_idx = num_to_abs[num]
                    else:
                        abs_idx = (abs_list[-1] + 1) if abs_list else len(sum(self._page_abs_indexes, []))
                        abs_idx = min(abs_idx, len(self.measures) - 1)

                    abs_list.append(abs_idx)
            except Exception as e:
                dlog("SVG parse error:", e)
                count = svg.count('data-vrv-type="measure"') or svg.count('class="measure"') or 1
                base = len(sum(self._page_abs_indexes, []))
                abs_list = [min(base + i, len(self.measures) - 1) for i in range(count)]

            self._page_abs_indexes.append(abs_list)
            for a in abs_list:
                self._index_to_page[a] = p

        if not self._page_abs_indexes:
            self._page_abs_indexes = [[i for i in range(len(self.measures))]]
            self._index_to_page = {i: 0 for i in range(len(self.measures))}

    def _page_for_index(self, abs_idx: int) -> int:
        return self._index_to_page.get(abs_idx, 0)

    def _load_page(self, page: int):
        page = max(0, min(self._page_count - 1, page))

        svg = self._page_svgs[page]
        self._log_svg_pitch_attrs(svg, limit=30)
        #self._log_verovio_pitch_api(svg, limit=10)
        # IMPORTANT: set current page early so SVG parsing uses the correct page mapping
        self._current_page = page

        dlog("writing svg...")
        self._assets.svg_path.write_text(self._page_svgs[page], encoding="utf-8")
        dlog("svg written")

        dlog("building maps...")
        abs_indexes = self._page_abs_indexes[page]
        note_times_map = {i: self.onsets_by_index[i] for i in abs_indexes if i < len(self.onsets_by_index)}
        beat_times_map = {i: self.beats_by_index[i] for i in abs_indexes if i < len(self.beats_by_index)}
        dlog("maps built")

        dlog("calling extract_pitches...")
        if extract_pitches is not None:
            try:
                _ = extract_pitches(self.xml_path)
            except Exception as e:
                dlog("extract_pitches ERROR:", e)
        dlog("extract_pitches returned")

        dlog("building note_map from verovio...")
        note_map = self._mapper.build_note_map_from_verovio(
            page_svg=self._page_svgs[page],
            abs_indexes=abs_indexes,
            beat_times_map=beat_times_map,
        )
        dlog("note_map built")

        dlog("building HTML...")
        html = (
            self._assets.html_template_raw
            .replace("{ABS_INDEXES_JSON}", json.dumps(abs_indexes))
            .replace("{NOTE_TIMES_MAP_JSON}", json.dumps(note_times_map))
            .replace("{BEAT_TIMES_MAP_JSON}", json.dumps(beat_times_map))
            .replace("{PITCH_MAP_JSON}", json.dumps(note_map))
        )

        self._assets.html_out.write_text(html, encoding="utf-8")

        self._html_ready = False
        self.lbl.setText(
            f"Score — page {page + 1}/{self._page_count}"
            + (" (beats ON)" if self._beats_visible else " (beats OFF)")
        )

        try:
            self.web.loadFinished.disconnect()
        except Exception:
            pass

        def on_loaded(ok: bool):
            self._html_ready = True
            self.web.page().runJavaScript(
                f"setPageAndSvg({page}, {json.dumps(self._assets.svg_path.as_uri())});"
            )
            self.set_beats_visible(self._beats_visible)
            if self._pending_sec is not None:
                sec = self._pending_sec
                self._pending_sec = None
                self._apply_time(sec)

        dlog("loading HTML into QWebEngineView...")
        self.web.load(QUrl.fromLocalFile(str(self._assets.html_out)))
        dlog("HTML load triggered")
        self.web.loadFinished.connect(on_loaded)


    @pyqtSlot(float)
    def set_music_time(self, sec: float):
        if not self._html_ready:
            self._pending_sec = sec
            return
        self._apply_time(sec)

    def _measure_for_time(self, sec: float) -> int:
        lo, hi = 0, len(self.measures) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            m = self.measures[mid]
            if sec < m.start_sec:
                hi = mid - 1
            elif sec >= m.end_sec:
                lo = mid + 1
            else:
                return mid
        return max(0, min(len(self.measures) - 1, lo))

    def _apply_time(self, sec: float):
        if not self.measures:
            return
        m_idx = self._measure_for_time(sec)
        m = self.measures[m_idx]
        page = self._page_for_index(m_idx)
        if page != self._current_page:
            self._pending_sec = sec
            self._load_page(page)
            return
        dur = max(1e-6, m.end_sec - m.start_sec)
        t_in = max(0.0, sec - m.start_sec)
        self.web.page().runJavaScript(f"jsSetCursorAbs({int(m_idx)}, {float(t_in)}, {float(dur)})")

        if self._last_logged != (page, m_idx):
            dlog(f"page={page} meas_abs={m_idx} num={m.number} t_in={t_in:.3f}/{dur:.3f}")
            self._last_logged = (page, m_idx)

        self.lbl.setText(
            f"t={sec:7.3f}s  page {page + 1}/{self._page_count}  "
            f"meas {m_idx} (no.{m.number})  t={t_in:0.3f}/{dur:0.3f}s"
        )

    def _log_verovio_pitch_api(self, svg: str, limit: int = 3):
        """
        Crash-proof diagnostic logger for Verovio pitch APIs.

        - Does not json.loads() anything (avoid unexpected 'null'/list/etc.).
        - Guards missing methods.
        - Guards per-id failures.
        """
        try:
            fn_midi = getattr(self._tk, "getMIDIValuesForElement", None)
            fn_attr = getattr(self._tk, "getElementAttr", None)

            if fn_midi is None and fn_attr is None:
                dlog("[pitch api] toolkit has neither getMIDIValuesForElement nor getElementAttr")
                return

            root = ET.fromstring(svg)
            ids = []
            for g in root.iter():
                if g.tag.split("}")[-1] != "g":
                    continue
                cls = (g.attrib.get("class", "") or "")
                if "note" in cls.split() and "id" in g.attrib:
                    ids.append(g.attrib["id"])

            dlog(f"[pitch api] candidate_note_ids={len(ids)} (logging first {min(limit, len(ids))})")

            for nid in ids[:limit]:
                # Skip IDs that toolkit doesn't recognize (cheap safety gate).
                try:
                    t = self._tk.getTimeForElement(nid)
                except Exception as e:
                    dlog(f"[pitch api] id={nid} getTimeForElement ERROR: {e}")
                    continue
                if t is None or (isinstance(t, (int, float)) and t < 0):
                    dlog(f"[pitch api] id={nid} getTimeForElement returned {t!r} (skipping)")
                    continue

                if fn_midi is not None:
                    try:
                        mv = fn_midi(nid)
                        dlog(f"[pitch api] id={nid} MIDI type={type(mv).__name__} val={mv!r}")
                    except Exception as e:
                        dlog(f"[pitch api] id={nid} getMIDIValuesForElement ERROR: {e}")

                if fn_attr is not None:
                    try:
                        ea = fn_attr(nid)
                        dlog(f"[pitch api] id={nid} Attr type={type(ea).__name__} val={ea!r}")
                    except Exception as e:
                        dlog(f"[pitch api] id={nid} getElementAttr ERROR: {e}")

        except Exception as e:
            dlog("[pitch api] FATAL ERROR:", e)
            dlog(traceback.format_exc())

            
    def _log_svg_pitch_attrs(self, svg: str, limit: int = 20):
        keys = [
            "data-pname", "data-oct", "data-accid",
            "data-pname.ges", "data-oct.ges", "data-accid.ges",
            "pname", "oct", "accid",
            "pname.ges", "oct.ges", "accid.ges", 
            "data-pnum", "data-pnum.ges",
        ]

        try:
            root = ET.fromstring(svg)
        except Exception as e:
            dlog("[SVG pitch] parse error:", e)
            return

        # Collect note groups
        note_g = []
        for g in root.iter():
            if g.tag.split("}")[-1] != "g":
                continue
            cls = (g.attrib.get("class", "") or "")
            if "note" in cls.split() and "id" in g.attrib:
                note_g.append(g)

        def collect_attrs(el):
            out = {}
            for k in keys:
                if k in el.attrib:
                    out[k] = el.attrib.get(k)
            return out

        total = len(note_g)
        with_pitch = 0
        dumped = 0

        for g in note_g:
            # search note group + descendants for pitch attrs
            merged = {}
            for el in g.iter():
                merged.update(collect_attrs(el))

            if merged:
                with_pitch += 1
                if dumped < limit:
                    dlog(f"[SVG pitch] id={g.attrib.get('id')} attrs={merged}")
                    dumped += 1

        dlog(f"[SVG pitch] notes_total={total} notes_with_any_pitch_attrs={with_pitch} dumped={dumped}/{limit}")
