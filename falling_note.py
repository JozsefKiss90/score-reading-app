class FallingNote:
    def __init__(self, bar_item, pitch, duration, keyboard_y, played=False):
        self.bar = bar_item
        self.pitch = pitch
        self.duration = duration
        self.keyboard_y = keyboard_y
        self.played = played

    def update(self, dy, player):
        self.bar.moveBy(0, dy)
        bottom = self.bar.y() + self.bar.rect().height()
        if not self.played and bottom >= self.keyboard_y:
            player.play_note(self.pitch, duration=self.duration)
            self.played = True
        return bottom
