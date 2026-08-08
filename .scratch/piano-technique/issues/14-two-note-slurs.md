# 14 — Exercise 10: two-note slurs

**What to build:** The drop-lift gesture study: slurred note pairs climbing an octave by step and
returning, for each finger pair — first note emphasized (wrist drops in), second released (wrist
lifts). Host: **Lab**, `lesson:tech_slurs`.

**Blocked by:** 01 — phrase engine; 02 — slur arcs + fingering (the slur mark is the lesson's
visual; grading works without it, so 02 may land after, but the leaves ship with marks).

**Status:** ready-for-agent

## Content

C major, quarter-note pairs, two pairs per measure:

* **Phrase for finger pair (a,b):** ascending pairs on bottom degree d = 1..7
  ((d, d+1) slurred), then descending pairs d = 7..1 ((d+1, d) slurred — the video descends with
  the same combination) — 14 pairs = 28 quarters = 7 measures.
* Notation per pair (needs 02): slur start/stop across the two notes; accent on the first note,
  staccato-style lift on the second is conventional but the video says simply "first emphasized,
  second less" — use accent + no mark, keep it clean. Fingering a on the first, b on the second
  (pairs 1-2, 2-3, 3-4, 4-5).
* **8 leaves:** `ex:tech_slur_<12|23|34|45>_<rh|lh>`. (Hands-together is a video aside — "makes
  it go faster" — skip; unison grading would work as in ticket 11 if ever wanted.)
* Grading: plain ordered walk — works with ticket 01 alone.
* Coach text: "Drop the wrist into the first note, let it float up on the second; the gesture is
  the exercise" + graded/not-graded.

## Where

`_tech_slur_specs()` in `harmony/curriculum.py`; pair data shared with ticket 11 in
`harmony/technique_data.py`; pins +8; `tests/test_technique.py`: pair construction and the
descent's inverted pair order; slur XML present on every pair (once 02 is in).

- [ ] 8 leaves launch/render/grade; descent pairs invert correctly.
- [ ] Slur arcs + accent + fingering render per pair.
- [ ] Pins updated; honesty text present.

## Grading honesty

The drop-lift dynamic shape (loud–soft) is exactly what velocity grading would measure one day —
the hooks exist and are unused (spec doctrine); today the walk grades the note pairs in order,
and the description says so.
