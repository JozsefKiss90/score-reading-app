# audio/midi_service.py
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from .midi_input import MidiInput


class MidiService(QObject):
    """
    Thin wrapper around MidiInput that can be shared between multiple windows.

    - Owns exactly one MidiInput instance.
    - Re-emits noteOn / noteOff / control so callers don't need to know
      about MidiInput directly.
    - Lifetime is managed by whoever owns the MidiService (typically AppContext).
    """

    # Public signals UIs can connect to
    noteOn = pyqtSignal(int, int, float)   # pitch, velocity, timestamp
    noteOff = pyqtSignal(int, float)       # pitch, timestamp
    control = pyqtSignal(int, int, float)  # cc, value, timestamp

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

        self._input: Optional[MidiInput] = MidiInput(self)
        self._port_name: Optional[str] = getattr(self._input, "_port_name", None)

        if self._input is not None:
            # Re-emit all events so other code only ever talks to MidiService
            self._input.noteOn.connect(self.noteOn)
            self._input.noteOff.connect(self.noteOff)
            self._input.control.connect(self.control)

    # ------------------------------------------------------------------ #
    # Properties
    # ------------------------------------------------------------------ #
    @property
    def port_name(self) -> Optional[str]:
        """Name of the MIDI port currently in use (if any)."""
        return self._port_name

    # ------------------------------------------------------------------ #
    # Lifetime helpers
    # ------------------------------------------------------------------ #
    def is_active(self) -> bool:
        """Return True if a MIDI input port is currently open."""
        return self._input is not None

    def shutdown(self) -> None:
        """Close the underlying MIDI input port. Safe to call multiple times."""
        if self._input is not None:
            try:
                self._input.close()
            finally:
                self._input = None
