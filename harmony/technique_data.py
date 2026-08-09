"""Standard piano fingering tables for the technique drills (data only).

Piano-technique ticket 06 ships the two-octave root-position tonic-arpeggio
table; the scale tables land with ticket 05.  Encoded from the standard
pedagogy charts (the ABRSM-style conventions as reproduced by the
colorinmypiano.com two-octave fingering appendix, Robert Kelley's keyboard
arpeggio chart and Margaret Denton's two-octave sheets):

* White-key patterns: RH ``1-2-3-1-2-3-5``; LH ``5-4-2-1-4-2-1`` — except
  the D/A/E/B-major LH, where 3 (not 4) takes the black third
  (``5-3-2-1-3-2-1``).
* Black-key roots (Db/Eb/Ab/Bb major; C#/F#/G#/Bb minor): the thumb never
  touches a black key — RH puts 1 on the single white chord tone
  (``2-1-2-4…``), LH crosses 4 over after the thumb (``2-1-4-2-1-4-2``,
  read descending-to-ascending as ``2142142``).  Bb minor's white tone is
  the FIFTH, so its patterns shift (RH ``2-3-1…``, LH ``3-2-1…``).
* Gb major / Eb minor are all-black triads, so the thumb does play black
  keys there: both keep the white-key RH; Eb minor keeps the white-key LH
  too, while Gb major's LH reads ``5-3-2-1-3-2-1``.

Where published charts disagree (D/A/E/B-major LH 5-3 vs 5-4; the Bb-major
alternates) the majority/primary reading above is encoded — these are
display-only fingerings, the grader never sees them.
"""

from __future__ import annotations

from typing import Dict, Tuple

#: 1-based scale degrees of a two-octave root-position tonic arpeggio,
#: ascending: root, 3rd, 5th, octave, 10th, 12th, double octave.
ARPEGGIO_DEGREES_UP: Tuple[int, ...] = (1, 3, 5, 8, 10, 12, 15)

_WHITE_RH = ("1", "2", "3", "1", "2", "3", "5")
_WHITE_LH = ("5", "4", "2", "1", "4", "2", "1")
_LH_BLACK_THIRD = ("5", "3", "2", "1", "3", "2", "1")   # D/A/E/B major
_BLACK_ROOT_RH = ("2", "1", "2", "4", "1", "2", "4")    # thumb on the white tone
_BLACK_ROOT_LH = ("2", "1", "4", "2", "1", "4", "2")

_W = {"rh": _WHITE_RH, "lh": _WHITE_LH}
_B3 = {"rh": _WHITE_RH, "lh": _LH_BLACK_THIRD}
_BR = {"rh": _BLACK_ROOT_RH, "lh": _BLACK_ROOT_LH}

#: ``(tonic, "major"|"minor") -> {"rh": 7 labels, "lh": 7 labels}`` —
#: ASCENDING two-octave fingering; every standard descent is the exact
#: reverse.  Tonic spellings match the trainer's practical key lists
#: (``DEFAULT_MAJOR_KEYS`` / ``DEFAULT_MINOR_KEYS``).
ARPEGGIO_FINGERINGS: Dict[Tuple[str, str], Dict[str, Tuple[str, ...]]] = {
    ("C", "major"): _W,
    ("Db", "major"): _BR,
    ("D", "major"): _B3,
    ("Eb", "major"): _BR,
    ("E", "major"): _B3,
    ("F", "major"): _W,
    ("Gb", "major"): _B3,        # all-black triad: the thumb plays black keys
    ("G", "major"): _W,
    ("Ab", "major"): _BR,
    ("A", "major"): _B3,
    ("Bb", "major"): {"rh": _BLACK_ROOT_RH,
                      "lh": ("3", "2", "1", "3", "2", "1", "3")},
    ("B", "major"): _B3,
    ("A", "minor"): _W,
    ("Bb", "minor"): {"rh": ("2", "3", "1", "2", "3", "1", "2"),
                      "lh": ("3", "2", "1", "3", "2", "1", "2")},
    ("B", "minor"): _W,
    ("C", "minor"): _W,
    ("C#", "minor"): _BR,
    ("D", "minor"): _W,
    ("Eb", "minor"): _W,         # all-black triad, like Gb major
    ("E", "minor"): _W,
    ("F", "minor"): _W,
    ("F#", "minor"): _BR,
    ("G", "minor"): _W,
    ("G#", "minor"): _BR,
}


def arpeggio_run_fingering(tonic: str, mode: str, hand: str) -> Tuple[str, ...]:
    """The 13 fingering labels of one up-and-down two-octave arpeggio cycle.

    Ascent (7 notes) then descent (6 more — the peak is not restruck); the
    descent is the ascent reversed, which every standard chart shares.
    """
    up = ARPEGGIO_FINGERINGS[(tonic, mode)][hand]
    return up + tuple(reversed(up))[1:]
