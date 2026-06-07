"""Exercise-spec format and compiler for the Diatonic Harmony Trainer.

An *exercise spec* is a small JSON-compatible description of a drill.  The
compiler expands it deterministically into an ordered list of
:class:`~theory.diatonic_harmony.DiatonicTriad` objects (one per chord to play),
each tagged with how it should be rendered (block / arpeggio) and a group label.

Four drill families are supported (matching the spec):

* ``horizontal_degree`` -- one scale degree across many keys
  (e.g. "all V triads in major keys").
* ``full_key``          -- all seven diatonic triads of one key.
* ``quality``           -- all diatonic triads of a chosen quality across keys.
* ``function``          -- a functional / Roman-numeral pattern across keys
  (e.g. "ii–V–I", "I–IV–V–I", "T–S–D–T", "vi–ii–V–I").

The schema is intentionally open for later extension (inversions, seventh
chords, cadences) without breaking existing fields.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

from theory.diatonic_harmony import (
    DiatonicTriad,
    generate_diatonic_triads,
    transpose_degree_pattern,
    roman_token_to_index,
    parse_key,
    _canon_mode,
    _mode_word,
)


SCHEMA_VERSION = "harmony-trainer/v1"

#: 12 major keys, chromatic ascending, with practical spellings (<=6 accidentals).
DEFAULT_MAJOR_KEYS = [
    "C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B",
]
#: 12 natural-minor keys, chromatic ascending, with practical spellings.
DEFAULT_MINOR_KEYS = [
    "A", "Bb", "B", "C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#",
]

#: Functional shorthand accepted inside ``function`` patterns.
_FUNCTION_TOKEN_TO_ROMAN = {
    "T": "I", "TONIC": "I",
    "S": "IV", "SD": "IV", "SUBDOMINANT": "IV",
    "PD": "ii", "PREDOMINANT": "ii",
    "D": "V", "DOMINANT": "V",
}

_VALID_DRILLS = {"horizontal_degree", "full_key", "quality", "function"}
_VALID_RENDER = {"block", "arpeggio"}
_VALID_QUALITY = {"major", "minor", "diminished", "augmented"}


# ---------------------------------------------------------------------------
# Spec dataclass
# ---------------------------------------------------------------------------

@dataclass
class HarmonyExerciseSpec:
    """A JSON-compatible description of a single trainer exercise."""

    exercise_id: str
    title: str
    drill: str                      # one of _VALID_DRILLS
    render: str = "block"           # "block" | "arpeggio"
    mode: str = "major"             # "major" | "natural_minor"
    description: str = ""

    # drill-specific parameters (only the relevant ones are used)
    degree: Optional[str] = None        # horizontal_degree, e.g. "V"
    key: Optional[str] = None           # full_key, e.g. "Eb major"
    quality: Optional[str] = None       # quality drill, e.g. "diminished"
    pattern: Optional[List[str]] = None  # function drill, e.g. ["ii", "V", "I"]
    keys: Optional[List[str]] = None     # explicit key list (else mode default)

    def validate(self) -> None:
        if self.drill not in _VALID_DRILLS:
            raise ValueError(f"Unknown drill {self.drill!r}; expected {_VALID_DRILLS}")
        if self.render not in _VALID_RENDER:
            raise ValueError(f"Unknown render {self.render!r}; expected {_VALID_RENDER}")
        self.mode = _canon_mode(self.mode)
        if self.drill == "horizontal_degree" and not self.degree:
            raise ValueError("horizontal_degree drill requires 'degree'")
        if self.drill == "full_key" and not self.key:
            raise ValueError("full_key drill requires 'key'")
        if self.drill == "quality":
            if not self.quality:
                raise ValueError("quality drill requires 'quality'")
            if self.quality not in _VALID_QUALITY:
                raise ValueError(f"Unknown quality {self.quality!r}")
        if self.drill == "function" and not self.pattern:
            raise ValueError("function drill requires 'pattern'")

    # --- JSON round-tripping ------------------------------------------
    def to_dict(self) -> Dict:
        d = {k: v for k, v in asdict(self).items() if v is not None}
        d["schema"] = SCHEMA_VERSION
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> "HarmonyExerciseSpec":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        kwargs = {k: v for k, v in d.items() if k in known}
        spec = cls(**kwargs)
        spec.validate()
        return spec


# ---------------------------------------------------------------------------
# Compiled output
# ---------------------------------------------------------------------------

@dataclass
class CompiledChord:
    """A single chord to be played, with render style and grouping."""

    triad: DiatonicTriad
    render: str          # "block" | "arpeggio"
    group: str           # label grouping consecutive chords (e.g. the key)
    index: int           # 0-based position within the exercise


@dataclass
class CompiledExercise:
    """The fully expanded, deterministic chord stream for an exercise."""

    spec: HarmonyExerciseSpec
    title: str
    chords: List[CompiledChord] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.chords)


# ---------------------------------------------------------------------------
# Pattern normalisation
# ---------------------------------------------------------------------------

def normalise_pattern(pattern: List[str]) -> List[str]:
    """Translate a mixed Roman / functional pattern into Roman numerals.

    ``["T", "S", "D", "T"]`` -> ``["I", "IV", "V", "I"]``;
    Roman tokens (``"ii"``, ``"V"``, ``"vii°"``) pass through unchanged.
    """
    out: List[str] = []
    for tok in pattern:
        raw = (tok or "").strip()
        upper = raw.upper()
        if upper in _FUNCTION_TOKEN_TO_ROMAN:
            out.append(_FUNCTION_TOKEN_TO_ROMAN[upper])
            continue
        # Validate it is a parseable Roman token (raises otherwise).
        roman_token_to_index(raw)
        out.append(raw)
    return out


def _keys_for(spec: HarmonyExerciseSpec) -> List[str]:
    if spec.keys:
        return list(spec.keys)
    return DEFAULT_MAJOR_KEYS if spec.mode == "major" else DEFAULT_MINOR_KEYS


def _key_label(key: str, mode: str) -> str:
    tonic, _ = parse_key(key)
    return f"{tonic} {_mode_word(mode)}"


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------

def compile_exercise(spec: HarmonyExerciseSpec) -> CompiledExercise:
    """Expand a spec into a deterministic, ordered list of chords."""
    spec.validate()
    mode = spec.mode
    chords: List[CompiledChord] = []

    def add(triad: DiatonicTriad, group: str) -> None:
        chords.append(CompiledChord(
            triad=triad, render=spec.render, group=group, index=len(chords),
        ))

    if spec.drill == "horizontal_degree":
        idx = roman_token_to_index(spec.degree)  # validate token early
        for key in _keys_for(spec):
            triad = generate_diatonic_triads(key, mode)[idx]
            add(triad, _key_label(key, mode))

    elif spec.drill == "full_key":
        key = spec.key
        _, parsed_mode = parse_key(key)
        if parsed_mode:
            mode = parsed_mode
        for triad in generate_diatonic_triads(key, mode):
            add(triad, _key_label(key, mode))

    elif spec.drill == "quality":
        want = spec.quality
        for key in _keys_for(spec):
            for triad in generate_diatonic_triads(key, mode):
                if triad.chord_quality == want:
                    add(triad, _key_label(key, mode))

    elif spec.drill == "function":
        roman_pattern = normalise_pattern(spec.pattern)
        pattern_label = "–".join(spec.pattern)
        for key in _keys_for(spec):
            triads = transpose_degree_pattern(roman_pattern, key, mode)
            group = f"{pattern_label} in {_key_label(key, mode)}"
            for triad in triads:
                add(triad, group)

    else:  # pragma: no cover - validate() guards this
        raise ValueError(f"Unhandled drill: {spec.drill}")

    return CompiledExercise(spec=spec, title=spec.title, chords=chords)


# ---------------------------------------------------------------------------
# JSON file helpers
# ---------------------------------------------------------------------------

def load_specs(path) -> List[HarmonyExerciseSpec]:
    """Load one or more specs from a JSON file.

    Accepts either a single spec object or ``{"exercises": [ ... ]}``.
    """
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(obj, dict) and "exercises" in obj:
        return [HarmonyExerciseSpec.from_dict(e) for e in obj["exercises"]]
    if isinstance(obj, list):
        return [HarmonyExerciseSpec.from_dict(e) for e in obj]
    return [HarmonyExerciseSpec.from_dict(obj)]


def save_specs(path, specs: List[HarmonyExerciseSpec]) -> None:
    payload = {
        "schema": SCHEMA_VERSION,
        "exercises": [s.to_dict() for s in specs],
    }
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                          encoding="utf-8")


# ---------------------------------------------------------------------------
# Demo specs (used by run_harmony_trainer_demo.py)
# ---------------------------------------------------------------------------

def default_demo_specs() -> List[HarmonyExerciseSpec]:
    """The first-slice demo set required by the acceptance criteria."""
    return [
        HarmonyExerciseSpec(
            exercise_id="c_major_all_triads",
            title="C major — all seven diatonic triads",
            drill="full_key", render="block", mode="major", key="C major",
            description="I ii iii IV V vi vii° in C major (block triads).",
        ),
        HarmonyExerciseSpec(
            exercise_id="g_major_all_triads",
            title="G major — all seven diatonic triads",
            drill="full_key", render="block", mode="major", key="G major",
            description="I ii iii IV V vi vii° in G major (block triads).",
        ),
        HarmonyExerciseSpec(
            exercise_id="ii_v_i_c_g_d",
            title="ii–V–I in C, G, and D major",
            drill="function", render="block", mode="major",
            pattern=["ii", "V", "I"], keys=["C", "G", "D"],
            description="The ii–V–I progression transposed across three keys.",
        ),
        HarmonyExerciseSpec(
            exercise_id="all_V_major",
            title="All V triads across major keys (horizontal degree)",
            drill="horizontal_degree", render="block", mode="major", degree="V",
            description="The dominant triad in all 12 major keys.",
        ),
        HarmonyExerciseSpec(
            exercise_id="a_minor_all_triads_arp",
            title="A natural minor — all triads (arpeggiated)",
            drill="full_key", render="arpeggio", mode="natural_minor",
            key="A minor",
            description="i ii° III iv v VI VII in A natural minor (arpeggios).",
        ),
    ]
