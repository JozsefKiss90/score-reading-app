"""Chord Progression Foundations — the beginner C/G/F guided lesson.

One guided lesson made of **12 selectable examples**: four Roman-numeral
families (the transposition families), each shown in C, G and F major:

* ``full_key_major`` (group A) — the full diatonic chord field
  I–ii–iii–IV–V–vi–vii°;
* ``I_IV_V_I``       (group B) — the basic functional loop;
* ``ii_V_I``         (group C) — predominant → dominant → tonic;
* ``ii7_V7_I``       (group D) — the same path with genuine seventh chords.

This module is a **presentation model only**.  It owns no theory and no
renderer: every chord, spelling, quality, Roman numeral and function is read
off :func:`harmony.exercise_spec.compile_exercise` (and thence
:mod:`theory.diatonic_harmony`), every playable example is a canonical
:class:`~harmony.exercise_spec.HarmonyExerciseSpec` wrapped in the
curriculum's ``drill``-passthrough :class:`~harmony.lab_spec.LabExperimentSpec`,
and the per-chord table shown beside the score is *derived* from the compiled
chords — the same objects the trainer payload and the MusicXML annotations are
built from, so table and score can never disagree.

Canonical reuse (never duplicate a leaf that already exists):

* group A reuses the shipped full-key drills ``major_fullkey_block_{C,G,F}``
  (curriculum leaves ``ex:drill_major_fullkey_block_*`` under Scales);
* B1 / C1 reuse the cadence catalogue's reference-key drills
  ``atlas_function_I_IV_V_I_major_C`` / ``atlas_function_ii_V_I_major_C``
  (leaves under Cadences);
* the remaining seven examples are new drills registered under the bridge
  lesson (see :func:`new_foundation_exercise_specs`).  B/C in G and F use the
  Atlas :func:`~harmony.atlas.function_spec` factory — the exact spec an Atlas
  cadence-map click in those keys generates, so the ids stay canonical; the
  seventh-chord examples get a ``foundations_`` id because no Atlas cadence
  node exists for a seventh pattern (the Atlas ontology is triads-only).

Atlas honesty follows :func:`harmony.curriculum._atlas_refs_for_native`'s
tetrad rule exactly (drift-tested): a triad row claims its scale / degree /
triad / quality / layer / function nodes; a seventh-chord row claims only the
scale, its *base* degree (ii7 is genuinely built on degree 2) and its
function — never a triad, quality or layer node it does not match.

Pure + deterministic: standard library + theory engine + spec layers only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from theory.diatonic_harmony import DiatonicTriad, generate_scale, parse_pitch_class
from harmony.exercise_spec import (
    HarmonyExerciseSpec,
    compile_exercise,
    degree_labels_for_mode,
    MAX_CHORDS_PER_SPEC,
    _full_key_specs,
    _key_slug,
)
from harmony.lab_spec import LabExperimentSpec
from harmony.atlas import (
    _slug,
    cadence_id,
    degree_id,
    function_id,
    function_spec,
    layer_id,
    quality_id,
    scale_id,
    triad_id,
)


SCHEMA_VERSION = "progression-foundations/v1"

#: The three keys of the lesson, in teaching order (no accidentals, one sharp,
#: one flat — the beginner's first key-signature contrast).
FOUNDATION_KEYS = ("C", "G", "F")

#: Beginner glosses shown ALONGSIDE the engine's canonical function labels
#: (presentation wording only — the labels themselves come from the engine).
FUNCTION_GLOSS = {
    "tonic": "home",
    "predominant": "prepares the tension",
    "subdominant": "prepares the tension",
    "dominant": "tension pointing home",
    "mediant": "between home and tension",
}


@dataclass(frozen=True)
class FoundationFamily:
    """One transposition family: a Roman pattern shared by three keys."""

    family_id: str            # stable transposition-family identifier
    letter: str               # display group letter A..D
    title: str
    roman_label: str          # e.g. "ii–V–I"
    tokens: Optional[tuple]   # function-drill tokens; None -> full_key drill
    blurb: str


FAMILIES = (
    FoundationFamily(
        family_id="full_key_major", letter="A",
        title="The full diatonic chord field",
        roman_label="I–ii–iii–IV–V–vi–vii°", tokens=None,
        blurb=("Stack a triad on every note of the scale: each scale degree "
               "carries its own chord, and the pattern of qualities "
               "(major–minor–minor–major–major–minor–diminished) is the same "
               "in every major key."),
    ),
    FoundationFamily(
        family_id="I_IV_V_I", letter="B",
        title="The basic functional loop",
        roman_label="I–IV–V–I", tokens=("I", "IV", "V", "I"),
        blurb=("Home (tonic), a step away (subdominant), tension (dominant), "
               "home again — the smallest complete harmonic journey."),
    ),
    FoundationFamily(
        family_id="ii_V_I", letter="C",
        title="Predominant → dominant → tonic",
        roman_label="ii–V–I", tokens=("ii", "V", "I"),
        blurb=("The supertonic chord prepares the tension, the dominant "
               "carries it, the tonic resolves it — the classic ii–V–I."),
    ),
    FoundationFamily(
        family_id="ii7_V7_I", letter="D",
        title="The same path with seventh chords",
        roman_label="ii7–V7–I", tokens=("ii7", "V7", "I"),
        blurb=("Add one more diatonic third on top of ii and V: four-note "
               "seventh chords with the same roots, degrees and functions — "
               "richer colour, same journey."),
    ),
)

_FAMILY_BY_ID = {f.family_id: f for f in FAMILIES}


@dataclass(frozen=True)
class FoundationExample:
    """One selectable example: a family rendered in one key."""

    example_id: str
    family_id: str
    group_letter: str
    ordinal: int              # 1..3 within the group (C, G, F order)
    key: str                  # spelled tonic, e.g. "G"
    reused: bool              # True -> the drill is an existing canonical leaf

    @property
    def label(self) -> str:
        """The short display label, e.g. ``"B2"``."""
        return f"{self.group_letter}{self.ordinal}"

    @property
    def family(self) -> FoundationFamily:
        return _FAMILY_BY_ID[self.family_id]

    def to_dict(self) -> Dict:
        return {
            "schema": SCHEMA_VERSION,
            "exampleId": self.example_id,
            "familyId": self.family_id,
            "groupLetter": self.group_letter,
            "ordinal": self.ordinal,
            "key": self.key,
            "reused": self.reused,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "FoundationExample":
        return cls(
            example_id=d["exampleId"], family_id=d["familyId"],
            group_letter=d["groupLetter"], ordinal=int(d["ordinal"]),
            key=d["key"], reused=bool(d["reused"]),
        )


# ---------------------------------------------------------------------------
# The canonical exercise spec of each example
# ---------------------------------------------------------------------------

#: The shipped full-key drills group A reuses (canonical by construction: the
#: same builder that feeds the trainer's default set and the Scales leaves).
_FULL_KEY_SPECS = {s.exercise_id: s for s in _full_key_specs("major", "block")}

#: Which (family, key) pairs reuse an existing canonical drill.  The cadence
#: catalogue registers the reference-key (C) I–IV–V–I and ii–V–I drills under
#: Cadences; the full-key drills live under Scales.
_REUSED = {
    ("full_key_major", "C"), ("full_key_major", "G"), ("full_key_major", "F"),
    ("I_IV_V_I", "C"),
    ("ii_V_I", "C"),
}


def _example_id(family: FoundationFamily, key: str) -> str:
    return f"foundations_{family.family_id.lower()}_{_key_slug(key)}"


def foundation_examples() -> List[FoundationExample]:
    """The 12 examples, in group (A..D) then key (C, G, F) order."""
    out: List[FoundationExample] = []
    for fam in FAMILIES:
        for i, key in enumerate(FOUNDATION_KEYS, start=1):
            out.append(FoundationExample(
                example_id=_example_id(fam, key),
                family_id=fam.family_id,
                group_letter=fam.letter,
                ordinal=i,
                key=key,
                reused=(fam.family_id, key) in _REUSED,
            ))
    return out


def exercise_spec_for(example: FoundationExample) -> HarmonyExerciseSpec:
    """The canonical playable drill behind an example.

    Reused examples return the *existing* canonical spec (same id, same
    compiled chords as the leaf that already owns it); new ones construct
    theirs through the same factories the rest of the app uses.
    """
    fam = example.family
    key = example.key
    if fam.tokens is None:
        return _FULL_KEY_SPECS[f"major_fullkey_block_{_key_slug(key)}"]
    if fam.family_id == "ii7_V7_I":
        # No Atlas cadence node exists for a seventh pattern (the Atlas
        # ontology is triads-only), so these ids live in the foundations
        # namespace rather than claiming an atlas_function_* origin.
        return HarmonyExerciseSpec(
            exercise_id=f"foundations_ii7_V7_I_{_key_slug(key)}",
            title=f"ii7–V7–I in {key} major",
            drill="function", render="block", mode="major",
            pattern=list(fam.tokens), keys=[key],
            description=(f"The ii–V–I path as diatonic seventh chords in "
                         f"{key} major: same degrees and functions, one more "
                         f"stacked third."),
        )
    # B/C: the Atlas function_spec factory — the exact spec an Atlas
    # cadence-map click in this key generates, so the id stays canonical.
    return function_spec(list(fam.tokens), fam.roman_label, "major", [key])


def wrap_drill(hs: HarmonyExerciseSpec) -> LabExperimentSpec:
    """Wrap a native drill in the passthrough ``drill`` LabExperimentSpec.

    Mirrors :func:`harmony.curriculum._wrap_native` (drift-tested), which this
    module cannot import — the curriculum imports *us* to register the lesson.
    """
    key = hs.key or f"{(hs.keys or ['C'])[0]} major"
    spec = LabExperimentSpec(
        experiment_id=f"drill_{hs.exercise_id}",
        title=hs.title,
        concept="drill",
        mode=hs.mode,
        key=key,
        render=hs.render,
        parameters={"exercise": hs.to_dict()},
        description=hs.description,
    )
    spec.validate()
    return spec


def lab_spec_for(example: FoundationExample) -> LabExperimentSpec:
    return wrap_drill(exercise_spec_for(example))


def curriculum_node_id(example: FoundationExample) -> str:
    """The curriculum leaf that owns this example's drill (reused or new)."""
    return f"ex:drill_{exercise_spec_for(example).exercise_id}"


def new_foundation_exercise_specs() -> List[HarmonyExerciseSpec]:
    """The drills WITHOUT an existing canonical leaf, in registration order.

    These are the leaves the curriculum's bridge lesson registers (seven:
    I–IV–V–I and ii–V–I in G and F, ii7–V7–I in C, G and F); the other five
    examples reference the pre-existing leaves instead of duplicating them.
    """
    return [exercise_spec_for(e) for e in foundation_examples() if not e.reused]


# ---------------------------------------------------------------------------
# Display spellings (♯ / ♭ with an ASCII-internal fallback)
# ---------------------------------------------------------------------------

def display_pitch(name: str) -> str:
    """``"Bb" -> "B♭"``, ``"F#" -> "F♯"`` (the canonical fields stay ASCII)."""
    letter, alter = parse_pitch_class(name)
    if alter > 0:
        return letter + "♯" * alter
    if alter < 0:
        return letter + "♭" * (-alter)
    return letter


def display_chord_symbol(symbol: str) -> str:
    """Unicode accidentals on a chord symbol's root (``"Bb" -> "B♭"``)."""
    out = symbol[:1]
    i = 1
    while i < len(symbol) and symbol[i] in "#b":
        out += "♯" if symbol[i] == "#" else "♭"
        i += 1
    return out + symbol[i:]


# ---------------------------------------------------------------------------
# The derived chord table (one row per compiled chord == per score measure)
# ---------------------------------------------------------------------------

def _base_degree_roman(t: DiatonicTriad) -> str:
    """The degree-node Roman a chord may claim: a tetrad projects onto its
    base degree BY INDEX (``ii7`` -> ``ii``), mirroring the curriculum rule."""
    if len(t.pitches) > 3:
        return degree_labels_for_mode(t.mode)[t.degree_index]
    return t.roman


def chord_atlas_refs(t: DiatonicTriad) -> List[str]:
    """The honest Atlas refs of ONE major-mode diatonic chord.

    The per-chord slice of :func:`harmony.curriculum._atlas_refs_for_native`
    (drift-tested against it): a triad claims scale / degree / triad /
    quality / layer / function; a seventh chord claims only scale, base
    degree and function — the Atlas has no seventh-chord nodes, and landing
    G7 on the G-triad node would be the ``base_roman`` dishonesty.
    """
    key = t.key.split()[0]
    is_tetrad = len(t.pitches) > 3
    refs = [scale_id(key, t.mode), degree_id(t.mode, _base_degree_roman(t))]
    if not is_tetrad:
        refs.append(triad_id(key, t.mode, t.degree_index))
        refs.append(quality_id(t.chord_quality))
        refs.append(layer_id(t.interval_layer))
    refs.append(function_id(t.mode, t.function_label))
    return refs


def _row_lessons(t: DiatonicTriad) -> List[str]:
    """Related curriculum references per row, derived from the chord itself."""
    refs = ["lesson:scales_major", "lesson:degrees_major",
            "lesson:functions_major"]
    if len(t.pitches) > 3:
        refs.append("lesson:sevenths_ii_v_i")
        if t.chord_quality == "dominant_seventh":
            refs.append("lesson:dominant_seventh")
        else:
            refs.append("lesson:seventh_qualities")
    else:
        refs.append("lesson:triad_qualities")
    return refs


def chord_table(example: FoundationExample) -> List[Dict]:
    """One derived row per score measure, straight off the compiled chords.

    Every value is read from the same :class:`DiatonicTriad` objects the
    MusicXML annotations and the trainer targets are built from — there is no
    second, hand-authored table to drift.
    """
    compiled = compile_exercise(exercise_spec_for(example))
    rows: List[Dict] = []
    for c in compiled.chords:
        t = c.triad
        rows.append({
            "position": c.index + 1,
            "measureNumber": c.index + 1,
            "key": t.key,
            "scale": list(t.scale_pitches),
            "scaleDisplay": [display_pitch(p) for p in t.scale_pitches],
            "degree": t.degree_number,
            "roman": t.roman,
            "chordSymbol": t.chord_symbol,
            "chordSymbolDisplay": display_chord_symbol(t.chord_symbol),
            "chordNotes": list(t.pitches),
            "chordNotesDisplay": [display_pitch(p) for p in t.pitches],
            "quality": t.chord_quality,
            "qualityLabel": t.chord_quality.replace("_", " "),
            "function": t.function_label,
            "functionGloss": FUNCTION_GLOSS.get(t.function_label, ""),
            "chordSize": "seventh chord" if len(t.pitches) > 3 else "triad",
            "pitchClasses": list(t.pitch_classes),
            "atlasNodes": chord_atlas_refs(t),
            "relatedLessons": _row_lessons(t),
        })
    return rows


# ---------------------------------------------------------------------------
# The lesson payload (consumed by beat_selector/foundations.js)
# ---------------------------------------------------------------------------

_INTRO = [
    "Every chord in this lesson comes from one major scale. Pick a scale "
    "note (a degree), stack two or three more scale notes in thirds on top, "
    "and you have that degree's chord — its Roman numeral names the degree, "
    "its chord symbol names the actual notes.",
    "Each example below is a short score, one chord per bar. Start with the "
    "key, the score and the chord symbols; reveal the Roman numerals and the "
    "analysis columns when you want the full picture. Play along with MIDI — "
    "the score validates the actual chord tones.",
    "The C, G and F versions of each group are the SAME Roman pattern moved "
    "to another key (\"same pattern in another key\"): the numerals, degrees, "
    "functions and quality pattern stay fixed while the chord names, "
    "pitches and key signature change.",
]

_TRANSPOSITION = {
    "note": "Same pattern in another key — what transposition keeps and what "
            "it changes:",
    "invariant": ["Roman progression", "Degree relationships",
                  "Functional direction (home → preparation → tension → home)",
                  "Chord-quality pattern"],
    "changing": ["Actual chord names", "Pitch spelling", "Key signature",
                 "Absolute pitches"],
}


def _family_cadence_id(fam: FoundationFamily) -> Optional[str]:
    """The Atlas cadence node shared by a family's three keys, where one
    exists (I–IV–V–I and ii–V–I; the full field and the seventh pattern have
    no cadence node — the Atlas cadence catalogue is triads-only)."""
    if fam.family_id in ("I_IV_V_I", "ii_V_I"):
        return cadence_id(f"{_slug(fam.roman_label)}_major")
    return None


def example_payload(example: FoundationExample) -> Dict:
    """The full JSON-safe payload of one example (score request + table)."""
    hs = exercise_spec_for(example)
    lab = lab_spec_for(example)
    scale = generate_scale(example.key, "major")
    table = chord_table(example)
    return {
        "exampleId": example.example_id,
        "familyId": example.family_id,
        "groupLetter": example.group_letter,
        "label": example.label,
        "key": example.key,
        "keyDisplay": f"{display_pitch(example.key)} major",
        "title": f"{example.label} · {example.family.roman_label} in "
                 f"{display_pitch(example.key)} major",
        "reused": example.reused,
        "curriculumNodeId": curriculum_node_id(example),
        "exerciseId": hs.exercise_id,
        "fifths": scale.fifths,
        "scale": list(scale.scale_pitches),
        "scaleDisplay": [display_pitch(p) for p in scale.scale_pitches],
        "chordSymbols": [r["chordSymbol"] for r in table],
        "chordSymbolsDisplay": [r["chordSymbolDisplay"] for r in table],
        "romans": [r["roman"] for r in table],
        "labSpec": lab.to_dict(),
        "table": table,
    }


def build_foundations_payload() -> Dict:
    """The complete lesson payload: intro + 4 groups × 3 examples + tables."""
    groups = []
    for fam in FAMILIES:
        examples = [e for e in foundation_examples()
                    if e.family_id == fam.family_id]
        groups.append({
            "letter": fam.letter,
            "familyId": fam.family_id,
            "title": fam.title,
            "romanLabel": fam.roman_label,
            "blurb": fam.blurb,
            "atlasCadenceId": _family_cadence_id(fam),
            "examples": [example_payload(e) for e in examples],
        })
    return {
        "schema": SCHEMA_VERSION,
        "title": "Chord Progression Foundations — C, G and F major",
        "intro": _INTRO,
        "transposition": _TRANSPOSITION,
        "keys": list(FOUNDATION_KEYS),
        "functionGloss": dict(FUNCTION_GLOSS),
        "groups": groups,
    }


__all__ = [
    "SCHEMA_VERSION",
    "FOUNDATION_KEYS",
    "FUNCTION_GLOSS",
    "FoundationFamily",
    "FoundationExample",
    "FAMILIES",
    "foundation_examples",
    "exercise_spec_for",
    "lab_spec_for",
    "wrap_drill",
    "curriculum_node_id",
    "new_foundation_exercise_specs",
    "chord_atlas_refs",
    "chord_table",
    "example_payload",
    "build_foundations_payload",
    "display_pitch",
    "display_chord_symbol",
]
