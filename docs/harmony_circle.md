# Interactive Circle of Fifths

The first visual module of the future [Interactive Harmony Atlas](harmony_atlas.md):
an interactive **navigation, explanation, and exercise-launching** layer for the
Harmony Trainer, shown as a panel inside the trainer window.

It is *not* decorative — clicking a key, a triad, or a shortcut launches a real
Harmony Trainer exercise, and during play the chart follows the live target
chord.

> Scope: **diatonic triads only** (major + natural minor). Seventh chords,
> secondary dominants, and the diminished network are *not* implemented yet, but
> the data structure reserves their relationship types (see [Extension](#extension-points)).

---

## Architecture

```
theory/diatonic_harmony.py      Pure theory engine — single source of truth.
harmony/exercise_spec.py        HarmonyExerciseSpec + compiler.
harmony/circle_payload.py       Circle payload generator + click->spec bridge.   <-- Python data
beat_selector/harmony_circle.js Interactive SVG renderer (window.HarmonyCircle).  <-- JS rendering
beat_selector/harmony_circle.html  Host page for the panel.
run_harmony_trainer_demo.py     CircleView panel + splitter + bridge + sync.
```

Python builds the data; JS only renders. Nothing re-derives theory: every label,
chord, quality, interval layer, function, scale, and key signature comes from
`generate_diatonic_triads` / `generate_scale` / `key_signature_fifths`, and the
circle *order* is computed from the circle of fifths (not hard-coded).

### Payload (`build_circle_payload()`, schema `harmony-circle/v1`)

```jsonc
{
  "schema": "harmony-circle/v1",
  "majorKeys": [ { "key":"C", "mode":"major", "relativeMinor":"A", "fifths":0,
                   "scale":["C","D","E","F","G","A","B"],
                   "triads":[ { "degree":"I","degreeNumber":1,"chordSymbol":"C","root":"C",
                                "quality":"major","tones":["C","E","G"],
                                "intervalLayer":"M3+m3","functionLabel":"tonic","functionClass":"T" }, … ] }, … ],
  "minorKeys": [ { "key":"A","mode":"natural_minor","relativeMajor":"C", … } ],
  "circleOrderMajor": ["C","G","D","A","E","B","Gb","Db","Ab","Eb","Bb","F"],
  "circleOrderMinor": ["A","E","B","F#","C#","G#","Eb","Bb","F","C","G","D"],
  "cheatsheet": { "majorPattern":[…], "minorPattern":[…], "intervalLayers":[…], "functionClasses":[…] },
  "relations": ["relative_minor_of", "dominant_of", …]
}
```

* `functionLabel` is the engine's label (`tonic`/`predominant`/`mediant`/
  `subdominant`/`dominant`) — it matches the trainer payload, so sync is direct.
* `functionClass` is the coarse colour bucket `T` / `S` / `D` (the only
  presentational grouping, defined once).

### Click → exercise bridge (`spec_from_circle_request()`)

The circle never builds MusicXML. It sends a spec-like request, e.g.

```json
{ "drill": "full_key", "render": "block", "mode": "major", "key": "G major" }
{ "drill": "horizontal_degree", "render": "arpeggio", "mode": "major", "degree": "V" }
```

`spec_from_circle_request()` synthesises a stable `exercise_id`/`title`, builds a
`HarmonyExerciseSpec`, and **validates** it (invalid requests raise
`ValueError`). `HarmonyTrainerWindow.load_spec_from_circle()` then loads it
through the normal trainer flow — `HarmonyExerciseSpec` is never bypassed.

---

## Running it

```bash
.venv/Scripts/python.exe run_harmony_trainer_demo.py
```

The trainer window opens with the score on the left and the **Circle of Fifths**
panel on the right (toggle with the **Circle** button).

### Interactions

| Action | Result |
|---|---|
| Click a **major key** (outer ring) | selects it; shows scale + 7 triads; shortcuts: *Full-key block*, *Full-key arpeggio* |
| Click a **relative minor** (inner ring) | selects that natural-minor key; same shortcuts |
| Click a **triad** (inner ring / chip) | shows tones, quality, interval layer, function; shortcuts: *degree across keys (block/arpeggio)*, *quality drill* |
| Click a **function** chip (T / S / D) | highlights all triads of that function in the selected key |
| **Cheatsheet** button | major/minor degree patterns + interval-layer + function legends (all theory-derived) |

During an exercise, the panel highlights the current **key / degree / chord /
function**. Sync uses the trainer's `currentTarget()` (polled by the Qt host)
and the `harmonytrainer:targetchange` event dispatched by `harmony_trainer.js`.

The standalone trainer and its MIDI validation are unchanged; the Atlas launcher
(`run_harmony_atlas_demo.py`) disables this built-in panel (`with_circle=False`)
since the Atlas is its own navigation layer.

---

## Extension points

The payload reserves the relationship vocabulary so later layers slot in without
reshaping data:

`relative_minor_of`, `relative_major_of`, `dominant_of`, `subdominant_of`,
`same_quality`, `same_function`, `same_interval_layer`, `transposes_to`,
`resolves_to`.

Reserved for: dominant-seventh ring, diminished-seventh network, secondary
dominants, borrowed chords, harmonic/melodic minor, modal mixture, cadence
graph, and a Bach score-analysis overlay (which the
[Harmony Atlas](harmony_atlas.md) `ScoreAnalysis` interface already seeds).

---

## Tests

```bash
.venv/Scripts/python.exe -m unittest tests.test_circle_payload -v   # payload + bridge
node tests/circle_node_test.js                                      # JS controller (headless)
```

---

## Known limitations

* Diatonic triads only (no 7ths / secondary dominants yet — by design).
* The side panel is a separate web view, so sync is driven by the Qt host
  polling the trainer (the `harmonytrainer:targetchange` event is also emitted
  for the future same-page case).
* The 7-triad detail ring is drawn for the selected key; the resolution arrows
  from the reference images are reserved for the cadence layer.
