# 06 — Answer modalities beyond MIDI (U2)

**What to build:** Drills become completable without MIDI hardware. Four input paths: (a) chord cards gain an answer mode — click to answer, not just navigate; (b) an MCQ strip for identification drills; (c) the on-screen piano becomes a pointer-input instrument, not display-only; (d) a QWERTY fallback mapping. This unlocks ear-training levels 2–4, applied-chord spotting, and NCT tagging downstream.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [x] An identification drill is completable mouse-only via the MCQ strip.
- [x] Click-to-answer on chord cards records and grades an answer.
- [x] The on-screen piano registers pointer presses as note input, graded by the existing validator.
- [x] QWERTY typing plays notes as a fallback input.
- [x] The existing hardware-MIDI flow is unchanged.

**Plan:** docs/curriculum_expansion_plan.md §5 U2

## Comments

**Implemented** (branch `fable_refactor`):

- **Note input without hardware** — new `beat_selector/note_input.js`
  (`window.NoteInput`, classic script): synthetic notes route through the same
  `window.onMidiNoteOn/off` entry points the Python host uses for hardware
  MIDI (resolved at call time, so the trainer's grading wrapper sees them),
  and queue a copy that `ScoreViewBeats._poll_note_input` (view.py, 50 ms
  QTimer) drains into the FluidSynth monitor — sound-only, no JS re-entry.
  The hardware slots (`_on_midi_note_on/_off`, `audio/midi_input.py`,
  `audio/midi_service.py`) are untouched.
- **On-screen piano** — `keyboard_view.js` gains pointer handlers
  (pointerdown/up/cancel with capture, pointerId→midi map); display logic
  unchanged. `beatpage.html` keys get `touch-action:none` so touch plays
  instead of scrolling.
- **QWERTY fallback** — in `note_input.js`: layout-independent `e.code`
  mapping (A-row whites from C4, W-row blacks, `Z`/`X` octave), guards for
  auto-repeat/modifiers/editable targets, blur failsafe releases held notes.
- **Answer modes** — `HarmonyExerciseSpec.answer_mode`
  (`midi`|`mcq`|`card`, validated) flows as payload `ANSWER_MODE`;
  `build_trainer_payload` attaches per-target `mcq` blocks (prompt, the
  mode's seven Roman options via new `degree_labels_for_mode`, answer).
  `harmony_trainer.js` grades via `submitAnswer` (public
  `HarmonyTrainer.answer` + `answerState()` log): MCQ strip replaces the
  giveaway card list and detail rows; card mode turns cards into the answer
  surface (active-card highlight suppressed, card display order shuffled
  once per exercise so clicking top-to-bottom cannot game the drill,
  per-target `answerIndex` override ready for G5a); MIDI monitors but never
  grades in ID modes.
- **Catalogue seam** — `identification_demo_specs()` +
  `GROUP_IDENTIFY` appended only in the trainer launcher's `_load_groups`;
  `default_exercise_groups()` (curriculum-wrapped, exactly 102 drills) is
  byte-identical.
- Cross-language contract pinned by a committed test:
  `CrossLanguageMcqContract` (tests/test_answer_modes.py) runs every real
  Python-emitted MCQ payload through the real `harmony_trainer.js` via
  `tests/mcq_contract_check.js` and completes each drill mouse-only
  (skipped when node is not on PATH).
- Code review (two-axis) outcome: no hard standards violations, all five
  criteria implemented. Applied from review: card display-order shuffle
  (drill was gameable top-to-bottom), `markCardDone` gated to card mode,
  dropped a speculative `getattr` guard in the payload builder, hoisted a
  cross-section variable in `note_input.js`, committed the contract test
  above. Noted follow-ups (not this ticket): shared node-test harness
  (4 copies now), per-mode strategy object if the `answerMode` cascade
  grows, quality/cadence MCQ derivations for A1 levels 2–4.
- Tests: `tests/test_answer_modes.py` (16), `tests/note_input_test.js` (29
  assertions), `tests/harmony_trainer_answer_test.js` (23 assertions);
  existing trainer/lab/circle node suites and the full Python suite
  pass. Docs: `docs/harmony_trainer.md` §5b.
