# 05 — Exercise 1: scales, the Russian form

**What to build:** Daily scales the way the video teaches them: a four-octave scale **broken at
the midpoint into contrary motion and rejoined**, in every major key and every harmonic-minor
key, with standard fingerings displayed. Host: **Lab** (curriculum leaves under
`cat:technique` → `lesson:tech_scales`).

**Blocked by:** 01 — phrase engine; 02 — 16ths + fingering. v2 measures additionally: 03 —
simultaneity (hands-together contrary steps are two-pc dyads).

**Status:** ready-for-agent

## Content

**v1 leaf (per key): hands separate, four octaves up and down.**
16th-note phrase, RH measures then LH measures in one leaf (the ordered walk crosses staves
naturally since only one line sounds at a time):

* RH: degrees 1→29 ascending (28 16ths = 1¾ measures), 29→1 descending; total 56 notes =
  3½ measures → rest-pad to 4. LH: same in the bass register (`hand` switches per measure group —
  extend `TechniqueParams` so `hand` may be per-measure, or compile the leaf from two specs in one
  experiment; implementer's choice, keep it simple).
* 8 measures total per leaf — within the 12-measure cap.
* Fingering from the standard tables (see oracle below). Coach text: "Vary it daily: staccato,
  forte, piano, crescendo–diminuendo — the grader only checks the notes."

**v2 leaf (per key, after 03): the actual Russian form, hands together.** Step list built from
segments (RH degree r, LH degree l as a dyad step `{pcs:[pc(r),pc(l)], minDistinct:2}` — unison
octaves are the same pc, hence minDistinct 2):

1. Unison in octaves, up two octaves: r = l+7… both hands 1→15.
2. **Break apart** (contrary): RH 15→22 while LH 15→8 (mirror: `l = 30 − r`), then back together
   (RH 22→15, LH 8→15).
3. Unison up to the top: 15→29. 4. Unison down: 29→15. 5. Contrary break again (as 2).
6. Unison down to the tonic: 15→1.

≈ 98 steps → 7 measures of 16ths — fits the cap. One v2 leaf per key.

**Keys:** 12 majors + 12 harmonic minors (the video: "C major all the way up through B major…
then the harmonic minor scale as well") = **24 v1 leaves** (v2 adds 24 more later; ship v1 here,
v2 behind its checkbox if 03 has landed, else file it as a follow-up comment).

**Fingering oracle** (acceptance spot-checks; encode the full standard table as data,
RH+LH × 24 keys):

* C major RH ascending: 1231234 1231234… (thumb on C,F); LH descending from top: 1231234….
* F major RH: 1234123 (thumb on F,Bb → 4 on Bb); B major LH: 4321432….
* Db major RH: 231234 1… (thumb on F,C — white keys only); A harmonic minor RH: 123123 45 pattern
  as per the standard table.

## Where

Spec factory `_tech_scale_specs()` in `harmony/curriculum.py` (pattern:
`_inversion_curriculum_specs`, `curriculum.py:1456`); fingering table as module data in
`harmony/technique_data.py` (new, shared with 06/07); leaves via `fill_lab`. Leaf ids
`ex:tech_scale_russian_<keyslug>_<mode>`. Update both leaf-count pins (+24) and add
`test_technique_scales` count/fingering-oracle tests.

- [ ] 24 v1 leaves launch, render 4-octave runs with fingering, grade note-by-note, record progress.
- [ ] Fingering oracle rows verified against the data table.
- [ ] Coach text and the graded/not-graded line render in the guide.
- [ ] v2 Russian-form leaf compiles behind 03 (or follow-up filed in Comments).

## Grading honesty

v1 grades the ordered notes mod-12 (octave placement of each hand is display + playback only);
v2 grades hand-simultaneity per step. Dynamics/articulation variants are coach-text.
