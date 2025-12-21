from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Optional

from model.score_loader import ql_to_seconds, load_notes_from_mxl


@dataclass
class Measure:
    index: int
    number: int
    start_ql: float
    end_ql: float
    start_sec: float
    end_sec: float


def build_onsets_by_measure(measures: List[Measure], tempo_segments, mxl_path: str, xml_path: str) -> List[List[float]]:
    notes, _ = load_notes_from_mxl(mxl_path, xml_path)
    arr = [[] for _ in measures]
    starts = [m.start_ql for m in measures]

    def find_idx(ql: float) -> int:
        lo, hi = 0, len(starts) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            m = measures[mid]
            if ql < m.start_ql:
                hi = mid - 1
            elif ql >= m.end_ql:
                lo = mid + 1
            else:
                return mid
        return max(0, min(len(starts) - 1, lo))

    for n in notes:
        ql = float(n["start"])
        i = find_idx(ql)
        m = measures[i]
        sec = ql_to_seconds(tempo_segments, ql)
        arr[i].append(max(0.0, sec - m.start_sec))

    for i, L in enumerate(arr):
        L.sort()
        uniq: list[float] = []
        for t in L:
            if not uniq or abs(t - uniq[-1]) > 0.010:
                uniq.append(t)
        arr[i] = uniq

    return arr


def build_beats_by_measure(measures: List[Measure], tempo_segments) -> List[List[float]]:
    beats = [[] for _ in measures]
    for i, m in enumerate(measures):
        bar_ql = m.end_ql - m.start_ql
        n_beats = max(1, int(round(bar_ql)))  # quarter = beat
        step_ql = bar_ql / n_beats
        row = []
        for k in range(n_beats):
            ql = m.start_ql + k * step_ql
            row.append(max(0.0, ql_to_seconds(tempo_segments, ql) - m.start_sec))
        beats[i] = row
    return beats


def midi_to_name(midi: int) -> str:
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    name = names[midi % 12]
    octave = (midi // 12) - 1
    return f"{name}{octave}"


def build_pitch_events_by_measure(measures: List[Measure], tempo_segments, mxl_path: str, xml_path: str) -> List[List[dict]]:
    notes, _ = load_notes_from_mxl(mxl_path, xml_path)
    events: List[List[dict]] = [[] for _ in measures]
    starts = [m.start_ql for m in measures]

    def find_idx(ql: float) -> int:
        lo, hi = 0, len(starts) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            m = measures[mid]
            if ql < m.start_ql:
                hi = mid - 1
            elif ql >= m.end_ql:
                lo = mid + 1
            else:
                return mid
        return max(0, min(len(starts) - 1, lo))

    for n in notes:
        ql = float(n["start"])
        i = find_idx(ql)
        m = measures[i]
        sec = ql_to_seconds(tempo_segments, ql)
        t_rel = max(0.0, sec - m.start_sec)
        pitch_name = midi_to_name(int(n["pitch"]))
        events[i].append({"t_rel": t_rel, "pitch": pitch_name, "used": False})

    for i in range(len(events)):
        events[i].sort(key=lambda e: (e["t_rel"], e["pitch"]))

    return events
