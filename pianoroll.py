from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView, QGraphicsRectItem, QWidget, QVBoxLayout 
from PyQt6.QtGui import QColor, QBrush
from PyQt6.QtCore import Qt, QTimer, QRectF, QTime, QElapsedTimer
import xml.etree.ElementTree as ET
from collections import defaultdict
from music21 import converter, note, chord
import sys
import os
from music21 import converter, note, chord
import fluidsynth

WHITE_KEYS = [0, 2, 4, 5, 7, 9, 11]
KEY_WIDTH = 20
KEY_HEIGHT = 100
NUM_KEYS = 88
START_MIDI = 21
NOTE_HEIGHT = 10
SCROLL_SPEED = 100  # pixels per second

class MidiPlayer:
    def __init__(self, soundfont_path):
        self.fs = fluidsynth.Synth()
        self.fs.start(driver="dsound")  # or "directsound" or ""
        sfid = self.fs.sfload(soundfont_path)
        if sfid == -1:
            raise RuntimeError(f"❌ Failed to load SoundFont: {soundfont_path}")
        else:
            print(f"✅ SoundFont loaded with ID {sfid}")

        self.fs.program_select(0, sfid, 0, 0)
        print("🎹 Synth ready.")

    def play_note(self, midi_num, velocity=100, duration=0.5):
        self.fs.noteon(0, midi_num, velocity)
        QTimer.singleShot(int(duration * 1000), lambda: self.fs.noteoff(0, midi_num))

    def shutdown(self):
        self.fs.delete()


class PianoRoll(QWidget):
    def __init__(self, mxl_path, xml_path):
        super().__init__()
        self.setWindowTitle("Dynamic Piano Roll")
        self.view = QGraphicsView()
        self.scene = QGraphicsScene(0, 0, NUM_KEYS * KEY_WIDTH, 800)
        self.view.setScene(self.scene)
        self.elapsed_time = 0  # seconds
        self.active_notes = []
        self.player = MidiPlayer("FluidR3_GM.sf2")
        self.clock = QElapsedTimer()
        self.clock.start()

        layout = QVBoxLayout()
        layout.addWidget(self.view)
        self.setLayout(layout)

        self.draw_keyboard()
        self.notes = self.load_notes_from_mxl(mxl_path, xml_path)
        self.start_animation()

    def closeEvent(self, event):
        self.player.shutdown()
        super().closeEvent(event)

    def draw_keyboard(self):
        for i in range(NUM_KEYS):
            midi = START_MIDI + i
            note = midi % 12
            x = i * KEY_WIDTH
            is_white = note in WHITE_KEYS
            key = QGraphicsRectItem(x, self.scene.height() - KEY_HEIGHT, KEY_WIDTH, KEY_HEIGHT)
            key.setBrush(QBrush(Qt.GlobalColor.white if is_white else Qt.GlobalColor.black))
            key.setZValue(1)
            self.scene.addItem(key)

    def load_notes_from_mxl(self, mxl_path, xml_path):
        # --- Step 1: Parse XML to get staff info ---
        tree = ET.parse(xml_path)
        root = tree.getroot()

        staff_map = defaultdict(int)  # (measure_num, pitch_name, duration) → staff

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

        # --- Step 2: Flatten notes with music21 for offsets ---
        score = converter.parse(mxl_path)
        flat_notes = score.flat.notes
        notes = []

        for n in flat_notes:
            if isinstance(n, note.Note):
                pitch_name = n.nameWithOctave
                start = float(n.offset)
                duration = float(n.quarterLength)
                measure_num = int(n.measureNumber) if hasattr(n, "measureNumber") else 0

                staff = staff_map.get((measure_num, pitch_name, str(int(duration))), 1)

                notes.append({
                    "pitch": n.pitch.midi,
                    "start": start,
                    "duration": duration,
                    "staff": staff,
                    "rendered": False
                })
                print(f"Note: pitch={n.pitch.midi}, start={start}, duration={duration}, staff={staff}")

            elif isinstance(n, chord.Chord):
                for p in n.pitches:
                    pitch_name = p.nameWithOctave
                    start = float(n.offset)
                    duration = float(n.quarterLength)
                    measure_num = int(n.measureNumber) if hasattr(n, "measureNumber") else 0

                    staff = staff_map.get((measure_num, pitch_name, str(int(duration))), 1)

                    notes.append({
                        "pitch": p.midi,
                        "start": start,
                        "duration": duration,
                        "staff": staff,
                        "rendered": False
                    })
                    print(f"Chord Note: pitch={p.midi}, start={start}, duration={duration}, staff={staff}")

        print(f"[INFO] Total notes loaded: {len(notes)}")
        return notes

    def start_animation(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_scene)
        self.timer.start(30)  # ~33 FPS

    def update_scene(self):
        self.elapsed_time = self.clock.elapsed() / 1000.0  # convert ms to seconds

        for note in self.notes:
            if not note["rendered"] and note["start"] <= self.elapsed_time:
                self.spawn_note(note)

        for bar in self.active_notes:
            bar.moveBy(0, SCROLL_SPEED * 0.03)
            if bar.y() > self.scene.height():
                self.scene.removeItem(bar)
                self.active_notes.remove(bar)

    def spawn_note(self, note):
        x = (note["pitch"] - START_MIDI) * KEY_WIDTH
        bar_height = note["duration"] * SCROLL_SPEED

        # Bar starts above screen with bottom at y=0
        initial_y = -bar_height
        bar = QGraphicsRectItem(x, initial_y, KEY_WIDTH, bar_height)
        color = QColor(255, 100, 100, 200) if note["staff"] == 1 else QColor(100, 100, 255, 200)
        bar.setBrush(color)
        bar.setZValue(0)
        self.scene.addItem(bar)
        self.active_notes.append(bar)
        note["rendered"] = True

        # Compute exact y-coordinate where the bar's bottom meets the keyboard
        target_y = self.scene.height() - KEY_HEIGHT

        # Compute distance to travel (from bar's bottom = 0 to target_y)
        distance = target_y - 0

        # Compute exact time (in ms) it will take to fall that far
        time_to_key = distance / SCROLL_SPEED
        delay_ms = time_to_key * 1000  # precise float

        # Use QTimer with float conversion precision
        QTimer.singleShot(round(delay_ms), lambda: self.player.play_note(note["pitch"], duration=note["duration"]))


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Make sure this matches your real .mxl file path
    mxl_file = "Gymnopdie_No._1__Satie.mxl"
    xml_path="Gymnopdie\score.xml"
    if not os.path.exists(mxl_file):
        print("MXL file not found.")
        sys.exit(1)

    window = PianoRoll(mxl_file,xml_path)
    window.resize(NUM_KEYS * KEY_WIDTH, 800)
    window.show()
    sys.exit(app.exec())