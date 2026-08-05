# 10 — G1b: all five diatonic seventh qualities

**What to build:** The full diatonic seventh vocabulary. The engine builds and spells every diatonic seventh (ii7, Imaj7, IV7, vi7, half-diminished, diminished); a seventh-quality drill mirrors the existing triad quality drill; ii7–V7–I lands in all 12 major keys (block → arpeggio); and a hear-a-seventh quality-ID drill answers by MCQ (Mm7 / mm7 / MM7 / ø7 / °7).

**Blocked by:** 09 — G1a V7 tracer. (The ear-ID variant additionally needs 06 — answer modalities and 07 — echo-play machinery.)

**Status:** ready-for-human

- [x] All diatonic seventh qualities build and spell correctly in supported modes.
- [x] A seventh-quality performance drill runs across keys.
- [x] ii7–V7–I drills exist in all 12 major keys in both block and arpeggio renders.
- [x] A quality-ID-by-ear MCQ drill covers the five seventh qualities.

**Implementation notes (2026-08-05):** shipped on `fable_refactor`. The token
vocabulary is one spelled roman per degree per mode (`Imaj7`, `ii7`, …,
`viiø7`; minor's `i7` … `VII7`) — `build_seventh_chord` refuses a token whose
built roman does not match (so `V7` still refuses natural minor). °7 is
classified but not buildable (no diatonic instance until harmonic minor, G2);
it appears only as an MCQ distractor. New curriculum: 16 leaves (7 quality +
3 hear-a-seventh echo+MCQ + 6 ii7–V7–I block/arp), cat:sevenths now 32,
grand total 263. The ear drills are natively `presentation="echo"` +
`answer_mode="mcq"` + `mcq_focus="quality"`; the Lab host withholds the
routed scene for them like the echo-button path. `lesson:sevenths_more`
stays reserved, reworded to the G1c figured-bass-inversion seam.

**Plan:** docs/curriculum_expansion_plan.md §3 G1
