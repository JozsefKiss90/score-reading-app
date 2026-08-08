"""Turn a compiled harmony exercise into playable MusicXML + a trainer payload.

The MusicXML style mirrors ``run_sight_notes_demo.py`` (2-staff piano part,
``divisions = 16``, 4/4) so it renders identically through Verovio /
``ScoreViewBeats``.  Each chord occupies its own measure:

* **block**     -- the chord as a whole-note chord on the treble staff.
* **arpeggio**  -- the chord tones as quarter notes from beat 1 (a triad
  leaves beat 4 as a rest; a tetrad such as V7 fills all four beats).

A single root note is written on the bass staff.  Text annotations are placed
above each measure, e.g. ``"C major | ii | Dm | m3+M3 | predominant"``.

The companion :func:`build_trainer_payload` produces the per-measure metadata
consumed at runtime by ``beat_selector/harmony_trainer.js`` (the injected MIDI
controller + guide panel).

This module is pure: it only builds strings / dicts, no Qt or Verovio.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from harmony.exercise_spec import (
    CompiledChord,
    CompiledExercise,
    degree_labels_for_mode,
)
from theory.diatonic_harmony import (
    DiatonicTriad,
    applied_target_options,
    key_signature_fifths,
    note_pc,
    parse_applied_token,
    parse_pitch_class,
    LETTER_INDEX,
    LETTER_BASE_PC,
    SEVENTH_QUALITY_LABELS,
)


# ----------------------------------------------------------------------------
# MusicXML timing constants (kept identical to run_sight_notes_demo.py)
# ----------------------------------------------------------------------------
DIVISIONS = 16
BEATS_PER_MEASURE = 4
MEASURE_TICKS = BEATS_PER_MEASURE * DIVISIONS  # 64
QUARTER_TICKS = DIVISIONS
WHOLE_TICKS = DIVISIONS * 4

TREBLE_BASE_OCTAVE = 4
BASS_OCTAVE = 3
TEMPO_BPM = 80

_SHARP_ORDER = ["F", "C", "G", "D", "A", "E", "B"]
_FLAT_ORDER = ["B", "E", "A", "D", "G", "C", "F"]


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------

def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _ks_alter_for_step(step: str, fifths: int) -> Optional[int]:
    """+1/-1 if ``step`` is altered by the key signature, else ``None``."""
    step = step.upper()
    if fifths > 0:
        return 1 if step in set(_SHARP_ORDER[: min(7, fifths)]) else None
    if fifths < 0:
        return -1 if step in set(_FLAT_ORDER[: min(7, -fifths)]) else None
    return None


def _triad_fifths(triad: DiatonicTriad) -> int:
    return key_signature_fifths(triad.key, triad.mode)


def _voiced_tone(name: str, root_letter_index: int, step_offset: int,
                 base_octave: int) -> Tuple[str, int, int]:
    """Return ``(step, alter, octave)`` for a chord tone.

    Octave is assigned by stacking letters above the root so that enharmonic
    spellings (E#, Cb, ...) keep their notated octave.
    """
    letter, alter = parse_pitch_class(name)
    octave = base_octave + (root_letter_index + step_offset) // 7
    return letter, alter, octave


def triad_treble_voicing(triad: DiatonicTriad,
                         base_octave: int = TREBLE_BASE_OCTAVE
                         ) -> List[Tuple[str, int, int]]:
    """Root-position ``[(step, alter, octave), ...]``: root, third, fifth(, seventh)."""
    r_letter, _ = parse_pitch_class(triad.root)
    ri = LETTER_INDEX[r_letter]
    return [_voiced_tone(name, ri, 2 * k, base_octave)
            for k, name in enumerate(triad.pitches)]


def triad_bass_note(triad: DiatonicTriad,
                    octave: int = BASS_OCTAVE) -> Tuple[str, int, int]:
    letter, alter = parse_pitch_class(triad.root)
    return letter, alter, octave


def _midi_of(step: str, alter: int, octave: int) -> int:
    return (octave + 1) * 12 + LETTER_BASE_PC[step] + alter


# ----------------------------------------------------------------------------
# Note / measure XML
# ----------------------------------------------------------------------------

def _note_xml(step: str, alter: int, octave: int, ticks: int, note_type: str,
              staff: int, voice: int, fifths: int,
              is_chord_tone: bool = False,
              fingering: str = "", slur: str = "",
              articulation: str = "") -> str:
    ks_alter = _ks_alter_for_step(step, fifths)
    eff_alter = alter

    alter_xml = f"<alter>{eff_alter}</alter>" if eff_alter != 0 else ""

    accidental_xml = ""
    if eff_alter != (ks_alter or 0):
        # Includes correct glyphs for double accidentals (future harmonic minor
        # can produce e.g. F double-sharp); diatonic content stays within +/-1.
        name = {2: "double-sharp", 1: "sharp", 0: "natural",
                -1: "flat", -2: "flat-flat"}.get(eff_alter)
        if name is not None:
            accidental_xml = f"<accidental>{name}</accidental>"

    chord_xml = "<chord/>" if is_chord_tone else ""

    # Per-note marks (piano-technique ticket 02): one <notations> wrapper,
    # only when a mark is set -- every existing caller's output is unchanged.
    # Values are spec-validated vocab: slur "start"/"stop", articulation
    # "staccato"/"accent", fingering "1".."5".
    notations_xml = ""
    if slur or articulation or fingering:
        slur_xml = f'<slur type="{slur}" number="1"/>' if slur else ""
        art_xml = (f"<articulations><{articulation}/></articulations>"
                   if articulation else "")
        fing_xml = (f"<technical><fingering>{fingering}</fingering>"
                    f"</technical>" if fingering else "")
        notations_xml = f"<notations>{slur_xml}{art_xml}{fing_xml}</notations>"

    # MusicXML note child order: chord?, pitch, duration, voice, type,
    # accidental, staff, notations (DTD-conformant).
    return (
        f"<note>{chord_xml}"
        f"<pitch><step>{step}</step>{alter_xml}<octave>{octave}</octave></pitch>"
        f"<duration>{ticks}</duration>"
        f"<voice>{voice}</voice>"
        f"<type>{note_type}</type>"
        f"{accidental_xml}"
        f"<staff>{staff}</staff>{notations_xml}</note>"
    )


def _rest_xml(ticks: int, note_type: str, staff: int, voice: int) -> str:
    return (
        f"<note><rest/><duration>{ticks}</duration>"
        f"<voice>{voice}</voice><type>{note_type}</type>"
        f"<staff>{staff}</staff></note>"
    )


# chord-symbol kind: quality -> (display-text suffix, MusicXML kind value)
_HARMONY_KIND = {
    "major": ("", "major"),
    "minor": ("m", "minor"),
    "diminished": ("°", "diminished"),
    "augmented": ("+", "augmented"),
    "dominant_seventh": ("7", "dominant"),
    "major_seventh": ("maj7", "major-seventh"),
    "minor_seventh": ("m7", "minor-seventh"),
    "half_diminished_seventh": ("ø7", "half-diminished"),
    "diminished_seventh": ("°7", "diminished-seventh"),
}
_ROMAN_VALUE = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7}


def _chord_symbol_harmony(triad: DiatonicTriad) -> str:
    """A <harmony> chord symbol (e.g. "Dm", "B°") shown above the treble staff."""
    step, alter = parse_pitch_class(triad.root)
    root_alter = f"<root-alter>{alter}</root-alter>" if alter else ""
    text, kind = _HARMONY_KIND.get(triad.chord_quality, ("", "major"))
    return (
        '<harmony placement="above">'
        f"<root><root-step>{step}</root-step>{root_alter}</root>"
        f'<kind text="{_xml_escape(text)}">{kind}</kind>'
        "</harmony>"
    )


def _roman_numeral_harmony(triad: DiatonicTriad) -> str:
    """A <numeral> Roman-numeral label (e.g. "ii", "vii°") below the staff."""
    base = re.sub(r"[^IVX]", "", triad.roman.upper())
    value = _ROMAN_VALUE.get(base, 1)
    return (
        '<harmony placement="below">'
        f'<numeral><numeral-root text="{_xml_escape(triad.roman)}">{value}'
        "</numeral-root></numeral>"
        '<kind text="">none</kind>'
        "</harmony>"
    )


def _annotation_xml(triad: DiatonicTriad) -> str:
    """On-staff labels via Verovio-native, auto-positioned elements.

    Chord symbol above the treble staff, Roman numeral below it. These never
    overlap (unlike free <words> text, which Verovio neither resizes nor
    measure-fits). The interval layer, harmonic function, key, scale, and
    explanation are shown in the sidebar guide panel for the current chord.
    """
    return _chord_symbol_harmony(triad) + _roman_numeral_harmony(triad)


def _treble_block(triad: DiatonicTriad, fifths: int) -> str:
    voicing = triad_treble_voicing(triad)
    parts = []
    for j, (step, alter, octave) in enumerate(voicing):
        parts.append(_note_xml(step, alter, octave, WHOLE_TICKS, "whole",
                               staff=1, voice=1, fifths=fifths,
                               is_chord_tone=(j > 0)))
    return "".join(parts)


def _treble_arpeggio(triad: DiatonicTriad, fifths: int) -> str:
    voicing = triad_treble_voicing(triad)
    parts = []
    for (step, alter, octave) in voicing:
        parts.append(_note_xml(step, alter, octave, QUARTER_TICKS, "quarter",
                               staff=1, voice=1, fifths=fifths))
    # Pad the 4/4 measure with rests (a triad leaves beat 4 free; a tetrad
    # fills all four beats).
    for _ in range(BEATS_PER_MEASURE - len(voicing)):
        parts.append(_rest_xml(QUARTER_TICKS, "quarter", staff=1, voice=1))
    return "".join(parts)


def _measure_xml(chord: CompiledChord, m_no: int, fifths: int,
                 prev_fifths: Optional[int], is_last: bool,
                 hide_roman: bool = False) -> str:
    triad = chord.triad

    if m_no == 1:
        attr_block = (
            "<attributes>"
            f"<divisions>{DIVISIONS}</divisions>"
            f"<key><fifths>{fifths}</fifths></key>"
            "<time><beats>4</beats><beat-type>4</beat-type></time>"
            "<staves>2</staves>"
            '<clef number="1"><sign>G</sign><line>2</line></clef>'
            '<clef number="2"><sign>F</sign><line>4</line></clef>'
            "</attributes>"
            '<direction placement="above"><direction-type>'
            "<metronome><beat-unit>quarter</beat-unit>"
            f"<per-minute>{TEMPO_BPM}</per-minute></metronome>"
            f'</direction-type><sound tempo="{TEMPO_BPM}"/></direction>'
        )
    elif prev_fifths is not None and fifths != prev_fifths:
        attr_block = f"<attributes><key><fifths>{fifths}</fifths></key></attributes>"
    else:
        attr_block = ""

    # The spot stage hides the intruder's Roman label on the score — the
    # roman ("V7/V") IS the answer; its chord symbol (D7) stays visible.
    annotation = (_chord_symbol_harmony(triad) if hide_roman
                  else _annotation_xml(triad))

    if chord.render == "arpeggio":
        treble = _treble_arpeggio(triad, fifths)
    else:
        treble = _treble_block(triad, fifths)

    b_step, b_alter, b_oct = triad_bass_note(triad)
    bass = _note_xml(b_step, b_alter, b_oct, WHOLE_TICKS, "whole",
                     staff=2, voice=2, fifths=fifths)

    barline = ('<barline location="right"><bar-style>light-heavy</bar-style>'
               "</barline>") if is_last else ""

    return (
        f'<measure number="{m_no}">'
        f"{attr_block}{annotation}{treble}"
        f"<backup><duration>{MEASURE_TICKS}</duration></backup>"
        f"{bass}{barline}</measure>"
    )


# ----------------------------------------------------------------------------
# Public: MusicXML
# ----------------------------------------------------------------------------

def build_musicxml(compiled: CompiledExercise, title: Optional[str] = None) -> str:
    """Build a full MusicXML document string for the compiled exercise."""
    if not compiled.chords:
        raise ValueError("Cannot build MusicXML for an empty exercise")

    title = title or compiled.title
    spot = compiled.spec.answer_mode == "spot"
    measures: List[str] = []
    prev_fifths: Optional[int] = None
    n = len(compiled.chords)
    for i, chord in enumerate(compiled.chords):
        fifths = _triad_fifths(chord.triad)
        measures.append(_measure_xml(
            chord, m_no=i + 1, fifths=fifths, prev_fifths=prev_fifths,
            is_last=(i == n - 1),
            hide_roman=(spot and
                        parse_applied_token(chord.triad.roman) is not None),
        ))
        prev_fifths = fifths

    body = "".join(measures)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE score-partwise PUBLIC '
        '"-//Recordare//DTD MusicXML 3.1 Partwise//EN" '
        '"http://www.musicxml.org/dtds/partwise.dtd">'
        '<score-partwise version="3.1">'
        f"<work><work-title>{_xml_escape(title)}</work-title></work>"
        "<part-list><score-part id=\"P1\">"
        "<part-name>Harmony Trainer</part-name></score-part></part-list>"
        f'<part id="P1">{body}</part>'
        "</score-partwise>"
    )


# ----------------------------------------------------------------------------
# Public: trainer payload (consumed by harmony_trainer.js)
# ----------------------------------------------------------------------------

def _target_for(chord: CompiledChord) -> Dict:
    triad = chord.triad
    voicing = triad_treble_voicing(triad)
    midi_pitches = [_midi_of(step, alter, octave) for (step, alter, octave) in voicing]
    pitch_classes = [m % 12 for m in midi_pitches]  # ordered root/third/fifth
    target = {
        "absMeasure": chord.index,
        "measureNumber": chord.index + 1,
        "group": chord.group,
        "render": chord.render,
        "key": triad.key,
        "mode": triad.mode,
        "scale": list(triad.scale_pitches),
        "degree": triad.roman,
        "degreeNumber": triad.degree_number,
        "roman": triad.roman,
        "chordSymbol": triad.chord_symbol,
        "root": triad.root,
        "quality": triad.chord_quality,
        "chordTones": list(triad.pitches),
        "pitchClasses": pitch_classes,
        "midiPitches": midi_pitches,
        "bassMidi": _midi_of(*triad_bass_note(triad)),
        "intervalLayer": triad.interval_layer,
        "functionLabel": triad.function_label,
        "scaleDegreeName": triad.scale_degree_name,
        "explanation": triad.explanation_text,
    }
    if parse_applied_token(triad.roman) is not None:
        # The intruder metadata (ticket 17 / plan G5a): which tones are
        # chromatic to the home key (the pulsing noteheads of the spot
        # stage), and the tritone the resolve stage watches.
        scale_pcs = {note_pc(p) for p in triad.scale_pitches}
        target["intruder"] = True
        target["chromaticPcs"] = [note_pc(p) for p in triad.pitches
                                  if note_pc(p) not in scale_pcs]
        tritone = _applied_tritone(triad)
        if tritone is not None:
            target["tritonePcs"] = [note_pc(p) for p in tritone]
    return target


#: The two tones of an applied chord that form the tritone resolving into the
#: target, by chord quality (ticket 17 for V7/x; ticket 19 for vii°7/x, which
#: has the same pull from a different pair): index into ``DiatonicTriad.pitches``.
#: A ``V/x`` triad has no tritone at all, so it is absent -- the resolve stage
#: simply shows no tritone highlight rather than inventing one.
_APPLIED_TRITONE_TONES = {
    "dominant_seventh": (1, 3),     # third + seventh (F#+C in D7)
    "diminished_seventh": (0, 2),   # root + diminished fifth (F#+C in F#°7)
}


def _applied_tritone(triad: DiatonicTriad):
    """``(lower, upper)`` chord tones of the applied chord's resolving tritone.

    ``None`` when the chord has none.  Both members resolve by step into the
    tonicised triad -- the leading tone up to its root, the other down to its
    third -- which is what the resolve stage flags green.
    """
    idx = _APPLIED_TRITONE_TONES.get(triad.chord_quality)
    if idx is None:
        return None
    return triad.pitches[idx[0]], triad.pitches[idx[1]]


def _mcq_for(target: Dict, focus: str = "roman") -> Dict:
    """The multiple-choice block of one ``answer_mode="mcq"`` target (plan U2).

    ``focus="roman"`` asks for the Roman numeral; the option vocabulary is the
    mode's seven degree labels, which match ``DiatonicTriad.roman`` spelling
    exactly (the ``°`` decoration included), so ``answer`` is always one of
    ``options``.

    ``focus="quality"`` (ticket 10) asks for the chord quality.  A tetrad
    target offers the five seventh-quality labels (Mm7 / mm7 / MM7 / ø7 / °7
    — °7 is a distractor until harmonic minor ships a buildable one); a triad
    target offers the four triad qualities (augmented likewise never sounds
    diatonically).
    """
    if focus == "quality":
        if len(target["pitchClasses"]) > 3:
            # option order = SEVENTH_QUALITY_LABELS' declaration order
            # (Mm7, mm7, MM7, ø7, °7) — one table, never restated
            return {
                "prompt": "Which seventh-chord quality do you hear?",
                "options": list(SEVENTH_QUALITY_LABELS.values()),
                "answer": SEVENTH_QUALITY_LABELS[target["quality"]],
            }
        return {
            "prompt": "Which triad quality do you hear?",
            "options": ["major", "minor", "diminished", "augmented"],
            "answer": target["quality"],
        }
    return {
        "prompt": f"Which chord of {target['key']} is this?",
        "options": degree_labels_for_mode(target["mode"]),
        "answer": target["roman"],
    }


def _applied_target_mcq(intruder: Dict) -> Dict:
    """The ear stage's follow-up: *which degree got tonicised?* (ticket 19).

    The options are every degree the mode can tonicise (derived from the
    engine's applied vocabulary, so the strip never offers a degree no applied
    chord could point at), and the answer is the intruder's own target.
    """
    target = parse_applied_token(intruder["roman"])[1]
    return {
        "prompt": "Which degree did that chord tonicise?",
        "options": applied_target_options(intruder["mode"]),
        "answer": target,
    }


def build_trainer_payload(compiled: CompiledExercise) -> Dict:
    """Per-measure metadata for the runtime trainer (JSON-serialisable).

    The shape intentionally exposes the field names called out in the spec:
    ``TRAINER_MODE``, ``TARGET_CHORDS``, ``TARGET_BY_MEASURE`` and
    ``EXPECTED_MIDI_BY_MEASURE_OR_BEAT``.
    """
    targets = [_target_for(c) for c in compiled.chords]

    answer_mode = compiled.spec.answer_mode
    if answer_mode == "mcq":
        for t in targets:
            t["mcq"] = _mcq_for(t, compiled.spec.mcq_focus)

    # Tritone-resolution metadata (ticket 17 for V7/x, ticket 19 for vii°7/x):
    # when an applied chord is immediately followed by its target (same key
    # group), the resolution target learns which noteheads to flag green as
    # the tritone resolves.  Both tones move by step into the target: the
    # leading tone up to its root, the other down to its third.
    for prev, nxt in zip(targets, targets[1:]):
        applied = parse_applied_token(prev["roman"])
        if (applied is None or "tritonePcs" not in prev
                or nxt["roman"] != applied[1]
                or nxt["group"] != prev["group"]):
            continue
        name_by_pc = dict(zip(prev["pitchClasses"], prev["chordTones"]))
        lower, upper = (name_by_pc[pc] for pc in prev["tritonePcs"])
        root, res_third = nxt["chordTones"][0], nxt["chordTones"][1]
        nxt["tritoneResolution"] = {
            "fromPcs": list(prev["tritonePcs"]),
            "fromMeasure": prev["absMeasure"],
            "toPcs": [nxt["pitchClasses"][0], nxt["pitchClasses"][1]],
            "text": f"{lower}→{root}, {upper}→{res_third}",
        }

    spot_index = None
    followup = None
    if answer_mode == "spot":
        spot_index = next(i for i, t in enumerate(targets)
                          if t.get("intruder"))
        targets[spot_index]["romanHidden"] = True
        if compiled.spec.presentation == "echo":
            # The ear stage (ticket 19 / plan G5c) asks the second half of the
            # plan's question: having heard *where* the chromatic chord is,
            # which degree did it tonicise?  Only the veiled variant carries
            # it — with the notation in front of you the answer is readable
            # off the score, so the visual spot drill stays one question.
            followup = _applied_target_mcq(targets[spot_index])

    target_by_measure: Dict[str, Dict] = {str(t["absMeasure"]): t for t in targets}

    expected: Dict[str, object] = {}
    for t in targets:
        abs_key = str(t["absMeasure"])
        if t["render"] == "arpeggio":
            # beat (1-based) -> [single expected pitch class]
            expected[abs_key] = {
                str(beat + 1): [t["pitchClasses"][beat]]
                for beat in range(len(t["pitchClasses"]))
            }
        else:
            expected[abs_key] = list(t["pitchClasses"])

    payload = {
        "TRAINER_MODE": True,
        "schema": "harmony-trainer/payload-v1",
        "exerciseId": compiled.spec.exercise_id,
        "title": compiled.title,
        "render": compiled.spec.render,
        "match": "pitch_class",
        "ANSWER_MODE": answer_mode,
        "PRESENTATION": compiled.spec.presentation,
        "TARGET_CHORDS": targets,
        "TARGET_BY_MEASURE": target_by_measure,
        "EXPECTED_MIDI_BY_MEASURE_OR_BEAT": expected,
    }
    if spot_index is not None:
        payload["SPOT_INDEX"] = spot_index
    if followup is not None:
        payload["SPOT_FOLLOWUP"] = followup
    return payload


def build_exercise(compiled: CompiledExercise) -> Tuple[str, Dict]:
    """Convenience: return ``(musicxml_string, trainer_payload)``."""
    return build_musicxml(compiled), build_trainer_payload(compiled)
