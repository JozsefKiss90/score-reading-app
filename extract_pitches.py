from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple, Any

# Reuse the project’s robust loaders
from model.score_loader import load_notes_from_mxl, build_measure_times


@dataclass
class NoteOut:
    part_index: int
    part_name: str
    measure_number: int           # displayed number
    abs_measure_index: int        # 0..N-1 across the whole score
    staff: int | None
    voice: int | None
    beat: int                     # 1-based (which beat within the measure)
    beat_pos: float               # 0..1 fractional position inside the beat
    offset_ql_in_measure: float
    duration_ql: float
    pitch_name: str               # notated spelling, e.g. G#4
    midi: int


def _compute_beats_for_measures(measures: List[Dict[str, Any]]
                                ) -> Tuple[List[int], List[float]]:
    """
    For each measure, decide how many beats it has and the QL per beat.

    This follows the same heuristic as BeatSelector._build_pitch_map so
    the beat numbering stays consistent with the UI.
    """
    beats_per_measure: List[int] = []
    beat_ql_per_measure: List[float] = []

    for m in measures:
        span_ql = float(m["end_ql"] - m["start_ql"]) or 4.0
        # If it's very close to an integer, use that as "beats"
        if abs(span_ql - round(span_ql)) < 1e-6:
            beats = int(max(1, min(12, round(span_ql))))
        else:
            # Fallback for odd bars (e.g. pick-up, irregular notation)
            beats = 4
        beats_per_measure.append(beats)
        beat_ql_per_measure.append(span_ql / beats)

    return beats_per_measure, beat_ql_per_measure


def extract_pitches(score_path: str
                    ) -> Tuple[List[NoteOut], Dict[int, Dict[int, List[str]]]]:
    """
    Bottom-up extraction of notated pitches per beat, using the same
    infrastructure as PianoRoll / BeatSelector.

    Returns:
      - flat list of NoteOut rows (one per notehead)
      - nested dict: abs_measure_index -> beat_number -> [pitch labels]
    """

    # 1) All notes with absolute QL timing and notated names
    #    (we pass score_path as both args; the helper figures out xml/mxl)
    notes, _bpm = load_notes_from_mxl(score_path, score_path)

    # 2) Measure timing (start/end QL + printed number)
    mt = build_measure_times(score_path)
    measures = list(mt)   # each: {"number","start_ql","end_ql",...}
    starts = [float(m["start_ql"]) for m in measures]

    def find_measure_index(ql: float) -> int:
        """Binary search to find which measure a given QL falls into."""
        lo, hi = 0, len(starts) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            m = measures[mid]
            if ql < m["start_ql"]:
                hi = mid - 1
            elif ql >= m["end_ql"]:
                lo = mid + 1
            else:
                return mid
        # Clamp if something lands exactly on the end, etc.
        return max(0, min(len(starts) - 1, lo))

    beats_per_measure, beat_ql_per_measure = _compute_beats_for_measures(measures)

    all_rows: List[NoteOut] = []
    beat_map: Dict[int, Dict[int, List[str]]] = {}

    # 3) Map every note into (measure, beat)
    pc_names = ["C", "C#", "D", "D#", "E", "F",
                "F#", "G", "G#", "A", "A#", "B"]

    for n in notes:
        start = float(n["start"])
        dur = float(n["duration"])
        midi = int(n["pitch"])
        staff = n.get("staff")

        mi = find_measure_index(start)
        m = measures[mi]
        beats = beats_per_measure[mi]
        beat_ql = beat_ql_per_measure[mi]
        m_start = float(m["start_ql"])

        rel = start - m_start
        if rel < 0:
            rel = 0.0

        # Beat index (1..beats) and fractional position in that beat
        if beat_ql > 0:
            beat_idx = int(rel // beat_ql) + 1
            beat_idx = max(1, min(beats, beat_idx))
            beat_pos = (rel % beat_ql) / beat_ql
        else:
            beat_idx = 1
            beat_pos = 0.0

        # Prefer notated spelling from loader; fallback to MIDI spelling
        name = n.get("name")
        if not name:
            name = f"{pc_names[midi % 12]}{midi // 12 - 1}"

        row = NoteOut(
            part_index=0,
            part_name="Score",
            measure_number=int(m["number"]),
            abs_measure_index=mi,
            staff=int(staff) if staff is not None else None,
            voice=None,
            beat=beat_idx,
            beat_pos=float(beat_pos),
            offset_ql_in_measure=float(rel),
            duration_ql=dur,
            pitch_name=name,
            midi=midi,
        )
        all_rows.append(row)
        beat_map.setdefault(mi, {}).setdefault(beat_idx, []).append(name)

    return all_rows, beat_map


if __name__ == "__main__":
    import argparse, csv, pathlib

    ap = argparse.ArgumentParser(
        description="Extract exact notated pitches per beat from a MusicXML/MXL score."
    )
    ap.add_argument("score", help="Path to .musicxml/.xml or .mxl")
    ap.add_argument("--json", default="pitches.json",
                    help="Output JSON (beat map + rows)")
    ap.add_argument("--csv", default="pitches.csv",
                    help="Optional flat CSV (one row per note)")
    args = ap.parse_args()

    rows, beats = extract_pitches(args.score)

    payload: Dict[str, Any] = {
        "beats_by_measure": {
            str(k): {str(b): v for b, v in d.items()}
            for k, d in beats.items()
        },
        "rows": [asdict(r) for r in rows],
    }
    pathlib.Path(args.json).write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    with open(args.csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "part_index", "part_name", "measure_number", "abs_measure_index",
            "staff", "voice", "beat", "beat_pos", "offset_ql_in_measure",
            "duration_ql", "pitch_name", "midi",
        ])
        for r in rows:
            w.writerow([
                r.part_index, r.part_name, r.measure_number, r.abs_measure_index,
                r.staff, r.voice, r.beat, f"{r.beat_pos:.3f}",
                f"{r.offset_ql_in_measure:.3f}", f"{r.duration_ql:.3f}",
                r.pitch_name, r.midi,
            ])

    print(f"Wrote {len(rows)} notes -> {args.json} / {args.csv}")
