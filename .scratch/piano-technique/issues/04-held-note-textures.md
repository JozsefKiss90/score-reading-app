# 04 — Held-note textures: intra-staff second voice + hold enforcement

**What to build:** The render + grading substrate for "hold one note while the same hand plays
others" — the rotation (12) and finger-independence (13) exercises. Today
`lab_musicxml._measure_xml` hardcodes exactly one voice per staff (voice 1 = staff1, voice 2 =
staff2, single `<backup>` between them, `lab_musicxml.py:118-125`), so a whole note held *under*
four moving quarters in the same hand is unrepresentable.

**Blocked by:** 01 — technique concept; 03 — active-note set (hold enforcement reuses it).

**Status:** ready-for-human

## Design

**Render.** `LabMeasure` gains `staff1_voice2: Tuple[LabNote, ...] = ()` and
`staff2_voice2: Tuple[LabNote, ...] = ()`. When non-empty, `_measure_xml` emits an extra
`<backup>64</backup>` after the staff's first voice and serializes the second stream with
`voice=3` (staff1) / `voice=4` (staff2), same staff number. Verovio then engraves classic
two-voice writing (stems up/down split). The held line is the second voice: e.g. voice 3 = one
whole note, voice 1 = four quarters. Tick-sum discipline: each voice stream must independently
fill the 64-tick bar (rest-pad as needed).

**Spec surface.** `TechniqueParams` gains `hold: tuple = ()` — one entry per measure, each
either `()` (no held note) or `(degree,)` for the note held through that measure. `_gen_technique`
renders the hold as the second voice on the active hand's staff and the moving notes as voice 1.

**Grading.**

* **v1 (this ticket's default):** the moving line only — targets/`expected_by_beat` come from the
  moving voice; the held note is notation + coach text. Honest description line required
  ("graded: the moving notes in order; not graded yet: keeping the hold down").
* **v2 (checkbox below, still this ticket):** payload target gains
  `hold: {"pc": <int>}`; in ordered mode the JS satisfies a step **only while** some active MIDI
  note maps mod-12 to the hold pc (the ticket-03 active-note set makes this a one-line predicate).
  Dropping the hold doesn't reset progress; the next step simply refuses until it is re-pressed,
  and the guide panel shows "keep the <note> held". Mod-12 is acceptable here (the learner has no
  reason to hold the wrong octave; note the limitation in the explanation).

- [x] Two-voice measures render correctly on both staves (stems split, bar ticks sum per voice).
- [x] v1: rotation-style phrase grades its moving line; hold is displayed only.
- [x] v2: with `hold` in the payload, releasing the held note blocks the next step until re-pressed.
- [x] Regression: measures without second-voice streams produce byte-identical MusicXML.

**Tests:** `tests/test_technique.py` — two-voice XML shape (`<backup>` count, voice numbers,
per-voice tick sums); payload `hold` emission; a no-hold spec's XML unchanged. Manual QA: MIDI
hold-release-repress cycle mid-phrase.

## Grading honesty

v2 verifies the hold exists at each step's satisfaction instant — not continuously between steps,
and not the *finger* used. Rotation gesture quality stays coach-text.

## Implementation notes (close-out)

* `harmony/lab_spec.py` — `TechniqueParams.hold` (one entry per measure, `()` or `(degree,)`,
  validated to mirror the phrase length + the 1..29 degree span) and the v2 switch
  `hold_graded: bool = False`; `hold_graded=True` without any hold is refused (it would promise
  a check that can never run). A hold sharing a pitch class with its measure's moving line is
  also refused (review finding): the mod-12 grader could not tell the held key from the moving
  note, so such a hold would grade itself — degrees an octave apart collide too (pure
  `(d-1) % 7` arithmetic, exact within one key).
* `harmony/lab.py` — `LabMeasure.staff1_voice2` / `staff2_voice2` (generic second-voice
  streams; each must fill the 64-tick bar on its own) + `hold_pc` / `hold_graded`;
  `_gen_technique` writes the hold as one whole note in the active hand's staff's second
  voice, keeps grading strictly the moving line, and appends the honest guide line (v1
  "Graded: … not graded yet: keeping the hold down" / v2 "counts only while the hold is
  sounding"). `sounding_midis()` now includes the second-voice notes so the runtime
  `PITCH_MAP` sees the engraved hold.
* `harmony/lab_musicxml.py` — `_measure_xml` emits `<backup>64</backup>` + voice 3 (staff 1) /
  voice 4 (staff 2) per non-empty stream; empty streams are byte-identical to the old layout.
  `_lab_target_for` gains the additive `hold: {"pc": <int>}` only when the measure is
  hold-graded.
* `beat_selector/harmony_trainer.js` — `holdPc`/`holdDown` over the ticket-03 `activeNotes`
  set; both ordered branches (scalar walk and `steps`) refuse a satisfied step while the hold
  is up, without touching `arpIndex` (no reset). The amber `#htHoldMsg` panel line shows
  "Keep the X held …" until the hold sounds again; the hint also fires on the hold's own
  note-off (proactively, not only once a moving note is refused). In `steps` mode re-pressing
  the hold re-evaluates the current step, so already-held fresh keys advance immediately. The
  hold key never counts as a step constituent — the collision gate guarantees its pc is
  outside every moving pc of its measure.
* Docs: `docs/harmony_trainer.md` §5 hold paragraph; the technique concept explanation's
  misconception + next-steps entries updated (instant-based, mod-12, never continuous).
* Tests: `tests/test_technique.py` `TestHold{Validation,Compile,MusicXml,Payload}` +
  explanation-honesty pin; `tests/harmony_lab_midi_test.js` Tests I (scalar
  hold-release-repress cycle) and J (hold composed with dyad steps).
* Playback honesty gap (accepted, same class as ticket 03's octave-pair gap): the playback
  plan sounds `expected_by_beat` only, so the held whole note is engraved but not sounded by
  auto-play.
