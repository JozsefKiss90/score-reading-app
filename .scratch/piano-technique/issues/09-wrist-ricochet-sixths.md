# 09 — Exercise 5: wrist ricochet (repeated sixths)

**What to build:** Quick repeated double notes from the wrist: a sixth restruck four times, the
neighbouring sixth answered, then denser middles. The gradable core is **repetition** — the same
dyad demanded N times in a row, each requiring a fresh attack (ticket 03's re-attack rule is the
load-bearing piece). Host: **Lab**, `lesson:tech_ricochet`.

**Blocked by:** 01 — phrase engine; 03 — dyad steps + re-attack rule; 02 — articulation marks
(wanted for the wrist-staccato display, not blocking if sequenced later).

**Status:** ready-for-agent

## Content

C major sixths (the video's pair): **E4+C5** then **F4+D5** (degrees (3,8) and (4,9)).

* **Variant A (quarters):** E/C ×4, F/D ×4, alternate for 4 measures (16 dyad steps/leaf half).
* **Variant B (eighths):** same alternation at eighths — the "add more notes in the middle"
  ramp. The video's triplet middle is **not representable** (no tuplet support — spec's
  out-of-scope list); approximate the density ramp with the eighth variant and say so in the
  coach text.
* Both variants in one leaf per hand (A measures then B measures, ≤ 12 total), LH an octave
  lower. **2 leaves:** `ex:tech_ricochet_<rh|lh>`.
* Every step: `{pcs: [pc(d), pc(d+5°)], minDistinct: 2}`; consecutive identical steps are exactly
  the case the re-attack rule exists for — holding both keys must NOT auto-complete the next
  repetition.
* Coach text: "The wrist provides the motion, not the fingers; stay loose" + graded/not-graded.

## Where

`_tech_ricochet_specs()` in `harmony/curriculum.py`; pins +2; `tests/test_technique.py` gains a
repeated-step payload test (identical consecutive steps preserved, not collapsed) and a manual-QA
note: hold both keys through two steps and confirm the second does not satisfy without re-attack.

- [ ] Repeated identical dyads each require a fresh strike of at least one constituent key.
- [ ] Alternation between the two sixths grades cleanly at both note values.
- [ ] Playback sounds the repetitions (playback plan already handles per-beat pc lists).
- [ ] Pins updated; honesty + no-triplet note present.

## Grading honesty

Repetition count and pitch are graded; speed, wrist motion, and the true triplet rhythm are not
(rhythm is playback/notation only).
