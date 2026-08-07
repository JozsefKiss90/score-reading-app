# Music Theory Laboratory

A laboratory layer **on top of** the [Harmony Trainer](harmony_trainer.md) and
the [Interactive Harmony Atlas](harmony_atlas.md). Where the trainer drills
root-position triads and the Atlas maps the invariant tonal system, the **Lab**
lets you pick a *concept*, generate concrete **playable** examples, hear and
MIDI-validate them through the existing `ScoreViewBeats`, and see how each maps
back onto the Atlas.

> **Scope (this slice).** Inversions, voice-leading cadences, motive
> transposition, and synthetic two-voice polyphony — in **major** and **natural
> minor**, triads only. Full automatic score analysis, Schenkerian reduction, a
> counterpoint engine, secondary dominants, seventh-chord voice leading, and
> harmonic/melodic minor are **non-goals** here, but the data model and the
> reserved `ScoreAnalysis` contract were shaped so they slot in without a
> redesign (see [Extension points](#extension-points)).

It is *not* a replacement for the trainer or the Atlas — it reuses both.

---

## 1. Architecture

```
harmony/lab_spec.py        LabExperimentSpec (schema "harmony-lab/v1") + validation
                           + to_exercise_specs()  — the bridge back to the trainer.
harmony/lab.py             Pure generation engine: compile_lab() -> LabExperiment
                           (an ordered list of LabMeasure with rich annotation).
harmony/lab_musicxml.py    LabExperiment -> playable MusicXML + a trainer payload.
harmony/atlas.py           (+additive) HarmonySlice / CadenceSpan / PolyphonicTexture
                           + adapters, extending the reserved ScoreAnalysis interface.
beat_selector/harmony_lab.html / .js   The concept-selector + explanation web UI.
run_harmony_lab_demo.py    Wires the Lab beside the (reused) Harmony Trainer.
```

The theory and rendering layers (`lab_spec`, `lab`, `lab_musicxml`) are **pure**
— standard library + `theory.diatonic_harmony` + `HarmonyExerciseSpec` + the
Atlas node-id helpers, no Qt / Verovio / MIDI — so they are unit-tested
headlessly. The UI is a separate web layer; MIDI validation is the **unchanged**
`harmony_trainer.js`. The shared viewer (`app.js`, `view.py`, `harmony_trainer.js`,
`musicxml_builder.py`, `atlas.py`'s ontology) is never modified: `atlas.py`
gained only *additive* Phase-6 dataclasses, and `run_harmony_trainer_demo.py`
gained only the additive `load_external_lab()` host method.

### Single source of truth

Nothing here re-encodes a chord, quality, Roman numeral, function, interval
layer, or spelling. Every value is **derived** from
`theory.diatonic_harmony.generate_diatonic_triads` /
`generate_scale` / `transpose_degree_pattern`, and every playable *drill* is a
`HarmonyExerciseSpec` expanded by the existing compiler. The SATB voicing is the
one genuinely new computation — a deterministic nearest-soprano close-position
helper (`harmony.lab._satb_progression`), explicitly *not* a counterpoint engine.

---

## 2. `LabExperimentSpec`

```json
{
  "schema": "harmony-lab/v1",
  "experiment_id": "inv_C_I",
  "title": "Inversions of the C major I chord",
  "concept": "inversion",
  "mode": "major",
  "key": "C major",
  "render": "block",
  "parameters": { "degree": "I", "inversions": [0, 1, 2] }
}
```

| `concept` | `render` (allowed) | key `parameters` |
|---|---|---|
| `inversion` | `block`, `arpeggio` | `degree` (a triad degree, or a seventh token like `V7` — ticket 11 / G1c), `inversions` ⊆ `{0,1,2}` (triads) / `{0,1,2,3}` (sevenths), `strict_bass?` |
| `cadence` | `block`, `voice_leading` | `pattern` (figured tokens like `ii6` — and the dominant-seventh figures `V65`/`V43`/`V42` — allowed with `render="block"`), `cadence_type?`, `dictation?` (`"bass"` = ear-first bass-line dictation, ticket 11 / A1 L5) |
| `voice_leading` | `voice_leading`, `block` | `pattern` |
| `motive` | `melody` | `degrees`, `keys?` |
| `polyphonic_harmony` | `polyphonic` | `progression`, `upper_degrees`, `bass_degrees?` |
| `reduction` | *(reserved)* | `skeleton?` |

`validate()` canonicalises the mode, enforces the render/concept pairing, range-
checks the key (−7..+7 fifths, like the trainer), checks each concept's
parameters, and caps the rendered measure count at `MAX_CHORDS_PER_SPEC` (12) so
every example renders on one page.

### `to_exercise_specs()` — the bridge back to the trainer

A lab experiment compiles **down to one or more `HarmonyExerciseSpec` objects
whenever possible** (the root-position chord skeleton), each guarded to compile
within the readability cap:

| Concept | Down-compiles to |
|---|---|
| `inversion` | one `function` drill `[degree]` in the key (the chord's root-position identity) |
| `cadence` / `voice_leading` | one `function` drill over the progression |
| `polyphonic_harmony` | one `function` drill over the implied per-measure progression |
| `motive` | `[]` — a scale-degree melody has no chord-drill representation |
| `reduction` | `[]`, or one `function` drill if an explicit `skeleton` is supplied |

`validate()` accepts diatonic Roman numerals (and `T`/`S`/`D` function shorthand)
only; chromatic or secondary tokens (`bII`, `V/V`, `#iv`) are **rejected** — they
are a non-goal of this slice and the diatonic engine cannot render them yet (see
[Extension points](#extension-points)).

So `cad_V_I_C.to_exercise_specs()` yields a `function` drill that compiles to
`[G, C]` in C major — exactly the trainer/Atlas `V–I` exercise — while the lab
*renders* it as SATB voice leading.

---

## 3. The implemented labs

### Inversions (Phase 2)
The chord tones are invariant; only the **bass** changes. For C major I:

| Inversion | Bass | Figured bass | Sounding pitch classes |
|---|---|---|---|
| root position | C | `5/3` | C E G |
| first inversion | E | `6` | C E G |
| second inversion | G | `6/4` | C E G |

The upper voices stay the root-position `C–E–G`; the bass staff shows `C → E → G`.
The guide names the inversion, figured bass, the invariant tones, and the changing
bass. **Every plain block inversion measure is bass-graded** (ticket 04 / plan
G4/F4): the payload target carries `strictBass: true` + `bassPitchClass`, and
`harmony_trainer.js` only completes the chord when the demanded member is the
*lowest sounding chord tone* — the right pitch classes over the wrong bass fail
with feedback naming the expected bass. The optional `strict_bass` parameter
*instead* requires the **bass note first in time** (its demand is encoded as the
ordered-tone walk, so those targets do not carry the `strictBass` flag). Cadence
patterns may demand a voicing with a figured token (`ii6`): that measure's bass
is then graded the lowest-note way (see `cad_ii6_V_I_C`, the curriculum's
inversions↔cadences bridge drill).

Ticket 11 (plan G1c) widens the same machinery to the **dominant seventh**: the
pattern tokens `V65` / `V43` / `V42` (slash spellings accepted) parse to the V7
tetrad with a demanded bass, and an `inversion` experiment with `degree: "V7"`
walks all four voicings with the tetrad figures `7 · 6/5 · 4/3 · 4/2` — every
figured measure bass-graded exactly like the triad grid. **Bass-line dictation**
(plan A1 level 5) is a cadence spec with `dictation: "bass"`: the notation and
playback keep the full chords, but each measure's graded target collapses to its
single bass pitch class; the payload carries `PRESENTATION: "echo"` (veil +
host auto-play) and `DICTATION: "bass"` (the JS prompt asks for the bass line,
one note per measure, any octave).

### Voice-leading cadences (Phase 3)
Cadences are rendered as a simple **closed-position SATB-like** grand-staff
voicing (soprano + alto on the treble staff, tenor + bass on the bass staff),
with derived annotation: common tones, bass motion, and tendency tones (e.g. the
leading tone B → C in `V–I`). Implemented progressions:

* **Major:** `V–I`, `IV–I`, `V–vi`, `ii–V–I`.
* **Natural minor:** `v–i`, `iv–v–i`, `VII–i`, `i–VI–VII–i` (modal — minor `v`,
  major subtonic `VII`, no raised leading tone).

The SATB voicing is deterministic (nearest-soprano close position, root in the
bass, no voice crossing, all chord tones); the **target** for MIDI validation is
the 3 reduced triad pitch classes, so a four-voice measure still validates as the
triad.

### Motive transposition (Phase 4)
A short scale-degree cell (e.g. `1–3–5–3`, `5–4–3–2–1`) is realised as a melodic
line and **transposed through all 12 keys** of the mode (`1–3–5–3` in C → `C E G E`;
in G → `G B D B`; in A natural minor → `A C E C`). Rendered as a single melodic
voice, MIDI-validated note-by-note in order. A motive has no chord-drill
representation, so `to_exercise_specs()` returns `[]` — it is still fully playable
through the lab payload.

### Polyphonic harmony (Phase 5)
Two independent voices whose **vertical slices imply a triad** per measure: a bass
that states chord roots under an upper voice that outlines thirds/fifths. A
build-time cross-check asserts both sounding voices belong to the declared chord
(so a declared Roman is never silently wrong). The implied chord is shown in the
guide and links to its Atlas triad node; the implied per-measure progression is
the down-compiled `function` drill.

---

## 4. How MIDI correctness works

The lab emits the **same payload shape** as the trainer
(`build_trainer_payload`): each `TARGET_CHORDS` entry carries the trainer's full
target key set (`key`, `mode`, `scale`, `roman`, `pitchClasses`, …) plus additive
lab fields (`figuredBass`, `voices`, `bassMotion`, `impliedChord`, `atlasTriadId`,
…) that the controller ignores but the explanation pane reads. The controller
judges correctness purely by **pitch-class set** — `coversAll` for `block`
targets, ordered `arpIndex` for `arpeggio`/`melody` targets — so SATB and
two-voice measures validate correctly because every sounding note is in the
rendered MusicXML and `pitchClasses` lists the target pcs. (See
[harmony_trainer.md §5](harmony_trainer.md#5-how-midi-correctness-works).)

---

## 5. Phase 6 — reserved real-score analysis contract

`harmony/atlas.py` was extended (additively) with three data structures and four
pure adapters that let *future* automatic analysis and the lab's *synthetic*
polyphony share one shape:

* **`HarmonySlice`** — one analysed vertical sonority (measure / beat / notes /
  inferred root / chord symbol / Roman / function / confidence / …).
* **`CadenceSpan`** — a detected progression over a measure range.
* **`PolyphonicTexture`** — independent voices + their verticalised slices.

Adapters: `slice_to_annotation` (→ resolves onto an Atlas `triad` node via the
existing `Atlas.node_for_annotation`), `texture_to_slices` (verticalises voices,
labelling with `identify_triad_from_pitches`), `cadence_span_to_spec` (→ a
launchable, cap-guarded drill), and `slices_from_lab_experiment` (turns a
synthetic `LabExperiment` into the same `HarmonySlice` shape, proving the
contract end-to-end today). `ScoreAnalysis` gained reserved
`extract_textures` / `extract_cadence_spans` (raising `NotImplementedError`).
No ontology node was added — the Atlas's node counts and determinism are
unchanged.

---

## 6. Running it

```bash
.venv/Scripts/python.exe run_harmony_lab_demo.py
```

The window shows the **Lab** (left: concept selector + explanation; bottom: live
Atlas mapping) beside the reused **Harmony Trainer** (middle: the generated score
+ the MIDI guide panel). Pick a concept, click an experiment — it compiles,
renders to MusicXML, and loads into the trainer; play along on a MIDI keyboard for
green/red feedback. The right pane explains the current chord (inversion / figured
bass / voice leading / implied harmony).

### Tests

```bash
# Python theory + MusicXML + payload + atlas-contract tests (stdlib unittest)
.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -t .

# Headless behavioural test for the lab web controller
node tests/harmony_lab_node_test.js
```

`tests/test_harmony_lab.py` asserts the generated pitches/voicings/figured bass
against an engine-verified reference, the `to_exercise_specs` chord symbols, the
cap invariant, payload/`harmony_trainer.js` compatibility, MusicXML
well-formedness + Verovio rendering, the Phase-6 Atlas mapping, and module purity.

---

## 7. Extension points

The non-goals were given explicit seams:

* **Real-score analysis (Bach, …)** — implement `ScoreAnalysis` to emit
  `HarmonySlice` / `CadenceSpan` / `PolyphonicTexture` (with
  `identify_triad_from_pitches` as the seed); the adapters already land them on
  Atlas nodes and playable drills.
* **Schenkerian reduction** — `concept="reduction"` validates today and
  down-compiles an explicit `skeleton`; `compile_lab` raises until the reduction
  algorithm ships.
* **Counterpoint** — `_satb_progression` is a deliberately minimal helper behind a
  stable signature; richer voicing swaps in without touching the payload or
  renderer.
* **Seventh chords** — `LabMeasure.target_pitch_classes` already allows *N* pcs;
  `coversAll` handles *N* tones. Add `generate_diatonic_sevenths` upstream and the
  lab consumes it unchanged.
* **Secondary dominants / tonicizations** — shipped by ticket 17 (plan G5a):
  the gate widened to `is_supported_roman` (applied `V/x` / `V7/x` tokens), the
  theory engine builds applied dominants (`build_applied_dominant`), and the
  `applied_chord` concept stages the spot/resolve intruder drills.
* **Harmonic / melodic minor** — add a `_MODE_STEPS` entry in
  `theory.diatonic_harmony`; the lab inherits it with no lab-side change.
```
