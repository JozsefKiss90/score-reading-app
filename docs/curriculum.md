# Music Theory Laboratory — Curriculum Consolidation

> The Music Theory Laboratory is now the **canonical educational layer** of the
> Harmony Trainer ecosystem. The original trainer drills are no longer an ad-hoc
> launcher list; they are organised into one deterministic curriculum ontology.
> The Lab is the **source**; the Harmony Trainer is the **execution engine**.

## 1. Goal

Replace the flat *Concept Catalogue* (Inversions, Voice Leading, Motive,
Polyphony…) with a pedagogical tree rebuilt from the original Harmony-Trainer
curriculum. Every exercise in the whole ecosystem now exists as:

```
CurriculumNode (kind="exercise")
        owns exactly one ↓
   LabExperimentSpec
        compiles to one or more ↓
   HarmonyExerciseSpec
        executed by ↓
   the Harmony Trainer
```

No trainer exercise exists outside a `LabExperimentSpec`. New material is added
only by appending a `LabExperimentSpec` (or a new category builder) — never by
reshaping the node schema or duplicating an exercise definition.

## 2. Architecture

```
                         ┌──────────────────────────────────────────────┐
                         │            theory.diatonic_harmony            │  (single source of truth)
                         └──────────────────────────────────────────────┘
                                  │              │                │
              ┌───────────────────┘              │                └──────────────────┐
              ▼                                   ▼                                   ▼
   harmony.exercise_spec                  harmony.atlas                     harmony.circle_payload
   (HarmonyExerciseSpec,                  (AtlasNode ids, cadence/          (key/degree refs,
    default_exercise_groups =              interval/function factories)      function colours)
    the canonical 102 drills)                     │                                   │
              │  │                                │                                   │
              │  └──────────────┐                 │                                   │
              ▼                 ▼                 │                                   │
   harmony.lab_spec        harmony.lab            │                                   │
   (LabExperimentSpec;     (lab_demo_specs:       │                                   │
    NEW "drill"            inversion / voice-      │                                   │
    passthrough concept)   leading / motive /      │                                   │
              │             polyphony)            │                                   │
              │                 │                 │                                   │
              └────────┬────────┴─────────────────┴───────────────────────────────────┘
                       ▼
        ┌─────────────────────────────────────────────────────────────┐
        │                  harmony.curriculum  (NEW)                    │
        │  CurriculumNode tree · build_curriculum() · search · to_json  │
        │  - wraps the 102 native drills in LabExperimentSpec(drill)    │
        │  - adds the lab concepts + cadence/inversion curriculum grids │
        │  - derives Atlas + Circle refs per node                       │
        └─────────────────────────────────────────────────────────────┘
             │                          │                         │
             ▼                          ▼                         ▼
  harmony.curriculum_          harmony.curriculum_       beat_selector/curriculum.{html,js}  (NEW)
  explanations  (NEW)          progress  (NEW)           - the canonical left-panel tree browser
  lesson/exercise pages        per-leaf + roll-up        - lazy expand · remembered state · search
  + build_curriculum_payload   progress + JSON store     - keyboard nav · lesson & exercise pages
             │                          │                         │
             └──────────────────────────┴─────────────────────────┘
                                        ▼
                     run_harmony_lab_demo.py  (rewired host)
              LEFT: CurriculumView   MIDDLE: HarmonyTrainerWindow (unchanged)
              RIGHT: Atlas / Circle / Cheatsheet / Current Mapping (reused)
              + bidirectional Atlas/Circle ↔ curriculum sync + progress
```

## 3. Data model — `CurriculumNode`

Every node (any `kind`) carries the full pedagogical envelope:

| field | meaning |
|---|---|
| `id`, `parent`, `kind`, `order` | identity + placement (`kind` ∈ curriculum/category/lesson/group/exercise/reserved) |
| `title`, `subtitle`, `description` | display |
| `learning_objective` | what the learner achieves |
| `difficulty` (1–5), `estimated_minutes` | effort |
| `prerequisites`, `recommended_next`, `related` | learning path (node ids) |
| `atlas_nodes`, `circle_nodes` | cross-layer references (Atlas node ids / circle key & degree refs) |
| `theory`, `keywords` | prose + extra search terms |
| `reserved`, `exercise_count`, `completion_state` | status + roll-up |
| `children` | sub-tree (empty for a leaf) |
| `lab_spec` | the **one** `LabExperimentSpec` an exercise leaf owns |

Exercise-leaf payloads additionally carry `echoEligible` (plan A1, ticket 07):
`true` on native `drill`-concept leaves, whose aural **echo twin** (same drill
by ear, one shared mastery record) the workspace offers once the visual leaf
is started — see `docs/harmony_trainer.md` §5c.

## 4. Mapping of the original 102 drills

`harmony.exercise_spec.default_exercise_groups()` yields exactly **102**
`HarmonyExerciseSpec`s across six families. They partition cleanly by drill family
into the curriculum (no duplication, nothing dropped):

| Drill family (source) | Count | Curriculum category › lesson › group |
|---|---:|---|
| `full_key` major block | 12 | Scales › Major scales & triads › Full-key drills (block) |
| `full_key` major arpeggio | 12 | Scales › Major scales & triads › Arpeggios |
| `full_key` minor block | 12 | Scales › Minor scales & triads › Full-key drills (block) |
| `full_key` minor arpeggio | 12 | Scales › Minor scales & triads › Arpeggios |
| `quality` (major mode) | 7 | Chords (Triads) › Triad qualities › Major / Minor / Diminished triads |
| `horizontal_degree` major block | 7 | Degrees & Transposition › Major degree transposition › Block |
| `horizontal_degree` major arpeggio | 7 | Degrees & Transposition › Major degree transposition › Arpeggio |
| `horizontal_degree` minor block | 7 | Degrees & Transposition › Minor degree transposition › Block |
| `horizontal_degree` minor arpeggio | 7 | Degrees & Transposition › Minor degree transposition › Arpeggio |
| `function` major | 11 | Functions › Major functional progressions |
| `function` minor | 8 | Functions › Minor functional progressions |
| **native total** | **102** | |

Plus the synthetic + derived material, each also owned by a `LabExperimentSpec`:

| Source | Count | Category |
|---|---:|---|
| inversion grid (I/ii/IV/V × 12 major + i/iv/v/VII × 12 minor) + 1 worked example | 97 | Inversions |
| ii6–V–I bridge drill (`cad_ii6_V_I_C`, figured predominant — ticket 04 / G4) | 1 | Inversions › ii6 at the cadence |
| voice-leading cadences (one SATB per cadence: 8 demos + 5 generated) | 13 | Cadences (SATB variants) |
| `lab.lab_demo_specs` motive | 2 | Motives |
| `lab.lab_demo_specs` polyphonic | 3 | Polyphonic Harmony |
| block cadences from `_CADENCE_CATALOG` (6 two-chord types + 7 progressions) | 13 | Cadences |
| seventh-chord tracer (ticket 09 / G1a): add-the-7th (2 chunked) + tritone resolution (12 keys) + V7→I (2 chunked) | 16 | Seventh Chords |
| seventh qualities (ticket 10 / G1b): quality drills (7 chunked: Mm7 1 + MM7 2 + mm7 3 + ø7 1) + hear-a-seventh MCQ (3 keys) + ii7–V7–I block/arpeggio (3+3 chunked) | 16 | Seventh Chords |
| V7 figured bass (ticket 11 / G1c): figured-bass inversions (7 · 6/5 · 4/3 · 4/2, 12 keys) + resolution walks (V6/5→I, V4/3→I, V4/2→I6, 12 keys) | 24 | Seventh Chords |
| bass-line dictation (ticket 11 / A1 level 5): roots + ii6 + V7-figure bass lines × C/G/Eb, ear-first (`dictation: "bass"`) | 9 | Inversions › Bass-line dictation |
| **grand total** | **296 exercise leaves** | (~375 nodes total) |

The cadence + voice-leading layers are driven by one canonical `_CADENCE_CATALOG`
(13 cadences) rendered as two variants under the single **Cadences** category —
block drills plus SATB voice-leading (the old separate Voice Leading category
duplicated the catalogue and was merged, plan F7); every cadence maps to an Atlas
cadence node and each variant cross-links its counterpart. The inversion grid uses `LabExperimentSpec(concept="inversion")`
(3 measures: root / first / second) and reuses `inv_C_I` as its C-major-I cell.
Coverage is verified by `harmony.curriculum_audit` (see
`docs/harmony_curriculum_coverage_audit.md`).

Theory-only / bridge / reserved categories (own **no** exercises, so nothing is
duplicated): **Intervals & Interval Layers** (cross-links to the quality drills),
**Interactive Harmony Atlas**, **Circle of Fifths**, **Advanced Topics**
(7ths, harmonic minor, modal, jazz, secondary dominants), **Real Score Analysis
& Reduction**.

## 5. Files

### Created
- `harmony/curriculum.py` — the canonical ontology (`CurriculumNode`,
  `build_curriculum`, search, `to_json`).
- `harmony/curriculum_explanations.py` — generated lesson/exercise pages +
  `build_curriculum_payload`.
- `harmony/curriculum_progress.py` — per-leaf progress + hierarchical roll-up +
  `ProgressStore`.
- `beat_selector/curriculum.html`, `beat_selector/curriculum.js` — the tree
  browser UI (lazy expand, remembered state, search, keyboard nav, lesson &
  exercise pages, progress overlay, Atlas sync strip).
- `tests/test_curriculum.py`, `tests/test_curriculum_explanations.py`,
  `tests/test_curriculum_progress.py`, `tests/curriculum_node_test.js`.
- `docs/curriculum.md` (this file).

### Changed (additive only)
- `harmony/lab_spec.py` — added the **`drill`** passthrough concept (wraps a
  native `HarmonyExerciseSpec`). Existing concepts/behaviour untouched.
- `run_harmony_lab_demo.py` — LEFT panel is now `CurriculumView`; launch routing,
  bidirectional Atlas/Circle ↔ curriculum sync, and progress tracking added. The
  legacy `LabView`/`build_lab_catalog` flat catalogue is retained (still works
  with `beat_selector/harmony_lab.html`).
- `run_harmony_trainer_demo.py` — added the read-only `query_trainer_state`
  helper (sibling of `query_current_target`) for completion detection. The
  trainer's behaviour is unchanged.

## 6. Migration strategy

1. **Additive first.** The `drill` concept and the curriculum modules are new;
   nothing existing is removed. The full suite stays green at every step.
2. **Source of truth, not a copy.** The curriculum reads
   `default_exercise_groups()` / `lab_demo_specs()` / the Atlas factories at build
   time. A new exercise appears in the curriculum automatically once it is added
   to one of those sources, or by adding a new `LabExperimentSpec`.
3. **UI swap, not rewrite.** The host points the LEFT pane at `curriculum.html`.
   The old `harmony_lab.html`/`.js` remain for reference and keep their tests.

## 7. Backward compatibility

- `HarmonyExerciseSpec`, the Trainer, the Atlas, the Circle, the MusicXML builder,
  `ScoreViewBeats`, and MIDI validation are **unchanged**.
- `lab_spec.CONCEPTS` gained `"drill"` additively; every existing lab test passes
  unchanged (the set is not pinned by any test).
- The `drill` passthrough round-trips losslessly: for all 102 native drills,
  `LabExperimentSpec(drill).to_exercise_specs()[0]` compiles to the *same* chord
  stream, render, and mode as the original.
- Every exercise leaf still respects `MAX_CHORDS_PER_SPEC` (the one-page cap).

## 8. Test results

```
Python:  272 passed   (210 pre-existing + 62 new)
JS:      6 suites, 156 assertions   (incl. 34 new curriculum.js checks)
Host:    run_harmony_lab_demo imports cleanly (CurriculumView + HarmonyLabWindow)
```

New invariants under test: determinism (identical build twice), all 102 native
drills reachable exactly once, every leaf owns one cap-respecting `LabExperimentSpec`,
the drill passthrough round-trips, every node has the pedagogical envelope, search
jumps to the right nodes, the progress state machine + roll-up, and module purity
(no PyQt6/Verovio in the pure layers).

## 9. Recommendations for future expansion

The reserved branches already name the seams; each needs only a new
`LabExperimentSpec` (or a new theory mode), not a schema change:

- **Seventh chords** — extend the theory engine with a `seventh` quality and a
  new drill family; the curriculum's *Advanced Topics › Seventh chords* lesson is
  the slot. `V7`'s tritone resolution is a natural voice-leading lesson.
- **Harmonic & melodic minor** — add the modes to `theory._MODE_STEPS`; the
  augmented triad (`III+`) then becomes diatonic and the reserved *Augmented
  triads* group activates automatically.
- **Modal & jazz harmony** — new modes + a `function`-style drill family for
  ii–V–I voicings and extensions.
- **Secondary dominants** — relax `is_diatonic_roman` to accept `V/V`-style
  tokens behind a feature flag; the lab spec already rejects them today as a
  non-goal.
- **Schenkerian reduction & real-score analysis** — the Atlas `ScoreAnalysis`
  contract (`HarmonySlice` / `CadenceSpan` / `PolyphonicTexture`) is already
  shaped; implementing the analysis algorithm lands each structural chord on an
  Atlas node and into the reserved *Reduction* / *Real score analysis* lessons.
```
