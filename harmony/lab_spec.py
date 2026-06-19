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
non-goals -- seventh chords, secondary dominants, harmonic/melodic minor, full
counterpoint, Schenkerian reduction, real-score analysis -- extend without
breaking existing fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from theory.diatonic_harmony import (
    parse_key,
    key_signature_fifths,
    roman_token_to_index,
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
)


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
CONCEPTS = {
    "inversion", "voice_leading", "cadence",
    "polyphonic_harmony", "motive", "reduction",
    "drill",
}

#: Render styles.  ``block`` / ``arpeggio`` reuse the trainer's renderers;
#: ``voice_leading`` draws an SATB-like grand-staff voicing; ``polyphonic``
#: draws two independent voices; ``melody`` draws a single melodic line.
RENDERS = {"block", "arpeggio", "voice_leading", "polyphonic", "melody"}

MODES = {"major", "natural_minor"}

#: Which render styles are legal for each concept (``validate`` enforces).
_CONCEPT_RENDERS = {
    "inversion":          {"block", "arpeggio"},
    "voice_leading":      {"voice_leading", "block"},
    "cadence":            {"block", "voice_leading"},
    "polyphonic_harmony": {"polyphonic"},
    "motive":             {"melody"},
    "reduction":          {"block", "voice_leading"},   # reserved
    "drill":              {"block", "arpeggio"},         # mirrors the trainer's renders
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


def is_diatonic_roman(token: str) -> bool:
    """True iff ``token`` is a plain diatonic Roman numeral (no accidental/slash).

    Rejects chromatic / secondary tokens (``bII``, ``V/V``, ``#iv``) -- which are
    a non-goal of this slice and cannot be rendered by the diatonic engine -- while
    accepting quality-decorated diatonic numerals (``vii°``, ``III+``).  Use it on
    a token already passed through :func:`normalise_pattern` (so ``T``/``S``/``D``
    shorthand has become Roman).
    """
    t = (token or "").strip()
    if any(c in t for c in "/()"):
        return False
    core = t.replace("°", "").replace("o", "").replace("+", "")
    if any(c in core for c in "b#♭♯"):       # flat / sharp accidental
        return False
    try:
        roman_token_to_index(t)
        return True
    except ValueError:
        return False


def default_keys(mode: str) -> List[str]:
    """The 12 practical keys of ``mode`` (used by the motive lab's default sweep)."""
    return list(DEFAULT_MAJOR_KEYS if mode == "major" else DEFAULT_MINOR_KEYS)


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
    cadence_type: str = ""            # display only: authentic|plagal|half|deceptive
    strict_bass: bool = False


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

    def _check_diatonic(self, tokens) -> None:
        """Reject chromatic / secondary tokens (a non-goal) after normalisation."""
        for orig, norm in zip(tokens, normalise_pattern(list(tokens))):
            if not is_diatonic_roman(norm):
                raise ValueError(
                    f"chromatic/secondary token {orig!r} is not supported yet "
                    f"(a non-goal); use diatonic Roman numerals or T/S/D shorthand")

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
            roman_token_to_index(ip.degree)         # raises on a bad token
            if not ip.inversions:
                raise ValueError("inversion requires a non-empty 'inversions' list")
            if any(i not in (0, 1, 2) for i in ip.inversions):
                raise ValueError("inversions must be a subset of {0,1,2} (triads)")
            self._check_len(len(ip.inversions))

        elif self.concept in ("cadence", "voice_leading"):
            cp = cadence_params(p)
            if not cp.pattern:
                raise ValueError(f"{self.concept} requires a non-empty 'pattern'")
            self._check_diatonic(cp.pattern)        # raises on bad/chromatic token
            self._check_len(len(cp.pattern))

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
            self._check_diatonic(pp.progression)
            if len(pp.upper_degrees) != len(pp.progression):
                raise ValueError(
                    "polyphonic_harmony needs one upper_degree per progression chord")
            if pp.bass_degrees and len(pp.bass_degrees) != len(pp.progression):
                raise ValueError(
                    "polyphonic_harmony bass_degrees must match progression length")
            if any(not (1 <= d <= 14) for d in pp.upper_degrees):
                raise ValueError("polyphonic upper_degrees must be in 1..14")
            self._check_len(len(pp.progression))

        elif self.concept == "reduction":
            rp = reduction_params(p)
            if rp.skeleton:
                self._check_diatonic(rp.skeleton)
                self._check_len(len(rp.skeleton))

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
            specs.append(HarmonyExerciseSpec(
                exercise_id=f"lab_inv_{self.mode}_{_ident(tonic)}_{_ident(ip.degree)}",
                title=f"{ip.degree} in {tonic} {_mode_word(self.mode)} (root position)",
                drill="function", render="block", mode=self.mode,
                pattern=[ip.degree], keys=[tonic],
                description=(f"The root-position {ip.degree} triad underlying the "
                             f"inversion experiment."),
            ))

        elif self.concept in ("cadence", "voice_leading"):
            cp = cadence_params(p)
            roman = normalise_pattern(list(cp.pattern))   # validate() ensured diatonic
            label = "–".join(cp.pattern)
            specs.append(HarmonyExerciseSpec(
                exercise_id=f"lab_{self.concept}_{self.mode}_{_ident(tonic)}_{_ident('_'.join(roman))}",
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
                exercise_id=f"lab_poly_{self.mode}_{_ident(tonic)}_{_ident('_'.join(roman))}",
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
                exercise_id=f"lab_reduction_{self.mode}_{_ident(tonic)}",
                title=f"Reduced skeleton in {tonic} {_mode_word(self.mode)}",
                drill="function", render="block", mode=self.mode,
                pattern=normalise_pattern(list(rp.skeleton)), keys=[tonic],
                description="The explicit reduced harmonic skeleton.",
            ))

        elif self.concept == "drill":
            # Passthrough: the embedded native HarmonyExerciseSpec *is* the
            # playable drill.  Rebuilt (and re-validated) from the stored dict so
            # the trainer receives exactly the original exercise.
            specs.append(HarmonyExerciseSpec.from_dict(self.parameters["exercise"]))

        else:  # motive -> monophonic melody, no chord-drill representation
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
        ident = f"{_ident(tonic)}_{_ident(degree)}"

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
        ident = f"{_ident(tonic)}_{_ident('_'.join(pattern))}"

    elif concept == "polyphonic_harmony":
        progression = list(req.get("progression") or
                           (["I", "V", "I"] if mode == "major" else ["i", "VII", "i"]))
        upper = list(req.get("upper_degrees") or [3] * len(progression))
        params = {"progression": progression, "upper_degrees": upper}
        ident = f"{_ident(tonic)}_{_ident('_'.join(progression))}"

    else:  # motive
        degrees = list(req.get("degrees") or [1, 3, 5, 3])
        params = {"degrees": degrees}
        if req.get("keys"):
            params["keys"] = list(req["keys"])
        ident = f"{_ident('_'.join(str(d) for d in degrees))}_{_ident(tonic)}"

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
