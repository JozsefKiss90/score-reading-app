
from PyQt6.QtGui import QColor

# Keyboard / layout
WHITE_KEYS = [0, 2, 4, 5, 7, 9, 11]
KEY_WIDTH = 20
KEY_HEIGHT = 100
# config.py
START_MIDI = 24             # actual pitch the SE61 sends
VISIBLE_START_MIDI = 24     # draw keyboard from C2 (correct pattern)
NUM_KEYS = 61
# View / timing
SCROLL_SPEED = 100.0
FPS = 60
VIEW_HEIGHT = 800
FOOTER_HEIGHT = 24
AUDIO_LATENCY_MS = 0

# Derived
VISUAL_PREROLL_S = VIEW_HEIGHT / SCROLL_SPEED

# Grid layers: name, quarters, color, pen_width, dash_pattern (or None)
GRID_LEVELS = [
    ("whole",    4.0, QColor(30, 30, 30, 220), 2, None),          # dark solid
    ("half",     2.0, QColor(25, 115, 232, 180), 1, [8, 4]),      # blue dashes
    ("quarter",  1.0, QColor(34, 160,  90, 160), 1, [4, 4]),      # green dashes
    ("eighth",   0.5, QColor(232, 138,  23, 140), 1, [2, 4]),     # orange dashes
]
GRID_MIN_SPACING_PX = 14

# Static grid settings
GRID_NOTE_VALUE = "quarter"   # one of: "whole", "half", "quarter", "eighth", "sixteenth"
SHOW_MAJOR_WHOLE_LINES = True
GRID_COLOR = QColor(0, 0, 0, 70)
GRID_MAJOR_COLOR = QColor(0, 0, 0, 140)

# Resource names (relative to project / resources dir)
DEFAULT_SF2 = "FluidR3_GM.sf2"
#DEFAULT_MXL = "Prelude_No._15_in_D_flat_major_Op._28_The_Raindrop_Prelude.mxl"
#DEFAULT_XML = "Prelude_No._15_in_D_flat_major_Op._28_The_Raindrop_Prelude\score.xml"
#DEFAULT_MXL = "organ-sonata-no-4-bwv-528-2-andante-adagio-vikingur-olafsson-interpretation.mxl"
#DEFAULT_XML = "organ-sonata-no-4-bwv-528-2-andante-adagio-vikingur-olafsson-interpretation\score.xml"
DEFAULT_MXL = "bb_major_5-4_melody_expanded.mxl"
DEFAULT_XML = "mxl_extracted\\META-INF\\container.xml"

#DEFAULT_MXL = "chopin-prelude-in-e-minor-opus-28-no-4.mxl"
#DEFAULT_XML = "bach-prelude-bwv-926/score.xml"
#DEFAULT_MXL =  "bach-prelude-bwv-926.mxl"
LIVE_VELOCITY_SCALE = 1.8