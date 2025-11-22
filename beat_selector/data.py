
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Tuple

# Be resilient to project layout differences
try:
    from model.score_loader import (
        build_tempo_segments,
        build_measure_times,
        ql_to_seconds,
        load_notes_from_mxl,
    )
except Exception:  # fallback to flat layout
    from score_loader import (
        build_tempo_segments,
        build_measure_times,
        ql_to_seconds,
        load_notes_from_mxl,
    )

@dataclass
class Measure:
    index: int
    number: int
    start_ql: float
    end_ql: float
    start_sec: float
    end_sec: float

def build_measures(mxl_path: str) -> Tuple[List[Measure], List[dict], list]:
    tempo_segments = build_tempo_segments(mxl_path)
    mt = build_measure_times(mxl_path)
    measures = [
        Measure(i, int(m["number"]), float(m["start_ql"]), float(m["end_ql"]),
                float(m["start_sec"]), float(m["end_sec"]))
        for i, m in enumerate(mt)
    ]
    return measures, mt, tempo_segments

def build_onsets(measures: List[Measure], tempo_segments, notes: List[dict]) -> List[List[float]]:
    arr = [[] for _ in measures]
    starts = [m.start_ql for m in measures]

    def find_idx(ql: float) -> int:
        lo, hi = 0, len(starts)-1
        while lo<=hi:
            mid=(lo+hi)//2
            m=measures[mid]
            if ql < m.start_ql: hi=mid-1
            elif ql >= m.end_ql: lo=mid+1
            else: return mid
        return max(0, min(len(starts)-1, lo))

    for n in notes:
        ql=float(n["start"])
        i=find_idx(ql)
        m=measures[i]
        sec=ql_to_seconds(tempo_segments, ql)
        arr[i].append(max(0.0, sec - m.start_sec))

    for i, L in enumerate(arr):
        L.sort()
        uniq=[]
        for t in L:
            if not uniq or abs(t-uniq[-1])>0.010: uniq.append(t)
        arr[i]=uniq
    return arr

def build_pitch_map(measures: List[Measure], notes: List[dict]) -> Dict[int, Dict[int, List[str]]]:
    by_measure: Dict[int, list] = {i: [] for i in range(len(measures))}
    starts = [m.start_ql for m in measures]
    for n in notes:
        ql = float(n["start"])
        lo, hi = 0, len(starts) - 1
        i = 0
        while lo <= hi:
            mid = (lo + hi) // 2
            m = measures[mid]
            if ql < m.start_ql: hi = mid - 1
            elif ql >= m.end_ql: lo = mid + 1
            else: i = mid; break
        else:
            i = max(0, min(len(starts) - 1, lo))
        by_measure[i].append(n)

    pitch_map: Dict[int, Dict[int, List[str]]] = {}
    for i, m in enumerate(measures):
        span_ql = (m.end_ql - m.start_ql) or 4.0
        beats = int(max(1, min(12, round(span_ql)))) if abs(span_ql - round(span_ql)) < 1e-6 else 4
        beat_ql = span_ql / beats
        labels_by_beat: Dict[int, List[str]] = {b: [] for b in range(1, beats + 1)}
        ms = measures[i].start_ql
        for n in sorted(by_measure[i], key=lambda x: (x["start"], x["pitch"])):
            rel = float(n["start"]) - ms
            b   = int(rel // beat_ql) + 1
            b   = max(1, min(beats, b))
            midi = int(n["pitch"])
            names = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
            labels_by_beat[b].append(f"{names[midi%12]}{midi//12 - 1}")
        pitch_map[i] = labels_by_beat
    return pitch_map
