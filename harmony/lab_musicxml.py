"""Render a compiled :class:`~harmony.lab.LabExperiment` to MusicXML + a payload.

This is the lab's rendering layer.  It assembles the per-staff note streams of
each :class:`~harmony.lab.LabMeasure` into a MusicXML document and into a runtime
payload that is **compatible with the existing** ``beat_selector/harmony_trainer.js``
controller, so every lab example plays + MIDI-validates through the unchanged
:class:`ScoreViewBeats` + trainer machinery.

It reuses the low-level helpers of :mod:`harmony.musicxml_builder` verbatim
(``_note_xml`` / ``_rest_xml`` / ``_chord_symbol_harmony`` / ``_roman_numeral_harmony``
and the timing constants) so the lab's notation matches the trainer's byte-for-byte
where the layouts coincide; only the multi-voice / changed-bass / melodic layouts
the trainer cannot express are assembled here.  The document wrapper is a small
constant template copied from :func:`harmony.musicxml_builder.build_musicxml` so
that module stays unmodified (the project's shared-file discipline).

The renderer is **pure** (strings + dicts; no Qt / Verovio / MIDI).

Payload compatibility (grounded in ``harmony_trainer.js``):

* Each ``TARGET_CHORDS`` entry carries the same key set
  ``harmony.musicxml_builder._target_for`` produces (so ``renderCurrent`` /
  ``renderList`` / ``afterNoteOn`` never read a missing field), plus additive lab
  fields the controller ignores.
* The controller judges correctness purely by **pitch-class set** -- ``coversAll``
  for ``render == "block"``, ordered ``arpIndex`` for ``render == "arpeggio"``.
  It is octave- and voice-agnostic, so a 4-note SATB or 2-voice polyphonic
  measure validates correctly as long as ``pitchClasses`` lists the target pcs
  and every sounding note is in the rendered MusicXML (it is -- that builds the
  runtime ``PITCH_MAP``).
* Per measure the payload ``render`` is ``"arpeggio"`` when the measure has an
  ``expected_by_beat`` map (melodic lines, arpeggios, and the optional
  strict-bass inversion mode -- which reuses the existing ordered-tone arpeggio
  branch with the bass pitch class first, needing **no** JS change), else
  ``"block"``.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from harmony.lab import LabExperiment, LabMeasure, LabNote
from harmony.musicxml_builder import (
    _note_xml,
    _rest_xml,
    _chord_symbol_harmony,
    _roman_numeral_harmony,
    _xml_escape,
    DIVISIONS,
    MEASURE_TICKS,
    TEMPO_BPM,
)


#: note_type -> duration in divisions (DIVISIONS=16 -> quarter=16).
_TICKS = {"whole": MEASURE_TICKS, "half": MEASURE_TICKS // 2,
          "quarter": DIVISIONS, "eighth": DIVISIONS // 2}


# ----------------------------------------------------------------------------
# Note / measure XML
# ----------------------------------------------------------------------------

def _note_to_xml(note: LabNote, staff: int, voice: int, fifths: int) -> str:
    ticks = _TICKS[note.note_type]
    if note.is_rest:
        return _rest_xml(ticks, note.note_type, staff=staff, voice=voice)
    return _note_xml(note.step, note.alter, note.octave, ticks, note.note_type,
                     staff=staff, voice=voice, fifths=fifths,
                     is_chord_tone=note.is_chord_tone)


def _staff_xml(notes, staff: int, voice: int, fifths: int) -> str:
    return "".join(_note_to_xml(n, staff, voice, fifths) for n in notes)


def _annotation_xml(measure: LabMeasure) -> str:
    """Chord symbol + Roman numeral above/below the staff for chord measures.

    Reuses the trainer's Verovio-native, auto-positioned ``<harmony>`` elements
    (never free ``<words>``).  Melodic (motive) measures have no chord, so they
    carry no harmony annotation -- the motive label lives in the guide panel.
    """
    triad = measure.underlying
    if triad is None:
        return ""
    return _chord_symbol_harmony(triad) + _roman_numeral_harmony(triad)


def _attributes_xml(measure: LabMeasure, m_no: int,
                    prev_fifths: Optional[int]) -> str:
    fifths = measure.fifths
    if m_no == 1:
        return (
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
    if prev_fifths is not None and fifths != prev_fifths:
        return f"<attributes><key><fifths>{fifths}</fifths></key></attributes>"
    return ""


def _measure_xml(measure: LabMeasure, m_no: int, prev_fifths: Optional[int],
                 is_last: bool) -> str:
    fifths = measure.fifths
    attr = _attributes_xml(measure, m_no, prev_fifths)
    annotation = _annotation_xml(measure)
    staff1 = _staff_xml(measure.staff1, staff=1, voice=1, fifths=fifths)
    staff2 = _staff_xml(measure.staff2, staff=2, voice=2, fifths=fifths)
    backup = f"<backup><duration>{MEASURE_TICKS}</duration></backup>"
    barline = ('<barline location="right"><bar-style>light-heavy</bar-style>'
               "</barline>") if is_last else ""
    return (
        f'<measure number="{m_no}">'
        f"{attr}{annotation}{staff1}{backup}{staff2}{barline}</measure>"
    )


def _wrap(title: str, body: str) -> str:
    """The MusicXML document wrapper (copied from build_musicxml's template)."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE score-partwise PUBLIC '
        '"-//Recordare//DTD MusicXML 3.1 Partwise//EN" '
        '"http://www.musicxml.org/dtds/partwise.dtd">'
        '<score-partwise version="3.1">'
        f"<work><work-title>{_xml_escape(title)}</work-title></work>"
        "<part-list><score-part id=\"P1\">"
        "<part-name>Music Theory Lab</part-name></score-part></part-list>"
        f'<part id="P1">{body}</part>'
        "</score-partwise>"
    )


def build_lab_musicxml(experiment: LabExperiment,
                       title: Optional[str] = None) -> str:
    """Build a full MusicXML document string for a compiled lab experiment."""
    if not experiment.measures:
        raise ValueError("Cannot build MusicXML for an empty experiment")
    title = title or experiment.title
    measures: List[str] = []
    prev_fifths: Optional[int] = None
    n = len(experiment.measures)
    for i, measure in enumerate(experiment.measures):
        measures.append(_measure_xml(
            measure, m_no=i + 1, prev_fifths=prev_fifths, is_last=(i == n - 1)))
        prev_fifths = measure.fifths
    return _wrap(title, "".join(measures))


# ----------------------------------------------------------------------------
# Trainer payload
# ----------------------------------------------------------------------------

def _payload_render(measure: LabMeasure) -> str:
    """Map a measure to the controller's render mode (block vs ordered tones)."""
    return "arpeggio" if measure.expected_by_beat is not None else "block"


def _lab_target_for(measure: LabMeasure) -> Dict:
    """A trainer target dict: the full ``_target_for`` key set + lab extras."""
    a = measure.annotation
    pcs = list(measure.target_pitch_classes)
    target = {
        # --- the exact key set harmony.musicxml_builder._target_for produces ---
        "absMeasure": measure.index,
        "measureNumber": measure.index + 1,
        "group": measure.group,
        "render": _payload_render(measure),
        "key": measure.key_display,
        "mode": measure.mode,
        "scale": list(measure.scale_pitches),
        "degree": a.roman or "",
        "degreeNumber": a.degree_number or 1,
        "roman": a.roman or "",
        "chordSymbol": a.chord_symbol or "",
        "root": a.root or "",
        "quality": a.quality or "",
        "chordTones": list(a.chord_tones),
        "pitchClasses": pcs,
        "midiPitches": measure.sounding_midis(),
        "bassMidi": min((n.midi for n in measure.staff2 if not n.is_rest),
                        default=None),
        "intervalLayer": a.interval_layer or "",
        "functionLabel": a.function_label or "",
        "scaleDegreeName": a.scale_degree_name or "",
        "explanation": a.explanation or a.lab_note,
        # --- additive lab fields (harmony_trainer.js ignores unknown fields) ---
        "concept": measure.render,
        "labNote": a.lab_note,
        "inversion": a.inversion,
        "figuredBass": a.figured_bass,
        "inversionLabel": a.inversion_label,
        "bassNote": a.bass_note,
        "bassPitchClass": measure.bass_pitch_class,
        "strictBass": measure.strict_bass,
        "voices": [list(v) for v in a.voices],
        "commonTones": list(a.common_tones),
        "bassMotion": a.bass_motion,
        "tendencyTones": list(a.tendency_tones),
        "cadenceType": a.cadence_type,
        "motiveLabel": a.motive_label,
        "degreeLabels": list(a.degree_labels),
        "impliedRoman": a.implied_roman,
        "impliedChord": a.implied_chord,
        "atlasScaleId": a.atlas_scale_id,
        "atlasDegreeId": a.atlas_degree_id,
        "atlasTriadId": a.atlas_triad_id,
    }
    return target


def build_lab_payload(experiment: LabExperiment) -> Dict:
    """Per-measure metadata for the runtime trainer (JSON-serialisable).

    Mirrors :func:`harmony.musicxml_builder.build_trainer_payload`'s shape
    (``TRAINER_MODE`` / ``TARGET_CHORDS`` / ``TARGET_BY_MEASURE`` /
    ``EXPECTED_MIDI_BY_MEASURE_OR_BEAT``) so the same controller drives it.
    """
    spec = experiment.spec
    targets = [_lab_target_for(m) for m in experiment.measures]
    target_by_measure = {str(t["absMeasure"]): t for t in targets}

    expected: Dict[str, object] = {}
    for measure, t in zip(experiment.measures, targets):
        abs_key = str(t["absMeasure"])
        if measure.expected_by_beat is not None:
            expected[abs_key] = {str(beat): list(pcs)
                                 for beat, pcs in measure.expected_by_beat.items()}
        else:
            expected[abs_key] = list(t["pitchClasses"])

    overall_render = "arpeggio" if spec.render in ("arpeggio", "melody") else "block"
    return {
        "TRAINER_MODE": True,
        "schema": "harmony-trainer/payload-v1",
        "labSchema": spec.schema,
        "exerciseId": spec.experiment_id,
        "experimentId": spec.experiment_id,
        "concept": spec.concept,
        "title": experiment.title,
        "render": overall_render,
        "match": "pitch_class",
        "TARGET_CHORDS": targets,
        "TARGET_BY_MEASURE": target_by_measure,
        "EXPECTED_MIDI_BY_MEASURE_OR_BEAT": expected,
    }


def build_lab_exercise(experiment: LabExperiment):
    """Convenience: return ``(musicxml_string, lab_payload)``."""
    return build_lab_musicxml(experiment), build_lab_payload(experiment)
