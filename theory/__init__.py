"""Pure, dependency-free music-theory utilities for the Score Reading App.

The :mod:`theory.diatonic_harmony` module is the canonical source of truth for
the Diatonic Harmony Trainer.  It is deliberately free of any GUI / Qt / Verovio
imports so it can be unit-tested in isolation and reused from any context.
"""

from .diatonic_harmony import (  # noqa: F401
    Scale,
    DiatonicTriad,
    TriadAnalysis,
    generate_scale,
    generate_diatonic_triads,
    transpose_degree_pattern,
    identify_triad_from_pitches,
    key_signature_fifths,
    note_to_midi,
    QUALITY_TO_INTERVAL_LAYER,
)
