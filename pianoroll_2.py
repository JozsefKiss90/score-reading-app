from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsScene,
    QGraphicsView,
    QGraphicsRectItem,
    QWidget,
    QVBoxLayout,
    QLabel,  
)
from PyQt6.QtGui import QColor, QBrush, QPainter, QPen
from PyQt6.QtCore import Qt, QTimer, QElapsedTimer, QRectF
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from music21 import converter, note as m21note, chord as m21chord, tempo
import sys
import os
import platform
import fluidsynth

WHITE_KEYS = [0, 2, 4, 5, 7, 9, 11]
KEY_WIDTH = 20
KEY_HEIGHT = 100
NUM_KEYS = 88
START_MIDI = 21
SCROLL_SPEED = 100.0
FPS = 60
VIEW_HEIGHT = 800
VISUAL_PREROLL_S = VIEW_HEIGHT / SCROLL_SPEED
AUDIO_LATENCY_MS = 0
FOOTER_HEIGHT = 24

# (name, quarters, color, pen_width, dash_pattern or None)
GRID_LEVELS = [
    ("whole",    4.0, QColor(30, 30, 30, 220), 2, None),          # dark solid
    ("half",     2.0, QColor(25, 115, 232, 180), 1, [8, 4]),      # blue dashes
    ("quarter",  1.0, QColor(34, 160,  90, 160), 1, [4, 4]),      # green dashes
    ("eighth",   0.5, QColor(232, 138,  23, 140), 1, [2, 4]),     # orange dashes
]
GRID_MIN_SPACING_PX = 14

# --- Static grid settings ---
GRID_NOTE_VALUE = "quarter"   # one of: "whole", "half", "quarter", "eighth", "sixteenth"
SHOW_MAJOR_WHOLE_LINES = True # draw darker lines every whole note (4 quarters)
GRID_COLOR = QColor(0, 0, 0, 70)
GRID_MAJOR_COLOR = QColor(0, 0, 0, 140)
GRID_MIN_SPACING_PX = 14      # avoid ultra-dense grids


class MidiPlayer:
    def __init__(self, soundfont_path: str | None):
        self.fs = fluidsynth.Synth()
        drv = None
        if platform.system() == "Windows":
            drv = "dsound"
        elif platform.system() == "Darwin":
            drv = "coreaudio"
        else:
            drv = "pulseaudio"
        try:
            self.fs.start(driver=drv)
        except Exception:
            self.fs.start()
        if soundfont_path and os.path.exists(soundfont_path):
            sfid = self.fs.sfload(soundfont_path)
            if sfid == -1:
                raise RuntimeError(f"Failed to load SoundFont: {soundfont_path}")
            self.fs.program_select(0, sfid, 0, 0)
        else:
            print("⚠️ No soundfont provided or not found; Fluidsynth will be silent.")

    def play_note(self, midi_num: int, velocity: int = 100, duration: float = 0.5):
        self.fs.noteon(0, midi_num, velocity)
        QTimer.singleShot(int(duration * 1000), lambda: self.fs.noteoff(0, midi_num))

    def shutdown(self):
        try:
            self.fs.delete()
        except Exception:
            pass

class NoteItem(QGraphicsRectItem):
    __slots__ = ("pitch", "start", "duration", "staff", "bar_height", "spawn_time_music", "initial_y")
    def __init__(self, pitch: int, start: float, duration: float, staff: int, bar_height: float,
                 x: float, initial_y: float):
        super().__init__(QRectF(x, initial_y, KEY_WIDTH, bar_height))
        self.pitch = pitch
        self.start = start
        self.duration = duration
        self.staff = staff
        self.bar_height = bar_height
        self.initial_y = initial_y
        self.spawn_time_music = None
        color = QColor(255, 100, 100, 220) if staff == 1 else QColor(100, 120, 255, 220)
        self.setBrush(QBrush(color))
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setCacheMode(QGraphicsRectItem.CacheMode.DeviceCoordinateCache)
        self.setZValue(0)

    def on_spawn(self, spawn_time_music: float):
        self.spawn_time_music = spawn_time_music
    def update_position(self, music_now: float):
        if self.spawn_time_music is None:
            return
        t = max(0.0, music_now - self.spawn_time_music)
        y = self.initial_y + (t * SCROLL_SPEED)
        rect = self.rect()
        if rect.y() != y:
            rect.moveTop(y)
            self.setRect(rect)

class PianoRoll(QWidget):
    def __init__(self, mxl_path: str, xml_path: str, soundfont: str = "FluidR3_GM.sf2"):
        super().__init__()
        self.setWindowTitle("Dynamic Piano Roll – BPM & Grid")
        self.scene = QGraphicsScene(0, 0, NUM_KEYS * KEY_WIDTH, VIEW_HEIGHT + FOOTER_HEIGHT)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.view.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)
        self.view.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, True)
        self.view.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontSavePainterState, True)
        self.view.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)
        self.scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)

        self.bpm_label = QLabel("BPM: ...")
        self.bpm_label.setStyleSheet("color: white; background-color: rgba(0,0,0,150); padding: 4px;")

        layout = QVBoxLayout(self)
        layout.addWidget(self.bpm_label)
        layout.addWidget(self.view)

        self.clock = QElapsedTimer()
        self.clock.start()
        self.music_time_offset = -VISUAL_PREROLL_S
        self.player = MidiPlayer(soundfont)

        self.all_notes, self.tempo_bpm = self.load_notes_from_mxl(mxl_path, xml_path)
        self.bpm_label.setText(f"BPM: {self.tempo_bpm:.2f}")
        self.all_notes.sort(key=lambda n: n["start"])
        self.spawn_queue = deque(self.all_notes)
        self.active_items: list[NoteItem] = []
        self.draw_keyboard()

        # Build tempo map & set up BPM label/grid
        self.tempo_segments = self._build_tempo_segments(mxl_path)
        self._last_bpm_shown = None

        # Static grid storage
        self._grid_items = []
        self._last_grid_bpm = None

        initial_bpm = self._bpm_at_seconds(0.0)
        self._rebuild_static_grid(initial_bpm)
        self._update_bpm_label(0.0)


        #self.draw_timing_grid()

        self.target_y = self.scene.height() - KEY_HEIGHT - FOOTER_HEIGHT
        self.travel_time = (self.target_y - 0) / SCROLL_SPEED

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(int(1000 / FPS))
        self._draw_vertical_key_grid()

    def _note_value_factor(self, name: str) -> float:
        # factor in *quarters* (whole=4q, half=2q, quarter=1q, etc.)
        return {
            "whole": 4.0, "half": 2.0, "quarter": 1.0,
            "eighth": 0.5, "sixteenth": 0.25
        }.get(name, 1.0)

    def _grid_spacing_px(self, bpm: float) -> float:
        # seconds per quarter = 60/bpm; multiply by chosen note value; convert to pixels
        sec_per_quarter = 60.0 / max(bpm, 1e-6)
        sec_per_grid = sec_per_quarter * self._note_value_factor(GRID_NOTE_VALUE)
        return max(GRID_MIN_SPACING_PX, sec_per_grid * SCROLL_SPEED)

    def _clear_grid(self):
        if not self._grid_items:
            return
        for it in self._grid_items:
            self.scene.removeItem(it)
        self._grid_items.clear()

    def _rebuild_static_grid(self, bpm: float):
        """Draw fixed horizontal lines for multiple note values (whole/half/quarter/eighth)."""
        self._clear_grid()

        width  = self.scene.width()
        base_y = self.scene.height() - KEY_HEIGHT - FOOTER_HEIGHT  # where notes hit the keys

        # to avoid duplicate y’s across layers, keep the best (strongest) style per y
        # key by integer pixel to be robust to float noise
        chosen: dict[int, QPen] = {}

        sec_per_quarter = 60.0 / max(bpm, 1e-6)

        # iterate from coarsest to finest so coarser lines win ties
        for _, quarters, color, pen_w, dash in GRID_LEVELS:  # <-- include dash
            spacing_px = max(GRID_MIN_SPACING_PX, sec_per_quarter * quarters * SCROLL_SPEED)
            if spacing_px < 0.5:
                continue

            y = base_y - spacing_px
            while y > 0:
                key = int(round(y))
                if key not in chosen:
                    pen = QPen(color)
                    pen.setCosmetic(True)
                    pen.setWidth(pen_w)
                    if dash is not None:                    # <-- use dash here
                        pen.setStyle(Qt.PenStyle.CustomDashLine)
                        pen.setDashPattern(dash)
                    chosen[key] = pen
                y -= spacing_px

        # draw from top to bottom for nicer painter batching
        for key in sorted(chosen.keys()):
            y = float(key)
            line = self.scene.addLine(0, y, width, y, chosen[key])
            line.setZValue(-1)
            self._grid_items.append(line)

        self._draw_footer_legend()
        self._draw_pitch_labels(show_sharps=True, show_octave=True)

    def _maybe_update_grid(self, bpm_now: float):
        if self._last_grid_bpm is None or int(round(bpm_now)) != int(round(self._last_grid_bpm)):
            # Rebuild when tempo actually changes (rounded to avoid flicker)
            self._last_grid_bpm = bpm_now
            self._rebuild_static_grid(bpm_now)
        

    def draw_keyboard(self):
        for i in range(NUM_KEYS):
            midi = START_MIDI + i
            pc = midi % 12
            x = i * KEY_WIDTH
            is_white = pc in WHITE_KEYS
            key = QGraphicsRectItem(x, self.scene.height() - KEY_HEIGHT - FOOTER_HEIGHT, KEY_WIDTH, KEY_HEIGHT)
            key.setBrush(QBrush(Qt.GlobalColor.white if is_white else Qt.GlobalColor.black))
            key.setZValue(1)
            key.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, False)
            key.setCacheMode(QGraphicsRectItem.CacheMode.DeviceCoordinateCache)
            self.scene.addItem(key)

    def draw_timing_grid(self):
        if self.tempo_bpm <= 0:
            return
        seconds_per_beat = 60.0 / self.tempo_bpm
        pixels_per_beat = seconds_per_beat * SCROLL_SPEED
        pen = QPen(QColor(200, 200, 200, 80))
        for y in range(0, int(VIEW_HEIGHT + pixels_per_beat * 4), int(pixels_per_beat)):
            line = self.scene.addLine(0, y, NUM_KEYS * KEY_WIDTH, y, pen)
            line.setZValue(-1)

    def load_notes_from_mxl(self, mxl_path: str, xml_path: str):
        tree = ET.parse(xml_path)
        root = tree.getroot()
        staff_map = defaultdict(int)
        for part in root.findall(".//part"):
            for measure in part.findall("measure"):
                measure_num = int(measure.attrib.get("number", "0"))
                for n in measure.findall("note"):
                    staff = int(n.findtext("staff", default="1"))
                    if n.find("rest") is None:
                        pitch_el = n.find("pitch")
                        if pitch_el is not None:
                            step = pitch_el.findtext("step", "?")
                            alter = pitch_el.findtext("alter")
                            octave = pitch_el.findtext("octave", "?")
                            accidental = "#" if alter == "1" else "b" if alter == "-1" else ""
                            pitch_name = f"{step}{accidental}{octave}"
                            duration = n.findtext("duration", "?")
                            staff_map[(measure_num, pitch_name, duration)] = staff
        score = converter.parse(mxl_path)
        bpm = 0.0
        mm = score.metronomeMarkBoundaries()
        if mm:
            bpm = mm[0][2].number if mm[0][2].number else 0.0
        flat_notes = score.flat.notes
        notes = []
        for n in flat_notes:
            if isinstance(n, m21note.Note):
                pitch_name = n.nameWithOctave
                start = float(n.offset)
                duration = float(n.quarterLength)
                measure_num = int(getattr(n, "measureNumber", 0) or 0)
                staff = staff_map.get((measure_num, pitch_name, str(int(duration))), 1)
                notes.append({"pitch": n.pitch.midi, "start": start, "duration": duration, "staff": staff})
            elif isinstance(n, m21chord.Chord):
                for p in n.pitches:
                    pitch_name = p.nameWithOctave
                    start = float(n.offset)
                    duration = float(n.quarterLength)
                    measure_num = int(getattr(n, "measureNumber", 0) or 0)
                    staff = staff_map.get((measure_num, pitch_name, str(int(duration))), 1)
                    notes.append({"pitch": p.midi, "start": start, "duration": duration, "staff": staff})
        return notes, bpm
    
    def _draw_vertical_key_grid(self):
        """Static vertical lines aligned to key boundaries; stronger line at each C (octave start)."""
        # Clear old verticals if we re-enter (optional: track them separately)
        # For simplicity we fold them into _grid_items so they’re cleared with the horizontal grid.
        width = self.scene.width()
        top   = 0.0
        bottom= self.scene.height() - KEY_HEIGHT - FOOTER_HEIGHT  # stop at top of keys

        for i in range(NUM_KEYS + 1):
            x = i * KEY_WIDTH
            midi = START_MIDI + i
            pc = midi % 12
            # Emphasize the C boundaries (octave grid)
            if pc == 0:  # C
                color = QColor(80, 80, 80, 140)
                pen_w = 2
            else:
                color = QColor(120, 120, 120, 60)
                pen_w = 1

            pen = QPen(color)
            pen.setCosmetic(True)
            pen.setWidth(pen_w)

            line = self.scene.addLine(x, top, x, bottom, pen)
            line.setZValue(-2)   # behind horizontal grid (-1) and notes (0)
            self._grid_items.append(line)

    # --- Tempo helpers (piecewise tempo → seconds map) ---
    def _build_tempo_segments(self, mxl_path: str):
        from music21 import tempo as m21tempo, converter
        try:
            score = converter.parse(mxl_path)
            highest_ql = float(score.flat.highestTime)

            # Collect one MetronomeMark per unique offset across the full score
            marks = {}
            for mm in score.recurse().getElementsByClass(m21tempo.MetronomeMark):
                try:
                    off = float(mm.getOffsetBySite(score))
                except Exception:
                    off = float(mm.offset or 0.0)
                qpm = float(mm.getQuarterBPM() or 60.0)
                key = round(off, 6)
                if key not in marks:
                    marks[key] = qpm

            items = sorted(marks.items(), key=lambda t: t[0])
            if not items:
                items = [(0.0, 60.0)]
            if items[0][0] > 0.0:
                items.insert(0, (0.0, items[0][1]))

            # Build segments with absolute seconds
            segs = []
            t_sec = 0.0
            for i, (off, bpm) in enumerate(items):
                next_off = items[i + 1][0] if i + 1 < len(items) else highest_ql
                dur_q = max(0.0, (next_off - off))
                end_sec = t_sec + (dur_q * 60.0 / bpm)
                segs.append({
                    "start_ql": off, "end_ql": next_off,
                    "bpm": bpm, "start_sec": t_sec, "end_sec": end_sec
                })
                t_sec = end_sec
            return segs
        except Exception as e:
            print("Tempo parse error:", e)
            return [{"start_ql": 0.0, "end_ql": 1e9, "bpm": 60.0, "start_sec": 0.0, "end_sec": 1e9}]

    def _bpm_at_seconds(self, sec: float) -> float:
        for s in self.tempo_segments:
            if s["start_sec"] <= sec < s["end_sec"]:
                return s["bpm"]
        return self.tempo_segments[-1]["bpm"] if self.tempo_segments else 60.0

    def _spawn_due_notes(self, music_now: float):
        while self.spawn_queue:
            nxt = self.spawn_queue[0]
            bar_height = nxt["duration"] * SCROLL_SPEED
            spawn_time_music = nxt["start"] - self.travel_time
            if music_now + 1e-6 < spawn_time_music:
                break
            note_dict = self.spawn_queue.popleft()
            x = (note_dict["pitch"] - START_MIDI) * KEY_WIDTH
            initial_y = -bar_height
            item = NoteItem(note_dict["pitch"], note_dict["start"], note_dict["duration"], note_dict["staff"],
                            bar_height, x, initial_y)
            self.scene.addItem(item)
            item.on_spawn(spawn_time_music)
            self.active_items.append(item)
            delay_ms = max(0, int((note_dict["start"] - music_now) * 1000) + AUDIO_LATENCY_MS)
            QTimer.singleShot(delay_ms, lambda p=note_dict["pitch"], d=note_dict["duration"]: self.player.play_note(p, duration=d))

    def _collect_garbage(self):
        cutoff_y = self.scene.height() - FOOTER_HEIGHT  # bottom of the keyboard
        to_remove = [it for it in self.active_items if it.rect().y() > cutoff_y]
        if to_remove:
            for it in to_remove:
                self.scene.removeItem(it)
            self.active_items = [it for it in self.active_items if it not in to_remove]


    def tick(self):
        wall_s = self.clock.elapsed() / 1000.0
        music_now = wall_s + self.music_time_offset
        self._update_bpm_label(music_now)
        self._spawn_due_notes(music_now)
        for item in self.active_items:
            item.update_position(music_now)
        self._collect_garbage()

    def closeEvent(self, event):
        self.player.shutdown()
        super().closeEvent(event)

    def _update_bpm_label(self, music_now_sec: float):
        bpm = round(self._bpm_at_seconds(music_now_sec))
        if bpm != self._last_bpm_shown:
            self._last_bpm_shown = bpm
            self.bpm_label.setText(f"♪ {int(bpm)} BPM")
            # keep grid spacing honest with current tempo
            self._maybe_update_grid(float(bpm))

    def _draw_footer_legend(self):
        """Draws small samples and labels for Whole / Half grid styles under the keyboard."""
        # Remove prior legend items if we rebuild
        # (We reuse _grid_items for simplicity so cleanup happens with grid rebuild.)
        y0 = self.scene.height() - FOOTER_HEIGHT + 5
        x  = 8
        spacing = 110

        def sample(label, color, dash, pen_w):
            nonlocal x
            pen = QPen(color); pen.setCosmetic(True); pen.setWidth(pen_w)
            if dash is not None:
                pen.setStyle(Qt.PenStyle.CustomDashLine)
                pen.setDashPattern(dash)
            # sample line
            line = self.scene.addLine(x, y0, x + 60, y0, pen)
            line.setZValue(2)
            self._grid_items.append(line)
            # text label
            txt = self.scene.addText(label)
            txt.setDefaultTextColor(QColor(40, 40, 40))
            txt.setPos(x + 66, y0 - 10)
            txt.setZValue(2)
            self._grid_items.append(txt)
            x += spacing

        # Pull styles from your GRID_LEVELS so legend always matches
        styles = {name: (col, dash if len(t) == 5 else None, w)
                for t in GRID_LEVELS
                for (name, quarters, col, w, *rest) in [t]
                for dash in ([rest[0]] if rest else [None])}
        '''
        # Safeguard if using the 4-tuple GRID_LEVELS (no dashes):
        def get(name, fallback):
            return styles.get(name, fallback)
        # Whole
        c, d, w = get("whole", (QColor(30,30,30,220), None, 2))
        sample("Whole", c, d, w)
        # Half
        c, d, w = get("half", (QColor(25,115,232,180), [8,4], 1))
        sample("Half",  c, d, w)
        '''

    def _draw_pitch_labels(self, show_sharps=True, show_octave=True):
        """
        Draw pitch names in the footer under each key.
        White keys get labels centered; optional small labels for black keys.
        """
        from PyQt6.QtWidgets import QGraphicsSimpleTextItem

        # remove previous labels (reuse _grid_items so they're cleared on rebuild)
        base_y = self.scene.height() - FOOTER_HEIGHT
        text_color = QColor(40, 40, 40)

        names = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]

        for i in range(NUM_KEYS):
            midi = START_MIDI + i
            pc = midi % 12
            octave = (midi // 12) - 1
            is_white = pc in WHITE_KEYS

            # choose which keys to label:
            if is_white:
                label = names[pc]
                if show_octave and names[pc] == "C":
                    label += str(octave)          # C’s octave marker is most useful
                elif show_octave and names[pc] == "A" and octave == 0:
                    label += str(octave)          # A0 at the far left

                item = QGraphicsSimpleTextItem(label)
                item.setBrush(text_color)
                x = i * KEY_WIDTH + KEY_WIDTH * 0.5 - item.boundingRect().width() * 0.5
                y = base_y + (FOOTER_HEIGHT - item.boundingRect().height()) * 0.5
                item.setPos(x, y)
                item.setZValue(3)
                self._grid_items.append(item)
                self.scene.addItem(item)
            else:
                if not show_sharps:
                    continue
                # tiny sharp labels for black keys (optional)
                label = names[pc]
                item = QGraphicsSimpleTextItem(label)
                item.setBrush(QColor(80, 80, 80))
                item.setScale(0.8)
                x = i * KEY_WIDTH + KEY_WIDTH * 0.5 - (item.boundingRect().width()*0.8) * 0.5
                y = base_y + 2
                item.setPos(x, y)
                item.setZValue(3)
                self._grid_items.append(item)
                self.scene.addItem(item)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    mxl_file = "Prelude_No._15_in_D_flat_major_Op._28_The_Raindrop_Prelude.mxl"
    xml_path = "mxl_extracted\lg-4991167500045005.xml"
    if not os.path.exists(mxl_file):
        print("MXL file not found.")
        sys.exit(1)
    window = PianoRoll(mxl_file, xml_path, soundfont="FluidR3_GM.sf2")
    window.resize(NUM_KEYS * KEY_WIDTH, VIEW_HEIGHT)
    window.show()
    sys.exit(app.exec())
