# 02 — Lab/Atlas reference convention + wiki validator

**What to build:** The contract that ties wiki pages to the app, and the tool that enforces it. After this ticket, a wiki author can cite a curriculum node, Atlas view, or Lab experiment in a page's frontmatter and body, and a single command verifies the whole vault: every cited id really exists in the app, every wikilink resolves, every page has schema-compliant frontmatter, and no page is orphaned. Proven end-to-end with one or two seed pages.

**Blocked by:** 01 — Vault scaffold + governance schema.

**Status:** ready-for-human

Scope:

- Define the reference convention in `wiki/CLAUDE.md`: `lab_refs` holds curriculum node ids (category ids like `cat:scales` and leaf/lesson ids) taken verbatim from the canonical curriculum tree; `atlas_refs` holds Atlas surface identifiers (Atlas parts/views, Circle of Fifths, network/graph launchers). Body prose uses human phrasing ("practise this in the Lab under *Scales*") — ids live in frontmatter only.
- References are strictly one-directional: the Lab, Atlas, trainer, and curriculum code are read, never modified.
- A validator script (repo tooling, outside `wiki/`, e.g. alongside existing test/tooling conventions) that checks: (a) every `lab_refs` id exists in the live curriculum tree built by the harmony package; (b) every `atlas_refs` id is in the documented Atlas-surface vocabulary; (c) every `[[wikilink]]` resolves to an existing page or alias; (d) frontmatter is present, enums are valid, `domain` matches directory; (e) no orphan pages (0 inbound links); (f) `index.md` lists every page. Exit non-zero on violation, with a readable report.
- One or two seed pages (they may be stubs later superseded) exercising every check, including a deliberate failure demonstrated and then fixed.
- Document how to run the validator in `wiki/CLAUDE.md` so every content ticket uses it as its acceptance gate.

- [x] `lab_refs`/`atlas_refs` semantics documented in CLAUDE.md with examples
- [x] Validator verifies lab_refs against the real curriculum tree (not a hardcoded id list)
- [x] Validator catches broken wikilinks, bad frontmatter, domain/directory mismatch, orphans, and index drift
- [x] Seed page(s) pass; an intentionally broken ref is shown to fail
- [x] No file under the Lab/Atlas/trainer/curriculum code is modified

## Comments

2026-08-17 — Implemented in commits 85fdf21 + follow-up. Validator at
`tools/validate_wiki.py` (`python -m tools.validate_wiki`, `--list-refs` for id
discovery), 31 tests in `tests/test_wiki_validator.py` including a
real-vault-clean gate. `lab_refs` = any live curriculum node id (cat:/lesson:/
group:/ex:, checked against `get_curriculum().walk()`); `atlas_refs` = closed
13-id surface vocabulary (9 Atlas parts + circle:fifths + 3 network launchers;
Parts VII/VIII deliberately excluded, documented in CLAUDE.md). Seed pages
Triad + Circle of Fifths (active) with Third + Major Scale stubs for their
Prerequisites links. Deliberate-failure demo (`lesson:triad_qualitees` → exit 1
→ fixed) recorded in wiki/log.md. Two-axis review findings addressed:
duplicate-name/alias detection, folder-qualified links rejected, nested pages
rejected, template headings ignore code fences, unused injector param removed,
ref checks deduplicated, seed-page outbound-link targets met via the stubs.
Beyond scope, kept deliberately: template-completeness check (mechanises
CLAUDE.md lint check 4) and `--list-refs`.
