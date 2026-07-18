# 02 — Content truth fixes (F2, F3-prose, F7)

**What to build:** Three learner-facing corrections so nothing on screen is wrong today: (a) I–V–vi–IV is re-tagged as a progression ("axis / deceptive motion inside a loop"), with the V–vi two-chord leaf kept as the deceptive exemplar; (b) the cadence catalogue stops being duplicated as two categories — one catalogue, two render variants (block / SATB) under one category, with cadence-type enums aligned (subtonic included) and label style unified; (c) the I6/4 lesson prose stops claiming unqualified tonic function for second inversion (the full cadential-6/4 module lands later in ticket 16).

**Blocked by:** None — can start immediately.

**Status:** ready-for-human

- [x] No curriculum or Atlas surface labels I–V–vi–IV "deceptive"; the V–vi leaf remains the deceptive exemplar.
- [x] Cadences and Voice Leading no longer duplicate the same 13-entry catalogue; one catalogue renders as two variants under one category.
- [x] Cadence type enums agree across curriculum and analysis spans; label style (words vs romans) is consistent.
- [x] The I6/4 lesson no longer presents second inversion as purely tonic function.

**Plan:** docs/curriculum_expansion_plan.md §1.2 F2, F3, F7

## Comments

**Implemented** (branch `fable_refactor`):

- **F2** — I–V–vi–IV re-tagged `axis` in `curriculum._CADENCE_CATALOG`, `atlas._EXTRA_CADENCES` and `harmonic_network.CADENCE_CATALOGUE` (was `mixed` there), with the blurb "deceptive motion (V → vi) inside a repeating loop that ends on IV". V–vi stays the only deceptive-tagged cadence (tested).
- **F7** — the Voice Leading category is gone; its `voice_leading_cadences` lesson (same lesson/group/leaf ids, so progress survives) now lives under Cadences, so the category holds 26 leaves: 13 block + 13 SATB variants, pairwise cross-linked and both mapped to the same Atlas cadence node. VL concept comes from the catalogue family (`type`→cadence, `progression`→voice_leading) instead of chord count; the two minor progression demos were re-tagged accordingly and all cadence demos now carry an explicit `cadence_type`. Canonical enum `harmonic_roles.CADENCE_TYPES` (subtonic, aeolian, axis included) is enforced by `LabExperimentSpec.validate()` and `ScoreCadenceSpan.validate()`; `VII–i` is `subtonic` in the network catalogue too. Atlas two-chord cadence labels unified to roman style ("V–I" not "Authentic"), which renames those Atlas node ids (`cadence:Authentic_major` → `cadence:V_I_major`; lookups are token-based, and pre-existing `ex:drill_atlas_function_Authentic_*` progress entries were orphaned by an earlier change, not this one — curriculum leaf ids are unchanged).
- **F3-prose** — the inversion lessons (`curriculum.py`) and the lab inversion explanation (`lab_explanations.py`) now say function *usually* survives inversion and name the cadential 6/4 dominant-embellishment exception; the "a later topic" throwaway is replaced pending ticket 16.
- Tests: `tests/test_content_truth.py` (16 tests) locks all three fixes; `test_curriculum_cadences.py`/`test_curriculum.py` updated to the merged structure; audit docs regenerated.
