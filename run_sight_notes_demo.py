from __future__ import annotations

import json
import random
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt, QCoreApplication, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QComboBox,
    QLabel,
)


# ----------------- Imports matching your existing framework -----------------

def _import_score_view_beats():
    try:
        from beat_selector.view import ScoreViewBeats  # type: ignore
        return ScoreViewBeats
    except Exception:
        pass
    from view import ScoreViewBeats  # type: ignore
    return ScoreViewBeats


def _import_midi_service():
    try:
        from audio.midi_service import MidiService  # type: ignore
        return MidiService
    except Exception:
        pass
    try:
        from .midi_service import MidiService  # type: ignore
        return MidiService
    except Exception:
        pass
    try:
        from midi_service import MidiService  # type: ignore
        return MidiService
    except Exception:
        pass
    return None


ScoreViewBeats = _import_score_view_beats()
MidiService = _import_midi_service()


# ----------------- Config: 4 bars of 4/4 -----------------

# NOTE: The JSON schema does *not* limit you to 4 measures.
# The original demo hard-coded 4 bars for convenience; we now compute
# the required number of measures dynamically from the token stream.
DEFAULT_MEASURES = 4
# Safety cap to avoid accidentally generating huge temporary scores
# from malformed inputs.
MAX_MEASURES = 64
BEATS_PER_MEASURE = 4

# Use a high-enough divisions so quarter/eighth/sixteenth are integers.
# quarter = 16, eighth = 8, sixteenth = 4
DIVISIONS = 16
MEASURE_TICKS = BEATS_PER_MEASURE * DIVISIONS  # 64


# ----------------- Key signature logic (major/minor to fifths) -----------------

_MAJOR_FIFTHS = {
    "C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F#": 6, "C#": 7,
    "F": -1, "Bb": -2, "Eb": -3, "Ab": -4, "Db": -5, "Gb": -6, "Cb": -7,
}
_MINOR_FIFTHS = {
    "A": 0, "E": 1, "B": 2, "F#": 3, "C#": 4, "G#": 5, "D#": 6, "A#": 7,
    "D": -1, "G": -2, "C": -3, "F": -4, "Bb": -5, "Eb": -6, "Ab": -7,
}

_SHARP_ORDER = ["F", "C", "G", "D", "A", "E", "B"]
_FLAT_ORDER  = ["B", "E", "A", "D", "G", "C", "F"]

_NOTE_RE = re.compile(r"^([A-Ga-g])([#b]{0,2})?(-?\d+)$")


def key_to_fifths(key_str: str) -> int:
    """
    Robust key parser.
    Accepts:
      - "C major"
      - "A minor"
      - "A harmonic minor" / "A melodic minor" / "A natural minor"
    Also tolerates accidental misuse like:
      - "B half-diminished"
      - "B fully diminished"
    In such cases we fall back to a sensible key signature (tonic + minor by default).
    """
    s = (key_str or "").strip()
    if not s:
        print("[WARN] Empty key; defaulting to C major.")
        return 0

    # --- 1) canonical musical keys ---
    # "A harmonic minor" style
    m = re.match(
        r"^([A-Ga-g])\s*([#b]{0,2})\s*(natural|harmonic|melodic)\s+minor\s*$",
        s,
        flags=re.IGNORECASE,
    )
    if m:
        tonic = m.group(1).upper() + (m.group(2) or "")
        if tonic in _MINOR_FIFTHS:
            return _MINOR_FIFTHS[tonic]
        print(f"[WARN] Unsupported minor tonic spelling: {tonic!r}; defaulting to 0.")
        return 0

    # "A minor" / "C major" style
    m = re.match(
        r"^([A-Ga-g])\s*([#b]{0,2})\s*(major|minor)\s*$",
        s,
        flags=re.IGNORECASE,
    )
    if m:
        tonic = m.group(1).upper() + (m.group(2) or "")
        mode = m.group(3).lower()
        if mode == "major":
            if tonic in _MAJOR_FIFTHS:
                return _MAJOR_FIFTHS[tonic]
            print(f"[WARN] Unsupported major tonic spelling: {tonic!r}; defaulting to 0.")
            return 0
        else:
            if tonic in _MINOR_FIFTHS:
                return _MINOR_FIFTHS[tonic]
            print(f"[WARN] Unsupported minor tonic spelling: {tonic!r}; defaulting to 0.")
            return 0

    # --- 2) Detect chord-quality strings incorrectly placed in `key` ---
    # Examples in your sequences.json: "B half-diminished", "B fully diminished" :contentReference[oaicite:4]{index=4}
    m = re.match(r"^([A-Ga-g])\s*([#b]{0,2})\s+(.+)$", s)
    if m:
        tonic = m.group(1).upper() + (m.group(2) or "")
        qual = (m.group(3) or "").strip().lower()

        if any(k in qual for k in ["diminished", "half-diminished", "fully diminished", "augmented", "dominant", "major7", "minor7"]):
            # Best-effort: use tonic minor signature (works well for vii°/ø contexts),
            # but you can switch to major if you prefer.
            if tonic in _MINOR_FIFTHS:
                print(f"[WARN] Key looks like chord quality ({key_str!r}); using {tonic} minor key signature.")
                return _MINOR_FIFTHS[tonic]
            if tonic in _MAJOR_FIFTHS:
                print(f"[WARN] Key looks like chord quality ({key_str!r}); using {tonic} major key signature.")
                return _MAJOR_FIFTHS[tonic]

    print(f"[WARN] Bad key format: {key_str!r}; defaulting to C major.")
    return 0


def ks_alter_for_step(step: str, fifths: int) -> Optional[int]:
    step = step.upper()
    if fifths > 0:
        sharps = set(_SHARP_ORDER[: min(7, fifths)])
        return 1 if step in sharps else None
    if fifths < 0:
        flats = set(_FLAT_ORDER[: min(7, -fifths)])
        return -1 if step in flats else None
    return None


# ----------------- Duration parsing -----------------
# Token format:
#   "C4"     -> quarter
#   "C4/8"   -> eighth
#   "C4/16"  -> sixteenth
# You may also write accidentals: "C#4/16", "Db3/8", etc.

_TOKEN_RE = re.compile(r"^(.+?)(?:/(\d+(?:\.\d+)?))?$")


def parse_note_token(tok: str) -> Tuple[str, Optional[int], int, int, str]:
    """
    Returns (step, alter, octave, ticks, note_type)
    Token format:
      "C4"     -> quarter (default)
      "C4/1"   -> whole
      "C4/2"   -> half
      "C4/4"   -> quarter
      "C4/8"   -> eighth
      "C4/16"  -> sixteenth
    """
    t = tok.strip()
    m = _TOKEN_RE.match(t)
    if not m:
        raise ValueError(f"Bad token: {tok!r}")

    pitch_part = m.group(1).strip()
    denom_str = m.group(2)
    if denom_str is None:
        # default quarter
        ticks = DIVISIONS
        note_type = "quarter"
    elif "." in denom_str:
        # Treat decimals as BEATS (1.0 = quarter note)
        beats = float(denom_str)

        # Only allow values that map cleanly to the supported note types
        # (you can extend this later with dots/ties)
        if beats == 4.0:
            ticks = DIVISIONS * 4
            note_type = "whole"
        elif beats == 2.0:
            ticks = DIVISIONS * 2
            note_type = "half"
        elif beats == 1.0:
            ticks = DIVISIONS
            note_type = "quarter"
        elif beats == 0.5:
            ticks = DIVISIONS // 2
            note_type = "eighth"
        elif beats == 0.25:
            ticks = DIVISIONS // 4
            note_type = "16th"
        else:
            raise ValueError(
                f"Unsupported beat duration /{denom_str} in {tok!r}. "
                f"Allowed beat values: /4.0 /2.0 /1.0 /0.5 /0.25 "
                f"(or use denominators: /1 /2 /4 /8 /16)."
            )
    else:
        # Treat integers as NOTE DENOMINATORS
        denom = int(denom_str)
        if denom == 1:
            ticks = DIVISIONS * 4
            note_type = "whole"
        elif denom == 2:
            ticks = DIVISIONS * 2
            note_type = "half"
        elif denom == 4:
            ticks = DIVISIONS
            note_type = "quarter"
        elif denom == 8:
            ticks = DIVISIONS // 2
            note_type = "eighth"
        elif denom == 16:
            ticks = DIVISIONS // 4
            note_type = "16th"
        else:
            raise ValueError(f"Unsupported duration /{denom} in {tok!r}. Allowed: /1 /2 /4 /8 /16")


    return step, alter, octave, ticks, note_type

def parse_event_token(tok: str):
    t = tok.strip()
    m = _TOKEN_RE.match(t)
    if not m:
        raise ValueError(f"Bad token: {tok!r}")

    pitch_part = m.group(1).strip()
    denom_str = m.group(2)  # <-- string, lehet "8" vagy "0.5" vagy None

    # ---- DURATION PARSING (supports decimals as beats) ----
    if denom_str is None:
        ticks = DIVISIONS
        note_type = "quarter"
    elif "." in denom_str:
        beats = float(denom_str)
        if beats == 4.0:
            ticks = DIVISIONS * 4; note_type = "whole"
        elif beats == 2.0:
            ticks = DIVISIONS * 2; note_type = "half"
        elif beats == 1.0:
            ticks = DIVISIONS; note_type = "quarter"
        elif beats == 0.5:
            ticks = DIVISIONS // 2; note_type = "eighth"
        elif beats == 0.25:
            ticks = DIVISIONS // 4; note_type = "16th"
        else:
            raise ValueError(
                f"Unsupported beat duration /{denom_str} in {tok!r}. "
                f"Allowed: /4.0 /2.0 /1.0 /0.5 /0.25 (or /1 /2 /4 /8 /16)."
            )
    else:
        denom = int(denom_str)
        if denom == 1:
            ticks = DIVISIONS * 4; note_type = "whole"
        elif denom == 2:
            ticks = DIVISIONS * 2; note_type = "half"
        elif denom == 4:
            ticks = DIVISIONS; note_type = "quarter"
        elif denom == 8:
            ticks = DIVISIONS // 2; note_type = "eighth"
        elif denom == 16:
            ticks = DIVISIONS // 4; note_type = "16th"
        else:
            raise ValueError(f"Unsupported duration /{denom} in {tok!r}. Allowed: /1 /2 /4 /8 /16")

    # chord split (or single)
    pitch_tokens = [p.strip() for p in pitch_part.split("+") if p.strip()]
    if not pitch_tokens:
        raise ValueError(f"Empty pitch in token: {tok!r}")

    pitches: List[Tuple[str, Optional[int], int]] = []
    for p in pitch_tokens:
        pm = _NOTE_RE.match(p)
        if not pm:
            raise ValueError(f"Bad pitch: {p!r} in token {tok!r}. Use e.g. C4, C#4, Db3.")
        step = pm.group(1).upper()
        acc = pm.group(2) or ""
        octave = int(pm.group(3))
        alter = None if acc == "" else (acc.count("#") - acc.count("b"))
        pitches.append((step, alter, octave))

    return pitches, ticks, note_type

# ----------------- MusicXML generation -----------------

def note_xml(
    step: str,
    alter: Optional[int],
    octave: int,
    ticks: int,
    note_type: str,
    staff: int,
    voice: int,
    ks_fifths: int,
    beam_tags: str = "",
    is_chord_tone: bool = False,
) -> str:
    ks_alter = ks_alter_for_step(step, ks_fifths)
    eff_alter = alter if alter is not None else ks_alter

    alter_xml = f"<alter>{eff_alter}</alter>" if eff_alter is not None else ""

    accidental_xml = ""
    if eff_alter != ks_alter and eff_alter is not None:
        accidental_xml = f"<accidental>{'sharp' if eff_alter > 0 else 'flat'}</accidental>"
    if eff_alter is None and ks_alter is not None:
        accidental_xml = "<accidental>natural</accidental>"

    chord_xml = "<chord/>" if is_chord_tone else ""

    return f"""
      <note>
        {chord_xml}
        <pitch><step>{step}</step>{alter_xml}<octave>{octave}</octave></pitch>
        {accidental_xml}
        <duration>{ticks}</duration><type>{note_type}</type>
        {beam_tags}
        <voice>{voice}</voice><staff>{staff}</staff>
      </note>
    """


def rest_xml(ticks: int, note_type: str, staff: int, voice: int) -> str:
    return f"""
      <note>
        <rest/>
        <duration>{ticks}</duration><type>{note_type}</type>
        <voice>{voice}</voice><staff>{staff}</staff>
      </note>
    """


def _beam_tags_for(note_type: str, pos_in_group: int, group_len: int) -> str:
    """
    note_type: "eighth" or "16th"
    pos_in_group: 0..group_len-1
    """
    if note_type == "eighth":
        if group_len < 2:
            return ""
        if pos_in_group == 0:
            return '<beam number="1">begin</beam>'
        if pos_in_group == group_len - 1:
            return '<beam number="1">end</beam>'
        return '<beam number="1">continue</beam>'

    if note_type == "16th":
        if group_len < 2:
            return ""
        # beam 1 always spans the whole group
        if pos_in_group == 0:
            b1 = '<beam number="1">begin</beam>'
        elif pos_in_group == group_len - 1:
            b1 = '<beam number="1">end</beam>'
        else:
            b1 = '<beam number="1">continue</beam>'

        # beam 2 spans the same group for 16ths
        if pos_in_group == 0:
            b2 = '<beam number="2">begin</beam>'
        elif pos_in_group == group_len - 1:
            b2 = '<beam number="2">end</beam>'
        else:
            b2 = '<beam number="2">continue</beam>'

        return b1 + b2

    return ""


def _measures_needed(tokens: List[str]) -> int:
    """Return how many 4/4 measures are needed to place all tokens.

    We simulate packing using the same rules as _pack_to_measures():
    - tokens that don't fit in the remaining space of a bar are deferred
      to the next bar (no splitting).
    - leftover space is filled with rests.
    """
    if not tokens:
        return DEFAULT_MEASURES

    idx = 0
    n_measures = 0

    while idx < len(tokens) and n_measures < MAX_MEASURES:
        n_measures += 1
        remaining = MEASURE_TICKS

        while remaining > 0 and idx < len(tokens):
            _pitches, ticks, _note_type = parse_event_token(tokens[idx])

            # If a single token is longer than a bar, we can't place it.
            # Consume it to avoid an infinite loop.
            if ticks > MEASURE_TICKS:
                idx += 1
                break

            if ticks > remaining:
                break

            remaining -= ticks
            idx += 1

    if n_measures < DEFAULT_MEASURES:
        n_measures = DEFAULT_MEASURES

    return min(n_measures, MAX_MEASURES)


def _pack_to_measures(
    tokens: List[str],
    ks_fifths: int,
    staff: int,
    voice: int,
    n_measures: int,
) -> List[List[str]]:
    """
    Pack note/chord events into n_measures measures, each MEASURE_TICKS long.
    tokens: like ["C4/4", "E4+G4/2", ...]
    Returns list of measures, each a list of MusicXML note/rest strings.
    """
    measures: List[List[str]] = [[] for _ in range(n_measures)]
    idx = 0

    for m in range(n_measures):
        remaining = MEASURE_TICKS
        out: List[str] = []

        while remaining > 0 and idx < len(tokens):
            pitches, ticks, note_type = parse_event_token(tokens[idx])

            if ticks > remaining:
                break

            # beaming is only meaningful for single-note short values; for chords we can still beam,
            # but simplest: apply beam tags only to the FIRST chord tone.
            used = MEASURE_TICKS - remaining
            ticks_per_beat = DIVISIONS
            pos_in_beat = used % ticks_per_beat

            beam_tags = ""
            if note_type == "eighth" and ticks == DIVISIONS // 2:
                pos_in_group = 0 if pos_in_beat < (DIVISIONS // 2) else 1
                beam_tags = _beam_tags_for("eighth", pos_in_group, 2)
            elif note_type == "16th" and ticks == DIVISIONS // 4:
                pos_in_group = min(3, pos_in_beat // (DIVISIONS // 4))
                beam_tags = _beam_tags_for("16th", pos_in_group, 4)

            # emit chord: first note normal, subsequent notes with <chord/>
            for j, (step, alter, octave) in enumerate(pitches):
                out.append(
                    note_xml(
                        step,
                        alter,
                        octave,
                        ticks,
                        note_type,
                        staff=staff,
                        voice=voice,
                        ks_fifths=ks_fifths,
                        beam_tags=(beam_tags if j == 0 else ""),
                        is_chord_tone=(j > 0),
                    )
                )

            remaining -= ticks
            idx += 1

        # Fill remainder with rests
        while remaining > 0:
            if remaining >= DIVISIONS * 2:
                out.append(rest_xml(DIVISIONS * 2, "half", staff=staff, voice=voice))
                remaining -= DIVISIONS * 2
            elif remaining >= DIVISIONS:
                out.append(rest_xml(DIVISIONS, "quarter", staff=staff, voice=voice))
                remaining -= DIVISIONS
            elif remaining >= DIVISIONS // 2:
                out.append(rest_xml(DIVISIONS // 2, "eighth", staff=staff, voice=voice))
                remaining -= DIVISIONS // 2
            else:
                out.append(rest_xml(DIVISIONS // 4, "16th", staff=staff, voice=voice))
                remaining -= DIVISIONS // 4

        measures[m] = out

    return measures


def write_exercise_musicxml(
    path: Path,
    title: str,
    key_str: str,
    treble_tokens: List[str],
    bass_tokens: List[str],
) -> tuple[int, int]:
    """
    Writes the exercise to MusicXML.

    Returns:
      (key_signature_fifths, n_measures_written)
    """
    ks_fifths = key_to_fifths(key_str)

    n_treble = _measures_needed(treble_tokens)
    n_bass = _measures_needed(bass_tokens)
    n_measures = max(DEFAULT_MEASURES, n_treble, n_bass)
    n_measures = min(n_measures, MAX_MEASURES)

    treble_measures = _pack_to_measures(treble_tokens, ks_fifths=ks_fifths, staff=1, voice=1, n_measures=n_measures)
    bass_measures = _pack_to_measures(bass_tokens, ks_fifths=ks_fifths, staff=2, voice=2, n_measures=n_measures)

    measures_xml: List[str] = []
    for m_no in range(1, n_measures + 1):
        attr_block = ""
        if m_no == 1:
            attr_block = f"""
      <attributes>
        <divisions>{DIVISIONS}</divisions>
        <key><fifths>{ks_fifths}</fifths></key>
        <time><beats>4</beats><beat-type>4</beat-type></time>
        <staves>2</staves>
        <clef number="1"><sign>G</sign><line>2</line></clef>
        <clef number="2"><sign>F</sign><line>4</line></clef>
      </attributes>

      <direction placement="above">
        <direction-type>
          <metronome><beat-unit>quarter</beat-unit><per-minute>80</per-minute></metronome>
        </direction-type>
        <sound tempo="80"/>
      </direction>
"""

        barline = ""
        if m_no == n_measures:
            barline = '<barline location="right"><bar-style>light-heavy</bar-style></barline>'

        treble_xml = "\n".join(treble_measures[m_no - 1])
        bass_xml = "\n".join(bass_measures[m_no - 1])

        measures_xml.append(f"""
    <measure number="{m_no}">
{attr_block}
      {treble_xml}

      <backup><duration>{MEASURE_TICKS}</duration></backup>

      {bass_xml}

      {barline}
    </measure>
""")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN"
  "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="3.1">
  <work><work-title>{title}</work-title></work>

  <part-list>
    <score-part id="P1"><part-name>Piano</part-name></score-part>
  </part-list>

  <part id="P1">
    {''.join(measures_xml)}
  </part>
</score-partwise>
"""
    path.write_text(xml, encoding="utf-8")
    return ks_fifths, n_measures


# ----------------- JS mapping: build selNotesByMidi from PITCH_MAP -----------------

def build_js_init_selnotes_by_midi(ks_fifths: int) -> str:
    """
    Builds a JS snippet that:
      1) normalizes enharmonic spelling in PITCH_MAP based on key signature
         (flat keys => prefer flats; ensures Eb major never displays D#)
      2) builds selNoteIds + selNotesByMidi for MIDI highlighting
    """
    return rf"""
(() => {{
  const app = window.ScoreApp;
  if(!app || !app.state) return {{ ok:false, why:"ScoreApp not ready" }};

  const S = app.state;
  const pm = S.boot && S.boot.PITCH_MAP;
  if(!pm) return {{ ok:false, why:"No PITCH_MAP yet" }};

  const KS_FIFTHS = {ks_fifths};
  const preferFlats = (KS_FIFTHS < 0);

  const asciiPitch = (s) => (s || "").toString().trim().replace(/♯/g,"#").replace(/♭/g,"b");

  // For flat keys: coerce sharp spellings to flat spellings (enharmonic),
  // so Eb major never displays D# (it becomes Eb), etc.
  const preferPitchSpelling = (pitch) => {{
    const t = asciiPitch(pitch);
    if(!preferFlats) return t;
    const m = /^([A-Ga-g])([#b]{{0,2}})(-?\d+)$/.exec(t);
    if(!m) return t;
    const step = m[1].toUpperCase();
    const acc  = m[2] || "";
    const oct  = m[3];

    // Only rewrite common sharp spellings to their flat enharmonics.
    // (We do NOT touch already-flat spellings.)
    const map = {{
      "C#": "Db",
      "D#": "Eb",
      "F#": "Gb",
      "G#": "Ab",
      "A#": "Bb",
      // Rare, but safe-ish for display:
      "E#": "F",
      "B#": "C",
    }};

    const key = step + acc;
    const repl = map[key];
    if(!repl) return t;
    return repl + oct;
  }};

  const pitchToMidi = (pitch) => {{
    const t = preferPitchSpelling(pitch);
    const m = /^([A-Ga-g])([#b]{{0,2}})(-?\d+)$/.exec(t);
    if(!m) return null;
    const pc = m[1].toUpperCase();
    const acc = m[2] || "";
    const oct = parseInt(m[3], 10);
    const base = ({{C:0,D:2,E:4,F:5,G:7,A:9,B:11}})[pc];
    const delta = (acc.match(/#/g)||[]).length - (acc.match(/b/g)||[]).length;
    return (oct + 1) * 12 + (base + delta);
  }};

  const selIds = new Set();
  const byMidi = new Map();

  for(const absStr of Object.keys(pm)){{
    const beatsObj = pm[absStr] || {{}};
    for(const beatStr of Object.keys(beatsObj)){{
      const rows = Array.isArray(beatsObj[beatStr]) ? beatsObj[beatStr] : [];
      for(const r of rows){{
        const id = r && r.id ? String(r.id) : null;
        const pitch = r && r.pitch ? String(r.pitch) : null;
        if(!id) continue;

        selIds.add(id);

        // Normalize spelling in-place so any UI that reads r.pitch won't show sharps in flat keys.
        if(pitch && preferFlats) {{
          const p2 = preferPitchSpelling(pitch);
          if(p2 && p2 !== pitch) r.pitch = p2;
        }}

        const midi = pitch ? pitchToMidi(pitch) : null;
        if(midi !== null){{
          let set = byMidi.get(midi);
          if(!set){{ set = new Set(); byMidi.set(midi, set); }}
          set.add(id);
        }}
      }}
    }}
  }}

  S.selNoteIds = selIds;
  S.selNotesByMidi = byMidi;

  if(typeof app.refreshMidiHighlights === "function") app.refreshMidiHighlights();
  return {{ ok:true, ids: selIds.size, midiKeys: byMidi.size, preferFlats }};
}})()
"""


# ----------------- Loading exercises -----------------

@dataclass(frozen=True)
class Exercise:
    name: str
    key: str
    treble: List[str]
    bass: List[str]


def load_exercises(json_path: Path) -> List[Exercise]:
    """
    Supports TWO formats:

    A) legacy:
      { "exercises": [ { "name":..., "key":..., "treble":[...], "bass":[...] }, ... ] }

    B) new task-based (recommended):
      {
        "exercise_id": "...",
        "title": "...",
        "tasks": [
          {
            "task_id": "...",
            "key": "E major",
            "score": { "treble":[...], "bass":[...] }
          },
          ...
        ]
      }
    """
    obj = json.loads(json_path.read_text(encoding="utf-8"))

    exs: List[Exercise] = []

    # ---- A) legacy format ----
    if isinstance(obj, dict) and "exercises" in obj:
        for e in obj.get("exercises", []) or []:
            if not isinstance(e, dict):
                continue
            exs.append(
                Exercise(
                    name=str(e.get("name", "Unnamed")),
                    key=str(e["key"]),
                    treble=list(e.get("treble", [])),
                    bass=list(e.get("bass", [])),
                )
            )
        if not exs:
            raise ValueError(f"No exercises found under 'exercises' in: {json_path}")
        return exs

    # ---- B) new task-based format ----
    if isinstance(obj, dict) and "tasks" in obj:
        exercise_title = str(obj.get("title") or obj.get("exercise_id") or json_path.parent.name)

        tasks = obj.get("tasks", []) or []
        if not isinstance(tasks, list) or not tasks:
            raise ValueError(f"No tasks found under 'tasks' in: {json_path}")

        for t in tasks:
            if not isinstance(t, dict):
                continue
            key = str(t.get("key", "")).strip()
            score = t.get("score") or {}
            if not isinstance(score, dict):
                score = {}

            treble = list(score.get("treble", []) or [])
            bass = list(score.get("bass", []) or [])

            # name: combine exercise title + task id for UI dropdown
            task_id = str(t.get("task_id", "task"))
            name = f"{exercise_title} / {task_id}"

            if not key:
                raise ValueError(f"Task {task_id} is missing 'key' in: {json_path}")
            if not treble and not bass:
                raise ValueError(f"Task {task_id} has empty score in: {json_path}")

            exs.append(
                Exercise(
                    name=name,
                    key=key,
                    treble=treble,
                    bass=bass,
                )
            )

        if not exs:
            raise ValueError(f"No usable tasks found in: {json_path}")
        return exs

    raise ValueError(
        f"Unsupported sequences.json format in: {json_path}. "
        f"Expected either top-level 'exercises' or top-level 'tasks'."
    )


# ----------------- UI wrapper: switch between exercises -----------------

class PracticeWindow(QWidget):
    def __init__(self, exercises: List[Exercise], midi_service=None):
        super().__init__()
        self.exercises = exercises
        self._midi_service = midi_service

        self._current_idx = 0
        self._score_widget: Optional[ScoreViewBeats] = None
        self._tmp_paths: List[Path] = []
        self._tmp_fifths: List[int] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)

        top = QHBoxLayout()
        top.addWidget(QLabel("Exercise:"))

        self.cmb = QComboBox()
        for ex in exercises:
            self.cmb.addItem(f"{ex.name}  —  {ex.key}")
        self.cmb.currentIndexChanged.connect(self._on_combo_changed)
        top.addWidget(self.cmb, 1)

        self.btnPrevEx = QPushButton("◀ Prev")
        self.btnPrevEx.clicked.connect(self.prev_exercise)
        top.addWidget(self.btnPrevEx)

        self.btnNextEx = QPushButton("Next ▶")
        self.btnNextEx.clicked.connect(self.next_exercise)
        top.addWidget(self.btnNextEx)

        self.btnRandom = QPushButton("Random")
        self.btnRandom.clicked.connect(self.random_exercise)
        top.addWidget(self.btnRandom)

        root.addLayout(top)

        self._score_container = QVBoxLayout()
        self._score_container.setContentsMargins(0, 0, 0, 0)
        root.addLayout(self._score_container, 1)

        self.load_index(0)

    def _remove_current_score(self):
        if self._score_widget is None:
            return
        w = self._score_widget
        self._score_container.removeWidget(w)
        w.setParent(None)
        w.deleteLater()
        self._score_widget = None

    def _make_temp_score(self, ex: Exercise) -> Tuple[Path, int, int]:
        tmp = tempfile.NamedTemporaryFile(prefix="sight_ex_", suffix=".xml", delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()
        ks_fifths, n_measures = write_exercise_musicxml(
            tmp_path,
            title=ex.name,
            key_str=ex.key,
            treble_tokens=ex.treble,
            bass_tokens=ex.bass,
        )
        self._tmp_paths.append(tmp_path)
        self._tmp_fifths.append(ks_fifths)
        return tmp_path, ks_fifths, n_measures

    def load_index(self, idx: int):
        if not self.exercises:
            return
        idx = idx % len(self.exercises)
        self._current_idx = idx
        ex = self.exercises[idx]

        # Score length is derived from the token stream.
        # (We set the final title after generating the temp score.)
        self.setWindowTitle(f"Sight Practice — {ex.name} ({ex.key})")

        self.cmb.blockSignals(True)
        self.cmb.setCurrentIndex(idx)
        self.cmb.blockSignals(False)

        self._remove_current_score()

        mxl_path, ks_fifths, n_measures = self._make_temp_score(ex)
        self.setWindowTitle(f"Sight Practice — {ex.name} ({ex.key}) — {n_measures} bars")
        self._score_widget = ScoreViewBeats(str(mxl_path), midi_service=self._midi_service)
        self._score_container.addWidget(self._score_widget, 1)

        def try_inject():
            w = self._score_widget
            if w is None:
                return
            if not getattr(w, "_html_ready", False):
                QTimer.singleShot(50, try_inject)
                return
            js = build_js_init_selnotes_by_midi(ks_fifths)
            w._run_js_safe(js, label="init_selNotesByMidi")

        QTimer.singleShot(50, try_inject)

    def prev_exercise(self):
        self.load_index(self._current_idx - 1)

    def next_exercise(self):
        self.load_index(self._current_idx + 1)

    def random_exercise(self):
        if not self.exercises:
            return
        if len(self.exercises) == 1:
            self.load_index(0)
            return
        choices = list(range(len(self.exercises)))
        choices.remove(self._current_idx)
        self.load_index(random.choice(choices))

    def _on_combo_changed(self, idx: int):
        self.load_index(idx)


def main(argv: List[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    app = QApplication(argv)

    PROJECT_ROOT = Path(__file__).resolve().parent
    json_path = PROJECT_ROOT / "exercises" / "ex_07_06_fast_chord_filtering_bach_iteration" / "sequences.json"

    exercises = load_exercises(json_path)

    midi_service = None
    if MidiService is None:
        print("[PRACTICE] MidiService import failed. MIDI will NOT work.")
    else:
        midi_service = MidiService()
        print("[PRACTICE] MidiService active:", getattr(midi_service, "port_name", None))

    win = PracticeWindow(exercises, midi_service=midi_service)
    win.resize(1000, 760)
    win.show() 

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
