# 17 — G5a: applied-chord tracer — "Spot the intruder"

**What to build:** The first applied chords, via the flagship drill. The Lab's roman gate widens from diatonic-only to a supported-roman allowlist accepting applied-dominant tokens; the engine builds V7/x chords; the drill ships in C major with two stages. *Spot* (visual): the trainer renders I–vi–V7/V–V–I with the roman hidden on the intruder; the learner clicks the chord that doesn't live in C major; the card turns amber, the chromatic notehead pulses, and a one-liner explains ("F♯ is the leading tone of G — D7 is V7/V, the dominant of the dominant"). *Resolve* (performance): play the intruder and its resolution on the keyboard, tritone flagged green as it resolves; arpeggio variant for a second pass.

The spec shape from the plan's worked example encodes the concept/stages decision:

```json
{
  "schema": "harmony-lab/v1",
  "concept": "applied_chord",
  "key": "C", "mode": "major",
  "progression": ["I", "vi", "V7/V", "V", "I"],
  "render": "block",
  "stages": ["spot", "resolve", "ear"]
}
```

**Blocked by:** 09 — G1a V7 tracer (the V7 vocabulary); 06 — answer modalities (click-to-answer).

**Status:** ready-for-human

- [x] The widened gate accepts V7/V, V7/IV, etc., and still rejects unsupported chromatic tokens.
- [x] Spot stage works end to end: click answer, amber card, pulsing chromatic notehead, explanatory one-liner.
- [x] Resolve stage grades via MIDI with tritone-resolution highlighting.
- [x] Curriculum leaves under the reserved secondary-dominants stub go live.

**Implementation notes (2026-08-07):** shipped in commit on `fable_refactor`.
The `stages` vocabulary accepts `spot`/`resolve`; `"ear"` is refused loudly
with a pointer to ticket 19 (G5c) — the ticket JSON's three-stage shape
becomes writable there. Scene routing fails closed for applied chords until
the secondary-dominant template ships (ticket 18 / G5b). 12 leaves under
`lesson:adv_secondary` (4 spot + 4 block resolve + 4 arpeggio resolve, C
major); leaf fingerprint 351 → 363.

**Plan:** docs/curriculum_expansion_plan.md §3 G5, §7
