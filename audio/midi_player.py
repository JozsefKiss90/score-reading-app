# midi_player.py
from __future__ import annotations
import os, platform
from PyQt6.QtCore import QTimer
import fluidsynth

class MidiPlayer:
    def __init__(self, soundfont_path: str | None):
        # Lower, safer gain to prevent clipping / harshness
        self.fs = fluidsynth.Synth(gain=0.9, samplerate=44100)

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

            # Healthy channel levels
            self.fs.cc(0, 7, 110)    # CC7 Volume
            self.fs.cc(0, 11, 127)   # CC11 Expression

            # Mild ambience via GM sends (portable across pyfluidsynth versions)
            self.fs.cc(0, 91, 56)    # CC91 Reverb send (0–127). Try 48–72 range.
            self.fs.cc(0, 93, 0)     # CC93 Chorus send OFF (avoid metallic artifacts)

            # If available, you can also gently shape the reverb algorithm (optional)
            if hasattr(self.fs, "set_reverb"):
                # roomsize, damping, width, level — keep these modest
                self.fs.set_reverb(0.6, 0.3, 0.5, 0.35)
            
             # very subtle chorus; many SF2 pianos don’t need this
            if hasattr(self.fs, "set_chorus"):
                self.fs.set_chorus(3, 0.2, 0.25, 1.2, 0)  # few voices, low level/speed/depth
                self.fs.cc(0, 93, 20)  # tiny chorus send

        else:
            print("⚠️ No soundfont provided or not found; Fluidsynth will be silent.")

    def play_note(self, midi_num: int, velocity: int = 100, duration: float = 0.5):
        vel = max(1, min(int(velocity), 127))
        self.fs.noteon(0, midi_num, vel)
        QTimer.singleShot(int(duration * 1000), lambda: self.fs.noteoff(0, midi_num))

    def all_notes_off(self):
        # Panic helper
        self.fs.cc(0, 120, 0)  # All Sound Off
        self.fs.cc(0, 123, 0)  # All Notes Off

    def shutdown(self):
        try:
            self.all_notes_off()
            self.fs.delete()
        except Exception:
            pass
