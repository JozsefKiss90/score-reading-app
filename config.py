
from PyQt6.QtGui import QColor

# Keyboard / layout
WHITE_KEYS = [0, 2, 4, 5, 7, 9, 11]
KEY_WIDTH = 20
KEY_HEIGHT = 100
NUM_KEYS = 88
START_MIDI = 21

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
DEFAULT_MXL = "Gymnopdie_No._1__Satie.mxl"
DEFAULT_XML = "Gymnopdie/score.xml"
