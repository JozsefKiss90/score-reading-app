# 04 — Held-note textures: intra-staff second voice + hold enforcement

**What to build:** The render + grading substrate for "hold one note while the same hand plays
others" — the rotation (12) and finger-independence (13) exercises. Today
`lab_musicxml._measure_xml` hardcodes exactly one voice per staff (voice 1 = staff1, voice 2 =
staff2, single `<backup>` between them, `lab_musicxml.py:118-125`), so a whole note held *under*
four moving quarters in the same hand is unrepresentable.

**Blocked by:** 01 — technique concept; 03 — active-note set (hold enforcement reuses it).

**Status:** ready-for-agent

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

- [ ] Two-voice measures render correctly on both staves (stems split, bar ticks sum per voice).
- [ ] v1: rotation-style phrase grades its moving line; hold is displayed only.
- [ ] v2: with `hold` in the payload, releasing the held note blocks the next step until re-pressed.
- [ ] Regression: measures without second-voice streams produce byte-identical MusicXML.

**Tests:** `tests/test_technique.py` — two-voice XML shape (`<backup>` count, voice numbers,
per-voice tick sums); payload `hold` emission; a no-hold spec's XML unchanged. Manual QA: MIDI
hold-release-repress cycle mid-phrase.

## Grading honesty

v2 verifies the hold exists at each step's satisfaction instant — not continuously between steps,
and not the *finger* used. Rotation gesture quality stays coach-text.
