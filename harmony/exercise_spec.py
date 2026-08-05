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
from collections import OrderedDict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

from theory.diatonic_harmony import (
    DiatonicTriad,
    generate_diatonic_triads,
    generate_diatonic_sevenths,
    transpose_degree_pattern,
    roman_token_to_index,
    parse_seventh_token,
    seventh_tokens_for_mode,
    SEVENTH_QUALITY_LABELS,
    key_signature_fifths,
    parse_key,
    _canon_mode,
    _mode_word,
)
from harmony.harmonic_roles import FUNCTION_TOKEN_ALIASES, FUNCTION_EXEMPLAR_DEGREE


SCHEMA_VERSION = "harmony-trainer/v1"

#: 12 major keys, chromatic ascending, with practical spellings (<=6 accidentals).
DEFAULT_MAJOR_KEYS = [
    "C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B",
]
#: 12 natural-minor keys, chromatic ascending, with practical spellings.
DEFAULT_MINOR_KEYS = [
    "A", "Bb", "B", "C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#",
]

_VALID_DRILLS = {"horizontal_degree", "full_key", "quality", "function"}
_VALID_RENDER = {"block", "arpeggio"}
#: Seventh-chord qualities the quality drill accepts (ticket 10 / plan G1b),
#: derived from the theory module's canonical label table so the two can
#: never drift.  ``diminished_seventh`` is refused at validation: no diatonic
#: °7 exists in the supported modes (it arrives with harmonic minor, plan G2).
_SEVENTH_QUALITIES = frozenset(SEVENTH_QUALITY_LABELS)
_VALID_QUALITY = {"major", "minor", "diminished", "augmented"} | _SEVENTH_QUALITIES
#: How the learner answers a drill (plan U2, ticket 06).  ``midi`` is the
#: classic play-the-chord flow (hardware, on-screen piano, or QWERTY — all
#: three feed the same grader); ``mcq`` renders a multiple-choice strip for
#: identification drills; ``card`` turns the chord-card list into the answer
#: surface (click the matching card).
_VALID_ANSWER_MODES = {"midi", "mcq", "card"}

#: How the exercise is presented (plan A1, ticket 07).  ``visual`` is the
#: classic notation-first drill; ``echo`` is its aural twin — the target plays
#: with the notation hidden.  With ``answer_mode="midi"`` the learner plays
#: back what they hear; with ``answer_mode="mcq"`` they *identify* what they
#: hear from the answer strip (the A1 ID drills, ticket 10).  ``card`` cannot
#: be echoed: the card list is the answer surface and is withheld while the
#: notation is veiled.
_VALID_PRESENTATIONS = {"visual", "echo"}

#: What an ``mcq`` answer strip asks for (ticket 10).  ``roman`` is the
#: classic which-degree-is-this question; ``quality`` asks for the chord
#: quality (the hear-a-seventh drill's Mm7 / mm7 / MM7 / ø7 / °7).
_VALID_MCQ_FOCUS = {"roman", "quality"}

#: Readability cap: the maximum number of chords (== measures) in a single
#: spec.  It matches the project's existing shipped demo ("all V across the
#: 12 keys" = 12 measures), the de-facto single-exercise length; the trainer
#: renders a single Verovio page, so chords past the cap would land on a
#: hidden second page.  The default builders split long drills (function
#: patterns, multi-degree quality drills across all 12 keys) into several
#: specs by key-group, and ``validate()`` enforces the cap for *every* spec,
#: including hand-authored JSON and bridge-supplied ones (plan F6).
MAX_CHORDS_PER_SPEC = 12

#: Quality-cased Roman labels for each diatonic degree.  Used in titles and as
#: ``horizontal_degree`` tokens (``roman_token_to_index`` tolerates the case and
#: the ``°`` decoration, so e.g. "vii°" and "ii°" resolve to the right index).
_MAJOR_DEGREE_LABELS = ["I", "ii", "iii", "IV", "V", "vi", "vii°"]
_MINOR_DEGREE_LABELS = ["i", "ii°", "III", "iv", "v", "VI", "VII"]

#: Functional shorthand accepted inside ``function`` patterns.  Derived from the single
#: function vocabulary (ticket 01 / plan F1): each alias resolves to the exemplar degree its
#: function name denotes (T -> I, S/SD -> IV, PD -> ii, D -> V) -- never hand-edit.
_FUNCTION_TOKEN_TO_ROMAN = {
    alias: _MAJOR_DEGREE_LABELS[FUNCTION_EXEMPLAR_DEGREE[name]]
    for name, aliases in FUNCTION_TOKEN_ALIASES.items()
    for alias in aliases
}

#: Function/Roman patterns required by the trainer, grouped by mode.  Each entry
#: is ``(tokens, display_label)``.
_FUNCTION_PATTERNS_MAJOR = [
    (["I", "IV", "V", "I"], "I–IV–V–I"),
    (["ii", "V", "I"], "ii–V–I"),
    (["vi", "ii", "V", "I"], "vi–ii–V–I"),
]
_FUNCTION_PATTERNS_MINOR = [
    (["i", "iv", "v", "i"], "i–iv–v–i"),
    (["i", "VI", "VII", "i"], "i–VI–VII–i"),
]

#: The six launcher groups, in display order.
GROUP_MAJOR_FULL_KEY = "Major full-key drills"
GROUP_MINOR_FULL_KEY = "Minor full-key drills"
GROUP_DEGREE = "Degree transposition drills"
GROUP_QUALITY = "Quality recognition drills"
GROUP_FUNCTION = "Function drills"
GROUP_ARPEGGIO = "Arpeggio drills"
#: Opt-in launcher group for the no-MIDI identification drills (plan U2).
#: NOT part of ``default_exercise_groups()`` — see ``identification_demo_specs``.
GROUP_IDENTIFY = "Identification drills (no MIDI needed)"


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
    answer_mode: str = "midi"            # one of _VALID_ANSWER_MODES (plan U2)
    presentation: str = "visual"         # one of _VALID_PRESENTATIONS (plan A1)
    mcq_focus: str = "roman"             # one of _VALID_MCQ_FOCUS (ticket 10)

    def validate(self) -> None:
        if self.drill not in _VALID_DRILLS:
            raise ValueError(f"Unknown drill {self.drill!r}; expected {_VALID_DRILLS}")
        if self.render not in _VALID_RENDER:
            raise ValueError(f"Unknown render {self.render!r}; expected {_VALID_RENDER}")
        if self.answer_mode not in _VALID_ANSWER_MODES:
            raise ValueError(
                f"Unknown answer_mode {self.answer_mode!r}; expected "
                f"{sorted(_VALID_ANSWER_MODES)}")
        if self.presentation not in _VALID_PRESENTATIONS:
            raise ValueError(
                f"Unknown presentation {self.presentation!r}; expected "
                f"{sorted(_VALID_PRESENTATIONS)}")
        if self.presentation == "echo" and self.answer_mode == "card":
            raise ValueError(
                "presentation='echo' cannot use answer_mode='card': the card "
                "list is the answer surface and is withheld while the "
                "notation is veiled. Echo drills answer by midi (play back "
                "what you hear) or mcq (identify what you hear).")
        if self.mcq_focus not in _VALID_MCQ_FOCUS:
            raise ValueError(
                f"Unknown mcq_focus {self.mcq_focus!r}; expected "
                f"{sorted(_VALID_MCQ_FOCUS)}")
        if self.mcq_focus != "roman" and self.answer_mode != "mcq":
            raise ValueError(
                "mcq_focus is an mcq-only knob: set answer_mode='mcq' or "
                "leave mcq_focus at its default")
        self.mode = _canon_mode(self.mode)
        if self.drill == "horizontal_degree":
            if not self.degree:
                raise ValueError("horizontal_degree drill requires 'degree'")
            if any(ch.isdigit() for ch in self.degree):
                raise ValueError(
                    f"horizontal_degree drills transpose triads; for a "
                    f"seventh chord across the keys ({self.degree!r}) use a "
                    f"quality drill (e.g. quality='dominant_seventh') or a "
                    f"function drill with a seventh-token pattern.")
        if self.drill == "full_key" and not self.key:
            raise ValueError("full_key drill requires 'key'")
        if self.drill == "quality":
            if not self.quality:
                raise ValueError("quality drill requires 'quality'")
            if self.quality not in _VALID_QUALITY:
                raise ValueError(f"Unknown quality {self.quality!r}")
            if self.quality == "augmented":
                raise ValueError(
                    "quality='augmented' is not drillable yet: no augmented "
                    "triad is diatonic to major or natural minor, so the "
                    "drill would compile to zero chords and the score "
                    "builder would fail. Augmented drills arrive with "
                    "harmonic minor's III+.")
            if self.quality == "diminished_seventh":
                raise ValueError(
                    "quality='diminished_seventh' is not drillable yet: no "
                    "fully diminished seventh is diatonic to major or "
                    "natural minor (viiø7 / iiø7 are HALF-diminished), so "
                    "the drill would compile to zero chords. The °7 arrives "
                    "with harmonic minor's raised leading tone (plan G2).")
        if self.drill == "function":
            if not self.pattern:
                raise ValueError("function drill requires 'pattern'")
            # Raises on unsupported figured / seventh tokens (honesty: never
            # silently downgrade "ii7" to a ii triad).
            roman = normalise_pattern(self.pattern)
            allowed = None
            for t in roman:
                if parse_seventh_token(t) is None:
                    continue
                if allowed is None:
                    allowed = set(seventh_tokens_for_mode(self.mode))
                if t not in allowed:
                    raise ValueError(
                        f"{t!r} is not diatonic to {_mode_word(self.mode)}: "
                        f"the {_mode_word(self.mode)} seventh vocabulary is "
                        f"{seventh_tokens_for_mode(self.mode)}. (The "
                        f"minor-key V7 needs harmonic minor's raised leading "
                        f"tone, plan G2.)")

        # Reject theoretical keys that need more than 7 sharps/flats (e.g.
        # "G# major" = 8 sharps); MusicXML key signatures only span -7..+7.
        for k in self._all_keys():
            self._check_key_range(k)

        # Enforce the readability cap: the trainer renders a single Verovio
        # page, so chords past the cap would land on a hidden second page.
        n = self._expected_chord_count()
        if n > MAX_CHORDS_PER_SPEC:
            raise ValueError(
                f"Spec {self.exercise_id!r} compiles to {n} chords; the "
                f"single-page readability cap is {MAX_CHORDS_PER_SPEC} "
                f"(chords past the cap would render on a hidden second "
                f"page). Split the drill into shorter specs, e.g. by "
                f"scoping 'keys' to fewer keys.")

    def _expected_chord_count(self) -> int:
        """How many chords :func:`compile_exercise` will emit for this spec.

        Mirrors the compiler's per-drill expansion exactly, without building
        the triads for the non-``quality`` drills.
        """
        if self.drill == "full_key":
            return 7
        keys = _keys_for(self)
        if self.drill == "horizontal_degree":
            return len(keys)
        if self.drill == "function":
            return len(self.pattern or []) * len(keys)
        return sum(len(_triads_of_quality(k, self.mode, self.quality))
                   for k in keys)

    def _all_keys(self) -> List[str]:
        keys: List[str] = []
        if self.key:
            keys.append(self.key)
        keys.extend(self.keys or [])
        return keys

    def _check_key_range(self, key: str) -> None:
        tonic, parsed_mode = parse_key(key)
        mode = _canon_mode(parsed_mode) if parsed_mode else self.mode
        fifths = key_signature_fifths(tonic, mode)
        if not -7 <= fifths <= 7:
            raise ValueError(
                f"Key {key!r} needs {fifths} sharps/flats; MusicXML key "
                f"signatures only support -7..+7. Use the practical enharmonic "
                f"spelling instead (e.g. Ab major rather than G# major)."
            )

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
    Roman tokens (``"ii"``, ``"V"``, ``"vii°"``) pass through unchanged, as do
    the supported seventh tokens (``"V7"``).  Any *other* digit-bearing token
    (``"ii7"``, ``"V9"``, a figured ``"ii6"``) raises: the tolerant
    ``roman_token_to_index`` would silently strip the digits and play a
    root-position triad under a label it does not match -- exactly the
    dishonesty the roman gate exists to prevent.
    """
    out: List[str] = []
    for tok in pattern:
        raw = (tok or "").strip()
        upper = raw.upper()
        if upper in _FUNCTION_TOKEN_TO_ROMAN:
            out.append(_FUNCTION_TOKEN_TO_ROMAN[upper])
            continue
        if parse_seventh_token(raw) is not None:
            out.append(raw)
            continue
        if any(ch.isdigit() for ch in raw):
            raise ValueError(
                f"Unsupported chord token {raw!r}: the buildable seventh "
                f"tokens are the diatonic vocabulary (Imaj7, ii7, ..., viiø7 "
                f"and natural minor's i7 ... VII7); figured-bass suffixes "
                f"(6, 6/4) belong to Lab cadence specs, not trainer patterns.")
        # Validate it is a parseable Roman token (raises otherwise).
        roman_token_to_index(raw)
        out.append(raw)
    return out


def _keys_for(spec: HarmonyExerciseSpec) -> List[str]:
    if spec.keys:
        return list(spec.keys)
    return DEFAULT_MAJOR_KEYS if spec.mode == "major" else DEFAULT_MINOR_KEYS


def _triads_of_quality(key: str, mode: str, quality: str) -> List[DiatonicTriad]:
    """The diatonic chords of ``key``/``mode`` with ``quality``, in degree order.

    A triad quality selects from the seven diatonic triads; a seventh quality
    (ticket 10) from the seven diatonic seventh chords.  The single definition
    of "which chords a quality drill selects": the compiler, the validation
    chord count, and the default spec builders all call this, so they cannot
    drift apart.
    """
    chords = (generate_diatonic_sevenths(key, mode)
              if quality in _SEVENTH_QUALITIES
              else generate_diatonic_triads(key, mode))
    return [t for t in chords if t.chord_quality == quality]


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
        for key in _keys_for(spec):
            for triad in _triads_of_quality(key, mode, spec.quality):
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


# ---------------------------------------------------------------------------
# Comprehensive default exercise sets (all 12 major + 12 natural-minor keys)
# ---------------------------------------------------------------------------
#
# These builders expand the trainer to practise *every* major and natural-minor
# key systematically, in both block and arpeggio rendering.  None of them
# hard-code MusicXML: every entry is a :class:`HarmonyExerciseSpec` consumed by
# :func:`compile_exercise` and the MusicXML builder.  Long drills are split into
# several short specs (see :data:`MAX_CHORDS_PER_SPEC`) so each exercise stays
# readable on the staff.

def _key_slug(key: str) -> str:
    """A stable, identifier-safe token for a tonic name (``"Bb" -> "Bf"``)."""
    return key.replace("#", "s").replace("b", "f")


def _roman_slug(label: str) -> str:
    """A stable token for a Roman-numeral label (``"vii°" -> "vii"``)."""
    return "".join(ch for ch in label if ch.isalpha()).lower()


def _label_slug(label: str) -> str:
    """A stable token for a function-pattern label (``"I–IV–V–I" -> "i_iv_v_i"``)."""
    out = "".join(ch if ch.isalnum() else "_" for ch in label)
    return "_".join(p for p in out.split("_") if p).lower()


def _mode_words(mode: str) -> "tuple[str, str]":
    """``(short, long)`` mode words: major->("major","major"); minor->("minor","natural minor")."""
    return ("major", "major") if mode == "major" else ("minor", "natural minor")


def _keys_label(chunk: List[str], all_keys: List[str]) -> str:
    """Human label for a key subset: the full list, or 'all 12 keys'."""
    if len(chunk) == len(all_keys):
        return f"all {len(all_keys)} keys"
    return ", ".join(chunk)


def _chunk_keys(keys: List[str], chords_per_key: int) -> List[List[str]]:
    """Split ``keys`` so each chunk yields at most :data:`MAX_CHORDS_PER_SPEC` chords."""
    per = max(1, MAX_CHORDS_PER_SPEC // max(1, chords_per_key))
    return [keys[i:i + per] for i in range(0, len(keys), per)]


def _full_key_specs(mode: str, render: str) -> List[HarmonyExerciseSpec]:
    """All seven triads of every key in ``mode`` (one spec per key)."""
    short, long = _mode_words(mode)
    keys = DEFAULT_MAJOR_KEYS if mode == "major" else DEFAULT_MINOR_KEYS
    specs = []
    for k in keys:
        specs.append(HarmonyExerciseSpec(
            exercise_id=f"{mode}_fullkey_{render}_{_key_slug(k)}",
            title=f"{k} {short} — all 7 triads ({render})",
            drill="full_key", render=render, mode=mode, key=f"{k} {short}",
            description=f"All seven diatonic triads of {k} {long} ({render}).",
        ))
    return specs


def _degree_specs(mode: str, render: str) -> List[HarmonyExerciseSpec]:
    """One spec per scale degree, that degree's triad across all 12 keys."""
    short, long = _mode_words(mode)
    labels = _MAJOR_DEGREE_LABELS if mode == "major" else _MINOR_DEGREE_LABELS
    specs = []
    for label in labels:
        specs.append(HarmonyExerciseSpec(
            exercise_id=f"{mode}_degree_{_roman_slug(label)}_{render}",
            title=f"{label} across all 12 {long} keys ({render})",
            drill="horizontal_degree", render=render, mode=mode, degree=label,
            description=(f"The {label} triad transposed through all 12 {long} "
                         f"keys ({render})."),
        ))
    return specs


def _quality_specs(mode: str = "major") -> List[HarmonyExerciseSpec]:
    """Quality-recognition drills (major / minor / diminished) across all keys.

    A quality drill collects every diatonic triad of one quality across the 12
    keys of ``mode``.  Where that exceeds the readability cap (the major- and
    minor-quality drills have three triads per key) it is split by key-group.
    """
    short, long = _mode_words(mode)
    keys = DEFAULT_MAJOR_KEYS if mode == "major" else DEFAULT_MINOR_KEYS
    specs = []
    for quality in ("major", "minor", "diminished"):
        # How many triads of this quality occur per key in this mode.
        per_key = len(_triads_of_quality(keys[0], mode, quality))
        if per_key == 0:
            continue
        chunks = _chunk_keys(keys, per_key)
        for ci, chunk in enumerate(chunks, start=1):
            label = _keys_label(chunk, keys)
            suffix = "" if len(chunks) == 1 else f" (set {ci})"
            specs.append(HarmonyExerciseSpec(
                exercise_id=f"quality_{quality}_in_{mode}_{ci}",
                title=f"{quality.capitalize()} triads across {long} keys{suffix}",
                drill="quality", render="block", mode=mode,
                quality=quality, keys=list(chunk),
                description=(f"Every {quality} diatonic triad across {label} "
                             f"({long})."),
            ))
    return specs


def _function_specs(mode: str, patterns) -> List[HarmonyExerciseSpec]:
    """Function/Roman-pattern drills across all 12 keys, split by key-group."""
    short, long = _mode_words(mode)
    keys = DEFAULT_MAJOR_KEYS if mode == "major" else DEFAULT_MINOR_KEYS
    specs = []
    for tokens, label in patterns:
        chunks = _chunk_keys(keys, len(tokens))
        for ci, chunk in enumerate(chunks, start=1):
            keys_label = _keys_label(chunk, keys)
            specs.append(HarmonyExerciseSpec(
                exercise_id=f"function_{_label_slug(label)}_{mode}_{ci}",
                title=f"{label} — {keys_label} ({long})",
                drill="function", render="block", mode=mode,
                pattern=list(tokens), keys=list(chunk),
                description=(f"The {label} progression transposed across "
                             f"{keys_label} ({long})."),
            ))
    return specs


def default_exercise_groups() -> "OrderedDict[str, List[HarmonyExerciseSpec]]":
    """The full default set, organised into the six launcher groups.

    The groups partition the set (every spec appears in exactly one group):
    block full-key and degree drills live in their family group, while every
    arpeggio-rendered drill is collected under "Arpeggio drills".
    """
    return OrderedDict([
        (GROUP_MAJOR_FULL_KEY, _full_key_specs("major", "block")),
        (GROUP_MINOR_FULL_KEY, _full_key_specs("natural_minor", "block")),
        (GROUP_DEGREE,
            _degree_specs("major", "block")
            + _degree_specs("natural_minor", "block")),
        (GROUP_QUALITY, _quality_specs("major")),
        (GROUP_FUNCTION,
            _function_specs("major", _FUNCTION_PATTERNS_MAJOR)
            + _function_specs("natural_minor", _FUNCTION_PATTERNS_MINOR)),
        (GROUP_ARPEGGIO,
            _full_key_specs("major", "arpeggio")
            + _full_key_specs("natural_minor", "arpeggio")
            + _degree_specs("major", "arpeggio")
            + _degree_specs("natural_minor", "arpeggio")),
    ])


def all_default_specs() -> List[HarmonyExerciseSpec]:
    """Flat list of every default spec, in group order (stable, de-duplicated)."""
    out: List[HarmonyExerciseSpec] = []
    for specs in default_exercise_groups().values():
        out.extend(specs)
    return out


def degree_labels_for_mode(mode: str) -> List[str]:
    """The seven quality-cased Roman labels of ``mode``, in degree order.

    This is the MCQ option vocabulary for Roman-numeral identification drills
    (plan U2): the labels match ``DiatonicTriad.roman`` exactly, so a target's
    ``roman`` is always one of them.
    """
    return list(_MAJOR_DEGREE_LABELS if _canon_mode(mode) == "major"
                else _MINOR_DEGREE_LABELS)


def identification_demo_specs() -> List[HarmonyExerciseSpec]:
    """Launchable no-MIDI identification drills (plan U2, ticket 06).

    Deliberately a *separate* set: ``default_exercise_groups()`` is
    load-bearing (the curriculum wraps exactly its 102 drills and tests pin
    its group names), so identification drills are appended only where a host
    opts in (the trainer launcher's :data:`GROUP_IDENTIFY` group).
    """
    specs = [
        HarmonyExerciseSpec(
            exercise_id="identify_mcq_fullkey_c_major",
            title="Identify the chord — C major (MCQ)",
            drill="full_key", mode="major", key="C major", answer_mode="mcq",
            description=("The cursor sits on one diatonic triad of C major; "
                         "name its Roman numeral from the answer strip. "
                         "No MIDI needed.")),
        HarmonyExerciseSpec(
            exercise_id="identify_mcq_fullkey_a_minor",
            title="Identify the chord — A minor (MCQ)",
            drill="full_key", mode="natural_minor", key="A minor",
            answer_mode="mcq",
            description=("Name the Roman numeral of each diatonic triad of "
                         "A natural minor from the answer strip.")),
        HarmonyExerciseSpec(
            exercise_id="identify_mcq_function_251_c_major",
            title="Identify the chord — ii–V–I in C (MCQ)",
            drill="function", mode="major", pattern=["ii", "V", "I"],
            keys=["C"], answer_mode="mcq",
            description=("Name each chord of the ii–V–I progression in "
                         "C major from the answer strip.")),
        HarmonyExerciseSpec(
            exercise_id="identify_card_fullkey_c_major",
            title="Match the chord card — C major",
            drill="full_key", mode="major", key="C major", answer_mode="card",
            description=("Read the current chord's tones and function, then "
                         "click the matching chord card in the list.")),
    ]
    for s in specs:
        s.validate()
    return specs
