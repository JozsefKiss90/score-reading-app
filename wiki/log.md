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

## 2026-08-18 intervals | Ticket 04 — intervals layer

- Expanded the two ticket-03 stubs to `active` (`Interval`, `Third`) and added four new `active` pages in `intervals/`: `Perfect Fifth`, `Tritone`, `Interval Inversion`, `Consonance and Dissonance`. All `level: core`, fully cross-linked to the fundamentals strand (Semitone, Whole Tone, Octave, Staff, Pitch Class, Enharmonic Equivalence) and forward to `Triad`.
- Lab/Atlas refs: `cat:intervals` + `lesson:interval_layers` on Interval (the category's one lesson is theory-only — 0 exercise leaves — so "In the Lab" prose routes the actual drilling to the triad-quality drills); `lesson:interval_layers` + `lesson:triad_qualities` on Third; `lesson:triad_qualities` on Tritone and Consonance and Dissonance; `atlas:interval-layer-map` on the layer pages; `circle:fifths` on Perfect Fifth.
- Stub-policy stubs for the Tritone page's forward links: `sevenths/Dominant Seventh Chord.md` (ticket 09), `chromaticism/Applied Dominant.md` (ticket 10).
- `Triad.md` Related Concepts updated to link the now-real interval pages (link-only edit; `updated` unchanged).
- `index.md`: intervals table filled (6 rows), sevenths/chromaticism stub rows added, statistics updated (26 canonical: 22 active, 4 stubs; 6 domains populated).
- Lint: `python -m tools.validate_wiki` → OK (26 pages).

## 2026-08-19 scales-keys | Ticket 05 — scales, keys & the circle of fifths

- Expanded the two earlier stubs to `active` (`Major Scale`, `Key Signature`) and added five new `active` pages in `scales-keys/`: `Key`, `Scale Degree`, `Natural Minor Scale`, `Relative and Parallel Keys`, `Transposition`. All `level: core`, cross-linked to fundamentals (Semitone, Whole Tone, Note Names, Accidental, Octave, Clef, Staff) and intervals (Interval, Perfect Fifth).
- `Leading Tone` created as a `scales-keys` stub — canonical home chosen per `CLAUDE.md`'s own ownership example (first needed pedagogically here, when Scale Degree names 7̂); ticket 08 expands it in place.
- Scale Degree page names all seven degrees (tonic → leading tone, subtonic in natural minor) and maps them to the Lab's degree drills (fix one degree, transpose through 12 keys).
- Lab/Atlas refs: `cat:scales` + `lesson:scales_major` + `atlas:global-map` on Major Scale; `cat:scales` on Key; `lesson:circle_overview` + `circle:fifths` on Key Signature; `cat:degrees` + `lesson:degrees_major` + `lesson:degrees_minor` + `atlas:global-map` on Scale Degree; `lesson:scales_minor` + `lesson:degrees_minor` on Natural Minor Scale; `lesson:circle_overview` + `lesson:scales_minor` + `circle:fifths` on Relative and Parallel Keys; `cat:degrees` + `lesson:motive_transposition` + `atlas:transposition-matrix` on Transposition.
- Stub-policy stubs for forward links: `minor-modes/Harmonic Minor Scale.md`, `minor-modes/Melodic Minor Scale.md` (ticket 08), `musicianship/Motive.md` (ticket 11).
- `Circle of Fifths.md`: Prerequisites and Related Concepts now link the real Key Signature / Relative and Parallel Keys / Transposition / Scale Degree pages; ticket-05 placeholder notes removed (link-only edits; `updated` unchanged).
- `index.md`: scales-keys table filled (9 rows), minor-modes/musicianship stub rows added, statistics updated (35 canonical: 29 active, 6 stubs; 8 domains populated).
- Two-axis review fixes (same session): linked Grand Staff / Ledger Line / Accidental at first body mention in Key Signature and de-linked later mentions; de-linked repeat body links (Key in Major Scale, Relative and Parallel Keys in Natural Minor Scale, Transposition in Key); glossed *diatonic* inline at first use in Major Scale; added `lesson:degrees_minor` to Natural Minor Scale (its "In the Lab" describes the minor degree drills); trimmed Scale Degree's confusion 4 to defer the subtonic detail to Natural Minor Scale; dropped speculative aliases (`Tonal Centre` on Key, `Minor Scale` on Natural Minor Scale); simplified Circle of Fifths' Related Concepts to pure links so the edit stays link-only.
- Lint: `python -m tools.validate_wiki` → OK (35 pages).

## 2026-08-19 chords | Ticket 06 — triads, Roman numerals & inversions

- 5 new `active` pages in `chords/`: `Triad Quality`, `Diatonic Triads`, `Roman Numeral`, `Chord Inversion`, `Figured Bass` — all `level: core`, cross-linked to intervals (Third, Perfect Fifth, Tritone, Interval, Interval Inversion, Consonance and Dissonance) and scales-keys (Major Scale, Natural Minor Scale, Scale Degree, Key, Transposition, Circle of Fifths).
- `Triad.md` reworked to canonical-ownership shape: Explanation now names the members (root/third/fifth) and defers the quality table to `Triad Quality` and the per-degree pattern to `Diatonic Triads`; Related Concepts links the new pages (substantive edit; `updated` bumped).
- Figured-bass page matches the drills' exact triad vocabulary (5/3, 6 as shorthand for 6/3, 6/4; figures attach to numerals as ii6 / I6/4; the figure is graded — demanded member must be the lowest sounding note). Doubling/spacing covered at the Lab's depth as a section of `Chord Inversion` (pitch-class grading, octave doubling, bass-only positional demand) rather than a page of its own — deeper voicing/SATB material belongs to ticket 07's harmony domain.
- Lab/Atlas refs: `cat:chords` + `lesson:triad_qualities` on Triad (unchanged) and Triad Quality; `lesson:scales_major` + `lesson:scales_minor` on Diatonic Triads; `cat:degrees` on Roman Numeral; `cat:inversions` + `lesson:chord_inversions` on Chord Inversion; `lesson:inversion_cadence_bridge` + `lesson:bass_dictation` on Figured Bass; `atlas:quality-matrix` / `atlas:global-map` on the pages whose Atlas sections describe those views.
- Stub-policy stubs for forward links: `cadences/Cadential Six-Four.md` (ticket 07 expands; both inversion pages need the function-changing exception) and `harmony/Harmonic Function.md` (ticket 07; "function survives inversion" claim needs its term).
- Link-only edits (no `updated` bumps): Interval Inversion → [[Chord Inversion]] (first body mention + Related Concepts); Scale Degree → [[Roman Numeral]]; Major Scale and Natural Minor Scale → [[Diatonic Triads]].
- `index.md`: chords table filled (6 rows), harmony/cadences stub rows added, statistics updated (42 canonical: 34 active, 8 stubs; 10 of 11 domains).
- Two-axis review fixes (same session): moved the [[Pitch Class]] link to first body mention in Chord Inversion and de-linked the later one; de-linked the repeat body mention of Interval Inversion in its Common confusions; scoped the Why-it-matters grading claim to block drills (arpeggiated drills grade an ordered walk, not lowest-note) and corrected the lesson title to *Natural minor inversions*; linked/deferred forward jargon in Triad Quality and Roman Numeral (seventh-chord and function/inversion mentions), glossed M3/m3 at first use; Triad Quality now defers the per-degree quality layout to Diatonic Triads instead of restating it; dropped speculative per-quality aliases; trimmed the Cadential Six-Four stub to the one-paragraph-definition shape. Kept the numeral sequences on Roman Numeral (they demonstrate case-encoding, the page's own subject; Diatonic Triads owns notes+qualities) and doubling/spacing as a Chord Inversion section (Lab-depth, documented above).
- Lint: `python -m tools.validate_wiki` → OK (42 pages).
