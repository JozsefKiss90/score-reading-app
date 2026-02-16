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

            # Debug: show every incoming MIDI message
            try:
                note = getattr(msg, "note", None)
                vel = getattr(msg, "velocity", None)
                print(f"[MidiInput] RX type={msg.type} note={note} vel={vel} raw={msg!r}", flush=True)
            except Exception:
                print(f"[MidiInput] RX raw={msg!r}", flush=True)

            if msg.type == "note_on":
                # NoteOn with velocity 0 is a NoteOff in MIDI.
                if int(getattr(msg, "velocity", 0)) == 0:
                    print(f"[MidiInput] EMIT noteOff note={int(msg.note)} ts={ts:.6f} (note_on vel=0)", flush=True)
                    self.noteOff.emit(int(msg.note), ts)
                else:
                    print(f"[MidiInput] EMIT noteOn  note={int(msg.note)} vel={int(msg.velocity)} ts={ts:.6f}", flush=True)
                    self.noteOn.emit(int(msg.note), int(msg.velocity), ts)

            elif msg.type == "note_off":
                # IMPORTANT: note_off often has non-zero release velocity; still a NoteOff.
                print(f"[MidiInput] EMIT noteOff note={int(msg.note)} ts={ts:.6f} (note_off)", flush=True)
                self.noteOff.emit(int(msg.note), ts)

            elif msg.type == "control_change":
                print(f"[MidiInput] EMIT control cc={int(msg.control)} val={int(msg.value)} ts={ts:.6f}", flush=True)
                self.control.emit(int(msg.control), int(msg.value), ts)

    def close(self):
        if self._midiin:
            self._midiin.close()
            self._midiin = None
        if hasattr(self, "_timer"):
            self._timer.stop()
