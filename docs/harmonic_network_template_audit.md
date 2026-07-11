# Harmonic Network — Template Audit

> A design/audit pass deciding whether **additional graph templates** are
> justified now, and preparing the template registry to receive them cleanly.
> This is the deliverable for *PATCH 5*. No new graph generation was implemented;
> the candidates below are registered as **metadata-only stubs** in
> `harmony/network_template.py` (`PLANNED_TEMPLATES`).

## 1. How a template works today

The Harmonic Network is **template-driven**. A `HarmonicNetworkTemplate`
(`harmony/network_template.py`) is a pure, serialisable description of:

- the **node classes** (kind + visual class + meaning),
- the **edge classes** (the relationship vocabulary, split implemented vs.
  reserved),
- the **layout rules** (concentric rings + angular placement by fifth index),
- the **generation rules** the builder should run, and
- the **launch rules** (what is launchable vs. reserved).

`harmony/harmonic_network.py` consumes the template and derives every node/edge
from the live theory engine (`theory.diatonic_harmony`) + the Atlas ontology —
**no theory tables are duplicated**. A new topology is added by writing another
template + (where the topology differs) one or more new `generation_rules`, then
registering a factory in `TEMPLATES`.

A template graduates from *planned* to *implemented* by:
1. adding any new node-class kinds to `NODE_KINDS` (+ a `VISUAL_CLASSES` colour),
2. adding any new edge relations to `IMPLEMENTED_RELATIONS`,
3. adding the `generation_rules` it needs (a `_rule_<name>` method on the
   builder) to `GENERATION_RULES`,
4. writing the factory and registering it in `TEMPLATES`, and
5. moving its stub out of `PLANNED_TEMPLATES`.

The builder's current generation rules are **pairwise** (each rule wires node A
to node B). Anything needing ordered, multi-node *paths* (cadence chains,
inversion voice-leading walks) needs a small new edge model first.

## 2. Current template

| id | status | notes |
|----|--------|-------|
| `dominant_diminished_relative_network_v1` | **implemented / shipped** | 48 nodes (12 major + 12 relative-minor + 12 dominant-seventh + 12 leading-tone diminished); resolution arrows V7→I and vii°→I. Triad-based engine, so dominant-seventh nodes carry a **reserved** seventh-chord drill and link to the closest launchable triad drill (the V→I resolution). |

This template is correct and complete for what it claims. The dominant-seventh
honesty caveat (reserved, not launchable) is the only place the topology is
"theoretical".

## 3. Audited candidate templates

### A. `core_triad_function_network_v1` — Core triad / function network
**Priority: HIGH. Recommended as the next template.**

> **STATUS UPDATE — superseded / implemented.** This candidate shipped as
> **`functional_degree_network_v1`** (`harmony/functional_network_template.py`
> + `harmony/functional_network.py`, launcher `run_functional_network_demo.py`;
> see `docs/functional_network.md`). It deliberately lives in a **parallel
> template module** with its own closed vocabularies instead of widening this
> module's `NODE_KINDS`/`ALL_RELATIONS` (the v1 `validate()` is a contract
> other tests rely on), so the §1 graduation recipe was intentionally not
> followed; the stub stays in `PLANNED_TEMPLATES` as inert metadata. The
> shipped network also absorbs the *staged-drill half* of candidate B (V→I,
> ii→V→I, vi→ii→V–I etc. as guided journey stages); B's ordered-path *edge
> model* remains unbuilt and B stays planned.

- **Purpose:** triads only — `I ii iii IV V vi vii°` across all keys, with **no
  seventh-chord theoretical nodes**. Aligns directly with the Global Diatonic
  Map, Transposition Matrix, Quality Matrix and Function Map.
- **Why now:** highest value, lowest risk. *Every* node is a real, launchable
  diatonic triad, so it sheds the reserved-seventh caveat entirely — the most
  "honest" possible network for the current triad-based engine. The builder
  already derives all seven degrees per key from `generate_diatonic_triads`.
- **What it needs:** a `diatonic_degree` node class (+ a colour in
  `VISUAL_CLASSES`), and one new pairwise generation rule
  (`diatonic_degree_edges`) wiring each degree to the tonic / by function. No new
  edge *model* — fits the existing pairwise builder.
- **Dependencies:** `theory.diatonic_harmony`, Atlas degree/function/quality ids.
- **Risk:** low. Mostly additive; reuses existing launch-spec factories.

### B. `cadence_resolution_network_v1` — Cadence resolution network
**Priority: MEDIUM.**

- **Purpose:** a graph of cadence *paths* — `V→I`, `IV→I`, `ii→V→I`,
  `vi→ii→V→I`, `V→vi`, `i→VII→i` — integrating the Voice-leading Lab and the
  Cadence curriculum.
- **Why (partly) now:** each path is already a `HarmonyExerciseSpec` **function
  drill**, so launchables come for free, and the cadence catalogue already exists
  in the curriculum layer.
- **Why not yet:** the cadences are *ordered, multi-node arcs*; the current
  builder only emits pairwise edges. This needs a small **ordered-path edge
  model** (a sequence of node ids per cadence) before it can be drawn faithfully.
- **Dependencies:** `harmony.exercise_spec` function drills, the curriculum
  cadence catalogue, the Lab voice-leading experiments, **+ a new path-edge
  model**.
- **Risk:** medium (new edge model, but bounded).

### C. `inversion_space_network_v1` — Inversion-space network
**Priority: LOW. Defer.**

- **Purpose:** slash-chord / inversion topology (`C`, `C/E`, `C/G`): one chord
  identity, changing bass, voice-leading adjacency between inversions.
- **Why not now:** **blocked.** The trainer's spec compiler and MusicXML builder
  are root-position triad based, so inversion drills are **not launchable** — a
  network of them would be all-reserved, repeating the very honesty problem this
  layer tries to avoid. Inversions are also an explicit project non-goal for now.
- **Dependencies:** inversion support in `harmony.exercise_spec` +
  `harmony.musicxml_builder` (not present).
- **Risk:** high / blocked until the engine grows inversions.

### D. `dominant_diminished_relative_network_v1` (current)
See §2. Shipped and stable; no action.

## 4. Decision

- **Implement now:** only **metadata stubs** for A, B, C in
  `PLANNED_TEMPLATES` (done). They are *not* registered in `TEMPLATES`, so
  `get_template()` keeps resolving only the one buildable template; a planned id
  raises `KeyError` cleanly (covered by `TestPlannedTemplates`).
- **Do not implement now:** any full graph generation. The current patch stays
  focused on fixing/hardening the existing graph (launch bridge, edge styling,
  graph-scoped trainer groups, trainer→node sync).
- **Recommended next step (separate change):** build
  `core_triad_function_network_v1` (candidate A) — it is the only candidate that
  is both high-value and low-risk under the current triad-based engine, and it
  exercises the template registry's extensibility without needing a new edge
  model.

## 5. Implementation priority summary

| candidate | priority | launchable today? | new edge model? | blocker |
|-----------|----------|-------------------|-----------------|---------|
| A. core triad / function | **shipped** as `functional_degree_network_v1` | yes (all triads) | no | none |
| B. cadence resolution | medium (drill half absorbed by A's journey stages) | yes (function drills) | **yes** (ordered paths) | path-edge model |
| C. inversion space | low | **no** | yes (voice-leading) | engine lacks inversions |

## 6. Where the stubs live

`harmony/network_template.py`:
- `PlannedTemplate` dataclass (`template_id`, `title`, `description`,
  `rationale`, `status="planned"`, `priority`, `dependencies`),
- `PLANNED_TEMPLATES` list (the three candidates above),
- `list_planned_templates()` and `list_templates()` (implemented + planned).

These are inert with respect to the running graph — they exist for discovery and
to make the next template a small, well-scoped addition rather than a redesign.
