"""Turn a trainer/lab payload into a beat-timed target-playback plan (plan U1).

The trainer's transport (``audio.target_playback``) needs "what sounds when"
for a loaded exercise.  This module is that pure seam: it reads the payload
shape both builders emit (``harmony.musicxml_builder.build_trainer_payload``
and ``harmony.lab_musicxml.build_lab_payload``) and produces note events on a
beat clock, one 4/4 measure per target chord -- exactly what the score
notates:

* **block** -- the target's ``midiPitches`` plus its ``bassMidi`` sound
  together for the whole measure (whole notes);
* **arpeggio / melody** -- the bass (when notated) holds the whole measure
  while the tones sound one slot each, driven by the payload's
  ``EXPECTED_MIDI_BY_MEASURE_OR_BEAT`` map when present (4 quarter slots, 8
  eighth slots when the map extends past beat 4 as long motives do, or 16
  16th slots for the technique drills' 16th-note bars).

Playback follows the *notation*, not the grading: lab strict-bass measures
grade as ordered walks (``render == "arpeggio"``) but are notated as block
whole notes, so the lab's ``concept`` field overrides ``render`` here.

This module is pure: no Qt, no audio -- tempo, loop and transport state live
in the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

#: The builders emit 4/4 with one chord per measure.
BEATS_PER_MEASURE = 4

#: Renders whose notation is one tone per slot rather than sustained notes.
#: Everything else -- block, and the lab's voice_leading / polyphonic
#: concepts -- notates whole notes, so the block branch is faithful for them.
_SEQUENTIAL_RENDERS = ("arpeggio", "melody")

#: Octave used when a graded pitch class has no notated midi to borrow.
_FALLBACK_BASE_MIDI = 60


@dataclass(frozen=True)
class PlaybackEvent:
    """One noteon/noteoff span on the plan's beat clock."""

    start_beat: float
    dur_beats: float
    midis: Tuple[int, ...]
    target_index: int          # index into the payload's TARGET_CHORDS
    abs_measure: int           # score measure to sweep/flash


@dataclass(frozen=True)
class PlaybackPlan:
    events: Tuple[PlaybackEvent, ...]
    total_beats: float
    beats_per_measure: int = BEATS_PER_MEASURE


def seconds_per_beat(bpm: float) -> float:
    """Beat duration at ``bpm``; rejects non-positive tempi."""
    if bpm <= 0:
        raise ValueError(f"bpm must be positive, got {bpm!r}")
    return 60.0 / float(bpm)


def _dedup(midis: List[int]) -> Tuple[int, ...]:
    seen: Dict[int, None] = {}
    for m in midis:
        seen.setdefault(m, None)
    return tuple(seen)


def _midi_for_pc(pc: int, midis: List[int]) -> int:
    """The notated midi sounding pitch class ``pc``, else a middle-octave stand-in."""
    pc %= 12
    for m in midis:
        if m % 12 == pc:
            return m
    return _FALLBACK_BASE_MIDI + pc


def _beat_map(expected: object) -> Optional[Dict[int, List[int]]]:
    """The payload's per-slot pc map (1-based slot -> pcs), or None for block.

    Slots follow the notation: 4 quarters normally, 8 eighths for the long
    motives (``harmony.lab._gen_motive`` keys 1..8 when a motive has more
    than four degrees), 16 16ths for the technique drills' 16th-note bars
    (``harmony.lab._gen_technique`` keys 1..16).
    """
    if not isinstance(expected, dict):
        return None
    out: Dict[int, List[int]] = {}
    for beat, pcs in expected.items():
        try:
            b = int(beat)
        except (TypeError, ValueError):
            continue
        if 1 <= b <= 4 * BEATS_PER_MEASURE:
            out[b] = [int(p) for p in (pcs or [])]
    return out or None


def _slot_count(target: Dict, beat_map: Dict[int, List[int]]) -> int:
    """The measure's slot count: 4 quarters, 8 eighths, or 16 16ths.

    Lab melody targets state it (``slotsPerMeasure``), which keeps
    rest-padded bars at their notated speed -- ``beat_map`` keys only the
    sounding notes, so a 3-note 16th bar would otherwise stretch to
    quarters.  Without the field (trainer payloads, older lab payloads) the
    count is inferred as the smallest halving of the beat that holds the
    highest occupied slot.
    """
    declared = target.get("slotsPerMeasure")
    slots = declared if isinstance(declared, int) and declared > 0 \
        else BEATS_PER_MEASURE
    while slots < max(beat_map):
        slots *= 2
    return slots


def _sequential_events(target: Dict, expected: object, start: float,
                       index: int, abs_measure: int) -> List[PlaybackEvent]:
    midis = [int(m) for m in (target.get("midiPitches") or [])]
    events: List[PlaybackEvent] = []

    bass = target.get("bassMidi")
    if bass is not None:
        events.append(PlaybackEvent(start, float(BEATS_PER_MEASURE),
                                    (int(bass),), index, abs_measure))

    beat_map = _beat_map(expected)
    if beat_map is not None:
        slot_dur = BEATS_PER_MEASURE / float(_slot_count(target, beat_map))
        for beat in sorted(beat_map):
            tones = _dedup([_midi_for_pc(pc, midis) for pc in beat_map[beat]])
            if tones:
                events.append(PlaybackEvent(start + (beat - 1) * slot_dur,
                                            slot_dur, tones,
                                            index, abs_measure))
    else:
        for k, m in enumerate(midis[:BEATS_PER_MEASURE]):
            events.append(PlaybackEvent(start + k, 1.0, (m,),
                                        index, abs_measure))
    return events


def build_playback_plan(payload: Dict) -> PlaybackPlan:
    """Beat-timed events for a payload's ``TARGET_CHORDS``, in score order."""
    targets = payload.get("TARGET_CHORDS") or []
    expected_map = payload.get("EXPECTED_MIDI_BY_MEASURE_OR_BEAT") or {}

    events: List[PlaybackEvent] = []
    for i, t in enumerate(targets):
        abs_measure = int(t.get("absMeasure", i))
        start = float(BEATS_PER_MEASURE * i)
        notated = t.get("concept") or t.get("render") or "block"

        if notated in _SEQUENTIAL_RENDERS:
            events.extend(_sequential_events(
                t, expected_map.get(str(abs_measure)), start, i, abs_measure))
        else:
            midis = [int(m) for m in (t.get("midiPitches") or [])]
            bass = t.get("bassMidi")
            if bass is not None:
                midis.insert(0, int(bass))
            tones = _dedup(midis)
            if tones:
                events.append(PlaybackEvent(start, float(BEATS_PER_MEASURE),
                                            tones, i, abs_measure))

    events.sort(key=lambda e: (e.start_beat, e.target_index))
    return PlaybackPlan(events=tuple(events),
                        total_beats=float(BEATS_PER_MEASURE * len(targets)))
