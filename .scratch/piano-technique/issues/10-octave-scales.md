# 10 — Exercise 6: octave scales

**What to build:** Major scales in octaves, all 12 keys, up and down — the drill where the grader
must finally tell C4+C5 from a lone C. Host: **Lab**, `lesson:tech_octaves`.

**Blocked by:** 01 — phrase engine; 03 — distinct-count steps (the octave-aware grading);
02 — fingering (trivial 1–5/1–4 labels; non-blocking if sequenced later).

**Status:** ready-for-agent

## Content

Per key: one octave up and down in eighth-note octave steps (the four-octave span is ticket 05's
job; here the texture is the lesson):

* Steps: degree d = 1..8 ascending then 8..1 descending, each rendered as the written octave pair
  (lower note + `<chord/>` upper octave) and graded as `{pcs: [pc(d)], minDistinct: 2}` — two
  distinct MIDI keys of the same pitch class down together (ticket 03 semantics). 16 steps =
  2 measures; repeat once = 4 measures per leaf.
* RH measures then LH measures (LH two octaves lower) in the same leaf.
* Fingering: 5 on white-key tops, 4 on black-key tops (RH), mirrored for LH — label the top note
  only.
* **12 leaves:** `ex:tech_octave_scale_<keyslug>` (majors; the video runs "all of the major
  scales just like this").
* Coach text: "Same ricochet wrist as exercise 5 — bounce, don't press; build speed gradually."

## Where

`_tech_octave_scale_specs()` in `harmony/curriculum.py`; pins +12; `tests/test_technique.py`
gains: every step carries `minDistinct: 2`; the rendered measure stacks the written octave;
playback sounds both octaves (per-beat pc list carries one pc — extend the playback emission to
honour `minDistinct` by sounding the written MIDI pair from `staff` notes, or accept single-pc
playback with a Comments note; implementer verifies which the transport already does with
`midiPitches`).

- [ ] A single key press never satisfies an octave step; the true octave pair does.
- [ ] 12 leaves launch/render/grade; both hands' registers correct.
- [ ] Fingering on top notes; pins updated; honesty text present.

## Grading honesty

The grader demands two distinct keys of the right pc — it cannot demand they be exactly an octave
apart (a fifteenth would pass). Raw-MIDI interval checking is a possible sharpening; note it in
the leaf description rather than blocking on it.
