from __future__ import annotations
import os
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")
os.environ.setdefault("QT_OPENGL", "software")  # often fixes silent exits on Windows
import json
import sys
from dataclasses import dataclass
from pathlib import Path
import shutil, tempfile, json
from typing import List, Dict, Tuple, Optional
from extract_pitches import extract_pitches   # if colocated; otherwise import your module

from PyQt6.QtCore import Qt, QUrl, pyqtSlot, QCoreApplication
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QHBoxLayout,
    QPushButton,
    QApplication,
    QFileDialog,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
import verovio
import xml.etree.ElementTree as ET
 
from model.score_loader import (
    build_tempo_segments,         # -> [{start_ql,end_ql,bpm,start_sec,end_sec},]
    build_measure_times,          # -> [{"number", "start_ql","end_ql","start_sec","end_sec"}, .]
    ql_to_seconds,                # -> sec for absolute QL offset
    load_notes_from_mxl,          # -> (notes,bpm) notes: {"pitch","start","duration","staff"} in QL
)  

def dlog(*args): print("[ScoreViewBeats]", *args, flush=True)


@dataclass
class Measure:
    index: int
    number: int
    start_ql: float
    end_ql: float
    start_sec: float
    end_sec: float


# --- HTML/JS host -------------------------------------------------------------

_HTML = r'''
<!DOCTYPE html>
'''


# --- QWidget wrapper ----------------------------------------------------------

class ScoreViewBeats(QWidget):
    """
    Variant of ScoreView: same cursor behaviour, but all beat/measure boxes
    are drawn at once and can be toggled on/off.
    """

    musicTimeChanged = None  # placeholder; view is passive and driven externally

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
        # Toggle button for beat boxes
        self._beats_visible = False
        self.btnBeats = QPushButton("Show beats")
        self.btnBeats.setCheckable(True)
        self.btnBeats.setChecked(False)
        self.btnBeats.clicked.connect(self._on_toggle_beats)
        top.addWidget(self.btnBeats)

        # --- pagination buttons ---
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

        # Verovio render
        self._tk = verovio.toolkit()
        self._tk.setOptions({
            "pageHeight": 1800,
            "pageWidth": 1200,
            "scale": 40,
            "breaks": "auto",
            "adjustPageHeight": 1,
            "svgViewBox": 1,
        })
        self._tk.loadFile(self.mxl_path)
        self._tk.redoLayout()
        self._tk.renderToMIDI()
        print("pageCount =", self._tk.getPageCount())
        print("duration =", getattr(self._tk, "getDuration", lambda: None)())
        self._page_count = int(self._tk.getPageCount() or 1)

        # Musical timing from loader
        self.tempo_segments = build_tempo_segments(self.mxl_path)
        mt = build_measure_times(self.mxl_path)
        self.measures: List[Measure] = [
            Measure(
                i,
                int(m["number"]),
                float(m["start_ql"]),
                float(m["end_ql"]),
                float(m["start_sec"]),
                float(m["end_sec"]),
            )
            for i, m in enumerate(mt)
        ]

        # Onsets per measure (seconds relative)
        self.onsets_by_index: List[List[float]] = self._build_onsets()
        self.events_by_index = self._build_pitch_events()

        self.beats_by_index = self._build_beats()
        # Build paging map by parsing each page SVG for measure numbers ("n" attribute)
        self._page_svgs: List[str] = []
        self._page_abs_indexes: List[List[int]] = []  # per page, abs measure indexes
        self._index_to_page: Dict[int, int] = {}
        self._discover_pages_by_numbers()

        # temp files + initial page
        tmp = Path(tempfile.gettempdir())
        self._svg_path = tmp / "score_page_beats.svg"
        self._prepare_web_assets()
        print(self._svg_path)
        self._html_out.write_text(_HTML, encoding="utf-8")
        self._current_page = -1
        self._html_ready = False
        self._pending_sec: Optional[float] = None
        self._last_logged: Tuple[int, int] | None = None  

        print("[ScoreViewBeats] about to _load_page(0)", flush=True)
        self._load_page(0)
        print("[ScoreViewBeats] _load_page(0) returned", flush=True)

    # --- beat toggle API ------------------------------------------------------

    def _on_toggle_beats(self, checked: bool):
        self.set_beats_visible(checked)

    # --- pagination API ----------------------------------------------------------

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
        """Public method: show/hide all beat boxes."""
        self._beats_visible = bool(visible)
        try:
            self.web.page().runJavaScript(
                f"setBeatBoxesVisible({str(self._beats_visible).lower()});"
            )
        except Exception:
            pass
        self.btnBeats.setText("Hide beats" if self._beats_visible else "Show beats")

    def _build_pitch_events(self) -> List[List[dict]]:
        """
        For each abs measure index: list of events {t_rel: seconds-in-measure, pitch: 'C#4', used: bool}
        """
        notes, _ = load_notes_from_mxl(self.mxl_path, self.xml_path)
        events = [[] for _ in self.measures]

        starts = [m.start_ql for m in self.measures]

        def find_idx(ql: float) -> int:
            lo, hi = 0, len(starts) - 1
            while lo <= hi:
                mid = (lo + hi) // 2
                m = self.measures[mid]
                if ql < m.start_ql:
                    hi = mid - 1
                elif ql >= m.end_ql:
                    lo = mid + 1
                else:
                    return mid
            return max(0, min(len(starts) - 1, lo))

        for n in notes:
            ql = float(n["start"])
            i = find_idx(ql)
            m = self.measures[i]
            sec = ql_to_seconds(self.tempo_segments, ql)
            t_rel = max(0.0, sec - m.start_sec)

            # n["pitch"] is MIDI in your loader output; reuse your formatter
            pitch_name = self._midi_to_name(int(n["pitch"]))
            events[i].append({"t_rel": t_rel, "pitch": pitch_name, "used": False})

        # sort per measure by time, then pitch (stable)
        for i in range(len(events)):
            events[i].sort(key=lambda e: (e["t_rel"], e["pitch"]))
        return events

    def _build_beats(self):
        beats = [[] for _ in self.measures]
        for i, m in enumerate(self.measures):
            bar_ql = m.end_ql - m.start_ql
            n_beats = max(1, int(round(bar_ql)))   # quarter = beat (2/4,3/4,4/4…)
            step_ql = bar_ql / n_beats
            row=[]
            for k in range(n_beats):
                ql = m.start_ql + k*step_ql
                row.append(max(0.0, ql_to_seconds(self.tempo_segments, ql) - m.start_sec))
            beats[i]=row
        return beats
    # --- core implementation (mostly copied from original ScoreView) ---------

    def _build_onsets(self) -> List[List[float]]:
        notes, _ = load_notes_from_mxl(self.mxl_path, self.xml_path)
        arr = [[] for _ in self.measures]

        # precompute for binary search
        starts = [m.start_ql for m in self.measures]

        def find_idx(ql: float) -> int:
            lo, hi = 0, len(starts) - 1
            while lo <= hi:
                mid = (lo + hi) // 2
                m = self.measures[mid]
                if ql < m.start_ql:
                    hi = mid - 1
                elif ql >= m.end_ql:
                    lo = mid + 1
                else:
                    return mid
            return max(0, min(len(starts) - 1, lo))

        for n in notes:
            ql = float(n["start"])
            i = find_idx(ql)
            m = self.measures[i]
            sec = ql_to_seconds(self.tempo_segments, ql)
            arr[i].append(max(0.0, sec - m.start_sec))

        # sort & dedup 10ms
        for i, L in enumerate(arr):
            L.sort()
            uniq = []
            for t in L:
                if not uniq or abs(t - uniq[-1]) > 0.010:
                    uniq.append(t)
            arr[i] = uniq
        return arr

    def _discover_pages_by_numbers(self):
        self._page_svgs.clear()
        self._page_abs_indexes.clear()
        self._index_to_page.clear()

        # helper: build mapping measure number -> absolute index in our measures
        num_to_abs: Dict[int, int] = {}
        for m in self.measures:
            if m.number not in num_to_abs:
                num_to_abs[m.number] = m.index

        for p in range(self._page_count):
            svg = self._tk.renderToSVG(p + 1)  # 1-based API
            self._page_svgs.append(svg)
            abs_list: List[int] = []
            try:
                root = ET.fromstring(svg)
                # find all groups that declare data-vrv-type="measure"
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
                        # fallback: continue sequentially
                        abs_idx = (abs_list[-1] + 1) if abs_list else len(
                            sum(self._page_abs_indexes, [])
                        )
                        abs_idx = min(abs_idx, len(self.measures) - 1)
                    abs_list.append(abs_idx)
            except Exception as e:
                dlog("SVG parse error:", e)
                # fallback: attempt to count measures by substring
                count = (
                    svg.count('data-vrv-type="measure"')
                    or svg.count('class="measure"')
                    or 1
                )
                base = len(sum(self._page_abs_indexes, []))
                abs_list = [
                    min(base + i, len(self.measures) - 1) for i in range(count)
                ]

            self._page_abs_indexes.append(abs_list)
            for a in abs_list:
                self._index_to_page[a] = p

        if not self._page_abs_indexes:
            self._page_abs_indexes = [[i for i in range(len(self.measures))]]
            self._index_to_page = {i: 0 for i in range(len(self.measures))}

    def _page_for_index(self, abs_idx: int) -> int:
        return self._index_to_page.get(abs_idx, 0)

    def _prepare_web_assets(self):
        """
        Prepare a self-contained web root for QWebEngine:

        %TEMP%/score_beats_web/web/
            beatpage.html        <-- processed (placeholders replaced)
            js/                  <-- copied ES modules
            app.js, dom.js, cursor.js, geom.js, sidebar.js, state.js, utils.js
        """

        # 1) Project root = folder that contains score_view_beats.py
        project_root = Path(__file__).resolve().parent

        # 2) HTML template lives in: <project_root>/beat_selector/beatpage.html
        html_template = project_root / "beat_selector" / "beatpage.html"
        if not html_template.exists():
            raise FileNotFoundError(f"HTML template not found: {html_template}")

        # 3) JS files live directly in: <project_root>/beat_selector/
        js_source_dir = project_root / "beat_selector"
        if not js_source_dir.exists():
            raise FileNotFoundError(f"JS source dir not found: {js_source_dir}")

        # 4) Create the temp web root
        tmp_root = Path(tempfile.gettempdir()) / "score_beats_web" / "web"
        js_out   = tmp_root / "js"
        tmp_root.mkdir(parents=True, exist_ok=True)
        js_out.mkdir(parents=True, exist_ok=True)

        # 5) Copy JS modules you need from beat_selector → temp/web/js
        wanted = [
            "app.js",
            "dom.js",
            "cursor.js",
            "geom.js",
            "sidebar.js",
            "state.js",
            "utils.js",
        ]
        for name in wanted:
            src = js_source_dir / name
            if not src.exists():
                raise FileNotFoundError(f"Missing JS module: {src}")
            shutil.copyfile(src, js_out / name)

        # 6) Read the HTML template and keep raw for later placeholder replacement
        self._html_template_raw = html_template.read_text(encoding="utf-8")

        # 7) Remember the processed HTML output path inside temp web root
        self._web_root = tmp_root
        self._html_out = tmp_root / "beatpage.html"

    
    def _load_page(self, page: int):
        page = max(0, min(self._page_count - 1, page))

        # IMPORTANT: set current page early so SVG parsing uses the correct page mapping
        self._current_page = page

        dlog("writing svg...")
        self._svg_path.write_text(self._page_svgs[page], encoding="utf-8")
        dlog("svg written")

        dlog("building maps...")
        abs_indexes = self._page_abs_indexes[page]
        note_times_map = {i: self.onsets_by_index[i] for i in abs_indexes if i < len(self.onsets_by_index)}
        beat_times_map = {i: self.beats_by_index[i] for i in abs_indexes if i < len(self.beats_by_index)}
        dlog("maps built")

        dlog("calling extract_pitches...")
        ret = extract_pitches(self.xml_path)
        dlog("extract_pitches returned")

        dlog("building note_map from verovio...")
        note_map = self.build_note_map_from_verovio(abs_indexes, note_times_map, beat_times_map)
        note_map_json = json.dumps(note_map)
        dlog("note_map built")

        # Build processed HTML from the external template
        dlog("building HTML...")
        html = (
            self._html_template_raw
            .replace("{ABS_INDEXES_JSON}", json.dumps(abs_indexes))
            .replace("{NOTE_TIMES_MAP_JSON}", json.dumps(note_times_map))
            .replace("{BEAT_TIMES_MAP_JSON}", json.dumps(beat_times_map))
            .replace("{PITCH_MAP_JSON}", note_map_json)
        )

        # Write processed HTML next to the /js modules so relative imports resolve
        self._html_out.write_text(html, encoding="utf-8")

        self._html_ready = False
        self._current_page = page
        self.lbl.setText(
            f"Score — page {page+1}/{self._page_count}"
            + (" (beats ON)" if self._beats_visible else " (beats OFF)")
        )

        try:
            self.web.loadFinished.disconnect()
        except Exception:
            pass

        def on_loaded(ok: bool):
            self._html_ready = True
            # now call the bridges installed by app.js
            self.web.page().runJavaScript(
                f"setPageAndSvg({page}, {json.dumps(self._svg_path.as_uri())});"
            )
            self.set_beats_visible(self._beats_visible)
            if self._pending_sec is not None:
                sec = self._pending_sec
                self._pending_sec = None
                self._apply_time(sec)

        dlog("loading HTML into QWebEngineView...")
        self.web.load(QUrl.fromLocalFile(str(self._html_out)))
        dlog("HTML load triggered")
        self.web.loadFinished.connect(on_loaded)

    def _vv_json(self, x):
        """Verovio Python bindings often return JSON strings; normalize to dict/list."""
        if x is None:
            return None
        if isinstance(x, (dict, list)):
            return x
        if isinstance(x, str):
            s = x.strip()
            if not s:
                return None
            try:
                return json.loads(s)
            except Exception:
                return s
        return x


    def _vv_get_element_info(self, el_id: str) -> dict | None:
        """Return parsed element info dict or None."""
        try:
            info = self._tk.getElementInfo(el_id)
        except Exception:
            return None
        return self._vv_json(info)


    def _pitch_from_info(self, info: dict) -> str | None:
        if not isinstance(info, dict):
            return None

        # 1) direct note fields (current behavior)
        pname = info.get("pname") or info.get("pName") or info.get("pitchName")
        octv  = info.get("oct") or info.get("octave")
        accid = info.get("accid") or info.get("accidental") or info.get("accidGes")
        if pname is not None and octv is not None:
            return self._format_pitch(pname, octv, accid)

        # 2) MIDI pitch directly
        midi = info.get("midi") or info.get("pitch")
        if isinstance(midi, int):
            return self._midi_to_name(midi)

        # 3) Nested notes (common for chords / note groups)
        for key in ("notes", "note", "children", "elements"):
            child = info.get(key)
            if isinstance(child, list) and child:
                # try first child that yields a pitch
                for c in child:
                    if isinstance(c, dict):
                        p = self._pitch_from_info(c)
                        if p:
                            return p

        return None


    def _format_pitch(self, pname, octv, accid) -> str:
        acc = ""
        if accid in ("s", "sharp", "#"):
            acc = "#"
        elif accid in ("f", "flat", "b"):
            acc = "b"
        elif accid in ("x", "ss", "dblsharp", "##"):
            acc = "##"
        elif accid in ("ff", "dblflat", "bb"):
            acc = "bb"
        return f"{str(pname).upper()}{acc}{int(octv)}"


    def _midi_to_name(self, midi: int) -> str:
        names = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
        name = names[midi % 12]
        octave = (midi // 12) - 1
        return f"{name}{octave}"


    def _x_from_info(self, info: dict) -> float | None:
        """Try to read x-coordinate from bbox in element info."""
        if not isinstance(info, dict):
            return None
        bbox = info.get("bbox") or info.get("boundingBox") or info.get("box")
        if isinstance(bbox, dict):
            x = bbox.get("x")
            if isinstance(x, (int, float)):
                return float(x)
        # sometimes x is at top-level
        x = info.get("x")
        if isinstance(x, (int, float)):
            return float(x)
        return None

    def _svg_note_x(self, note_g: ET.Element) -> float | None:
        # find a <use ... transform="translate(X, Y) ..."> inside this note group
        for el in note_g.iter():
            tag = el.tag.split("}")[-1]
            if tag != "use":
                continue
            tr = el.attrib.get("transform", "")
            # common: "translate(4043, 2250) scale(...)"
            if "translate(" in tr:
                try:
                    inside = tr.split("translate(", 1)[1].split(")", 1)[0]
                    x_str = inside.split(",", 1)[0].strip()
                    return float(x_str)
                except Exception:
                    return None
        return None

    def _collect_note_ids_by_measure_from_svg(self, svg: str, abs_indexes: list[int]) -> dict[int, list[str]]:
        out: dict[int, list[str]] = {}
        num_to_abs = {self.measures[i].number: i for i in abs_indexes}

        root = ET.fromstring(svg)

        # collect measure groups in document order
        measure_groups = []
        for g in root.iter():
            if g.tag.split("}")[-1] != "g":
                continue
            cls = g.attrib.get("class", "")
            if "measure" in cls.split() or cls == "measure":
                measure_groups.append(g)
        dlog(f"SVG measure groups found = {len(measure_groups)}; abs_indexes on page = {len(abs_indexes)}")

        # fallback mapping: k-th measure group -> abs_indexes[k]
        for k, g in enumerate(measure_groups):
            abs_m = None

            # preferred: read measure number if present
            n_attr = g.attrib.get("n") or g.attrib.get("data-n") or ""
            if n_attr:
                try:
                    meas_num = int(str(n_attr).strip().split()[0])
                    abs_m = num_to_abs.get(meas_num)
                except Exception:
                    abs_m = None

            # fallback: sequential on-page order
            if abs_m is None:
                if k >= len(abs_indexes):
                    continue
                abs_m = abs_indexes[k]

            ids: list[str] = []
            for gg in g.iter():
                if gg.tag.split("}")[-1] != "g":
                    continue
                cls2 = gg.attrib.get("class", "")
                if "note" not in cls2.split():   # only true note groups
                    continue
                nid = gg.attrib.get("id")
                if nid:
                    ids.append(nid)
                out[abs_m] = ids


            out[abs_m] = ids

        return out

    def build_note_map_from_verovio(self, abs_indexes, note_times_map, beat_times_map) -> dict:
        note_map: dict[str, dict[str, list[dict]]] = {}

        # Parse current page SVG once and get note IDs per measure
        svg = self._page_svgs[self._current_page]
        ids_by_abs = self._collect_note_ids_by_measure_from_svg(svg, abs_indexes)
        dlog(f"SVG note-id collection: measures={len(ids_by_abs)} totalNotes={sum(len(v) for v in ids_by_abs.values())}")

        for abs_m in abs_indexes:
            m = self.measures[abs_m]
            beats = beat_times_map.get(abs_m, [])

            # beats[] are already RELATIVE-to-measure (seconds)
            beat_starts_rel = [float(t) for t in beats]
            measure_dur_rel = float(m.end_sec - m.start_sec)
            beat_ends_rel = beat_starts_rel[1:] + [measure_dur_rel]

            note_map[str(abs_m)] = {str(i + 1): [] for i in range(len(beats))}

            ids = ids_by_abs.get(abs_m, [])
            if not ids:
                continue

            # --- Verovio-based measure anchor (ms) ---
            times_ms = []
            bucketed = 0
            pitch_ok = 0
            pitch_miss = 0

            for el_id in ids:
                try:
                    ms = int(self._tk.getTimeForElement(str(el_id)))
                    # Some builds return -1 when unknown
                    if ms >= 0:
                        times_ms.append(ms)
                except Exception:
                    pass

            if not times_ms:
                continue

            measure_start_ms = min(times_ms)
            dlog(
                f"abs_m={abs_m} measure_start_ms={measure_start_ms} "
                f"t_rel_range={[ (min(times_ms)-measure_start_ms)/1000.0, (max(times_ms)-measure_start_ms)/1000.0 ]} "
                f"beats={beat_starts_rel}"
            )

            # ---- MusicXML pitch events for this measure (must be precomputed) ----
            # Expected shape: self.events_by_index[abs_m] = [{"t_rel": float, "pitch": str, "used": bool}, ...]
            events = []
            if hasattr(self, "events_by_index") and self.events_by_index and abs_m < len(self.events_by_index):
                events = self.events_by_index[abs_m]
                for e in events:
                    e["used"] = False

            # Define ONCE per measure (not inside the per-note loop)
            def pick_pitch(t_rel: float, tol: float = 0.08):
                """
                Choose nearest unused MusicXML pitch event by measure-relative time.
                tol is in seconds; tune if necessary.
                """
                if not events:
                    return None

                best = None
                best_dt = 1e18
                for e in events:
                    if e.get("used", False):
                        continue
                    dt = abs(float(e["t_rel"]) - float(t_rel))
                    if dt < best_dt:
                        best_dt = dt
                        best = e

                if best is not None and best_dt <= tol:
                    best["used"] = True
                    return best["pitch"]
                return None

            # ---- Build beat buckets ----
            for el_id in ids:
                try:
                    ms = int(self._tk.getTimeForElement(str(el_id)))
                except Exception:
                    continue
                if ms < 0:
                    continue

                # measure-relative time in seconds, in Verovio's timing domain
                t_rel = (ms - measure_start_ms) / 1000.0

                # bucket into beat index using RELATIVE beat windows
                b_idx = None
                for i, (bs, be) in enumerate(zip(beat_starts_rel, beat_ends_rel), start=1):
                    if bs - 1e-6 <= t_rel < be - 1e-6:
                        b_idx = i
                        break
                if b_idx is None:
                    continue
                bucketed += 1

                # Pitch assignment WITHOUT getElementInfo()
                pitch = pick_pitch(t_rel)
                if pitch is None:
                    pitch_miss += 1
                    continue
                pitch_ok += 1

                # You currently do not compute x here; avoid NameError.
                x = None

                note_map[str(abs_m)][str(b_idx)].append({"id": el_id, "pitch": pitch, "x": x})

            dlog(f"abs_m={abs_m} bucketed={bucketed} pitch_ok={pitch_ok} pitch_miss={pitch_miss}")

            # sort each beat left->right by x
            for b in note_map[str(abs_m)].keys():
                rows = note_map[str(abs_m)][b]
                rows.sort(key=lambda r: (1e18 if r["x"] is None else r["x"]))

                # debug
                print("\n--- VEROVIO NOTE_MAP DEBUG ---")
                print(f"abs_measure={abs_m} beat={b}")
                print("ids:", [r["id"] for r in rows])
                print("pitches:", [r["pitch"] for r in rows])
                print("x:", [r["x"] for r in rows])
                print("--- END DEBUG ---\n")

        return note_map

    # --- time-driven cursor (unchanged API) ----------------------------------

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
        self.web.page().runJavaScript(
            f"jsSetCursorAbs({int(m_idx)}, {float(t_in)}, {float(dur)})"
        )
        if self._last_logged != (page, m_idx):
            dlog(
                f"page={page} meas_abs={m_idx} num={m.number} "
                f"t_in={t_in:.3f}/{dur:.3f}"
            )
            self._last_logged = (page, m_idx)
        self.lbl.setText(
            f"t={sec:7.3f}s  page {page+1}/{self._page_count}  "
            f"meas {m_idx} (no.{m.number})  t={t_in:0.3f}/{dur:0.3f}s"
        )


# --- simple executable harness ------------------------------------------------

def _pick_file_if_needed(path: Optional[str]) -> Optional[str]:
    if path:
        return path
    dlg = QFileDialog()
    dlg.setFileMode(QFileDialog.FileMode.ExistingFile)
    dlg.setNameFilter("Scores (*.mxl *.xml *.musicxml)")
    if dlg.exec():
        files = dlg.selectedFiles()
        if files:
            return files[0]
    return None


def main(argv: List[str] | None = None):
    argv = list(sys.argv if argv is None else argv)

    # Required for QtWebEngine stability on many Windows setups
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

    app = QApplication(argv)
    app.aboutToQuit.connect(lambda: print("[ScoreViewBeats] aboutToQuit()", flush=True))

    mxl_path = _pick_file_if_needed(argv[1] if len(argv) > 1 else None)
    if not mxl_path:
        print("No score selected, exiting.")
        return 0

    w = ScoreViewBeats(mxl_path)
    w.resize(900, 700)
    w.show()

    rc = app.exec()
    print(f"[ScoreViewBeats] app.exec() returned {rc}", flush=True)
    return rc



if __name__ == "__main__":
    raise SystemExit(main())
