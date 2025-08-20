
from __future__ import annotations
from PyQt6.QtWidgets import QGraphicsRectItem
from PyQt6.QtGui import QColor, QBrush
from PyQt6.QtCore import QRectF
from config import KEY_WIDTH, SCROLL_SPEED

class NoteItem(QGraphicsRectItem): 
    __slots__ = ("pitch", "start", "duration", "staff", "bar_height", "spawn_time_music", "initial_y")
    def __init__(self, pitch: int, start: float, duration: float, staff: int,
                 bar_height: float, x: float, initial_y: float):
        super().__init__(QRectF(x, initial_y, KEY_WIDTH, bar_height))
        self.pitch = pitch
        self.start = start
        self.duration = duration
        self.staff = staff
        self.bar_height = bar_height
        self.initial_y = initial_y
        self.spawn_time_music = None
        color = QColor(255, 100, 100, 220) if staff == 1 else QColor(100, 120, 255, 220)
        self.setBrush(QBrush(color))
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setCacheMode(QGraphicsRectItem.CacheMode.DeviceCoordinateCache)
        self.setZValue(0)

    def on_spawn(self, spawn_time_music: float):
        self.spawn_time_music = spawn_time_music

    def update_position(self, music_now: float):
        if self.spawn_time_music is None:
            return
        t = max(0.0, music_now - self.spawn_time_music)
        y = self.initial_y + (t * SCROLL_SPEED)
        rect = self.rect()
        if rect.y() != y:
            rect.moveTop(y)
            self.setRect(rect)
