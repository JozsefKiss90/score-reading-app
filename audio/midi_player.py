
from __future__ import annotations
import os, platform
from PyQt6.QtCore import QTimer
import fluidsynth

class MidiPlayer:
    def __init__(self, soundfont_path: str | None):
        # Increase default gain from 0.2 to 2.0 (10× louder)
        self.fs = fluidsynth.Synth(gain=2.0, samplerate=44100)

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

            # Maximize channel volume + expression
            self.fs.cc(0, 7, 127)   # CC7 Volume
            self.fs.cc(0, 11, 127)  # CC11 Expression
        else:
            print("⚠️ No soundfont provided or not found; Fluidsynth will be silent.")

    def play_note(self, midi_num: int, velocity: int = 100, duration: float = 0.5):
        vel = max(1, min(int(velocity), 127))  # clamp
        self.fs.noteon(0, midi_num, vel)
        QTimer.singleShot(int(duration * 1000), lambda: self.fs.noteoff(0, midi_num))

    def shutdown(self):
        try:
            self.fs.delete()
        except Exception:
            pass
