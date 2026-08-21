# B-flat Major 5/4 Melody — Composition Master

## 1. Document purpose

This file is the single musical ledger for the new score derived from
`resources/bb_major_5-4_melody.mxl`.

The new score will be composed and approved one measure at a time. No material
from `resources/bb_major_5-4_melody_expanded.mxl` may be copied into it unless
that material is explicitly retained below or is approved in a later revision
of this ledger.

**Status:** foundation only; no new score has yet been created  
**Composer:** Jozsef Kiss  
**Working title:** *B-flat Major Melody in 5/4* (final title pending)  
**Ledger version:** 0.1  
**Established:** 2026-08-21

## 2. Source hierarchy

| Priority | Source | Authority in the new composition |
|---:|---|---|
| 1 | Decisions recorded as **locked** in this file | Binding until Jozsef changes them |
| 2 | `resources/bb_major_5-4_melody.mxl` | Authoritative source for the basic melody and its original accompaniment |
| 3 | The attached 2026-08-21 recording | Reference for the rocking, staccato-like opening idea and its transition into the melody |
| 4 | Measures 1–2 of `resources/bb_major_5-4_melody_expanded.mxl` | Preliminary notation of the opening; retained only as specified in Section 6 |
| 5 | All other material in `bb_major_5-4_melody_expanded.mxl` | Rejected; not a compositional source |

## 3. Notation and decision conventions

- Pitches use scientific pitch notation: middle C is `C4`.
- Simultaneous pitches appear in brackets, low to high: `[B♭1, B♭2]`.
- Successive events are separated by `→`.
- Durations use `e` (eighth), `q` (quarter), `h` (half), and `dh`
  (dotted half).
- The score's tonal spelling uses flats. User-specified `A♯` and `D♯` are
  retained in the source column but normally engraved as `B♭` and `E♭`.
- A dyad does not determine a complete chord when its third or other defining
  chord tones are absent. Functional labels for such dyads are therefore
  contextual, not absolute.

| Status | Meaning |
|---|---|
| **Locked** | Pitch content or design decision explicitly required by Jozsef |
| **Retained draft** | Useful source material, but rhythm, articulation, voicing, or placement still requires approval |
| **Provisional analysis** | A theory-based working interpretation, not yet a compositional decision |
| **Rejected** | Must not be carried into the new score |

## 4. Basic musical properties

| Property | Current specification | Status / basis |
|---|---|---|
| Instrument | Solo piano, two staves | Verified in both MusicXML files |
| Initial tonal centre | B♭ major | Verified: key signature has two flats (`fifths = -2`, mode `major`) |
| Initial scale | B♭–C–D–E♭–F–G–A | Consequence of the key signature |
| Tonal trajectory | B♭ major → minor-coloured/modal-mixture region → consolation and solace | Locked narrative; exact pivot and minor collection remain to be composed |
| Possible final centre | E♭ major | Provisional analysis of the locked final sonorities; see Section 7.3 |
| Metre | 5/4 | Verified |
| Working beat grouping | 3+2 | Strongly implied by the original I → I6/4 division and `dh` → `h` bass rhythm; to be made perceptible in phrasing |
| Tempo | Quarter note = 90 | Verified in both MusicXML files |
| Smallest current notated value | Eighth note | Verified |
| Opening character | Quiet, rocking, staccato-like; a swing becomes a memory | Locked image; exact articulation is not yet encoded |
| Main affect | Nostalgic childhood recollection | Locked narrative |
| Middle affect | Nostalgia darkens into mourning | Locked narrative |
| Ending affect | Tension gives way to consolation and solace | Locked narrative |
| Clefs in source | Bass clef on both staves | Verified; may be reconsidered later for readability if the register rises |
| Current selected pitch span | B♭1–B♭5 | From the locked ending material |

## 5. Formal and emotional blueprint

| Section | Dramatic function | Musical obligation | Construction status |
|---|---|---|---|
| A. Rocking opening | The first motion of a swing; memory is approached indirectly | Short, separated gestures must grow naturally into the theme | Retained idea; measures not yet approved |
| B. Main theme | Nostalgic childhood memory becomes recognisable | Preserve the one-measure melody from the basic XML | Melody locked; placement and repetition plan pending |
| C. Darkening | Major recollection becomes mournful | Introduce a theoretically explicit minor/modal-mixture mechanism | Not composed |
| D. Tension | Intensify grief without losing the thematic thread | Incorporate the three locked tension dyads contextually | Pitches locked; harmony and rhythm pending |
| E. Preparation | Withdraw energy and prepare the consoling arrival | Use the five locked dyads in the stated order | Pitches locked; quarter-note 5/4 layout retained provisionally |
| F. Consolation | The harmonic space opens rather than collapses | E♭/B♭ sonority resolves/redistributes into full E♭ | Chord pitches locked; durations and voice leading pending |

## 6. Consolidated source measures

The measure IDs below describe source material, not final measure numbers in the
new score.

### 6.1 Retained opening draft

| ID | Source | Right hand | Left hand | Harmonic anchor | Function and status |
|---|---|---|---|---|---|
| O1 | Expanded m.1 | `q rest → e D3 → e F3 → q F3 → e D3 → e F3 → q F3` | `dh B♭2 → h F2` | Beats 1–3: B♭ (`I`); beats 4–5: B♭/F (`I6/4`) | The two `D3–F3` impulses and repeated `F3` landings provide the first rocking gesture. **Retained draft.** The XML marks `pp`, but contains no staccato articulation tags. |
| O2 | Expanded m.2 | `e D3 → e F3 → e B♭3 → e C4 → h B♭3 → q F3` | `dh B♭2 → h F2` | Beats 1–3: B♭ (`I`); beats 4–5: B♭/F (`I6/4`) | Opens the gesture into a recognisable thematic contour. **Retained draft.** The XML marks `p`, but its articulation and exact connection to the main theme still require approval. |

The recording is consistent with the registral field and pitch groups used by
O1–O2—B♭2/F2 below and D3/F3/B♭3/C4 above—and with the idea of a rocking
opening leading into repeated theme statements. It is an interpretive reference,
not a replacement for note-by-note approval.

### 6.2 Authoritative basic melody

`bb_major_5-4_melody.mxl` contains three identical measures. The core is
therefore a **one-measure theme repeated verbatim three times in the source**.
The new score is not required to preserve all three source repetitions; its
formal placement will be approved during construction.

| Source measures | Right hand: ten eighth notes | Left hand | Harmony | Analysis |
|---|---|---|---|---|
| Basic m.1–m.3 | `D3 → F3 → B♭3 → C4 → B♭3 → F3 → D3 → F3 → D3 → F3` | `dh B♭2 → h F2` | Beats 1–3: B♭ major (`I`); beats 4–5: B♭/F (`I6/4`) | `D–F–B♭` exposes the tonic triad; `C4` is a diatonic non-chord colour/upper-neighbour event. The final `D–F–D–F` keeps the tonic identity while the bass moves to F. **Melody locked.** |

### 6.3 Audit of the discarded expansion

| Expanded measures | Decision |
|---|---|
| 1–2 | Retain only as opening drafts O1–O2 above |
| 3 | **Rejected** |
| 4–5 | Arrangement **rejected**; the basic melody appearing here is preserved only because it comes from the authoritative basic XML |
| 6–9 | **Rejected**; no progression, bass line, register, dynamics, or developmental material carries forward |
| 10–11 | Arrangement **rejected**; the basic melody remains independently preserved |
| 12 | **Superseded in full** by the corrected five-dyad sequence in Section 7. The old second and third upper pitches (`E3`, `B3`) are specifically forbidden. |

## 7. Locked pitch and chord inventory

### 7.1 Tension dyads

| ID | User spelling | Tonal spelling for the score | Pitch-class content | Theoretical constraint |
|---|---|---|---|---|
| T1 | `D♯2–G3` | `E♭2–G3` | E♭–G | Root and major third of IV in B♭. It can also help pivot toward E♭, but is not minor by itself. |
| T2 | `F2–F3` | `F2–F3` | F octave | Bare dominant-scale-degree pedal in B♭. Its tension and mode must come from the surrounding voices. |
| T3 | `A♯2–D3` | `B♭2–D3` | B♭–D | Root and major third of I in B♭. It suggests return/resolution, but is not minor by itself. |

**Important:** T1 → T2 → T3 outlines fragments compatible with `IV → V → I`
in B♭ major. The required mournful major-to-minor turn must therefore be created
by additional pitches, altered scale degrees, voice leading, and/or a local key
reinterpretation. The dyads must not be falsely labelled as a minor progression.

### 7.2 Five-dyad preparation for the concluding theme

The corrected pitch order is locked. The existing idea of one quarter-note dyad
per beat would fill one 5/4 measure and is retained as the working rhythm, but it
must be confirmed when that measure is built.

| Beat / ID | User spelling | Tonal spelling | Safe harmonic description | Status |
|---:|---|---|---|---|
| 1 / P1 | `D♯2–A♯3` | `E♭2–B♭3` | Open fifth of E♭; IV fragment in B♭ or I fragment in E♭ | Pitches **locked** |
| 2 / P2 | `D2–F3` | `D2–F3` | Minor third; D-minor/iii fragment in B♭ | Pitches **locked**; replaces erroneous `D2–E3` |
| 3 / P3 | `G2–D3` | `G2–D3` | Open fifth of G; G-minor/vi fragment in B♭ | Pitches **locked**; replaces erroneous `G2–B3` |
| 4 / P4 | `C2–C3` | `C2–C3` | C octave; ii root/pedal in B♭ | Pitches **locked** |
| 5 / P5 | `A♯1–A♯2` | `B♭1–B♭2` | B♭ octave; tonic pedal in B♭ and future fifth-bass for E♭/B♭ | Pitches **locked** |

The dyads do not, by themselves, prove a conventional progression. A provisional
B♭ reading is `IV-fragment → iii-fragment → vi-fragment → ii-root → I-root`,
but the intended function must be established by the measures that precede and
follow it. P5 is especially important because its B♭ can remain as the bass of
the first consoling sonority.

### 7.3 Final consoling sonorities

| ID | Locked voicing in user spelling | Tonal spelling for the score | Harmonic reading | Status |
|---|---|---|---|---|
| C1 | LH `[A♯1, A♯2]`; RH `[D♯4, G4, A♯4, D♯5]` | LH `[B♭1, B♭2]`; RH `[E♭4, G4, B♭4, E♭5]` | E♭/B♭: `IV6/4` in B♭, or `I6/4` after E♭ is established as a local tonic | Pitches and order **locked** |
| C2 | LH `[D♯2, A♯2, D♯3]`; RH `[A♯4, D♯5, G5, A♯5]` | LH `[E♭2, B♭2, E♭3]`; RH `[B♭4, E♭5, G5, B♭5]` | Root-position E♭ major, registrally expanded | Final pitches and order **locked** |

C1 → C2 changes E♭ major from second inversion to root position and expands it
across the keyboard. In the original B♭-major frame this is `IV6/4 → IV`, not a
standard tonic cadence. The most coherent provisional interpretation is that
the closing section gradually establishes E♭ as a new local tonic, so the final
redistribution is heard as arrival and solace rather than as an unresolved
subdominant. This interpretation must be prepared in the preceding harmony; the
two final chords cannot create a modulation by themselves.

## 8. Harmonic guardrails for new measures

Every added measure must satisfy all of the following:

1. **Metre:** each active voice sums exactly to five quarter-note beats.
2. **Grouping:** accents, bass motion, or phrasing must make the chosen 5/4
   grouping intelligible; the default is 3+2 unless a documented expressive
   displacement is approved.
3. **Chord identity:** list the complete pitch collection and bass note before
   assigning a chord symbol or Roman numeral.
4. **Key context:** state the current tonal centre and identify any tonicisation,
   modulation, modal mixture, or chromatic alteration.
5. **Non-chord tones:** classify accented and metrically important non-chord
   tones (passing tone, neighbour, suspension, appoggiatura, pedal, and so on).
6. **Voice leading:** document common tones and the motion of bass, soprano, and
   tendency tones into the following event.
7. **Narrative role:** explain how the measure advances nostalgia, mourning,
   tension, consolation, or solace.
8. **Source control:** do not import a rejected expanded measure as filler.
9. **Notation:** use B♭/E♭ spellings in the B♭/E♭ tonal environment unless an
   alternate enharmonic spelling has a documented functional reason.
10. **Approval:** a measure is not locked until its ledger row and MusicXML
    implementation have both been reviewed.

## 9. Measure ledger template

Add one row for every proposed measure or distinct harmonic event. If a measure
contains multiple harmonies, give each event its own row.

| New measure / beat | Section | RH pitches and rhythm | LH pitches and rhythm | Chord symbol / Roman numeral | Tonal centre | Non-chord tones | Voice-leading in → out | Emotional role | Status |
|---|---|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — | — | — | Not composed |

## 10. Immediate next construction task

The next revision should construct only the opening and the approach to the main
theme:

1. decide whether O1 and O2 are accepted unchanged or surgically revised;
2. encode the intended separated/staccato-like articulation explicitly;
3. confirm the 3+2 swing and the `pp → p` dynamic plan;
4. design the smallest possible harmonic and melodic bridge into the locked
   one-measure theme; and
5. update this ledger before creating or changing the new MusicXML score.
