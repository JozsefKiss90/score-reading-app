# 19 — G5c: applied-chord ramps + ear stage

**What to build:** The full difficulty ramp for applied chords: intruder position goes from fixed to random; the target set widens from V7/V to V7/IV, V7/ii, and vii°7/V (needs the diminished-seventh tetrads); keys ramp outward by circle-of-fifths distance; and the *ear* stage lands — playback with notation hidden, the learner clicks the position of the chromatic chord while listening, then answers an MCQ for which degree got tonicized. Plus "dominant chains" (V/V/V…) as a circle-of-fifths performance drill. Mastery uses the existing thresholds (≥80% completed, ≥95%×3 mastered).

**Blocked by:** 17 — G5a tracer; 10 — G1b seventh qualities (vii°7/x needs °7); 07 — echo-play machinery (ear stage).

**Status:** ready-for-human

- [x] All four ramp axes work: position, target set, key distance, visual→ear.
- [x] vii°7/x drills are live.
- [x] The ear stage is completable without notation and counts toward the same mastery record.
- [x] A dominant-chains performance drill exists.

**Implementation notes (2026-08-08):** shipped on `fable_refactor`. 380 leaves
(363 + 17), fingerprint pinned in `tests/test_applied_chords.py` and
`tests/curriculum_node_test.js`.

**Theory.** `_APPLIED_HEADS` became the public `APPLIED_HEADS`, mapping each
head to `(root rule, quality)`: `V`/`V7` build a fifth above the tonicised
triad, `vii°7` a semitone below it (spelled on the letter below — a leading
tone is always the momentary key's seventh degree). One builder serves both
(`build_applied_chord`); `build_applied_dominant` is now its dominants-only
face (as `build_dominant_seventh` is of `build_seventh_chord`) and refuses a
`vii°7/x` token rather than quietly building it. Every ticket-17 honesty gate
is unchanged and shared: exact target-roman match, no tonic target, no
diminished/augmented target. `applied_tokens_for_mode(mode, heads=…)` gained
the filter the network needs.

**The ramp is derived, not typed** (`harmony/applied_ramp.py`, pure):
`applied_progression(token, position)` builds the phrase *around* the intruder
— `position` chords of the key's cushion, then the applied chord and its
target (the resolution is not optional), then a cadential tail that never
repeats the target; `keys_by_fifths_distance` reads distance off each key's own
signature; `dominant_chain(depth)` walks the circle anticlockwise until a
degree refuses to be tonicised (major stops at 5 links, `vii°`). The ticket-17
leaves now come from the same function — the flagship `I–vi–V7/V–V–I` is
literally `applied_progression("V7/V", 2)`, so the ramp's position axis is a
parameter rather than a second shape.

**Ear stage = the spot leaf's 🎧 twin.** `APPLIED_STAGES` gained `ear`, which
compiles to `answer_mode="spot"` + `presentation="echo"`; `is_echo_eligible`
now accepts applied `spot` leaves and `echo_variant` accepts `spot` specs, so
the same drill is reachable both ways and a test pins that the twin and the
ear stage compile identically. That is what satisfies the mastery criterion:
the twin records under the **visual leaf's node id** (ticket 07's rule), so the
visual→ear axis needs no leaves of its own. `presentation="echo"` +
`answer_mode="spot"` was refused by ticket 17 (no veiled answer surface
existed); the veil now leaves **bar positions** clickable, which name no chord.
The payload's new `SPOT_FOLLOWUP` block (only on the veiled variant — with the
score in front of you the answer is readable off it) carries the plan's second
question, *which degree got tonicised?*, options derived from the mode's
tonicisable targets. The drill finishes — and the veil lifts — only when both
answers land, so the revealed notation can never answer the follow-up.
Cross-language contract: `tests/ear_spot_contract_check.js`, driven from
`tests/test_applied_ramps.py`.

**Curriculum.** New lesson *Advanced Topics › Applied chords: the ramp* with
one group per axis: 3 moved positions, 3 `vii°7/x` spots + 3 resolves, 4 keys
(G, F, D, Bb), 4 dominant chains. The chains are **native** function drills,
not `applied_chord` experiments — a chain holds several applied chords, each
resolving into the next dominant rather than into its own diatonic target, so
it is a performance run, not an intruder hunt.

**Scope decision — the network stays dominants-only.** `vii°7/x` nodes would
need their own node class and relation in `secondary_dominant_network_v1`
(calling a leading-tone seventh an "applied dominant" is exactly the kind of
label this repo refuses), so the template now filters explicitly with
`APPLIED_DOMINANT_HEADS` and the *scene* carries the new family: it draws the
tonicisation arrow for `vii°7/x` on the same evidence one step removed — the
network's own arrows say that degree is tonicisable, and the engine built this
chord as the tonicisation of exactly that degree. Role labels follow the head,
so `vii°7/V` is never described as a dominant.

**Review outcomes.** The spec axis caught two real defects, both fixed. (1) The
`vii°7/x` resolve leaves emitted no tritone metadata — `tritonePcs` was gated on
`dominant_seventh`, so the three new leaves promised "the tritone resolves" and
highlighted nothing; the resolving pair is now a per-quality table
(`_APPLIED_TRITONE_TONES`: V7's third+seventh, °7's root+diminished fifth — in
C both are F#+C resolving to G+B). (2) The scene drew a `vii°7/x` arrow under
`relation="secondary_dominant_of"`, and that id is learner-visible in the scene
detail panel — exactly the mislabel cited for keeping these chords out of the
network; the scene now emits `applied_leading_tone_of` for the leading-tone
family (`_APPLIED_FAMILY`, keyed by the engine's own root rule).

Three findings were deliberate and stand: the ticket-17 leaves are now derived
by `applied_progression`, which changed two of their phrases (`V7/ii` and
`V7/vi`) while keeping their ids — the skill and the progress key are the same,
and one derivation beats two content paths; the position axis is *varied*, not
runtime-random (specs compile deterministically here — ids, payloads and scene
routing all depend on it), which is what "the ear cannot rely on position"
requires; and the dominant chains inherit the standard 🎧 twin every native
drill leaf owns.

**Review follow-ups (standards axis).** One slug rule for applied tokens
(`theory.applied_token_slug`, `°`→`dim` as the Atlas/Circle schemes already
spell it) now backs the network node id, the overlay proxy id and the
curriculum exercise ids; `exemplar_key(mode)` replaced three copies of the
"C for major, A for minor" rule; `applied_target_options` moved to the theory
module (the payload builder must not depend on curriculum content); the
scene's applied role words index `APPLIED_HEADS` instead of defaulting an
unknown head to "dominant"; and `_applied_spec` raises for a stage it has no
leaf text for rather than falling through to the spot wording.

**Two honesty bugs found on the way** (both latent before this ticket, both
reachable by its content): `_chord_entity_type` typed a *fully diminished
seventh* as `diminished` — the entity that names the leading-tone **triad** —
so the tetrad test now comes first (this also fixes harmonic minor's `vii°7`
scenes); and `_atlas_refs_for_native` / `_circle_refs_for_native` mapped an
applied chord onto the degree node it merely shares a root with (A7 = V7/ii in
C would have claimed the submediant), which the dominant chains would have been
the first content to trigger — applied chords now claim the key context and
nothing else, matching the Lab path.

**Plan:** docs/curriculum_expansion_plan.md §3 G5, §7 (ramp + mastery)
