# 11 — G1c: V7 figured bass + bass-line dictation

**What to build:** V7 inversions become performance instructions. The learner reads 7–6/5–4/3–4/2 figures and must voice the demanded bass note, graded by the strict-bass machinery from ticket 04. Plus *bass-line dictation*: hear a progression play, then perform only its bass line.

**Blocked by:** 09 — G1a V7 tracer; 04 — strict-bass grading; 05 — target playback.

**Status:** done

- [x] V6/5, V4/3, and V4/2 drills grade the demanded bass note as the lowest sounding note.
- [x] Figured-bass captions match exactly what is graded.
- [x] A bass-line dictation drill plays a progression and grades a bass-only response.

**Plan:** docs/curriculum_expansion_plan.md §3 G1, G4; §4 A1 (level 5)

**Shipped (ticket 11):**
- `harmony/lab_spec.py`: `V65`/`V43`/`V42` (+ slash spellings) parse to the V7
  tetrad + inversion 1–3; the `inversion` concept accepts seventh-token degrees
  with inversions `{0,1,2,3}`; new cadence parameter `dictation: "bass"`.
- `harmony/lab.py`: tetrad figure table (`7 · 6/5 · 4/3 · 4/2`, third
  inversion), seventh-degree inversion experiments, figured-seventh cadence
  measures strict-bass graded; dictation collapses each graded target to its
  bass pitch class while notation/playback keep the full chords.
- `harmony/lab_musicxml.py`: lab payloads carry `PRESENTATION` (dictation ⇒
  `"echo"`, veil + host auto-play) and `DICTATION: "bass"`.
- `beat_selector/harmony_trainer.js`: dictation-aware veiled prompt/header.
- `harmony/curriculum.py`: `lesson:sevenths_more` went live — 12 V7
  figured-inversion leaves + 12 resolution-walk leaves (`V6/5→I, V4/3→I,
  V4/2→I6` per key); new `lesson:bass_dictation` under Inversions with 9
  ear-first leaves (roots / ii6 / V7-figure bass lines × C, G, Eb). 263→296.
- Honesty: `graph_scene_router` refuses `inversion_space` for seventh-degree
  experiments (no V7 on a triad node — the network nodes unreserve with G1d);
  the Lab host withholds the routed scene for dictation leaves like echo.
- Tests: `tests/test_figured_sevenths.py`, `tests/test_bass_dictation.py`,
  JS Test J in `tests/harmony_trainer_echo_test.js`; count pins updated.
