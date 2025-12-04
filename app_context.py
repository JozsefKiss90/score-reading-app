# app_context.py
from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import QObject

from audio.midi_service import MidiService


class AppContext(QObject):
    """
    Application-wide context.

    Responsibilities:
      - Knows where the resources directory lives.
      - Optionally stores the default soundfont path.
      - Owns a shared MidiService instance.

    Typical usage in app.py:

        ctx = AppContext(soundfont_name=DEFAULT_SF2)
        mxl_path = ctx.resources_path(DEFAULT_MXL)
        xml_path = ctx.resources_path(DEFAULT_XML)

        win = PracticeWindow(ctx, mxl_path, xml_path)
    """

    def __init__(
        self,
        resources_root: Optional[str] = None,
        soundfont_name: Optional[str] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)

        # --- resource paths -------------------------------------------------
        self._resources_root = resources_root or self._default_resources_root()

        # If caller gave a relative soundfont filename, resolve it now
        self.soundfont_path: Optional[str] = (
            self.resources_path(soundfont_name)
            if soundfont_name is not None
            else None
        )

        # --- shared services ------------------------------------------------
        # One global MIDI entry point for the whole application
        self.midi = MidiService(self)

    # ---------------------------------------------------------------------- #
    # Resource helpers
    # ---------------------------------------------------------------------- #
    def _default_resources_root(self) -> str:
        """
        Mirror the behaviour of the old resources_path helper:
        - Prefer <package_dir>/resources
        - Fallback to <cwd>/resources
        """
        here = os.path.dirname(os.path.abspath(__file__))
        cand = os.path.join(here, "resources")
        if os.path.isdir(cand):
            return cand
        return os.path.join(os.getcwd(), "resources")

    def resources_path(self, name: str) -> str:
        """
        Resolve a file in the resources directory.

        If `name` is already an absolute path it is returned unchanged.
        """
        if not name:
            return self._resources_root

        if os.path.isabs(name):
            return name

        return os.path.join(self._resources_root, name)

    # ---------------------------------------------------------------------- #
    # Lifetime
    # ---------------------------------------------------------------------- #
    def shutdown(self) -> None:
        """
        Tear down long-lived services.

        Call this once on application exit (e.g. in app.py) if you want
        to be explicit, though letting the process die will also close
        the MIDI port.
        """
        if getattr(self, "midi", None) is not None:
            self.midi.shutdown()
            self.midi = None
