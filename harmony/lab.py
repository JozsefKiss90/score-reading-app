"""Generation engine for the Music Theory Laboratory.

This module turns a :class:`~harmony.lab_spec.LabExperimentSpec` into a
deterministic, pure intermediate model -- a :class:`LabExperiment` made of an
ordered list of :class:`LabMeasure` objects.  Each measure carries:

* the rendered note streams for the two staves (:class:`LabNote`),
* a rich :class:`LabAnnotation` (chord identity + concept-specific labels such as
  figured bass / inversion / voice-leading prose / motive label + precomputed
  Atlas node ids), and
* the data the runtime MIDI validator needs (``target_pitch_classes``,
  ``bass_pitch_class``, ``expected_by_beat``).

It is **pure**: standard library + :mod:`theory.diatonic_harmony` +
:mod:`harmony.atlas` node-id helpers only -- no Qt, Verovio, MIDI, or MusicXML.
MusicXML and the trainer payload are built from this model by
:mod:`harmony.lab_musicxml`.  Nothing here re-encodes a theory table: every
chord, quality, Roman numeral, function, interval layer, and spelling is derived
from :func:`theory.diatonic_harmony.generate_diatonic_triads` /
:func:`~theory.diatonic_harmony.generate_scale` /
:func:`~theory.diatonic_harmony.transpose_degree_pattern`.

The implemented concepts (Phases 2-5 + piano-technique ticket 01):

* ``inversion``          -- one chord, invariant upper tones, a changing bass.
* ``cadence`` / ``voice_leading`` -- a progression as block triads or an
  SATB-like grand-staff voicing with derived voice-leading annotation.
* ``motive``             -- a scale-degree melodic cell transposed across keys.
* ``polyphonic_harmony`` -- two independent voices whose vertical slices imply a
  triad per measure.
* ``technique``          -- a multi-measure, single-key melodic phrase (the
  piano-technique phrase engine; graded as an ordered pitch-class walk).

``reduction`` is reserved (``compile_lab`` raises ``NotImplementedError``); its
spec validates and -- given an explicit skeleton -- down-compiles to a drill, so
the Schenkerian-reduction phase slots in without an architectural change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from theory.diatonic_harmony import (
    DiatonicTriad,
    build_seventh_chord,
    generate_diatonic_triads,
    generate_scale,
    melodic_minor_raised,
    transpose_degree_pattern,
    roman_token_to_index,
    parse_seventh_token,
    parse_pitch_class,
    note_pc,
    LETTER_BASE_PC,
    LETTER_INDEX,
    _mode_word,
)
from harmony.atlas import scale_id, degree_id, triad_id
from harmony.exercise_spec import MAX_CHORDS_PER_SPEC, normalise_pattern
from harmony.lab_spec import (
    LabExperimentSpec,
    SCHEMA_VERSION,
    TECHNIQUE_SLOTS,
    tonic_of,
    default_keys,
    inversion_params,
    cadence_params,
    motive_params,
    polyphonic_params,
    technique_params,
    split_figured_pattern,
)


# ---------------------------------------------------------------------------
# Constants (musical, not divisions-specific -- the renderer maps to ticks)
# ---------------------------------------------------------------------------

TREBLE_OCTAVE = 4          # base octave for root-position treble voicings
BASS_OCTAVE = 3            # octave for the bass note / SATB bass
SATB_BASE_OCTAVE = 4       # base octave for SATB close-position upper voices

#: Inversion -> figured-bass + label.  ``"6"`` is the common shorthand for 6/3;
#: a tetrad (ticket 11 / plan G1c) figures 7 · 6/5 · 4/3 · 4/2 instead.
_FIGURED_BASS = {0: "5/3", 1: "6", 2: "6/4"}
_FIGURED_BASS_TETRAD = {0: "7", 1: "6/5", 2: "4/3", 3: "4/2"}
_INVERSION_LABEL = {0: "root position", 1: "first inversion",
                    2: "second inversion", 3: "third inversion"}


def _figures_for(chord: DiatonicTriad) -> dict:
    """The figured-bass table matching the chord's size (triad vs tetrad)."""
    return _FIGURED_BASS_TETRAD if len(chord.pitches) > 3 else _FIGURED_BASS


def _inversion_annotation(inv: int, bass_name: str,
                          figures: dict = _FIGURED_BASS) -> dict:
    """The annotation fields an inversion always carries together."""
    return dict(inversion=inv, figured_bass=figures[inv],
                inversion_label=_INVERSION_LABEL[inv], bass_note=bass_name)

#: Scale-degree caret labels for motive degrees (^1..^7, octave-folded).
_CARET = {1: "^1", 2: "^2", 3: "^3", 4: "^4", 5: "^5", 6: "^6", 7: "^7"}


# ---------------------------------------------------------------------------
# Pure intermediate model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LabNote:
    """One rendered note (or rest) on a staff.  ``note_type`` fixes the duration."""

    step: str                       # "C".."B"
    alter: int                      # signed accidental count
    octave: int
    note_type: str                  # "whole" | "half" | "quarter" | "eighth" | "16th"
    is_chord_tone: bool = False     # 2nd+ note of a stacked chord (<chord/>)
    is_rest: bool = False
    # Per-note notation marks (ticket 02) -- presentation only, "" for none;
    # the serializer emits a <notations> wrapper only when one is set.
    fingering: str = ""             # "1".."5"
    slur: str = ""                  # "start" | "stop"
    articulation: str = ""          # "staccato" | "accent"

    @property
    def midi(self) -> int:
        return (self.octave + 1) * 12 + LETTER_BASE_PC[self.step] + self.alter

    @property
    def pitch_class(self) -> int:
        return self.midi % 12


@dataclass(frozen=True)
class LabAnnotation:
    """Rich, JSON-serialisable per-measure annotation (a superset of a triad)."""

    key: str
    mode: str
    roman: Optional[str] = None
    chord_symbol: Optional[str] = None
    root: Optional[str] = None
    quality: Optional[str] = None
    chord_tones: Tuple[str, ...] = ()
    interval_layer: Optional[str] = None
    function_label: Optional[str] = None
    scale_degree_name: Optional[str] = None
    degree_number: Optional[int] = None
    explanation: str = ""
    # concept-specific (consumed by the explanation pane; harmony_trainer.js
    # ignores unknown fields):
    inversion: Optional[int] = None
    figured_bass: Optional[str] = None
    inversion_label: Optional[str] = None
    bass_note: Optional[str] = None
    voices: Tuple[Tuple[str, str], ...] = ()      # ((name, spelled+octave), ...)
    common_tones: Tuple[str, ...] = ()
    bass_motion: Optional[str] = None
    tendency_tones: Tuple[str, ...] = ()
    cadence_type: Optional[str] = None
    motive_label: Optional[str] = None
    degree_labels: Tuple[str, ...] = ()
    implied_roman: Optional[str] = None
    implied_chord: Optional[str] = None
    lab_note: str = ""
    # Atlas linkage (precomputed with the existing node-id helpers):
    atlas_scale_id: Optional[str] = None
    atlas_degree_id: Optional[str] = None
    atlas_triad_id: Optional[str] = None


@dataclass(frozen=True)
class LabStepTarget:
    """One ordered simultaneity step of a measure (piano-technique ticket 03).

    ``pcs`` are the pitch classes that must be HELD CONCURRENTLY to satisfy
    the step; ``min_distinct`` is the minimum number of distinct MIDI keys
    sounding among them (octave doubling: one pc, two keys).  The JS grader
    walks these in order exactly like the scalar arpeggio walk.
    """

    pcs: Tuple[int, ...]
    min_distinct: int


@dataclass(frozen=True)
class LabMeasure:
    """One measure of a compiled experiment, fully specified for render+MIDI+guide."""

    index: int                              # 0-based == absMeasure
    render: str                             # block|arpeggio|voice_leading|polyphonic|melody
    group: str
    key_display: str                        # "C major"
    tonic: str                              # "C"
    mode: str
    fifths: int
    scale_pitches: Tuple[str, ...]          # the key's 7 scale pitches (always set)
    staff1: Tuple[LabNote, ...]             # treble (G clef)
    staff2: Tuple[LabNote, ...]             # bass (F clef)
    annotation: LabAnnotation
    underlying: Optional[DiatonicTriad]     # implied/underlying root-position triad
    target_pitch_classes: Tuple[int, ...]   # what the MIDI validator expects (ordered)
    bass_pitch_class: Optional[int] = None
    expected_by_beat: Optional[Dict[int, List[int]]] = None  # arpeggio/melody/strict
    strict_bass: bool = False               # demand bass_pitch_class as the LOWEST note
    #: Ordered simultaneity steps (ticket 03) -- set only when a step needs
    #: more than one concurrent key; scalar walks stay None (payload unchanged).
    step_targets: Optional[Tuple[LabStepTarget, ...]] = None

    def sounding_midis(self) -> List[int]:
        out = [n.midi for n in (self.staff1 + self.staff2) if not n.is_rest]
        return sorted(out)


@dataclass
class LabExperiment:
    """A fully compiled experiment: the ordered measures + the trainer skeleton."""

    spec: LabExperimentSpec
    title: str
    measures: List[LabMeasure]
    exercise_specs: List = field(default_factory=list)   # == spec.to_exercise_specs()

    def __len__(self) -> int:
        return len(self.measures)


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------

def _midi(step: str, alter: int, octave: int) -> int:
    return (octave + 1) * 12 + LETTER_BASE_PC[step] + alter


def _octave_of(midi: int) -> int:
    return midi // 12 - 1


def _note_from_spelled(name: str, octave: int, note_type: str,
                       is_chord_tone: bool = False) -> LabNote:
    step, alter = parse_pitch_class(name)
    return LabNote(step, alter, octave, note_type, is_chord_tone=is_chord_tone)


def _treble_octave_for(triad: DiatonicTriad, i: int) -> int:
    """The notated octave of root-position chord tone ``i`` (root/third/fifth)."""
    return _octave_of(triad.midi_pitches[i])


def _treble_block_notes(triad: DiatonicTriad) -> Tuple[LabNote, ...]:
    """Root-position whole-note chord (root plain, third/fifth as <chord/>)."""
    return tuple(
        _note_from_spelled(name, _treble_octave_for(triad, i), "whole",
                           is_chord_tone=(i > 0))
        for i, name in enumerate(triad.pitches)
    )


def _treble_arpeggio_notes(triad: DiatonicTriad) -> Tuple[LabNote, ...]:
    """Chord tones as quarters, rest-padded to the 4/4 bar (mirrors the trainer)."""
    notes = [
        _note_from_spelled(name, _treble_octave_for(triad, i), "quarter")
        for i, name in enumerate(triad.pitches)
    ]
    for _ in range(4 - len(notes)):
        notes.append(LabNote("C", 0, TREBLE_OCTAVE, "quarter", is_rest=True))
    return tuple(notes)


def _bass_note(name: str, octave: int = BASS_OCTAVE) -> LabNote:
    return _note_from_spelled(name, octave, "whole")


def _scale_note(scale, degree: int) -> Tuple[str, int, int]:
    """``(step, alter, octave)`` of 1-based scale ``degree`` (may exceed 7)."""
    i = degree - 1
    name = scale.scale_pitches[i % 7]
    midi = scale.midi_pitches[i % 7] + 12 * (i // 7)
    step, alter = parse_pitch_class(name)
    return step, alter, _octave_of(midi)


def _nearest_octave(step: str, alter: int, target_midi: int) -> int:
    """Octave (2..6) whose pitch is nearest ``target_midi`` (ties -> lower)."""
    best = None
    for octave in range(2, 7):
        midi = (octave + 1) * 12 + LETTER_BASE_PC[step] + alter
        key = (abs(midi - target_midi), midi)
        if best is None or key < best[0]:
            best = (key, octave)
    return best[1]


def _annotation_for(triad: DiatonicTriad, tonic: str, mode: str,
                    **extra) -> LabAnnotation:
    """Base annotation derived 1:1 from a chord, with Atlas ids stamped.

    A tetrad (V7) claims NO Atlas degree/triad node: the Atlas's 168 chord
    nodes are triads only, and honesty means refusing to land a seventh chord
    on the triad node that merely shares its root (the ``base_roman`` rule).
    """
    is_tetrad = len(triad.pitches) > 3
    return LabAnnotation(
        key=triad.key, mode=mode, roman=triad.roman,
        chord_symbol=triad.chord_symbol, root=triad.root,
        quality=triad.chord_quality, chord_tones=tuple(triad.pitches),
        interval_layer=triad.interval_layer, function_label=triad.function_label,
        scale_degree_name=triad.scale_degree_name, degree_number=triad.degree_number,
        explanation=triad.explanation_text,
        atlas_scale_id=scale_id(tonic, mode),
        atlas_degree_id=(None if is_tetrad else degree_id(mode, triad.roman)),
        atlas_triad_id=(None if is_tetrad
                        else triad_id(tonic, mode, triad.degree_index)),
        **extra,
    )


# ---------------------------------------------------------------------------
# Concept generators
# ---------------------------------------------------------------------------

def _gen_inversion(spec: LabExperimentSpec) -> List[LabMeasure]:
    ip = inversion_params(spec.parameters)
    tonic, mode = tonic_of(spec.key), spec.mode
    scale = generate_scale(tonic, mode)
    fifths = scale.fifths
    if parse_seventh_token(ip.degree) is not None:
        # A seventh degree (ticket 11 / plan G1c): four voicings, figures
        # 7 · 6/5 · 4/3 · 4/2.  build_seventh_chord enforces the mode gate.
        triad = build_seventh_chord(ip.degree, tonic, mode)
    else:
        triad = generate_diatonic_triads(tonic, mode)[roman_token_to_index(ip.degree)]
    figures = _figures_for(triad)
    triad_pcs = tuple(triad.pitch_classes)             # root/third/fifth(/seventh)
    group = f"{triad.roman} inversions in {triad.key}"

    measures: List[LabMeasure] = []
    for k, inv in enumerate(ip.inversions):
        bass_name = triad.pitches[inv]                 # 0=root,1=third,2=fifth,3=seventh
        bass_pc = note_pc(bass_name)
        bass = _bass_note(bass_name)

        # The MIDI validator reads only `pitchClasses` (== target_pitch_classes),
        # so strict bass-first ordering must live THERE, not only in
        # expected_by_beat.  Strict mode reuses harmony_trainer.js's ordered-tone
        # ("arpeggio") branch with the bass pitch class first.
        target = triad_pcs
        if spec.render == "arpeggio":
            staff1 = _treble_arpeggio_notes(triad)
            expected = {i + 1: [pc] for i, pc in enumerate(triad_pcs)}
        elif ip.strict_bass:  # block notation, bass required first
            staff1 = _treble_block_notes(triad)
            target = tuple([bass_pc] + [pc for pc in triad_pcs if pc != bass_pc])
            expected = {i + 1: [pc] for i, pc in enumerate(target)}
        else:  # block
            staff1 = _treble_block_notes(triad)
            expected = None

        invariant = "–".join(triad.pitches)
        lab_note = (
            f"{triad.chord_symbol} in {_INVERSION_LABEL[inv]} ({figures[inv]}): "
            f"the chord tones {invariant} are invariant; only the bass changes to "
            f"{bass_name}."
        )
        ann = _annotation_for(
            triad, tonic, mode, lab_note=lab_note,
            **_inversion_annotation(inv, bass_name, figures),
        )
        measures.append(LabMeasure(
            index=k, render=spec.render, group=group,
            key_display=triad.key, tonic=tonic, mode=mode, fifths=fifths,
            scale_pitches=tuple(scale.scale_pitches),
            staff1=staff1, staff2=(bass,), annotation=ann, underlying=triad,
            target_pitch_classes=target, bass_pitch_class=bass_pc,
            expected_by_beat=expected,
            # An inversion's bass is the task (plan G4/F4): plain block measures
            # are graded lowest-sounding-note-strict.  The legacy strict_bass
            # parameter instead encodes its demand as a bass-first ordered walk
            # (expected_by_beat), and arpeggio stays an ordered walk -- neither
            # carries the flag, so the panel never claims a lowest-note check
            # that the ordered branch is not making.
            strict_bass=(spec.render == "block" and expected is None),
        ))
    return measures


def _close_rotations(triad: DiatonicTriad) -> List[List[Tuple[str, int, int]]]:
    """The three ascending close-position stackings of (root, third, fifth)."""
    rots = []
    for r in range(3):
        order = [triad.pitches[(r + k) % 3] for k in range(3)]
        rots.append(_stack_ascending(order, SATB_BASE_OCTAVE))
    return rots


def _stack_ascending(names: List[str], base_octave: int
                     ) -> List[Tuple[str, int, int]]:
    """Assign octaves so ``names`` ascend by letter (bump on a letter wrap)."""
    out: List[Tuple[str, int, int]] = []
    prev_pos: Optional[int] = None
    octave = base_octave
    for name in names:
        step, alter = parse_pitch_class(name)
        pos = LETTER_INDEX[step]
        if prev_pos is not None and pos <= prev_pos:
            octave += 1
        out.append((step, alter, octave))
        prev_pos = pos
    return out


def _satb_progression(triads: List[DiatonicTriad],
                      soprano_pcs: Optional[List[Optional[int]]] = None
                      ) -> List[Dict[str, Tuple[str, int, int]]]:
    """Deterministic SATB-like voicing: smooth soprano, root in the bass.

    For each chord, the three upper voices are the close-position rotation whose
    soprano is nearest the previous soprano (the first chord targets ~C5); the
    bass is the chord root an octave below.  No voice crossing (each rotation is
    strictly ascending and the bass sits below the tenor).  This is a simple
    closed-position voicing, not a counterpoint engine (see the module docstring
    and the lab docs for the extension seam).

    ``soprano_pcs`` (ticket 16 / plan G3) demands a soprano pitch class per
    chord (``None`` = free): only the rotation topping that tone is eligible,
    and the whole upper-voice block may slide an octave so the demanded
    soprano still lands near the previous one (validate() guarantees the tone
    is a chord tone, so the rotation always exists).
    """
    out: List[Dict[str, Tuple[str, int, int]]] = []
    prev_sop: Optional[int] = None
    for k, triad in enumerate(triads):
        rots = _close_rotations(triad)
        b_step, b_alter = parse_pitch_class(triad.pitches[0])
        bass = (b_step, b_alter, BASS_OCTAVE)

        def sop_midi(rot):
            return _midi(*rot[2])

        target = 72 if prev_sop is None else prev_sop
        want = soprano_pcs[k] if soprano_pcs else None
        if want is not None:
            base = next(r for r in rots if sop_midi(r) % 12 == want)
            rots = [[(s, a, o + shift) for (s, a, o) in base]
                    for shift in (-1, 0, 1)
                    if _midi(base[0][0], base[0][1], base[0][2] + shift)
                    > _midi(*bass)]                    # tenor stays above bass
        best = min(rots, key=lambda r: (abs(sop_midi(r) - target), sop_midi(r)))
        tenor, alto, sop = best
        prev_sop = sop_midi(best)
        out.append({"S": sop, "A": alto, "T": tenor, "B": bass})
    return out


def _voice_leading_notes(voicing: Dict[str, Tuple[str, int, int]]
                         ) -> Tuple[Tuple[LabNote, ...], Tuple[LabNote, ...]]:
    """Render an SATB voicing as a treble [A,S] chord + a bass [B,T] chord."""
    def note(v, chord_tone):
        step, alter, octave = v
        return LabNote(step, alter, octave, "whole", is_chord_tone=chord_tone)

    treble = (note(voicing["A"], False), note(voicing["S"], True))
    bass = (note(voicing["B"], False), note(voicing["T"], True))
    return treble, bass


def _voice_leading_text(prev: Optional[DiatonicTriad], cur: DiatonicTriad,
                        scale) -> Tuple[Tuple[str, ...], Optional[str], Tuple[str, ...]]:
    """Derive (common tones, bass motion, tendency tones) relative to ``prev``.

    The degree-7 of a dominant-functioning chord is a *tendency tone*; it always
    resolves to the **tonic pitch** (degree 1), not to the next chord's root --
    so a deceptive ``V → vi`` still resolves the leading tone to the tonic while
    the bass moves elsewhere.  It is a true *leading tone* only when degree 7 is a
    semitone below the tonic (major mode); in natural minor degree 7 is a
    whole-step *subtonic* with no leading-tone pull (the modal cadence sound).
    """
    if prev is None:
        return (), None, ()
    prev_pcs = set(prev.pitch_classes)
    common = tuple(p for p in cur.pitches if note_pc(p) in prev_pcs)
    bass_motion = f"{prev.root} → {cur.root}"
    tendency: List[str] = []
    tonic_name = scale.scale_pitches[0]                # degree 1
    tonic_pc = note_pc(tonic_name)
    deg7_name = scale.scale_pitches[6]                 # degree 7
    deg7_pc = note_pc(deg7_name)
    if prev.function_label == "dominant" and deg7_pc in prev_pcs:
        is_deceptive = note_pc(cur.root) != tonic_pc
        if (tonic_pc - deg7_pc) % 12 == 1:             # semitone below -> leading tone
            txt = f"leading tone {deg7_name} → {tonic_name} (degree 7 → 1)"
            if is_deceptive:
                txt += (f"; the bass moves deceptively to {cur.roman} "
                        f"({cur.root}) instead of the tonic")
            tendency.append(txt)
        else:                                          # whole step -> subtonic (minor)
            txt = (f"subtonic {deg7_name} → {tonic_name} "
                   f"(♭7 → 1, whole step — no leading tone)")
            if is_deceptive:
                txt += f"; the bass moves deceptively to {cur.roman} ({cur.root})"
            tendency.append(txt)
    return common, bass_motion, tuple(tendency)


def _gen_voice_leading(spec: LabExperimentSpec) -> List[LabMeasure]:
    cp = cadence_params(spec.parameters)
    tonic, mode = tonic_of(spec.key), spec.mode
    scale = generate_scale(tonic, mode)
    fifths = scale.fifths
    # Figured tokens ("ii6") demand an inversion's chord member in the bass
    # (plan G4); validate() guarantees figures only appear with render="block".
    heads, inversions = split_figured_pattern(list(cp.pattern))
    roman = normalise_pattern(heads)
    triads = transpose_degree_pattern(roman, tonic, mode)
    # Relabel tokens (ticket 16, the cadential-6/4 relabel drill) rename what
    # the annotation CALLS each chord; compilation and grading use cp.pattern.
    shown_tokens = list(cp.relabel or cp.pattern)
    label = "–".join(shown_tokens)
    concept_word = "voice leading" if spec.concept == "voice_leading" else "cadence"
    group = f"{label} ({concept_word}) in {scale.key}"

    use_satb = (spec.render == "voice_leading")
    # A demanded soprano line (ticket 16 / plan G3): scale degrees -> pitch
    # classes; validate() guaranteed one chord tone per pattern chord.
    soprano_pcs = ([note_pc(scale.scale_pitches[d - 1])
                    for d in cp.soprano_degrees]
                   if cp.soprano_degrees else None)
    satb = (_satb_progression(triads, soprano_pcs) if use_satb
            else [None] * len(triads))

    measures: List[LabMeasure] = []
    prev_triad: Optional[DiatonicTriad] = None
    prev_bass_name: Optional[str] = None
    for k, triad in enumerate(triads):
        inv = inversions[k]
        triad_pcs = tuple(triad.pitch_classes)
        common, bass_motion, tendency = _voice_leading_text(prev_triad, triad, scale)

        if use_satb:
            voicing = satb[k]
            staff1, staff2 = _voice_leading_notes(voicing)
            voices = (
                ("soprano", _spell_octave(voicing["S"])),
                ("alto", _spell_octave(voicing["A"])),
                ("tenor", _spell_octave(voicing["T"])),
                ("bass", _spell_octave(voicing["B"])),
            )
            bass_name = triad.pitches[0]
            bass_pc = note_pc(bass_name)
            render = "voice_leading"
        else:  # block triads; the figure (if any) selects the bass chord member
            staff1 = _treble_block_notes(triad)
            bass_name = triad.pitches[inv]
            staff2 = (_bass_note(bass_name),)
            voices = ()
            bass_pc = note_pc(bass_name)
            render = "block"

        # Bass motion names the actual (possibly inverted) bass, not the root.
        if bass_motion is not None and prev_bass_name is not None:
            bass_motion = f"{prev_bass_name} → {bass_name}"

        # The cadential 6/4 (ticket 16 / plan G3+F3): a tonic-spelled 6/4
        # heading into a dominant is NOT tonic function — its 6th and 4th are
        # suspensions over the dominant bass.  Detected here, at the engine,
        # so every surface that renders this measure tells the truth.
        cadential_64 = (inv == 2 and roman[k].upper() == "I"
                        and k + 1 < len(triads)
                        and triads[k + 1].function_label == "dominant")
        func_word = ("dominant (cadential 6/4)" if cadential_64
                     else triad.function_label)
        sym = triad.chord_symbol if not inv else f"{triad.chord_symbol}/{bass_name}"
        bits = [f"{shown_tokens[k]} ({sym}, {func_word})"]
        if inv:
            bits.append(f"{_INVERSION_LABEL[inv]} ({_figures_for(triad)[inv]}) — "
                        f"{bass_name} in the bass")
        if bass_motion:
            bits.append(f"bass {bass_motion}")
        if common:
            bits.append("common tone " + "–".join(common))
        if tendency:
            bits.append(tendency[0])
        lab_note = "; ".join(bits) + "."

        if cadential_64:
            lab_note += (f" Cadential 6/4 — dominant in function despite the "
                         f"tonic spelling: the bass is already the dominant "
                         f"({bass_name}), and the 6th and 4th above it are "
                         f"suspensions that resolve down (6–5, 4–3) into the "
                         f"next chord. Hear this as an embellished dominant, "
                         f"not a tonic chord.")
        inv_extra = ({} if not inv
                     else _inversion_annotation(inv, bass_name,
                                                _figures_for(triad)))
        sop_name = _spell_octave(voicing["S"]) if use_satb else None
        sop_pc = _midi(*voicing["S"]) % 12 if use_satb else None
        if cp.dictation == "bass":
            # Bass-line dictation (ticket 11 / plan A1 level 5): the notation
            # and playback keep the FULL chord, but the graded target is the
            # bass alone — every measure demands its (possibly figured) bass.
            lab_note = (f"Bass-line dictation: play only the bass note "
                        f"({bass_name}). {lab_note}")
        elif cp.dictation == "soprano":
            # Soprano dictation (ticket 16 / plan G3): the PAC-vs-IAC ear —
            # full SATB playback, but the graded target is the top line.
            lab_note = (f"Soprano dictation: play only the top note "
                        f"({sop_name}). {lab_note}")
        ann = _annotation_for(
            triad, tonic, mode, voices=voices, common_tones=common,
            bass_motion=bass_motion, tendency_tones=tendency,
            cadence_type=cp.cadence_type or None, lab_note=lab_note,
            **inv_extra,
        )
        measures.append(LabMeasure(
            index=k, render=render, group=group, key_display=scale.key,
            tonic=tonic, mode=mode, fifths=fifths,
            scale_pitches=tuple(scale.scale_pitches),
            staff1=staff1, staff2=staff2, annotation=ann, underlying=triad,
            target_pitch_classes=((bass_pc,) if cp.dictation == "bass"
                                  else (sop_pc,) if cp.dictation == "soprano"
                                  else triad_pcs),
            bass_pitch_class=bass_pc,
            expected_by_beat=None,
            # A figured chord's bass is always graded; in BASS dictation every
            # measure's answer is its bass.  Soprano dictation grades the top
            # line — a lowest-note demand would be nonsense there.
            strict_bass=bool(inv) or cp.dictation == "bass",
        ))
        prev_triad = triad
        prev_bass_name = bass_name
    return measures


def _spell_octave(v: Tuple[str, int, int]) -> str:
    from theory.diatonic_harmony import alter_to_str
    step, alter, octave = v
    return f"{step}{alter_to_str(alter)}{octave}"


def _gen_motive(spec: LabExperimentSpec) -> List[LabMeasure]:
    mp = motive_params(spec.parameters)
    mode = spec.mode
    keys = list(mp.keys) or default_keys(mode)
    degrees = list(mp.degrees)
    n = len(degrees)
    if n <= 4:
        dtype, slots = "quarter", 4
    else:
        dtype, slots = "eighth", 8
    motive_label = "–".join(_CARET.get(d, f"^{d}") for d in degrees)
    degree_label_tuple = tuple(_CARET.get(d, f"^{d}") for d in degrees)

    # Melodic minor (ticket 14 / plan G2b) is the direction-dependent scale
    # form: each 6th/7th-degree note takes the ASCENDING (raised) form or the
    # natural form per melodic_minor_raised.  The measure's key context stays
    # natural minor (same rule as harmonic minor: raised notes are per-note
    # accidentals, never a new key), so `scale` below is the natural form and
    # only raised notes read from the ascending form.
    directional = (mode == "melodic_minor")
    raised = melodic_minor_raised(degrees) if directional else [False] * n
    mode_keys_word = "melodic minor" if directional else _mode_word(mode)

    measures: List[LabMeasure] = []
    for k, key in enumerate(keys):
        scale = generate_scale(key, "natural_minor" if directional else mode)
        ascending = generate_scale(key, mode) if directional else scale
        tonic = scale.tonic
        notes: List[LabNote] = []
        pcs: List[int] = []
        spelled: List[str] = []
        for d, r in zip(degrees, raised):
            step, alter, octave = _scale_note(ascending if r else scale, d)
            notes.append(LabNote(step, alter, octave, dtype))
            pcs.append((_midi(step, alter, octave)) % 12)
            spelled.append(f"{step}{_alter_str(alter)}{octave}")
        for _ in range(slots - n):
            notes.append(LabNote("C", 0, TREBLE_OCTAVE, dtype, is_rest=True))

        expected = {i + 1: [pc] for i, pc in enumerate(pcs)}
        lab_note = (f"Motive {motive_label} in {scale.key}: {'–'.join(spelled)}.")
        if directional:
            lab_note += (" Melodic minor: 6th and 7th raised on the way up, "
                         "natural on the way down.")
        ann = LabAnnotation(
            key=scale.key, mode=mode, roman=motive_label, chord_tones=(),
            scale_degree_name="motive", degree_number=degrees[0],
            explanation=lab_note, motive_label=motive_label,
            degree_labels=degree_label_tuple, lab_note=lab_note,
            atlas_scale_id=scale_id(tonic, scale.mode),
        )
        measures.append(LabMeasure(
            index=k, render="melody",
            group=f"Motive {motive_label} across {mode_keys_word} keys",
            key_display=scale.key, tonic=tonic, mode=mode, fifths=scale.fifths,
            scale_pitches=tuple(scale.scale_pitches),
            staff1=tuple(notes),
            staff2=(LabNote("C", 0, BASS_OCTAVE, "whole", is_rest=True),),
            annotation=ann, underlying=None,
            target_pitch_classes=tuple(pcs), bass_pitch_class=None,
            expected_by_beat=expected,
        ))
    return measures


def _step_labels(mark: object, n: int) -> Tuple[str, ...]:
    """Per-note labels for one step's ``n`` noteheads.

    A tuple mark maps note for note (validate() pinned the length against the
    dyad); a scalar label marks the step's first notehead only.
    """
    if isinstance(mark, tuple):
        return tuple(mark)
    return (str(mark),) + ("",) * (n - 1)


def _mark_text(mark: object) -> str:
    """One guide-text token per step: ``1`` / ``1+3`` / ``·`` for none."""
    if isinstance(mark, tuple):
        return "+".join(x or "·" for x in mark)
    return mark or "·"


def _gen_technique(spec: LabExperimentSpec) -> List[LabMeasure]:
    """A multi-measure, single-key melodic phrase (piano-technique ticket 01).

    The missing shape between ``motive`` (one measure per key, ≤ 8 notes) and
    the daily technique exercises: every measure stays in ``spec.key``, degrees
    may span four octaves (``_scale_note`` wraps degrees > 7, no clamp), and
    the ``lh`` variant puts the moving line on the bass staff (octaves 2-3)
    with the treble staff whole-rested.  ``expected_by_beat`` carries the pcs
    of ONE step per slot — ``_gen_motive``'s ordered-walk contract, which the
    playback plan already sounds as chords.  The ``coach`` line is
    instruction, never assessment: it travels in the guide text only.

    Simultaneity (ticket 03): a phrase entry that is a tuple of degrees is a
    dyad sounded together (chord-stacked noteheads), and ``octaves=True``
    writes every step as the degree plus its octave.  Such measures carry
    ordered ``step_targets`` — the concurrent pitch classes plus the minimum
    number of distinct keys — and the payload grows the additive ``steps``
    field; purely scalar measures stay ``None`` so old payloads are
    byte-identical.
    """
    tp = technique_params(spec.parameters)
    mode = spec.mode
    tonic = tonic_of(spec.key)
    scale = generate_scale(tonic, mode)
    dtype = tp.note_value
    slots = TECHNIQUE_SLOTS[dtype]
    n_measures = len(tp.phrase)
    left = tp.hand == "lh"
    octave_shift = -2 if left else 0          # LH: same degrees, octaves 2-3
    hand_word = "left hand" if left else "right hand"
    group = f"{spec.title} — {scale.key}, {hand_word}"
    coach = tp.coach.strip()
    # The Atlas has no harmonic-minor scale node: the key context is claimed
    # on the natural-minor node (the Score Soul precedent — raised degrees
    # are per-note accidentals, never a new key).
    atlas_mode = "natural_minor" if mode == "harmonic_minor" else mode

    measures: List[LabMeasure] = []
    for k, entries in enumerate(tp.phrase):
        # validate() pins each mark tuple to the measure's step count.
        fingers = tp.fingering[k] if tp.fingering else ()
        slur_marks = tp.slurs[k] if tp.slurs else ()
        arts = tp.articulations[k] if tp.articulations else ()
        notes: List[LabNote] = []
        pcs: List[int] = []              # flat ordered union over the steps
        spelled: List[str] = []          # one token per step: "C4" / "C4+E4"
        step_targets: List[LabStepTarget] = []
        for j, entry in enumerate(entries):
            degrees = entry if isinstance(entry, tuple) else (entry,)
            if tp.octaves:
                degrees = (degrees[0], degrees[0] + 7)   # the written pair
            n = len(degrees)
            f_labels = _step_labels(fingers[j], n) if fingers else ("",) * n
            s_labels = _step_labels(slur_marks[j], n) if slur_marks else ("",) * n
            a_labels = _step_labels(arts[j], n) if arts else ("",) * n
            step_pcs: List[int] = []
            names: List[str] = []
            for x, d in enumerate(degrees):
                step, alter, octave = _scale_note(scale, d)
                octave += octave_shift
                notes.append(LabNote(
                    step, alter, octave, dtype,
                    is_chord_tone=x > 0,
                    fingering=f_labels[x], slur=s_labels[x],
                    articulation=a_labels[x]))
                pc = _midi(step, alter, octave) % 12
                if pc not in step_pcs:   # octave pair: one pc, two keys
                    step_pcs.append(pc)
                names.append(f"{step}{_alter_str(alter)}{octave}")
            pcs.extend(step_pcs)
            spelled.append("+".join(names))
            step_targets.append(LabStepTarget(pcs=tuple(step_pcs),
                                              min_distinct=n))
        rest_octave = BASS_OCTAVE if left else TREBLE_OCTAVE
        for _ in range(slots - len(entries)):
            notes.append(LabNote("C", 0, rest_octave, dtype, is_rest=True))

        expected = {i + 1: list(s.pcs) for i, s in enumerate(step_targets)}
        # Simultaneity is opt-in per measure: scalar walks keep the old
        # payload shape (no steps), so pre-ticket-03 grading is untouched.
        simultaneous = tp.octaves or any(
            isinstance(e, tuple) and len(e) >= 2 for e in entries)
        lab_note = (f"{scale.key} technique phrase, measure {k + 1}/"
                    f"{n_measures} ({hand_word}): {'–'.join(spelled)}.")
        if tp.fingering:
            lab_note += (" Fingering: "
                         + " ".join(_mark_text(f) for f in tp.fingering[k])
                         + ".")
        if coach:
            lab_note += f" Coach: {coach}"
        first = entries[0]
        ann = LabAnnotation(
            key=scale.key, mode=mode, chord_tones=(),
            scale_degree_name="technique",
            degree_number=first[0] if isinstance(first, tuple) else first,
            explanation=lab_note, lab_note=lab_note,
            atlas_scale_id=scale_id(tonic, atlas_mode),
        )
        line = tuple(notes)
        idle = (LabNote("C", 0, TREBLE_OCTAVE if left else BASS_OCTAVE,
                        "whole", is_rest=True),)
        measures.append(LabMeasure(
            index=k, render="melody", group=group,
            key_display=scale.key, tonic=tonic, mode=mode, fifths=scale.fifths,
            scale_pitches=tuple(scale.scale_pitches),
            staff1=idle if left else line,
            staff2=line if left else idle,
            annotation=ann, underlying=None,
            target_pitch_classes=tuple(pcs), bass_pitch_class=None,
            expected_by_beat=expected,
            step_targets=tuple(step_targets) if simultaneous else None,
        ))
    return measures


def _alter_str(alter: int) -> str:
    from theory.diatonic_harmony import alter_to_str
    return alter_to_str(alter)


def _gen_polyphonic(spec: LabExperimentSpec) -> List[LabMeasure]:
    pp = polyphonic_params(spec.parameters)
    tonic, mode = tonic_of(spec.key), spec.mode
    scale = generate_scale(tonic, mode)
    fifths = scale.fifths
    label = "–".join(pp.progression)
    group = f"{label} (two-voice polyphony) in {scale.key}"

    roman_prog = normalise_pattern(list(pp.progression))   # T/S/D -> Roman
    implied_triads = transpose_degree_pattern(roman_prog, tonic, mode)
    bass_degrees = list(pp.bass_degrees) if pp.bass_degrees else None
    measures: List[LabMeasure] = []
    prev_upper: Optional[int] = None
    for k, implied in enumerate(implied_triads):
        implied_pcs = set(implied.pitch_classes)

        # Upper voice = the requested scale degree, folded to a smooth treble band
        # (nearest the previous upper note; the first targets ~E4) so two-voice
        # lines stay compact rather than drifting an octave up per scale degree.
        u_step, u_alter, _ = _scale_note(scale, pp.upper_degrees[k])
        u_oct = _nearest_octave(u_step, u_alter, prev_upper if prev_upper is not None else 64)
        upper = LabNote(u_step, u_alter, u_oct, "whole")
        upper_pc = upper.pitch_class
        prev_upper = upper.midi

        # Bass voice = a requested degree, else the implied chord root.  An
        # explicit degree keeps its scale octave (shifted one octave down into
        # the bass register) so a rising line like 7̂→8̂ actually rises (B3→C4)
        # instead of collapsing to a fixed octave.
        if bass_degrees is not None:
            b_step, b_alter, b_oct = _scale_note(scale, bass_degrees[k])
            lower = LabNote(b_step, b_alter, b_oct - 1, "whole")
        else:
            lower = _bass_note(implied.root)
        lower_pc = lower.pitch_class

        # Build-time cross-check: both voices must belong to the declared chord,
        # else the declared Roman is wrong (never silently mislabel).
        for pc, who in ((upper_pc, "upper"), (lower_pc, "bass")):
            if pc not in implied_pcs:
                raise ValueError(
                    f"polyphonic slice {k} ({implied.roman}): {who} pitch class "
                    f"{pc} is not in the implied chord {implied.chord_symbol} "
                    f"{implied.pitches}; fix the declared progression/degrees")

        # Target = the actually-sounding voice pitch classes (what is on staff).
        target = (lower_pc,) if lower_pc == upper_pc else (lower_pc, upper_pc)

        u_name = f"{u_step}{_alter_str(u_alter)}"
        l_name = lower.step + _alter_str(lower.alter)
        lab_note = (
            f"Slice {k + 1}: bass {l_name} + upper {u_name} imply "
            f"{implied.chord_symbol} ({implied.roman}, {implied.function_label}).")
        ann = _annotation_for(
            implied, tonic, mode,
            voices=(("upper", _spell_octave((u_step, u_alter, u_oct))),
                    ("bass", _spell_octave((lower.step, lower.alter, lower.octave)))),
            implied_roman=implied.roman, implied_chord=implied.chord_symbol,
            lab_note=lab_note,
        )
        measures.append(LabMeasure(
            index=k, render="polyphonic", group=group, key_display=scale.key,
            tonic=tonic, mode=mode, fifths=fifths,
            scale_pitches=tuple(scale.scale_pitches),
            staff1=(upper,), staff2=(lower,), annotation=ann, underlying=implied,
            target_pitch_classes=target, bass_pitch_class=lower_pc,
            expected_by_beat=None,
        ))
    return measures


_GENERATORS = {
    "inversion": _gen_inversion,
    "cadence": _gen_voice_leading,
    "voice_leading": _gen_voice_leading,
    "motive": _gen_motive,
    "polyphonic_harmony": _gen_polyphonic,
    "technique": _gen_technique,
}


# ---------------------------------------------------------------------------
# Public compile
# ---------------------------------------------------------------------------

def compile_lab(spec: LabExperimentSpec) -> LabExperiment:
    """Expand a lab spec into a deterministic :class:`LabExperiment`."""
    spec.validate()
    if spec.concept == "reduction":
        raise NotImplementedError(
            "The Schenkerian reduction lab is reserved (a non-goal of this slice). "
            "LabExperimentSpec(concept='reduction') validates and -- given an "
            "explicit 'skeleton' -- down-compiles to a drill via to_exercise_specs, "
            "but compile_lab is not implemented yet.")

    gen = _GENERATORS.get(spec.concept)
    if gen is None:  # pragma: no cover - validate() guards this
        raise ValueError(f"Unhandled concept: {spec.concept}")

    measures = gen(spec)
    if len(measures) > MAX_CHORDS_PER_SPEC:
        raise ValueError(
            f"experiment {spec.experiment_id} produced {len(measures)} measures "
            f"(> {MAX_CHORDS_PER_SPEC}); keep each example on one page")

    return LabExperiment(
        spec=spec, title=spec.title, measures=measures,
        exercise_specs=spec.to_exercise_specs(),
    )


# ---------------------------------------------------------------------------
# Demo experiments (used by run_harmony_lab_demo.py + tests)
# ---------------------------------------------------------------------------

def lab_demo_specs() -> List[LabExperimentSpec]:
    """The first-slice demo set: one experiment per implemented concept family."""
    return [
        LabExperimentSpec(
            experiment_id="inv_C_I",
            title="Inversions of the C major I chord",
            concept="inversion", mode="major", key="C major", render="block",
            parameters={"degree": "I", "inversions": [0, 1, 2]},
            description="C, C/E, C/G — invariant tones C–E–G, a changing bass.",
        ),
        LabExperimentSpec(
            experiment_id="inv_C_V_arp",
            title="Inversions of the C major V chord (arpeggiated)",
            concept="inversion", mode="major", key="C major", render="arpeggio",
            parameters={"degree": "V", "inversions": [0, 1, 2]},
        ),
        LabExperimentSpec(
            experiment_id="cad_V_I_C",
            title="V–I authentic cadence in C major (voice leading)",
            concept="cadence", mode="major", key="C major", render="voice_leading",
            parameters={"pattern": ["V", "I"], "cadence_type": "authentic"},
            description="Leading tone B→C; bass G→C.",
        ),
        LabExperimentSpec(
            experiment_id="cad_IV_I_C",
            title="IV–I plagal cadence in C major (voice leading)",
            concept="cadence", mode="major", key="C major", render="voice_leading",
            parameters={"pattern": ["IV", "I"], "cadence_type": "plagal"},
        ),
        LabExperimentSpec(
            experiment_id="cad_V_vi_C",
            title="V–vi deceptive cadence in C major (voice leading)",
            concept="cadence", mode="major", key="C major", render="voice_leading",
            parameters={"pattern": ["V", "vi"], "cadence_type": "deceptive"},
        ),
        # Progressions carry concept "voice_leading", two-chord types "cadence" --
        # the same family rule as the curriculum catalogue (ticket 02 / plan F7);
        # every catalogue cadence names its type from harmonic_roles.CADENCE_TYPES.
        LabExperimentSpec(
            experiment_id="cad_ii_V_I_C",
            title="ii–V–I in C major (voice leading)",
            concept="voice_leading", mode="major", key="C major",
            render="voice_leading",
            parameters={"pattern": ["ii", "V", "I"], "cadence_type": "authentic"},
        ),
        LabExperimentSpec(
            experiment_id="cad_v_i_Am",
            title="v–i in A natural minor (voice leading)",
            concept="cadence", mode="natural_minor", key="A minor",
            render="voice_leading",
            parameters={"pattern": ["v", "i"], "cadence_type": "authentic"},
        ),
        LabExperimentSpec(
            experiment_id="cad_iv_v_i_Am",
            title="iv–v–i in A natural minor (voice leading)",
            concept="voice_leading", mode="natural_minor", key="A minor",
            render="voice_leading",
            parameters={"pattern": ["iv", "v", "i"], "cadence_type": "authentic"},
        ),
        LabExperimentSpec(
            experiment_id="cad_VII_i_Am",
            title="VII–i subtonic cadence in A natural minor",
            concept="cadence", mode="natural_minor", key="A minor",
            render="voice_leading",
            parameters={"pattern": ["VII", "i"], "cadence_type": "subtonic"},
        ),
        LabExperimentSpec(
            experiment_id="cad_i_VI_VII_i_Am",
            title="i–VI–VII–i Aeolian loop in A natural minor",
            concept="voice_leading", mode="natural_minor", key="A minor",
            render="voice_leading",
            parameters={"pattern": ["i", "VI", "VII", "i"], "cadence_type": "aeolian"},
        ),
        LabExperimentSpec(
            experiment_id="motive_1353_major",
            title="Motive 1–3–5–3 across the major keys",
            concept="motive", mode="major", key="C major", render="melody",
            parameters={"degrees": [1, 3, 5, 3]},
            description="The tonic-arpeggio motive transposed through all 12 major keys.",
        ),
        LabExperimentSpec(
            experiment_id="motive_54321_minor",
            title="Motive 5–4–3–2–1 across the natural-minor keys",
            concept="motive", mode="natural_minor", key="A minor", render="melody",
            parameters={"degrees": [5, 4, 3, 2, 1]},
        ),
        LabExperimentSpec(
            experiment_id="poly_I_V_I_C",
            title="Two-voice I–V–I in C major",
            concept="polyphonic_harmony", mode="major", key="C major",
            render="polyphonic",
            parameters={"progression": ["I", "V", "I"], "upper_degrees": [3, 2, 3]},
            description="Bass roots C–G–C under an upper voice E–D–E imply I–V–I.",
        ),
        LabExperimentSpec(
            experiment_id="poly_ii_V_I_C",
            title="Two-voice ii–V–I in C major",
            concept="polyphonic_harmony", mode="major", key="C major",
            render="polyphonic",
            parameters={"progression": ["ii", "V", "I"], "upper_degrees": [4, 7, 3]},
        ),
        LabExperimentSpec(
            experiment_id="poly_i_VII_i_Am",
            title="Two-voice i–VII–i in A natural minor",
            concept="polyphonic_harmony", mode="natural_minor", key="A minor",
            render="polyphonic",
            parameters={"progression": ["i", "VII", "i"], "upper_degrees": [3, 4, 5]},
        ),
    ]
