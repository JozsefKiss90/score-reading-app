# Harmonic Network Bidirectional Graph–Drill Mapping
## Comprehensive implementation plan for Claude Code

**Target repository:** Score Reading App / Harmony Trainer / Interactive Harmony Atlas / Music Theory Laboratory  
**Primary objective:** turn the Harmonic Network from a mostly static relationship visualisation with one-chord highlighting into a bidirectional, sequence-aware execution layer:

1. **Graph → Drill:** graph nodes, edges, paths, and constellations generate musically valid trainer or laboratory exercises.
2. **Drill → Graph:** every chord or harmonic state in a running drill maps to an explicit graph node or an honest temporary proxy, while the full constellation, order, current position, visited path, and next step remain visible.

This document is an implementation plan. Inspect the live repository before editing and reconcile all file names and APIs with the current checkout.

---

# 1. Architectural diagnosis

## 1.1 The current root problem

The current Harmonic Network mixes different ontological levels:

- `major_key` and `minor_key` nodes represent **keys / tonal centres / scale contexts**.
- `dominant_seventh` and `diminished_triad` nodes represent **chords**.
- A major- or minor-key node launches a `full_key` drill containing all seven diatonic triads.
- A diminished node can launch a concrete `vii°→I` triad drill.
- A dominant-seventh node cannot launch the literal seventh chord because the trainer engine remains triad-based; it exposes a reserved seventh-chord action and a triadic approximation such as `V→I`.

This creates a semantic mismatch:

- selecting the `C` key node does not mean “play the C-major triad”; it currently means “play the complete C-major diatonic field”;
- the running drill contains concrete triads such as `Dm`, `Em`, and `F`, but the legacy graph has no exact chord nodes for most of them;
- the network receives only the trainer’s current target and highlights a best-match node;
- the network does not receive or retain the complete drill sequence, its semantic type, its grouping, its previous/current/next positions, or the difference between theoretical harmonic motion and pedagogical enumeration.

The fix is **not** to reinterpret key nodes as chord nodes. The fix is to introduce explicit semantic levels, exact triad nodes in new templates, and a shared graph–drill projection model.

## 1.2 Current integration gap

The present launcher performs two narrow operations:

- the graph queues a `HarmonyExerciseSpec`, which the host passes to the embedded trainer;
- the host polls the trainer’s current chord and asks the graph to highlight a matching node.

Missing capabilities include:

- no complete drill projection;
- no stable chord-occurrence identity;
- no sequence index or group boundary;
- no distinction between a theoretical graph edge and “this happens to be the next drill item”;
- no graph path preview before launch;
- no graph-node navigation through the running drill;
- no exact representation for non-tonic diatonic triads in the legacy template;
- no actual Lab launch envelope for inversion or voice-leading experiments;
- no reusable mapping contract shared with score analysis.

## 1.3 Required architectural correction

Implement three distinct layers:

1. **Canonical network**
   - persistent theory nodes and theory edges;
   - generated from `theory.diatonic_harmony`, Atlas IDs, and template rules;
   - never mutated by the current drill.

2. **Drill projection**
   - a runtime overlay describing how one exercise maps onto the canonical network;
   - may add temporary proxy nodes when the active template lacks an exact node;
   - contains ordered occurrences and sequence-only edges.

3. **Trainer state**
   - current occurrence, visited occurrences, expected next occurrence, correctness, completion;
   - updates the projection without rebuilding the canonical graph.

This separation is non-negotiable.

---

# 2. Non-negotiable design principles

1. **Do not duplicate theory tables.**  
   Derive scales, triads, Roman numerals, functions, qualities, interval layers, roots, pitch classes, and spellings from `theory.diatonic_harmony` and existing Atlas helpers.

2. **Do not collapse keys and chords into one entity type.**  
   A key node may anchor a chord drill, but it is not the chord occurrence itself.

3. **Do not claim that every drill order is a harmonic progression.**  
   `full_key`, `horizontal_degree`, and `quality` drills use pedagogical or classificatory ordering. Only suitable progression/cadence material receives theoretical motion edges.

4. **Keep theoretical edges separate from runtime sequence edges.**
   - canonical: `resolves_to`, `prepares`, `relative_minor_of`, etc.;
   - runtime overlay: `drill_next`, `transpose_next`, `enumerate_next`, `voicing_next`.

5. **Preserve the current legacy template.**  
   `dominant_diminished_relative_network_v1` must remain available and visually recognisable.

6. **Every drill chord must become visible.**  
   If the active template has no exact canonical chord node, generate an honest temporary proxy node linked to its key context and Atlas triad reference.

7. **Every mapping must declare confidence/status.**  
   Use `exact`, `contextual`, `approximate`, `unmapped`, or `unsupported`. Never silently map a chord to a merely similar node.

8. **Use the Music Theory Lab for concepts the root-position trainer cannot represent.**  
   Inversions and SATB/voice-leading examples already have a Lab pathway. Do not block the inversion template on adding inversion fields to `HarmonyExerciseSpec`.

9. **Keep pure theory/mapping code separate from Qt and JavaScript.**

10. **Keep all output deterministic.**  
    Stable IDs, stable ordering, stable layout, no random graph generation.

---

# 3. Common music-theory thematic groups

Use one controlled vocabulary in both directions.

```python
THEMATIC_GROUPS = {
    "node_identity",
    "tonal_field",
    "functional_neighbourhood",
    "relation_pair",
    "functional_path",
    "transposition_orbit",
    "quality_class",
    "functional_equivalence",
    "inversion_space",
    "modulation_path",
}
```

## 3.1 Group definitions

| ID | Meaning | Graph → Drill | Drill → Graph |
|---|---|---|---|
| `node_identity` | One chord identity or one tonal-centre anchor | play the selected triad; for a key node, generate its tonic triad as a separate chord node | map a one-chord drill to one chord node plus its key-context node |
| `tonal_field` | The seven diatonic triads of one key | key node → complete diatonic field | show seven chord nodes as a constellation; order is pedagogical |
| `functional_neighbourhood` | Tonic, predominant, or dominant family in a key | select a function node/family and enumerate its member triads | group drill chords by shared function |
| `relation_pair` | One explicit theoretical relation between two entities | edge → two-item comparison/resolution exercise | show source, target, and the exact relation when supported |
| `functional_path` | Ordered harmonic motion or cadence | path → progression/cadence drill | show ordered nodes and theoretical motion edges |
| `transposition_orbit` | Same degree/pattern across multiple keys | degree/pattern → orbit around keys | show invariant abstract degree and changing key/chord instances |
| `quality_class` | Major/minor/diminished/augmented class | quality node → all requested examples | show class membership; do not imply progression |
| `functional_equivalence` | Alternative chords sharing a function | e.g. `V`, `V7`, and `vii°` alternatives | show alternatives/branches and common function |
| `inversion_space` | Same chord identity with changing bass/voicing | triad → root, first, second inversion Lab | show same harmonic anchor with three voicing-state nodes |
| `modulation_path` | Movement between key areas | reserved until pivot/chromatic support exists | reserved; do not infer from adjacent key changes |

The first eight groups form the core MVP. `inversion_space` is implemented through the Lab. `modulation_path` remains reserved.

---

# 4. Correct graph semantics for existing drill families

The native trainer’s current drill families require different graph semantics.

| `HarmonyExerciseSpec.drill` | Default thematic group | Sequence semantics | Canonical theoretical edges between consecutive items? |
|---|---|---|---|
| `full_key` | `tonal_field` | `pedagogical_enumeration` | No |
| `horizontal_degree` | `transposition_orbit` | `transposition` | No |
| `quality` | `quality_class` | `class_enumeration` | No |
| `function` | `functional_path` | `harmonic_motion` | Yes, only where the relation is theoretically supported |
| Lab `inversion` | `inversion_space` | `voicing_change` | `inversion_of` / `voice_leads_to`, not harmonic-function change |
| Lab `cadence` / `voice_leading` | `functional_path` | `harmonic_motion` | Yes |
| Lab `polyphonic_harmony` | `functional_path` | `implied_harmony` | Yes, based on the underlying progression |
| real-score slice stream | score-specific | `score_time` | Only when confirmed/curated |

## 4.1 Critical rule

A `full_key` drill such as:

```text
I → ii → iii → IV → V → vi → vii°
```

must not create seven asserted harmonic-resolution edges. It produces:

- seven chord nodes;
- a key anchor;
- sequence overlays labelled `enumerate_next` or `drill_next`;
- theoretical edges only where the canonical network independently contains one.

The same rule applies to quality and transposition drills.

---

# 5. Target architecture

## 5.1 New pure modules

Add:

```text
harmony/harmonic_flow.py
harmony/network_projection.py
harmony/network_launch.py
```

Recommended responsibilities:

### `harmony/harmonic_flow.py`

Own the shared data contracts and controlled vocabularies:

- `HarmonicStep`
- `HarmonicTransition`
- `ProjectionNode`
- `ProjectionEdge`
- `DrillGraphProjection`
- `GraphDrillRequest`
- `LaunchAction`
- thematic-group, semantic-level, mapping-status, and sequence-semantics constants.

No Qt, JavaScript, MusicXML, or file I/O.

### `harmony/network_projection.py`

Own **Drill → Graph**:

- compile a `HarmonyExerciseSpec` to ordered steps;
- adapt a compiled Lab experiment to ordered steps;
- resolve canonical network nodes;
- generate proxy nodes where required;
- derive anchor constellation;
- derive sequence overlays;
- identify supported canonical theory edges;
- split/reset at exercise group boundaries;
- generate a deterministic `DrillGraphProjection`.

### `harmony/network_launch.py`

Own **Graph → Drill**:

- list valid actions for a node, edge, path, or constellation;
- validate a graph selection;
- generate `HarmonyExerciseSpec` or `LabExperimentSpec`;
- generate the corresponding preview projection before launch;
- return a typed `LaunchAction` / launch envelope.

## 5.2 Existing modules to change

```text
harmony/harmonic_network.py
harmony/network_template.py
run_harmonic_network_demo.py
beat_selector/harmonic_network.html
beat_selector/harmonic_network.js
beat_selector/harmonic_network.css        # if styling is currently inline, extraction is optional
run_harmony_trainer_demo.py
beat_selector/harmony_trainer.js
harmony/lab_spec.py                       # reuse request factory; minimal changes only
harmony/score_analysis.py                 # later adapter/reuse, avoid immediate broad refactor
```

Inspect actual repository paths before editing.

---

# 6. Shared data contracts

## 6.1 `HarmonicStep`

Implement a frozen or carefully validated dataclass.

```python
@dataclass(frozen=True)
class HarmonicStep:
    occurrence_id: str
    sequence_index: int
    group_index: int
    index_in_group: int

    source_kind: str              # harmony_exercise | lab | score
    source_id: str                # exercise_id / experiment_id / score_id
    drill_family: str             # full_key | function | inversion | ...

    key_context: str              # "C major"
    tonic: str                    # "C"
    mode: str                     # major | natural_minor
    roman: str
    degree_index: Optional[int]
    chord_symbol: str
    root: str
    quality: str
    function_label: str
    interval_layer: str
    pitch_classes: Tuple[int, ...]
    chord_tones: Tuple[str, ...]

    semantic_group: str
    sequence_semantics: str

    atlas_refs: Tuple[str, ...]
    primary_network_node: Optional[str]
    context_network_nodes: Tuple[str, ...]
    visual_node_id: str           # canonical node or projection proxy

    mapping_type: str             # chord_instance | key_context | class | voicing_state
    mapping_status: str           # exact | contextual | approximate | unmapped | unsupported
    mapping_reason: str

    bass_pitch_class: Optional[int] = None
    inversion: Optional[int] = None
    figured_bass: Optional[str] = None
```

### Stable occurrence IDs

The same canonical node may occur more than once. Do not use the node ID as the occurrence ID.

Use:

```text
occ:{source_id}:{group_index}:{index_in_group}:{sequence_index}
```

A repeated `I` at the beginning and end of `I–IV–V–I` must produce two occurrences pointing to the same canonical triad node.

## 6.2 `HarmonicTransition`

```python
@dataclass(frozen=True)
class HarmonicTransition:
    id: str
    from_occurrence: str
    to_occurrence: str

    sequence_relation: str        # drill_next | transpose_next | enumerate_next | voicing_next
    theory_relation: Optional[str]  # prepares | resolves_to | prolongs | ...
    canonical_edge_id: Optional[str]

    is_group_boundary: bool
    relation_status: str          # exact | inferred | sequence_only | unsupported
    explanation: str
```

### Group-boundary rule

Never create a harmonic-motion edge between the last chord of one transposition group and the first chord of the next.

Example:

```text
ii–V–I in C | ii–V–I in G
```

The transition `C:I → G:ii` is a group boundary, not a harmonic resolution or modulation.

## 6.3 `ProjectionNode`

Temporary visual nodes are required for legacy templates.

```python
@dataclass(frozen=True)
class ProjectionNode:
    id: str
    label: str
    kind: str                    # proxy_triad | occurrence_marker | proxy_voicing
    canonical_ref: Optional[str]
    atlas_refs: Tuple[str, ...]
    anchor_node_id: Optional[str]
    x: float
    y: float
    visual_class: str
    mapping_status: str
    data: Dict
```

Proxy ID format:

```text
overlay:triad:{tonic}:{mode}:{degree_index}
overlay:inversion:{tonic}:{mode}:{degree_index}:{inversion}
```

A proxy is not added to the canonical network. It exists only inside the active projection.

## 6.4 `ProjectionEdge`

```python
@dataclass(frozen=True)
class ProjectionEdge:
    id: str
    source: str
    target: str
    relation: str                # drill_next | transpose_next | enumerate_next | voicing_next
    canonical_edge_id: Optional[str]
    visual_class: str
    explanation: str
```

## 6.5 `DrillGraphProjection`

```python
@dataclass
class DrillGraphProjection:
    schema: str                  # harmony-network-projection/v1
    projection_id: str
    template_id: str

    source_kind: str
    source_id: str
    title: str
    drill_family: str
    semantic_group: str
    sequence_semantics: str

    anchor_node_ids: List[str]
    constellation_node_ids: List[str]
    steps: List[HarmonicStep]
    transitions: List[HarmonicTransition]
    projection_nodes: List[ProjectionNode]
    projection_edges: List[ProjectionEdge]

    warnings: List[str]
    metadata: Dict
```

Required methods:

```python
validate()
to_dict()
from_dict()
step_by_occurrence()
step_at_index()
canonical_nodes()
counts()
```

Validation must assert:

- stable unique occurrence IDs;
- contiguous sequence indices;
- every transition refers to known occurrences;
- no theoretical edge crosses a group boundary;
- every step has a visible node;
- `exact` mappings use a canonical node;
- proxy steps declare a non-exact mapping status;
- unsupported content is clearly marked.

## 6.6 `GraphDrillRequest`

```python
@dataclass(frozen=True)
class GraphDrillRequest:
    schema: str                   # harmony-graph-drill-request/v1
    template_id: str
    interaction_kind: str        # node | edge | path | constellation
    selected_node_ids: Tuple[str, ...]
    selected_edge_ids: Tuple[str, ...]
    selected_path_id: Optional[str]

    thematic_group: str
    key_context: Optional[str]
    mode: Optional[str]
    render: str
    options: Dict
```

## 6.7 `LaunchAction`

Replace ad hoc trainer-only launch dictionaries with a unified additive action model.

```python
@dataclass(frozen=True)
class LaunchAction:
    id: str
    label: str
    target: str                   # trainer | lab
    status: str                   # launchable | reserved | unavailable
    semantic_group: str
    interaction_kind: str

    spec_type: Optional[str]      # harmony_exercise | lab_experiment
    spec: Optional[Dict]
    request: Optional[Dict]
    reason: str
    preview_projection: Optional[Dict]
```

Maintain old `trainerSpecs` and `labSpecs` payload fields during migration, but add `launchActions` and make the UI prefer it.

---

# 7. Semantic levels for canonical nodes

Add additive fields to `NetNode` and `NodeClass`:

```python
semantic_level: str    # key | chord | function | class | voicing | path
entity_role: str       # anchor | instance | family | state | reference
canonical_ref: str
```

Recommended visual semantics:

| Semantic level | Suggested shape |
|---|---|
| key | double-ring circle |
| chord | normal circle |
| function | hexagon |
| quality/class | rounded rectangle |
| voicing/inversion | small satellite circle |
| cadence/path | path badge or pill, not necessarily a graph node |

Do not rely on colour alone. Existing colour classes must remain available.

For the legacy graph:

- `major_key`, `minor_key` → `semantic_level="key"`, `entity_role="anchor"`;
- `dominant_seventh`, `diminished_triad` → `semantic_level="chord"`, `entity_role="instance"`.

This makes the ontological distinction explicit without changing existing IDs.

---

# 8. Mapping precedence and honesty rules

## 8.1 Exact triad mapping

For a compiled `DiatonicTriad`, exact mapping requires:

- same tonic/key context;
- same mode;
- same degree index or exact triad node ID;
- compatible quality;
- compatible spelling or an explicitly accepted enharmonic equivalent.

Preferred ID in the core template:

```text
hn:triad:{tonic}:{mode}:{degree_index}
```

Atlas bridge:

```text
triad:{tonic}:{mode}:{degree_index}
```

## 8.2 Legacy-template mapping

The legacy graph lacks most triad nodes.

Use:

1. create an overlay proxy triad node;
2. anchor it to the correct major/minor key node;
3. include the Atlas triad reference;
4. map the step to the proxy as `contextual`;
5. keep the key node in `context_network_nodes`;
6. never claim the key node itself is the chord instance.

Exceptions:

- an exact diminished-triad node may be used when root, quality, and context agree;
- an actual dominant seventh may map exactly to a dominant-seventh node;
- a plain V triad must not be called an exact `V7` node. It may be `approximate` only if intentionally represented as the closest dominant-family proxy, with a visible reason.

## 8.3 Enharmonic policy

Preserve source spelling in labels. Compare pitch classes only as a fallback.

Mapping statuses:

- `exact`: same semantic entity and context;
- `contextual`: exact chord known through key/Atlas context but missing from active canonical template;
- `approximate`: related but not identical entity, e.g. V triad shown near V7;
- `unmapped`: no reliable target;
- `unsupported`: concept is outside the engine, e.g. unimplemented chromatic/seventh content.

## 8.4 Reuse with score analysis

Do not create a second independent pitch-class-only mapping implementation.

Extract/reuse common helpers where practical:

- mode canonicalisation;
- key tonic parsing;
- diatonic triad matching;
- Atlas reference generation;
- network index construction.

Add later adapters:

```python
harmonic_step_from_score_slice(...)
harmonic_step_from_lab_measure(...)
harmonic_step_from_compiled_chord(...)
```

Avoid a broad score-analysis rewrite in the first implementation phase.

---

# 9. Drill → Graph projection algorithm

Implement a pure entry point:

```python
project_harmony_exercise(
    spec: HarmonyExerciseSpec,
    network: HarmonicNetwork,
    *,
    semantic_override: Optional[Dict] = None,
) -> DrillGraphProjection
```

Algorithm:

1. Validate and compile the spec with `compile_exercise`.
2. Classify the default thematic group from the drill family.
3. Apply a graph-launch semantic override when the exercise was generated from a node/edge/path action.
4. Group compiled chords using `CompiledChord.group`.
5. For each chord:
   - derive key/mode/Roman/degree/root/quality/function/layer/pitches;
   - resolve Atlas refs;
   - resolve an exact canonical node;
   - otherwise create/reuse a projection proxy;
   - create a unique occurrence.
6. Build anchors:
   - key nodes;
   - optional function or class nodes;
   - selected source node/edge/path from Graph → Drill.
7. Build sequence transitions:
   - `full_key` → `enumerate_next`;
   - `horizontal_degree` → `transpose_next`;
   - `quality` → `enumerate_next`;
   - `function` → `drill_next`, plus a canonical theory relation where valid.
8. Reset theoretical transitions at group boundaries.
9. Record warnings for approximations, unsupported seventh content, or missing canonical nodes.
10. Validate and serialise.

## 9.1 Theory-relation resolver

Add a small deterministic resolver:

```python
resolve_theory_relation(prev_step, next_step, network) -> RelationMatch
```

Precedence:

1. exact canonical edge between canonical nodes;
2. template path definition containing the occurrence pair;
3. known diatonic cadence rule already represented in the active template;
4. `None`.

Do not implement a new general-purpose harmonic-inference engine in this task.

## 9.2 Projection for Lab experiments

Implement:

```python
project_lab_experiment(
    spec: LabExperimentSpec,
    network: HarmonicNetwork,
) -> DrillGraphProjection
```

Use `compile_lab(spec)` and each `LabMeasure.annotation`.

For inversion:

- all steps share the same chord anchor;
- each inversion gets a voicing-state node;
- `bass_pitch_class`, `inversion`, and `figured_bass` must be populated;
- overlay transitions use `voicing_next`;
- canonical relations use `inversion_of` and optional `voice_leads_to`.

For cadence/voice-leading:

- map the underlying triads;
- preserve individual-voice details in step metadata;
- use functional path semantics.

For polyphonic harmony:

- map the implied chord per measure/slice;
- mark mapping type as `implied_chord`.

---

# 10. Graph → Drill compiler

Implement:

```python
actions_for_selection(
    request: GraphDrillRequest,
    network: HarmonicNetwork,
) -> List[LaunchAction]
```

and:

```python
compile_graph_drill_action(action_or_request, network) -> LaunchAction
```

## 10.1 Node actions

### Key node

Offer distinct actions:

1. **Play tonic chord**
   - one-item triad exercise;
   - semantic group `node_identity`;
   - key node remains anchor;
   - chord node/proxy is the drill step.

2. **Explore all seven diatonic triads**
   - existing `full_key_spec`;
   - semantic group `tonal_field`.

3. **Tonic family**
   - enumerate I–iii–vi in major, mode-derived equivalents in minor;
   - semantic group `functional_neighbourhood`;
   - explicitly labelled “family enumeration, not a progression”.

4. **Predominant family**
   - enumerate ii–IV or mode-derived members.

5. **Dominant family**
   - enumerate V–vii° or natural-minor equivalents supported by the current engine.

6. **Common cadence paths**
   - V–I, IV–I, V–vi, ii–V–I, etc.;
   - semantic group `functional_path`.

### Triad node

Offer:

- play chord identity;
- play arpeggio;
- play all inversions in the Lab;
- show function-family neighbours;
- launch valid outgoing relation/path drills.

### Dominant-seventh node

Until seventh-chord trainer support exists:

- actual `V7` drill remains reserved;
- triad approximation is explicitly labelled;
- V→I Lab/trainer action remains launchable;
- mapping status must be `approximate` when the literal V triad is displayed on a V7 node.

### Diminished node

Offer:

- single diminished triad identity;
- `vii°→I`;
- dominant-family comparison with V/V7 where available.

### Function-family node

Offer member enumeration and standard routes:

```text
predominant → dominant → tonic
```

The member enumeration itself is not a progression unless the action explicitly creates a route.

### Quality/class node

Offer a quality recognition/class drill. Use the existing cap-respecting quality spec factories.

## 10.2 Edge actions

Classify edge types.

### Harmonic-motion edges

Examples:

- `resolves_to`;
- `leading_tone_to`;
- `prepares`;
- future `prolongs`.

These may compile to a two-item or multi-item function drill when both endpoints resolve to supported diatonic triads in one key context.

### Key-relation edges

Examples:

- `relative_minor_of`;
- `fifth_relation`.

These must compile to a **comparison or transposition** drill, not an asserted chord progression.

### Equivalence edges

Examples:

- `same_function`;
- `same_quality`;
- `same_pitch_class`.

Compile to comparison/classification material with `functional_equivalence` or `quality_class` semantics.

## 10.3 Path actions

Introduce a first-class path model.

```python
@dataclass(frozen=True)
class HarmonicPath:
    id: str
    label: str
    key_context: str
    mode: str
    node_ids: Tuple[str, ...]
    edge_ids: Tuple[str, ...]
    romans: Tuple[str, ...]
    cadence_type: Optional[str]
    semantic_group: str
    launch_action_ids: Tuple[str, ...]
```

Add `paths` to `HarmonicNetwork.to_payload()`.

A selected path must:

- be contiguous;
- stay in one key context unless a future modulation path explicitly permits key changes;
- contain only supported Roman patterns;
- respect `MAX_CHORDS_PER_SPEC`;
- generate both a trainer block action and, where appropriate, a Lab voice-leading action.

## 10.4 Preview before launch

Every launchable action must include a preview projection. The user must be able to see:

- anchor constellation;
- ordered nodes;
- sequence relation type;
- whether edges are theoretical or only pedagogical;
- approximation/unsupported warnings.

Only then launch the trainer/Lab.

---

# 11. Visual layers and UI state

Keep the existing explore-mode relation highlighting. Add independent drill layers.

## 11.1 Required layers

1. **Base network**
   - canonical nodes and canonical theory edges.

2. **Anchor constellation**
   - the source key/node/edge/path and all nodes participating in the exercise.

3. **Projected drill**
   - all canonical or proxy nodes representing drill occurrences;
   - sequence overlay edges.

4. **Visited path**
   - completed occurrences and traversed sequence edges.

5. **Current step**
   - strongest visual focus.

6. **Expected next step**
   - distinct dashed/pulsing halo.

7. **Correctness/status**
   - optional green/red/neutral outer ring tied to trainer/MIDI state.

8. **Selection/hover**
   - existing user exploration state; must not overwrite current-step state.

The first six are mandatory.

## 11.2 CSS/state classes

Recommended:

```text
.is-anchor
.in-projection
.is-visited
.is-current
.is-next
.is-correct
.is-incorrect
.is-proxy
.is-approximate
.is-unsupported
```

Edges:

```text
.edge-theory
.edge-overlay-drill
.edge-overlay-transpose
.edge-overlay-enumerate
.edge-overlay-voicing
.edge-visited
.edge-current
```

## 11.3 Visual grammar

- canonical theory edge: solid;
- active canonical theory edge: thick/animated solid;
- `drill_next`: dashed;
- `transpose_next`: dotted with key-change marker;
- `enumerate_next`: light dashed neutral;
- `voicing_next`: curved satellite edge;
- proxy node: dashed outline and small “contextual” badge;
- approximate mapping: amber warning marker;
- unsupported mapping: grey/red slash marker.

Do not encode all meaning by colour.

## 11.4 Runtime state object in JavaScript

```javascript
state = {
  mode: "explore" | "graph_to_drill" | "drill_to_graph",

  selectedNodeIds: new Set(),
  relatedNodeIds: new Set(),

  projection: null,
  occurrenceById: new Map(),
  occurrencesByVisualNode: new Map(),

  visitedOccurrenceIds: new Set(),
  currentOccurrenceId: null,
  nextOccurrenceId: null,
  correctnessByOccurrence: new Map(),

  selectedPathId: null,
  previewActionId: null,
};
```

## 11.5 Timeline panel

Because one canonical node may occur multiple times, add a compact occurrence timeline below or beside the graph.

Each occurrence chip shows:

- sequence index;
- Roman numeral;
- chord symbol;
- key/group;
- mapping status;
- current/visited/correctness state.

The timeline is the authoritative occurrence-level view; the graph is the canonical-entity view.

---

# 12. Bidirectional runtime navigation

## 12.1 Trainer → Graph

The current trainer query must be extended to return more than a harmonic target.

Add a stable query such as:

```python
trainer.query_current_flow_state(callback)
```

Expected payload:

```json
{
  "sourceId": "ii_v_i_c_g_d",
  "sequenceIndex": 1,
  "groupIndex": 0,
  "indexInGroup": 1,
  "count": 9,
  "group": "ii–V–I in C major",
  "key": "C major",
  "mode": "major",
  "roman": "V",
  "root": "G",
  "quality": "major",
  "status": "active",
  "correct": null
}
```

Keep the current polling architecture unless the repository already has a better event channel. Do not introduce QWebChannel only for this feature.

Update only the runtime state when the index changes. Do not rebuild the network or projection every 400 ms.

## 12.2 Graph → Trainer navigation

In Drill → Graph mode:

- clicking a projected node or timeline occurrence must request a trainer seek;
- if a node has multiple occurrences, show/cycle an occurrence chooser;
- host calls a new trainer method such as:

```python
trainer.seek_to_index(sequence_index)
```

The trainer remains the source of truth for the active index.

Add a JS request queue analogous to the current launch polling:

```javascript
takeSeekRequest()
```

or generalise to:

```javascript
takeHostRequest()
```

with request types:

```text
launch
seek
change_template_context
open_lab
```

## 12.3 Loading a new exercise

When a graph action launches:

1. compile/validate the spec;
2. build the preview projection;
3. send projection to graph;
4. load spec into trainer or Lab;
5. set current occurrence to index 0;
6. retain source selection as anchor;
7. begin runtime state updates.

---

# 13. Network-template refactor

## 13.1 Current builder limitation

The current builder’s node construction assumes all four legacy kinds exist. This cannot support templates with different node classes.

Refactor template-driven construction.

Add additive fields to `HarmonicNetworkTemplate`:

```python
node_generation_rules: List[str] = field(default_factory=list)
layout_strategy: str = "concentric_fifths"
context_schema: Dict[str, Any] = field(default_factory=dict)
```

Default legacy fallback:

```python
node_generation_rules=["legacy_key_dom_dim_nodes"]
```

Add `NetworkBuildContext`:

```python
@dataclass(frozen=True)
class NetworkBuildContext:
    key: str = "C"
    mode: str = "major"
    degree: Optional[str] = None
    quality: Optional[str] = None
    pattern: Tuple[str, ...] = ()
    keys: Tuple[str, ...] = ()
```

Extend:

```python
build_network(template=None, atlas=None, context=None)
```

The payload must include the resolved context.

## 13.2 Rule registries

Use explicit registries instead of a large template-specific conditional block.

```python
NODE_GENERATORS = {
    "legacy_key_dom_dim_nodes": ...,
    "key_center_nodes": ...,
    "diatonic_triad_nodes": ...,
    "function_family_nodes": ...,
    "inversion_state_nodes": ...,
}

EDGE_GENERATORS = {
    "major_circle_by_fifths": ...,
    "relative_minor_edges": ...,
    "diatonic_membership_edges": ...,
    "function_membership_edges": ...,
    "core_function_motion_edges": ...,
    "cadence_path_edges": ...,
    "inversion_edges": ...,
}
```

Every rule must be pure and deterministic.

## 13.3 Vocabulary extensions

Extend canonical node kinds:

```text
key_center
diatonic_triad
function_family
quality_class
degree_class
inversion_state
```

Preserve:

```text
major_key
minor_key
dominant_seventh
diminished_triad
```

Extend canonical relations:

```text
belongs_to_key
member_of_function
prepares
prolongs
substitutes_for
inversion_of
voice_leads_to
```

Do not add runtime sequence relations to canonical `NetEdge` vocabulary. Keep them in `ProjectionEdge`.

---

# 14. New network templates

Implement in this order.

## 14.1 `core_triad_function_network_v1` — highest priority

### Scope

Parameterized, key-local graph. Default context: C major.

### Nodes

- one key-centre anchor;
- seven exact diatonic triad nodes;
- three broad function-family nodes:
  - tonic;
  - predominant;
  - dominant;
- optional quality-class references only if they do not overcrowd the graph.

### Edges

- triad `belongs_to_key` key;
- triad `member_of_function` family;
- standard supported function-motion edges;
- links to Atlas triad/function/quality/layer IDs.

### Layout

- key node at centre;
- function-family regions around it;
- triads clustered in their function region;
- use stable deterministic positions.

### Launch actions

- each triad: node identity, arpeggio, inversion Lab;
- key: full field and function families;
- function node: member enumeration and standard functional routes;
- supported path launch actions.

### Acceptance

- C-major `full_key` produces seven exact chord-node mappings;
- `Dm` maps to `hn:triad:C:major:1`, not to the C key node;
- current/visited/next states work;
- graph click seeks the correct trainer occurrence;
- no `drill_next` edge is presented as a theoretical resolution.

## 14.2 `cadence_resolution_network_v1` — second priority

### Scope

Parameterized by key and mode.

### Path catalogue

Reuse existing curriculum/Atlas cadence definitions. Do not duplicate chord lists.

Initial major paths:

```text
V–I
IV–I
I–V
V–vi
ii–V–I
I–IV–V–I
vi–ii–V–I
I–V–vi–IV
```

Initial natural-minor paths:

```text
v–i
VII–i
iv–v–i
i–iv–v–i
i–VI–VII–i
```

### Model

Prefer reusable exact triad nodes plus first-class `HarmonicPath` definitions rather than duplicating a chord node for each path.

### Launch actions

- block trainer;
- arpeggio trainer where supported;
- voice-leading Lab for cadence/voice-leading concepts.

### Acceptance

- selecting `ii–V–I` previews the exact route;
- launching it keeps the whole route visible;
- active theory edge moves with the trainer;
- path resets correctly when the same progression is transposed to another key.

## 14.3 `inversion_space_network_v1` — third priority

### Correct dependency

The repository already has inversion support through `LabExperimentSpec`, `compile_lab`, and the lab request factory. Do not leave this template blocked on root-position trainer support.

### Scope

Parameterized by key, mode, and degree.

### Nodes

- harmonic identity anchor;
- root-position state;
- first-inversion state;
- second-inversion state.

### Edges

- each state `inversion_of` the anchor;
- adjacent states `voice_leads_to` one another;
- optional bass-motion metadata.

### Launch

Generate a real `LabExperimentSpec` using the existing lab request factory:

```python
{
  "labConcept": "inversion",
  "key": "C major",
  "mode": "major",
  "degree": "I",
  "inversions": [0, 1, 2]
}
```

### Acceptance

- C, C/E, C/G are distinct state nodes;
- they share one chord identity;
- bass notes and figured bass are visible;
- graph clicks navigate among Lab measures;
- the chord function does not change across inversion states.

## 14.4 Post-MVP templates

Plan but do not block the core release:

### `transposition_orbit_network_v1`

- one degree or progression pattern across selected keys;
- orbit order selectable: circle of fifths or trainer order;
- sequence overlay is `transpose_next`;
- no false modulation claim.

### `quality_class_network_v1`

- major/minor/diminished examples across key contexts;
- class node plus exact chord instances;
- sequence overlay is `enumerate_next`.

### `functional_equivalence_network_v1`

- V, V7, vii°, and future substitutes;
- exact distinction between triad, seventh chord, and diminished triad;
- useful after seventh-chord support expands.

Update `PLANNED_TEMPLATES` metadata as templates ship.

---

# 15. Legacy-template integration before new templates

The legacy graph must gain full drill visibility immediately, even before `core_triad_function_network_v1` is selected.

Implement projection proxies:

- selecting C major and launching all triads shows seven temporary chord nodes around the C key anchor;
- exact canonical diminished nodes may be reused where appropriate;
- V triad near G7 remains `approximate`, never exact;
- all proxy nodes show their Atlas references;
- the legacy network’s original geometry remains intact.

This creates a functional migration path:

1. legacy template + projections;
2. exact core triad template;
3. cadence and inversion templates.

---

# 16. Graph UI modes

Add an explicit mode switch.

## 16.1 Explore

Preserve current behaviour:

- select node/edge;
- show related nodes;
- inspect explanation;
- toggle canonical edge layers.

## 16.2 Graph → Drill

Workflow:

1. select node, edge, path, or constellation;
2. show valid thematic actions;
3. preview the resulting projection;
4. display theory-vs-sequence legend;
5. launch trainer or Lab.

Controls:

- key/mode context;
- block/arpeggio/voice-leading render where valid;
- template selector;
- path selector;
- “show only launchable” filter.

## 16.3 Drill → Graph

Workflow:

1. active drill automatically projects;
2. whole constellation stays visible;
3. current/visited/next states update;
4. timeline allows occurrence selection;
5. graph node click seeks trainer;
6. mapping warnings remain visible.

Include summary fields:

```text
exercise title
drill family
thematic group
sequence semantics
current index / total
group
exact / contextual / approximate / unsupported counts
```

---

# 17. Host and launch routing

## 17.1 Generalised launch envelope

The current launcher accepts only a `HarmonyExerciseSpec` dictionary. Generalise it.

Host signal:

```python
launchRequested = pyqtSignal(dict)
```

Payload:

```json
{
  "schema": "harmony-network-launch/v1",
  "target": "trainer",
  "specType": "harmony_exercise",
  "spec": { "...": "..." },
  "projection": { "...": "..." },
  "actionId": "..."
}
```

Lab example:

```json
{
  "schema": "harmony-network-launch/v1",
  "target": "lab",
  "specType": "lab_experiment",
  "spec": { "...": "..." },
  "projection": { "...": "..." },
  "actionId": "..."
}
```

## 17.2 Trainer launch

- validate via `HarmonyExerciseSpec.from_dict`;
- load with existing external-spec API;
- set active projection.

## 17.3 Lab launch

Use the repository’s existing Lab window/controller API. If no reusable embedded Lab loader exists:

- first implement a minimal host method that opens or reuses the Lab window with a validated `LabExperimentSpec`;
- do not reimplement Lab MusicXML in the network;
- keep Lab as the execution engine for inversion/voice-leading.

## 17.4 Reserved actions

Keep defense-in-depth:

- UI disables reserved action;
- Python host rejects reserved/unavailable actions;
- spec validation rejects unsupported drill types.

---

# 18. File-by-file implementation plan

## `harmony/harmonic_flow.py` — new

Implement:

- schemas/constants;
- dataclasses;
- validation;
- serialisation;
- stable ID helpers;
- semantic classification defaults.

Tests must cover round trips and invariants.

## `harmony/network_projection.py` — new

Implement:

- adapters from `CompiledChord`, `LabMeasure`, and later `ScoreHarmonySlice`;
- canonical-node indexes;
- exact/contextual/approximate mapping;
- proxy placement;
- group handling;
- transition construction;
- projection builder.

Proxy placement must be deterministic. Recommended approach:

- position around the anchor node on a small local orbit;
- order by degree index;
- avoid changing the canonical graph layout;
- use a fixed radius and angle rule.

## `harmony/network_launch.py` — new

Implement:

- action registry by semantic level/kind/relation/path;
- GraphDrillRequest validation;
- trainer spec factories;
- Lab request factories;
- preview projection;
- launch envelope.

Reuse:

- `full_key_spec`;
- `function_spec`;
- quality spec factories;
- `spec_from_lab_request` or equivalent existing factory.

## `harmony/network_template.py`

Change:

- add semantic metadata to `NodeClass`;
- add optional `node_generation_rules`, `layout_strategy`, and context schema;
- extend node/relation vocabularies;
- preserve old template validation;
- implement three new template factories;
- register them;
- update planned-template list.

## `harmony/harmonic_network.py`

Refactor:

- introduce `NetworkBuildContext`;
- split legacy hard-coded node construction into a registered node rule;
- register node/edge generators;
- extend `NetNode`;
- add `HarmonicPath`;
- add `paths` and `context` to payload;
- add lookup indexes:
  - by ID;
  - by semantic level;
  - by Atlas triad ref;
  - by key/mode/degree;
  - by pitch class and kind;
- generate launch actions through `network_launch`, not ad hoc node dictionaries;
- retain old payload fields for compatibility.

## `run_harmonic_network_demo.py`

Change:

- support launch envelopes targeting trainer or Lab;
- create projection on every launch;
- send projection to the web UI;
- poll richer trainer flow state;
- support seek requests from graph;
- support template/context rebuild requests;
- cache last state hash to avoid redundant JS updates.

Do not rebuild the network on every timer tick.

## `beat_selector/harmonic_network.js`

Implement:

- mode switch;
- projection ingestion;
- proxy rendering;
- path rendering;
- occurrence timeline;
- visual-layer class application;
- launch preview;
- seek request queue;
- template/context request queue;
- compatibility with legacy v1 payload.

Public API recommendation:

```javascript
init(payload)
setProjection(projection)
clearProjection()
updateFlowState(state)
highlightSelection(nodeId)
previewLaunch(actionId)
takeHostRequest()
```

Keep `highlightFromTrainerTarget` as a compatibility wrapper that creates a minimal one-step state only when no projection exists.

## `beat_selector/harmonic_network.html` / CSS

Add:

- mode selector;
- template selector;
- key/mode/degree context controls;
- action panel;
- projection summary;
- timeline;
- layer legend;
- warning panel.

Preserve current graph/search/edge controls.

## Trainer host and JS

Inspect current files and add:

```python
query_current_flow_state(callback)
seek_to_index(index)
```

The JS controller should expose stable state without changing scoring logic.

Do not duplicate chord metadata already present in the trainer payload.

## `harmony/lab_spec.py`

Prefer no architectural rewrite.

Ensure the network can call the existing request factory for:

- inversion;
- cadence;
- voice-leading;
- polyphonic harmony.

Add only small helper exports if current names are private/inconvenient.

## `harmony/score_analysis.py`

Initial phase:

- leave current score contracts operational;
- optionally route common mapping helpers through `network_projection`;
- add an adapter only after trainer/Lab mapping tests pass.

Do not destabilise the Score Soul Graph during the core network work.

---

# 19. Implementation phases and gates

## Phase 0 — Repository audit

Before editing:

1. inspect:
   - `harmony/harmonic_network.py`;
   - `harmony/network_template.py`;
   - `harmony/exercise_spec.py`;
   - `harmony/atlas.py`;
   - `harmony/lab_spec.py`;
   - `harmony/lab.py`;
   - `run_harmonic_network_demo.py`;
   - trainer host/JS;
   - network HTML/JS;
   - relevant tests;
2. document actual APIs and discrepancies;
3. confirm how trainer current index and external spec loading work;
4. confirm how the Lab accepts an external spec;
5. run the baseline test suite;
6. save baseline results.

**Gate:** no implementation until the audit identifies exact extension points.

## Phase 1 — Shared contracts

Implement `harmonic_flow.py`.

**Gate:**

- headless round-trip tests pass;
- validation catches invalid mapping/transition/group states;
- no UI changes yet.

## Phase 2 — Drill projection on legacy graph

Implement `network_projection.py` and legacy proxy nodes.

**Gate:**

- all four native drill families produce projections;
- every step has a visible node;
- full-key, degree, and quality drills use non-harmonic sequence semantics;
- group boundaries are correct;
- legacy graph remains unchanged without an active projection.

## Phase 3 — Runtime sync and visual layers

Integrate projection into launcher/network JS.

**Gate:**

- full constellation visible;
- current/visited/next update;
- timeline works;
- graph click seeks trainer;
- repeated canonical nodes are handled by occurrence IDs;
- no regression in existing node-selection highlighting.

## Phase 4 — `core_triad_function_network_v1`

Refactor builder and add exact triad/function template.

**Gate:**

- seven exact mappings in C major and selected minor key;
- stable layout;
- exact Atlas refs;
- node/field/function actions preview and launch.

## Phase 5 — Graph → Drill actions

Implement node and edge action compiler.

**Gate:**

- key-node tonic action differs from full-key action;
- key-relation edge produces comparison/transposition semantics;
- resolution edge produces harmonic-path semantics;
- previews display warnings and sequence type;
- reserved seventh action cannot launch.

## Phase 6 — `cadence_resolution_network_v1`

Add path catalogue and trainer/Lab actions.

**Gate:**

- initial major/minor cadence catalogue represented;
- block and voice-leading actions launch;
- active canonical edge follows current transition;
- multi-key drills reset at group boundaries.

## Phase 7 — `inversion_space_network_v1`

Route to Lab.

**Gate:**

- C, C/E, C/G state nodes;
- invariant chord identity;
- bass/figured-bass annotations;
- graph/Lab navigation works;
- no false function change.

## Phase 8 — Additional orbit/class templates

Implement only after core gates pass.

## Phase 9 — Score-analysis adapter

Adapt `ScoreHarmonySlice` streams to the same projection contract.

Do not add automatic harmonic certainty. Preserve curated/heuristic status.

## Phase 10 — Documentation and final audit

Update:

- architecture docs;
- template catalogue;
- run instructions;
- screenshots or payload examples;
- known limitations;
- migration notes.

Run all tests and perform manual MIDI/UI smoke tests.

---

# 20. Test plan

## 20.1 Pure contract tests

Add:

```text
tests/test_harmonic_flow.py
```

Cover:

- serialisation round trip;
- duplicate occurrence rejection;
- invalid transition rejection;
- group-boundary rules;
- mapping-status invariants;
- deterministic IDs.

## 20.2 Projection tests

Add:

```text
tests/test_network_projection.py
```

Required cases:

1. **C-major full-key**
   - seven steps;
   - `tonal_field`;
   - `pedagogical_enumeration`;
   - no asserted theoretical edge for every pair.

2. **ii–V–I in C**
   - three steps;
   - `functional_path`;
   - theory relation on supported pairs.

3. **ii–V–I in C, G, D**
   - nine steps;
   - three groups;
   - no theory edge across groups.

4. **V across twelve major keys**
   - `transposition_orbit`;
   - `transpose_next`;
   - no modulation claim.

5. **Major-quality drill**
   - `quality_class`;
   - `class_enumeration`.

6. **Legacy template**
   - proxy nodes for missing triads;
   - key node used only as context;
   - diminished exact where valid;
   - V triad vs V7 marked approximate.

7. **Core template**
   - exact mapping for all seven triads.

8. **Enharmonic spelling**
   - F#/Gb pitch-class fallback;
   - source spelling preserved;
   - status/reason deterministic.

9. **Repeated chord**
   - separate occurrences;
   - same canonical node.

10. **Natural minor**
   - mode-correct Roman/function mappings.

## 20.3 Graph → Drill tests

Add:

```text
tests/test_network_launch.py
```

Cover:

- key node → tonic identity;
- key node → full field;
- function-family enumeration;
- diminished node → `vii°–I`;
- resolution edge → progression;
- fifth relation → comparison/transposition, not progression;
- cadence path → block and Lab actions;
- unsupported/reserved action rejection;
- cap enforcement.

## 20.4 Template tests

Add:

```text
tests/test_network_templates.py
```

Cover:

- template validation;
- node kinds and semantic levels;
- stable counts;
- stable node IDs;
- path validity;
- context validation;
- no duplicate edges;
- Atlas refs exist.

## 20.5 Lab/inversion integration tests

Cover:

- graph inversion request produces valid `LabExperimentSpec`;
- compile_lab returns three measures;
- chord tones invariant;
- bass changes;
- projection maps one identity plus three voicing states;
- seek indexes align with Lab measure indexes.

## 20.6 JavaScript/UI tests

Use the repository’s existing JS test approach.

Cover:

- projection ingestion;
- layer-class precedence;
- timeline rendering;
- repeated-node occurrence chooser;
- current/next transitions;
- seek request queue;
- launch request queue;
- v1 payload compatibility.

## 20.7 Integration/manual checks

- launch standalone network;
- switch templates;
- select C major;
- preview and launch tonic chord;
- preview and launch all seven triads;
- navigate trainer by graph click;
- verify MIDI correctness does not break;
- launch ii–V–I path;
- launch inversion Lab;
- return to Explore mode;
- verify old edge filters/search still work.

---

# 21. Acceptance matrix

## Problem-root correction

- key nodes are visibly typed as keys;
- chord steps no longer masquerade as key nodes;
- legacy missing chords receive proxies;
- core template provides exact chord nodes.

## Shared thematic groups

- every launch/projection declares one thematic group;
- drill defaults match the semantic table;
- graph-generated overrides are preserved.

## Graph semantics

- theoretical and runtime sequence edges are visually and structurally separate;
- group boundaries prevent false harmonic edges;
- transposition is not presented as modulation.

## Graph → Drill

- node, edge, path, and constellation selections can generate valid exercises where musically supported;
- previews are available;
- actual trainer/Lab launch uses validated native specs.

## Drill → Graph

- every chord/state is visible;
- complete constellation persists;
- current, visited, and next are tracked;
- graph click navigates the exercise;
- repeated chords are handled correctly.

## Intermediate model

- `HarmonicStep`, `HarmonicTransition`, and `DrillGraphProjection` are pure, validated, serialisable, and used by trainer and Lab mappings.

## Visual layers

- all mandatory layers function without destroying original node colours or selection behaviour.

## New templates

- core triad/function;
- cadence resolution;
- inversion space.

## Backward compatibility

- legacy template and existing trainer/Atlas/Lab launchers still run;
- old network payload remains readable;
- dominant-seventh limitations remain honest.

---

# 22. Non-goals for this implementation

Do not implement:

- a full seventh-chord trainer engine;
- secondary dominants;
- borrowed chords;
- tritone substitutions;
- chromatic modulation analysis;
- automatic pivot-chord detection;
- harmonic or melodic minor redesign;
- full counterpoint-rule validation;
- Schenkerian reduction;
- automatic Bach analysis beyond adapting already curated score slices;
- replacement of Atlas or Curriculum;
- wholesale replacement of the current Qt/JavaScript bridge.

Add extension seams, not speculative functionality.

---

# 23. Performance and maintainability constraints

1. Pure projection of a capped trainer exercise should be effectively instantaneous.
2. Cache canonical indexes per network build.
3. Do not rebuild the SVG graph on each trainer timer tick.
4. Send runtime deltas where practical.
5. Keep proxy-node count bounded by the exercise cap.
6. Keep template context local to avoid rendering all 168+ triads at once.
7. Keep public IDs stable and documented.
8. Add docstrings explaining the semantic distinction between:
   - key anchor;
   - chord instance;
   - occurrence;
   - projection proxy;
   - theory edge;
   - sequence edge.

---

# 24. Claude Code execution protocol

Follow this sequence.

## Step 1 — Audit only

Produce:

- current architecture summary;
- exact files/API entry points;
- baseline tests and results;
- discrepancy list;
- final proposed changed/new file list.

Do not edit yet.

## Step 2 — Implement one phase at a time

For each phase:

1. state the phase goal;
2. list files to change;
3. implement pure model/tests first;
4. run targeted tests;
5. run affected regression tests;
6. report results and known limitations;
7. proceed only when the phase gate passes.

## Step 3 — Preserve evidence

At the end, provide:

- changed files;
- new files;
- schema/API changes;
- test commands;
- complete results;
- manual UI checks;
- unresolved limitations;
- screenshots/payload examples if the environment permits;
- migration notes.

## Step 4 — Final architecture audit

Verify explicitly:

- no duplicated theory tables;
- no key/chord semantic collapse;
- no false harmonic edges in enumeration/orbit drills;
- every drill step has a visible representation;
- all mappings expose status/reason;
- legacy template remains functional;
- all three new templates are registered and selectable;
- inversion uses the Lab rather than duplicating its renderer;
- score-analysis interfaces are not destabilised.

---

# 25. Definition of done

The work is complete when the following scenario succeeds:

1. Open the Harmonic Network.
2. Choose `core_triad_function_network_v1`, C major.
3. Select the C-major key node.
4. Preview “all seven diatonic triads”.
5. See seven exact triad nodes grouped by function.
6. Launch the trainer.
7. Watch the graph show the entire constellation, visited nodes, current chord, and next chord.
8. Click a future node and navigate the trainer to that occurrence.
9. Switch to a V–I or ii–V–I cadence path and see actual theoretical edges activate.
10. Switch to a horizontal-degree drill and see `transpose_next`, not a resolution/modulation claim.
11. Switch to the legacy template and still see every drill chord through proxy nodes.
12. Select a triad and launch its inversion Lab.
13. Navigate C, C/E, and C/G as three voicing states of one chord identity.
14. Run the complete test suite with no regressions in Trainer, Atlas, Lab, Curriculum, or Score Soul Graph.

The final result must make the Harmonic Network an executable, bidirectional harmonic map rather than a static graph with a loosely coupled drill panel.
