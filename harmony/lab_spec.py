"""Experiment-spec format + trainer-spec bridge for the Music Theory Laboratory.

A *lab experiment spec* (:class:`LabExperimentSpec`) describes one laboratory
demonstration: a concept (inversion / voice-leading / cadence / motive /
polyphonic harmony / reduction), a key + mode, a render style, and an open
``parameters`` dict.  It is deliberately **separate** from
:class:`~harmony.exercise_spec.HarmonyExerciseSpec` (the root-position triad
drill the Harmony Trainer plays), because the lab demonstrates things a
root-position triad drill cannot express (a changing bass, four independent
voices, a melodic motive, two implied-harmony voices).

But the lab never *bypasses* the trainer where an exercise can be represented by
it: :meth:`LabExperimentSpec.to_exercise_specs` compiles an experiment **down to
one or more HarmonyExerciseSpec objects whenever possible** (a cadence's
root-position progression *is* a ``function`` drill; an inverted chord's
identity *is* its root-position triad; a polyphonic example's per-measure
implied harmony *is* a ``function`` drill).  Where no chord-drill representation
exists (a scale-degree motive), it returns ``[]`` -- the lab still renders and
MIDI-validates the example through its own payload (see
:mod:`harmony.lab_musicxml`).

Design rules (shared with the rest of the project):

* **No duplicated theory tables.**  Everything derives from
  :mod:`theory.diatonic_harmony` and :class:`HarmonyExerciseSpec`.
* **Pure + deterministic.**  No Qt / Verovio / MIDI here.
* **Cap-respecting.**  Every spec returned by :meth:`to_exercise_specs` is run
  through :func:`compile_exercise` and asserted to be within
  :data:`~harmony.exercise_spec.MAX_CHORDS_PER_SPEC` (mirrors
  ``harmony.circle_payload.spec_from_circle_request``); the lab itself caps the
  measure count at the same value so every example renders on a single page.

The schema is intentionally open (``parameters`` is a free dict) so the
remaining non-goals -- full counterpoint, Schenkerian reduction, real-score
analysis -- extend without breaking existing fields.  Seventh chords arrived
with ticket 09 (plan G1a), harmonic/melodic minor with tickets 13-14 (G2),
and secondary dominants with ticket 17 (G5a): the roman gate
(:func:`is_supported_roman`) accepts exactly the tokens the theory engine
knows how to build -- :data:`theory.diatonic_harmony.SEVENTH_DEGREE_TOKENS`
plus the applied ``V/x`` / ``V7/x`` vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from theory.diatonic_harmony import (
    parse_key,
    key_signature_fifths,
    roman_token_to_index,
    parse_seventh_token,
    parse_applied_token,
    seventh_tokens_for_mode,
    applied_tokens_for_mode,
    generate_scale,
    transpose_degree_pattern,
    note_pc,
    _canon_mode,
    _mode_word,
)
from harmony.exercise_spec import (
    HarmonyExerciseSpec,
    compile_exercise,
    normalise_pattern,
    MAX_CHORDS_PER_SPEC,
    DEFAULT_MAJOR_KEYS,
    DEFAULT_MINOR_KEYS,
    _key_slug,
)
from harmony.harmonic_roles import CADENCE_TYPES


SCHEMA_VERSION = "harmony-lab/v1"

#: The concepts the lab can express.  ``inversion`` / ``cadence`` /
#: ``voice_leading`` / ``motive`` / ``polyphonic_harmony`` are implemented;
#: ``reduction`` is reserved (validates + down-compiles a supplied skeleton, but
#: ``compile_lab`` raises until the Schenkerian reduction phase ships).
#:
#: ``drill`` is the **passthrough** concept (the Music Theory Laboratory's
#: architectural consolidation): it wraps a *native* trainer
#: :class:`~harmony.exercise_spec.HarmonyExerciseSpec` (a scale / full-key /
#: degree / quality / function drill) inside a ``LabExperimentSpec`` so that
#: **every** Harmony-Trainer exercise -- not only the synthetic lab concepts --
#: is owned by exactly one LabExperimentSpec.  Its ``parameters['exercise']`` is
#: the embedded HarmonyExerciseSpec dict; :meth:`to_exercise_specs` returns it
#: verbatim (the round-position chord drill *is* the exercise), and the
#: Laboratory launches it straight into the trainer (it is **not** routed through
#: :func:`harmony.lab.compile_lab`, which only synthesises the non-trainer
#: concepts).  This is how the curriculum (:mod:`harmony.curriculum`) makes the
#: trainer the execution engine and the Lab the canonical source.
#: ``applied_chord`` (ticket 17 / plan G5a) is the first chromatic concept:
#: a diatonic progression with exactly one applied dominant (the intruder),
#: staged as *spot* (click the chord that does not live in the key) and
#: *resolve* (play the intruder and its resolution).  The *ear* stage is
#: reserved for G5c (ticket 19).  Each stage compiles to one native trainer
#: drill, so the launch path is the trainer, not the lab renderer.
#: ``technique`` (piano-technique ticket 01) is the phrase engine: a
#: multi-measure, single-key melodic phrase — the missing shape between
#: ``motive`` (one measure per key, ≤ 8 notes) and the daily technique
#: exercises (scale runs, trill cells, arpeggio runs).  It renders through
#: the lab's melody pipeline and grades as an ordered pitch-class walk.
CONCEPTS = {
    "inversion", "voice_leading", "cadence",
    "polyphonic_harmony", "motive", "reduction",
    "drill", "applied_chord", "technique",
}

#: Render styles.  ``block`` / ``arpeggio`` reuse the trainer's renderers;
#: ``voice_leading`` draws an SATB-like grand-staff voicing; ``polyphonic``
#: draws two independent voices; ``melody`` draws a single melodic line.
RENDERS = {"block", "arpeggio", "voice_leading", "polyphonic", "melody"}

#: ``melodic_minor`` is motive-only (ticket 14 / plan G2b): the two-way scale
#: form is drilled as a melody; every chordal concept refuses it (validate).
MODES = {"major", "natural_minor", "harmonic_minor", "melodic_minor"}

#: Which render styles are legal for each concept (``validate`` enforces).
_CONCEPT_RENDERS = {
    "inversion":          {"block", "arpeggio"},
    "voice_leading":      {"voice_leading", "block"},
    "cadence":            {"block", "voice_leading"},
    "polyphonic_harmony": {"polyphonic"},
    "motive":             {"melody"},
    "reduction":          {"block", "voice_leading"},   # reserved
    "drill":              {"block", "arpeggio"},         # mirrors the trainer's renders
    "applied_chord":      {"block", "arpeggio"},         # arpeggio: resolve stage only
    "technique":          {"melody"},                    # a single moving line
}

#: Concepts whose ``parameters`` may carry ``strict_bass`` (require render="block";
#: it is enforced by emitting the bass pitch class first in the ordered target).
_STRICT_BASS_CONCEPTS = {"inversion"}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _ident(text: str) -> str:
    """A stable, identifier-safe token (keeps alphanumerics, ``_``)."""
    out = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in (text or ""))
    return out.strip("_")


def tonic_of(key: str) -> str:
    """``"Eb minor"`` / ``"Eb"`` -> ``"Eb"`` (the spelled tonic token only)."""
    return parse_key(key)[0]


def is_supported_roman(token: str) -> bool:
    """True iff ``token`` is a Roman numeral an engine can actually build.

    Ticket 17 (plan G5a) widened this gate from diatonic-only
    (``is_diatonic_roman``) to a *supported-roman allowlist*: it now also
    accepts the applied-dominant tokens (``V/x`` / ``V7/x``, per
    :func:`theory.diatonic_harmony.parse_applied_token`) alongside the
    quality-decorated diatonic numerals (``vii°``, ``III+``) and the
    *supported* seventh tokens (``V7``, per
    :data:`theory.diatonic_harmony.SEVENTH_DEGREE_TOKENS`).  Everything the
    engines cannot build stays rejected -- other chromatic tokens (``bII``,
    ``#iv``, ``N6``), applied leading-tone chords (``vii°7/V``), and any
    other digit-bearing token (``ii7``, ``V9``), explicitly rather than
    tolerantly stripped down to a triad.  Use it on a token already passed
    through :func:`normalise_pattern` (so ``T``/``S``/``D`` shorthand has
    become Roman).
    """
    t = (token or "").strip()
    if parse_applied_token(t) is not None:
        return True
    if any(c in t for c in "/()"):
        return False
    if parse_seventh_token(t) is not None:
        return True
    core = t.replace("°", "").replace("o", "").replace("+", "")
    if any(c in core for c in "b#♭♯"):       # flat / sharp accidental
        return False
    if any(ch.isdigit() for ch in core):     # unsupported seventh / figure
        return False
    try:
        roman_token_to_index(t)
        return True
    except ValueError:
        return False


def default_keys(mode: str) -> List[str]:
    """The 12 practical keys of ``mode`` (used by the motive lab's default sweep)."""
    return list(DEFAULT_MAJOR_KEYS if mode == "major" else DEFAULT_MINOR_KEYS)


#: Understood triad figured-bass suffixes -> inversion number, longest first so
#: ``"64"`` wins over ``"6"``.
_TRIAD_FIGURES = [
    ("6/4", 2), ("64", 2), ("6/3", 1), ("63", 1), ("5/3", 0), ("53", 0), ("6", 1),
]

#: Seventh-chord figured-bass suffixes -> inversion number (ticket 11 / plan
#: G1c).  G1c's vocabulary is the DOMINANT seventh only: the suffix attaches
#: to a bare ``V`` head (``V65`` / ``V6/5`` …) and resolves to the ``V7``
#: tetrad token, whose mode gate (major only, plan G2 for minor) then applies
#: unchanged.  Other degrees' figured sevenths (``ii65``) stay rejected.
_SEVENTH_FIGURES = [
    ("6/5", 1), ("65", 1), ("4/3", 2), ("43", 2), ("4/2", 3), ("42", 3),
]


def parse_figured_token(token: str) -> "Tuple[str, int]":
    """Split an optional figured-bass suffix off a Roman token.

    ``"ii6" -> ("ii", 1)``; ``"I64" -> ("I", 2)``; ``"V" -> ("V", 0)``; and
    the dominant-seventh figures ``"V65" -> ("V7", 1)``, ``"V43" -> ("V7",
    2)``, ``"V42" -> ("V7", 3)`` (slash spellings too).  The figure is a
    *performance instruction* (plans G4/G1c): it demands the inversion's
    chord member in the bass.  Unknown figures are left on the token — the
    caller's Roman validation rejects them explicitly (the tolerant
    ``roman_token_to_index`` would otherwise silently strip digits, playing
    ``"ii6"`` as root-position ii, which is exactly the F4 dishonesty).
    """
    t = (token or "").strip()
    for suffix, inv in _SEVENTH_FIGURES:
        if t.endswith(suffix) and t[:-len(suffix)].strip() == "V":
            return "V7", inv
    for suffix, inv in _TRIAD_FIGURES:
        if t.endswith(suffix) and len(t) > len(suffix):
            return t[:-len(suffix)].strip(), inv
    return t, 0


def _compact_figure(inv: int, figures) -> str:
    """The shortest slash-free spelling of ``inv`` in a figure table
    (``1 -> "6"`` for triads, ``1 -> "65"`` for sevenths) — derived from the
    parse tables so the id vocabulary can never drift from what parses."""
    return min((s for s, i in figures if i == inv and "/" not in s), key=len)


def _figured_id_token(head: str, inv: int) -> str:
    """The stable id token of a figured chord (``("V7", 1) -> "V65"``).

    Re-attaches the figure so a figured drill's id never collides with its
    root-position sibling; for a seventh head the figure replaces the ``7``
    (standard notation: V65 implies the seventh).
    """
    if not inv:
        return head
    if parse_seventh_token(head) is not None:
        stem = head[:-1] if head.endswith("7") else head
        return stem + _compact_figure(inv, _SEVENTH_FIGURES)
    return head + _compact_figure(inv, _TRIAD_FIGURES)


def split_figured_pattern(pattern) -> "Tuple[List[str], List[int]]":
    """``["ii6","V","I"] -> (["ii","V","I"], [1,0,0])`` (see parse_figured_token)."""
    romans: List[str] = []
    inversions: List[int] = []
    for tok in pattern:
        head, inv = parse_figured_token(tok)
        romans.append(head)
        inversions.append(inv)
    return romans, inversions


# ---------------------------------------------------------------------------
# Per-concept parameter views (typed, validated read of ``parameters``)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InversionParams:
    degree: str = "I"                 # one diatonic degree token, e.g. "I", "V"
    inversions: tuple = (0, 1, 2)     # which inversions to show, one measure each
    strict_bass: bool = False         # payload-only: require the bass note first


@dataclass(frozen=True)
class CadenceParams:
    pattern: tuple = ("V", "I")       # Roman / functional tokens
    cadence_type: str = ""            # display only; one of harmonic_roles.CADENCE_TYPES
    strict_bass: bool = False
    dictation: str = ""               # "" | "bass" | "soprano" — grade one line only
    #: 1-based scale degree demanded in the soprano, one per pattern chord
    #: (ticket 16 / plan G3: PAC ends on 1̂, IAC on 3̂/5̂).  Empty -> the SATB
    #: voicing picks the smoothest soprano as before.
    soprano_degrees: tuple = ()
    #: Display-only alternative token per pattern chord (ticket 16's cadential
    #: 6/4 relabel drill: the same sounds shown as ``V(6–4)`` instead of
    #: ``I64``).  Never changes what compiles or what is graded — only what
    #: each measure's annotation CALLS the chord.
    relabel: tuple = ()


@dataclass(frozen=True)
class MotiveParams:
    degrees: tuple = (1, 3, 5, 3)     # 1-based scale degrees (the melodic cell)
    keys: tuple = ()                  # keys to transpose through ([] -> mode's 12)


@dataclass(frozen=True)
class PolyphonicParams:
    progression: tuple = ("I", "V", "I")   # implied Roman per measure
    upper_degrees: tuple = (3, 2, 3)       # 1-based scale degree of the upper voice
    bass_degrees: tuple = ()               # optional bass scale degrees ([] -> roots)


@dataclass(frozen=True)
class ReductionParams:
    skeleton: tuple = ()              # optional reduced progression -> drillable
    source: dict = field(default_factory=dict)


#: The applied-chord stages, in teaching order (ticket 17 / plan G5a; the
#: *ear* stage landed with ticket 19 / plan G5c).  ``spot`` hunts the
#: intruder by eye, ``resolve`` plays it into its target, and ``ear`` is the
#: same hunt with the notation veiled: the progression is heard, the learner
#: clicks the *position* of the chromatic chord and then names the degree it
#: tonicised (the payload's follow-up question).
APPLIED_STAGES = ("spot", "resolve", "ear")

#: The stages that render the whole progression as a block hunt (an arpeggio
#: render spreads one chord over four beats -- fine for the resolve pass, but
#: it stops the progression reading as a row of chords to pick from).
_APPLIED_BLOCK_STAGES = ("spot", "ear")


@dataclass(frozen=True)
class AppliedChordParams:
    #: Roman tokens with exactly ONE applied dominant (the intruder),
    #: immediately followed by its target (the resolve stage and the spot
    #: explanation both promise that resolution).
    progression: tuple = ("I", "vi", "V7/V", "V", "I")
    stages: tuple = ("spot",)         # subset of APPLIED_STAGES, in order


#: Slots per 4/4 measure for each technique note value (piano-technique
#: tickets 01+02; ``_TICKS`` divides a 16-division quarter exactly for all).
TECHNIQUE_SLOTS = {"quarter": 4, "eighth": 8, "16th": 16}

#: Highest 1-based scale degree a technique phrase may reach: four octaves
#: (``_scale_note`` wraps degrees > 7 into higher octaves with no clamp).
TECHNIQUE_MAX_DEGREE = 29


@dataclass(frozen=True)
class TechniqueParams:
    #: One inner tuple per MEASURE; entries are 1-based scale degrees
    #: (1..TECHNIQUE_MAX_DEGREE — the four-octave span of a scale run).
    #: An entry may itself be a tuple of distinct degrees (ticket 03): a
    #: dyad/step sounded TOGETHER, notated chord-stacked and graded as one
    #: simultaneity step.
    phrase: tuple = ()
    note_value: str = "quarter"       # "quarter" | "eighth" | "16th"
    hand: str = "rh"                  # "rh" (treble staff) | "lh" (bass staff)
    #: Octave doubling (ticket 03): every step is written as the degree plus
    #: its octave (d, d+7) and graded as two distinct keys on one pitch
    #: class.  Scalar phrase entries only — a doubled dyad is refused.
    octaves: bool = False
    #: Optional per-note marks, each mirroring ``phrase``'s shape (one inner
    #: tuple per measure, one label per step, "" for none).  A dyad step may
    #: take a tuple of per-note labels; a scalar label marks the step's
    #: first notehead.  Presentation only: Verovio renders them, the mod-12
    #: note-on grader cannot see them.
    fingering: tuple = ()             # "1".."5"
    slurs: tuple = ()                 # "start" | "stop"
    articulations: tuple = ()         # "staccato" | "accent"
    #: The not-graded gesture instruction (wrist, accents, tempo intent).
    #: Shown in the leaf description / guide panel, never assessed.
    coach: str = ""


def inversion_params(p: Dict) -> InversionParams:
    return InversionParams(
        degree=str(p.get("degree", "I")),
        inversions=tuple(int(i) for i in p.get("inversions", (0, 1, 2))),
        strict_bass=bool(p.get("strict_bass", False)),
    )


def cadence_params(p: Dict) -> CadenceParams:
    return CadenceParams(
        pattern=tuple(p.get("pattern", ("V", "I"))),
        cadence_type=str(p.get("cadence_type", "")),
        strict_bass=bool(p.get("strict_bass", False)),
        dictation=str(p.get("dictation", "") or ""),
        soprano_degrees=tuple(int(d) for d in p.get("soprano_degrees", ())),
        relabel=tuple(str(t) for t in p.get("relabel", ())),
    )


def motive_params(p: Dict) -> MotiveParams:
    return MotiveParams(
        degrees=tuple(int(d) for d in p.get("degrees", (1, 3, 5, 3))),
        keys=tuple(p.get("keys", ())),
    )


def polyphonic_params(p: Dict) -> PolyphonicParams:
    return PolyphonicParams(
        progression=tuple(p.get("progression", ("I", "V", "I"))),
        upper_degrees=tuple(int(d) for d in p.get("upper_degrees", (3, 2, 3))),
        bass_degrees=tuple(int(d) for d in p.get("bass_degrees", ())),
    )


def reduction_params(p: Dict) -> ReductionParams:
    return ReductionParams(
        skeleton=tuple(p.get("skeleton", ())),
        source=dict(p.get("source", {})),
    )


def applied_chord_params(p: Dict) -> AppliedChordParams:
    return AppliedChordParams(
        progression=tuple(str(t) for t in p.get(
            "progression", ("I", "vi", "V7/V", "V", "I"))),
        stages=tuple(str(s) for s in p.get("stages", ("spot",))),
    )


def _phrase_entry(d: object) -> object:
    """One phrase step: a 1-based degree, or a tuple of degrees sounded together."""
    if isinstance(d, (list, tuple)):
        return tuple(int(x) for x in d)
    return int(d)


def _mark_entry(x: object) -> object:
    """One per-step mark: a label, or per-note labels mirroring a dyad step."""
    if isinstance(x, (list, tuple)):
        return tuple(str(f) for f in x)
    return str(x)


def technique_params(p: Dict) -> TechniqueParams:
    return TechniqueParams(
        phrase=tuple(tuple(_phrase_entry(d) for d in m)
                     for m in p.get("phrase", ())),
        note_value=str(p.get("note_value", "quarter")),
        hand=str(p.get("hand", "rh")),
        octaves=bool(p.get("octaves", False)),
        fingering=tuple(tuple(_mark_entry(f) for f in m)
                        for m in p.get("fingering", ())),
        slurs=tuple(tuple(_mark_entry(s) for s in m)
                    for m in p.get("slurs", ())),
        articulations=tuple(tuple(_mark_entry(a) for a in m)
                            for m in p.get("articulations", ())),
        coach=str(p.get("coach", "")),
    )


# ---------------------------------------------------------------------------
# Spec dataclass
# ---------------------------------------------------------------------------

#: Lab concepts a Circle/Atlas "Open ... lab" click can generate (a subset; the
#: reserved reduction concept is not launchable from a click).
_LAB_REQUEST_CONCEPTS = {"inversion", "cadence", "voice_leading",
                         "polyphonic_harmony", "motive"}

#: Default render per requestable concept (matches _CONCEPT_RENDERS).
_LAB_REQUEST_RENDER = {
    "inversion": "block",
    "cadence": "voice_leading",
    "voice_leading": "voice_leading",
    "polyphonic_harmony": "polyphonic",
    "motive": "melody",
}


@dataclass
class LabExperimentSpec:
    """A JSON-compatible description of one laboratory experiment."""

    experiment_id: str
    title: str
    concept: str                         # one of CONCEPTS
    schema: str = SCHEMA_VERSION
    mode: str = "major"                  # "major" | "natural_minor"
    key: str = "C major"
    render: str = "block"                # one of RENDERS, compatible with concept
    parameters: Dict = field(default_factory=dict)
    description: str = ""

    # --- validation ---------------------------------------------------
    def validate(self) -> None:
        if self.schema not in (SCHEMA_VERSION, None, ""):
            raise ValueError(
                f"Unknown lab schema {self.schema!r}; expected {SCHEMA_VERSION}")
        self.schema = SCHEMA_VERSION
        if self.concept not in CONCEPTS:
            raise ValueError(f"Unknown concept {self.concept!r}; expected {CONCEPTS}")
        self.mode = _canon_mode(self.mode)
        if self.mode == "melodic_minor" and self.concept != "motive":
            raise ValueError(
                "mode='melodic_minor' is motive-only: the scale form is "
                "direction-dependent (raised 6th/7th ascending, natural "
                "descending), so it has no honest chord set. Chordal "
                "concepts use natural_minor or harmonic_minor; melodic "
                "minor is drilled by the ascent/descent motive lab.")
        if self.render not in RENDERS:
            raise ValueError(f"Unknown render {self.render!r}; expected {RENDERS}")
        if self.render not in _CONCEPT_RENDERS[self.concept]:
            raise ValueError(
                f"render {self.render!r} is not valid for concept "
                f"{self.concept!r} (allowed: {_CONCEPT_RENDERS[self.concept]})")
        if not isinstance(self.parameters, dict):
            raise ValueError("parameters must be a dict")
        self._check_key_range(self.key)
        self._validate_params()

    def _check_key_range(self, key: str) -> None:
        tonic, parsed_mode = parse_key(key)
        mode = _canon_mode(parsed_mode) if parsed_mode else self.mode
        fifths = key_signature_fifths(tonic, mode)
        if not -7 <= fifths <= 7:
            raise ValueError(
                f"Key {key!r} needs {fifths} sharps/flats; MusicXML key "
                f"signatures only support -7..+7. Use the practical enharmonic "
                f"spelling instead (e.g. Ab major rather than G# major).")

    def _check_supported(self, tokens, allow_applied: bool = False) -> None:
        """Reject unsupported chromatic tokens after normalisation.

        Applied dominants pass the widened :func:`is_supported_roman` gate,
        but each concept must opt in (``allow_applied``): only the
        ``applied_chord`` concept (and the native function drills it compiles
        to) can render them -- the SATB / polyphonic / inversion paths have
        no applied voicing yet.
        """
        for orig, norm in zip(tokens, normalise_pattern(list(tokens))):
            if not is_supported_roman(norm):
                raise ValueError(
                    f"chromatic/secondary token {orig!r} is not supported yet "
                    f"(a non-goal); use diatonic Roman numerals or T/S/D shorthand")
            if parse_applied_token(norm) is not None:
                if not allow_applied:
                    raise ValueError(
                        f"applied token {orig!r} is only supported by the "
                        f"applied_chord concept (and the native function "
                        f"drills it compiles to) for now; the "
                        f"{self.concept!r} render paths have no applied "
                        f"voicing yet")
                if norm not in applied_tokens_for_mode(self.mode):
                    raise ValueError(
                        f"{orig!r} is not honest in {self.mode}: the "
                        f"applied-dominant vocabulary of this mode is "
                        f"{sorted(applied_tokens_for_mode(self.mode))}")
                continue
            if (parse_seventh_token(norm) is not None
                    and norm not in seventh_tokens_for_mode(self.mode)):
                raise ValueError(
                    f"{orig!r} is not diatonic to {self.mode}: the seventh "
                    f"vocabulary of this mode is "
                    f"{seventh_tokens_for_mode(self.mode)}. (The minor-key V7 "
                    f"needs harmonic minor's raised leading tone: mode "
                    f"'harmonic_minor'.)")

    def _validate_params(self) -> None:
        p = self.parameters
        if p.get("strict_bass"):
            if self.concept not in _STRICT_BASS_CONCEPTS:
                raise ValueError(
                    f"strict_bass is only valid for {_STRICT_BASS_CONCEPTS}")
            if self.render != "block":
                raise ValueError(
                    "strict_bass requires render='block' (bass-first ordering)")

        if self.concept == "inversion":
            ip = inversion_params(p)
            if parse_seventh_token(ip.degree) is not None:
                # A seventh degree (ticket 11 / plan G1c) owns FOUR voicings
                # (7 · 6/5 · 4/3 · 4/2); the mode gate mirrors the pattern
                # tokens' (natural minor has no V7 until harmonic minor).
                self._check_supported([ip.degree])
                allowed, shapes = (0, 1, 2, 3), "{0,1,2,3} (seventh chords)"
            else:
                roman_token_to_index(ip.degree)     # raises on a bad token
                allowed, shapes = (0, 1, 2), "{0,1,2} (triads)"
            if not ip.inversions:
                raise ValueError("inversion requires a non-empty 'inversions' list")
            if any(i not in allowed for i in ip.inversions):
                raise ValueError(f"inversions must be a subset of {shapes}")
            self._check_len(len(ip.inversions))

        elif self.concept in ("cadence", "voice_leading"):
            cp = cadence_params(p)
            if not cp.pattern:
                raise ValueError(f"{self.concept} requires a non-empty 'pattern'")
            romans, figures = split_figured_pattern(cp.pattern)
            for orig, head in zip(cp.pattern, romans):
                if (any(ch.isdigit() for ch in head)
                        and parse_seventh_token(head) is None
                        and parse_applied_token(head) is None):
                    raise ValueError(
                        f"unrecognised figured-bass suffix in {orig!r}; the "
                        f"understood triad figures are 5/3, 6 (6/3) and 6/4, "
                        f"the seventh figures are the dominant's 6/5, 4/3 "
                        f"and 4/2 (V65, V43, V42), and the seventh chords "
                        f"are the diatonic vocabulary "
                        f"(Imaj7, ii7, ..., viiø7; i7, ..., VII7)")
            if any(figures) and self.render != "block":
                raise ValueError(
                    "figured tokens (e.g. 'ii6') require render='block'; the "
                    "SATB voice-leading render voices root positions only")
            if (any(parse_seventh_token(h) is not None for h in romans)
                    and self.render != "block"):
                raise ValueError(
                    "seventh tokens require render='block'; the SATB "
                    "voice-leading render voices triads only (a later "
                    "seventh slice widens it)")
            self._check_supported(romans)            # raises on bad/chromatic token
            self._check_len(len(cp.pattern))
            if cp.relabel and len(cp.relabel) != len(cp.pattern):
                raise ValueError(
                    "relabel needs one display token per pattern chord (it "
                    "renames what a measure's annotation calls the chord, "
                    "never what compiles)")
            if cp.soprano_degrees:
                # A demanded soprano (ticket 16 / plan G3, the PAC/IAC seam):
                # only the SATB render HAS a soprano, and each demanded degree
                # must be a tone of its chord (never voice a non-chord tone).
                if self.render != "voice_leading":
                    raise ValueError(
                        "soprano_degrees requires render='voice_leading': a "
                        "block stack has no designated soprano")
                if len(cp.soprano_degrees) != len(cp.pattern):
                    raise ValueError(
                        "soprano_degrees needs one 1-based scale degree per "
                        "pattern chord")
                if any(not (1 <= d <= 7) for d in cp.soprano_degrees):
                    raise ValueError("soprano_degrees must be in 1..7")
                tonic = tonic_of(self.key)
                scale = generate_scale(tonic, self.mode)
                triads = transpose_degree_pattern(
                    normalise_pattern(list(romans)), tonic, self.mode)
                for tok, deg, triad in zip(cp.pattern, cp.soprano_degrees,
                                           triads):
                    pc = note_pc(scale.scale_pitches[deg - 1])
                    if pc not in triad.pitch_classes:
                        raise ValueError(
                            f"soprano degree {deg} "
                            f"({scale.scale_pitches[deg - 1]}) is not a tone "
                            f"of {tok} ({'-'.join(triad.pitches)}); the "
                            f"soprano must sing a chord tone")
            if cp.dictation:
                # Line dictation: hear the full progression, answer with one
                # line only — the bass (ticket 11 / plan A1 level 5) or the
                # soprano (ticket 16 / plan G3, the PAC-vs-IAC ear seam).
                if cp.dictation not in ("bass", "soprano"):
                    raise ValueError(
                        f"unknown dictation {cp.dictation!r}; the dictation "
                        f"modes are 'bass' (play only the bass line) and "
                        f"'soprano' (play only the top line)")
                if cp.dictation == "bass" and (
                        self.concept != "cadence" or self.render != "block"):
                    raise ValueError(
                        "dictation='bass' requires concept='cadence' with "
                        "render='block' (the veiled block progression whose "
                        "bass line is the graded answer)")
                if cp.dictation == "soprano" and (
                        self.concept != "cadence"
                        or self.render != "voice_leading"):
                    raise ValueError(
                        "dictation='soprano' requires concept='cadence' with "
                        "render='voice_leading' (only the SATB voicing has a "
                        "soprano line to dictate)")
            if cp.cadence_type and cp.cadence_type not in CADENCE_TYPES:
                raise ValueError(
                    f"unknown cadence_type {cp.cadence_type!r}; expected one of "
                    f"{sorted(CADENCE_TYPES)} (harmony.harmonic_roles.CADENCE_TYPES)")

        elif self.concept == "motive":
            mp = motive_params(p)
            if not mp.degrees:
                raise ValueError("motive requires a non-empty 'degrees' list")
            if len(mp.degrees) > 8:
                raise ValueError("a motive cell may have at most 8 notes (one 4/4 bar)")
            if any(not (1 <= d <= 14) for d in mp.degrees):
                raise ValueError("motive degrees must be in 1..14")
            keys = list(mp.keys) or default_keys(self.mode)
            self._check_len(len(keys))

        elif self.concept == "polyphonic_harmony":
            pp = polyphonic_params(p)
            if not pp.progression:
                raise ValueError("polyphonic_harmony requires a 'progression'")
            self._check_supported(pp.progression)
            if len(pp.upper_degrees) != len(pp.progression):
                raise ValueError(
                    "polyphonic_harmony needs one upper_degree per progression chord")
            if pp.bass_degrees and len(pp.bass_degrees) != len(pp.progression):
                raise ValueError(
                    "polyphonic_harmony bass_degrees must match progression length")
            if any(not (1 <= d <= 14) for d in pp.upper_degrees):
                raise ValueError("polyphonic upper_degrees must be in 1..14")
            if pp.bass_degrees and any(not (1 <= d <= 14) for d in pp.bass_degrees):
                raise ValueError("polyphonic bass_degrees must be in 1..14")
            self._check_len(len(pp.progression))

        elif self.concept == "reduction":
            rp = reduction_params(p)
            if rp.skeleton:
                self._check_supported(rp.skeleton)
                self._check_len(len(rp.skeleton))

        elif self.concept == "applied_chord":
            ap = applied_chord_params(p)
            if not ap.stages:
                raise ValueError("applied_chord requires a non-empty 'stages'")
            for s in ap.stages:
                if s not in APPLIED_STAGES:
                    raise ValueError(
                        f"unknown applied stage {s!r}; the stages are "
                        f"{APPLIED_STAGES}")
            block_stages = [s for s in ap.stages if s in _APPLIED_BLOCK_STAGES]
            if block_stages and self.render != "block":
                raise ValueError(
                    f"the {block_stages[0]} stage requires render='block': the "
                    f"intruder hunt reads a block progression (the arpeggio "
                    f"render is the resolve stage's second pass)")
            if not ap.progression:
                raise ValueError("applied_chord requires a 'progression'")
            roman = normalise_pattern(list(ap.progression))
            self._check_supported(roman, allow_applied=True)
            applied = [(i, t) for i, t in enumerate(roman)
                       if parse_applied_token(t) is not None]
            if len(applied) != 1:
                raise ValueError(
                    f"applied_chord requires exactly one applied token in "
                    f"the progression (the intruder); got {len(applied)} in "
                    f"{list(ap.progression)!r}")
            pos, tok = applied[0]
            target = parse_applied_token(tok)[1]
            if pos + 1 >= len(roman) or roman[pos + 1] != target:
                raise ValueError(
                    f"the applied chord must resolve: {tok} must be "
                    f"immediately followed by its target {target} (the spot "
                    f"explanation and the resolve stage both promise that "
                    f"resolution)")
            self._check_len(len(roman))

        elif self.concept == "technique":
            tp = technique_params(p)
            if not tp.phrase:
                raise ValueError(
                    "technique requires a non-empty 'phrase' (one tuple of "
                    "1-based scale degrees per measure)")
            if tp.note_value not in TECHNIQUE_SLOTS:
                raise ValueError(
                    f"unknown note_value {tp.note_value!r}; the technique "
                    f"phrase engine understands {sorted(TECHNIQUE_SLOTS)}")
            slots = TECHNIQUE_SLOTS[tp.note_value]
            for i, m in enumerate(tp.phrase):
                if not m:
                    raise ValueError(
                        f"technique measure {i + 1} is empty; give it at "
                        f"least one degree")
                if len(m) > slots:
                    raise ValueError(
                        f"technique measure {i + 1} has {len(m)} notes but a "
                        f"4/4 bar of {tp.note_value}s holds {slots}; split "
                        f"the measure (short measures are rest-padded)")
                for entry in m:
                    degrees = entry if isinstance(entry, tuple) else (entry,)
                    if isinstance(entry, tuple):
                        if tp.octaves:
                            raise ValueError(
                                f"octaves=True already doubles every step; "
                                f"technique measure {i + 1} may not also "
                                f"carry dyad tuples (got {entry!r})")
                        if len(set(degrees)) != len(degrees):
                            raise ValueError(
                                f"technique measure {i + 1} step {entry!r} "
                                f"repeats a degree; concurrent notes need "
                                f"distinct keys (an octave pair is the same "
                                f"degree 7 apart, or octaves=True)")
                    for d in degrees:
                        if not (1 <= d <= TECHNIQUE_MAX_DEGREE):
                            raise ValueError(
                                f"technique degrees must be in "
                                f"1..{TECHNIQUE_MAX_DEGREE} (four octaves "
                                f"above the tonic); got {d}")
                        if tp.octaves and d + 7 > TECHNIQUE_MAX_DEGREE:
                            raise ValueError(
                                f"octaves=True writes degree {d} with its "
                                f"octave {d + 7}, past the "
                                f"1..{TECHNIQUE_MAX_DEGREE} span; keep "
                                f"octave-doubled degrees <= "
                                f"{TECHNIQUE_MAX_DEGREE - 7}")
            if tp.hand not in ("rh", "lh"):
                raise ValueError(
                    f"unknown hand {tp.hand!r}; 'rh' plays the line on the "
                    f"treble staff, 'lh' on the bass staff")
            for pname, marks, vocab in (
                    ("fingering", tp.fingering, ("1", "2", "3", "4", "5")),
                    ("slurs", tp.slurs, ("start", "stop")),
                    ("articulations", tp.articulations,
                     ("staccato", "accent"))):
                if not marks:
                    continue
                if (len(marks) != len(tp.phrase)
                        or any(len(f) != len(m)
                               for f, m in zip(marks, tp.phrase))):
                    raise ValueError(
                        f"{pname} must mirror the phrase shape: one tuple "
                        f"per measure, one label per step")
                for measure_labels, measure_steps in zip(marks, tp.phrase):
                    for label, entry in zip(measure_labels, measure_steps):
                        if isinstance(label, tuple) and (
                                not isinstance(entry, tuple)
                                or len(label) != len(entry)):
                            raise ValueError(
                                f"{pname} tuple labels must mirror a dyad "
                                f"step note for note; got {label!r} against "
                                f"step {entry!r}")
                        labels = (label if isinstance(label, tuple)
                                  else (label,))
                        for lab in labels:
                            if lab and lab not in vocab:
                                raise ValueError(
                                    f"{pname} labels are "
                                    f"{'/'.join(repr(v) for v in vocab)} "
                                    f"(or '' for none); got {lab!r}")
            self._check_len(len(tp.phrase))

        elif self.concept == "drill":
            raw = p.get("exercise")
            if not isinstance(raw, dict):
                raise ValueError(
                    "drill concept requires parameters['exercise'] "
                    "(an embedded HarmonyExerciseSpec dict)")
            inner = HarmonyExerciseSpec.from_dict(raw)   # validates the embedded spec
            # The wrapper's render/mode must agree with the embedded drill so the
            # Lab never mislabels a native exercise.
            if inner.render != self.render:
                raise ValueError(
                    f"drill render {self.render!r} != embedded exercise render "
                    f"{inner.render!r}")
            self._check_len(len(compile_exercise(inner)))   # one-page cap

    def _check_len(self, n: int) -> None:
        if n > MAX_CHORDS_PER_SPEC:
            raise ValueError(
                f"experiment would render {n} measures (> "
                f"{MAX_CHORDS_PER_SPEC}); split it so each example stays on one page")

    # --- JSON round-tripping ------------------------------------------
    def to_dict(self) -> Dict:
        d = {k: v for k, v in asdict(self).items()
             if v is not None and not (k in ("parameters",) and not v)
             and not (k == "description" and not v)}
        d["schema"] = SCHEMA_VERSION
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> "LabExperimentSpec":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        kwargs = {k: v for k, v in d.items() if k in known}
        spec = cls(**kwargs)
        spec.validate()
        return spec

    # --- bridge back to the Harmony Trainer ---------------------------
    def to_exercise_specs(self) -> List[HarmonyExerciseSpec]:
        """Compile this experiment down to playable trainer drills *where possible*.

        Returns one or more :class:`HarmonyExerciseSpec` objects -- the
        root-position chord-drill skeleton of the experiment -- or ``[]`` when the
        concept has no chord-drill representation (a scale-degree motive; a
        reduction without an explicit skeleton).  Every returned spec is
        validated and asserted to compile within
        :data:`~harmony.exercise_spec.MAX_CHORDS_PER_SPEC` (never silently emit an
        oversized drill).
        """
        self.validate()
        tonic = tonic_of(self.key)
        p = self.parameters
        specs: List[HarmonyExerciseSpec] = []

        if self.concept == "inversion":
            ip = inversion_params(p)
            # The tonic uses the accidental-preserving pitch slug (_key_slug:
            # C#->Cs, Bb->Bf) -- NOT _ident, which strips '#' and would collide
            # C# minor with C minor -- and the render is part of the id so a
            # block and an arpeggio inversion of the same chord stay distinct.
            specs.append(HarmonyExerciseSpec(
                exercise_id=(f"lab_inv_{self.mode}_{_key_slug(tonic)}_"
                             f"{_ident(ip.degree)}_{self.render}"),
                title=f"{ip.degree} in {tonic} {_mode_word(self.mode)} (root position)",
                drill="function", render=self.render, mode=self.mode,
                pattern=[ip.degree], keys=[tonic],
                description=(f"The root-position {ip.degree} triad underlying the "
                             f"inversion experiment."),
            ))

        elif self.concept in ("cadence", "voice_leading"):
            cp = cadence_params(p)
            heads, figures = split_figured_pattern(cp.pattern)
            roman = normalise_pattern(heads)              # validate() ensured diatonic
            # Figures re-attach in the id (ii6 must not collide with a plain ii
            # drill), while the skeleton itself is the root-position pattern.
            id_tokens = [_figured_id_token(n, f) for n, f in zip(roman, figures)]
            if cp.dictation:
                # the dictation variant's skeleton must not collide with the
                # plain drill of the same pattern
                id_tokens.append(f"{cp.dictation}dict")
            label = "–".join(cp.pattern)
            specs.append(HarmonyExerciseSpec(
                exercise_id=f"lab_{self.concept}_{self.mode}_{_key_slug(tonic)}_{_ident('_'.join(id_tokens))}",
                title=f"{label} in {tonic} {_mode_word(self.mode)}",
                drill="function", render="block", mode=self.mode,
                pattern=roman, keys=[tonic],
                description=f"The root-position {label} progression.",
            ))

        elif self.concept == "polyphonic_harmony":
            pp = polyphonic_params(p)
            roman = normalise_pattern(list(pp.progression))   # validate() ensured diatonic
            label = "–".join(pp.progression)
            specs.append(HarmonyExerciseSpec(
                exercise_id=f"lab_poly_{self.mode}_{_key_slug(tonic)}_{_ident('_'.join(roman))}",
                title=f"{label} implied harmony in {tonic} {_mode_word(self.mode)}",
                drill="function", render="block", mode=self.mode,
                pattern=roman, keys=[tonic],
                description=f"The implied root-position harmony of the polyphonic "
                            f"example ({label}).",
            ))

        elif self.concept == "reduction":
            rp = reduction_params(p)
            if not rp.skeleton:
                return []
            specs.append(HarmonyExerciseSpec(
                exercise_id=f"lab_reduction_{self.mode}_{_key_slug(tonic)}",
                title=f"Reduced skeleton in {tonic} {_mode_word(self.mode)}",
                drill="function", render="block", mode=self.mode,
                pattern=normalise_pattern(list(rp.skeleton)), keys=[tonic],
                description="The explicit reduced harmonic skeleton.",
            ))

        elif self.concept == "applied_chord":
            ap = applied_chord_params(p)
            roman = normalise_pattern(list(ap.progression))
            tok = next(t for t in roman
                       if parse_applied_token(t) is not None)
            target = parse_applied_token(tok)[1]
            label = "–".join(ap.progression)
            for stage in ap.stages:
                if stage == "spot":
                    specs.append(HarmonyExerciseSpec(
                        exercise_id=(f"lab_applied_spot_{self.mode}_"
                                     f"{_key_slug(tonic)}_"
                                     f"{_ident('_'.join(roman))}"),
                        title=f"Spot the intruder: {label} in {tonic} "
                              f"{_mode_word(self.mode)}",
                        drill="function", render="block", mode=self.mode,
                        pattern=roman, keys=[tonic], answer_mode="spot",
                        description=(f"One chord of {label} does not live in "
                                     f"{tonic} {_mode_word(self.mode)} — "
                                     f"click it."),
                    ))
                elif stage == "ear":
                    # The same hunt with the notation veiled (ticket 19 / plan
                    # G5c): the progression plays, the learner clicks the
                    # position of the chromatic chord and then names the
                    # degree it tonicised (the payload's follow-up question).
                    specs.append(HarmonyExerciseSpec(
                        exercise_id=(f"lab_applied_ear_{self.mode}_"
                                     f"{_key_slug(tonic)}_"
                                     f"{_ident('_'.join(roman))}"),
                        title=f"Hear the intruder: {label} in {tonic} "
                              f"{_mode_word(self.mode)}",
                        drill="function", render="block", mode=self.mode,
                        pattern=roman, keys=[tonic], answer_mode="spot",
                        presentation="echo",
                        description=(f"Listen — the notation is hidden. Click "
                                     f"the bar where the chord leaves {tonic} "
                                     f"{_mode_word(self.mode)}, then name the "
                                     f"degree it tonicises."),
                    ))
                else:  # resolve — the intruder and its promised target
                    specs.append(HarmonyExerciseSpec(
                        exercise_id=(f"lab_applied_resolve_{self.mode}_"
                                     f"{_key_slug(tonic)}_{_ident(tok)}_"
                                     f"{self.render}"),
                        title=f"Resolve the intruder: {tok}→{target} in "
                              f"{tonic} {_mode_word(self.mode)}",
                        drill="function", render=self.render, mode=self.mode,
                        pattern=[tok, target], keys=[tonic],
                        description=(f"Play {tok}, then resolve it to "
                                     f"{target}: the tritone pulls the "
                                     f"chromatic tone home."),
                    ))

        elif self.concept == "drill":
            # Passthrough: the embedded native HarmonyExerciseSpec *is* the
            # playable drill.  Rebuilt (and re-validated) from the stored dict so
            # the trainer receives exactly the original exercise.
            specs.append(HarmonyExerciseSpec.from_dict(self.parameters["exercise"]))

        else:  # motive / technique -> monophonic melody, no chord drill
            return []

        # Cap guard: never hand the trainer an oversized drill (mirrors
        # spec_from_circle_request).
        for s in specs:
            s.validate()
            n = len(compile_exercise(s))
            if n > MAX_CHORDS_PER_SPEC:
                raise ValueError(
                    f"{s.exercise_id} compiles to {n} chords (> "
                    f"{MAX_CHORDS_PER_SPEC})")
        return specs


# ---------------------------------------------------------------------------
# Click -> lab-experiment bridge (Circle/Atlas "Open ... lab")
# ---------------------------------------------------------------------------

def _key_display(req: Dict) -> str:
    """Resolve a request's key into a ``"<tonic> <mode word>"`` display string."""
    raw = str(req.get("key", "C")).strip()
    tonic = raw.split()[0] if raw else "C"
    mode = _canon_mode(req.get("mode", "major"))
    return f"{tonic} {_mode_word(mode)}"


def spec_from_lab_request(req: Dict) -> LabExperimentSpec:
    """Convert a circle/atlas "Open ... lab" click into a :class:`LabExperimentSpec`.

    The visual layers never build MusicXML or compile experiments; they send a
    small request dict such as::

        {"labConcept": "inversion", "key": "C major", "mode": "major", "degree": "I"}
        {"labConcept": "cadence", "key": "C major", "mode": "major", "pattern": ["V", "I"]}
        {"labConcept": "motive", "key": "G major", "mode": "major", "degrees": [1, 3, 5, 3]}

    This synthesises a stable ``experiment_id`` / ``title`` and a concept-specific
    ``parameters`` dict, builds a ``LabExperimentSpec``, and validates it (which
    enforces the diatonic-only and one-page caps).  Invalid requests raise
    :class:`ValueError` (never silently produce a bad spec) -- mirroring
    :func:`harmony.circle_payload.spec_from_circle_request`.
    """
    if not isinstance(req, dict):
        raise ValueError("lab request must be a dict")
    concept = req.get("labConcept") or req.get("concept")
    if concept not in _LAB_REQUEST_CONCEPTS:
        raise ValueError(f"unsupported lab concept: {concept!r}")

    key = _key_display(req)
    mode = _canon_mode(req.get("mode", "major"))
    tonic = tonic_of(key)
    render = req.get("render") or _LAB_REQUEST_RENDER[concept]

    if concept == "inversion":
        degree = str(req.get("degree", "I"))
        params = {"degree": degree,
                  "inversions": list(req.get("inversions", [0, 1, 2]))}
        ident = f"{_key_slug(tonic)}_{_ident(degree)}"

    elif concept in ("cadence", "voice_leading"):
        pattern = list(req.get("pattern") or ([] if concept == "cadence" else []))
        if not pattern:
            # Sensible defaults: a two-chord cadence, or a ii-V-I voice-leading lab.
            pattern = (["ii", "V", "I"] if mode == "major" else ["iv", "v", "i"]) \
                if concept == "voice_leading" else \
                (["V", "I"] if mode == "major" else ["v", "i"])
        params = {"pattern": pattern}
        if req.get("cadence_type"):
            params["cadence_type"] = str(req["cadence_type"])
        ident = f"{_key_slug(tonic)}_{_ident('_'.join(pattern))}"

    elif concept == "polyphonic_harmony":
        progression = list(req.get("progression") or
                           (["I", "V", "I"] if mode == "major" else ["i", "VII", "i"]))
        upper = list(req.get("upper_degrees") or [3] * len(progression))
        params = {"progression": progression, "upper_degrees": upper}
        ident = f"{_key_slug(tonic)}_{_ident('_'.join(progression))}"

    else:  # motive
        degrees = list(req.get("degrees") or [1, 3, 5, 3])
        params = {"degrees": degrees}
        if req.get("keys"):
            params["keys"] = list(req["keys"])
        ident = f"{_ident('_'.join(str(d) for d in degrees))}_{_key_slug(tonic)}"

    title = req.get("title") or _lab_request_title(concept, key, params)
    spec = LabExperimentSpec(
        experiment_id=f"lab_click_{concept}_{mode}_{ident}",
        title=title, concept=concept, mode=mode, key=key,
        render=render, parameters=params,
        description=req.get("description", ""))
    spec.validate()
    return spec


def _lab_request_title(concept: str, key: str, params: Dict) -> str:
    if concept == "inversion":
        return f"Inversions of {params['degree']} in {key}"
    if concept in ("cadence", "voice_leading"):
        word = "voice leading" if concept == "voice_leading" else "cadence"
        return f"{'–'.join(params['pattern'])} {word} in {key}"
    if concept == "polyphonic_harmony":
        return f"Two-voice {'–'.join(params['progression'])} in {key}"
    return (f"Motive {'–'.join(str(d) for d in params['degrees'])} across the "
            f"{_mode_word(_canon_mode(key.split()[-1]))} keys")
