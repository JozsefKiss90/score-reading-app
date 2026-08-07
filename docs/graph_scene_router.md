# GraphScene — curriculum-driven, per-exercise harmonic scenes

This document describes the **GraphScene** layer: the correction of the Harmonic Network's
user-visible behaviour from *"one fixed graph, project every drill onto it"* to *"select or
generate a bounded, topic-specific graph scene per exercise."*

It sits on top of the [bidirectional graph ↔ drill mapping](harmonic_network_bidirectional.md):
that work added the infrastructure (templates, projection, honesty rules); this layer adds the
**routing, a unified scene contract, and the runtime that rebuilds the graph per exercise.**

## The problem it fixes

The runtime built one network at startup — the legacy `dominant_diminished_relative_network_v1`
(whole keys / relative minors / dominant sevenths / leading-tone diminished triads) — and projected
**every** drill onto it. Because that ontology cannot represent an arbitrary drill, the projection
degraded:

* a plain **G major triad** landed on the **G7** node;
* the seven diatonic triads became weak overlay **proxies** (Dm barely visible);
* an **Am** chord conflated with the **A-minor key** node (via the legacy pitch-class highlight);
* scale-order enumeration read like a harmonic progression.

The topic-specific graph *generators already existed* (as the 7 templates from the bidirectional
work). The defect was purely **routing + build-context + the missing unified contract + the
build-once runtime.** So this layer is ~70% wiring, ~30% net-new.

The replacement pipeline:

```
active curriculum exercise / Lab experiment / trainer drill
        ↓  classify musical + pedagogical semantics   (graph_scene_router.decide_graph_scene)
        ↓  select a suitable scene generator          (graph_scene_generators)
        ↓  build a bounded, topic-specific scene       (harmony.graph_scene.GraphScene)
        ↓  map every drill occurrence exactly           (occurrence_map)
        ↓  navigate trainer ↔ graph bidirectionally     (setScene / updateOccurrenceState / seek)
```

## Modules

| Module | Responsibility |
|---|---|
| `harmony/graph_scene.py` | The pure, serialisable **contract** — `GraphScene` + `GraphSceneNode/Edge/Path` + `SceneOccurrence` + `SceneLayer`, the closed vocabularies, and `validate()` (the honesty gate). No theory, no I/O. |
| `harmony/graph_scene_generators.py` | The **generators** — one bounded scene per topic, adapting the already-tested `HarmonicNetwork` (canonical topology) + `DrillGraphProjection` (occurrences) into a `GraphScene`. Build-context is derived from the *compiled* spec, so a drill builds a graph for its own key. |
| `harmony/graph_scene_router.py` | The **router** — `decide_graph_scene` / `build_graph_scene`. Classifies from semantics (never a root pitch class), gates on buildability, fails closed. |
| `harmony/curriculum.py` | Additive `graph_scene_type` / `graph_scene_scope` / `graph_scene_options` / `graph_required` on `CurriculumNode` (routing precedence 1). |
| `beat_selector/harmonic_network.{js,html,css}` | The **scene-native renderer** — `setScene` / `clearScene` / `updateOccurrenceState` / `requestSceneSeek`. |

## The contract (`graph_scene.py`)

A `GraphScene` is the single object the UI renders for one learning objective. It carries scene
metadata + `nodes` + `edges` + `paths` + `occurrence_map` + `layer_definitions` +
`supported_actions` + `warnings`.

Node identity is semantic, never a root pitch class. Each `GraphSceneNode` has an `entity_type`:

```
key · triad · seventh · diminished · degree · function · quality · inversion · occurrence · score_slice
```

Each `GraphSceneEdge` carries a **layer**, keeping pedagogical order strictly separate from asserted
harmony:

```
structure · theory · sequence · voice_leading · context
```

### The honesty gate (`GraphScene.validate()`)

The crux invariant, enforced at build time (a mis-generated scene raises `SceneValidationError`
rather than rendering wrong):

* a **chord occurrence never maps onto a `key` node** — `Am` ≠ the A-minor key; a C-major triad ≠
  the C-major key;
* an **`exact`** occurrence points at a real, present, non-proxy node (and not a key node);
* the **`unsupported`** scene carries no occurrences and states why in `warnings`;
* edge endpoints and path nodes must exist; occurrence sequence indices are contiguous `0..N-1`.

## The scene catalogue

| Scene type | Routed from | Topology |
|---|---|---|
| `legacy_key_relation` | Explore / no exercise | The 48-node key-relation graph (fifths / relatives / V7→I / vii°→I). Used **only** here. |
| `diatonic_key_field` | `full_key` | Key anchor + the 7 **exact** diatonic triads by function; enumeration order; theory as a default-off layer. |
| `degree_transposition` | `horizontal_degree` | One invariant **degree** node + N exact per-key instances; `transpose_next`; no motion edges. |
| `triad_quality_class` | `quality` | One **quality** anchor (with interval layer) + the drill's exact same-quality instances; `enumerate_next`; no theory. |
| `functional_progression` | `function`, pattern ≥ 2 | **Bounded** path: one marker per occurrence (repeats → distinct markers of one identity), banded into Predominant / Tonic / Dominant lanes; sequence + theory + transition explanations (common tones, root motion). One local key at a time. |
| `secondary_dominant_path` | An applied token in the pattern, or Lab `applied_chord` | The diatonic row with the chromatic intruder **lifted out of it**: only the diatonic markers link to the key anchor, and the applied chord's `secondary_dominant_of` arrow points at the degree it tonicises (drawn only where `secondary_dominant_network_v1` supports the pair). No other scene may claim an applied chord. |
| `cadence_resolution` | Lab `cadence` (block render) | Source → arrival with the cadence type, reusing the progression layout. |
| `inversion_space` | Lab `inversion` | One chord identity + its inversion voicings. |
| `voice_leading_path` | Lab `voice_leading` (or `cadence` w/ voice-leading render) | Harmonic path **plus** a voice-motion layer (SATB lanes, per-voice motion, common/tendency tones). |
| `polyphonic_harmony_path` | Lab `polyphonic_harmony` | Ordered implied-chord slices + two compact voice lanes; no asserted motion. |
| `score_harmonic_path` | An **explicit score source** only | A real score's slices as ordered markers, grouped by key area; diatonic = exact, chromatic = honest marker. |
| `unsupported` | `motive`, `reduction`, unroutable, failed build | Honest "No suitable harmonic graph" — the trainer keeps running. |

## Routing (`graph_scene_router.py`)

`decide_graph_scene(request)` classifies a `GraphSceneRequest`
(`curriculum_node_id` / `lab_spec` / `exercise_spec` / `source_metadata` / `preferred_scene_type`)
by this precedence — **never** by a chord's root pitch class:

0. an **applied (chromatic) chord** — drill pattern or Lab `applied_chord` — takes
   `secondary_dominant_path` and nothing else; decided *before* metadata so no hint or manual
   override can route it onto a diatonic scene (with no compiled drill behind it, it still fails
   closed);
1. explicit curriculum `graph_scene_type` metadata (only when buildable here);
2. Lab concept — *unless* `concept == "drill"`, the curriculum's native-drill wrapper, which is
   **unwrapped** to its `HarmonyExerciseSpec` and routed by drill family;
3. native drill family (`full_key` / `horizontal_degree` / `quality` / `function`);
4. function pattern length (≥ 2 → progression, 1 → key field);
5. source category;
6. no active exercise → Explore → `legacy_key_relation`;
7. otherwise → **fail closed** to an honest `unsupported` scene (never the legacy graph as a
   catch-all).

**Buildability gate.** `decide` only returns `supported`/`ambiguous` for a scene this router can
actually build (`_buildable`): an exercise scene needs an `exercise_spec`, a Lab scene needs a
`lab_spec`, and `score_harmonic_path`/`unsupported` are never valid override targets. This keeps
`decide` and `build` consistent — a metadata or `preferred_scene_type` override that names a scene
without its input is ignored (falls through to the semantic route) rather than being blessed and
then silently degraded.

`build_graph_scene(request)` dispatches to the generator, is fully `try`-wrapped (a malformed spec
can never crash the host — it degrades to `unsupported`), and surfaces an incompatible manual
override as `status="ambiguous"` (a warning, never a silent mis-map).

## Runtime integration

The graph is chosen **per exercise**, not once at startup.

* **`run_harmonic_network_demo.py`** — no fixed network. `HarmonyTrainerWindow` offers the full
  drill set; a new additive `current_spec()` getter lets the host detect a drill switch. On change:
  `load_graph_scene_for_exercise()` (route → build → `setScene`); the trainer's running position
  drives `updateOccurrenceState`; graph/timeline seeks route back via `seek_to_index`.
* **`run_harmony_lab_demo.py`** (curriculum workspace) — gained a **"Harmonic Scene" tab**.
  `_load_scene(node_id, spec)` routes each selected curriculum exercise; `_drive_scene(state)` pushes
  the occurrence position.
* **Cross-key functional progressions** — one local key at a time. `progression_group_map(spec)`
  gives the group structure; the host rebuilds the local-key scene at each group boundary and
  translates the trainer's global chord index to the shown group's local index. The invariant Roman
  pattern travels in the subtitle/metadata; a key-group change is a **transposition, not a
  modulation**.

### The scene-native JS renderer

`window.HarmonicNetwork` gained an additive, isolated scene path:

```
setScene(scenePayload)          clearScene(reason)
updateOccurrenceState(state)    requestSceneSeek(sequenceIndex)
```

It renders from the scene's own fields (colours by `visualClass`, edges by `layer`, occurrences
current/visited/next, context anchors persistent-secondary), replaces stale nodes on every scene,
and — crucially — runs with **its own state, so the legacy pitch-class highlight never runs in
parallel with an active scene.** The `unsupported` scene shows a prominent "No suitable harmonic
graph" message. The legacy `init` / `setProjection` API is untouched.

### Dual-mode `HarmonicNetworkView`

`HarmonicNetworkView` is **dual-mode** so the separate graph layers keep working:

* **scene mode** (`initial_scene=` + `set_scene` / `update_occurrence_state` / `clear_scene`) — the
  routed hosts;
* **legacy mode** (positional network `payload` + `send_projection` / `update_flow_state` /
  `highlight_from_trainer` + the `launchRequested` signal) — the **Functional Degree Network**
  launcher (which subclasses it) and the **Score Soul Graph** demo, whose graph models are not the
  scene catalogue.

## Score stays score-specific

`build_score_scene(result)` generates a `score_harmonic_path` **from the score's own slices**, with
the curator's honesty preserved (diatonic → exact marker; chromatic → honest `unsupported` marker;
key areas grouped; no asserted motion). The Score Soul Graph mandala remains the primary
score-specific view; this is its network-pane counterpart. The ordinary drill router **cannot**
emit a score scene — no `GraphSceneRequest` field carries a score, and `score_harmonic_path` is not
a router-buildable override target.

## Adversarial audit (independent reviewers)

Two independent reviewers audited musical honesty and routing. Confirmed findings, all fixed with
regression tests:

* **Diminished mistyping** — the generic node adapter typed a diminished diatonic triad (`vii°` /
  `ii°`) as `triad`; it now checks quality → `diminished` + a distinct colour, matching the
  hand-built generators.
* **decide/build mismatch** — `decide` could return `supported` for a scene `build` couldn't
  construct; fixed by the buildability gate + honest fail-closed reasons + full `try`-wrap +
  drill-unwrap fail-closed.
* **Regression fix (found while wiring)** — the Phase-7 `HarmonicNetworkView` rewrite broke the
  Functional and Score launchers that reuse it; resolved by making the view dual-mode.

*Non-issue confirmed:* the default-off theory layer on `diatonic_key_field` is intentional (the
key-field spec explicitly wants theory edges in a separate optional layer).

## Non-goals / unsupported (honest by design)

`motive` (melodic), `reduction` (reserved), borrowed chords and modulation/pivot detection are
**not** implemented. They fail closed with an honest message; none is silently mis-mapped.
Seventh chords and applied dominants have since shipped — the latter with their own scene
(`secondary_dominant_path`, ticket 18), which remains the *only* scene an applied chord may take.

## Tests & evidence

* Python: `tests/test_graph_scene.py` (contract + honesty gate) and `tests/test_graph_scene_router.py`
  (the full routing table, per-scene content, audit regressions, score scene).
* JS: `tests/harmonic_scene_node_test.js` (scene renderer, headless) — the legacy
  `tests/harmonic_network_node_test.js` (135 assertions) is untouched.
* Visual evidence: each scene was rendered from its payload and inspected (C-major field on
  C/Dm/G/Am, V-degree transposition, I–IV–V–I, ii–V–I, quality class, voice leading, polyphony,
  score, legacy Explore).

Full suite: **697 Python + 135 JS-legacy + 6 JS-scene** assertions green; all four launchers import.

## File map

```
harmony/graph_scene.py             contract + honesty gate
harmony/graph_scene_generators.py  the 10 scene generators + build-context derivation
harmony/graph_scene_router.py      decide_graph_scene / build_graph_scene
harmony/curriculum.py              additive graph_scene_* metadata
beat_selector/harmonic_network.js  setScene / clearScene / updateOccurrenceState / requestSceneSeek
run_harmonic_network_demo.py       route-per-exercise host; dual-mode HarmonicNetworkView
run_harmony_lab_demo.py            curriculum workspace "Harmonic Scene" tab
run_score_harmonic_network_demo.py score scene pane
run_harmony_trainer_demo.py        additive current_spec()
tests/test_graph_scene*.py         contract + routing + audit + score tests
tests/harmonic_scene_node_test.js  scene renderer (headless)
```
