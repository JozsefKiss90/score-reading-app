# 06 — Exercise 2: arpeggios in groups of four

**What to build:** The video's twist on arpeggios: play them in **groups of four instead of
three** ("1-2-3-4" so the accent — and the thumb — lands on a different chord tone each time).
Two deliverables, matching the host evaluation:

* **A. Trainer** (`run_harmony_trainer_demo.py`): the four-tone accent cell as an opt-in group —
  the only exercise in this effort the trainer's own builder can carry.
* **B. Lab:** two-octave arpeggio *runs* with standard fingerings, as `cat:technique` leaves.

**Blocked by:** (A) — nothing. (B) 01 — phrase engine; 02 — fingering/16ths.

**Status:** ready-for-agent

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

- [ ] A: flag + builder change; both specs appear in the opt-in group; default groups unchanged
      (pinned tests stay green); ordered grading accepts the 4-tone cell.
- [ ] B: 24 leaves launch/render/grade with fingering; accent marks on beat-1 of each group.
- [ ] Leaf-count pins +24; per-category test extended.

## Grading honesty

Accent placement is unobservable (velocity is discarded — `harmony_trainer.js:561` uses it only
as a note-off test); the groups-of-four benefit is embodied in the *notation and fingering*, the
grade remains right-tones-in-order.
