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

### The comprehensive default set

`default_exercise_groups()` builds the full practice set deterministically from
specs (no hard-coded MusicXML) — **102 exercises** covering every major and
natural-minor key. They are organised into six launcher groups (the "Group"
filter in the demo narrows the exercise list to one of these):

| Group | Contents | # |
|---|---|---|
| **Major full-key drills** | all 7 triads of each of the 12 major keys (block) | 12 |
| **Minor full-key drills** | all 7 triads of each of the 12 natural-minor keys (block) | 12 |
| **Degree transposition drills** | each scale degree across all 12 keys, both modes (block) | 14 |
| **Quality recognition drills** | every major / minor / diminished triad across the major keys | 7 |
| **Function drills** | I–IV–V–I, ii–V–I, vi–ii–V–I (major) and i–iv–v–i, i–VI–VII–i (minor) | 19 |
| **Arpeggio drills** | full-key (both modes) and per-degree (both modes), arpeggiated | 38 |

The groups **partition** the set — every exercise appears in exactly one group
(block full-key/degree drills in their family group; every arpeggio-rendered
drill under "Arpeggio drills"), so the same content is reachable once.

**Readability.** Each generated spec is capped at `MAX_CHORDS_PER_SPEC` (12,
matching the existing "V across the 12 keys" drill — the project's de-facto
single-exercise length). `full_key` (7 chords) and per-degree drills (12) sit
within the cap as-is; longer drills (function patterns, multi-degree quality
drills) are **split by key-group** into several short specs rather than one long
score. `all_default_specs()` returns the flat list in group order.

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

Every chord is labelled on the staff using Verovio-native, auto-positioned
elements, so labels never overlap no matter how Verovio packs the measures:

* the **chord symbol** (`Dm`, `G`, `B°`) — a `<harmony>` element above the
  treble staff, and
* the **Roman numeral** (`ii`, `V`, `vii°`) — a `<numeral>` element below it.

(Free `<words>` text was avoided: Verovio neither resizes it to a given
font-size nor widens measures to fit it, so per-measure prose overlaps badly.)

The **interval layer** and **harmonic function** — plus the key, scale, chord
tones, and a written explanation — are shown in the sidebar guide panel for the
current chord:

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
  `app.state.selNotesByMidi` to that chord's tones. The existing
  `app.refreshMidiHighlights()` then colours each pressed key:
  * **green** if the pitch belongs to the target chord, and the notehead the
    key *is* turns green too;
  * **red** if the pitch is not in the target chord.
* The two halves of that entry use **different octave rules**, on purpose:
  * **Key colour is octave-agnostic** — any octave of a chord tone counts, the
    same rule the grader uses. Every octave of an expected pitch class gets an
    entry carrying a `__ht_target_<pc>` sentinel id, which resolves to no SVG
    node and so only keeps the key green.
  * **Noteheads are octave-exact** — MIDI `m` selects only noteheads actually
    notated at `m` (via `idsByMidiForMeasure`), so pressed pitch → lit notehead
    is one-to-one. Playing a chord tone in an octave the score does not notate
    still greens the key but lights no notehead.

  Keying every octave onto one shared pitch-class-wide id set made this
  ambiguous in both directions: pressing any C lit every C in the bar (the
  two-octave arpeggio runs lit C4/C5/C6 at once, reading as premature
  progress), and every C on the keyboard lit the same single notehead.
* **Block mode** expects all chord tones together: the chord is complete once
  every tone has been pressed, and the trainer advances to the next chord after
  you release the keys. Block grading is **octave-agnostic** — a block target
  asks *which chord*, so any voicing of it counts.
* **Arpeggio mode** expects the tones **in order** (root → third → fifth);
  pressing the wrong next note shows red, and each correct note advances.
  Ordered walks grade **octave-exact**: the walk asks *which keys*, so a slot
  written C5 is not satisfied by C4 (`walkStepMatches`). The key colour follows
  the same rule here — for a slot-aligned walk `buildWalkSelection` maps only
  the notated pitches, so a wrong-octave press reads red rather than showing a
  green key that refuses to advance. Already-played slots stay green.

  The demanded octaves come from the notation itself: `walkSlotRows` recovers
  the measure's noteheads in walk order from `PITCH_MAP`. When the rows cannot
  be slot-aligned — chord stacks, second voices, or no `PITCH_MAP` yet — there
  is no honest octave to demand and the comparison falls back to mod-12, the
  same fallback the display uses.

The runtime payload (built by `build_trainer_payload`) drives the controller
entirely through `TARGET_CHORDS`; the JS recomputes the per-tone expectation
itself from each target's `pitchClasses` (all tones for block, advancing
root → third → fifth for arpeggio). The payload also exposes the additional
spec-named fields `TRAINER_MODE`, `TARGET_BY_MEASURE`, and
`EXPECTED_MIDI_BY_MEASURE_OR_BEAT` (per-measure for block, per-beat for
arpeggio) for inspection and the Python-side tests; the current controller does
not read them.

An arpeggio-walk target may additionally carry `steps` (piano-technique
ticket 03) — an ordered list of simultaneity steps,
`{"pcs": [0, 4], "minDistinct": 2, "midis": [60, 64]}`: the pitch classes that
must be **held concurrently**, the minimum number of distinct MIDI keys
sounding among them (octave doubling is one pc, two keys), and the step's keys
**as notated**. The walk then advances per step: at each note-on the current
step is satisfied iff its keys are held and at least one of them was struck
after the previous step completed (the re-attack rule — a held chord never
plays the next step for free, while finger-legato overlap between *different*
consecutive steps still passes). Wrong notes stay ignored and releases carry
no error state. `midis` makes the step octave-exact like the scalar walk, so
an octave pair written C4+C5 is **not** satisfied by C3+C4; a step without it
falls back to the `pcs`/`minDistinct` comparison. `pitchClasses` keeps the flat
ordered union, so payloads without `steps` — and controllers that ignore
unknown fields — behave exactly as before. This grades **concurrency at note-on time**, not attack synchrony:
striking exactly together would need the timestamps the grader discards.

An arpeggio-walk target may also carry `hold` (piano-technique ticket 04 v2,
the held-note textures), `{"pc": <int>}`: the pitch class that must be
sounding — any octave — for the walk's steps to be accepted. A correct
moving note struck while the hold is up is refused *without* resetting
progress; the guide panel shows an amber "keep the X held" hint until the
hold sounds again. Honesty limits, stated in the guide text: the hold is
verified **at each step's satisfaction instant**, not continuously between
steps; mod-12 means the octave of the held key is not checked, nor is the
finger used. Without `hold` in the payload (the v1 default) the held whole
note is notation + coach text only, and the measure's guide line says which
side of that boundary it is on.

The guide panel also has **Prev / Next / Reset** controls and a clickable chord
list, so you can jump to any chord for free practice.

---

## 5b. Answer modalities beyond hardware MIDI (plan U2)

Drills are completable **without MIDI hardware** through four input paths.

**Note input without a MIDI keyboard.** Two new sources synthesize the very
same `window.onMidiNoteOn` / `window.onMidiNoteOff` calls the Python host
makes for hardware MIDI, so highlighting and grading are byte-identical and
the hardware path is untouched:

* **On-screen piano** (`keyboard_view.js`) — pointer presses play keys
  (primary button / touch / pen, with pointer capture; multi-touch chords work
  on touchscreens, and block targets also accumulate across sequential
  mouse taps because the grader's `satisfied` set survives releases).
* **QWERTY fallback** (`note_input.js`, `window.NoteInput`) — DAW-style,
  layout-independent `e.code` mapping: the `A`-row plays white keys from C4,
  the `W`-row the black keys between them (`A`=C4 … `K`=C5 … `'`=F5), `Z`/`X`
  shift the octave. Auto-repeat, modifier chords and typing into inputs are
  ignored; a window-blur failsafe releases held notes.

Both queue their events in `NoteInput`; `ScoreViewBeats` polls
`NoteInput.takeEvents()` (50 ms) and sounds them on the FluidSynth monitor —
sound-only, never re-entering the page.

**Answering without playing.** The spec gains `answer_mode`
(`midi` default | `mcq` | `card` | `spot`), carried to the controller as the
payload's `ANSWER_MODE`:

* **`mcq`** — identification drills. Each target carries an `mcq` block
  (`prompt`, the mode's seven Roman-numeral `options`, `answer`); the panel
  renders an answer strip, hides the giveaway detail rows and the ordered
  chord-card list, and grades clicks via `HarmonyTrainer.answer(option)`.
  Correct advances after a feedback beat; wrong records the miss and lets you
  retry. MIDI (from any source) still lights keys but never grades.
* **`card`** — the chord cards become the answer surface: the prompt shows
  the current chord's tones/function and clicking the matching card answers
  (`HarmonyTrainer.answer(index)`). A per-target `answerIndex` override is the
  seam for a per-target answer override. In classic `midi` mode card clicks
  keep navigating exactly as before.
* **`spot`** — "spot the intruder" (plan G5a, ticket 17): a *single-question*
  drill over one rendered progression holding exactly one applied chord. The
  payload carries `SPOT_INDEX` (the intruder's target index) and marks that
  target `romanHidden` (its Roman numeral is suppressed in the MusicXML too —
  the chord symbol stays); a correct click finishes the whole exercise, pulses
  the intruder's chromatic noteheads (`ht-intruder`) and reveals its name.
  Wrong clicks are logged and re-askable.
* **`spot` + `presentation: "echo"`** — the **ear stage** (plan G5c, ticket
  19): the same hunt with the notation veiled, so the answer surface becomes a
  strip of **bar positions** (the chord-card list names chords and stays
  withheld). The payload adds `SPOT_FOLLOWUP` (`prompt`, the mode's
  tonicisable `options`, `answer`) — a second question, *which degree did that
  chord tonicise?* — and the drill is finished (and the veil lifted) only when
  **both** are answered, so the revealed notation can never answer the
  follow-up. `state().followupPending` exposes the phase; follow-up attempts
  log as `mode: "spot_followup"`. The cross-language contract for the whole
  flow is `tests/ear_spot_contract_check.js`, driven from
  `tests/test_applied_ramps.py`.

Every attempt lands in an answer log (`HarmonyTrainer.answerState()`,
`state().answered`), the seam for progress tracking. Launchable no-MIDI drills
live in `identification_demo_specs()` under the trainer launcher's
**Identification drills (no MIDI needed)** group — deliberately *not* part of
the load-bearing `default_exercise_groups()` 102-drill set that the
curriculum/Atlas/network wrap.

---

## 5c. Echo-play ear drills (plan A1 level 1, ticket 07)

Every native drill has an **aural twin**: the same spec with
`presentation: "echo"` (default `"visual"`), the first level of the
ear-training engine. Echo-play is *sound before symbol* on the *same
vocabulary* — the target plays with the notation hidden, the learner plays it
back by ear, and the very same pitch-class validator grades the attempt.

* **Model** (`harmony/echo_drills.py`, pure): `echo_variant(spec)` derives the
  twin (`*_echo` id, "Echo: " title, same compiled chords — the payload differs
  *only* in identity + `PRESENTATION`); `is_echo_eligible(lab_spec)` marks the
  curriculum leaves that own one (native `drill`-concept leaves: the triad
  families and the cadence block drills — plus, since ticket 19, the
  applied-chord **spot** leaves, whose twin is the ear stage above);
  `echo_unlocked(state)` gates the twin on the visual leaf being at least
  *started*.
* **Listen phase** (`harmony_trainer.js`): while an echo drill is unfinished
  the notation is **veiled** — an `ht-veil` class + injected SVG style hide
  noteheads, beams, rests, accidentals, ledger lines and the chord-symbol /
  Roman-numeral labels (staff, clefs, signatures and the cursor stay, so the
  learner sees *where* they are, not *what* sounds); the guide panel redacts
  every chord-identifying field; the chord-card list is withheld; and
  `currentTarget()` (the Atlas/Circle/guide sync feed) is redacted to
  key/mode/position with `echoVeiled: true`, so no external pane can leak the
  answer. Grading state is untouched: the same note events complete and
  advance targets, and the keyboard's green/red monitoring works as always.
* **Sound-first**: loading an echo payload auto-starts the section-6 transport
  (`HarmonyTrainerWindow._show_score`), and ▶ Play replays it at will.
* **Reveal**: finishing the drill lifts the veil — the notation (and, in the
  Lab, the withheld Harmonic Scene) appears for review. Navigating the chords
  again re-veils for a fresh ear pass.
* **Curriculum wiring** (Lab workspace): eligible leaves show a **🎧 Echo
  drill** button that unlocks once the visual leaf is started; the launch
  payload is the leaf's own `labSpec` plus an `echo: true` flag, so the host
  records the echo attempt under the **same curriculum node id** — aural and
  visual attempts share one mastery record per leaf.
* **Launcher demo**: the standalone trainer appends the opt-in
  `GROUP_ECHO` group (`echo_demo_specs()`), leaving the load-bearing
  `default_exercise_groups()` 102-drill set untouched (same pattern as the
  identification group). That launcher has no progress store, so — like every
  drill there — the demo group is ungated and records nothing; the gated,
  mastery-recorded path is the curriculum workspace.

Later A1 levels (quality ID, progression ID, cadence ID, bass dictation,
chromatic spotting) ship inside their module tickets — this slice is
echo-play only.

---

## 6. Target playback (transport)

Every drill can be *heard*, not just seen (plan U1 — "sound before symbol").
The trainer window's top bar has a transport — **▶ Play / ⏸ Pause**, **⏹**
(stop + rewind), **Loop**, and a **tempo** spinner (30–240 bpm, default 80) —
that plays the target progression through the score widget's already-loaded
FluidSynth monitor. Because the transport lives in `HarmonyTrainerWindow`
itself, it is available in every launcher that hosts the trainer (standalone,
Atlas, Lab, Harmonic Network, Functional Network, Curriculum).

Three layers share the work:

* **`harmony/playback_plan.py`** (pure, no Qt) turns a trainer/lab payload
  into beat-timed note events — one 4/4 measure per target, exactly what the
  score notates: block chords sound `midiPitches` + the new `bassMidi` target
  field (the notated bass whole note) for the full measure; arpeggio/melody
  measures hold the bass while the tones sound one beat each (driven by the
  payload's `EXPECTED_MIDI_BY_MEASURE_OR_BEAT` beat map). Playback follows the
  *notation*, not the grading: lab strict-bass measures grade as ordered walks
  but play as the block chords they notate (`concept` overrides `render`).
* **`audio/target_playback.py`** (`TargetTransport`) owns transport state on a
  QTimer beat clock: play/pause (pause silences but holds position and
  re-attacks on resume), stop (rewind + hand the display back), loop, and live
  tempo changes. It fires synth `noteon`/`noteoff`, sweeps the cursor via the
  page-global `jsSetCursorAbs` in notated-measure seconds, and mirrors every
  onset into the controller.
* **`harmony_trainer.js`** (`playbackFlash` / `playbackClear`) flashes the
  noteheads that actually sound — octave-exact against `PITCH_MAP`, with a
  pitch-class fallback — in amber (`pb-live`), distinct from the learner's
  green/red. Overlapping flashes (held bass under per-beat tones) expire
  independently.

The playback path is display-only: it never touches `midiDown`,
`selNotesByMidi`, or the grading position, so the learner's own MIDI
monitoring works unchanged during playback — and while the transport is idle
it runs no timers and makes no synth or JS calls at all.

---

## 7. Running it

```bash
# comprehensive default set (102 exercises, with the Group filter)
.venv/Scripts/python.exe run_harmony_trainer_demo.py

# or a custom spec file (loaded as a single group)
.venv/Scripts/python.exe run_harmony_trainer_demo.py exercises/harmony_trainer/sequences.json
```

With no argument the demo loads `default_exercise_groups()` — all 12 major and
12 natural-minor keys as full-key, per-degree, quality, function and arpeggio
drills (see [the comprehensive default set](#the-comprehensive-default-set)) —
and shows a **Group** dropdown to filter the exercise list. The committed
[`exercises/harmony_trainer/sequences.json`](../exercises/harmony_trainer/sequences.json)
holds the same set as a flat, ready-to-run file. (The smaller five-exercise
`default_demo_specs()` remains in the code for tests and quick checks.)

### Tests

```bash
# Python theory + MusicXML smoke tests (stdlib unittest, no extra deps)
.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -t .

# Headless behavioural tests for the injected JS controller
node tests/harmony_trainer_node_test.js
node tests/harmony_trainer_playback_test.js
node tests/harmony_trainer_bass_test.js
node tests/harmony_trainer_answer_test.js   # MCQ / card answer modes (U2)
node tests/note_input_test.js               # on-screen piano + QWERTY input (U2)
node tests/harmony_trainer_echo_test.js     # echo-play veil + reveal (A1, ticket 07)
```

---

## 8. Future work

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
