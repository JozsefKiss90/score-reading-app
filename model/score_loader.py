
from __future__ import annotations
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import List, Dict, Any
from music21 import converter, note as m21note, chord as m21chord, tempo as m21tempo, stream
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import List, Dict, Any, Tuple
import zipfile, io
from music21 import converter, note as m21note, chord as m21chord, tempo as m21tempo, stream

def _parse_musicxml_tree(xml_path: str, mxl_path: str) -> ET.Element | None:
    """
    Try to return an ElementTree root for a MusicXML document.
    - If xml_path is a .xml -> parse it
    - If xml_path is an .mxl (zip) or parsing fails -> try to extract the first .xml from that .mxl
    - If that still fails -> return None
    """
    # 1) try xml_path directly
    try:
        return ET.parse(xml_path).getroot()
    except Exception:
        pass

    # 2) if xml_path looks like .mxl, try unzip
    try_candidates = []
    if xml_path.lower().endswith(".mxl"):
        try_candidates.append(xml_path)
    if mxl_path and mxl_path.lower().endswith(".mxl") and mxl_path != xml_path:
        try_candidates.append(mxl_path)

    for cand in try_candidates:
        try:
            with zipfile.ZipFile(cand, "r") as zf:
                # prefer common names; otherwise first .xml in the archive
                names = zf.namelist()
                preferred = [n for n in names if n.lower().endswith((".xml", ".musicxml"))]
                if not preferred:
                    continue
                name = preferred[0]
                data = zf.read(name)
                return ET.fromstring(data)
        except Exception:
            continue

    return None

def load_notes_from_mxl(mxl_path: str, xml_path: str):
    """
    Returns (notes, bpm), where notes = list of dicts with keys: pitch, start, duration, staff.
    - 'start' and 'duration' are in quarter-lengths (QL), as before.
    - Robust to xml_path being an .mxl or a non-parseable file.
    """
    root = _parse_musicxml_tree(xml_path, mxl_path)
    staff_map = defaultdict(int)

    # Build staff map (best-effort). If we cannot parse a tree, we skip and default staff=1 later.
    if root is not None:
        for part in root.findall(".//part"):
            for measure in part.findall("measure"):
                try:
                    measure_num = int(measure.attrib.get("number", "0"))
                except Exception:
                    measure_num = 0
                for n in measure.findall("note"):
                    staff = int(n.findtext("staff", default="1"))
                    if n.find("rest") is None:
                        pitch_el = n.find("pitch")
                        if pitch_el is not None:
                            step = pitch_el.findtext("step", "?")
                            alter = pitch_el.findtext("alter")
                            octave = pitch_el.findtext("octave", "?")
                            accidental = "#" if alter == "1" else "b" if alter == "-1" else ""
                            pitch_name = f"{step}{accidental}{octave}"
                            duration = n.findtext("duration", "?")
                            staff_map[(measure_num, pitch_name, str(duration))] = staff

    # Music21 flatten for timing/pitches
    score = converter.parse(mxl_path)
    bpm = 0.0
    mm = score.metronomeMarkBoundaries()
    if mm:
        bpm = mm[0][2].number if mm[0][2].number else 0.0

    flat_notes = score.flat.notes
    notes = []
    for n in flat_notes:
        if isinstance(n, m21note.Note):
            pitch_name = n.nameWithOctave
            start = float(n.offset)
            duration = float(n.quarterLength)
            try:
                measure_num = int(getattr(n, "measureNumber", 0) or 0)
            except Exception:
                measure_num = 0
            staff = staff_map.get((measure_num, pitch_name, str(int(duration))), 1)
            notes.append({"pitch": n.pitch.midi, "start": start, "duration": duration, "staff": staff})
        elif isinstance(n, m21chord.Chord):
            for p in n.pitches:
                pitch_name = p.nameWithOctave
                start = float(n.offset)
                duration = float(n.quarterLength)
                try:
                    measure_num = int(getattr(n, "measureNumber", 0) or 0)
                except Exception:
                    measure_num = 0
                staff = staff_map.get((measure_num, pitch_name, str(int(duration))), 1)
                notes.append({"pitch": p.midi, "start": start, "duration": duration, "staff": staff})

    return notes, bpm

def build_tempo_segments(mxl_path: str):
    """
    Returns list of tempo segments with absolute times:
    [{start_ql, end_ql, bpm, start_sec, end_sec}, ...]
    """
    try:
        score = converter.parse(mxl_path)
        highest_ql = float(score.flat.highestTime)

        marks = {}
        for mm in score.recurse().getElementsByClass(m21tempo.MetronomeMark):
            try:
                off = float(mm.getOffsetBySite(score))
            except Exception:
                off = float(mm.offset or 0.0)
            qpm = float(mm.getQuarterBPM() or 60.0)
            key = round(off, 6)
            if key not in marks:
                marks[key] = qpm

        items = sorted(marks.items(), key=lambda t: t[0])
        if not items:
            items = [(0.0, 60.0)]
        if items[0][0] > 0.0:
            items.insert(0, (0.0, items[0][1]))

        segs = []
        t_sec = 0.0
        for i, (off, bpm) in enumerate(items):
            next_off = items[i + 1][0] if i + 1 < len(items) else highest_ql
            dur_q = max(0.0, (next_off - off))
            end_sec = t_sec + (dur_q * 60.0 / bpm)
            segs.append({
                "start_ql": off, "end_ql": next_off,
                "bpm": bpm, "start_sec": t_sec, "end_sec": end_sec
            })
            t_sec = end_sec
        return segs
    except Exception as e:
        print("Tempo parse error:", e)
        return [{"start_ql": 0.0, "end_ql": 1e9, "bpm": 60.0, "start_sec": 0.0, "end_sec": 1e9}]

def bpm_at_seconds(tempo_segments, sec: float) -> float:
    for s in tempo_segments:
        if s["start_sec"] <= sec < s["end_sec"]:
            return s["bpm"]
    return tempo_segments[-1]["bpm"] if tempo_segments else 60.0

# score_loader.py
def ql_to_seconds(tempo_segments, ql: float) -> float:
    """Map an absolute quarter-length offset to absolute seconds using tempo segments."""
    for s in tempo_segments:
        if s["start_ql"] <= ql < s["end_ql"]:
            return s["start_sec"] + (ql - s["start_ql"]) * (60.0 / s["bpm"])
    # If beyond the last segment, continue at the last tempo
    last = tempo_segments[-1]
    return last["end_sec"] + (ql - last["end_ql"]) * (60.0 / last["bpm"])

def ql_duration_to_seconds(tempo_segments, start_ql: float, dur_ql: float) -> float:
    """Convert a duration that may span tempo changes to seconds."""
    remaining = float(dur_ql)
    pos_ql = float(start_ql)
    total_sec = 0.0
    for s in tempo_segments:
        if pos_ql >= s["end_ql"]:
            continue
        if pos_ql < s["start_ql"]:
            # jump into the segment
            pos_ql = s["start_ql"]
        if remaining <= 0:
            break
        take_ql = min(remaining, s["end_ql"] - pos_ql)
        total_sec += take_ql * (60.0 / s["bpm"])
        remaining -= take_ql
        pos_ql += take_ql
    return total_sec

def build_measure_times(mxl_path: str):
    """
    Return a list of measures with absolute timing:
    [{"number": int, "start_ql": float, "end_ql": float,
      "start_sec": float, "end_sec": float}, ...]
    Uses the first part as the barline reference.
    """
    score = converter.parse(mxl_path)
    tempo_segments = build_tempo_segments(mxl_path)

    # Pick a reference part (barlines/time sigs live here in standard scores)
    part = score.parts[0] if getattr(score, "parts", None) else score
    measures = list(part.getElementsByClass(stream.Measure))

    out = []
    for i, m in enumerate(measures):
        # Measure number (fallback to 1-based index if missing)
        try:
            num = int(getattr(m, "number", None) or (i + 1))
        except Exception:
            num = i + 1

        start_ql = float(m.offset)

        # Prefer notated bar duration; fall back to next measure's offset
        bar_dur = getattr(m, "barDuration", None)
        if bar_dur is not None:
            end_ql = start_ql + float(bar_dur.quarterLength)
        else:
            next_off = float(measures[i + 1].offset) if i + 1 < len(measures) else float(part.highestTime)
            end_ql = max(start_ql, next_off)

        start_sec = ql_to_seconds(tempo_segments, start_ql)
        end_sec = ql_to_seconds(tempo_segments, end_ql)
        out.append({
            "number": num,
            "start_ql": start_ql, "end_ql": end_ql,
            "start_sec": start_sec, "end_sec": end_sec
        })
    return out