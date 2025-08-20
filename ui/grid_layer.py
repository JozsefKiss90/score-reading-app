# ui/grid_layer.py
from typing import List, Dict
from PyQt6.QtGui import QPen, QColor
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsSimpleTextItem

from config import (
    GRID_LEVELS, GRID_MIN_SPACING_PX,
    KEY_HEIGHT, FOOTER_HEIGHT, SCROLL_SPEED,
    START_MIDI, NUM_KEYS, KEY_WIDTH, WHITE_KEYS,
)

def rebuild_static_grid(scene: QGraphicsScene, grid_items: List, bpm: float) -> None:
    """Draw fixed horizontal lines for multiple note values. Clears & repopulates grid_items."""
    _clear_grid(scene, grid_items)

    width  = scene.width()
    base_y = scene.height() - KEY_HEIGHT - FOOTER_HEIGHT
    chosen: Dict[int, QPen] = {}

    sec_per_quarter = 60.0 / max(bpm, 1e-6)

    for _, quarters, color, pen_w, *rest in GRID_LEVELS:
        dash = rest[0] if rest else None
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
                if dash is not None:
                    pen.setStyle(Qt.PenStyle.CustomDashLine)
                    pen.setDashPattern(dash)
                chosen[key] = pen
            y -= spacing_px

    for key in sorted(chosen.keys()):
        y = float(key)
        line = scene.addLine(0, y, width, y, chosen[key])
        line.setZValue(-1)
        grid_items.append(line)

    # optional extra layers:
    draw_footer_legend(scene, grid_items)
    draw_pitch_labels(scene, grid_items, show_sharps=True, show_octave=True)


def maybe_update_grid(scene: QGraphicsScene, grid_items: List, bpm_now: float, last_bpm: float | None) -> float:
    """Rebuild only when tempo actually changes (rounded) and return updated last_bpm."""
    if last_bpm is None or int(round(bpm_now)) != int(round(last_bpm)):
        rebuild_static_grid(scene, grid_items, bpm_now)
        return bpm_now
    return last_bpm


def draw_vertical_key_grid(scene: QGraphicsScene, grid_items: List) -> None:
    width = scene.width()
    top   = 0.0
    bottom= scene.height() - KEY_HEIGHT - FOOTER_HEIGHT

    for i in range(NUM_KEYS + 1):
        x = i * KEY_WIDTH
        midi = START_MIDI + i
        pc = midi % 12
        if pc == 0:  # C
            color = QColor(80, 80, 80, 140); pen_w = 2
        else:
            color = QColor(120, 120, 120, 60); pen_w = 1
        pen = QPen(color); pen.setCosmetic(True); pen.setWidth(pen_w)
        line = scene.addLine(x, top, x, bottom, pen)
        line.setZValue(-2)
        grid_items.append(line)


def draw_footer_legend(scene: QGraphicsScene, grid_items: List) -> None:
    y0 = scene.height() - FOOTER_HEIGHT + 5
    x  = 8
    spacing = 110

    def sample(label, color, dash, pen_w):
        nonlocal x
        pen = QPen(color); pen.setCosmetic(True); pen.setWidth(pen_w)
        if dash is not None:
            pen.setStyle(Qt.PenStyle.CustomDashLine); pen.setDashPattern(dash)
        line = scene.addLine(x, y0, x + 60, y0, pen); line.setZValue(2); grid_items.append(line)
        txt = scene.addText(label); txt.setDefaultTextColor(QColor(40, 40, 40))
        txt.setPos(x + 66, y0 - 10); txt.setZValue(2); grid_items.append(txt)
        x += spacing

    styles = {name: (col, (rest[0] if rest else None), w)
              for (name, q, col, w, *rest) in GRID_LEVELS}
    for name in ("whole", "half"):
        col, dash, w = styles.get(name, (QColor(30,30,30,220), None, 2))
        sample(name.capitalize(), col, dash, w)


def draw_pitch_labels(scene: QGraphicsScene, grid_items: List, show_sharps=True, show_octave=True) -> None:
    base_y = scene.height() - FOOTER_HEIGHT
    text_color = QColor(40, 40, 40)
    names = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
    for i in range(NUM_KEYS):
        midi = START_MIDI + i
        pc = midi % 12
        octave = (midi // 12) - 1
        is_white = pc in WHITE_KEYS
        if is_white:
            label = names[pc]
            if show_octave and names[pc] == "C":
                label += str(octave)
            elif show_octave and names[pc] == "A" and octave == 0:
                label += str(octave)
            item = QGraphicsSimpleTextItem(label)
            item.setBrush(text_color)
            x = i * KEY_WIDTH + KEY_WIDTH * 0.5 - item.boundingRect().width() * 0.5
            y = base_y + (FOOTER_HEIGHT - item.boundingRect().height()) * 0.5
            item.setPos(x, y); item.setZValue(3)
            grid_items.append(item); scene.addItem(item)
        else:
            if not show_sharps:
                continue
            label = names[pc]
            item = QGraphicsSimpleTextItem(label)
            item.setBrush(QColor(80, 80, 80)); item.setScale(0.8)
            x = i * KEY_WIDTH + KEY_WIDTH * 0.5 - (item.boundingRect().width()*0.8) * 0.5
            y = base_y + 2
            item.setPos(x, y); item.setZValue(3)
            grid_items.append(item); scene.addItem(item)


def _clear_grid(scene: QGraphicsScene, grid_items: List) -> None:
    if not grid_items:
        return
    for it in grid_items:
        scene.removeItem(it)
    grid_items.clear()
