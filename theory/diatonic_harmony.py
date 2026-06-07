"""Diatonic harmony theory for major and natural-minor keys.

This module is the *pedagogical contract* for the Diatonic Harmony Trainer.
It is pure Python (standard library only) so it can be unit-tested without a
display, MIDI device, Verovio, or Qt.

Scope (first slice)
-------------------
* Major and natural-minor diatonic triads only.
* Root-position triads.
* No harmonic/melodic minor, secondary dominants, cadences, or seventh chords
  yet -- but the data model is designed so those extend without refactoring:
  quality (and therefore Roman-numeral case, chord symbol, and function) is
  always *derived* from the actual interval content, never hard-coded per mode.
  A future ``harmonic_minor`` mode only needs a new scale-step pattern.

Triad interval layers (the canonical table)
-------------------------------------------
* major       = M3 + m3
* minor       = m3 + M3
* diminished  = m3 + m3
* augmented   = M3 + M3

Public API
----------
* :func:`generate_scale`
* :func:`generate_diatonic_triads`
* :func:`transpose_degree_pattern`
* :func:`identify_triad_from_pitches`
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

try:  # Python 3.8+ has Literal in typing
    from typing import Literal

    Mode = Literal["major", "natural_minor"]
except Exception:  # pragma: no cover - defensive only
    Mode = str  # type: ignore


__all__ = [
    "Scale",
    "DiatonicTriad",
    "TriadAnalysis",
    "generate_scale",
    "generate_diatonic_triads",
    "transpose_degree_pattern",
    "identify_triad_from_pitches",
    "key_signature_fifths",
    "note_to_midi",
    "QUALITY_TO_INTERVAL_LAYER",
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

_MODE_STEPS = {
    "major": MAJOR_STEPS,
    "natural_minor": NATURAL_MINOR_STEPS,
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

#: Canonical interval-layer string per triad quality.
QUALITY_TO_INTERVAL_LAYER = {
    "major": "M3+m3",
    "minor": "m3+M3",
    "diminished": "m3+m3",
    "augmented": "M3+M3",
}

#: chord-symbol suffix per quality.
_QUALITY_SYMBOL_SUFFIX = {
    "major": "",
    "minor": "m",
    "diminished": "°",  # °
    "augmented": "+",
}

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
    """A single diatonic triad with its full pedagogical annotation."""

    key: str                 # display label, e.g. "G major"
    mode: str                # "major" | "natural_minor"
    scale_pitches: List[str]  # the parent scale's 7 pitch classes
    degree_index: int        # 0-based scale-degree index
    degree_number: int       # 1-based scale-degree number
    roman: str               # e.g. "ii", "V", "vii°"
    root: str                # spelled root pitch class, e.g. "D"
    chord_symbol: str        # e.g. "Dm", "G", "B°"
    chord_quality: str       # "major" | "minor" | "diminished" | "augmented"
    pitches: List[str]       # [root, third, fifth] spelled (no octave)
    midi_pitches: List[int]  # root-position MIDI numbers (treble register)
    interval_layer: str      # e.g. "m3+M3"
    function_label: str      # broad T/S/D category (+mediant)
    scale_degree_name: str   # tonic/supertonic/.../leading-tone/subtonic
    explanation_text: str

    @property
    def pitch_classes(self) -> List[int]:
        """The three chord-tone pitch classes (0-11), order root/third/fifth."""
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
    ``"A natural minor"``.  The mode (when present) is returned canonicalised to
    ``"major"`` / ``"natural_minor"``; otherwise ``None``.
    """
    m = _TONIC_RE.match(key or "")
    if not m:
        raise ValueError(f"Cannot parse key: {key!r}")
    tonic = m.group(1).upper() + _normalise_accidental(m.group(2))
    rest = (m.group(3) or "").strip().lower()
    mode: Optional[str] = None
    if rest:
        if "minor" in rest:
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
    raise ValueError(f"Unsupported mode: {mode!r} (use 'major' or 'natural_minor')")


def _mode_word(mode: str) -> str:
    """Short label used in key strings: major -> 'major', minor -> 'minor'."""
    return "major" if mode == "major" else "minor"


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

def _triad_voicing_midi(root_name: str, third_name: str, fifth_name: str,
                        base_octave: int = 4) -> List[int]:
    """Root-position MIDI numbers, ascending, preserving letter spelling.

    Octaves are assigned by stacking letters (root, +2 letters, +4 letters) so
    that enharmonic spellings such as B#/Cb keep their notated octave while the
    sounding pitches still ascend.
    """
    r_letter, r_alter = parse_pitch_class(root_name)
    r_idx = LETTER_INDEX[r_letter]

    out = []
    for name, step in ((root_name, 0), (third_name, 2), (fifth_name, 4)):
        letter, alter = parse_pitch_class(name)
        octave = base_octave + (r_idx + step) // 7
        out.append((octave + 1) * 12 + LETTER_BASE_PC[letter] + alter)
    return out


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

    if scale.mode == "major":
        function_label = _FUNCTION_LABELS_MAJOR[i]
        degree_name = _DEGREE_NAMES_MAJOR[i]
    else:
        function_label = _FUNCTION_LABELS_MINOR[i]
        degree_name = _DEGREE_NAMES_MINOR[i]

    midis = _triad_voicing_midi(root, third, fifth)

    mode_label = "major" if scale.mode == "major" else "natural minor"
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

    Example::

        transpose_degree_pattern(["ii", "V", "I"], "C", "major")
        # -> [Dm, G, C]
        transpose_degree_pattern(["ii", "V", "I"], "G", "major")
        # -> [Am, D, G]
    """
    triads = generate_diatonic_triads(key, mode)
    return [triads[roman_token_to_index(tok)] for tok in pattern]


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
