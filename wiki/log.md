# Wiki Session Log

Append one entry per session that modifies the vault. Never rewrite past entries.

## 2026-08-17 scaffold | Ticket 01 — vault scaffold + governance schema

- Created the Obsidian vault: `.obsidian` config, 11 domain folders (`fundamentals`, `intervals`, `scales-keys`, `chords`, `harmony`, `cadences`, `minor-modes`, `sevenths`, `chromaticism`, `musicianship`, `glossary`).
- Wrote `CLAUDE.md` governance: purpose/scope, the one-directional Lab/Atlas reference invariant, naming conventions, canonical ownership, mandatory page template, frontmatter schema (with reserved `lab_refs`/`atlas_refs`), stub policy, cross-linking protocol, pedagogical style rules, lint checklist.
- Seeded `index.md` (empty per-domain tables) and this log.
- Lint: n/a — no content pages yet; validator arrives with ticket 02.

## 2026-08-17 validator | Ticket 02 — lab/atlas reference convention + wiki validator

- Defined `lab_refs`/`atlas_refs` semantics in `CLAUDE.md` (curriculum node ids verbatim; closed Atlas-surface vocabulary) and documented the validator as the acceptance gate.
- Validator landed at `tools/validate_wiki.py` (repo tooling; reads the app, never modifies it) with tests in `tests/test_wiki_validator.py`.
- Seed pages: `chords/Triad.md`, `scales-keys/Circle of Fifths.md` (cross-linked, real curriculum/Atlas ids) plus stubs `intervals/Third.md`, `scales-keys/Major Scale.md` for their Prerequisites links (stub policy); index tables + statistics updated.
- Deliberate-failure demo: `Triad.md` briefly cited `lesson:triad_qualitees` — validator reported `[lab_ref] chords/Triad.md: 'lesson:triad_qualitees' is not a node id in the live curriculum tree` and exited 1; fixed back to `lesson:triad_qualities`.
- Post-review hardening: duplicate name/alias detection, folder-qualified wikilinks rejected, nested-page rejection, template headings ignore code fences.
- Lint: `python -m tools.validate_wiki` → OK.

## 2026-08-17 fundamentals | Ticket 03 — fundamentals & notation layer

- 14 new `active` pages in `fundamentals/` (all `level: foundation`), forming a connected mini-graph in two strands: pitch naming (Note Names → Keyboard Geography → Octave / Semitone → Whole Tone → Accidental → Enharmonic Equivalence → Pitch Class) and notation (Staff → Clef → Ledger Line → Grand Staff; Beat and Measure → Time Signature).
- Lab/Atlas refs where a real drill exercises the concept: `cur` on Grand Staff and Pitch Class (grand-staff reading and pitch-class grading span the whole curriculum — cited once each on the page that owns the claim, not on every sub-concept); `lesson:tech_warmup` / `lesson:tech_arpeggios` / `cat:technique` for keyboard, octave, and rhythm pages; `lesson:scales_major` for the scale-step pages; `lesson:hm_one_accidental` for Accidental; `lesson:circle_overview` + `circle:fifths` for Enharmonic Equivalence; `cat:scales` + `atlas:global-map` for Note Names.
- Stub-policy stubs for forward links: `intervals/Interval.md` (ticket 04), `scales-keys/Key Signature.md` (ticket 05).
- `index.md`: fundamentals table filled, stub rows added, statistics updated (20 canonical pages, 4 domains populated).
- Two-axis review fixes (same session): corrected the octave staff-span fact (seven positions, not four); removed forward jargon (leading tone / tonic / seventh degree phrasing) from Accidental, Semitone, Whole Tone, Grand Staff; linked *triad* on first mention in Pitch Class; fixed Semitone prerequisite order; made Ledger Line the sole owner of middle C's placement (Clef and Grand Staff now defer); dropped the speculative `Meter` alias; tightened two Lab-facing claims (4/4 is the only rendered meter; circle entry opens a view, it doesn't "walk" you). Documented the `cur` root-citation convention in `CLAUDE.md`'s `lab_refs` section.
- Lint: `python -m tools.validate_wiki` → OK.
