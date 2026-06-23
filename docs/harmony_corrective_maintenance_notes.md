# Harmony ecosystem — corrective-maintenance bug analysis

Corrective maintenance pass (branch `IO`). This note records the root-cause
analysis written **before** editing, per the implementation discipline. It is
not a redesign: the canonical model

```
CurriculumNode → LabExperimentSpec → HarmonyExerciseSpec(s) → Trainer
```

is preserved throughout. Every fix is an *extension* of an existing seam.

---

## BUG 1 — Global Diatonic Map live-sync parity

**Symptom.** The *Horizontal Transposition Matrix* highlights the concrete
key/degree/triad of the current trainer target (correct, the reference
behaviour). The *Global Diatonic Map* does not: its keyboard / interval
deconstruction / caption stay frozen on the reference key (C major / A natural
minor) regardless of the selected concrete triad.

**Root cause.** In `beat_selector/atlas.js` the Global-map keyboard
(`updateKeyboard`) is only ever driven by a row's *reference-key* payload
(`r.keyboard`), and only on **hover** (`onHover` in `renderGlobal`). The Part-VII
`setSync(active)` path (`atlas.js`) merely toggles the `sync-on` CSS class on
matching relatables — it never retargets the keyboard, never switches the
Global-map mode, and there is no per-concrete-triad keyboard payload to retarget
*to*. The Python model (`harmony/atlas.py`) only emits a keyboard payload for the
seven *reference* degrees (`global_map`), and the fixed mini-keyboard range
`KEYBOARD_RANGE_MIDI = (60, 77)` is the measured union of the two reference keys
only — concrete root-position triads span MIDI **59–78** (e.g. Gb major IV =
Cb–Eb–Gb hits 59; D major vi = B–D–F# hits 78), so the reference board cannot
even contain them.

**Fix (extend Global-map rendering/sync only; Matrix untouched).**
- `harmony/atlas.py`: widen `KEYBOARD_RANGE_MIDI` to `(59, 79)` so every diatonic
  root-position triad (reference *and* concrete) fits one fixed board; add
  `roman` + `chordSymbol` to `_keyboard_payload` (for the caption); attach a
  per-cell `keyboard` payload to every `transposition_matrix` cell so the UI has
  a concrete keyboard for each of the 168 triads.
- `beat_selector/atlas.js`: build a `triad-id → keyboard` lookup from the
  transposition matrix at init; in `setSync`, retarget the Global-map keyboard to
  the concrete selected triad, switch the Global-map mode to the target's mode,
  re-highlight the active row, and update the caption to the concrete
  key/roman/chord/layer. The Transposition-matrix renderer is **not** changed.

No architectural change: the Matrix remains the sync reference model; the Global
map is brought to parity by reusing the existing keyboard payload shape.

## BUG 2 — Cadence curriculum too limited

**Symptom.** The Cadences category contains only the four major two-chord types
(plus the pop progression), grouped under a single "Two-chord cadences" lesson.
No minor cadence types, no functional-progression cadence group.

**Root cause.** `harmony/curriculum.py` builds the Cadences lesson solely from
`_cadence_type_specs()`, which iterates the Atlas `_CADENCE_TYPES`
(major-only: V–I, IV–I, I–V, V–vi) + `_EXTRA_CADENCES` (pop I–V–vi–IV). The Atlas
has no minor cadence *type* nodes (v–i, VII–i) and no iv–v–i node, and the
curriculum never surfaces the functional progressions (I–IV–V–I, ii–V–I,
vi–ii–V–I, i–iv–v–i, i–VI–VII–i) as cadences.

**Fix (reuse existing factories; one canonical catalog).**
- `harmony/atlas.py`: add the three missing cadence nodes — v–i, VII–i (types,
  natural minor) and iv–v–i (progression, natural minor) — to `_CADENCE_TYPES` /
  `_EXTRA_CADENCES`, so `Atlas.cadence_node_id(tokens, mode)` resolves for all 13
  required cadences. Purely additive (no node-count test asserts cadence totals).
- `harmony/curriculum.py`: drive the Cadences category from a single
  `_CADENCE_CATALOG` (13 entries: tokens, label, mode, type, family). Build two
  lessons — **Two-chord cadences** and **Cadential progressions** — each split
  into major/minor groups. Each leaf is a block drill (the Atlas `function_spec`
  factory), carries its Atlas cadence-node mapping (looked up by tokens, so it
  always resolves), and its theory text states the function path and bass motion.
  The Voice-Leading category is expanded to the matching 13 SATB cadences (the
  existing 8 demos + 5 generated), and every block cadence cross-links to its VL
  counterpart ("voice-leading lab version where possible").

## BUG 3 — Chord-inversions lesson incomplete

**Phase A (correctness).** Verified by direct compile: `inv_C_I` already produces
the correct basses C3/E3/G3 → root position (5/3), first inversion (6), second
inversion (6/4); `bassPitchClass`, `pitchClasses`, `expected_by_beat`, the
MusicXML bass note and the slash chords (C, C/E, C/G) all agree, and `strict_bass`
already orders the bass pitch class first in `pitchClasses[0]`
(`harmony/lab.py::_gen_inversion`, `harmony/lab_musicxml.py`). The reported "bass
tied to G3" does **not** reproduce — G3 is correctly the *second-inversion* bass
only. Phase A is therefore a verification + a locked regression test, not a code
change.

**Phase B (coverage).** Root cause: the Inversions lesson pulls only the two demo
inversion specs from `lab_demo_specs()`. Fix: generate the systematic grid in
`harmony/curriculum.py` — I/ii/IV/V across all 12 major keys + i/iv/v/VII across
all 12 minor keys, each a `LabExperimentSpec(concept="inversion")` rendering the
3 measures (root / first / second). Grouped as the spec dictates (Major
inversions: Tonic I, Predominant ii/IV, Dominant V; Natural-minor inversions:
Tonic i, Subdominant iv, Dominant v, Subtonic VII). The two demos remain
reachable (`inv_C_I` is reused as the C-major-I cell; `inv_C_V_arp` is kept as the
arpeggiated worked example).

## BUG 4 — Incomplete-lesson audit

Add a pure introspection generator `harmony/curriculum_audit.py` that walks the
built curriculum + Atlas + Circle and emits a machine-readable
`docs/harmony_curriculum_coverage_audit.json` and a human-readable
`docs/harmony_curriculum_coverage_audit.md` (expected vs actual coverage, missing
/ duplicate nodes, empty explanations, missing Atlas/Circle mappings per
category). A regression test asserts the audit reports no missing *required*
lesson from this prompt.

---

## Files touched (planned)

- `harmony/atlas.py` — keyboard range/payload + per-cell keyboard + 3 cadence nodes.
- `harmony/curriculum.py` — cadence catalog, inversion grid, VL expansion.
- `beat_selector/atlas.js` — Global-map sync retargeting + mode switch + caption.
- `harmony/curriculum_audit.py` (new) — audit generator.
- `docs/harmony_curriculum_coverage_audit.{json,md}` (new) — audit artifacts.
- `tests/…` — focused regression tests; existing keyboard-geometry tests updated
  for the widened range.

No public API is removed; the Trainer, Circle, MusicXML and curriculum
architecture are unchanged. Theory generation stays pure and derives from
`theory.diatonic_harmony` (no duplicated theory tables).
