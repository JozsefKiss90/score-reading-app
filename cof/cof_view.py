from __future__ import annotations
import time
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QUrl, pyqtSlot
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtWebEngineWidgets import QWebEngineView

from audio.midi_service import MidiService  # adjust import to your package layout

# add these imports near the top of cof_view.py
try:
    from audio.midi_player import MidiPlayer
except Exception:
    MidiPlayer = None

try:
    from config import DEFAULT_SF2
except Exception:
    DEFAULT_SF2 = None

def dlog(*args):
    print("[CofView]", *args, flush=True)


class CofView(QWidget):
    def __init__(self, html_path: str, parent=None, midi_service: Optional[MidiService] = None):
        super().__init__(parent)

        self._html_ready = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        top.setContentsMargins(6, 6, 6, 6)
        self.lbl = QLabel("Circle of Fifths")
        top.addWidget(self.lbl)
        top.addStretch(1)
        layout.addLayout(top)

        self.web = QWebEngineView(self)
        self.web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        layout.addWidget(self.web, 1)

        # MIDI service (share one service if caller provides it)
        self._midi_service = midi_service or MidiService(self)

        # Connect MIDI -> JS (same idea as ScoreViewBeats)
        self._midi_service.noteOn.connect(self._on_midi_note_on)
        self._midi_service.noteOff.connect(self._on_midi_note_off)

        # Load COF html
        p = Path(html_path).resolve()
        if not p.exists():
            raise FileNotFoundError(str(p))

        def on_loaded(ok: bool):
            self._html_ready = bool(ok)
            dlog("loadFinished", ok)

        self.web.loadFinished.connect(on_loaded)
        self.web.load(QUrl.fromLocalFile(str(p)))
                # --- Live audio (optional) ---
        self._midi_player = None
        self._midi_audio_enabled = True

        if MidiPlayer is not None:
            try:
                # IMPORTANT: if DEFAULT_SF2 is None/invalid, MidiPlayer will be silent (it prints a warning).
                self._midi_player = MidiPlayer(DEFAULT_SF2)
                dlog(f"[AUDIO] MidiPlayer ready. soundfont={DEFAULT_SF2!r}")
            except Exception as e:
                dlog("[AUDIO] MidiPlayer init failed:", e)
                self._midi_player = None
        else:
            dlog("[AUDIO] MidiPlayer import failed; no in-app sound.")

    def _run_js_safe(self, code: str):
        try:
            self.web.page().runJavaScript(code)
        except Exception as e:
            dlog("runJavaScript ERROR:", e)

    @pyqtSlot(int, int, float)
    def _on_midi_note_on(self, pitch: int, velocity: int, timestamp: float):
        if not self._html_ready:
            return

        # MIDI note-off encoded as note-on velocity 0
        if int(velocity) == 0:
            self._on_midi_note_off(int(pitch), float(timestamp))
            return
                # --- LIVE AUDIO: NoteOn ---
        if self._midi_audio_enabled and self._midi_player is not None:
            try:
                vel = max(1, min(int(velocity), 127))
                self._midi_player.fs.noteon(0, int(pitch), vel)
            except Exception as e:
                dlog("[AUDIO] noteon failed:", e)

        js = f"window.onMidiNoteOn && window.onMidiNoteOn({int(pitch)}, {int(velocity)}, {float(timestamp)});"
        self._run_js_safe(js)

    @pyqtSlot(int, float)
    def _on_midi_note_off(self, pitch: int, timestamp: float):
        if not self._html_ready:
            return
                # --- LIVE AUDIO: NoteOff ---
        if self._midi_audio_enabled and self._midi_player is not None:
            try:
                self._midi_player.fs.noteoff(0, int(pitch))
            except Exception as e:
                dlog("[AUDIO] noteoff failed:", e)

        js = f"window.onMidiNoteOff && window.onMidiNoteOff({int(pitch)}, {float(timestamp)});"
        self._run_js_safe(js)

    def closeEvent(self, event):
        try:
            if self._midi_service is not None:
                try: self._midi_service.noteOn.disconnect(self._on_midi_note_on)
                except Exception: pass
                try: self._midi_service.noteOff.disconnect(self._on_midi_note_off)
                except Exception: pass
        finally:
            super().closeEvent(event)
