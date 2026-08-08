# 01 — `technique` Lab concept + phrase engine

**What to build:** A new Lab concept `"technique"` that compiles a **multi-measure, single-key
melodic phrase** — the missing shape between `motive` (one measure per key, ≤ 8 notes, degrees
1..14) and everything the ten daily exercises need (scale runs, trill cells stepping through an
octave, arpeggio runs). Plus the `cat:technique` curriculum category with one tracer leaf proving
the whole path: curriculum click → lab compile → render → ordered MIDI grading → progress record.

**Blocked by:** —

**Status:** ready-for-human

- [x] `LabExperimentSpec(concept="technique", render="melody")` validates, compiles, renders, and
      grades end to end in `run_harmony_lab_demo.py`.
- [x] The tracer leaf `ex:tech_warmup_five_finger_c_rh` (below) is launchable from the tree, its
      completion is recorded by `ProgressService`, and the 🎧 echo button does NOT appear for it.
- [x] The Harmonic Scene pane shows the honest refusal for technique leaves (no router change).
- [x] Leaf-count pins updated 380 → 381; audit clean; explanations page present.

**Implementation notes (2026-08-08):** shipped on `fable_refactor`.
`TechniqueParams` (phrase/note_value/hand/fingering/coach) validates as
specced — `"16th"` is refused with a pointer to ticket 02, fingering is
stored + surfaced in the guide text only, and the coach line travels in the
leaf description and every measure's `lab_note` (instruction, never
assessment). `_gen_technique` reuses `_scale_note` verbatim (degree 29 →
C8), emits single-pc `expected_by_beat` (the `_gen_motive` contract), and
puts the `lh` line on staff2 two octaves down. No router change: the
technique refusal reason is pinned in `tests/test_graph_scene_router.py`;
echo ineligibility falls out of `is_echo_eligible` and is pinned too. The
`cat:technique` category sits between Polyphony and the Atlas bridge;
`tests/harmony_lab_midi_test.js` Test E walks the tracer's two-measure
shape through the real controller (wrong note red + no advance, cross-bar
cursor, octave-agnostic close). Leaf fingerprint 380 → 381; the tracked
coverage-audit artifacts were stale at 351 and are regenerated.

## Design

**Spec surface** (`harmony/lab_spec.py`):

* Add `"technique"` to `CONCEPTS`; `_CONCEPT_RENDERS["technique"] = {"melody"}`.
* New `TechniqueParams` + `technique_params(p)` reader, mirroring `MotiveParams`:
  * `phrase: tuple[tuple[int, ...], ...]` — one inner tuple per **measure**, entries are 1-based
    scale degrees. Degree range **1..29** (four octaves; `_scale_note` at `lab.py:251-257`
    already wraps degrees > 7 into higher octaves with no clamp — reuse it verbatim).
  * `note_value: str` — `"quarter" | "eighth"` (ticket 02 adds `"16th"`); validate that every
    measure fits its slot count (4 / 8 / 16) exactly like `_gen_motive`'s slots logic, rest-padding
    short measures.
  * `hand: str` — `"rh" | "lh"`. `rh` emits the line on staff1 (treble, octave 4-centred),
    `lh` on staff2 (bass clef, octave 2-3) with the other staff whole-rest — staff2 moving lines
    are legal today (`lab_musicxml.py:118-125` renders any note list per staff).
  * `fingering: tuple[tuple[str, ...], ...] = ()` — optional, parallel to `phrase`, one label per
    note ("1".."5" or ""). Stored now, **rendered** by ticket 02; until then it may surface in the
    guide text only.
  * `coach: str = ""` — the not-graded gesture instruction (wrist, accents, tempo intent). Must be
    shown in the leaf description / guide panel, per the spec's honesty doctrine.
* `validate()`: non-empty phrase; ≤ `MAX_CHORDS_PER_SPEC` (12) measures; degrees in range;
  fingering shape matches phrase shape when present.

**Generator** (`harmony/lab.py`): `_gen_technique(spec)` registered in the dispatch table
(`lab.py:762`). Per measure: build `LabNote`s via `_scale_note` (quarter/eighth types), pcs list,
`expected_by_beat = {i+1: [pc]}` (single pc per slot — exactly `_gen_motive`'s contract at
`lab.py:640-678`, so the JS ordered walk and `playback_plan.py` both work unchanged), `underlying=None`,
`render="melody"`. Annotation: `motive`-style caret labels are wrong here; use a plain
`lab_note` like "C major scale run, measure 3/8 — fingering 1 2 3 1 …" plus the coach line.
`atlas_scale_id` stamps the key so the Atlas still lights the scale chip.

**Payload:** nothing new — `_lab_target_for` (`lab_musicxml.py:170-220`) already maps
`expected_by_beat` measures to `render:"arpeggio"` ordered targets. Additive fields (fingering,
coach) are safe: harmony_trainer.js ignores unknown target fields by design (`lab_musicxml.py:19-35`).

**Concept registries** (each raises/fails a test if skipped):

* `harmony/lab_explanations.py`: `_CONCEPT_ALIASES` (:52), `_CONCEPT_EXPLANATIONS` (:88) with the
  required fields (:363) — write a short honest theory page ("what technique drills grade and what
  they cannot").
* `harmony/curriculum.py`: branches in `_lab_objective` (:620) and `_lab_keywords` (:649)
  (`test_curriculum.py:169` fails on blank objectives).

**Curriculum** (`harmony/curriculum.py`, assembly area ~:2394):

* `cat("technique", "Piano Technique", ...)` → `lesson("tech_warmup", "Five-finger warm-up")` →
  `fill_lab(group(...), [tracer spec], difficulty="beginner")`.
* Tracer spec: `experiment_id="tech_warmup_five_finger_c_rh"`, C major,
  `phrase=((1,2,3,4,5,4,3,2), (1,))` eighths+final, `hand="rh"`,
  `fingering=(("1","2","3","4","5","4","3","2"), ("1",))`,
  `coach="Even, relaxed tone; let the wrist float."`.
* `harmony/curriculum_audit.py::_CATEGORIES` gains `("technique", "Piano Technique",
  ["cat:technique"], ...)`.

**Tests:** new `tests/test_technique.py` — validation edges (13 measures refused, degree 30
refused, fingering shape mismatch refused), compile shape (measure count, expected_by_beat single
pcs, staff choice per hand), echo ineligibility (`is_echo_eligible` False), scene refusal via
`build_graph_scene` (pin the "no harmonic-graph scene yet" reason in
`tests/test_graph_scene_router.py`). Update pins: `tests/test_applied_chords.py`
`test_leaf_count_fingerprint` 380→381, `tests/curriculum_node_test.js` (extend the running-total
comment), `tests/test_curriculum.py::test_expected_top_level_categories` (+"Piano Technique"),
`tests/test_curriculum_explanations.py` page coverage.

## Grading honesty

Ordered mod-12 walk only: wrong notes are silently ignored (`harmony_trainer.js:559-577` — no
penalty, no reset), octaves are indistinguishable, releases invisible. State this in the concept
explanation; tickets 03/04 widen it.
