# 02 — Notation vocabulary: 16ths, fingering, slurs, articulations

**What to build:** The four notation elements the technique drills display that the renderer
cannot emit today: 16th notes, per-note fingering numerals, two-note slurs, and articulation
marks (staccato dot, accent). All additive, all presentational — grading is untouched.

**Blocked by:** 01 — technique concept (the fields ride on `LabNote` / `TechniqueParams`).

**Status:** ready-for-agent

- [ ] A technique phrase with `note_value="16th"` renders 16 notes in a 4/4 bar, plays back
      correctly, and grades note-by-note.
- [ ] Fingering numerals render above/below the correct noteheads (Verovio `<technical><fingering>`).
- [ ] A slurred note pair renders a slur arc; staccato/accent marks render on flagged notes.
- [ ] Existing exercises' MusicXML is byte-identical (all new emission is opt-in).

## Design

**Durations.** `harmony/lab_musicxml.py:56-57` `_TICKS` gains `"16th": DIVISIONS // 4`
(DIVISIONS=16, so ticks=4 — exact). `_gen_technique`'s slots table gains `("16th", 16)`.
**Playback:** widen `playback_plan.py`'s beat guard (`:98`, currently `1 <= b <= 2 *
BEATS_PER_MEASURE`) to accept 16 slots, and make its slot-duration math derive from the measure's
slot count rather than assuming eighths — verify a 16-slot measure plays at double eighth speed.

**Per-note marks.** `LabNote` (frozen dataclass, `lab.py:~140`) gains optional fields:
`fingering: str = ""`, `slur: str = ""` (`"start" | "stop" | ""`), `articulation: str = ""`
(`"staccato" | "accent" | ""`). The shared note serializer `_note_xml`
(`harmony/musicxml_builder.py:139-147`) gains matching optional keyword args (default `""` →
zero output change for every existing caller) and, when set, emits after `<type>`:

```xml
<notations>
  <slur type="start" number="1"/>
  <articulations><staccato/></articulations>
  <technical><fingering>3</fingering></technical>
</notations>
```

(One `<notations>` wrapper; Verovio renders all three; keep the house rule from
`lab_musicxml.py:78-83` — no free `<words>`.) `lab_musicxml._staff_xml` threads the fields
through. `_gen_technique` maps `TechniqueParams.fingering` onto the notes; slur/articulation
come from two new optional params mirroring fingering's shape:
`slurs: tuple[tuple[str, ...], ...]`, `articulations: tuple[tuple[str, ...], ...]`.

**Optional (low priority):** `<beam>` emission for eighth/16th groups-of-four — without it
Verovio draws separate flags, which is acceptable; if added, gate it behind a
`beam_groups: bool` param.

**Tests:** extend `tests/test_technique.py` — 16-slot compile + tick sums (measure == 64 ticks),
fingering/slur/articulation XML presence and placement, regression: a ticket-01 spec without the
new params produces identical MusicXML before/after.

## Grading honesty

Nothing here is graded: fingering compliance, articulation length, and slur gesture are
unobservable to the mod-12 note-on grader (releases are ignored in ordered mode,
`harmony_trainer.js:622`). These marks are the *lesson*; the grade stays "right notes in order".
