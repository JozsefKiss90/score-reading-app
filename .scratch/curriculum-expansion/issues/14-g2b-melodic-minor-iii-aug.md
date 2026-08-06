# 14 — G2b: melodic minor + III+

**What to build:** Melodic minor's ascent/descent as a motive drill, and III+ as the first *legitimate* augmented triad: a quality drill that un-reserves augmented for real, replacing ticket 03's blanket rejection with genuine support (the code's own comment predicted augmented "arrives with harmonic minor's III+").

**Blocked by:** 13 — G2a harmonic minor; 03 — spec validation hardening.

**Status:** done

- [x] A melodic-minor ascending/descending motive drill runs in minor keys.
- [x] A III+ quality drill launches and grades; augmented specs now validate and compile to real chords.
- [x] Ticket 03's augmented rejection is lifted only for legitimately supported contexts; unsupported augmented requests still fail clearly.

**Plan:** docs/curriculum_expansion_plan.md §3 G2, §1.2 F5

**Shipped (ticket 14):**
- `theory/diatonic_harmony.py`: `melodic_minor` joins `_MODE_STEPS` /
  `_canon_mode` / `parse_key` — as a *scale form*, not a harmony mode:
  `generate_scale` builds the ascending form (raised 6̂/7̂), the descending
  form IS natural minor, and the pure seam `melodic_minor_raised(degrees)`
  decides per melody note (raised while ascending, natural while
  descending; a final note continues its direction of arrival). Chord
  generation (`generate_diatonic_triads` / `generate_diatonic_sevenths`)
  refuses melodic minor with an explanation — a two-way scale has no single
  honest diatonic chord set.
- `harmony/exercise_spec.py`: ticket 03's blanket augmented rejection is
  replaced by a mode gate — `quality="augmented"` (and
  `quality="diminished_seventh"`, honouring the code's G2b promise)
  validates and compiles in `mode="harmonic_minor"` (III+ / vii°7, one per
  key) and still refuses major / natural minor, where it would compile to
  zero chords. `mode="melodic_minor"` is refused for ALL trainer drills
  (chord drills), pointing at the motive lab.
- `harmony/lab_spec.py` + `harmony/lab.py`: `melodic_minor` is motive-only
  (any chordal lab concept refuses). `_gen_motive` renders the
  direction-dependent form: raised notes read from the ascending scale,
  everything else from natural minor; key context (display, signature,
  `scale_pitches`, Atlas scale claim) stays natural minor — the ticket 13
  "key stays A minor" rule.
- Curriculum: `group:triads_aug` un-reserved and filled with the real III+
  quality drill (`quality_augmented_in_harmonic_minor_1`, 12 keys = one
  page; echo twin automatic); new `cat:melodic_minor` with ascent / descent
  / turn motive cells (`mminor_motive_*`, 3 leaves, 12 minor keys each);
  melodic minor graduated out of Advanced Topics. Leaves 308 → 312.
  Lab refs claim natural-minor key context (`_key_context_mode` extended;
  `_atlas_refs_for_lab` / `_circle_refs_for_lab` resolve). Audit table +
  explanations updated; JS mode words gain "melodic minor" (trainer / lab /
  curriculum guides).
- Scene routing needed no changes: the III+ drill routes to
  `triad_quality_class` (augmented instances are scene-native, no false
  Atlas triad claims); motive labs stay honestly `unsupported`.
- Tests: new `tests/test_melodic_minor.py` (29 tests: scale form, direction
  rule, harmony refusals, motive pitch classes, III+/°7 compile + refusal
  matrix, scene smoke, curriculum wiring); ticket 13's reservation test
  flipped to assert the un-reservation; JS leaf count 312.
