"""Diatonic harmony theory for major and natural-minor keys.

This module is the *pedagogical contract* for the Diatonic Harmony Trainer.
It is pure Python (standard library only) so it can be unit-tested without a
display, MIDI device, Verovio, or Qt.

Scope
-----
* Major, natural-minor and harmonic-minor diatonic triads, root position.
  Harmonic minor (ticket 13 / plan G2a) raises the 7th degree, giving minor
  keys a real major ``V``, a leading-tone ``vii°`` -- and the first
  ``III+`` augmented triad (drilled later, plan G2b).
* Every diatonic seventh chord of the supported modes (ticket 10 / plan G1b):
  :data:`SEVENTH_DEGREE_TOKENS` is the full vocabulary — one token per degree
  per mode, spelled exactly as the engine builds it (``Imaj7``, ``ii7``,
  ``viiø7``; minor's ``i7`` … ``VII7``).  Harmonic minor adds the fully
  diminished ``vii°7`` (and shares ``iiø7``/``iv7``/``V7``/``VImaj7``); its
  tonic and mediant tetrads (minor-major / augmented-major sevenths) have no
  supported quality and therefore no token.
* No melodic minor, secondary dominants, or cadences yet -- but the
  data model is designed so those extend without refactoring: quality (and
  therefore Roman-numeral case, chord symbol, and function) is always
  *derived* from the actual interval content, never hard-coded per mode.
  A future ``melodic_minor`` mode only needs a new scale-step pattern.

Chord interval layers (the canonical table)
-------------------------------------------
* major                   = M3 + m3
* minor                   = m3 + M3
* diminished              = m3 + m3
* augmented               = M3 + M3
* dominant_seventh        = M3 + m3 + m3
* major_seventh           = M3 + m3 + M3
* minor_seventh           = m3 + M3 + m3
* half_diminished_seventh = m3 + m3 + M3
* diminished_seventh      = m3 + m3 + m3

Public API
----------
* :func:`generate_scale`
* :func:`generate_diatonic_triads`
* :func:`generate_diatonic_sevenths`
* :func:`build_seventh_chord`
* :func:`build_dominant_seventh`
* :func:`parse_seventh_token`
* :func:`seventh_tokens_for_mode`
* :func:`transpose_degree_pattern`
* :func:`identify_triad_from_pitches`
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

try:  # Python 3.8+ has Literal in typing
    from typing import Literal

    Mode = Literal["major", "natural_minor", "harmonic_minor"]
except Exception:  # pragma: no cover - defensive only
    Mode = str  # type: ignore


__all__ = [
    "Scale",
    "DiatonicTriad",
    "TriadAnalysis",
    "generate_scale",
    "generate_diatonic_triads",
    "generate_diatonic_sevenths",
    "build_seventh_chord",
    "build_dominant_seventh",
    "parse_seventh_token",
    "seventh_tokens_for_mode",
    "transpose_degree_pattern",
    "identify_triad_from_pitches",
    "key_signature_fifths",
    "note_to_midi",
    "QUALITY_TO_INTERVAL_LAYER",
    "SEVENTH_DEGREE_TOKENS",
    "SEVENTH_QUALITY_LABELS",
]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Diatonic letter cycle.
LETTERS = ["C", "D", "E", "F", "G", "A", "B"]
LETTER_INDEX = {l: i for i, l in enumerate(LETTERS)}
#: Natural (no accidental) pitch class of each letter.
LETTER_BASE_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

#: Semitone offsets from the tonic for each supported mode.
MAJOR_STEPS = [0, 2, 4, 5, 7, 9, 11]
NATURAL_MINOR_STEPS = [0, 2, 3, 5, 7, 8, 10]
HARMONIC_MINOR_STEPS = [0, 2, 3, 5, 7, 8, 11]  # natural minor + raised 7th

_MODE_STEPS = {
    "major": MAJOR_STEPS,
    "natural_minor": NATURAL_MINOR_STEPS,
    "harmonic_minor": HARMONIC_MINOR_STEPS,
}

#: How a key tonic letter maps onto the circle of fifths (count of sharps,
#: negative = flats) for a *natural* letter; each sharp adds 7, each flat -7.
_BASE_FIFTHS_MAJOR = {"C": 0, "D": 2, "E": 4, "F": -1, "G": 1, "A": 3, "B": 5}
_BASE_FIFTHS_MINOR = {"A": 0, "B": 2, "C": -3, "D": -1, "E": 1, "F": -4, "G": -2}

ROMAN_NUMERALS = ["I", "II", "III", "IV", "V", "VI", "VII"]
_ROMAN_TO_NUMBER = {r: i + 1 for i, r in enumerate(ROMAN_NUMERALS)}

#: Scale-degree names (finer than the broad T/S/D function category).
_DEGREE_NAMES_MAJOR = [
    "tonic", "supertonic", "mediant", "subdominant",
    "dominant", "submediant", "leading-tone",
]
_DEGREE_NAMES_MINOR = [
    "tonic", "supertonic", "mediant", "subdominant",
    "dominant", "submediant", "subtonic",
]
#: Harmonic minor's raised 7th is a true leading tone, not a subtonic.
_DEGREE_NAMES_HARMONIC_MINOR = [
    "tonic", "supertonic", "mediant", "subdominant",
    "dominant", "submediant", "leading-tone",
]

#: Broad harmonic-function category per scale degree, following the trainer's
#: pedagogical contract (Tonic / Predominant / Subdominant / Dominant groups).
#: Major:  I->T  ii->PD  iii->mediant  IV->S  V->D  vi->T  vii deg->D
#: Minor:  i->T  ii deg->PD  III->T  iv->S  v->D  VI->T  VII->D
_FUNCTION_LABELS_MAJOR = [
    "tonic", "predominant", "mediant", "subdominant",
    "dominant", "tonic", "dominant",
]
_FUNCTION_LABELS_MINOR = [
    "tonic", "predominant", "tonic", "subdominant",
    "dominant", "tonic", "dominant",
]
#: Harmonic minor: III+ (augmented) cannot claim natural minor's relative-major
#: tonic grouping -- it is labelled the mediant, as in major.
_FUNCTION_LABELS_HARMONIC_MINOR = [
    "tonic", "predominant", "mediant", "subdominant",
    "dominant", "tonic", "dominant",
]

#: Canonical interval-layer string per chord quality (triads + tetrads).
QUALITY_TO_INTERVAL_LAYER = {
    "major": "M3+m3",
    "minor": "m3+M3",
    "diminished": "m3+m3",
    "augmented": "M3+M3",
    "dominant_seventh": "M3+m3+m3",
    "major_seventh": "M3+m3+M3",
    "minor_seventh": "m3+M3+m3",
    "half_diminished_seventh": "m3+m3+M3",
    "diminished_seventh": "m3+m3+m3",
}

#: chord-symbol suffix per quality.
_QUALITY_SYMBOL_SUFFIX = {
    "major": "",
    "minor": "m",
    "diminished": "°",  # °
    "augmented": "+",
    "dominant_seventh": "7",
    "major_seventh": "maj7",
    "minor_seventh": "m7",
    "half_diminished_seventh": "ø7",
    "diminished_seventh": "°7",
}

#: Tetrad quality from the three stacked thirds (in semitones).  All five
#: seventh qualities are classified; the fully diminished (3,3,3) occurs
#: diatonically only in harmonic minor (vii°7).  Harmonic minor's tonic and
#: mediant tetrads (minor-major / augmented-major sevenths) are deliberately
#: absent: callers refuse ``"unknown"`` rather than mislabel them.
_TETRAD_QUALITIES = {
    (4, 3, 3): "dominant_seventh",
    (4, 3, 4): "major_seventh",
    (3, 4, 3): "minor_seventh",
    (3, 3, 4): "half_diminished_seventh",
    (3, 3, 3): "diminished_seventh",
}

#: Roman-numeral suffix per TETRAD quality.  ``maj7`` marks the major seventh
#: (a bare ``I7`` would falsely suggest a dominant quality) and ``ø7`` the
#: half-diminished (``°7`` names the FULLY diminished seventh, which no
#: supported scale contains) — the roman never claims a quality the chord
#: does not have.
_TETRAD_ROMAN_SUFFIX = {
    "dominant_seventh": "7",
    "minor_seventh": "7",
    "major_seventh": "maj7",
    "half_diminished_seventh": "ø7",
    "diminished_seventh": "°7",
}

#: Short pedagogical quality labels (third-stack shorthand: triad quality +
#: seventh quality).  This is the MCQ option vocabulary of the hear-a-seventh
#: quality-ID drills (ticket 10): in the major/natural-minor drills °7 is a
#: distractor, but harmonic minor (ticket 13) can now genuinely sound it
#: (vii°7).
SEVENTH_QUALITY_LABELS = {
    "dominant_seventh": "Mm7",
    "minor_seventh": "mm7",
    "major_seventh": "MM7",
    "half_diminished_seventh": "ø7",
    "diminished_seventh": "°7",
}

#: Roman-numeral seventh tokens the engine can build, mapped to their 0-based
#: scale degree.  This is the single vocabulary source for "which seventh
#: chords exist": the trainer's pattern normaliser and the Lab's roman gate
#: both consult it, so a token is accepted exactly where a buildable chord
#: exists (never silently downgraded to a triad).  One token per degree per
#: mode, spelled exactly as :func:`_build_tetrad` derives the roman —
#: :func:`build_seventh_chord` enforces the match, which is what makes a
#: major-mode token (``V7``) refuse natural minor (whose degree-5 seventh is
#: ``v7``) and vice versa.
SEVENTH_DEGREE_TOKENS = {
    # major
    "Imaj7": 0, "ii7": 1, "iii7": 2, "IVmaj7": 3, "V7": 4, "vi7": 5,
    "viiø7": 6,
    # natural minor
    "i7": 0, "iiø7": 1, "IIImaj7": 2, "iv7": 3, "v7": 4, "VImaj7": 5,
    "VII7": 6,
    # harmonic minor adds the fully diminished leading-tone seventh; its other
    # buildable tetrads (iiø7 / iv7 / V7 / VImaj7) already appear above with
    # the same degree numbers -- the roman-match gate in
    # :func:`build_seventh_chord` does the per-mode filtering.
    "vii°7": 6,
}


def parse_seventh_token(token: str) -> Optional[int]:
    """0-based degree of a *supported* seventh token, else ``None``.

    Exact-match on the canonical spellings: case and quality decoration
    matter (``I7`` would claim a dominant quality the tonic seventh does not
    have; ``vii°7`` would mislabel the half-diminished ``viiø7``), so nothing
    tolerant happens here.
    """
    return SEVENTH_DEGREE_TOKENS.get((token or "").strip())

#: Roman-numeral suffix per quality.
_QUALITY_ROMAN_SUFFIX = {
    "major": "",
    "minor": "",
    "diminished": "°",  # °
    "augmented": "+",
}

_ACCIDENTAL_NORMALISE = {
    "♯": "#",  # ♯
    "♭": "b",  # ♭
    "\U0001D12A": "##",  # 𝄪 double sharp
    "\U0001D12B": "bb",  # 𝄫 double flat
}

_TONIC_RE = re.compile(r"^\s*([A-Ga-g])([#bx♯♭]{0,2})\s*(.*)$")
_PITCH_RE = re.compile(r"^\s*([A-Ga-g])([#bx♯♭]{0,2})(-?\d+)?\s*$")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Scale:
    """A diatonic scale in a given key/mode."""

    key: str                 # display label, e.g. "Eb major" / "A minor"
    mode: str                # "major" | "natural_minor"
    tonic: str               # spelled tonic pitch class, e.g. "Eb"
    scale_pitches: List[str]  # 7 spelled pitch classes (no octave)
    midi_pitches: List[int]  # 7 MIDI numbers, ascending from tonic (octave 4)
    fifths: int              # key-signature fifths (sharps +, flats -)


@dataclass(frozen=True)
class DiatonicTriad:
    """A single diatonic chord with its full pedagogical annotation.

    Despite the name (kept for the many importers), this carries any stacked-
    thirds diatonic chord: ``pitches`` is ``[root, third, fifth]`` for a triad
    and ``[root, third, fifth, seventh]`` for a tetrad (ticket 09's V7).
    """

    key: str                 # display label, e.g. "G major"
    mode: str                # "major" | "natural_minor"
    scale_pitches: List[str]  # the parent scale's 7 pitch classes
    degree_index: int        # 0-based scale-degree index
    degree_number: int       # 1-based scale-degree number
    roman: str               # e.g. "ii", "V", "vii°", "V7"
    root: str                # spelled root pitch class, e.g. "D"
    chord_symbol: str        # e.g. "Dm", "G", "B°", "G7"
    chord_quality: str       # major | minor | diminished | augmented | dominant_seventh
    pitches: List[str]       # [root, third, fifth(, seventh)] spelled (no octave)
    midi_pitches: List[int]  # root-position MIDI numbers (treble register)
    interval_layer: str      # e.g. "m3+M3", "M3+m3+m3"
    function_label: str      # broad T/S/D category (+mediant)
    scale_degree_name: str   # tonic/supertonic/.../leading-tone/subtonic
    explanation_text: str

    @property
    def pitch_classes(self) -> List[int]:
        """The chord-tone pitch classes (0-11), order root/third/fifth(/seventh)."""
        return [note_pc(p) for p in self.pitches]


@dataclass(frozen=True)
class TriadAnalysis:
    """Result of identifying an arbitrary triad from raw pitches."""

    pitches: List[str]              # input pitches as given (cleaned)
    root: Optional[str]
    chord_quality: str              # may be "unknown"
    interval_layer: str
    chord_symbol: Optional[str]
    # Filled in only when a key/mode context is supplied and the root is diatonic
    key: Optional[str] = None
    mode: Optional[str] = None
    degree_index: Optional[int] = None
    roman: Optional[str] = None
    function_label: Optional[str] = None
    scale_degree_name: Optional[str] = None
    explanation_text: str = ""


# ---------------------------------------------------------------------------
# Pitch spelling utilities
# ---------------------------------------------------------------------------

def _normalise_accidental(acc: str) -> str:
    """Convert any accidental spelling to an ascii ``#``/``b`` string."""
    acc = (acc or "").strip()
    out = []
    for ch in acc:
        if ch in _ACCIDENTAL_NORMALISE:
            out.append(_ACCIDENTAL_NORMALISE[ch])
        elif ch == "x":  # 'x' is a common double-sharp shorthand
            out.append("##")
        else:
            out.append(ch)
    return "".join(out)


def parse_pitch_class(name: str) -> "tuple[str, int]":
    """Parse a pitch-class name (no octave required) into ``(letter, alter)``.

    ``alter`` is the signed accidental count (sharps positive, flats negative).
    Accepts ascii (``C#``, ``Eb``, ``Fbb``) and unicode (``F♯``, ``E♭``).
    """
    m = _PITCH_RE.match(name or "")
    if not m:
        raise ValueError(f"Cannot parse pitch name: {name!r}")
    letter = m.group(1).upper()
    acc = _normalise_accidental(m.group(2))
    alter = acc.count("#") - acc.count("b")
    return letter, alter


def alter_to_str(alter: int) -> str:
    """Convert a signed accidental count into a display string."""
    if alter == 0:
        return ""
    if alter > 0:
        return "#" * alter
    return "b" * (-alter)


def spell_pitch_class(letter: str, alter: int) -> str:
    """Build a spelled pitch-class name, e.g. ``("E", -1) -> "Eb"``."""
    return f"{letter}{alter_to_str(alter)}"


def note_pc(name: str) -> int:
    """Pitch class (0-11) of a spelled pitch-class name (octave ignored)."""
    letter, alter = parse_pitch_class(name)
    return (LETTER_BASE_PC[letter] + alter) % 12


def note_to_midi(letter_or_name: str, alter: Optional[int] = None,
                 octave: Optional[int] = None) -> int:
    """MIDI number for a spelled note.

    Two call styles are supported::

        note_to_midi("F#", 1, 4)        # letter, alter, octave (alter ignored
                                        # if name already carries accidentals)
        note_to_midi("F#4")             # single spelled-with-octave string

    Middle C (C4) is MIDI 60, matching the rest of the app.
    """
    if alter is None and octave is None:
        m = _PITCH_RE.match(letter_or_name or "")
        if not m or m.group(3) is None:
            raise ValueError(f"note_to_midi needs an octave: {letter_or_name!r}")
        letter = m.group(1).upper()
        a = _normalise_accidental(m.group(2))
        alt = a.count("#") - a.count("b")
        octv = int(m.group(3))
        return (octv + 1) * 12 + LETTER_BASE_PC[letter] + alt

    letter, parsed_alter = parse_pitch_class(letter_or_name)
    # If the name carried its own accidental, prefer it; otherwise use `alter`.
    eff_alter = parsed_alter if parsed_alter != 0 else (alter or 0)
    if octave is None:
        raise ValueError("octave is required when alter is given")
    return (octave + 1) * 12 + LETTER_BASE_PC[letter] + eff_alter


# ---------------------------------------------------------------------------
# Key parsing / signature
# ---------------------------------------------------------------------------

def parse_key(key: str) -> "tuple[str, Optional[str]]":
    """Split a key string into ``(tonic, mode_or_None)``.

    Accepts ``"C"``, ``"Eb"``, ``"C major"``, ``"A minor"``,
    ``"A natural minor"``, ``"A harmonic minor"``.  The mode (when present) is
    returned canonicalised to ``"major"`` / ``"natural_minor"`` /
    ``"harmonic_minor"``; otherwise ``None``.  A plain ``"minor"`` stays
    natural minor -- the raised leading tone is opted into, never implied.
    """
    m = _TONIC_RE.match(key or "")
    if not m:
        raise ValueError(f"Cannot parse key: {key!r}")
    tonic = m.group(1).upper() + _normalise_accidental(m.group(2))
    rest = (m.group(3) or "").strip().lower()
    mode: Optional[str] = None
    if rest:
        if "harmonic" in rest and "minor" in rest:
            mode = "harmonic_minor"
        elif "minor" in rest:
            mode = "natural_minor"
        elif "major" in rest:
            mode = "major"
    return tonic, mode


def _canon_mode(mode: str) -> str:
    m = (mode or "").strip().lower().replace("-", "_").replace(" ", "_")
    if m in ("major", "maj", "ionian"):
        return "major"
    if m in ("natural_minor", "minor", "min", "aeolian", "natural"):
        return "natural_minor"
    if m in ("harmonic_minor", "harmonic"):
        return "harmonic_minor"
    raise ValueError(
        f"Unsupported mode: {mode!r} (use 'major', 'natural_minor' or "
        f"'harmonic_minor')")


def _mode_word(mode: str) -> str:
    """Short label used in key strings: major -> 'major', minor -> 'minor'.

    Both minors share ``"minor"``: the *key* of a harmonic-minor drill is
    still "A minor"; the raised leading tone is a scale form, not a new key.
    """
    return "major" if mode == "major" else "minor"


def _mode_label(mode: str) -> str:
    """Long prose label: 'major' / 'natural minor' / 'harmonic minor'."""
    return "major" if mode == "major" else mode.replace("_", " ")


def _mode_tables(mode: str) -> "tuple[List[str], List[str]]":
    """``(function_labels, degree_names)`` for a canonical mode."""
    if mode == "major":
        return _FUNCTION_LABELS_MAJOR, _DEGREE_NAMES_MAJOR
    if mode == "harmonic_minor":
        return _FUNCTION_LABELS_HARMONIC_MINOR, _DEGREE_NAMES_HARMONIC_MINOR
    return _FUNCTION_LABELS_MINOR, _DEGREE_NAMES_MINOR


def key_signature_fifths(key: str, mode: str) -> int:
    """Number of sharps (positive) or flats (negative) in the key signature."""
    tonic, _ = parse_key(key)
    mode = _canon_mode(mode)
    letter, alter = parse_pitch_class(tonic)
    base = _BASE_FIFTHS_MAJOR if mode == "major" else _BASE_FIFTHS_MINOR
    return base[letter] + 7 * alter


# ---------------------------------------------------------------------------
# Scale generation
# ---------------------------------------------------------------------------

def generate_scale(key: str, mode: str) -> Scale:
    """Generate a diatonic scale with correct enharmonic spelling.

    Each of the seven letters is used exactly once (in order from the tonic),
    and the accidental on each is whatever is required to land on the correct
    pitch class -- this guarantees, e.g., that F# major spells its 7th degree
    as ``E#`` (not ``F``) and that Eb major never shows ``D#``.
    """
    mode = _canon_mode(mode)
    tonic, _ = parse_key(key)
    tonic_letter, tonic_alter = parse_pitch_class(tonic)
    tonic_pc = (LETTER_BASE_PC[tonic_letter] + tonic_alter) % 12
    steps = _MODE_STEPS[mode]

    start = LETTER_INDEX[tonic_letter]
    base_octave = 4

    pitches: List[str] = []
    midis: List[int] = []
    for i in range(7):
        letter = LETTERS[(start + i) % 7]
        octave = base_octave + (start + i) // 7
        target_pc = (tonic_pc + steps[i]) % 12
        natural = LETTER_BASE_PC[letter]
        # Signed minimal alteration to reach target_pc (range -6..+5; diatonic
        # scales only ever need -2..+2).
        alter = ((target_pc - natural + 6) % 12) - 6
        pitches.append(spell_pitch_class(letter, alter))
        midis.append((octave + 1) * 12 + natural + alter)

    fifths = key_signature_fifths(tonic, mode)
    return Scale(
        key=f"{tonic} {_mode_word(mode)}",
        mode=mode,
        tonic=tonic,
        scale_pitches=pitches,
        midi_pitches=midis,
        fifths=fifths,
    )


# ---------------------------------------------------------------------------
# Triad quality / interval analysis
# ---------------------------------------------------------------------------

def _interval_name(semitones: int) -> str:
    """Name a stacked-third interval (3 -> m3, 4 -> M3); else 'i<semitones>'."""
    if semitones == 3:
        return "m3"
    if semitones == 4:
        return "M3"
    return f"i{semitones}"


def _classify_thirds(lower: int, upper: int) -> str:
    """Quality from the two stacked thirds (in semitones)."""
    table = {
        (4, 3): "major",
        (3, 4): "minor",
        (3, 3): "diminished",
        (4, 4): "augmented",
    }
    return table.get((lower, upper), "unknown")


def _layer_string(lower: int, upper: int) -> str:
    return f"{_interval_name(lower)}+{_interval_name(upper)}"


# ---------------------------------------------------------------------------
# Diatonic triad generation
# ---------------------------------------------------------------------------

def _stack_voicing_midi(names: List[str], base_octave: int = 4) -> List[int]:
    """Root-position MIDI numbers, ascending, preserving letter spelling.

    Octaves are assigned by stacking letters (root, +2 letters per chord tone)
    so that enharmonic spellings such as B#/Cb keep their notated octave while
    the sounding pitches still ascend.  Works for triads and tetrads alike.
    """
    r_letter, _ = parse_pitch_class(names[0])
    r_idx = LETTER_INDEX[r_letter]

    out = []
    for k, name in enumerate(names):
        letter, alter = parse_pitch_class(name)
        octave = base_octave + (r_idx + 2 * k) // 7
        out.append((octave + 1) * 12 + LETTER_BASE_PC[letter] + alter)
    return out


def _triad_voicing_midi(root_name: str, third_name: str, fifth_name: str,
                        base_octave: int = 4) -> List[int]:
    """Back-compat wrapper over :func:`_stack_voicing_midi` for triads."""
    return _stack_voicing_midi([root_name, third_name, fifth_name], base_octave)


def _build_triad(scale: Scale, i: int) -> DiatonicTriad:
    pitches = scale.scale_pitches
    root = pitches[i]
    third = pitches[(i + 2) % 7]
    fifth = pitches[(i + 4) % 7]

    rpc, tpc, fpc = note_pc(root), note_pc(third), note_pc(fifth)
    lower = (tpc - rpc) % 12
    upper = (fpc - tpc) % 12
    quality = _classify_thirds(lower, upper)
    layer = _layer_string(lower, upper)

    roman = ROMAN_NUMERALS[i]
    if quality in ("minor", "diminished"):
        roman = roman.lower()
    roman += _QUALITY_ROMAN_SUFFIX.get(quality, "")

    chord_symbol = root + _QUALITY_SYMBOL_SUFFIX.get(quality, "")

    function_labels, degree_names = _mode_tables(scale.mode)
    function_label = function_labels[i]
    degree_name = degree_names[i]

    midis = _triad_voicing_midi(root, third, fifth)

    mode_label = _mode_label(scale.mode)
    explanation = (
        f"In {scale.key}, {root} is scale degree {i + 1} ({degree_name}). "
        f"Stacking diatonic thirds (1–3–5) from {root} in the "
        f"{scale.tonic} {mode_label} scale gives {root}–{third}–{fifth}, "
        f"a {quality} triad ({layer}). Its harmonic function is {function_label}."
    )

    return DiatonicTriad(
        key=scale.key,
        mode=scale.mode,
        scale_pitches=list(pitches),
        degree_index=i,
        degree_number=i + 1,
        roman=roman,
        root=root,
        chord_symbol=chord_symbol,
        chord_quality=quality,
        pitches=[root, third, fifth],
        midi_pitches=midis,
        interval_layer=layer,
        function_label=function_label,
        scale_degree_name=degree_name,
        explanation_text=explanation,
    )


def generate_diatonic_triads(key: str, mode: str) -> List[DiatonicTriad]:
    """All seven diatonic triads of ``key``/``mode`` (degrees I..vii)."""
    scale = generate_scale(key, mode)
    return [_build_triad(scale, i) for i in range(7)]


# ---------------------------------------------------------------------------
# Diatonic tetrad (seventh chord) generation -- ticket 09 / plan G1
# ---------------------------------------------------------------------------

def _build_tetrad(scale: Scale, i: int) -> DiatonicTriad:
    """The diatonic seventh chord on 0-based degree ``i`` (1-3-5-7 stack).

    Quality is derived from the three stacked thirds via
    :data:`_TETRAD_QUALITIES`; qualities that table does not know yet come back
    as ``"unknown"`` (callers refuse them -- never mislabel).
    """
    pitches = scale.scale_pitches
    tones = [pitches[(i + 2 * k) % 7] for k in range(4)]
    pcs = [note_pc(p) for p in tones]
    thirds = tuple((pcs[k + 1] - pcs[k]) % 12 for k in range(3))
    quality = _TETRAD_QUALITIES.get(thirds, "unknown")
    layer = "+".join(_interval_name(s) for s in thirds)

    # Roman case follows the underlying triad (major/augmented upper case,
    # minor/diminished lower case); the seventh figure carries the TETRAD
    # quality (maj7 / 7 / ø7 / °7), never the triad's ° decoration — "vii°7"
    # would claim the fully diminished seventh the diatonic viiø7 is not.
    triad_quality = _classify_thirds(thirds[0], thirds[1])
    roman = ROMAN_NUMERALS[i]
    if triad_quality in ("minor", "diminished"):
        roman = roman.lower()
    roman += _TETRAD_ROMAN_SUFFIX.get(
        quality, _QUALITY_ROMAN_SUFFIX.get(triad_quality, "") + "7")

    root, third, fifth, seventh = tones
    chord_symbol = root + _QUALITY_SYMBOL_SUFFIX.get(quality, "7")

    function_labels, degree_names = _mode_tables(scale.mode)
    function_label = function_labels[i]
    degree_name = degree_names[i]

    mode_label = _mode_label(scale.mode)
    explanation = (
        f"In {scale.key}, {root} is scale degree {i + 1} ({degree_name}). "
        f"Stacking diatonic thirds (1–3–5–7) from {root} in the "
        f"{scale.tonic} {mode_label} scale gives {root}–{third}–{fifth}–{seventh}, "
        f"a {quality.replace('_', ' ')} chord ({layer}). "
    )
    if quality == "dominant_seventh":
        explanation += (
            f"Its third ({third}) and seventh ({seventh}) form a tritone — the "
            f"dissonance that drives the resolution "
            f"{third}→{pitches[0]} and {seventh}→{pitches[(i + 6) % 7]}. "
            f"Its harmonic function is {function_label}.")
    else:
        explanation += f"Its harmonic function is {function_label}."

    return DiatonicTriad(
        key=scale.key,
        mode=scale.mode,
        scale_pitches=list(pitches),
        degree_index=i,
        degree_number=i + 1,
        roman=roman,
        root=root,
        chord_symbol=chord_symbol,
        chord_quality=quality,
        pitches=tones,
        midi_pitches=_stack_voicing_midi(tones),
        interval_layer=layer,
        function_label=function_label,
        scale_degree_name=degree_name,
        explanation_text=explanation,
    )


def generate_diatonic_sevenths(key: str, mode: str) -> List[DiatonicTriad]:
    """All seven diatonic seventh chords of ``key``/``mode`` (1-3-5-7 stacks)."""
    mode = _canon_mode(mode)
    scale = generate_scale(key, mode)
    return [_build_tetrad(scale, i) for i in range(7)]


def seventh_tokens_for_mode(mode: str) -> List[str]:
    """The buildable seventh-chord Roman tokens of ``mode``, in degree order.

    Derived by actually building the chords (in an exemplar key -- the roman
    spellings are key-independent), so the list can never drift from what the
    engine produces.  Degrees whose tetrad quality is unsupported are omitted
    rather than listed under a dishonest label: major and natural minor keep
    all seven, harmonic minor yields five (its tonic minor-major and mediant
    augmented-major sevenths have no token).
    """
    mode = _canon_mode(mode)
    exemplar = "C" if mode == "major" else "A"
    return [c.roman for c in generate_diatonic_sevenths(exemplar, mode)
            if c.chord_quality in _TETRAD_ROMAN_SUFFIX]


def build_seventh_chord(token: str, key: str, mode: str = "major") -> DiatonicTriad:
    """The diatonic seventh chord ``token`` names, built in ``key``/``mode``.

    The built chord's roman must MATCH the requested token exactly: asking for
    ``V7`` in natural minor builds the degree-5 seventh and finds ``v7`` (a
    minor seventh -- the true minor-key V7 needs harmonic minor's raised
    leading tone), so it refuses rather than hand back a chord under a label
    it does not deserve.  Same honesty in the other direction (``v7`` in
    major is really ``V7``).
    """
    degree = parse_seventh_token(token)
    if degree is None:
        raise ValueError(
            f"Unsupported seventh token {token!r}; the buildable tokens are "
            f"{sorted(SEVENTH_DEGREE_TOKENS)}")
    mode = _canon_mode(mode)
    scale = generate_scale(key, mode)
    chord = _build_tetrad(scale, degree)
    if chord.roman != token or chord.chord_quality not in _TETRAD_ROMAN_SUFFIX:
        hint = (" The minor-key V7 needs harmonic minor's raised leading tone "
                "(mode 'harmonic_minor').") if token == "V7" else ""
        raise ValueError(
            f"{scale.key} has no diatonic {token}: its degree-{degree + 1} "
            f"seventh chord is {chord.roman} = {'–'.join(chord.pitches)} "
            f"({chord.interval_layer}).{hint}")
    return chord


def build_dominant_seventh(key: str, mode: str = "major") -> DiatonicTriad:
    """The dominant seventh (``V7``) of ``key`` -- major or harmonic minor
    (see :func:`build_seventh_chord` for why natural minor refuses)."""
    return build_seventh_chord("V7", key, mode)


# ---------------------------------------------------------------------------
# Transposition of degree / function patterns
# ---------------------------------------------------------------------------

def roman_token_to_index(token: str) -> int:
    """Map a Roman-numeral token (``"ii"``, ``"V"``, ``"vii°"``) to 0-based degree."""
    t = (token or "").strip()
    # Strip quality decorations / case to recover the bare numeral.
    t = t.replace("°", "").replace("o", "").replace("+", "").strip()
    t = t.upper()
    # Keep only I/V characters.
    t = re.sub(r"[^IV]", "", t)
    if t not in _ROMAN_TO_NUMBER:
        raise ValueError(f"Unrecognised Roman-numeral token: {token!r}")
    return _ROMAN_TO_NUMBER[t] - 1


def transpose_degree_pattern(pattern: List[str], key: str, mode: str) -> List[DiatonicTriad]:
    """Render a pattern of scale-degree Roman numerals into a key.

    Supported seventh tokens (:data:`SEVENTH_DEGREE_TOKENS`, e.g. ``"V7"``,
    ``"ii7"``, ``"viiø7"``) build their tetrad -- and raise when the token
    belongs to the other mode (see :func:`build_seventh_chord`); every other
    token is a diatonic triad.  Example::

        transpose_degree_pattern(["ii", "V", "I"], "C", "major")
        # -> [Dm, G, C]
        transpose_degree_pattern(["ii7", "V7", "I"], "G", "major")
        # -> [Am7, D7, G]
    """
    triads = generate_diatonic_triads(key, mode)
    out: List[DiatonicTriad] = []
    for tok in pattern:
        if parse_seventh_token(tok) is not None:
            out.append(build_seventh_chord(tok, key, mode))
        else:
            out.append(triads[roman_token_to_index(tok)])
    return out


# ---------------------------------------------------------------------------
# Triad identification from raw pitches
# ---------------------------------------------------------------------------

def _strip_octave(name: str) -> str:
    m = _PITCH_RE.match(name or "")
    if not m:
        raise ValueError(f"Cannot parse pitch: {name!r}")
    return m.group(1).upper() + _normalise_accidental(m.group(2))


def identify_triad_from_pitches(pitches: List[str],
                                key: Optional[str] = None) -> TriadAnalysis:
    """Classify a triad given as 3 pitches (root position or any inversion).

    The interval layer and quality follow the canonical table::

        C-E-G  = M3+m3 = major
        D-F-A  = m3+M3 = minor
        B-D-F  = m3+m3 = diminished
        C-E-G# = M3+M3 = augmented

    If ``key`` is supplied (e.g. ``"C major"`` or ``"A minor"``) and the
    identified root is diatonic, the Roman numeral / function / degree fields
    are filled in too.
    """
    cleaned = [_strip_octave(p) for p in pitches]
    if len(cleaned) != 3:
        return TriadAnalysis(
            pitches=cleaned, root=None, chord_quality="unknown",
            interval_layer="", chord_symbol=None,
        )

    # Collapse octave/enharmonic duplicates to distinct pitch classes; a triad
    # needs exactly three (e.g. C-B#-E has only two pitch classes -> unknown).
    distinct = list({note_pc(n): n for n in cleaned}.values())
    if len(distinct) != 3:
        return TriadAnalysis(
            pitches=cleaned, root=None, chord_quality="unknown",
            interval_layer="", chord_symbol=None,
        )

    root_name: Optional[str] = None
    third_name: Optional[str] = None
    fifth_name: Optional[str] = None
    lower = upper = -1

    # Try each note as a candidate root; pick the rotation that stacks thirds.
    for cand in distinct:
        rpc = note_pc(cand)
        others = sorted(
            (n for n in distinct if n is not cand),
            key=lambda n: (note_pc(n) - rpc) % 12,
        )
        i1 = (note_pc(others[0]) - rpc) % 12
        i2 = (note_pc(others[1]) - note_pc(others[0])) % 12
        if i1 in (3, 4) and i2 in (3, 4):
            root_name, third_name, fifth_name = cand, others[0], others[1]
            lower, upper = i1, i2
            break

    if root_name is None:
        # No tertian stacking found: report the literal stack (quality unknown).
        rpc = note_pc(distinct[0])
        lower = (note_pc(distinct[1]) - rpc) % 12
        upper = (note_pc(distinct[2]) - note_pc(distinct[1])) % 12
        root_name, third_name, fifth_name = distinct[0], distinct[1], distinct[2]

    quality = _classify_thirds(lower, upper)
    layer = _layer_string(lower, upper)
    chord_symbol = (root_name + _QUALITY_SYMBOL_SUFFIX.get(quality, "")
                    if quality != "unknown" else None)

    analysis = TriadAnalysis(
        pitches=cleaned,
        root=root_name,
        chord_quality=quality,
        interval_layer=layer,
        chord_symbol=chord_symbol,
    )

    if key is None:
        return analysis

    # --- Contextual analysis within a key -------------------------------
    tonic, parsed_mode = parse_key(key)
    mode = _canon_mode(parsed_mode or "major")
    triads = generate_diatonic_triads(tonic, mode)
    root_pc = note_pc(root_name)
    match = next((t for t in triads if note_pc(t.root) == root_pc), None)

    # Only adopt the diatonic degree's Roman / function / explanation when the
    # *played* quality matches that degree. A chromatically altered chord that
    # merely shares a root (e.g. a D-major chord in C major) must not be
    # mislabelled "ii"; fall back to the quality-only analysis instead.
    if match is None or match.chord_quality != quality:
        return analysis

    if match.root == root_name:
        explanation = match.explanation_text
    else:
        # Same pitch class, different spelling (e.g. Db vs C#): keep the degree
        # labels but describe the chord using the *input's* spelling so the
        # explanation never contradicts the reported root.
        explanation = (
            f"In {match.key}, {root_name} (enharmonic to {match.root}) is scale "
            f"degree {match.degree_index + 1} ({match.scale_degree_name}). "
            f"Stacking diatonic thirds (1–3–5) gives "
            f"{root_name}–{third_name}–{fifth_name}, a {quality} triad ({layer}). "
            f"Its harmonic function is {match.function_label}."
        )

    return TriadAnalysis(
        pitches=cleaned,
        root=root_name,
        chord_quality=quality,
        interval_layer=layer,
        chord_symbol=chord_symbol,
        key=match.key,
        mode=mode,
        degree_index=match.degree_index,
        roman=match.roman,
        function_label=match.function_label,
        scale_degree_name=match.scale_degree_name,
        explanation_text=explanation,
    )
