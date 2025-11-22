from music21 import converter
import os, sys

xml_path = r"resources\C-origin_fractal_spiral_arpeggio.xml"  # your attached file
midi_fp = "fractal_spiral.mid"

# Convert MusicXML -> MIDI
score = converter.parse(xml_path)
score.write("midi", fp=midi_fp)

# Play it with your default Windows MIDI player
os.startfile(midi_fp)  # opens the default app and starts playback
