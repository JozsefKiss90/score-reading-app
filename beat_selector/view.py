from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET
import time
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")
os.environ.setdefault("QT_OPENGL", "software")

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSlot
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton
from PyQt6.QtWebEngineWidgets import QWebEngineView

import verovio

from model.score_loader import build_tempo_segments, build_measure_times

# Optional: keep instrumentation parity with v0
try:
    from extract_pitches import extract_pitches
except Exception:
    extract_pitches = None

from .timing import Measure, build_onsets_by_measure, build_beats_by_measure, build_pitch_events_by_measure
from .web_assets import prepare_web_assets
from .verovio_map import SVG_ADDITIONAL_ATTRIBUTES, VerovioNoteMapper, map_page_measures_to_indexes

# MIDI integration (optional)
try:
    from audio.midi_service import MidiService
except Exception:
    try:
        from .midi_service import MidiService
    except Exception:
        MidiService = None

# --- Live MIDI audio monitoring (Fluidsynth) ---
try:
    from audio.midi_player import MidiPlayer
except Exception:
    try:
        from .midi_player import MidiPlayer
    except Exception:
        MidiPlayer = None

try:
    from config import DEFAULT_SF2
except Exception:
    DEFAULT_SF2 = None

def dlog(*args):
    print("[ScoreViewBeats]", *args, flush=True)


class ScoreViewBeats(QWidget):
    musicTimeChanged = None

    def __init__(self, mxl_path: str, xml_path: Optional[str] = None, parent=None, midi_service=None):
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

                # in __init__ right after btnBeats (or wherever you prefer)
        self._dark_mode = False
        self.btnDark = QPushButton("Dark")
        self.btnDark.setCheckable(True)
        self.btnDark.setChecked(False)
        self.btnDark.clicked.connect(self._on_toggle_dark)
        top.addWidget(self.btnDark)

        layout.addLayout(top)

        self.web = QWebEngineView(self)
        self.web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        layout.addWidget(self.web, 1)

        # MIDI (optional): forward note events into the embedded beat selector page.
        self._midi_service = None
        self._owns_midi_service = False

        def _dbg_note_on(*args):
                dlog(f"[MIDI SIG] noteOn args={args!r}")
                # Accept (pitch, vel, ts) or (pitch, vel) or other shapes.
                pitch = args[0] if len(args) >= 1 else -1
                vel   = args[1] if len(args) >= 2 else 0
                ts    = args[-1] if len(args) >= 3 else time.time()
                self._on_midi_note_on(int(pitch), int(vel), float(ts))

        def _dbg_note_off(*args):
            dlog(f"[MIDI SIG] noteOff args={args!r}")
            # Accept (pitch, ts), (pitch, vel, ts), or (pitch) shapes.
            pitch = args[0] if len(args) >= 1 else -1
            ts    = args[-1] if len(args) >= 2 else time.time()
            self._on_midi_note_off(int(pitch), float(ts))

        if midi_service is not None:
            self._midi_service = midi_service
        elif MidiService is not None:
            try:
                self._midi_service = MidiService(self)
                self._owns_midi_service = True
                dlog(f"[MIDI] listening on: {getattr(self._midi_service, 'port_name', None)}")
            except Exception as e:
                dlog("[MIDI] init failed:", e)
                self._midi_service = None

        if self._midi_service is not None:
            try:
                self._midi_service.noteOn.connect(_dbg_note_on)
                self._midi_service.noteOff.connect(_dbg_note_off)

                dlog("[MIDI] connected debug wrappers for noteOn/noteOff")

                dlog("[MIDI] connected noteOn/noteOff signals to ScoreViewBeats slots")
            except Exception as e:
                dlog("[MIDI] connect failed:", e)

        # --- Audio monitor synth (optional) ---
        self._midi_player = None
        self._midi_audio_enabled = True  # set False if you want silent highlight-only

        if MidiPlayer is not None:
            try:
                # IMPORTANT: if DEFAULT_SF2 is None or invalid, MidiPlayer will be silent (it prints a warning).
                self._midi_player = MidiPlayer(DEFAULT_SF2)
                dlog(f"[AUDIO] MidiPlayer ready. soundfont={DEFAULT_SF2!r}")
            except Exception as e:
                dlog("[AUDIO] MidiPlayer init failed:", e)
                self._midi_player = None
        else:
            dlog("[AUDIO] MidiPlayer import failed; no in-app sound.")

        # --- Synthetic note input (plan U2): pointer presses on the on-screen
        # piano and QWERTY typing queue events in the page (note_input.js).
        # This poll drains that queue and sounds the notes.  Grading and
        # highlighting already happened client-side (NoteInput routes through
        # window.onMidiNoteOn/off), so this path is sound-only and never
        # re-enters the page; the hardware-MIDI slots above are untouched.
        self._note_input_poll = QTimer(self)
        self._note_input_poll.setInterval(50)
        self._note_input_poll.timeout.connect(self._poll_note_input)
        self._note_input_poll.start()

        self._tk = verovio.toolkit()
        self._tk.setOptions({
            "pageHeight": 1800,
            "pageWidth": 1200,
            "scale": 40,
            "breaks": "auto",
            "adjustPageHeight": 1,
            "svgViewBox": 1,
            "svgAdditionalAttribute": list(SVG_ADDITIONAL_ATTRIBUTES),
        })

        self._tk.loadFile(self.mxl_path)
        self._tk.redoLayout()
        self._tk.renderToMIDI()

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
        dlog("events_by_index[0] sample:", self.events_by_index[0][:12])

        dlog("about to _load_page(0)")
        self._load_page(0)
        dlog("_load_page(0) returned")
        
    def _on_toggle_dark(self, checked: bool):
        self._dark_mode = bool(checked)
        self._run_js_safe(f"setDarkMode({str(self._dark_mode).lower()});")


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
        # PyQt6 uses Qt.Key.Key_*
        if event.key() == Qt.Key.Key_Right:
            self._go_next_page()
        elif event.key() == Qt.Key.Key_Left:
            self._go_prev_page()
        else:
            super().keyPressEvent(event)

    def set_beats_visible(self, visible: bool):
        self._beats_visible = bool(visible)
        self._run_js_safe(f"setBeatBoxesVisible({str(self._beats_visible).lower()});")
        self.btnBeats.setText("Hide beats" if self._beats_visible else "Show beats")

    def _discover_pages_by_numbers(self):
        self._page_svgs.clear()
        self._page_abs_indexes.clear()
        self._index_to_page.clear()

        self._page_svgs.extend(self._tk.renderToSVG(p + 1) for p in range(self._page_count))
        self._page_abs_indexes.extend(
            map_page_measures_to_indexes(self._page_svgs, self.measures, dlog=dlog)
        )
        for p, abs_list in enumerate(self._page_abs_indexes):
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

        self._current_page = page

        self._assets.svg_path.write_text(self._page_svgs[page], encoding="utf-8")

        abs_indexes = self._page_abs_indexes[page]
        note_times_map = {i: self.onsets_by_index[i] for i in abs_indexes if i < len(self.onsets_by_index)}
        beat_times_map = {i: self.beats_by_index[i] for i in abs_indexes if i < len(self.beats_by_index)}

        if extract_pitches is not None:
            try:
                _ = extract_pitches(self.xml_path)
            except Exception as e:
                dlog("extract_pitches ERROR:", e)

        note_map = self._mapper.build_note_map_from_verovio(
            page_svg=self._page_svgs[page],
            abs_indexes=abs_indexes,
            beat_times_map=beat_times_map,
        )

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
            self._run_js_safe(f"setPageAndSvg({page}, {json.dumps(self._assets.svg_path.as_uri())});")
            self.set_beats_visible(self._beats_visible)
            self._run_js_safe(f"setDarkMode({str(self._dark_mode).lower()});")
            if self._pending_sec is not None:
                sec = self._pending_sec
                self._pending_sec = None
                self._apply_time(sec)

        self.web.load(QUrl.fromLocalFile(str(self._assets.html_out)))
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
        self._run_js_safe(f"jsSetCursorAbs({int(m_idx)}, {float(t_in)}, {float(dur)})")

        if self._last_logged != (page, m_idx):
            dlog(f"page={page} meas_abs={m_idx} num={m.number} t_in={t_in:.3f}/{dur:.3f}")
            self._last_logged = (page, m_idx)

        self.lbl.setText(
            f"t={sec:7.3f}s  page {page + 1}/{self._page_count}  "
            f"meas {m_idx} (no.{m.number})  t={t_in:0.3f}/{dur:0.3f}s"
        )

    # ------------------------------------------------------------------
    # MIDI -> JS bridge
    # ------------------------------------------------------------------
    def _run_js_safe(self, code: str, label: Optional[str] = None):
        """
        Run JS and (optionally) print the returned value via callback.
        This lets us confirm whether the page received the MIDI event
        and whether the JS handler executed without errors.
        """
        try:
            if label:
                def _cb(res: Any):
                    dlog(f"[JS:{label}] result={res!r}")
                self.web.page().runJavaScript(code, _cb)
            else:
                self.web.page().runJavaScript(code)
        except Exception as e:
            dlog("[JS] runJavaScript ERROR:", e)

 
    @pyqtSlot(int, int, float)
    def _on_midi_note_on(self, pitch: int, velocity: int, timestamp: float):
        # Terminal log: did Python receive NoteOn at all?
        dlog(
            f"[MIDI ON ] pitch={int(pitch)} vel={int(velocity)} ts={float(timestamp):.6f} "
            f"html_ready={self._html_ready} page={self._current_page}"
        )

        # Many sources encode NoteOff as NoteOn with velocity 0.
        if int(velocity) == 0:
            dlog(f"[MIDI ON ] velocity=0 => treating as NoteOff (pitch={int(pitch)})")
            self._on_midi_note_off(int(pitch), float(timestamp))
            return

        # --- LIVE AUDIO: NoteOn ---
        if self._midi_audio_enabled and self._midi_player is not None:
            try:
                vel = max(1, min(int(velocity), 127))
                self._midi_player.fs.noteon(0, int(pitch), vel)
            except Exception as e:
                dlog("[AUDIO] noteon failed:", e)

        # Call JS handler, but return a debug object so we can print it in Python.
        js = f"""
    (() => {{
    const out = {{
        evt: "on",
        pitch: {int(pitch)},
        velocity: {int(velocity)},
        ts: {float(timestamp)},
        haveOn: !!window.onMidiNoteOn,
        haveOff: !!window.onMidiNoteOff,
    }};
    try {{
        if (window.onMidiNoteOn) window.onMidiNoteOn({int(pitch)}, {int(velocity)}, {float(timestamp)});
        out.called = true;
    }} catch (e) {{
        out.err = String(e);
    }}
    try {{
        const s = window.ScoreApp && window.ScoreApp.state;
        if (s && s.midiDown) out.midiDown = Array.from(s.midiDown.values());
        if (s && s.midiActiveIdsByMidi) out.activeKeys = Array.from(s.midiActiveIdsByMidi.keys());
    }} catch (e) {{}}
    try {{
        out.lastMidiEvent = (globalThis && globalThis.__lastMidiEvent) ? globalThis.__lastMidiEvent : null;
    }} catch (e) {{}}
    return out;
    }})()
    """
        self._run_js_safe(js, label="midi_on")


    @pyqtSlot(int, float)
    def _on_midi_note_off(self, pitch: int, timestamp: float):
        # Terminal log: did Python receive NoteOff at all?
        dlog(
            f"[MIDI OFF] pitch={int(pitch)} ts={float(timestamp):.6f} "
            f"html_ready={self._html_ready} page={self._current_page}"
        )

        # --- LIVE AUDIO: NoteOff ---
        if self._midi_audio_enabled and self._midi_player is not None:
            try:
                self._midi_player.fs.noteoff(0, int(pitch))
            except Exception as e:
                dlog("[AUDIO] noteoff failed:", e)

        js = f"""
    (() => {{
    const out = {{
        evt: "off",
        pitch: {int(pitch)},
        ts: {float(timestamp)},
        haveOn: !!window.onMidiNoteOn,
        haveOff: !!window.onMidiNoteOff,
    }};
    try {{
        if (window.onMidiNoteOff) window.onMidiNoteOff({int(pitch)}, {float(timestamp)});
        out.called = true;
    }} catch (e) {{
        out.err = String(e);
    }}
    try {{
        const s = window.ScoreApp && window.ScoreApp.state;
        if (s && s.midiDown) out.midiDown = Array.from(s.midiDown.values());
        if (s && s.midiActiveIdsByMidi) out.activeKeys = Array.from(s.midiActiveIdsByMidi.keys());
    }} catch (e) {{}}
    try {{
        out.lastMidiEvent = (globalThis && globalThis.__lastMidiEvent) ? globalThis.__lastMidiEvent : null;
    }} catch (e) {{}}
    return out;
    }})()
    """
        self._run_js_safe(js, label="midi_off")

    # ------------------------------------------------------------------
    # Synthetic note input (on-screen piano / QWERTY, plan U2): sound only.
    # ------------------------------------------------------------------
    def _poll_note_input(self):
        """Drain pointer/QWERTY note events from the page and sound them."""
        if not self._html_ready:
            return
        try:
            self.web.page().runJavaScript(
                "(window.NoteInput && window.NoteInput.takeEvents)"
                " ? window.NoteInput.takeEvents() : []",
                self._on_note_input_events,
            )
        except Exception as e:
            dlog("[SYNTH-IN] poll failed:", e)

    def _on_note_input_events(self, events):
        if not isinstance(events, list) or not events:
            return
        if not (self._midi_audio_enabled and self._midi_player is not None):
            return  # events are drained regardless, so the queue never backs up
        for ev in events:
            if not isinstance(ev, dict):
                continue
            try:
                midi = int(ev.get("midi", -1))
                if not 0 <= midi <= 127:
                    continue
                if ev.get("type") == "on":
                    vel = max(1, min(int(ev.get("vel", 96)), 127))
                    self._midi_player.fs.noteon(0, midi, vel)
                elif ev.get("type") == "off":
                    self._midi_player.fs.noteoff(0, midi)
            except Exception as e:
                dlog("[SYNTH-IN] sound failed:", e)

    def closeEvent(self, event):
        try:
            if getattr(self, "_midi_service", None) is not None:
                try:
                    self._midi_service.noteOn.disconnect(self._on_midi_note_on)
                except Exception:
                    pass
                try:
                    self._midi_service.noteOff.disconnect(self._on_midi_note_off)
                except Exception:
                    pass
                if getattr(self, "_owns_midi_service", False):
                    try:
                        self._midi_service.shutdown()
                    except Exception:
                        pass
        finally:
            try:
                if getattr(self, "_midi_player", None) is not None:
                    self._midi_player.shutdown()
            except Exception:
                pass

            super().closeEvent(event)

    def _log_svg_pitch_attrs(self, svg: str, limit: int = 20):
        keys = [
            "data-pname", "data-oct", "data-accid",
            "data-pname.ges", "data-oct.ges", "data-accid.ges",
            "pname", "oct", "accid",
            "pname.ges", "oct.ges", "accid.ges",
        ]

        try:
            root = ET.fromstring(svg)
        except Exception as e:
            dlog("[SVG pitch] parse error:", e)
            return

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
            merged = {}
            for el in g.iter():
                merged.update(collect_attrs(el))

            if merged:
                with_pitch += 1
                if dumped < limit:
                    dlog(f"[SVG pitch] id={g.attrib.get('id')} attrs={merged}")
                    dumped += 1

        dlog(f"[SVG pitch] notes_total={total} notes_with_any_pitch_attrs={with_pitch} dumped={dumped}/{limit}")
