from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Set, Tuple, List, Optional

from music21 import converter, note, chord, stream, meter


@dataclass
class BeatIndex:
    """
    per_measure: {measure_idx -> set[int midi]}
    per_beat: {(measure_idx, beat_number) -> set[int midi]}
    beats_in_measure: {measure_idx -> int}  (for overlay counts)
    """
    per_measure: Dict[int, Set[int]]
    per_beat: Dict[Tuple[int, int], Set[int]]
    beats_in_measure: Dict[int, int]


def _midi_set(n: note.NotRest) -> Set[int]:
    if isinstance(n, note.Note):
        return {int(n.pitch.midi)}
    if isinstance(n, chord.Chord):
        return {int(p.midi) for p in n.pitches}
    return set()


def _collect_measure_spans_and_ts(s: stream.Score) -> List[Tuple[int, float, float, meter.TimeSignature]]:
    parts = s.parts if hasattr(s, "parts") and len(s.parts) > 0 else [s]
    fp = parts[0].flat
    measures = list(fp.getElementsByClass(stream.Measure))
    if not measures:
        total = float(s.flat.highestTime)
        ts = meter.TimeSignature("4/4")
        beat_ql = float(ts.beatDuration.quarterLength)
        spans, start, idx = [], 0.0, 0
        while start < total - 1e-9:
            end = min(total, start + beat_ql * ts.numerator)
            spans.append((idx, start, end, ts))
            start, idx = end, idx + 1
        return spans

    starts = sorted(float(m.offset) for m in measures)
    total = float(s.flat.highestTime)

    eff_ts, current = [], None
    for m in measures:
        ts_here = m.getContextByClass(meter.TimeSignature)
        if ts_here is not None:
            current = ts_here
        if current is None:
            current = meter.TimeSignature("4/4")
        eff_ts.append(current)

    spans = []
    for i, st in enumerate(starts):
        en = starts[i + 1] if i + 1 < len(starts) else total
        spans.append((i, float(st), float(en), eff_ts[i] if i < len(eff_ts) else meter.TimeSignature("4/4")))
    return spans


def build_beat_index(path: str) -> BeatIndex:
    s = converter.parse(path)

    measure_spans = _collect_measure_spans_and_ts(s)  # [(m_idx, startQL, endQL, ts)]
    if not measure_spans:
        total = float(s.flat.highestTime) or 4.0
        ts = meter.TimeSignature("4/4")
        measure_spans = [(0, 0.0, total, ts)]

    per_measure: Dict[int, Set[int]] = {}
    per_beat: Dict[Tuple[int, int], Set[int]] = {}
    beats_in_measure: Dict[int, int] = {}

    info = []
    for (m_idx, start, end, ts) in measure_spans:
        beats = int(ts.numerator) if ts.numerator is not None else 4
        beat_ql = float(ts.beatDuration.quarterLength) if ts is not None else 1.0
        info.append((m_idx, start, end, beats, beat_ql))
        beats_in_measure[m_idx] = beats
        per_measure.setdefault(m_idx, set())
        for b in range(1, beats + 1):
            per_beat.setdefault((m_idx, b), set())

    for ev in s.recurse().notes:
        if isinstance(ev, note.Rest):
            continue
        onset = float(ev.offset)
        mids = _midi_set(ev)
        if not mids:
            continue
        placed = False
        for (m_idx, st, en, beats, beat_ql) in info:
            if onset < st - 1e-9 or onset >= en - 1e-9:
                continue
            rel = max(0.0, onset - st)
            b = int(rel // max(1e-9, beat_ql)) + 1
            b = max(1, min(beats, b))
            per_measure[m_idx].update(mids)
            per_beat[(m_idx, b)].update(mids)
            placed = True
            break
        if not placed and info:
            m_idx, *_rest = info[-1]
            b = beats_in_measure[m_idx]
            per_measure[m_idx].update(mids)
            per_beat[(m_idx, b)].update(mids)

    return BeatIndex(per_measure=per_measure, per_beat=per_beat, beats_in_measure=beats_in_measure)
