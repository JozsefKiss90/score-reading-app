# Chord Progression Foundations — C, G and F major

A **beginner bridge lesson**: one guided page of **12 selectable examples**
that walks the chain

```text
key and scale → scale degree → Roman numeral → chord symbol
→ chord notes → chord quality → harmonic function
→ the same progression transposed to another key
```

It is deliberately **diatonic and root-position only** — no inversions, no
figured bass, no applied chords (`V7/V`), no diminished sevenths, no
modulation. Those live in the later lessons this one links to (Inversions,
Seventh Chords, Advanced Topics); the exclusion is what makes this a first
lesson rather than a summary.

## 1. The four progression families

Each family is a **transposition family**: one Roman pattern shown in C, G
and F major (stable `family_id`s, serialized with every example):

| Group | `family_id` | Pattern | Why it is here |
|---|---|---|---|
| A | `full_key_major` | I–ii–iii–IV–V–vi–vii° | every degree carries a chord; the quality pattern is key-invariant |
| B | `I_IV_V_I` | I–IV–V–I | home → away → tension → home |
| C | `ii_V_I` | ii–V–I | predominant → dominant → tonic |
| D | `ii7_V7_I` | ii7–V7–I | the same path as genuine four-note seventh chords |

Each example is a **short score of its own** (one chord per measure, 3–7
measures) rather than one concatenated score: `MAX_CHORDS_PER_SPEC = 12` is
the single-page Verovio readability cap and stays unchanged — the largest
example (the 7-chord full field) fits comfortably, and twelve short scores
read better than one long one anyway.

## 2. Architecture — presentation model only

`harmony/progression_foundations.py` owns **no theory and no renderer**:

* every example resolves to a canonical `HarmonyExerciseSpec` (a `full_key`
  or `function` drill) wrapped in the curriculum's `drill`-passthrough
  `LabExperimentSpec`, so the score, MIDI playback, validation and Atlas
  sync are the **existing** trainer pipeline, unchanged;
* the chord table is **derived** from `compile_exercise`'s
  `DiatonicTriad` objects — the same objects the MusicXML annotations
  (`_chord_symbol_harmony` / `_roman_numeral_harmony`) and the trainer
  payload targets are built from, so the table and the score cannot drift
  (`tests/test_progression_foundations.py::TestChordTable` pins row ==
  compiled target);
* the acceptance chord lists (C–F–G–C, Gm–C–F, Dm7–G7–C, …) exist **only in
  the tests**; production values always come from the theory engine.

### Canonical reuse (no duplicate leaves)

Five of the 12 examples have an exact existing canonical drill and
**reference** it instead of registering a duplicate leaf:

| Example | Reused drill | Existing leaf |
|---|---|---|
| A1/A2/A3 (full field C/G/F) | `major_fullkey_block_{C,G,F}` | Scales › full-key drills |
| B1 (I–IV–V–I in C) | `atlas_function_I_IV_V_I_major_C` | Cadences catalogue |
| C1 (ii–V–I in C) | `atlas_function_ii_V_I_major_C` | Cadences catalogue |

The other **seven** are new leaves under
`Functions › Chord Progression Foundations` (leaf count 405 → 412):
I–IV–V–I and ii–V–I in G and F use the Atlas `function_spec` factory (the
exact spec an Atlas cadence-map click in those keys generates), and
ii7–V7–I in C/G/F gets `foundations_ii7_V7_I_*` ids because no Atlas
cadence node exists for a seventh pattern. Launching a reused example
records progress on the canonical leaf — one mastery record per drill, the
echo-drill precedent.

## 3. The chord table

One row per score measure, with Position / Key / Scale / Degree / Roman /
Chord symbol / Chord notes / Quality / Function / Chord size / Atlas
mapping / Related lesson. The function column pairs the engine's canonical
label with a beginner gloss ("tonic (home)", "dominant (tension pointing
home)"); accidentals render as ♯/♭/° with the canonical ASCII spellings
kept in separate fields as the fallback.

**Atlas honesty** follows `harmony.curriculum._atlas_refs_for_native`'s
tetrad rule exactly (drift-tested): a triad row claims its scale / degree /
triad / quality / layer / function nodes; a seventh-chord row claims only
the scale, its *base* degree (ii7 is genuinely built on degree 2) and its
function — the Atlas has no seventh-chord nodes, and landing G7 on the
G-triad node would be the `base_roman` dishonesty.

## 4. The page (`beat_selector/foundations.html` / `foundations.js`)

A second **left tab** beside the curriculum browser in
`run_harmony_lab_demo.py` (`FoundationsView`, same `runJavaScript` polling
bridge):

* selecting an example queues its `LabExperimentSpec`
  (`Foundations.takeLaunch()`) → the host launches it through the same
  `_on_curriculum_launch` path as a curriculum click;
* the live sync tick pushes the trainer's current target
  (`Foundations.setCurrent`) → the table highlights the active measure's
  row (`aria-current`), only when the playing drill *is* the selected
  example;
* table-row Atlas chips queue node-id lists
  (`Foundations.takeAtlasSelection()`) → the host highlights them with the
  existing `_active_from_atlas_nodes` → `AtlasView.set_sync` hook;
* **progressive disclosure**: the table opens at Position / Key / Chord
  symbol; a reveal toggle (`aria-expanded`) adds the Roman numerals and the
  explanatory columns. There is no prescribed order and no completion gate
  — it is a reference lesson, not a practice programme;
* each group renders a per-key chord-symbol strip — the visible "same
  pattern in another key" comparison — plus a stays-the-same / changes
  panel (Roman pattern, degrees, functions, quality pattern vs chord
  names, spellings, key signature, absolute pitches);
* accessibility: real `<table>` semantics (`<th scope>`), roving-tabindex
  arrow-key row navigation, `aria-pressed` key buttons, quality/function
  conveyed as text (never colour alone).

## 5. Harmonic Network projection seam

Full network UI integration is not part of this slice, but every example
already projects deterministically: stable ids, canonical Roman tokens,
ordered occurrences and key context flow through the existing
`project_harmony_exercise` seam
(`tests/test_progression_foundations.py::TestNetworkProjection`). On the
default template the D-group's `V7` lands **exactly** on its `hn:dom7:*`
node (ticket 12), while `ii7` has no network node and stays an honest
`overlay:` proxy — a documented limitation, not a triad masquerade; a
future seventh-aware template can pick these up without any change here.

## 6. Files

* `harmony/progression_foundations.py` — the presentation model (examples,
  specs, derived table, payload).
* `beat_selector/foundations.html` / `foundations.js` — the lesson page.
* `run_harmony_lab_demo.py` — `FoundationsView` + the left tab + launch /
  atlas / live-measure wiring.
* `harmony/curriculum.py` — the bridge lesson under `cat:functions`
  (7 leaves, `related` links to the five areas and the five reused leaves).
* `tests/test_progression_foundations.py`, `tests/foundations_node_test.js`.
