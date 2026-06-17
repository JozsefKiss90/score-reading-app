"""Circle-of-Fifths payload generator + click-to-exercise bridge.

The Interactive Circle of Fifths (``beat_selector/harmony_circle.js``) is the
first visual module of the future Interactive Harmony Atlas.  This module is its
**pure Python data layer**: it builds a JSON-serialisable payload describing the
whole diatonic key system and converts a circle "click request" into a real
:class:`~harmony.exercise_spec.HarmonyExerciseSpec`.

Design rules (shared with the rest of the Harmony Trainer):

* **No duplicated theory tables.**  Every label, chord, quality, interval layer,
  function, scale, and key-signature is *derived* from
  :mod:`theory.diatonic_harmony` (``generate_diatonic_triads`` /
  ``generate_scale`` / ``key_signature_fifths``).  No hard-coded chord lists.
* **Deterministic & pure.**  No Qt / Verovio / MIDI here, so it unit-tests
  headlessly and serialises straight to the JS renderer.
* **Practical spelling.**  Reuses ``DEFAULT_MAJOR_KEYS`` / ``DEFAULT_MINOR_KEYS``
  and the engine's enharmonic spelling (G major → F#, F major → Bb, ...).
* **Extensible.**  The payload reserves the relationship vocabulary (Part 8 of
  the spec) so dominant-seventh / diminished / secondary-dominant / cadence
  layers can be added without reshaping the data.

The circle *order* is computed from the circle of fifths (not hard-coded): each
key is placed by its key-signature ``fifths`` so the ring reads
C G D A E B Gb Db Ab Eb Bb F clockwise, with the relative minors directly inside.
"""

from __future__ import annotations

from typing import Dict, List

from theory.diatonic_harmony import (
    DiatonicTriad,
    generate_diatonic_triads,
    generate_scale,
    key_signature_fifths,
    QUALITY_TO_INTERVAL_LAYER,
)
from harmony.exercise_spec import (
    HarmonyExerciseSpec,
    compile_exercise,
    MAX_CHORDS_PER_SPEC,
    DEFAULT_MAJOR_KEYS,
    DEFAULT_MINOR_KEYS,
)


SCHEMA_VERSION = "harmony-circle/v1"

#: Coarse harmonic-function colour class (T / S / D) for each engine function
#: label.  This is a *presentational grouping* of the engine's labels into the
#: three colour buckets the chart uses -- defined once, not a theory table.
_FUNCTION_CLASS = {
    "tonic": "T",
    "mediant": "T",
    "predominant": "S",
    "subdominant": "S",
    "dominant": "D",
}

#: Human labels for the three function colour classes (Part 7 cheatsheet legend).
_FUNCTION_CLASS_LABELS = [
    {"class": "T", "label": "Tonic"},
    {"class": "S", "label": "Predominant / Subdominant"},
    {"class": "D", "label": "Dominant"},
]

#: Relationship vocabulary reserved for future layers (Part 8).  The circle only
#: *names* these now; the diatonic edges/graph live in :mod:`harmony.atlas`.
RESERVED_RELATIONS = [
    "relative_minor_of", "relative_major_of", "dominant_of", "subdominant_of",
    "same_quality", "same_function", "same_interval_layer", "transposes_to",
    "resolves_to",
]

#: Drills the circle can launch (a subset of the trainer's drills, for now).
_VALID_CIRCLE_DRILLS = {"full_key", "horizontal_degree", "quality", "function"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slug(text: str) -> str:
    out = (text or "").replace("#", "s").replace("b", "f").replace("°", "dim")
    return "".join(ch if ch.isalnum() else "_" for ch in out).strip("_")


def _mode_word(mode: str) -> str:
    return "major" if mode == "major" else "minor"


def _clockwise_index(fifths: int) -> int:
    """Position on the circle of fifths, clockwise from C (0) at 12 o'clock.

    ``C=0, G=1 ... B=5, Gb/F#=6, Db=7, Ab=8, Eb=9, Bb=10, F=11``.
    """
    return fifths if fifths >= 0 else 12 + fifths


def _triad_dict(t: DiatonicTriad) -> Dict:
    """A circle triad descriptor -- every field derived from the theory engine."""
    return {
        "degree": t.roman,
        "degreeNumber": t.degree_number,
        "chordSymbol": t.chord_symbol,
        "root": t.root,
        "quality": t.chord_quality,
        "tones": list(t.pitches),
        "intervalLayer": t.interval_layer,
        "functionLabel": t.function_label,                  # engine label (matches trainer)
        "functionClass": _FUNCTION_CLASS.get(t.function_label, "T"),
    }


def _key_entry(key: str, mode: str) -> Dict:
    scale = generate_scale(key, mode)
    relative = (scale.scale_pitches[5] if mode == "major"   # submediant = rel. minor
                else scale.scale_pitches[2])                # mediant = rel. major
    entry = {
        "key": key,
        "mode": mode,
        "fifths": scale.fifths,
        "scale": list(scale.scale_pitches),
        "triads": [_triad_dict(t) for t in generate_diatonic_triads(key, mode)],
    }
    entry["relativeMinor" if mode == "major" else "relativeMajor"] = relative
    return entry


def _relative_minor(major_key: str) -> str:
    return generate_scale(major_key, "major").scale_pitches[5]


# ---------------------------------------------------------------------------
# Payload
# ---------------------------------------------------------------------------

def _cheatsheet() -> Dict:
    """Degree patterns + interval-layer + function legends, derived from theory."""
    def pattern(key, mode):
        return [{
            "degree": t.roman,
            "quality": t.chord_quality,
            "intervalLayer": t.interval_layer,
            "functionLabel": t.function_label,
            "functionClass": _FUNCTION_CLASS.get(t.function_label, "T"),
        } for t in generate_diatonic_triads(key, mode)]

    return {
        "majorPattern": pattern("C", "major"),
        "minorPattern": pattern("A", "natural_minor"),
        "intervalLayers": [{"quality": q, "intervalLayer": layer}
                           for q, layer in QUALITY_TO_INTERVAL_LAYER.items()],
        "functionClasses": [dict(fc) for fc in _FUNCTION_CLASS_LABELS],
    }


def build_circle_payload() -> Dict:
    """Build the full, deterministic Circle-of-Fifths payload (schema v1)."""
    major_order = sorted(
        DEFAULT_MAJOR_KEYS,
        key=lambda k: _clockwise_index(key_signature_fifths(k, "major")))
    minor_order = [_relative_minor(k) for k in major_order]

    return {
        "schema": SCHEMA_VERSION,
        "majorKeys": [_key_entry(k, "major") for k in DEFAULT_MAJOR_KEYS],
        "minorKeys": [_key_entry(k, "natural_minor") for k in DEFAULT_MINOR_KEYS],
        "circleOrderMajor": major_order,
        "circleOrderMinor": minor_order,
        "cheatsheet": _cheatsheet(),
        "relations": list(RESERVED_RELATIONS),
    }


# ---------------------------------------------------------------------------
# Click -> exercise bridge
# ---------------------------------------------------------------------------

def spec_from_circle_request(req: Dict) -> HarmonyExerciseSpec:
    """Convert a circle click request into a validated :class:`HarmonyExerciseSpec`.

    The circle never builds MusicXML; it sends a spec-like dict such as::

        {"drill": "full_key", "render": "block", "mode": "major", "key": "G major"}
        {"drill": "horizontal_degree", "render": "arpeggio", "mode": "major", "degree": "V"}

    This synthesises a stable ``exercise_id`` / ``title`` (the circle omits
    them), constructs a ``HarmonyExerciseSpec``, validates it, and guards the
    readability cap.  Invalid *or oversized* requests raise :class:`ValueError`
    (never silently produce a bad/unreadable spec) -- e.g. a ``quality`` or
    ``function`` request spanning all 12 keys would exceed
    :data:`~harmony.exercise_spec.MAX_CHORDS_PER_SPEC`, so scope it (pass
    ``keys=[...]``) to keep a single exercise short.
    """
    if not isinstance(req, dict):
        raise ValueError("circle request must be a dict")
    drill = req.get("drill")
    if drill not in _VALID_CIRCLE_DRILLS:
        raise ValueError(f"unsupported circle drill: {drill!r}")

    allowed = ("render", "mode", "key", "degree", "quality", "pattern", "keys",
               "description")
    fields = {k: req[k] for k in allowed if req.get(k) is not None}

    ident = (fields.get("key") or fields.get("degree") or fields.get("quality")
             or "-".join(fields.get("pattern") or []) or "x")
    if fields.get("keys"):                # scoped quality/function -> unique id per key set
        ident = ident + "_" + "_".join(fields["keys"])
    render = fields.get("render", "block")
    mode = fields.get("mode", "major")
    # Only the identifier carries accidentals; keep the clean tokens verbatim so
    # ids stay readable (e.g. 'block' must not become 'flock').
    exercise_id = f"circle_{drill}_{mode}_{_slug(ident)}_{render}"
    title = req.get("title") or f"{ident} — {drill} ({render})"

    spec = HarmonyExerciseSpec(
        exercise_id=exercise_id, title=title, drill=drill, **fields)
    spec.validate()                      # raises on missing/invalid drill params

    # Readability guard: never hand the trainer a single exercise longer than the
    # cap (a quality/function drill across all 12 keys would be 36-48 chords).
    # The circle UI sends scoped requests; this backstops any other caller.
    n = len(compile_exercise(spec))
    if n > MAX_CHORDS_PER_SPEC:
        raise ValueError(
            f"circle request compiles to {n} chords (> {MAX_CHORDS_PER_SPEC}); "
            f"scope it to fewer keys (pass 'keys').")
    return spec
