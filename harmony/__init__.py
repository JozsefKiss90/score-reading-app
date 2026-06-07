"""Diatonic Harmony Trainer: exercise specs, compilation, and MusicXML.

This package builds on the pure :mod:`theory.diatonic_harmony` module:

* :mod:`harmony.exercise_spec`   -- JSON-compatible exercise schema + compiler.
* :mod:`harmony.musicxml_builder` -- playable MusicXML + the runtime trainer
  payload consumed by the injected JS controller.

Nothing here imports Qt/Verovio, so it stays unit-testable.
"""

from .exercise_spec import (  # noqa: F401
    HarmonyExerciseSpec,
    CompiledChord,
    CompiledExercise,
    compile_exercise,
    default_demo_specs,
    DEFAULT_MAJOR_KEYS,
    DEFAULT_MINOR_KEYS,
)
