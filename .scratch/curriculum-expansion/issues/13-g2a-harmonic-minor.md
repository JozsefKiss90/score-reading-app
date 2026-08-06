# 13 — G2a: harmonic minor — a real V in minor

**What to build:** The raised leading tone arrives. The engine gains the harmonic minor mode; minor keys get a real major V and vii°; the functional-equivalence layer stops refusing minor; minor role strengths update (v weak → V strong when the mode says so). Drills: the "one accidental changes everything" A/B lesson (the same cadence with ♭7, then ♮7), and V–i / vii°–i across all 12 minor keys. This fixes the platform's largest content limitation — today every minor cadence sounds Aeolian.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] i–iv–V–i with the raised 7̂ is drillable in all 12 minor keys.
- [x] The A/B lesson contrasting modal v–i vs tonal V–i ships (visual now; the aural pair lights up once playback/echo exist).
- [x] Functional equivalence accepts minor keys; the role model reflects mode-aware dominant strength.
- [x] Existing natural-minor drills are unchanged and the subtonic lesson remains correct.

**Plan:** docs/curriculum_expansion_plan.md §3 G2, §1.2 F11

**Shipped (ticket 13):**
- `theory/diatonic_harmony.py`: `harmonic_minor` joins `_MODE_STEPS` /
  `_canon_mode` / `parse_key` ("A harmonic minor"; plain "minor" stays
  natural). New degree/function tables (7̂ = leading-tone, III+ = mediant).
  `vii°7` joins `SEVENTH_DEGREE_TOKENS`; `seventh_tokens_for_mode` returns
  only honestly-classifiable tokens (harmonic minor: iiø7 iv7 V7 VImaj7
  vii°7 — the mM7/augMaj7 tetrads have no token). `build_seventh_chord("V7",
  key, "harmonic_minor")` builds the real minor-key dominant seventh.
- `harmony/exercise_spec.py`: harmonic-minor degree labels (i ii° III+ iv V
  VI vii°) for MCQ options; the `full_key` compiler no longer downgrades an
  explicit harmonic-minor spec when the key string says just "minor";
  augmented/°7 QUALITY drills still refuse (un-reserved by G2b, ticket 14)
  with mode-aware messages.
- `harmony/harmonic_roles.py`: `_HARMONIC_MINOR_ROLES` — V strong primary
  dominant, vii° strong leading-tone, III+ contextual mediant; natural-minor
  entries untouched (v/VII stay contextual).
- `harmony/harmonic_network.py`: functional equivalence un-refuses minor —
  the dominant trio (V / V7 / vii°) is drawn from HARMONIC minor, node ids /
  launch specs / refs use `harmonic_minor`, and no chord node claims a
  natural-minor atlas triad. JS needed no change (data-driven; the fnet
  major-only sync guard is ticket 15's scope).
- `harmony/curriculum.py`: new live category **Harmonic Minor** (12 leaves,
  296→308): the A/B "one accidental changes everything" lesson (v–i vs V–i
  and i–iv–v–i vs i–iv–V–i in A minor, A-then-B) + V–i, vii°–i, i–iv–V–i
  chunked across all 12 minor keys. All native MIDI drills → echo (🎧)
  twins light up automatically. Atlas/circle refs: key context stays
  natural minor (Score Soul precedent); chord refs only on exact match —
  the raised chords claim only quality/layer classes. `harmonic_minor`
  graduates out of Advanced Topics (melodic minor + III+ stays reserved).
- Scene router: all 12 leaves route to `functional_progression` and build
  valid scenes with the true chord qualities (E major V, G#° vii° in A
  minor); the chord-never-on-a-key-node gate holds.
- Tests: new `tests/test_harmonic_minor.py` (26 tests: engine → specs →
  MCQ/accidental rendering → roles → curriculum → scenes → echo);
  `test_functional_equivalence_rejects_minor_mode` flipped to assert the
  honest minor build. Full suite 1094 passed; all 17 JS node suites pass.
