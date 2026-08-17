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
- Seed pages: `chords/Triad.md`, `scales-keys/Circle of Fifths.md` (cross-linked, real curriculum/Atlas ids); index tables + statistics updated.
- Lint: `python -m tools.validate_wiki` → OK.
