# Harmonic Network — bidirectional graph ↔ drill mapping

This document describes the implementation of
`HARMONIC_NETWORK_BIDIRECTIONAL_MAPPING_IMPLEMENTATION_PLAN.md`: turning the Harmonic Network from
a mostly static relationship visualisation into a **bidirectional, sequence-aware execution
layer**.

* **Graph → Drill** — a graph node / edge / path selection generates musically valid trainer or
  Lab exercises.
* **Drill → Graph** — every chord (or voicing) in a running drill maps to an explicit graph node
  or an honest temporary proxy, while the whole constellation, order, current position, visited
  path and next step stay visible.

## Three layers (kept strictly separate)

1. **Canonical network** — persistent theory nodes/edges, generated from `theory.diatonic_harmony`
   + Atlas ids + template rules. Never mutated by the current drill.
2. **Drill projection** — a runtime overlay (`DrillGraphProjection`) describing how one exercise
   maps onto the canonical network. May add temporary proxy nodes; contains ordered occurrences
   and sequence-only edges.
3. **Trainer state** — current / visited / expected-next occurrence, correctness, completion.
   Updates the projection without rebuilding the canonical graph.

Terminology: **key anchor** (a key, never a chord) · **chord instance** (a triad node) ·
**occurrence** (one position of a chord in a drill) · **projection proxy** (a temporary overlay
for a chord the template can't draw) · **theory edge** (an asserted harmonic relation) ·
**sequence edge** (a "this is simply the next drill item" overlay).

## Modules

### New (pure, headless — no Qt / JS / MusicXML / I/O, no `Date`/random)

| Module | Responsibility |
|---|---|
| `harmony/harmonic_flow.py` | Shared contracts + controlled vocabularies: `HarmonicStep`, `HarmonicTransition`, `ProjectionNode`, `ProjectionEdge`, `DrillGraphProjection` (+`validate()`/`to_dict`/`from_dict`), `GraphDrillRequest`, `LaunchAction`, `HarmonicPath`, stable-id helpers. |
| `harmony/network_projection.py` | **Drill → Graph.** `project_harmony_exercise`, `project_lab_experiment`, and `project_score_analysis` / `harmonic_step_from_score_slice`. Exact/contextual/approximate mapping, proxy placement, group boundaries, the theory-relation resolver. |
| `harmony/network_launch.py` | **Graph → Drill.** `actions_for_selection(request, network)` and `compile_graph_drill_action(...)`. Node/edge/path action registry, reserved-action honesty, cap enforcement, preview projections. |

### Changed

| Module | Change |
|---|---|
| `harmony/network_template.py` | Extended `NODE_KINDS` / `IMPLEMENTED_RELATIONS` / `VISUAL_CLASSES` / `GENERATION_RULES` + new `NODE_GENERATION_RULES`; `NodeClass` gains `semantic_level` / `entity_role` / `canonical_ref`; template gains `node_generation_rules` / `layout_strategy` / `context_schema`; three new template factories registered. |
| `harmony/harmonic_network.py` | `NetworkBuildContext`; node/edge generation dispatched by rule (legacy path preserved); `NetNode` semantic fields; core / inversion node+edge builders; cadence `HarmonicPath` generation; `HarmonicNetwork.context` / `paths` / lookup helpers; `to_payload()` adds `context` + `paths`. |
| `run_harmonic_network_demo.py` | Sends the projection to the graph on launch, drives the occurrence-level flow layer from the trainer, routes graph/timeline **seek** requests, CLI template selector. |
| `run_harmony_trainer_demo.py` | `seek_to_index(index)` — a thin `window.HarmonyTrainer.goTo(i)` wrapper (in-drill chord seek, distinct from `load_index`). |
| `beat_selector/harmonic_network.{js,html,css}` | Projection ingestion, flow state, occurrence timeline, projection summary, proxy + overlay rendering, host-request queue, drill-layer CSS classes. All additive + headless-safe. |

## Templates

| Template id | Nodes | What it adds |
|---|---|---|
| `dominant_diminished_relative_network_v1` | 48 (12×4) | The legacy reference graph — **unchanged** (48 nodes / 240 edges). Now gains full drill visibility through projection proxies. |
| `core_triad_function_network_v1` | 11 (1 key + 7 triads + 3 functions) | Exact diatonic-triad nodes by function. A `full_key` drill maps to **exact** chord nodes; `Dm` → `hn:triad:C:major:1`, not the key node. Key-local (parameterised by key/mode). |
| `cadence_resolution_network_v1` | 11 + paths | The core graph overlaid with first-class `HarmonicPath` cadence arcs (8 major / 5 minor). Theory edges light up only where the network independently supports them. |
| `inversion_space_network_v1` | 4 (1 identity + 3 voicings) | One chord identity + root/1st/2nd inversion states. Routes to the Music Theory Lab (`compile_lab`) — no renderer duplicated. |
| `transposition_orbit_network_v1` | 1 degree + N instances | An abstract degree orbiting a set of keys as exact per-key instances. A `horizontal_degree` drill maps exact with `transpose_next` overlays — a transposition, never a modulation. |
| `quality_class_network_v1` | 3–4 classes + 7 triads | A key's diatonic triads grouped by chord quality; a `quality` drill enumerates a class (`enumerate_next`, never a progression). |
| `functional_equivalence_network_v1` | 4 | The dominant-function alternatives V (launchable) / V7 (**reserved**) / vii° (launchable), showing the exact triad vs. seventh vs. diminished distinction. |

Genuinely-future reserved stubs remain in `PLANNED_TEMPLATES`: `modulation_path_network_v1`,
`secondary_dominant_network_v1` (both need chromatic/pivot support the engine intentionally lacks).

## Score adapter (Phase 9)

`project_score_analysis(result, network)` adapts a curated `ScoreAnalysisResult` (Score Soul
Graph) to the same `DrillGraphProjection` contract — slices become ordered `score_time`
occurrences. It **reuses** `score_analysis` (`canon_mode`, `diatonic_triad_match`, the slice's
resolved `atlas_refs`) rather than forking a second mapper, and does not destabilise it. The
honesty gate is the curator's **`base_roman`**: a chromatic chord whose triad merely *coincides*
with a diatonic one (e.g. `C7` = V7/IV, triad = C major = I) has `base_roman=None` and is marked
`unsupported`, never claiming the tonic node. No theory edges are inferred between slices (curated
status is preserved, not upgraded); group boundaries fall at key changes.

## Honesty rules (enforced by `validate()` + tested)

* A chord is **never** mapped `exact` to a key node.
* `full_key` / `horizontal_degree` / `quality` drills use `pedagogical_enumeration` /
  `transposition` / `class_enumeration` and **never** assert a theoretical harmonic edge; only
  `harmonic_motion` / `voicing_change` orderings may, and **never across a group boundary**
  (derived from the steps' `group_index`, not just a flag).
* The V triad shown on a V7 node is `approximate`, never `exact`. The natural-minor subtonic VII
  is **not** treated as a dominant.
* Key-relation edges (fifth / relative) compile to a *comparison / transposition*, never a
  progression. Legacy dominant/diminished resolutions into a **minor** key are skipped (the
  natural-minor trainer cannot honestly voice the leading-tone dominant).
* Reserved seventh-chord actions are never launchable.
* Repeated chords produce distinct **occurrences** pointing at one canonical node.

## JS host-facing API (`window.HarmonicNetwork`)

Existing: `init`, `selectNode`, `selectEdge`, `setFilter`, `takeLaunch`,
`highlightFromTrainerTarget`, `exportState`, …

Added (all additive): `setMode`, `setProjection`, `clearProjection`, `updateFlowState`,
`previewLaunch`, `takeHostRequest`, `requestSeek`. The controller stays headless-safe (zero layout
maths; all SVG behind the `createElementNS` guard) and unit-tests under Node
(`tests/harmonic_network_node_test.js`, 135 assertions).

## Running

```
.venv/Scripts/python.exe run_harmonic_network_demo.py                                 # legacy
.venv/Scripts/python.exe run_harmonic_network_demo.py core_triad_function_network_v1  # core
.venv/Scripts/python.exe run_harmonic_network_demo.py cadence_resolution_network_v1   # cadence
.venv/Scripts/python.exe run_harmonic_network_demo.py inversion_space_network_v1      # inversion
```

Launch a drill from a node's launch button: the graph enters *Drill → Graph* mode, shows the whole
constellation + occurrence timeline, and the current/visited/next states follow the trainer.
Clicking a graph node or timeline chip seeks the running drill to that occurrence.

## Tests

* `tests/test_harmonic_flow.py` — contracts, round trips, validation invariants.
* `tests/test_network_projection.py` — Drill → Graph on the legacy template.
* `tests/test_network_templates.py` — the three new templates + builder refactor + cadence paths.
* `tests/test_network_launch.py` — Graph → Drill actions + lab-action specs.
* `tests/test_network_inversion.py` — inversion template + `project_lab_experiment`.
* `tests/test_score_projection.py` — the score adapter (honesty gate, chromatic markers, key
  boundaries, no inferred theory, score-analysis stability).
* `tests/harmonic_network_node_test.js` — JS controller incl. projection/flow/timeline/seek.

## Known limitations / non-goals (unchanged from the plan §22)

No seventh-chord trainer engine, secondary dominants, borrowed chords, tritone subs, chromatic
modulation, pivot detection, harmonic/melodic-minor redesign, counterpoint validation, or
automatic Bach analysis (the score adapter only *adapts* already-curated slices — it never invents
harmonic certainty). `modulation_path` and `secondary_dominant` remain reserved templates until
that chromatic support lands.
