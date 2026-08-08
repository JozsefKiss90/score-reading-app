# 03 — Simultaneity grading: dyad steps, octave doubling, re-attacks

**What to build:** Teach the ordered grader to demand **more than one concurrent note per step**.
Today `harmony_trainer.js:559-577` compares each note-on against a single scalar
`t.pitchClasses[arpIndex]` mod-12 — so a third (C+E together), an octave doubling (C4+C5), and a
re-struck repeated chord are all inexpressible. This is the enabling ticket for thirds (08),
ricochet sixths (09), octave scales (10), and hands-together scale forms (05 v2).

**Blocked by:** 01 — technique concept (the payload rides on technique targets).

**Status:** ready-for-human

## Design

**Payload (additive).** A target may carry `steps`: an ordered list of step objects,
`{"pcs": [0, 4], "minDistinct": 2}`:

* `pcs` — the pitch classes that must be **held concurrently** to satisfy the step.
* `minDistinct` — minimum number of distinct MIDI note numbers held among those pcs (default
  `len(pcs)`). Octave doubling = `{"pcs": [0], "minDistinct": 2}` — two different C keys down.

`pitchClasses` stays populated with the flat ordered union (guide panel, `buildSelection`
highlighting, and old payloads unchanged — the JS ignores unknown fields, so `steps` is
backward/forward safe). Emitted from `_lab_target_for` (`lab_musicxml.py:170-220`) when the
measure carries the new `LabMeasure.step_targets` field; `_gen_technique` builds it from a new
`TechniqueParams` shape: a phrase entry may be a **tuple of degrees** (dyad) instead of an int,
plus an `octaves: bool` param that turns every step into a `minDistinct: 2` doubling.
`expected_by_beat` keeps the per-beat pc lists (playback already handles lists —
`playback_plan.py:136` — so dyads *sound* correct with zero playback work).

**JS grader** (`beat_selector/harmony_trainer.js`):

* Track an **active-note set** of raw MIDI numbers (add on note-on, remove on note-off /
  velocity-0). This set is new state next to `satisfied`/`arpIndex` and is also the seam ticket
  04's hold enforcement reuses.
* In ordered mode, when the current target has `steps`: on each note-on, the current step is
  satisfied iff (a) every pc in `steps[i].pcs` is present in the active set, (b) the count of
  distinct active MIDI numbers whose mod-12 lands in `pcs` is ≥ `minDistinct`, and (c) **at least
  one constituent note-on arrived after the previous step completed** (the re-attack rule — this
  is what makes "play the same sixth four times" gradable, while still allowing finger-legato
  overlap between *different* consecutive dyads).
* On satisfy: advance `arpIndex`, `applySelection()`, `renderProgress()` — identical flow to the
  scalar branch; last step completes the measure. Wrong notes stay ignored (house behaviour).
* Near-miss forgiveness: notes released between the two halves of a dyad simply mean the step is
  not yet satisfied; no error state.

**Render.** A dyad step renders as two noteheads `<chord/>`-stacked on one stem (the serializer
already supports `<chord/>`); an octave step renders the written octave pair. `_gen_technique`
places dyad partners via `_scale_note` on both degrees.

**Tests:** JS-side in `tests/curriculum_node_test.js`-style harness if one exists for the trainer
(else Python-side payload tests): step emission shape; and `tests/test_technique.py` — dyad
phrase compiles to `steps` + flat `pitchClasses` union; octave phrase sets `minDistinct: 2`;
playback plan carries both pcs per beat. Manual QA note: verify with two-key presses that
out-of-order arrival (E before C) still satisfies a C+E step once both are down.

## Grading honesty

The step rule grades *concurrency at note-on time*, not attack synchrony: two notes struck 200 ms
apart but overlapping still pass. True attack-together grading needs the (currently discarded)
timestamps — out of scope, noted in the concept explanation.

## Implementation notes (close-out)

* `harmony/lab_spec.py` — phrase entries may be tuples of **distinct** degrees (duplicate degrees
  refused; an explicit octave pair is the degree twice 7 apart, e.g. `(1, 8)`); new
  `octaves: bool` (scalar entries only, degrees capped at 22 so the written pair stays ≤ 29).
  Marks mirror the phrase per step — a scalar label lands on the step's first notehead, a tuple
  label maps note-for-note onto a dyad.
* `harmony/lab.py` — `LabStepTarget(pcs, min_distinct)`; `LabMeasure.step_targets` is set only
  for measures containing a real simultaneity, so scalar payloads stay byte-identical. Step pcs
  are deduped in order (octave pair → one pc, `min_distinct` = key count); partners render as
  `LabNote(is_chord_tone=True)` → `<chord/>`.
* `harmony/lab_musicxml.py` — additive `steps` field; `harmony/playback_plan.py` untouched
  (dyads sound via the per-beat pc lists; an octave pair still *plays* as one note — pc-based
  playback contract, accepted and documented).
* `beat_selector/harmony_trainer.js` — `activeNotes` (raw-MIDI physical mirror, never cleared by
  navigation; ticket 04's hold seam, exported as `state().heldNotes`) + `freshNotes` (cleared on
  step satisfy and attempt reset) implement (a)/(b)/(c) exactly as specced; scalar branch
  untouched.
* Tests: `tests/test_technique.py` `TestSimultaneity{Validation,Compile,Payload}`;
  `tests/harmony_lab_midi_test.js` Tests F (out-of-order arrival, near-miss forgiveness, legato
  overlap), G (re-attack on a repeated sixth), H (octave doubling, same-key-twice ≠ two keys).
  Honesty noted in the `technique` concept explanation and `docs/harmony_trainer.md` §5.
