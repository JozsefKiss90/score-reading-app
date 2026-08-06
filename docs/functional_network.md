# Functional Degree Network — staged journey layer

**Launcher:** `run_functional_network_demo.py`
**Plan:** `docs/functional_network_plan.md` (implemented in full)
**Supersedes:** the `core_triad_function_network_v1` planned stub (and the
staged-drill half of `cadence_resolution_network_v1`) from
`docs/harmonic_network_template_audit.md`.

A practice-first harmonic network over four major journey keys (**C, G, D,
F** — no enharmonic seam) in which every diatonic degree is a real graph
node, the graph reveals itself in **seven guided stages**, and *playing the
Harmony Trainer is what drives the graph*: every correctly played chord
permanently lights its node, and finishing a stage's drill(s) unlocks the
next stage.

## Module map

| module | role |
|--------|------|
| `harmony/functional_network_template.py` | Schema **mirror** of `network_template.py` with its own closed vocabularies (`NODE_KINDS = degree_triad / function_group / key_hub`; 8 implemented + 2 reserved relations; panel layout data). The v1 vocabularies are deliberately **not widened** — `HarmonicNetworkTemplate.validate()` is a contract other tests rely on. |
| `harmony/functional_network.py` | Builder. Reuses `NetNode`/`NetEdge`/`_launch_entry` from `harmony.harmonic_network`, so the payload shares the **`harmony-network/v1` schema** and `harmonic_network.js` renders it unmodified. All theory from `theory.diatonic_harmony.generate_diatonic_triads`. |
| `harmony/functional_journey.py` | The 7-stage machine (`journey_stages(network)` — ids can never drift from the builder), `drill_node_ids(spec)`, and `JourneyProgress` (wraps `ProgressStore`, file `.functional_network_progress.json`). |
| `run_functional_network_demo.py` | Qt launcher: stage bar (top) + network web UI (left) + embedded `HarmonyTrainerWindow(with_circle=False)` (right); 400 ms sync/state polling. |
| `beat_selector/harmonic_network.js` | Three **additive** host hooks: `setVisibleNodes(ids\|null)` (stage whitelist), `markCompleted(ids)`/`completedIds()` (lit set), `highlightFromDegreeTarget(t)` (exact-id sync with legacy fallback), plus `data.sublabel` second-line rendering and a whitelist-aware viewBox. Legacy payloads behave exactly as before. |

## The graph (44 nodes, 103 edges — pinned in tests)

* One **panel per key**, panels left-to-right in circle-of-fifths order
  (F C G D). Inside a panel degrees sit at *functional* positions: PD/S
  column left (ii, IV), D column right (V, vii°), T cluster bottom-centre
  (I with vi/iii orbiting), function badges (T / PD-S / D) and the key hub
  around them. All x/y computed in Python; the JS stays layout-free.
* Node ids are stable and parseable — the exact-id trainer sync depends on
  them: `fnet:deg:<key>:<degree_index>` (0-based; `fnet:deg:C:4` = V of C),
  `fnet:fn:<key>:<group>`, `fnet:key:<key>`.
* Relations: `function_member` (28), `resolves_to` (8: V→I, vii°→I),
  `prepares` (8: ii→V, IV→V), `tonic_substitute` (8: vi↔I, iii↔I),
  `deceptive_to` (4: V→vi), `in_key` (28, default-off overlay),
  `fifth_relation` (3: F→C→G→D), `shared_triad` (16, **pitch-class-set
  equality across panels** — C:I ≡ G:IV ≡ F:V). Reserved:
  `modulation_path_to`, `borrowed_from_parallel`.
* **Every node is launchable** (the whole graph is triad-based): degree
  nodes drill `<roman>–I` (I drills the full key), function badges drill
  their family (e.g. V–vii°–I), key hubs drill all seven triads. Every spec
  is `_launch_entry`-guarded ≤ `MAX_CHORDS_PER_SPEC`.
* **Mediant honesty:** the engine labels iii `mediant`; the graph groups it
  with the tonic substitutes and the node/group explanations state the
  ambiguity (it shares two tones with both I and V).

## The journey (7 stages)

| # | stage id | reveals | drill(s) | unlock |
|---|----------|---------|----------|--------|
| 1 | `meet_the_scale` | C's 7 degree nodes, no edges | full-key C (7) | finish_any |
| 2 | `three_jobs` | + T/PD-S/D badges, `function_member` | I–IV–V–I in C | finish_any |
| 3 | `tension_home` | + `resolves_to` | V–I; vii°–I in C | **finish_all** |
| 4 | `approach_chain` | + `prepares` | ii–V–I in C | finish_any |
| 5 | `substitutes` | + `tonic_substitute`, `deceptive_to` | vi–ii–V–I in C | finish_any |
| 6 | `same_triad_new_key` | all panels, + `shared_triad`, `fifth_relation` | V across C,G,D,F; ii–V–I in G | **finish_all** |
| 7 | `free_exploration` | whitelist dropped; everything toggleable | node-click launches | — |

Stage state is applied to the JS with **one payload + a visibility
whitelist** (no re-`init()`), so transitions feel animated and selection
survives. The stage bar's **Stage ▶** stays disabled until the stage is
satisfied; `JourneyProgress.resume_stage_index()` reopens the journey where
the player left off.

## Live sync (why the score panel "has a purpose" here)

Every 400 ms the host reads `HarmonyTrainer.currentTarget()` (which carries
`key`/`degreeNumber`) and calls `highlightFromDegreeTarget` — node ids encode
key+degree, so the **exact** degree node and its function group light up, no
pitch-class guessing. The host also passes the *next* compiled chord
(`nextKey`/`nextDegreeNumber`, from the same `compile_exercise` the trainer
used), which makes the exercised `resolves_to`/`prepares` arrow light while
the drill sits on the current chord. A chord's node lights immediately when
the target advances one step past it **and** the host observed
`state().completed` for that chord — the gate matters because the trainer's
chord cards are clickable (`goTo`), and clicking through a drill must light
nothing. On `state().finished` (which only the MIDI path can set) the whole
drill's nodes are lit (`drill_node_ids`), the drill is recorded against the
spec that was on screen when the poll was issued, and the stage unlock is
re-evaluated.

## The v2 minor journey (ticket 15 / plan G2c)

`functional_degree_network_minor_v2` registers **through the registry seam**
(`TEMPLATES`) as a new template — the frozen v1 vocabulary is reused, never
widened, and the v1 template is untouched. Launch with
`run_functional_network_demo.py --minor` (or `--template <id>`).

* **Four minor panels — A, E, D, B** (the relative minors of the v1 journey;
  fifths chain D→A→E→B). Panel chords come from **harmonic minor** (ticket
  13 / G2a): i, ii°, III+, iv, **V (the real major-triad dominant)**, VI,
  vii°. Function groups mirror major exactly: T = {i, III+, VI},
  PD/S = {ii°, iv}, D = {V, vii°}.
* **Minor node ids suffix the key token with `m`** — `fnet:deg:Am:4` is the
  V of A minor — so minor ids are disjoint from every major id (both
  journeys share `.functional_network_progress.json`) and
  `highlightFromDegreeTarget` rebuilds them from `target.key` +
  `target.mode`. The JS gates on `template.mode`: a minor target clears the
  sync on the major graph and vice versa.
* **Ref honesty** (the G2a natural-minor-twin precedent): the KEY context is
  claimed natural minor (`scale:A:natural_minor`, `key:A:natural_minor`);
  chord-level Atlas nodes only on an exact pitch match (i / ii° / iv / VI);
  the raised chords III+ / V / vii° claim only their quality class. Only 4
  `shared_triad` edges survive across panels (Am, Dm, Em, C#°) vs major's
  16 — harmonic minor's altered chords are panel-unique, and stage 6 says so.
* **Stages mirror the major machine** one for one (same reveal order, same
  unlock rules), with `_minor`-suffixed stage ids and harmonic-minor drills:
  full-key → i–iv–V–i → V–i + vii°–i (**the real minor V story**) →
  ii°–V–i → VI–ii°–V–i → V across A,E,D,B + ii°–V–i in E → free exploration.
* Fingerprint: 44 nodes, **91 edges** (pinned in
  `tests/test_functional_minor.py`).

## Tests

* `tests/test_functional_network.py` — template validation, 44/103
  fingerprint, shared-triad pc-set honesty, Atlas ref resolution, cap
  guard, mediant honesty, payload shape (`progressive` flag), v1 network
  untouched.
* `tests/test_functional_journey.py` — stage table, monotonic reveal,
  unlock/resume logic against a real temp `ProgressStore`, `drill_node_ids`,
  lit-node namespace guards.
* `tests/test_functional_minor.py` — the v2 minor journey: registry seam,
  `m`-suffixed id disjointness, the real minor V, ref honesty, 44/91
  fingerprint, harmonic-minor drills, `_minor` stage ids, minor
  `drill_node_ids`.
* `tests/functional_network_node_test.js` — headless JS: whitelist
  filtering, `markCompleted` across re-renders, unlit/done classes, exact-id
  highlight + exercised edge, **legacy-payload fallback**, launch queue, and
  the minor payload (exact minor ids, the mode gate both ways).

Run everything:

```
.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -t .
node tests/functional_network_node_test.js
node tests/harmonic_network_node_test.js
```

## v2 candidates

~~Minor panels~~ (shipped: `functional_degree_network_minor_v2`, above).
Still open: `modulation_path_to` arcs reusing the same stage machine;
`borrowed_from_parallel` overlays; per-chord accuracy shading of lit nodes.
