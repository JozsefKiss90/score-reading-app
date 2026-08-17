# 01 — Vault scaffold + governance schema

**What to build:** An openable, governed, empty Obsidian vault at `wiki/` in the project root. A student (or agent) opening the vault in Obsidian sees the folder taxonomy, an index, and a governance file that tells any future session exactly how to add content. No theory content yet — the deliverable is the *system* that makes every later page consistent.

Adapt the generalisable machinery from the `C:\Code\el_nino\wiki` example (governance CLAUDE.md, frontmatter schema, canonical-ownership rules, page template, index/log) to a music-theory pedagogy context. Do not copy trading-specific content.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

Scope:

- Vault root `wiki/` with minimal `.obsidian` config (enough for Obsidian to open it as a vault; no plugins required).
- Folder taxonomy oriented to pedagogy, one domain per folder: `fundamentals`, `intervals`, `scales-keys`, `chords`, `harmony`, `cadences`, `minor-modes`, `sevenths`, `chromaticism`, `musicianship`, `glossary`.
- `wiki/CLAUDE.md` governance file covering: vault structure, naming conventions (Title Case, one canonical page per concept, `[[wikilinks]]` only), canonical-ownership + redundancy-prevention rules, the mandatory page template, frontmatter schema, cross-linking protocol, and a lint checklist (orphans, broken links, missing frontmatter, index sync).
- Frontmatter schema (closed enums, flat YAML): `type` (concept | lesson-support | glossary | hub), `domain` (must match directory), `level` (foundation | core | advanced), `status` (active | stub | draft), `created`, `updated`, optional `aliases`, plus `lab_refs: []` and `atlas_refs: []` (exact semantics defined in ticket 02 — reserve the fields now).
- Mandatory page template with pedagogical sections: Definition, Why it matters, Prerequisites, Explanation, In the Lab, In the Atlas, Common confusions, Related Concepts.
- `wiki/index.md` (per-domain tables, initially empty) and `wiki/log.md` (session log, seeded with the creation entry).
- A stated invariant in CLAUDE.md: the wiki references the Lab/Atlas one-directionally; no file outside `wiki/` (and the ticket-02 validator) is ever modified for the wiki's sake.

- [ ] `wiki/` opens as an Obsidian vault
- [ ] All 11 domain folders exist and match the `domain` enum in CLAUDE.md
- [ ] CLAUDE.md defines naming, canonical ownership, page template, frontmatter schema, cross-linking, and lint rules
- [ ] `index.md` and `log.md` exist and follow the governance file
- [ ] The one-directional Lab/Atlas reference invariant is stated in CLAUDE.md
