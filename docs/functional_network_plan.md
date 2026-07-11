# Functional Degree Network — implementation plan

**New launcher:** `run_functional_network_demo.py`
**Goal:** a practice-first harmonic network for a few major scales (C, G, D, F) in which every
diatonic degree is a real graph node, the graph reveals itself in guided stages, and *playing the
trainer is what drives the graph* — every correct chord lights its node, and finishing a drill
unlocks the next stage.

This graduates the two planned template stubs already audited in
`harmony/network_template.py` (`core_triad_function_network_v1` +
`cadence_resolution_network_v1`) into one concrete, staged experience.

---

## 1. Why the current demo feels static (diagnosis)

* `dominant_diminished_relative_network_v1` has only **key-level** nodes (major, relative minor,
  V7, vii°). A played chord inside a key can at best light the key node — so the score panel
  ("score table") never triggers anything meaningful. `highlightFromTrainerTarget` maps by pitch
  class to the four key-level kinds only (`harmonic_network.js` ~l.643).
* The payload is built once and never changes; the only interactivity is filter toggles.
* Node explanations are static strings; there is no ordering, no goal, no completion.

The fix is not to rewrite the layer but to feed it a **degree-resolution payload** and give the
host a **stage machine** that mutates visibility, emphasis, and completion marks over time.

---

## 2. User experience (the guided journey)

One key "panel" per journey key. Within a panel, degrees are laid out functionally, not by scale
order — a T→PD→D→T cycle the eye can follow:

```
        [ii]──prepares──▶[V]          PD/S column   D column
   [IV]─┘                 │ [vii°]
     ▲                    ▼resolves_to
   [vi]···substitute···▶[I]◀···[iii]   T cluster (I centre, vi/iii orbiting)
```

Stages (each = explanation + graph state + 1-2 launchable drills + an unlock rule):

| # | Stage | Graph state | Drill(s) (all ≤ 12 chords) |
|---|-------|-------------|----------------------------|
| 1 | Meet the scale | Only C panel; 7 degree nodes, no edges; all nodes "unlit" | `full_key` C major (7 chords) |
| 2 | Three jobs | Function-group nodes (T/PD-S/D) fade in + `function_member` edges | `function` I–IV–V–I in C |
| 3 | Tension → home | `resolves_to` edges V→I, vii°→I animate in | `function` V–I; `function` vii°–I in C |
| 4 | The approach chain | `prepares` edges ii→V, IV→V | `function` ii–V–I in C |
| 5 | Substitutes | `tonic_substitute` vi↔I, iii↔I; `deceptive` V→vi | `function` vi–ii–V–I in C |
| 6 | Same triad, new key | G and F panels appear; `shared_triad` edges link C:I≡G:IV≡F:V, C:V≡G:I, C:IV≡F:I … | `horizontal_degree` V across C,G,D,F (4 chords); repeat stage-4 drill in G |
| 7 | Free exploration | Everything visible; all relations toggleable | any node click launches its drill |

The core practice mechanic: **nodes start grey ("unlit"); a correctly played chord permanently
lights its node for the session**. The stage bar shows progress; finishing a stage's drill
(trainer `state().finished`) unlocks the next stage. Progress persists between sessions via
`ProgressStore` (reused from `harmony/curriculum_progress.py`) in `.functional_network_progress.json`.

Live sync (the "score table now has a purpose" part): every 400 ms the host reads
`HarmonyTrainer.currentTarget()` — which already carries `key, mode, roman, degreeNumber,
functionLabel, quality` (`musicxml_builder._target_for`) — and highlights the **exact degree
node**, its function group, and the edge being exercised (e.g. the V→I arrow while the drill sits
on V). This is precise because node ids encode key+degree; no pitch-class guessing needed.

---

## 3. Architecture (additive; nothing existing is rewritten)

### 3.1 `harmony/functional_network_template.py` (new)

Mirror of `network_template.py` with its own closed vocabularies (do **not** widen the v1
template's `NODE_KINDS`/`ALL_RELATIONS` — its `validate()` is a contract other tests rely on).

* `NODE_KINDS = ["degree_triad", "function_group", "key_hub"]`
* `IMPLEMENTED_RELATIONS = ["function_member", "resolves_to", "prepares", "tonic_substitute",
  "deceptive_to", "shared_triad", "fifth_relation", "in_key"]`
  (reserve `modulation_path_to`, `borrowed_from_parallel` as before)
* `LayoutRule` gains `panel_index` support: layout = per-key panel origin (x offset) + functional
  positions inside the panel (T centre-bottom, PD/S left, D right, substitutes orbiting T).
  All x/y still computed in Python — the JS stays layout-free.
* Template factory `functional_degree_network_v1(keys=("C","G","D","F"))`; registered in its own
  `TEMPLATES` registry with `get_template()`.

### 3.2 `harmony/functional_network.py` (new builder)

* Reuses `NetNode`/`NetEdge`/`_launch_entry` **imported from `harmony.harmonic_network`** —
  same `harmony-network/v1` payload schema, so `harmonic_network.js` renders it unmodified.
* Node ids: `fnet:deg:<key>:<degree_index>` (e.g. `fnet:deg:C:4` = V of C),
  `fnet:fn:<key>:<function_label>`, `fnet:key:<key>`.
* All theory derived from `theory.diatonic_harmony.generate_diatonic_triads` (roman,
  `function_label` — `tonic/predominant/mediant/subdominant/dominant` — pitches, explanation).
  Treat `mediant` as a tonic-substitute for grouping, with the explanation saying why.
* Per degree node:
  * `trainer_specs`: one `_launch_entry` per node — degree nodes get a focused `function` drill
    (`function_spec([roman,"I"], f"{roman}–I", "major", [key])` for non-tonic;
    `full_key_spec(key,"major")` for I); function-group nodes get the function-row drill
    (same pattern as `Atlas.function_map`'s cell spec); key hubs get `full_key_spec`.
    Every spec compiles ≤ `MAX_CHORDS_PER_SPEC` because each drill is single-key (3-7 chords).
  * `atlas_refs`: `triad_id/degree_id/function_id` via the existing resolvers.
* Edges per the stage table above. `shared_triad` edges computed by pitch-class-set equality of
  triads across panels (this is what shows a G triad being I in G and V in C simultaneously).
* Public: `build_functional_network(keys) -> HarmonicNetwork` and
  `stage_states(keys) -> List[StageState]` where `StageState = {stage_id, title, explanation,
  visible_node_ids, visible_relations, emphasis_node_ids, drills, unlock}`.
  Keeping stages **in the builder module's sibling** (below) keeps the payload build pure.

### 3.3 `harmony/functional_journey.py` (new stage machine)

* `@dataclass JourneyStage`: id, title, explanation (2-4 sentences of theory), the graph-state
  fields above, `drills: List[HarmonyExerciseSpec]`, `unlock: "finish_any" | "finish_all"`.
* `journey_stages(network) -> List[JourneyStage]` builds the 7 stages from the network (so node
  ids never drift from the builder).
* `JourneyProgress` wraps `ProgressStore`: per-stage started/completed + the set of lit node ids.

### 3.4 `beat_selector/harmonic_network.js` — three additive functions

All guarded so `tests/harmonic_network_node_test.js` and the existing demo are untouched:

1. `setVisibleNodes(ids | null)` — an optional whitelist layered on top of kind filters
   (`null` = no whitelist). This is what makes stages *appear to grow the graph* without
   re-`init()` (single payload, progressive reveal — no flicker, selection survives).
2. `markCompleted(ids)` / `completedIds()` — a persistent per-session set rendered as a
   `node--done` class (CSS: full-saturation fill + subtle ring; unlit default for this payload:
   `node--unlit` when `data.progressive` is true in the payload).
3. `highlightFromDegreeTarget(target)` — exact-id branch:
   `fnet:deg:<tonic(target.key)>:<target.degreeNumber-1>` plus its `fn:` group; also sets
   `edge--sync` on the incident `resolves_to`/`prepares` edge when the *next* target in
   `TARGET_CHORDS` is its resolution (host passes `nextRoman` alongside). Falls back to the
   existing `highlightFromTrainerTarget` when the payload isn't a `fnet` template.

Plus ~10 lines of CSS in `harmonic_network.html` (`node--unlit`, `node--done`, `node--locked`).

### 3.5 `run_functional_network_demo.py` (new launcher)

Same skeleton as `run_harmonic_network_demo.py`:

* **Left:** `HarmonicNetworkView` (reused class or a thin copy) loading the same
  `harmonic_network.html`, initialised once with the full multi-key payload.
* **Right:** `HarmonyTrainerWindow(groups, with_circle=False)` where `groups` =
  `OrderedDict("Stage N — title" -> stage.drills)` + empty `ATLAS_GROUP` for node-click launches.
* **Top strip (Qt):** stage bar — `QLabel` title + explanation, `◀ Stage / Stage ▶` buttons
  (Next disabled until unlocked), and a small progress label ("nodes lit: 9/21").
* Wiring (all existing patterns):
  * stage change → `setVisibleNodes(stage.visible_node_ids)` + `setFilter({relations: ...})`
    + `selectNode(stage.emphasis_node_ids[0])` (right JS panel shows the stage's focal theory)
    + load the stage's first drill via `load_external_spec`.
  * 400 ms sync → `query_current_target` → `highlightFromDegreeTarget`.
  * 400 ms state → `query_trainer_state`; on `finished` → mark the drill's node ids via
    `markCompleted`, record stage completion in `JourneyProgress`, enable **Stage ▶**.
  * node click in JS → `takeLaunch()` poll → `HarmonyExerciseSpec.from_dict` →
    `load_external_spec` (identical to the current demo; every node here is launchable, so no
    reserved-drill guard is needed — keep it anyway as defence-in-depth).

---

## 4. Build order and acceptance checks

1. **Template + builder** (pure Python).
   ✔ deterministic payload; every launch entry compiles ≤ 12 chords; every degree node carries a
   resolvable atlas ref; `shared_triad` edges match pitch-class-set equality across C/G/D/F.
   Unit tests mirror the existing builder tests.
2. **JS additive API.**
   ✔ headless Node test: `setVisibleNodes` filters counts; `markCompleted` survives re-render;
   `highlightFromDegreeTarget({key:"C major", degreeNumber:5})` → `fnet:deg:C:4` primary;
   old payloads still route through the legacy highlight. Existing tests still green.
3. **Journey module.**
   ✔ 7 stages reference only existing node ids/relations; unlock logic unit-tested with a fake
   progress store.
4. **Launcher.**
   ✔ manual: play stage 1 drill end-to-end via MIDI → 7 nodes light one by one, stage 2 unlocks;
   clicking G's V node launches its V–I drill and the score follows.
5. **Docs**: short section in `docs/` + entry in the planned-templates audit marking
   `core_triad_function_network_v1` as superseded/implemented by this.

Estimated size: ~450 lines Python (template+builder), ~150 (journey), ~180 (launcher),
~90 JS + CSS, plus tests — comparable to the harmonic-network layer itself.

---

## 5. Risks and decisions taken

* **Don't widen the v1 template vocabulary** — parallel module avoids breaking
  `HarmonicNetworkTemplate.validate()` consumers. (Alternative rejected: extending `NODE_KINDS`
  in place would force every existing template test to know the new kinds.)
* **Single payload + visibility whitelist** instead of per-stage `init()` re-renders — keeps
  selection/sync stable and makes stage transitions feel animated rather than reloaded.
* **Mediant honesty**: `iii` is labelled `mediant` by the engine; the graph groups it with tonic
  substitutes but the node explanation states the ambiguity (it shares two tones with both I and V).
* **Major only, 4 keys** for v1 (C, G, D, F — no enharmonic seam). Minor panels and modulation
  paths (`modulation_path_to`) are the natural v2, reusing the same stage machine.
* **Seventh chords stay out** — everything here is triad-based, so there are no reserved drills
  anywhere in this graph; every visible node is playable, which is the whole point.
