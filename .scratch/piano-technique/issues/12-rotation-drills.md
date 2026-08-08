# 12 — Exercise 8: rotation drills

**What to build:** The wrist-rotation study: hold a note, sound its upper neighbour three times
by rotating from the wrist, then shift the hold up a step — up the five-finger position and back.
The first held-note texture. Host: **Lab**, `lesson:tech_rotation`.

**Blocked by:** 01 — phrase engine; 04 — intra-staff second voice (render) + hold enforcement
(v2 grading); 02 — fingering.

**Status:** ready-for-agent

## Content

C major five-finger position, one measure per hold (quarters: three repeated neighbours + a
quarter rest to breathe / shift):

* **Ascending (4 measures):** hold degree d (whole note, second voice), play d+1 ×3 (voice 1
  quarters), for d = 1..4. **Descending (4 measures):** hold degree d, play d−1 ×3, for d = 5..2.
  8 measures per leaf.
* Fingering: hold-note finger = d's finger, moving finger = the neighbour's (1–2, 2–3, 3–4, 4–5
  ascending; 5–4 … descending); labels on both voices.
* **2 leaves:** `ex:tech_rotation_<rh|lh>` (LH mirrored an octave lower, staff2 + its second
  voice).
* Grading: v1 = the moving repetitions (the ordered walk demands the same pc three times — note
  ticket 03's re-attack rule applies to *dyad steps*; plain single-pc repeated steps already
  require distinct note-ons since each note-on advances one step). v2 (once 04's `hold` payload
  lands) = each repetition refuses unless the held note is down.
* Coach text (the video's core): "Don't activate the finger — rotate from the wrist to throw the
  upper note; the held finger just rests."

## Where

`_tech_rotation_specs()` in `harmony/curriculum.py`; pins +2; `tests/test_technique.py`: two-voice
measure shape (hold in voice 2, movers in voice 1), repeated-pc step sequence, `hold` payload
emission for v2.

- [ ] 2 leaves render hold-against-repetitions correctly on both staves.
- [ ] v1 grades the three strikes per measure; v2 blocks steps while the hold is up.
- [ ] Fingering on both voices; pins updated; honesty text present.

## Grading honesty

Rotation quality is precisely what MIDI cannot see; the drill grades pitches and (v2) the hold.
The coach line carries the technique.
