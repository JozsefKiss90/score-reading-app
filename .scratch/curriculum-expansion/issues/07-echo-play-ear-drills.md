# 07 — Echo-play ear drills, A1 v0

**What to build:** The first aural twin. From a visual chord/progression leaf that is at least *started*, the learner opens the echo variant: the target plays with notation hidden; the learner plays it back on the keyboard; the existing pitch-class validator grades it; the result counts toward the *same* leaf's mastery record. Sound-before-symbol ordering inside the lesson. Later A1 levels (quality ID, progression ID, cadence ID, bass dictation, chromatic spotting) ship inside their module tickets — this ticket is echo-play only.

**Blocked by:** 05 — Target playback + transport.

**Status:** done

- [x] An echo variant is available for triad and progression leaves once the visual leaf is started.
- [x] Notation is hidden during the listen phase; the playback attempt is graded exactly as in visual drills.
- [x] Aural and visual attempts share one mastery record per leaf.
- [x] At least the existing triad and cadence drill families have echo twins.

**Plan:** docs/curriculum_expansion_plan.md §4 A1 (level 1)

**Implementation notes (2026-07-26):**

- `harmony/echo_drills.py` (new, pure): `echo_variant` (same compiled chords,
  `presentation="echo"`), `is_echo_eligible` (native `drill`-concept leaves —
  115 of 231, covering the triad families *and* the cadence block drills),
  `echo_unlocked` (visual leaf at least started), `echo_demo_specs`/`GROUP_ECHO`
  for the standalone launcher.
- `HarmonyExerciseSpec.presentation` (`visual` default | `echo`; echo requires
  `answer_mode="midi"`), carried as the payload's `PRESENTATION`.
- `harmony_trainer.js`: unfinished echo drills veil the SVG notation
  (noteheads/beams/rests/accidentals/ledger lines/harm labels), redact the
  guide panel + chord cards + `currentTarget()` sync feed (`echoVeiled`);
  grading untouched; finishing reveals, renavigation re-veils.
- Hosts: trainer window auto-plays the transport on echo load (sound-first);
  Lab workspace adds the gated 🎧 Echo button per eligible leaf
  (`echoEligible` payload flag), enforces the gate host-side, withholds the
  Harmonic Scene until the completion reveal, and records echo completions
  under the same curriculum node id (one mastery record per leaf).
- Tests: `tests/test_echo_drills.py` (26), `tests/harmony_trainer_echo_test.js`
  (43 assertions), curriculum echo-affordance section in
  `tests/curriculum_node_test.js`; full suite 870 + all node suites green.
- Docs: `docs/harmony_trainer.md` §5c, `docs/curriculum.md` §3 note.
