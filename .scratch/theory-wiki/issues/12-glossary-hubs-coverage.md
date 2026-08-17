# 12 — Glossary, hub pages & coverage audit

**What to build:** The finishing layer that turns a set of pages into a lexicon. A student can open one "Start here" hub and follow a recommended learning path through the whole vault; look up any term in a single canonical glossary; and every curriculum category in the app is provably reinforced by at least one wiki page. The vault ends lint-clean.

**Blocked by:** 07 — Harmonic function & cadences; 08 — Minor modes; 09 — Seventh chords & figured bass; 10 — Applied chords & tonicization; 11 — Motives, polyphony & musicianship terms.

**Status:** ready-for-agent

Scope:

- `wiki/glossary/Glossary.md`: alphabetical term list, each entry a one-line definition plus a `[[wikilink]]` to the canonical page — no duplicated explanations.
- Hub pages: a "Start Here" learning-path hub ordering the domains pedagogically (fundamentals → intervals/scales → chords → function/cadences → minor → sevenths → chromaticism → musicianship), and per-domain hub links from `index.md`.
- Coverage audit: extend or run the ticket-02 validator to assert every launchable curriculum category (`cat:scales`, `cat:chords`, `cat:degrees`, `cat:functions`, `cat:cadences`, `cat:intervals`, `cat:inversions`, `cat:sevenths`, `cat:harmonic_minor`, `cat:melodic_minor`, `cat:motives`, `cat:polyphony`, `cat:technique`, `cat:advanced`, `cat:circle`) is referenced by at least one active wiki page; report any gap.
- Full lint pass: no orphans, no broken links, no stubs left unjustified, index in sync, log updated.

- [ ] Glossary covers every canonical page's headline term with a wikilink, no duplicated definitions
- [ ] "Start Here" hub exists and links every domain in pedagogical order
- [ ] Coverage audit shows every curriculum category referenced ≥1 time (or documents the accepted gap)
- [ ] Full-vault validator/lint pass is green
- [ ] `index.md` statistics section and `log.md` final entry written
