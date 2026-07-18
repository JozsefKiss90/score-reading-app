# 35 — One cadence catalogue (follow-up to 01/02)

**What to build:** A single cadence catalogue behind all layers — the same move ticket 01 made for function vocabulary. Today the catalogue exists three times in parallel: `harmony/curriculum.py` `_CADENCE_CATALOG` (tokens, label, mode, cadence_type, family), `harmony/atlas.py` `_CADENCE_TYPES` + `_EXTRA_CADENCES` + `_PROGRESSION_TYPE`, and `harmony/harmonic_network.py` `CADENCE_CATALOGUE`. Ticket 02 aligned their *types* (canonical `harmonic_roles.CADENCE_TYPES`, axis/subtonic re-tags) and drift-tests keep them agreeing, but the F2 re-tag itself was a three-file edit with a near-identical comment triplicated — every future catalogue change (ticket 16 adds PAC/IAC, the Phrygian half family, and the cadential 6/4) will be a three-file edit until the extraction lands.

Extract one source module (natural home: alongside `CADENCE_TYPES` in `harmony/harmonic_roles.py`, or a sibling `harmony/cadence_catalogue.py` if the entry shape warrants it) holding the catalogue entries — tokens, label, mode, cadence type, family (type vs progression) — ideally as a small dataclass rather than the current 5-tuple (the code-review pass flagged the tuple as a data clump; a `CadenceEntry` could also absorb the family→lab-concept rule `curriculum._vl_concept`). Curriculum, Atlas and the harmonic network then *derive* their views (Atlas needs its label/slug per entry; the network needs only the per-mode pattern lists). Honor the layering: `harmonic_roles`/the new module must stay pure (imports theory only), since atlas, curriculum, lab_spec and harmonic_network all import it.

**Blocked by:** None — 01 and 02 have landed (commit fb97c6f). Should land **before** ticket 16 (G3), whose new cadence types otherwise mean another three-file edit; 16's acceptance line "the cadence catalogue and the cadence-resolution template render the new types automatically; enums stay aligned" is exactly what this extraction buys.

**Status:** ready-for-agent

- [ ] One catalogue module owns every cadence entry (tokens, label, mode, cadence type, family); curriculum `_CADENCE_CATALOG`, atlas `_CADENCE_TYPES`/`_EXTRA_CADENCES`/`_PROGRESSION_TYPE`, and harmonic-network `CADENCE_CATALOGUE` are derived views, not hand-maintained copies.
- [ ] Adding or re-tagging a cadence is a one-file change; a drift test fails if any derived view disagrees with the source (extend `tests/test_content_truth.py`'s enum checks into full-catalogue equality).
- [ ] No id or payload churn: atlas cadence node ids (`cadence:V_I_major` style), curriculum leaf ids, and network path payloads stay byte-identical — this is a pure extraction, not a content change.
- [ ] Layering preserved: the source module imports at most `theory.diatonic_harmony` (no harmony-package imports), so every current consumer can import it without cycles.

**Plan:** docs/curriculum_expansion_plan.md §1.2 F7 (fix column: "One catalogue"), §9.5 (the single-source idiom); precedent: ticket 01's `harmonic_roles` derivations. Origin: code-review finding on commit fb97c6f (Duplicated Code / Shotgun Surgery — "the cadence catalogue exists three times").
