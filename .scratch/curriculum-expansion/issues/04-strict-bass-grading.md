# 04 — Strict-bass grading for inversions (G4/F4)

**What to build:** Inversion drills actually grade the bass. When a leaf demands a specific inversion, the trainer requires the demanded chord member as the lowest sounding note, with feedback naming the expected bass on a miss. Figured-bass captions become assessed performance instructions rather than decoration. A cadence drill using ii6 as *the* predominant voicing links the inversions and cadences categories.

**Blocked by:** None — can start immediately.

**Status:** ready-for-human

- [x] Playing the correct pitch-class set with the wrong bass note fails an inversion drill; feedback names the expected bass.
- [x] The existing ~97 inversion leaves gain bass grading without re-authoring each leaf.
- [x] Root-position and non-inversion drills keep octave-agnostic grading (no regression).
- [x] A cadence drill exists that demands ii6 as the predominant voicing.

**Plan:** docs/curriculum_expansion_plan.md §3 G4, §1.2 F4

## Comments

**Implemented** (branch `fable_refactor`):

- **JS lowest-note check** (`beat_selector/harmony_trainer.js`): a block target carrying `strictBass: true` + `bassPitchClass` only completes when the demanded member is the lowest *currently sounding* chord tone (`lowestHeldChordTone` over `midiDown` — a released low tap doesn't count, and a stray released tap can't poison the attempt; both pinned by tests after the code review caught the original press-history version). A right-set/wrong-bass chord flags `✗ Right chord, wrong bass: E must be the lowest sounding note (6) — you have C in the bass`, recoverable by adding the bass below (no release) or releasing everything for a fresh attempt. The panel shows an assessed `Bass` row (bass note + figure). Non-flagged targets keep the octave-agnostic set check untouched.
- **Payload threading** (`harmony/lab.py`, `lab_musicxml.py`): new `LabMeasure.strict_bass` → target `strictBass`. `_gen_inversion` sets it on every *plain block* measure, so the whole 96-cell grid + the canonical `inv_C_I` (97 block cells) gain bass grading from the generator alone. Deliberate exemptions, each with a rationale in code: the legacy `strict_bass` *parameter* keeps its bass-first-in-time ordered-walk encoding and does **not** carry the flag (the panel must not claim a lowest-note check the ordered branch isn't making); the arpeggio worked example `inv_C_V_arp` stays an ordered root-position walk — "lowest sounding note" is a chord-voicing concept, and re-notating the arpeggio walk per inversion is content redesign beyond this ticket.
- **Figured cadence tokens** (`harmony/lab_spec.py`): `parse_figured_token`/`split_figured_pattern` understand triad figures (5/3, 6/6/3, 6/4); unknown figures are rejected explicitly — the tolerant `roman_token_to_index` was silently stripping digits, so `"ii6"` used to *play as root-position ii* (the F4 dishonesty in one line). Figures require `render="block"` (SATB voices root positions only). `_gen_voice_leading` voices the figured chord's real bass (staff, `bassPitchClass`, slash symbol, figured annotation, actual-bass `bass_motion`) and bass-grades only the figured measures. `to_exercise_specs` strips figures for the root-position skeleton but keeps them in the bridge id (no collision with plain drills).
- **The ii6 bridge leaf** (`harmony/curriculum.py`): `cad_ii6_V_I_C` under a new `lesson:inversion_cadence_bridge` in the Inversions category ("ii6 at the cadence", bass walks 4̂–5̂–1̂), cross-linked two-way with `lesson:cadence_progressions`. Deliberately **not** a `_CADENCE_CATALOG` entry — the catalogue is the cadence *taxonomy* mirrored into the harmonic network; ii6–V–I is a voicing variant, and G3 owns taxonomy changes. Leaf total is now 231 (docs + audit regenerated, `curriculum_node_test.js` updated).
- G4's plug-in note named `build_trainer_payload`, but inversions only exist as lab payloads, so the threading landed in `build_lab_payload`; the native trainer payload intentionally stays flagless (criterion 3).
- Known pre-existing quirk (out of scope, surfaced by review): devices sending velocity-0 note-offs bypass the wrapped `window.onMidiNoteOff`, so advance-on-release (and now the bass-miss reset) doesn't fire for them — inherited from the base app's handler routing, affects the existing trainer equally.
- Tests: `tests/test_strict_bass_grading.py` (16 tests: payload threading across all 97 leaves, non-inversion regression, figured tokens, legacy-mode exemption, the bridge leaf) + `tests/harmony_trainer_bass_test.js` (7 scenarios, 14 assertions, incl. sounding-bass semantics). Full suite 798 Python + all 13 node suites green.
