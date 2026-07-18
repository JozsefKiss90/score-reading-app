# 03 — Spec validation hardening (F5, F6)

**What to build:** Hand-authored or bridge-supplied exercise specs can no longer crash the renderer or silently overflow the visible page. Validation rejects augmented-quality specs (until III+ ships legitimately in ticket 14) and specs exceeding the 12-chord cap, each with a clear explanatory error.

**Blocked by:** None — can start immediately.

**Status:** ready-for-human

- [x] An augmented-quality spec fails validation with an explanatory error instead of compiling to zero chords and crashing the score builder.
- [x] A 13-chord spec fails validation; no override exists yet (the explicit opt-in flag arrives with ticket 31).
- [x] Tests cover both rejections and the happy path at exactly 12 chords, including specs arriving via custom JSON and the circle input.

**Plan:** docs/curriculum_expansion_plan.md §1.2 F5, F6

## Comments

**Implemented** (branch `fable_refactor`):

- `HarmonyExerciseSpec.validate()` (harmony/exercise_spec.py) now carries both gates. F5: `quality="augmented"` raises with an error explaining the zero-chord/score-builder failure and that augmented drills arrive with harmonic minor's III+ (`"augmented"` stays in `_VALID_QUALITY` deliberately so ticket 14 only deletes the rejection). F6: a new `_expected_chord_count()` mirrors the compiler's per-drill expansion (full_key → 7, horizontal_degree → one per key, function → pattern × keys, quality → the shared filter) and validate() rejects any spec past `MAX_CHORDS_PER_SPEC` with an error naming the count, the cap, the hidden-second-page consequence, and the split-by-keys remedy. No override flag (ticket 31).
- Both gates cover every arrival path for free: `from_dict`/`load_specs` (custom JSON) and `spec_from_circle_request` (circle) both funnel into `validate()`; `compile_exercise` validates on entry. The circle bridge's own compile-and-check stays as a drift backstop + fail-fast on unparseable tokens (comment updated to say so).
- Post-review hardening: the per-key quality filter that existed in three copies (compiler, counter, `_quality_specs`) is now one helper, `_triads_of_quality()`; a drift test asserts `_expected_chord_count()` equals the compiled length for all 102 default specs, so a future compiler change (sevenths, cadences) fails loudly instead of silently reopening F6.
- Tests: `tests/test_spec_validation.py` (17 tests) — both rejections with message asserts, happy path at exactly 12 chords for function/degree/quality drills, custom-JSON round-trip through a real file, circle requests, and the count-mirrors-compiler drift suite. Full suite 782 green.
