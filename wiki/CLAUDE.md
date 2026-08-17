# Wiki Governance Schema

This vault is the **music theory lexicon** for the Score Reading App. It explains the theory the Harmony Lab and Harmony Atlas *assume* — terms, concepts and definitions a student needs before or alongside the drills. Every session that modifies the wiki MUST read this file first and follow it.

## Purpose and scope

- **In scope**: music theory terms, concepts, definitions, and the pedagogical explanations behind them (scales, intervals, chords, harmonic function, cadences, minor modes, seventh chords, chromaticism, musicianship vocabulary).
- **Out of scope**: application documentation, code architecture, implementation details, practice-method instruction beyond what a term needs to be understood. The app's own docs live in `docs/`; this vault never duplicates them.
- **Role relative to the app**: the Lab teaches by drilling; the wiki teaches by explaining. In-app blurbs exist (short definitions, practice advice); wiki pages go *deeper* — the why, the construction, the common confusions — and never merely restate the blurb.

## The one-directional reference invariant

Wiki pages reference the Lab, Atlas, trainer, and curriculum — **never the reverse**.

1. No file outside `wiki/` is ever created, modified, or deleted for the wiki's sake. (Sole exception: the wiki validator tooling introduced by ticket 02, which lives outside the vault and only *reads* the app.)
2. The Lab, Atlas, and curriculum code remain fully functional and unaware of the wiki's existence.
3. Wiki pages cite app surfaces via frontmatter `lab_refs` / `atlas_refs` (semantics defined when the validator lands; the fields are reserved now and may be empty lists until then).

## Vault structure

```
/wiki
  /fundamentals   — notation & prior-knowledge layer: staff, clefs, note names,
                    accidentals, semitone/whole tone, octave, keyboard geography
  /intervals      — interval number & quality, thirds, fifths, tritone, inversion
  /scales-keys    — major/natural-minor scales, keys & signatures, scale degrees,
                    relative/parallel keys, circle of fifths, transposition
  /chords         — triads, qualities, diatonic triads, Roman numerals,
                    chord inversion, figured bass for triads
  /harmony        — harmonic function (T/PD/D), progressions, SATB & voice-leading
                    vocabulary (common tones, tendency tones, resolution)
  /cadences       — cadence taxonomy: PAC, IAC, half, deceptive, plagal,
                    Phrygian half, cadential 6/4
  /minor-modes    — harmonic & melodic minor, leading tone in minor, III+,
                    minor-key function
  /sevenths       — seventh chords & qualities, V7 and its inversions/figures,
                    tritone resolution, bass dictation vocabulary
  /chromaticism   — applied dominants, applied leading-tone chords,
                    tonicization vs modulation, dominant chains
  /musicianship   — motive, polyphony & texture, performance-notation vocabulary
                    (articulation, slurs, fingering, accents, arpeggio),
                    ear-training vocabulary
  /glossary       — the single alphabetical glossary page
```

A page lives in exactly one domain folder, and its frontmatter `domain` must match the folder name.

## Naming conventions

- **File names**: Title Case with spaces (e.g. `Circle of Fifths.md`, `Dominant Seventh Chord.md`).
- **Canonical concept pages** are named after the concept itself (`Triad.md`, not `About Triads.md`).
- **Wikilinks**: always `[[Page Name]]` (or `[[Page Name|display text]]`), never raw markdown links for internal references.
- **Musical symbols**: page *names* use ASCII words (`Cadential Six-Four`, `Diminished Seventh Chord`); page *bodies* use proper symbols (6/4, ♯, ♭, ♮, °, ø) as the drills render them. Symbol-heavy synonyms go in `aliases`.

## Canonical ownership

1. Each concept has **exactly one** canonical page. Every other mention links to it.
2. Before creating a page, search the vault (name + synonyms) and check `index.md`. If the concept is covered, update the existing page instead.
3. Never write the same explanation in two places — link.
4. When a concept could live in two domains (e.g. *Leading Tone* touches scales-keys and minor-modes), pick the domain where the concept is *first needed pedagogically*, and have the other domain's pages link to it.

## Page template

Every canonical page with `status: active` MUST contain these sections, in this order (omit a section only when genuinely not applicable — e.g. a glossary or hub page). Pages with `status: stub` or `status: draft` are exempt until they become `active`:

```markdown
# {Concept Name}

## Definition
One or two sentences a beginner can hold onto. No forward jargon.

## Why it matters
What this concept unlocks — musically and in the app's drills.

## Prerequisites
Wikilinks to the concepts this page assumes, in learning order.

## Explanation
The teaching body: construction, examples, notation. Prefer concrete
examples in the keys the drills use most (C major, G major, A minor).

## In the Lab
Which drills exercise this concept and what the student will be asked
to do there. Human phrasing in the body; exact ids go in `lab_refs`.

## In the Atlas
Which Atlas views visualise this concept (omit if none).

## Common confusions
The mistakes and misreadings students actually make, and the
disambiguation for each.

## Related Concepts
Sibling and follow-on wikilinks: where to go next.
```

## Frontmatter schema

Every page (except `index.md`, `log.md`, `CLAUDE.md`) starts with this block. Flat YAML only — no nested objects. No keys beyond those listed here.

```yaml
---
type: concept          # concept | lesson-support | glossary | hub
domain: chords         # must equal the page's folder name
level: core            # foundation | core | advanced
status: active         # active | stub | draft
created: 2026-08-17    # set once, never modified
updated: 2026-08-17    # refreshed on substantive content edits only
aliases: []            # optional; alternative names, flat string array
lab_refs: []           # curriculum node ids, verbatim (see "Lab and Atlas references")
atlas_refs: []         # Atlas surface ids from the closed vocabulary (same section)
---
```

### Enum semantics

- **type** — `concept`: a canonical theory page. `lesson-support`: a page whose unit is a Lab lesson rather than a single concept. `glossary`: the glossary page. `hub`: an index/learning-path page.
- **level** — `foundation`: assumed prior knowledge the Lab never teaches. `core`: directly reinforces a drilled curriculum category. `advanced`: chromaticism and beyond.
- **status** — `active`: complete and trustworthy; subject to every lint check. `stub`: intentionally minimal, awaiting expansion (see stub policy). `draft`: being written. Stubs and drafts must still carry valid frontmatter and dangling-link-free bodies, but are exempt from the template-completeness and link-count checks until they become `active`.

### Field rules

1. `domain` MUST match the directory.
2. `created` is set at page creation and never changes; `updated` changes only on substantive content edits (not link additions, typo fixes, or frontmatter corrections).
3. Enum values are append-only: never rename or remove one; additions require updating this file first.
4. `lab_refs` / `atlas_refs` hold **ids only**, verbatim from the app. Prose descriptions of drills belong in the "In the Lab" / "In the Atlas" body sections.

## Lab and Atlas references

`lab_refs` and `atlas_refs` are how a page cites the app. Ids live in frontmatter **only**; body prose uses human phrasing ("practise this in the Lab under *Triad Qualities*", "see the quality matrix in the Atlas") and never embeds an id.

### `lab_refs` — curriculum node ids

Each entry is a node id taken **verbatim** from the live curriculum tree built by `harmony.curriculum.get_curriculum()`. Any node kind is citable:

- `cat:<slug>` — a category (e.g. `cat:chords`, `cat:scales`, `cat:cadences`)
- `lesson:<slug>` — a lesson (e.g. `lesson:triad_qualities`, `lesson:circle_overview`)
- `group:<slug>` — an exercise group (e.g. `group:triads_major`)
- `ex:<slug>` — a single exercise leaf (e.g. `ex:drill_major_fullkey_block_C`)

Cite the **most specific node that matches the page's scope** — a concept page usually cites a category or lesson, not thirty leaves. The validator checks every id against the real tree, so a typo or a renamed node fails the build.

### `atlas_refs` — Atlas surface ids

Each entry names a *place in the app* the student can open — an Atlas part, the Circle of Fifths, or a network launcher — from the closed vocabulary defined in `tools/validate_wiki.py` (`ATLAS_SURFACES`):

| Id | Surface |
|----|---------|
| `atlas:global-map` | Atlas Part I — Global Diatonic Map |
| `atlas:transposition-matrix` | Atlas Part II — Transposition Matrix |
| `atlas:quality-matrix` | Atlas Part III — Quality Matrix |
| `atlas:function-map` | Atlas Part IV — Function Map (T/PD/D) |
| `atlas:interval-layer-map` | Atlas Part V — Interval-Layer Map |
| `atlas:cadence-map` | Atlas Part VI — Cadence Map |
| `atlas:progress-map` | Atlas Part IX — Progress Map |
| `atlas:graph` | Atlas Part X — Graph view |
| `atlas:learning-path` | Atlas Part XI — Learning Path |
| `circle:fifths` | Circle of Fifths view |
| `network:harmonic` | Tonal Graph launcher (`run_harmonic_network_demo.py`) |
| `network:functional` | Functional Journey launcher (`run_functional_network_demo.py`) |
| `network:score-soul` | Score Soul Graph launcher (`run_score_harmonic_network_demo.py`) |

Fine-grained Atlas *node* ids (`scale:G:major`, `degree:major:V`, …) are **not** valid `atlas_refs` — the wiki points at surfaces, not ontology nodes. Extending the vocabulary means editing `ATLAS_SURFACES` and this table together (validator tooling is the one sanctioned edit outside the vault).

### Discovering valid ids

```
python -m tools.validate_wiki --list-refs
```

prints the full `atlas_refs` vocabulary and every live curriculum node id.

### Example

```yaml
---
type: concept
domain: chords
level: core
status: active
created: 2026-08-17
updated: 2026-08-17
aliases: ["Triads"]
lab_refs: ["cat:chords", "lesson:triad_qualities"]
atlas_refs: ["atlas:global-map", "atlas:quality-matrix"]
---
```

## Stub policy (no dangling links)

A wikilink to a page that does not exist yet is a **broken link** and fails lint. When a page needs to reference a concept that has no page yet:

- If the target is planned in the current ticket's domain — create it now.
- If the target belongs to a future ticket's domain — create a **stub**: frontmatter with `status: stub`, a one-paragraph Definition, and nothing else. The future ticket expands it in place (same file name, same domain), preserving inbound links.
- Never leave a dangling `[[wikilink]]`.

## Cross-linking protocol

Every canonical page links to:

- **Prerequisites** — what must be understood first (upstream).
- **Follow-ons** — what this concept enables (downstream), in Related Concepts.
- **Siblings** — related concepts at the same level.

Targets (for `status: active` pages): at least 2 outbound and, once the page's domain is populated, at least 1 inbound wikilink. The first mention of any technical term in a page body is wikilinked; later mentions are plain text.

## Pedagogical style

1. **Define before use.** A page may only use terms that are in its Prerequisites, defined earlier on the page, or wikilinked on first mention.
2. **Why before what.** Lead with the musical purpose, then the mechanics.
3. **Concrete first.** Every abstract rule gets a concrete example in a drill-familiar key before any generalisation.
4. **Name the confusion.** If students routinely mix two things up (relative vs parallel minor, 6/4 the inversion vs 6/4 the meter), say so explicitly in Common confusions.
5. **Match the app's vocabulary.** Use the same terms, symbols, and spellings the drills display; note standard synonyms in `aliases`.

## Index and log

- `index.md` lists **every** page, grouped by domain, with a one-line summary each. Update it in the same session that adds or renames a page.
- `log.md` gets one appended entry per session that modifies the vault: date, tickets/scope, pages added/changed, lint result. Never rewrite past entries.

## Lint checklist

Run before ending any session that touched the vault (checks 1–6 are mechanised by the validator — see the Validator section; check 7 stays manual). "Page" below means every `.md` file except the structural files `index.md`, `log.md`, and `CLAUDE.md`, which are exempt from checks 1–5:

1. **Broken wikilinks** — every `[[link]]` resolves to a page or alias (all pages, including stubs and drafts).
2. **Orphans** — no `active` page with zero inbound links (hub pages excepted).
3. **Frontmatter** — present on every page, valid enums, `domain` matches directory (all pages, including stubs and drafts).
4. **Template** — no `active` canonical page missing a mandatory section, except sections genuinely not applicable per the template's own omission rule.
5. **Ref validity** — every `lab_refs`/`atlas_refs` id exists in the app (validator).
6. **Index sync** — `index.md` lists every page; no ghosts.
7. **Log** — session entry appended to `log.md`.

## Validator

The wiki validator lives at `tools/validate_wiki.py` (repo tooling, outside the vault; it only *reads* the app). Run it from the repo root:

```
python -m tools.validate_wiki               # validate wiki/ (exit 0 = clean, 1 = violations)
python -m tools.validate_wiki --list-refs   # print all valid lab_refs / atlas_refs ids
python -m tools.validate_wiki --vault PATH  # validate a different vault
```

It mechanises lint checks 1–6: frontmatter schema (enums, `domain`↔directory, flat YAML, no unknown keys), broken wikilinks (alias-aware), orphans (`active` non-hub pages with zero inbound links), template completeness for `active` canonical pages ("In the Atlas" is the one omittable section), `lab_refs` against the **live** curriculum tree, `atlas_refs` against the surface vocabulary above, and `index.md` sync (every page listed, no ghosts).

**A green validator run is the acceptance gate for every content ticket.** Its own tests live in `tests/test_wiki_validator.py` (which also asserts the shipped vault is clean).
