# Piano Technique — spec

Source: `.scratch/10_exercises.md` — transcript of a professional pianist's "10 exercises I play
every day" video (2026-08-08). This effort converts those ten technique exercises into drills the
app can render, play, and grade, hosted by the existing launchers.

## Host evaluation (the ticket-placement question)

Two candidate hosts were evaluated against the actual pipelines:

* **`run_harmony_trainer_demo.py`** — compiles `HarmonyExerciseSpec` through
  `harmony/musicxml_builder.py`. That builder renders exactly two textures: block triads and
  3-note quarter arpeggios (`musicxml_builder.py:263-270`); its input vocabulary is "a chord",
  never "a sequence of notes". **No melody support exists or is reachable from a spec.**
* **`run_harmony_lab_demo.py`** — compiles `LabExperimentSpec` through `harmony/lab.py` +
  `harmony/lab_musicxml.py`. This pipeline already has the generic per-note stream
  (`LabNote`, `LabMeasure.staff1/staff2`), the `melody` render, ordered per-beat grading targets
  (`expected_by_beat`), and the curriculum/progress integration.

**Conclusion: nine of the ten exercises are Lab-pipeline work** (they are melodic / dyadic /
multi-voice textures the trainer's builder cannot express). The one genuine trainer-side fit is
the **arpeggio accent-cell drill (exercise 2)**, which is a one-flag extension of the trainer's
existing arpeggio render plus an opt-in launcher group. Note the nuance: the Lab *reuses*
`HarmonyTrainerWindow` as its middle pane, so the trainer window still executes everything —
"Lab-hosted" means the exercise is owned by a `LabExperimentSpec`, launched from the curriculum
tree, rendered by `build_lab_exercise`, and injected via `load_external_lab`.

| # | Exercise (video) | Host | Machinery | Ticket |
|---|------------------|------|-----------|--------|
| 1 | Scales, "Russian" 4-octave contrary form | Lab | technique phrases; hands-together needs dyad steps | 05 |
| 2 | Arpeggios in groups of four | **Trainer** (cell) + Lab (runs) | 4th arpeggio tone flag + opt-in group; multi-octave runs | 06 |
| 3 | Thumb-under drills | Lab | technique phrases + fingering display | 07 |
| 4 | Parallel thirds | Lab | dyad simultaneity grading | 08 |
| 5 | Wrist ricochet (repeated sixths) | Lab | dyad steps + re-attack rule | 09 |
| 6 | Octave scales | Lab | octave-aware (distinct-count) grading | 10 |
| 7 | Trill drills | Lab | technique phrases | 11 |
| 8 | Rotation (hold + neighbour ×3) | Lab | intra-staff second voice | 12 |
| 9 | Finger independence (hold one, play four) | Lab | intra-staff second voice | 13 |
| 10 | Two-note slurs | Lab | technique phrases + slur/fingering marks | 14 |

## Shared infrastructure (tickets 01–04)

The ten exercises decompose onto four foundations; every exercise ticket lists its blockers.

1. **01 — `technique` Lab concept + phrase engine.** Multi-measure, single-key melodic phrases
   (the motive concept is one-measure-per-key and capped at 8 notes / degrees 1..14 —
   `lab_spec.py:599-605` — so it cannot express a scale run).
2. **02 — notation vocabulary.** 16th notes, per-note fingering, slurs, articulation marks.
   The renderer today emits pitch/duration/voice/staff/accidental/`<chord/>` only; no
   `<technical><fingering>`, `<slur>`, `<articulations>`, `<beam>` anywhere in `harmony/`.
3. **03 — simultaneity grading.** The JS grader walks ONE pitch class per step
   (`harmony_trainer.js:559-577`) and reduces everything mod-12; a dyad or an octave doubling is
   currently ungradable. Adds step-lists with concurrent-hold + distinct-count semantics.
4. **04 — held-note textures.** One voice per staff is hardcoded (`lab_musicxml.py:118-125`);
   rotation/independence need a held note *against* a moving line in the same hand.

## Grading honesty doctrine

Every technique leaf must state, in its description, what is graded and what is coached only.

* **Gradable today:** ordered pitch sequence (note-on walk, mod-12); full-chord pc coverage;
  lowest/highest sounding note (strict-bass / soprano machinery).
* **Gradable after 03:** two-note simultaneities (thirds, sixths); octave doublings
  (distinct-count); repeated-chord re-attacks.
* **Gradable after 04 (v2):** "the held note stayed down" (note-off tracking).
* **Not graded in this effort (coach-text only):** tempo/speed targets, rhythmic evenness,
  dynamics/accents, staccato-vs-legato, wrist/rotation gesture quality. Note-on `velocity` and
  `timestamp` already flow into `afterNoteOn` and are discarded
  (`audio/midi_service.py:22` → `beat_selector/view.py:466` → `harmony_trainer.js:648`), so
  accent/timing grading has its hooks ready — explicitly out of scope here, a future effort.

Playback is free: `TargetTransport` + `playback_plan.py` already sound `expected_by_beat`
(including per-beat pc *lists*), with live bpm + Loop in the trainer's top bar — every phrase
drill doubles as a listen-and-loop practice track.

## Curriculum integration rules

* New top-level category `cat:technique` ("Piano Technique"), one lesson per video exercise.
* Leaf ids `ex:tech_<slug>` via `_exercise_node_from_lab` (`curriculum.py:599-617`); specs built
  by per-exercise factories following the `_inversion_spec` pattern (`curriculum.py:1440-1456`).
* Every content ticket updates: the global leaf-count pins (`tests/test_applied_chords.py`
  `test_leaf_count_fingerprint`, currently 380, and `tests/curriculum_node_test.js` with its
  running-total comment), `tests/test_curriculum.py::test_expected_top_level_categories` (01
  only), `harmony/curriculum_audit.py::_CATEGORIES` (01 only), and adds a per-category count
  test (house convention).
* Scene pane: the router already fails closed for unknown concepts —
  `graph_scene_router.py:265-269` yields "Lab concept 'technique' has no harmonic-graph scene
  yet", same path as `motive`. **No router change**; pin the refusal in
  `tests/test_graph_scene_router.py`.
* Echo drills do not apply (motor drills, not ear drills): `is_echo_eligible` only admits
  `drill`-concept leaves, so the 🎧 button never appears — assert it in 01.
* The trainer's `default_exercise_groups()` 102-drill set is load-bearing; the ticket-06 trainer
  group is appended **only** in `_load_groups` (`run_harmony_trainer_demo.py:593-605`), the
  `GROUP_IDENTIFY` / `GROUP_ECHO` pattern.

## Out of scope

Tempo/rhythm/velocity grading (hooks noted above); tuplets (the ricochet triplet variant is
presented as duple subdivisions with a coach note); hand-crossing exercises; pedal; any change to
the trainer's 102-drill default set; Score Soul.

## Tickets

01 technique concept + phrase engine · 02 notation vocabulary · 03 simultaneity grading ·
04 held-note textures · 05 Russian scales · 06 arpeggio accent cells + runs · 07 thumb-under ·
08 parallel thirds · 09 wrist ricochet · 10 octave scales · 11 trills · 12 rotation ·
13 finger independence · 14 two-note slurs
