# 09 — G1a: V7 tracer bullet

**What to build:** The platform's first seventh chord, end to end. The theory engine builds the dominant seventh (its first tetrad), the score builder voices it, the Lab's roman gate accepts V7, and three drills ship in all 12 major keys with live curriculum leaves: *add-the-7th* (play V, then V7, hear the added dissonance), *tritone resolution* (the two-voice 4̂→3̂ + 7̂→1̂ frame), and full *V7→I*.

**Blocked by:** None — can start immediately.

**Status:** ready-for-human

- [x] A V7→I drill launches from a curriculum leaf, renders correctly, and grades via MIDI in all 12 major keys.
- [x] Add-the-7th and tritone-resolution drills are live.
- [x] The roman gate accepts V7 while still rejecting all not-yet-supported tokens.
- [x] Honesty gates hold: no reserved graph seam is flipped in this ticket (that is ticket 12).

**Plan:** docs/curriculum_expansion_plan.md §3 G1, §9

## Comments

**2026-08-05 (agent):** Implemented on `fable_refactor`.

- **Theory** (`theory/diatonic_harmony.py`): `_build_tetrad` (1–3–5–7 stack, quality derived from the three stacked thirds via `_TETRAD_QUALITIES`), `build_dominant_seventh` (refuses natural minor — its degree-5 seventh is v7), `SEVENTH_DEGREE_TOKENS = {"V7": 4}` as the single seventh-token vocabulary, `parse_seventh_token`, and `transpose_degree_pattern` builds the tetrad for seventh tokens. G1b widens the token table.
- **Trainer** (`exercise_spec.py`): `normalise_pattern` accepts `V7` and now *raises* on any other digit-bearing token (previously `ii7` was silently played as a ii triad); function-drill validation rejects `V7` in minor; `horizontal_degree` rejects seventh degree tokens.
- **Score builder** (`musicxml_builder.py`): generic chord voicing (block = 4-note whole chord; arpeggio = 4 quarters, rest-padding now derived), `<kind text="7">dominant</kind>` chord symbol; the trainer payload grades 4 pitch classes through the unchanged JS validator (which is length-generic).
- **Lab** (`lab_spec.py`, `lab.py`): `is_diatonic_roman` accepts exactly the supported seventh tokens and explicitly rejects other digit tokens; seventh tokens require `render="block"` (SATB voicing of sevenths is G1b/G3) and major mode; a tetrad's `LabAnnotation` claims **no** Atlas degree/triad node (base_roman honesty). Polyphonic `bass_degrees` are now octave-aware (7̂→8̂ renders B3→C4, not a falling seventh) and range-validated.
- **Curriculum** (`curriculum.py`): new live category **Seventh Chords** (`cat:sevenths`, 16 leaves): *Add the 7th* (V–V7, 2 chunked specs × 6 keys), *Tritone resolution* (12 per-key polyphonic two-voice frames, progression `["V7","I"]`, upper 4̂→3̂ over bass 7̂→1̂), *Full resolution V7→I* (2 chunked specs); reserved lesson `sevenths_more` names the G1b/G1c seam; the `adv_sevenths` stub retired from Advanced Topics. Atlas/circle refs for tetrads claim only scale + degree(base roman) + function — never the triad/quality/layer nodes. Audit registry entry added. Leaf total 231 → 247 (counts derived everywhere; the one JS pin in `curriculum_node_test.js` updated).
- **Graph scenes** (`graph_scene_generators.py`): V7 markers use the contract's (formerly reserved) `seventh` entity type (`_chord_entity_type`), with no canonical Atlas triad ref; `harmonic_network.js` already labels it ("Dominant seventh") — no JS lockstep change. The network's 12 reserved dom7 nodes are untouched (ticket 12).
- **Tests:** new `tests/test_seventh_chords.py` (35 tests: theory spelling incl. Gb-major's Cb, token honesty, MusicXML/payload, roman gate, tritone frame, curriculum coverage in 12 keys, scene honesty, router). Full suite 940 passed; all JS node tests pass.
