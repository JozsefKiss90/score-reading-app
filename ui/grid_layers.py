
from __future__ import annotations
from PyQt6.QtWidgets import QGraphicsSimpleTextItem
from PyQt6.QtGui import QPen, QColor
from PyQt6.QtCore import Qt
from config import (
    GRID_LEVELS, GRID_MIN_SPACING_PX, GRID_NOTE_VALUE,
    GRID_COLOR, GRID_MAJOR_COLOR,
    KEY_HEIGHT, FOOTER_HEIGHT, START_MIDI, NUM_KEYS, KEY_WIDTH, WHITE_KEYS,
    SCROLL_SPEED
)

def note_value_factor(name: str) -> float:
    return {"whole": 4.0, "half": 2.0, "quarter": 1.0, "eighth": 0.5, "sixteenth": 0.25}.get(name, 1.0)

def grid_spacing_px(bpm: float) -> float:
    sec_per_quarter = 60.0 / max(bpm, 1e-6)
    sec_per_grid = sec_per_quarter * note_value_factor(GRID_NOTE_VALUE)
    return max(GRID_MIN_SPACING_PX, sec_per_grid * SCROLL_SPEED)

def clear_items(scene, items_store: list):
    if not items_store:
        return
    for it in items_store:
        scene.removeItem(it)
    items_store.clear()

def rebuild_static_grid(scene, items_store: list, bpm: float):
    clear_items(scene, items_store)

    width  = scene.width()
    base_y = scene.height() - KEY_HEIGHT - FOOTER_HEIGHT

    chosen = {}
    sec_per_quarter = 60.0 / max(bpm, 1e-6)

    for _, quarters, color, pen_w, dash in GRID_LEVELS:
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
        items_store.append(line)

    draw_footer_legend(scene, items_store)
    draw_pitch_labels(scene, items_store, show_sharps=True, show_octave=True)

def draw_vertical_key_grid(scene, items_store: list):
    width = scene.width()
    top   = 0.0
    bottom= scene.height() - KEY_HEIGHT - FOOTER_HEIGHT
    for i in range(NUM_KEYS + 1):
        x = i * KEY_WIDTH
        midi = START_MIDI + i
        pc = midi % 12
        if pc == 0:
            color = QColor(80, 80, 80, 140)
            pen_w = 2
        else:
            color = QColor(120, 120, 120, 60)
            pen_w = 1

        pen = QPen(color)
        pen.setCosmetic(True)
        pen.setWidth(pen_w)
        line = scene.addLine(x, top, x, bottom, pen)
        line.setZValue(-2)
        items_store.append(line)

def draw_footer_legend(scene, items_store: list):
    y0 = scene.height() - FOOTER_HEIGHT + 5
    x  = 8
    spacing = 110

    def sample(label, color, dash, pen_w):
        nonlocal x
        pen = QPen(color); pen.setCosmetic(True); pen.setWidth(pen_w)
        if dash is not None:
            pen.setStyle(Qt.PenStyle.CustomDashLine)
            pen.setDashPattern(dash)
        line = scene.addLine(x, y0, x + 60, y0, pen)
        line.setZValue(2)
        items_store.append(line)
        txt = scene.addText(label)
        txt.setDefaultTextColor(QColor(40, 40, 40))
        txt.setPos(x + 66, y0 - 10)
        txt.setZValue(2)
        items_store.append(txt)
        x += spacing

    # Always match GRID_LEVELS
    for name, quarters, col, w, d in GRID_LEVELS:
        label = name.capitalize()
        sample(label, col, d, w)

def draw_pitch_labels(scene, items_store: list, show_sharps=True, show_octave=True):
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
            item.setPos(x, y)
            item.setZValue(3)
            items_store.append(item)
            scene.addItem(item)
        else:
            if not show_sharps:
                continue
            label = names[pc]
            item = QGraphicsSimpleTextItem(label)
            item.setBrush(QColor(80, 80, 80))
            item.setScale(0.8)
            x = i * KEY_WIDTH + KEY_WIDTH * 0.5 - (item.boundingRect().width()*0.8) * 0.5
            y = base_y + 2
            item.setPos(x, y)
            item.setZValue(3)
            items_store.append(item)
            scene.addItem(item)
