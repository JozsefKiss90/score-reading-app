# 06 — Exercise 2: arpeggios in groups of four

**What to build:** The video's twist on arpeggios: play them in **groups of four instead of
three** ("1-2-3-4" so the accent — and the thumb — lands on a different chord tone each time).
Two deliverables, matching the host evaluation:

* **A. Trainer** (`run_harmony_trainer_demo.py`): the four-tone accent cell as an opt-in group —
  the only exercise in this effort the trainer's own builder can carry.
* **B. Lab:** two-octave arpeggio *runs* with standard fingerings, as `cat:technique` leaves.

**Blocked by:** (A) — nothing. (B) 01 — phrase engine; 02 — fingering/16ths.

**Status:** ready-for-human

## A. Trainer accent cell (no Lab involvement)

* `HarmonyExerciseSpec` gains optional `arp_octave_root: bool = False` (additive; `from_dict`
  tolerant; default False keeps the pinned 102-drill set byte-stable).
* `_treble_arpeggio` (`musicxml_builder.py:220-230`) appends the root **an octave up** as the 4th
  quarter when the flag is set (no rest padding). Grading is automatic: `pitchClasses` becomes
  `[r, 3rd, 5th, r]` and the ordered walk accepts the return to the root (mod-12).
* New group constant `GROUP_TECH_ARPEGGIO = "Technique: arpeggio cells (groups of four)"` +
  `technique_arpeggio_demo_specs()` — model: `identification_demo_specs`
  (`exercise_spec.py:767-806`). Content: tonic-arpeggio cells across all 12 keys, one spec per
  mode (drill="horizontal_degree", degree I/i, render="arpeggio", flag on) = 12 measures each,
  major + minor = 2 specs.
* Registered **only** in `_load_groups` (`run_harmony_trainer_demo.py:593-605`), after
  `GROUP_ECHO`.

## B. Lab arpeggio runs

* Phrase per key: degrees (1,3,5,8,10,12,15) up and (15,12,10,8,5,3,1) down = 13 notes… render as
  eighths across 2 measures (v1) or one 16th measure + pad (implementer's choice; eighths read
  better). RH then LH measure groups as in ticket 05. Repeat the cycle twice so the groups-of-four
  accent shifts through the chord tones — with 02's accent mark on every 4th note.
* Keys: 12 major + 12 minor tonic arpeggios = **24 leaves**, `ex:tech_arp_run_<keyslug>_<mode>`,
  under `lesson:tech_arpeggios`. Standard arpeggio fingerings from `harmony/technique_data.py`
  (RH C major 1-2-3-1…, LH 5-4-2-1…; the black-key sets per the standard table).
* Coach text: "Accent the first of each four — the accent itself is not graded."

- [x] A: flag + builder change; both specs appear in the opt-in group; default groups unchanged
      (pinned tests stay green); ordered grading accepts the 4-tone cell.
- [x] B: 24 leaves launch/render/grade with fingering; accent marks on beat-1 of each group.
- [x] Leaf-count pins +24; per-category test extended.

## Grading honesty

Accent placement is unobservable (velocity is discarded — `harmony_trainer.js:561` uses it only
as a note-off test); the groups-of-four benefit is embodied in the *notation and fingering*, the
grade remains right-tones-in-order.

## Comments

Implemented (2026-08-09). Notes for the reviewer:

* A: `arp_octave_root` validates fail-closed (requires `render="arpeggio"`; refuses
  `mcq_focus="quality"`, whose option set counts pitch classes); `to_dict` omits the flag when
  False so the pinned default set serialises byte-identically. The builder raises on a tetrad +
  flag (5 quarters can't fit 4/4). JS needed no change — pinned by the new Test B2 in
  `tests/harmony_trainer_node_test.js`.
* B: the RH-then-LH single leaf uses the "hand may be per-measure" option (ticket 05's
  implementer's choice): `TechniqueParams.hand` accepts a per-measure tuple, group labels split
  per hand. Runs are eighths (13-note cycle ×2 = 26 notes = 3¼ measures, rest-padded to 4, per
  hand → 8 measures/leaf).
* `harmony/technique_data.py` (new, shared with 05/07) encodes the two-octave arpeggio table,
  source-verified (colorinmypiano appendix, R. Kelley chart, M. Denton sheets): white-key
  RH 1231235 / LH 5421421; D/A/E/B-major LH 5321321; black-key roots RH 2124124 / LH 2142142;
  Bb major LH 3213213; Bb minor RH 2312312 / LH 3213212; Gb major & Eb minor keep thumb-on-black
  white-key patterns (Gb LH 5321321). Where charts disagree the majority reading was taken —
  display-only, never graded.
* Leaf fingerprint 381 → 405 (`tests/test_applied_chords.py`, `tests/curriculum_node_test.js`);
  audit artifacts regenerated; `docs/curriculum.md` totals updated (529 nodes).
* Tests: `tests/test_technique_arpeggio.py` (34 cases, A + B).

**Bug fix (2026-08-09, user report):** in bars whose walk repeats a pitch class (the runs carry
three C's: C4/C5/C6), the selection lit EVERY same-pc notehead at once — pressing any C greened
all of them, reading as premature progress. Cause: `buildSelection` maps an expected pc to all
of that pc's noteheads in the measure. Fix: slot-aware selection for scalar ordered walks
(`walkSlotRows`/`buildWalkSelection` in `harmony_trainer.js`) — PITCH_MAP rows are put in
notation order (numeric beat buckets + Verovio note times) and each walked slot selects only
its own notehead; on any shape mismatch (chord stacks, second voices) it falls back to
`buildSelection`. Grading was and stays octave-blind mod-12 by design (a C in any octave
advances a C step) — that is the documented honesty contract, not part of the bug. Pinned by
Tests B3/B4 in `tests/harmony_trainer_node_test.js`.

**Follow-up (2026-08-09, same user report):** the slot fix cured *slot* aliasing but not
*octave* aliasing — both selection builders still keyed every octave of a pitch class onto one
shared id set (`for (var m = pc; m <= 127; m += 12) byMidi.set(m, ids)`), so pressing any C
still lit all three walked C's, and in the trainer's block triads every C on the keyboard lit
the same single notehead. Fix: `selNotesByMidi` now splits its two jobs — noteheads are keyed
octave-exact (`idsByMidiForMeasure`), while each octave keeps a `__ht_target_<pc>` sentinel so
the key colour stays octave-agnostic like the grader. A chord tone played in an unnotated
octave greens the key and lights nothing. Pinned by Test B5 (block) and the reworked B3/B4.

**Follow-up 2 (2026-08-09, user report):** display was then right but the walk still
*advanced* on any octave, because grading was mod-12 everywhere. Ordered walks are execution
drills — the written octave IS the exercise — so they now grade octave-exact, while block
chords keep voicing freedom (a block target asks *which chord*; the ~400-leaf harmony
curriculum is untouched). Scalar walks compare against `walkSlotRows(t)[arpIndex].midi`
(`walkStepMatches`), falling back to mod-12 when the rows cannot be slot-aligned; for a
slot-aligned walk `buildWalkSelection` also drops the cross-octave sentinels, so a
wrong-octave press reads red instead of green-but-inert. Simultaneity steps carry the same
honesty: `LabStepTarget.midis` (new, additive) keeps each step's notated keys —
`_gen_technique` already computed the octave at the `% 12` and threw it away — and
`stepSatisfiedExact` demands them, so a written C4+C5 octave is no longer satisfied by
C3+C4. Tests: B2/B3 reworked, lab Test E reworked, new lab Test H2; H keeps the pc-only
fallback covered.
