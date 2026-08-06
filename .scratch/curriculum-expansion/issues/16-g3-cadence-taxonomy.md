# 16 — G3: cadence taxonomy repair + the cadential 6/4

**What to build:** A truthful cadence ontology. PAC vs IAC (same V–I, soprano on 1̂ vs 3̂/5̂) with eye and ear discrimination pairs; the full half-cadence family (ii–V, IV–V, i–V, and Phrygian iv6–V in minor); a deceptive-vs-authentic reflex drill (V→? by ear); and the cadential 6/4 taught as a dominant embellishment — play IV–I6/4–V7–I, then relabel the same sounds as IV–V(6-5/4-3)–I. Cadence drills escape their single reference key via the existing transposition-orbit pattern.

**Blocked by:** 02 — content truth fixes (catalogue/enum groundwork); 13 — G2a harmonic minor (Phrygian needs the real minor V). Ear-discrimination stages additionally need 05/06/07.

**Status:** ready-for-human

- [x] PAC and IAC exist as distinct leaves with discrimination drills (no more undifferentiated "authentic").
- [x] The half-cadence family includes approaches from any predominant, including Phrygian iv6–V.
- [x] The cadential 6/4 lesson + relabel drill ship; the learner can explain why "I6/4" is not tonic here.
- [x] The cadence catalogue and the cadence-resolution template render the new types automatically; enums stay aligned.
- [x] Cadence drills are available in multiple keys via transposition orbits.

**Plan:** docs/curriculum_expansion_plan.md §3 G3, §1.2 F8, F9

## Comments

2026-07-18: Ticket 35 (one cadence catalogue) extracts the triplicated catalogue (curriculum / atlas / harmonic network) behind one source. It is not a hard blocker, but landing 35 first makes this ticket's new cadence types a one-file catalogue change instead of a three-file edit — see 35's third acceptance box for the no-churn guarantee it must hold.

2026-08-07: **Implemented** (branch `fable_refactor`). Ticket 35 had not landed, so the ii–V / IV–V half entries are the anticipated three-file edit (curriculum `_CADENCE_CATALOG` 13→15, atlas `_CADENCE_TYPES`, network `CADENCE_CATALOGUE` major 8→10 paths) — the extraction remains for 35.

- **Enum** — `harmonic_roles.CADENCE_TYPES` += `perfect_authentic`, `imperfect_authentic`, `phrygian`; `authentic` stays the family label a soprano-less block drill may honestly claim. The scene generators' `("V","I") → "authentic (perfect)"` fallback was the F9 lie and is now `"authentic"`.
- **Soprano seam** — `CadenceParams.soprano_degrees` (VL render only; each degree validated as a chord tone) drives `_satb_progression`: the demanded tone's rotation is chosen and may octave-shift toward the previous soprano (tenor kept above the bass). Unconstrained voicings are byte-identical to before.
- **PAC vs IAC** (`lesson:pac_iac`) — 3 eye leaves (soprano 7̂→1̂ / 2̂→3̂ / 5̂–5̂ over one V–I) + 3 ear twins via the new `dictation:"soprano"` (mirror of ticket 11's bass dictation: full SATB playback, top line graded; JS demands the played note be the *highest* sounding — `harmony_trainer.js` + echo Test K).
- **Half family** (`lesson:half_cadence_family`) — ii–V / IV–V land in the catalogue (block + SATB automatically); i–V ships as native harmonic-minor drills across the 12 minor keys; Phrygian iv6–V as figured block cadences in A/E/D minor (♭6̂ bass graded), `cadence_type:"phrygian"`. `_atlas_refs_for_lab` learned the ticket-13 natural-minor-twin rule (harmonic-minor lab cadences previously emitted unresolvable refs).
- **Cadential 6/4** (`lesson:cadential_64`) — hear/relabel pairs (same `IV–I64–V7–I` sounds) in C/G/F, cross-linked; the honesty fix is in the *engine*: `_gen_voice_leading` annotates any tonic-spelled 6/4 before a dominant as "Cadential 6/4 — dominant in function", on every surface. Inversion-lesson prose now points at the lesson (closes the F3 "coming soon").
- **Reflex + orbits** — `🎧 V→?` echo+MCQ(roman) pair (V–I / V–vi in C,G,F) under the two-chord lesson; `lesson:cadence_orbits` transposes all 8 two-chord types through the 12 keys (16 chunked native specs, echo twins automatic) — the F8 fix.
- **Counts** — 312→351 leaves (+4 catalogue variants, +35 taxonomy); Cadences category 26→65. Audit `duplicateExerciseIds` now applies to launched (`drill`) ids only: PAC/IAC voicings and the relabel drill share their root-position bridge skeleton *by design* (experiment ids stay unique).
- **Tests** — new `tests/test_cadence_taxonomy.py` (33) + JS echo Test K; catalogue-contract suites re-scoped to the six catalogue groups; full suite 1204 Python + all JS node harnesses green; audit docs regenerated.

Two-axis code review (standards + spec sub-agents) ran before commit; fixes applied from it:

- The relabel drill now actually relabels: display-only `CadenceParams.relabel` tokens rename what each measure's annotation calls the chord (B leaves show `V(6–4)` / `V7(5–3)`; sounds, grading and bridge ids byte-identical — tested), and the engine's leading annotation bit says "dominant (cadential 6/4)" instead of plain "tonic" on any detected cadential 6/4.
- `graph_scene_generators._CADENCE_NAMES[("iv","V")]` corrected to plain `"half"` — root-position iv–V is not Phrygian (that needs iv6's bass).

Reviewed-and-accepted limitations (deliberate scope):

- PAC/IAC eye+ear live in C major only — the soprano distinction is key-independent, and F8's multi-key complaint is answered by the orbit lesson (all 8 two-chord types × 12 keys) plus the 3-key 6/4 and Phrygian spreads.
- Ear leaves announce their content in the curriculum tree title (platform-wide A1 v0 convention; the in-drill veil redacts it). True blind discrimination needs randomized targets — tickets 17 (intruder) / 22 (adaptive).
- `perfect_authentic` / `imperfect_authentic` / `phrygian` are enum types + leaf tags, not block-catalogue entries: a soprano-less block drill may not claim "perfect", and a figured iv6 cannot take the catalogue's SATB render. Enum alignment is drift-tested.
- `curriculum_audit` bridge-duplicate check narrowed to `concept=="drill"` leaves repo-wide: the bridge id was an over-strict proxy for launch identity of lab concepts (their identity is the experiment id, still checked); native passthroughs stay strict.
