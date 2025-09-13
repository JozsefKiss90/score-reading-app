# midi_input.py
from __future__ import annotations
import time
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
import mido

class MidiInput(QObject):
    noteOn = pyqtSignal(int, int, float)
    noteOff = pyqtSignal(int, float)
    control = pyqtSignal(int, int, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._midiin = None
        self._port_name = None

        try:
            ports = mido.get_input_names()
            print("Available MIDI input ports:", ports)

            target = None
            # 1) Prefer loopMIDI
            for name in ports:
                if "loopMIDI" in name:
                    target = name
                    break
            # 2) Else prefer SE61 0
            if not target:
                for name in ports:
                    if "SE61 0" in name:
                        target = name
                        break
            # 3) Else first available
            if not target and ports:
                target = ports[0]

            if target:
                print("Opening:", target)
                self._midiin = mido.open_input(target)
                self._port_name = target
                print(f"🎹 Listening on: {self._port_name}")
            else:
                print("⚠️ No usable MIDI ports found")

        except Exception as e:
            print("⚠️ Could not open MIDI input:", e)
            return

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(5)

    def _poll(self):
        if not self._midiin:
            return
        for msg in self._midiin.iter_pending():
            ts = time.time()
            if msg.type == "note_on" and msg.velocity > 0:
                self.noteOn.emit(msg.note, msg.velocity, ts)
            elif msg.type in ("note_off", "note_on") and msg.velocity == 0:
                self.noteOff.emit(msg.note, ts)
            elif msg.type == "control_change":
                self.control.emit(msg.control, msg.value, ts)

    def close(self):
        if self._midiin:
            self._midiin.close()
            self._midiin = None
        if hasattr(self, "_timer"):
            self._timer.stop()
