from __future__ import annotations

from collections import deque
from PyQt6.QtWidgets import ( 
    QWidget, QVBoxLayout, QLabel, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QDoubleSpinBox, QPushButton
)
from PyQt6.QtGui import QPainter
    # If you prefer icons or shortcuts later, we can add them easily.
from PyQt6.QtCore import Qt, QTimer, QElapsedTimer, pyqtSignal

from config import (
    NUM_KEYS, KEY_WIDTH, VIEW_HEIGHT, FOOTER_HEIGHT, FPS, SCROLL_SPEED,
    START_MIDI, AUDIO_LATENCY_MS, VISUAL_PREROLL_S, DEFAULT_SF2
)
from audio.midi_player import MidiPlayer
from model.score_loader import load_notes_from_mxl, build_tempo_segments, bpm_at_seconds, ql_to_seconds, ql_duration_to_seconds
from .keyboard import draw_keyboard
from .grid_layers import rebuild_static_grid, draw_vertical_key_grid
from .note_item import NoteItem
from .score_view import ScoreView

class PianoRoll(QWidget):
    """
    Piano roll with speed control (0.25×–2.00×) + transport:
    Pause/Resume, Forward, Rewind, Stop, Restart.

    - Music time = wall_time * playback_rate + offset
    - Audio fires just-in-time each frame -> speed/seek changes stay in sync.
    """
    musicTimeChanged = pyqtSignal(float)

    def __init__(self, mxl_path: str, xml_path: str, soundfont: str = DEFAULT_SF2):
        super().__init__()
        self.setWindowTitle("Piano Roll — Transport + Speed")

        # Scene & view
        self.scene = QGraphicsScene(0, 0, NUM_KEYS * KEY_WIDTH, VIEW_HEIGHT + FOOTER_HEIGHT)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.view.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)
        self.view.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, True)
        self.view.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontSavePainterState, True)
        self.view.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)
        self.scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)

        # Status / BPM
        self.bpm_label = QLabel("BPM: …")
        self.bpm_label.setStyleSheet("color: white; background-color: rgba(0,0,0,150); padding: 4px;")

        # ------- Transport controls -------
        transport = QHBoxLayout()
        self.btn_rewind = QPushButton("⟲ Rewind")
        self.btn_stop = QPushButton("■ Stop")
        self.btn_restart = QPushButton("↻ Restart")
        self.btn_forward = QPushButton("Forward ⟳")
        self.btn_pause_resume = QPushButton("Pause")

        transport.addWidget(self.btn_rewind)
        transport.addWidget(self.btn_stop)
        transport.addWidget(self.btn_restart)
        transport.addWidget(self.btn_forward)
        transport.addStretch(1)
        transport.addWidget(self.btn_pause_resume)

        # ------- Speed control -------
        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel("Speed"))
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.25, 2.00)
        self.speed_spin.setSingleStep(0.05)
        self.speed_spin.setDecimals(2)
        self.speed_spin.setValue(1.00)
        self.speed_spin.setSuffix("×")
        speed_row.addWidget(self.speed_spin)
        speed_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self.bpm_label)
        layout.addLayout(transport)
        layout.addLayout(speed_row)
        layout.addWidget(self.view)

        # Timing state
        self.clock = QElapsedTimer()
        self.clock.start()
        self.music_time_offset = -VISUAL_PREROLL_S
        self.playback_rate = 1.0   # 0.0 means paused (transport only; speed spin stays at last non-zero)
        self._pre_pause_rate = 1.0
        self.step_seconds = 5.0    # Forward/Rewind amount (music seconds)

        # Audio
        self.player = MidiPlayer(soundfont)

        # Notes / data
        self.all_notes, self.tempo_bpm = load_notes_from_mxl(mxl_path, xml_path)
        self.bpm_label.setText(f"BPM: {self.tempo_bpm:.2f}")

        self.active_items: list[NoteItem] = []

        draw_keyboard(self.scene)

        # Tempo segments for BPM label & grid spacing
        self.tempo_segments = build_tempo_segments(mxl_path)
        self._last_bpm_shown = None
        self.total_duration_sec = self.tempo_segments[-1]["end_sec"] if self.tempo_segments else 0.0  # total piece length

        notes_sec = []
        for n in self.all_notes:
            start_sec = ql_to_seconds(self.tempo_segments, n["start"])
            dur_sec   = ql_duration_to_seconds(self.tempo_segments, n["start"], n["duration"])
            notes_sec.append({**n, "start": start_sec, "duration": dur_sec})
        self.all_notes = sorted(notes_sec, key=lambda x: x["start"])
        self.spawn_queue = deque(self.all_notes)
        self.audio_queue = deque(self.all_notes)
                # Grid
        self._grid_items = []
        self._last_grid_bpm = None
        initial_bpm = bpm_at_seconds(self.tempo_segments, 0.0)
        rebuild_static_grid(self.scene, self._grid_items, initial_bpm)
        self._update_bpm_label(0.0)
        draw_vertical_key_grid(self.scene, self._grid_items)

        # Travel time from spawn to key bed (in *music* seconds)
        self.target_y = self.scene.height() - FOOTER_HEIGHT - 100
        self.travel_time = (self.target_y - 0) / SCROLL_SPEED

        # Frame timer
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(int(1000 / FPS))

        # Wire controls
        self.speed_spin.valueChanged.connect(self._on_speed_changed)
        self.btn_pause_resume.clicked.connect(self._on_toggle_pause)
        self.btn_rewind.clicked.connect(lambda: self._seek_by(-self.step_seconds))
        self.btn_forward.clicked.connect(lambda: self._seek_by(+self.step_seconds))
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_restart.clicked.connect(self._on_restart)

    # -------- speed / time mapping --------
    def current_music_time(self) -> float:
        wall_s = self.clock.elapsed() / 1000.0
        return wall_s * self.playback_rate + self.music_time_offset

    def _set_playback_rate(self, new_rate: float):
        """Change speed while keeping music time continuous. Allows 0.0 for Pause."""
        wall_s = self.clock.elapsed() / 1000.0
        music_now = self.current_music_time()
        # clamp (except allow exact 0 for pause)
        if new_rate == 0.0:
            rate = 0.0
        else:
            rate = min(2.0, max(0.25, float(new_rate)))
        self.playback_rate = rate
        self.music_time_offset = music_now - wall_s * self.playback_rate
        self._update_pause_btn()
        # Don't push 0 into the speed spin while paused; let it keep the last non-zero
        if self.playback_rate != 0.0 and abs(self.speed_spin.value() - self.playback_rate) > 1e-9:
            self.speed_spin.blockSignals(True)
            self.speed_spin.setValue(self.playback_rate)
            self.speed_spin.blockSignals(False)
        self._update_bpm_label(self.current_music_time())

    def _on_speed_changed(self, new_rate: float):
        # If paused, store the desired rate to resume with, but stay paused.
        if self.playback_rate == 0.0:
            self._pre_pause_rate = float(new_rate)
            self._update_bpm_label(self.current_music_time())
            return
        self._set_playback_rate(new_rate)

    # -------- transport actions --------
    def _on_toggle_pause(self):
        if self.playback_rate == 0.0:
            self._set_playback_rate(self._pre_pause_rate or 1.0)
        else:
            self._pre_pause_rate = self.playback_rate
            self._set_playback_rate(0.0)

    def _on_stop(self):
        # Go to start and stay paused
        self._seek_to(-VISUAL_PREROLL_S)
        self._pre_pause_rate = max(0.25, float(self.speed_spin.value()))
        self._set_playback_rate(0.0)

    def _on_restart(self):
        # Stop then resume at last chosen speed (or 1.0)
        self._on_stop()
        self._set_playback_rate(self._pre_pause_rate or 1.0)

    def _seek_by(self, delta_sec: float):
        self._seek_to(self.current_music_time() + float(delta_sec))

    def _seek_to(self, new_music_now: float):
        # Clamp to earliest preroll (you can extend this if you want an upper clamp)
        new_music_now = max(-VISUAL_PREROLL_S, float(new_music_now))

        # Set new offset keeping the current rate
        wall_s = self.clock.elapsed() / 1000.0
        self.music_time_offset = new_music_now - wall_s * self.playback_rate

        # Reset visuals
        for it in self.active_items:
            self.scene.removeItem(it)
        self.active_items.clear()

        # Rebuild queues so we don't play past notes after a seek
        eps = 1e-6
        self.audio_queue = deque(n for n in self.all_notes if n["start"] >= new_music_now - eps)
        self.spawn_queue = deque(
            n for n in self.all_notes
            if (n["start"] - self.travel_time) >= new_music_now - eps
        )

        self._update_bpm_label(new_music_now)

    def _update_pause_btn(self):
        self.btn_pause_resume.setText("Resume" if self.playback_rate == 0.0 else "Pause")

    # -------- visuals --------
    def _maybe_update_grid(self, bpm_now: float):
        if self._last_grid_bpm is None or int(round(bpm_now)) != int(round(self._last_grid_bpm)):
            self._last_grid_bpm = bpm_now
            rebuild_static_grid(self.scene, self._grid_items, bpm_now)

    def _spawn_due_notes(self, music_now: float):
        """Spawn graphics early so bars arrive on the keys at note start."""
        while self.spawn_queue:
            nxt = self.spawn_queue[0]
            bar_height = nxt["duration"] * SCROLL_SPEED
            spawn_time_music = nxt["start"] - self.travel_time
            if music_now + 1e-6 < spawn_time_music:
                break
            note_dict = self.spawn_queue.popleft()
            x = (note_dict["pitch"] - START_MIDI) * KEY_WIDTH
            initial_y = -bar_height
            item = NoteItem(
                note_dict["pitch"], note_dict["start"], note_dict["duration"], note_dict["staff"],
                bar_height, x, initial_y
            )
            self.scene.addItem(item)
            item.on_spawn(spawn_time_music)
            self.active_items.append(item)

    def _collect_garbage(self):
        cutoff_y = self.scene.height()
        to_remove = [it for it in self.active_items if it.rect().y() > cutoff_y]
        if to_remove:
            for it in to_remove:
                self.scene.removeItem(it)
            self.active_items = [it for it in self.active_items if it not in to_remove]

    # -------- audio (just-in-time, adaptive to speed & seeks) --------
    def _trigger_audio_onsets(self, music_now: float):
        """
        Fire notes exactly when music time reaches their start, adjusted for AUDIO_LATENCY_MS.
        If paused, do nothing. After a seek, past notes are skipped because audio_queue is rebuilt.
        """
        if self.playback_rate == 0.0:
            return
        audio_now = music_now + (AUDIO_LATENCY_MS / 1000.0)
        while self.audio_queue and self.audio_queue[0]["start"] <= audio_now + 1e-6:
            n = self.audio_queue.popleft()
            # duration in wall seconds so it sounds right at slower/faster rates
            dur_wall = max(0.0, n["duration"] / max(self.playback_rate, 1e-6))
            self.player.play_note(n["pitch"], duration=dur_wall)

    # -------- frame --------
    def _update_bpm_label(self, music_now_sec: float):
        base_bpm = round(bpm_at_seconds(self.tempo_segments, music_now_sec))
        if self._last_bpm_shown != base_bpm:
            self._last_bpm_shown = base_bpm
            self.bpm_label.setText(f"♪ {int(base_bpm)} BPM")
            self._maybe_update_grid(float(base_bpm))

    def tick(self):
        music_now = self.current_music_time()
        self._update_bpm_label(music_now)

        # AUDIO first to minimize perceived latency
        self._trigger_audio_onsets(music_now)

        # VISUALS
        self._spawn_due_notes(music_now)
        for item in self.active_items:
            item.update_position(music_now)

        self.musicTimeChanged.emit(music_now)
        self._collect_garbage()

    def closeEvent(self, event):
        self.player.shutdown()
        super().closeEvent(event)
