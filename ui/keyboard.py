
from __future__ import annotations
from PyQt6.QtWidgets import QGraphicsRectItem
from PyQt6.QtGui import QBrush
from PyQt6.QtCore import Qt
from config import NUM_KEYS, START_MIDI, KEY_WIDTH, KEY_HEIGHT, WHITE_KEYS, FOOTER_HEIGHT

def draw_keyboard(scene):
    for i in range(NUM_KEYS):
        midi = START_MIDI + i
        pc = midi % 12
        x = i * KEY_WIDTH
        is_white = pc in WHITE_KEYS
        key = QGraphicsRectItem(x, scene.height() - KEY_HEIGHT - FOOTER_HEIGHT, KEY_WIDTH, KEY_HEIGHT)
        key.setBrush(QBrush(Qt.GlobalColor.white if is_white else Qt.GlobalColor.black))
        key.setZValue(1)
        key.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, False)
        key.setCacheMode(QGraphicsRectItem.CacheMode.DeviceCoordinateCache)
        scene.addItem(key)
