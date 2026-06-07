# Diatonic Harmony Trainer

A score-reading module that generates **playable harmony exercises** for
learning diatonic triads in major and natural-minor keys. It plugs into the
existing app: MusicXML is rendered through Verovio / `ScoreViewBeats`, and a
MIDI keyboard provides green/red correctness feedback.

> **Scope (first slice).** Diatonic **major** and **natural-minor** triads,
> **root position** only. Harmonic/melodic minor, secondary dominants,
> seventh chords, inversions, cadences, and real-piece analysis are *not*
> implemented yet — but the data model was designed so they can be added later
> without refactoring (see [Future work](#future-work)).

---

## 1. Pedagogical purpose

The trainer turns abstract theory tables into something you *play and hear*.
It targets six learning goals (the first five are implemented now):

1. **All diatonic triads** of every major and natural-minor key.
2. **Horizontal traversal** of a single scale degree across all keys
   (e.g. "every V triad in major").
3. **Triad interval-layer identification** (M3/m3 stacking).
4. **Transposition** of the same degree/function across keys.
5. **Harmonic-function recognition** through short progressions (ii–V–I, …).
6. *(foundation only)* cadences and real-piece harmonic analysis.

Every chord shown on the staff is annotated and explained, so reading,
ear, and theory reinforce each other.

---

## 2. Architecture

```
theory/diatonic_harmony.py     Pure theory (no Qt/Verovio/MIDI) — the contract.
harmony/exercise_spec.py       JSON exercise schema + deterministic compiler.
harmony/musicxml_builder.py    Compiled chords -> MusicXML + runtime payload.
beat_selector/harmony_trainer.js  Injected controller + sidebar guide panel.
run_harmony_trainer_demo.py    Wires it all into ScoreViewBeats.
```

The theory and harmony layers are **pure** and unit-tested. The controller is
**injected at runtime** into the existing viewer page; the shared viewer code
(`app.js`, `sidebar.js`, `keyboard_view.js`, `beatpage.html`) is never
modified, so existing behaviour (score view, beat selector, MIDI highlighting,
keyboard) cannot regress.

### The theory contract (source of truth)

* **Major triad pattern** — `I ii iii IV V vi vii°`
  = major, minor, minor, major, major, minor, diminished.
* **Natural-minor triad pattern** — `i ii° III iv v VI VII`
  = minor, diminished, major, minor, minor, major, major.

Crucially, the quality (and therefore the Roman-numeral case, chord symbol,
and function) is **derived from the actual interval content**, never hard-coded
per mode. Enharmonic spelling is computed by the "one letter per scale degree"
rule, so e.g. F# major spells its leading tone `E#` (not `F`) and E♭ major
never shows `D#`.

---

## 3. Triad interval-layer logic

A triad is two stacked thirds. The pair of thirds determines the quality:

| Quality      | Layer    | Lower third | Upper third | Example   |
|--------------|----------|-------------|-------------|-----------|
| major        | `M3+m3`  | major 3rd   | minor 3rd   | C–E–G     |
| minor        | `m3+M3`  | minor 3rd   | major 3rd   | D–F–A     |
| diminished   | `m3+m3`  | minor 3rd   | minor 3rd   | B–D–F     |
| augmented    | `M3+M3`  | major 3rd   | major 3rd   | C–E–G♯    |

`identify_triad_from_pitches([...])` returns this classification for any triad
(root position or inversion) and, when given a key, the Roman numeral and
function as well.

### Harmonic function labels

Each triad carries a broad **function label** (the T/S/D category) and a finer
**scale-degree name**:

| Degree (major) | I | ii | iii | IV | V | vi | vii° |
|---|---|---|---|---|---|---|---|
| function | tonic | predominant | mediant | subdominant | dominant | tonic | dominant |
| degree name | tonic | supertonic | mediant | subdominant | dominant | submediant | leading-tone |

| Degree (minor) | i | ii° | III | iv | v | VI | VII |
|---|---|---|---|---|---|---|---|
| function | tonic | predominant | tonic | subdominant | dominant | tonic | dominant |
| degree name | tonic | supertonic | mediant | subdominant | dominant | submediant | subtonic |

---

## 4. Exercise modes

Exercises are described by a small JSON-compatible spec
(`HarmonyExerciseSpec`) and expanded deterministically by `compile_exercise`.
Four drill families are supported:

| Drill | Meaning | Key fields |
|---|---|---|
| `horizontal_degree` | one degree across many keys (e.g. all V) | `degree`, `keys?` |
| `full_key` | all seven triads of one key | `key` |
| `quality` | all triads of a quality across keys | `quality`, `keys?` |
| `function` | a Roman / functional pattern across keys | `pattern`, `keys?` |

`function` patterns accept Roman numerals (`["ii","V","I"]`, `["vi","ii","V","I"]`)
**or** functional shorthand (`["T","S","D","T"]` → `I–IV–V–I`).

Each exercise is rendered as **block** triads or **arpeggiated** triads
(`render: "block" | "arpeggio"`), root position only.

### Example spec

```json
{
  "schema": "harmony-trainer/v1",
  "exercises": [
    { "exercise_id": "ii_v_i_c_g_d", "title": "ii–V–I in C, G, D",
      "drill": "function", "render": "block", "mode": "major",
      "pattern": ["ii", "V", "I"], "keys": ["C", "G", "D"] }
  ]
}
```

A ready-to-run set lives in
[`exercises/harmony_trainer/sequences.json`](../exercises/harmony_trainer/sequences.json).

### Staff annotations

Every measure is labelled above the staff with:

```
C major | ii | Dm | m3+M3 | predominant
key     | RN | sym| layer | function
```

The sidebar guide panel shows the full breakdown for the current chord:

```
G major — V (dominant)
Mode: major
Scale: G A B C D E F#
Chord: D (major)
Tones: D–F#–A
Layer: M3+m3
Function: dominant (dominant)
Explanation: In G major, D is scale degree 5 (dominant). Stacking diatonic
thirds (1–3–5) from D in the G major scale gives D–F#–A, a major triad
(M3+m3). Its harmonic function is dominant.
```

---

## 5. How MIDI correctness works

The trainer reuses the app's existing MIDI keyboard-colouring machinery rather
than replacing it:

* For the **current target chord**, the controller sets
  `app.state.selNotesByMidi` to that chord's tones, mapped **octave-agnostically**
  (any octave of a chord tone counts). The existing
  `app.refreshMidiHighlights()` then colours each pressed key:
  * **green** if the pitch belongs to the target chord, and the matching
    notehead on the staff turns green too;
  * **red** if the pitch is not in the target chord.
* **Block mode** expects all chord tones together: the chord is complete once
  every tone has been pressed, and the trainer advances to the next chord after
  you release the keys.
* **Arpeggio mode** expects the tones **in order** (root → third → fifth);
  pressing the wrong next note shows red, and each correct note advances.

The runtime payload (built by `build_trainer_payload`) drives the controller
entirely through `TARGET_CHORDS`; the JS recomputes the per-tone expectation
itself from each target's `pitchClasses` (all tones for block, advancing
root → third → fifth for arpeggio). The payload also exposes the additional
spec-named fields `TRAINER_MODE`, `TARGET_BY_MEASURE`, and
`EXPECTED_MIDI_BY_MEASURE_OR_BEAT` (per-measure for block, per-beat for
arpeggio) for inspection and the Python-side tests; the current controller does
not read them.

The guide panel also has **Prev / Next / Reset** controls and a clickable chord
list, so you can jump to any chord for free practice.

---

## 6. Running it

```bash
# default demo set (5 exercises)
.venv/Scripts/python.exe run_harmony_trainer_demo.py

# or a custom spec file
.venv/Scripts/python.exe run_harmony_trainer_demo.py exercises/harmony_trainer/sequences.json
```

The default demo includes all seven triads in C major, all seven in G major,
ii–V–I in C/G/D major, every V triad across the 12 major keys, and an
arpeggiated A natural-minor run.

### Tests

```bash
# Python theory + MusicXML smoke tests (stdlib unittest, no extra deps)
.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -t .

# Headless behavioural test for the injected JS controller
node tests/harmony_trainer_node_test.js
```

---

## 7. Future work

The data model and payload were shaped to grow without refactoring:

* **Harmonic / melodic minor** — add a new scale-step pattern in
  `_MODE_STEPS`; quality/Roman/function fall out automatically.
* **Seventh chords & inversions** — extend the triad builder with a fourth tone
  / a bass-note index; the MusicXML builder already separates voicing from
  spelling.
* **Cadences** — `function` drills already model progressions; a cadence is a
  named pattern plus a voice-leading constraint.
* **Real-piece harmonic analysis (e.g. Bach)** — `identify_triad_from_pitches`
  is the seed: feed it vertical slices of an imported score, with a key context,
  to label chords. The same guide-panel + green/red feedback then applies.
