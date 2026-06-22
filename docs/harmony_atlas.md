# Interactive Harmony Atlas

The **central visual and theoretical navigation layer** for the Harmony Trainer
(and, later, cadence analysis and real-score analysis). The Atlas turns the
whole *invariant* tonal system into an interactive map: scales, scale degrees,
interval layers, chord qualities, harmonic functions, transposition, and
cadences — every element clickable, and every click generating a **playable
Harmony Trainer exercise**.

> The user should never memorise isolated chords — they should see and play the
> complete, invariant harmonic system. The Atlas is that map.

---

## Architecture (single source of truth)

```
theory/diatonic_harmony.py     Pure theory engine — THE contract.
harmony/exercise_spec.py       JSON exercise schema + deterministic compiler.
harmony/musicxml_builder.py    Compiled chords -> MusicXML + runtime payload.
harmony/atlas.py               Pure ontology + views (this module).  <-- Atlas model
beat_selector/atlas.html/.css/.js   The web Atlas UI (QWebEngine).
run_harmony_atlas_demo.py      Combined launcher: Atlas + Harmony Trainer.
```

`harmony/atlas.py` is **pure** (no Qt/Verovio/MIDI) and follows the spec's
implementation rules:

* **Single source of truth.** Nothing re-encodes a chord, quality, Roman
  numeral, function, or interval layer. Every value is derived from
  `theory.diatonic_harmony`; every launchable exercise is a
  `HarmonyExerciseSpec` expanded by the existing compiler. No hard-coded chord
  lists, no duplicated theory tables.
* **Deterministic.** Same inputs → identical nodes, edges, ids, and views.
* **Serialisable.** `Atlas.to_json()` emits the full payload the web UI renders.
* **Extensible.** The node/edge ontology and the reserved `ScoreAnalysis`
  interface are shaped so seventh chords, harmonic/melodic minor, modal harmony,
  and automatic score analysis slot in without redesign.

### The ontology (Part X)

`Atlas` builds a typed graph that *is* the future analysis ontology:

| Node kind | Count | Example id | Clicking launches |
|---|---|---|---|
| `scale` | 24 | `scale:G:major` | `full_key` drill of that key |
| `degree` | 14 | `degree:major:V` | `horizontal_degree` drill (that degree, all keys) |
| `triad` | 168 | `triad:G:major:4` | `full_key` drill of its key (focused on the chord) |
| `quality` | 4 | `quality:diminished` | `quality` recognition drill |
| `layer` | 4 | `layer:M3+m3` | `quality` recognition drill |
| `function` | 9 | `function:major:dominant` | — (grouping node) |
| `cadence` | 10 | `cadence:ii_v_i_major` | `function` (cadence) drill |

Edge relations: `belongs_to`, `transposes_to`, `same_quality`, `same_function`,
`same_interval_layer`, `precedes`, `dominant_of`, `subdominant_of`, `tonic_of`.

> `quality`/`layer` include the non-diatonic **augmented** / `M3+M3` (marked
> `diatonic: false`) so the UI can show it as reserved — it becomes live once a
> mode that produces it (e.g. harmonic minor) is added to the theory engine.

---

## The views (Parts I–VI, IX–XI)

`Atlas.to_json()` returns one payload with every view; the web UI renders them
as tabs. All are derived from the theory engine.

| Part | View | Method | What it shows |
|---|---|---|---|
| I | Global diatonic map | `global_map(mode)` | the invariant degree → quality → layer → function table, plus a per-degree **keyboard view**: the selected degree's root-position triad on a piano (C major / A natural minor), with its interval layer deconstructed into whole/half scale steps that reveal the m3–M3 (minor/major) structure |
| II | Transposition matrix | `transposition_matrix(mode)` | rows = degrees, columns = keys; each cell a concrete triad |
| III | Quality matrix | `quality_matrix(mode)` | every major / minor / diminished triad across keys |
| IV | Function map | `function_map(mode)` | function invariant, chord names change (T / PD / S / D rows) |
| V | Interval-layer map | `interval_layer_map()` | `M3+m3`, `m3+M3`, `m3+m3` (+ reserved `M3+M3`) → recognition drills |
| VI | Cadence map | `cadence_map()` | I–IV–V–I, ii–V–I, vi–ii–V–I, I–V–vi–IV, i–iv–v–i, i–VI–VII–i + types, transposed to all keys |
| IX | Progress | `progress_map(completed_ids)` | completion % by Scales / Triads / Functions / Cadences |
| X | Graph | `graph(include_triads=False)` | the ontology as nodes + typed edges |
| XI | Learning path | `learning_path()` | Scales → Triads → Interval layers → Transposition → Functions → Cadences → Real music |

### Part VII — synchronisation

`Atlas.sync(target)` takes one chord from the trainer payload's `TARGET_CHORDS`
and returns the node ids to highlight (current scale, degree, triad, quality,
interval layer, function) plus the learning-path level. The combined launcher
polls the trainer's current chord and pushes this to the UI, so the Atlas
**follows live playback**.

### Part VIII — real-score mode (reserved)

`ScoreAnalysis` defines the future interface — `analyze_score`,
`extract_harmony`, `extract_functions`, `extract_cadences` — returning
`HarmonyAnnotation` slices. **Nothing is implemented yet**; the methods raise
`NotImplementedError` so callers can program against the contract now.
`Atlas.node_for_annotation()` already maps an annotation onto a triad node, so a
future Bach/Mozart/Chopin analysis can highlight its position in the Atlas.

---

## Running it

```bash
.venv/Scripts/python.exe run_harmony_atlas_demo.py
```

The Atlas (left) and the Harmony Trainer (right) open side by side. Click any
Atlas element → that exercise loads into the trainer and plays via MIDI; while it
runs, the Atlas highlights the current key / degree / triad / quality / layer /
function.

The existing trainer-only launcher is unchanged:

```bash
.venv/Scripts/python.exe run_harmony_trainer_demo.py
```

### How click → launch and sync work

No QWebChannel — the app's existing `runJavaScript` + polling pattern is reused:

* **Click → launch.** Atlas elements push their `HarmonyExerciseSpec` dict onto
  a queue; the host polls `AtlasUI.takeLaunch()` and calls
  `HarmonyTrainerWindow.load_external_spec()`.
* **Sync.** The host polls `HarmonyTrainer.currentTarget()`, runs `Atlas.sync()`,
  and calls `AtlasUI.setSync()` to highlight the matching nodes.

---

## Tests

```bash
# Atlas model layer (determinism, single-source-of-truth, specs, sync, graph)
.venv/Scripts/python.exe -m unittest tests.test_harmony_atlas -v

# whole Python suite (theory + trainer + atlas)
.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -t .

# Atlas UI controller (headless, Node) + trainer controller
node tests/atlas_node_test.js
node tests/harmony_trainer_node_test.js
```

---

## Future work (no redesign required)

* **Seventh chords / inversions** — extend the triad builder; the ontology's
  `triad` nodes and `same_quality` / `same_interval_layer` edges already model
  the relationships.
* **Harmonic / melodic minor, modal harmony** — add a scale-step pattern in the
  theory engine; new degrees/qualities (incl. augmented) flow into the Atlas.
* **Real-score analysis** — implement `ScoreAnalysis`; annotations map onto
  `triad` nodes via `node_for_annotation`, and the same highlight machinery
  lights up the Atlas.
* **Graph-RAG ontology** — `graph(include_triads=True)` is already the typed
  node/edge ontology to export.
