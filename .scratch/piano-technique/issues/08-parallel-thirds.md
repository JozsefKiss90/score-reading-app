# 08 — Exercise 4: thirds

**What to build:** Legato double thirds through one octave, in groups of four, parallel and
contrary — the first drill whose *answer* is a simultaneity. Host: **Lab**,
`lesson:tech_thirds`.

**Blocked by:** 01 — phrase engine; 02 — fingering; 03 — dyad steps (hard dependency: without it
a third is ungradable).

**Status:** ready-for-agent

## Content

C major, eighth-note dyad steps (each step = ticket-03 `{pcs: [pc(d), pc(d+2)]}`, rendered as a
`<chord/>`-stacked pair):

* **Ascending:** bottom degree d = 1..8 (C–E up to C–E an octave higher), each dyad played once,
  stepwise — 8 steps = 1 measure; then **descending** back 8..1 — 1 measure. Repeat the pair of
  measures in the video's groups-of-four phrasing (accent mark on steps 1 and 5 once 02 lands) —
  4 measures total per leaf.
* **Fingering** (standard alternation, rendered on both noteheads): RH 1-3, 2-4, 3-5, then the
  13/24/35 rotation continuing up (data row in `harmony/technique_data.py`); LH mirrored 5-3,
  4-2, 3-1….
* **Leaves (3):** `ex:tech_thirds_rh`, `ex:tech_thirds_lh`, and `ex:tech_thirds_contrary`
  (hands together, RH ascending while LH descends from the same C — each step is a FOUR-pc
  demand: both hands' thirds merged into one step's `pcs` with `minDistinct: 4`; where the four
  tones collapse to fewer distinct pcs, `minDistinct` still forces four distinct keys).
* Coach text: "Smooth and connected — finger legato; contrary motion is symmetrical and easier:
  notice why" (video's point), plus graded/not-graded.

## Where

`_tech_thirds_specs()` in `harmony/curriculum.py`; leaf-count pins +3; `tests/test_technique.py`
gains a dyad-payload shape test (8 steps per measure, each 2 pcs; contrary leaf steps carry 4 pcs
/ minDistinct 4).

- [ ] RH/LH leaves grade dyad-by-dyad (both keys down advances; single key does not).
- [ ] Contrary leaf demands all four keys down per step.
- [ ] Fingering renders on the dyads; accent marks land on 1 and 5 of each group.
- [ ] Pins updated; honesty text present.

## Grading honesty

Concurrency, not attack synchrony (ticket 03's rule) — and legato itself is invisible to the
grader (releases ignored). Say so in the leaf description.
