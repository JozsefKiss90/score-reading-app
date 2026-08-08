# 07 — Exercise 3: thumb-under drills

**What to build:** The four thumb-crossing cells, both hands, with the fingering display carrying
the entire lesson: the pitch content is trivial scale steps — the *point* is which finger plays
what. Host: **Lab**, `lesson:tech_thumb` under `cat:technique`.

**Blocked by:** 01 — phrase engine; 02 — fingering rendering (essential here, not cosmetic).

**Status:** ready-for-agent

## Content

Four cells in C major (the video demonstrates in position; transposition is a non-goal here —
ticket 05 covers all keys). Each cell: ascend with the thumb tucking under, descend with the
crossing reversed, repeated twice, eighth notes. RH ascending degrees / fingering:

| Cell | Degrees (up + down) | RH fingering (up + down) |
|------|--------------------|--------------------------|
| Under 2nd | 1 2 3 2 1 | 1 2 **1** 2 1 |
| Under 3rd | 1 2 3 4 3 2 1 | 1 2 3 **1** 3 2 1 |
| Under 4th | 1 2 3 4 5 4 3 2 1 | 1 2 3 4 **1** 4 3 2 1 |
| Under 5th | 1 2 3 4 5 6 5 4 3 2 1 | 1 2 3 4 5 **1** 5 4 3 2 1 |

(The bolded **1** is the crossing — after it the hand has shifted; on the descent the crossing
finger recrosses *over* the thumb.) LH mirrors: same fingering numbers on **descending** degrees
first (LH thumb-under happens going down), i.e. LH cell = the degree sequence inverted below the
tonic: 1, 7, 6… — build it as degrees (8,7,6,7,8) etc. anchored an octave lower so the line stays
in bass-clef range.

Each leaf = one cell, one hand: repeat the cell to fill 2–4 measures (rest-pad the tail), so
**8 leaves**: `ex:tech_thumb_<u2|u3|u4|u5>_<rh|lh>`. Coach text: "As fast as clean; minimal wrist
— let the thumb do the work" (from the video), plus the graded/not-graded line.

## Where

Spec factory `_tech_thumb_specs()` in `harmony/curriculum.py`; fingering rows in
`harmony/technique_data.py`. Difficulty "beginner"; `_chain_siblings` orders u2→u5, rh before lh.
Update both leaf-count pins (+8) and extend `tests/test_technique.py` with a fingering-oracle
check for the under-3rd RH row.

- [ ] 8 leaves launch, render the cells with the crossing fingering visible, grade in order.
- [ ] LH leaves render on the bass staff in a playable register.
- [ ] Coach + honesty text present; pins updated.

## Grading honesty

Speed and the physical tuck are ungraded (no timing grading exists); what is graded is the exact
note order — which does catch the classic error of *skipping* the crossing note.
