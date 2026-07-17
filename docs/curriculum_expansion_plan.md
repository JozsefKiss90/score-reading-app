# Music Theory Lab & Harmony Atlas — Curriculum Expansion Plan

*Drafted 2026-07-16 from a five-track code audit (curriculum layer, exercise engine, Lab/Atlas/Score Soul, graph layers, UI surface). All claims below are grounded in file references; "reserved" quotes are the repo's own roadmap idiom.*

---

## 0. Executive summary

The platform today is a **diatonic, root-position-triad, MIDI-performance trainer** with an unusually strong scaffold around it: 230 curriculum leaves, a 7-kind Harmony Atlas, four graph layers with honesty gates, and a real-score layer (Score Soul) that walks Bach measure by measure — currently broken (see scope note below). Its single biggest pedagogical problem is structural, not incremental:

> **The app's curated corpus already *contains* harmony it never *teaches*.** The BWV 846/999 analyses (`data/score_annotations/`) name V7/V, V7/IV, vii°7/V, vii°7 with modal mixture, the Neapolitan sixth, the harmonic-minor dominant, and six diatonic seventh-chord types — while the drill engine is hard-gated to diatonic root-position triads in major/natural minor (`lab_spec.py:125-144`, `theory/diatonic_harmony.py:74-77`). The honesty model handles this gracefully (chromatic slices are marked `unsupported_chromatic`, never faked), but honesty is not pedagogy: every chromatic annotation is a promise the curriculum hasn't kept.

The plan's organizing principle is therefore **"teach what you already show"**: expand the drillable vocabulary along the exact seams the codebase has already reserved (seventh chords, harmonic minor, secondary dominants, modulation, mixture — all named as reserved stubs in `curriculum.py:1157-1178` and `network_template.py:911-932`).

**Scope note — Score Soul is out of scope.** The Score Soul / Harmonic Mandala launcher (`run_score_harmonic_network_demo.py`) is currently broken. Its repair — and every feature that depends on walking a real score: measure anchors from lessons, the BWV 999 score-file drop-in, chorale-corpus ingestion, sidecar `base_roman` flips — is deliberately excluded here and deferred to a **separate repair plan**. The corpus annotations remain this plan's *evidence base* (§1.3) and coverage benchmark (§8), but no deliverable below touches the Score Soul surface.

Three phases:

1. **Phase 1 — Fix & Foundation** (~4–6 wks): repair labeling inconsistencies and grading defects; ship target playback + first ear drills (the audio stack already exists and is idle); add answer modalities beyond the MIDI keyboard; stand up a progress dashboard and review queue.
2. **Phase 2 — The Chromatic Bridge** (~8–12 wks): seventh chords → harmonic/melodic minor → cadence-taxonomy repair → applied chords → non-chord tones → modulation. This closes the corpus gap (§1.3).
3. **Phase 3 — Advanced Suites** (~10–14 wks, modular): chromatic harmony (mixture, N6, Aug6, CT°7, chromatic mediants), modal interchange, counterpoint studio, adaptive difficulty.

---

## 1. Audit of current content

### 1.1 Verified coverage today

| Layer | What it covers | Evidence |
|---|---|---|
| Theory engine | Major + **natural minor only**; triads maj/min/dim (aug defined, unreachable); root position only | `theory/diatonic_harmony.py:74-77,395-403`; `musicxml_builder.py:87-103` |
| Trainer drills | 4 types (`horizontal_degree, full_key, quality, function`), block/arpeggio, 24 keys, ≤12 chords/spec | `exercise_spec.py:60-70` |
| Curriculum | 230 leaves / ~300 nodes, 14 categories; heavy on scales (48), inversions (97), degrees (28); cadences 13, all in one reference key | `curriculum.py:678`; `docs/harmony_curriculum_coverage_audit.md:20-33` |
| Lab | 15 experiments + `drill` passthrough; concepts inversion/cadence/voice-leading/motive/polyphony; **reduction reserved** (`NotImplementedError`) | `lab.py:666-766, 639-644` |
| Atlas | 7 node kinds (scale/degree/triad/quality/layer/function/cadence), 168 triad nodes; **its own ScoreAnalysis API is dead code** (all six methods raise, deliberately bypassed by `score_analysis.py`) | `atlas.py:648-691`; `score_analysis.py:7-11` |
| Graphs | 7 registered network templates + 10 GraphScene types + functional journey (4 major keys, 7 stages); 2 planned stubs (`modulation_path`, `secondary_dominant`); new two-level role model (`harmonic_roles.py`) | `network_template.py:849,911`; `graph_scene.py:48`; `functional_network_plan.md:41-56` |
| Score Soul | BWV 846 fully annotated (34 mm.); **BWV 999 sidecar only — score file missing**; launcher currently broken — **out of scope, separate repair plan** | `data/score_annotations/bwv999…json:8` |
| Interaction | **Hardware MIDI keyboard is the only answer modality**; no identify/MCQ/build/click-answer drill exists anywhere | engine audit §5; `curriculum_explanations.py:290` |
| Feedback | Immediate, per-note green/red, pitch-class (octave-agnostic), unlimited retry | `harmony_trainer.js:81-212`; `cursor.js:67-95` |
| Audio | FluidSynth + FluidR3_GM.sf2 present and wired — but only monitors the learner's own playing. **No target playback**; `renderToMIDI()` output discarded | `audio/midi_player.py`; `view.py:180,436-441` |
| Progress | Per-leaf `not_started→started→completed(≥80)→mastered(≥0.95×3)`; linear advisory prerequisites, **never enforced**; `last_played` stored, **never used**; difficulty 1–5 is a static label | `curriculum_progress.py:38-108`; `curriculum.py:659-665` |

### 1.2 Findings — inconsistencies, defects, stale content

| # | Finding | Evidence | Fix |
|---|---|---|---|
| F1 | **Three-way function-label conflict.** Theory engine: IV=subdominant, iii=mediant; curriculum prose: IV=predominant, iii=tonic; drill tokens: S→IV, PD→ii. A learner sees "subdominant" and "predominant" for the same IV in one session. | `theory/diatonic_harmony.py:101-108` vs `curriculum.py:903-906,1028` vs `exercise_spec.py:53-58` | Adopt the new two-level model (`harmonic_roles.py:46,173`: broad family + specific role) as the **single vocabulary source** everywhere prose or labels render a function. |
| F2 | **I–V–vi–IV tagged "deceptive".** It's the axis progression; V–vi is mid-phrase, the phrase ends on IV. Wrong info shown to learners. | `curriculum.py:495`; `atlas.py:103` | Re-tag as `progression` ("axis / deceptive motion inside a loop"), keep V–vi two-chord leaf as the deceptive exemplar. |
| F3 | **Cadential 6/4 mis-framed.** Second inversion taught only as "tonic with the fifth in the bass"; its dominant-function cadential use is deferred with a bare "a later topic". | `curriculum.py:1016-1025`; `lab_explanations.py:124` | G3 module below; meanwhile soften the tonic-function claim in the I6/4 lesson prose. |
| F4 | **Inversion drills don't grade the bass.** A curriculum inversion leaf's trainer skeleton is a *root-position* function drill; grading is octave-agnostic; `strict_bass` exists only in the Lab payload. Figured bass is shown but never assessed. | `lab_spec.py:8-20,410-424`; `lab.py:294-297` | G4: thread `bass_pitch_class` into the trainer payload + JS validator; lowest-sounding-note check. |
| F5 | **Latent crash: augmented specs.** `quality="augmented"` passes `validate()` but compiles to zero chords → `build_musicxml` raises. Reachable via custom JSON/circle input. | `exercise_spec.py:62`; `musicxml_builder.py:272-273` | Reject at `validate()` until III+ ships (G2), then generate legitimately. |
| F6 | **MAX_CHORDS_PER_SPEC not enforced.** The 12-chord cap is a construction convention; hand-authored specs overflow onto a hidden second Verovio page — invisible chords. | `exercise_spec.py:64-70`; `run_harmony_trainer_demo.py:462-467` | Enforce in `validate()` (with explicit override flag once U5 lands). |
| F7 | **Cadences duplicated as Voice Leading.** Same 13-entry catalogue rendered twice as two categories; lab concept chosen purely by chord count (2 = cadence, ≥3 = voice_leading); `CadenceSpan` omits the `subtonic` type the curriculum uses; label style drifts (words vs romans). | `curriculum.py:570-571,698-707`; `atlas.py:119,1129` | One catalogue, two *render variants* (block / SATB) under one category; align type enums. |
| F8 | **Uneven key coverage.** Quality drills major-only; cadences/voice-leading exist in a single reference key (C / Am) while scales/degrees span all 12. | `exercise_spec.py:496`; `curriculum.py:521,568-571` | Add transposition variants via the existing `transposition_orbit` pattern. |
| F9 | **No PAC/IAC distinction; "half cadence" reified as I–V only.** | `curriculum.py:482-500` | G3 taxonomy repair. |
| F10 | **Stale/dead surfaces.** Atlas `ScoreAnalysis` (Part VIII) fully reserved and bypassed; `renderToMIDI()` result thrown away; BWV 999 playable sidecar blocked on a missing `.mxl`; Lab/Curriculum panels hard-locked light while the score surface has a full dark theme; the Score Soul launcher itself is broken (user-reported). | `atlas.py:648-691`; `view.py:180`; `bwv999…json:8`; `curriculum.html:8` | Wire playback (U1); theme unification (U7). The launcher repair, the Atlas Part VIII decision, and the BWV 999 score file belong to the separate Score Soul repair plan. |
| F11 | **Natural-minor-only dominant.** Minor drills use minor v and "♭7→1, no leading tone"; the common-practice V–i with raised 7̂ doesn't exist anywhere. Correctly honest (`functional_equivalence` refuses minor, `harmonic_network.py:1131`) — but it means every minor cadence sounds Aeolian. | `lab.py:420-425`; `curriculum.py:921-927` | G2 — the single highest-value content addition. |

### 1.3 The headline gap: in the corpus but never taught

Every roman below is present in the curated score analyses (`data/score_annotations/`) — the Score Soul walker rendered them to learners before it broke — with zero drill/curriculum coverage (secondary dominants: "Actual exercise leaves: 0", `harmony_curriculum_coverage_audit.md:93-94`).

**How this indicts the Lab and the Atlas — the plan's primary targets.** The corpus annotations are only where the evidence was *found*; the deficit they expose lives in the layers this plan expands. Every curriculum leaf compiles through a `LabExperimentSpec`, so the Lab's roman gate (`is_diatonic_roman`, `lab_spec.py:125-144`, enforced at `:290-296`) *is* the platform's entire teachable vocabulary — and it rejects every token below. The Atlas, in turn, has no node kind these chords could honestly land on (its 168 chord nodes are triads only), which its own `base_roman` honesty mechanism demonstrates at each of these measures: rather than lie, the analysis refuses to claim any Atlas node at all ("C7 = V7/IV … never claims the tonic node", `score_analysis.py:585-589`). The causal chain: corpus data (Score Soul's layer, out of scope) → reveals chords → that the Lab's gate rejects and the Atlas cannot represent → which the G/A modules fix in the Lab, the Atlas, and the theory engine beneath both. The *Blocked by* column names the responsible layer per row:

| Phenomenon | Corpus evidence | Blocked by (layer) | Fix |
|---|---|---|---|
| V7/V (D7 with F♯) | BWV 846 mm. 6, 10 | **Lab** gate rejects `V/x` tokens; **Atlas** has no applied-dominant relation; curriculum stub reserved (`curriculum.py:1177`) | G5 |
| V7/IV (C7 with B♭) | BWV 846 mm. 20, 31 | same Lab gate + Atlas gap | G5 |
| vii°7/ii (C♯°7) | BWV 846 m. 12 | **Theory engine** is triad-only; **Lab** gate rejects the applied-°7 token | G1→G5 |
| vii°7/V (F♯°7) | BWV 846 mm. 22, 27 | same | G1→G5 |
| vii°7 with mixture ♭6 (B°7 with A♭) | BWV 846 mm. 14, 23 | Triad-only **engine**; no parallel-mode borrowing in any layer (`borrowed_from_parallel` reserved) | G1 + A2 |
| Dominant suspension ("V11sus", slice `ambiguous`) | BWV 846 m. 29 | **Lab** has no NCT concept; grading is per-chord, never per-note | G6 |
| Harmonic-minor V (raised B♮) | BWV 999 mm. 2, 11 | **Theory engine**: `_MODE_STEPS` = major/natural minor only | G2 |
| V7/iv | BWV 999 m. 9 | **Lab** gate + **engine** (needs G2's minor dominant first) | G2→G5 |
| **Neapolitan ♭II6 → V half cadence** | BWV 999 mm. 10–11 | **Lab** gate rejects `bII`; **Atlas** has no node kind for it; engine cannot build it | A2 |
| Diatonic sevenths: ii7, V7, V6/5, vi7, Imaj7, IV7 | BWV 846 mm. 2, 3, 8, 9, 16–18, 21, 24, 26, 30–32 | **Engine** builds triads only; **Atlas** has no seventh-chord node kind; network dom7 nodes visual-only ("reserved-7th honesty", `harmonic_network.py:22-23`) | G1 |

**Didactic role of this section.** The table is the plan's *needs analysis* in the backward-design sense: the target vocabulary is derived from the terminal skill — reading real music — rather than from a textbook checklist. It contributes three things. (1) *Scope control:* a topic earns a module only if easy, real repertoire already demands it; all ten rows occur within the 46 annotated measures of two beginner-friendly Bach preludes, so nothing proposed is exotic. (2) *Sequencing evidence:* corpus frequency sets priority — applied chords appear in eight separate measures across both pieces (hence flagship G5), the Neapolitan once (hence Phase 3, A2). (3) *A measurable finish line:* §8's coverage-honesty metric counts exactly these rows, and the Phase 2/3 exit criteria retire specific rows, so "the gap is closed" is checkable rather than rhetorical. The learner never sees this table; its didactic contribution is the guarantee that every module downstream teaches something a learner will verifiably meet in real music — the plan's substitute, until the Score Soul repair lands, for meeting it *in situ*.

---

## 2. Didactic design principles

These govern every module below; the codebase already embodies several, which the plan extends rather than reinvents.

1. **Sound before symbol.** Every new concept opens with playback (U1) before notation or labels. Today the learner must already know the sound; drills never play the target.
2. **One-new-thing ramps.** Difficulty increases along a single axis at a time: key distance on the circle of fifths (the app's own geometry), render (block → arpeggio → SATB), label fading (full analysis → roman only → sound only), tempo. Matches the existing transposition-orbit pattern.
3. **Immediate, explanatory feedback.** Keep per-note green/red; add one-line *why* on error ("you played ♭7 — natural minor's subtonic; this drill wants the raised leading tone"), driven by an error taxonomy (§8).
4. **Retrieval + spacing.** `last_played` is already persisted; schedule review with an SM-2-lite queue, interleaving categories (quality + degree + cadence in one session) rather than blocking.
5. **Mastery gating, honestly soft.** Prerequisites exist but are decorative; enforce as *soft locks* (recommended-with-override), reusing the `finish_any/finish_all` gating that `functional_journey.py:384-396` already implements — unify the two progress systems.
6. **Honesty preserved.** The validate() gates (chord ≠ key node, reserved-relation checks) are pedagogical assets: the app never fakes certainty. New vocabulary flips a reserved seam to implemented *only* when a launchable drill exists; nothing is ever projected onto a node it doesn't truly match.

---

## 3. Pedagogical gap modules (G-series) — the Chromatic Bridge

Ordered by prerequisite chain; this is the Phase 2 spine.

### G1 — Diatonic seventh chords
- **Objective:** play, spell, and resolve all five diatonic seventh qualities; own V7's tritone as the engine of tonal motion.
- **Prerequisites:** Triads *completed*; Inversions (root/1st) *completed*; Cadences authentic/half *completed*.
- **Outcomes:** learner plays V7→I with correct tritone resolution in 12 major keys; identifies Mm7/mm7/MM7/ø7/°7 by ear (with A1); reads V6/5–V4/2 figures.
- **Lessons & drills:** (1) V7 anatomy — add-the-7th drill: play V, then V7, hear the added dissonance; (2) tritone resolution — play 4̂→3̂ + 7̂→1̂ two-voice frame, then full V7→I; (3) ii7–V7–I in all keys (block → arpeggio); (4) seventh-quality drill mirroring the existing quality drill; (5) figured-bass inversions of V7 (with G4 bass grading).
- **Plug-ins:** widen `_build_triad`→`_build_tetrad` in `theory/diatonic_harmony.py`; new `_VALID_QUALITY` entries; voicing in `musicxml_builder.py`; **flip the network's reserved dom7 nodes to launchable** (`_reserved_entry`, `harmonic_network.py:315`; JS `RESERVED_DRILLS`, `harmonic_network.js:210`) — the graph was built waiting for this.

### G2 — Harmonic & melodic minor
- **Objective:** the raised leading tone; real V and vii° in minor; III+ as the first legitimate augmented triad.
- **Prerequisites:** Minor scales/degrees *completed*; G1 helpful but not required for the triad layer.
- **Outcomes:** learner plays i–iv–V–i with raised 7̂ in 12 minor keys; contrasts v–i (modal) vs V–i (tonal) by ear; plays the three forms of the minor scale.
- **Lessons & drills:** (1) "one accidental changes everything" — A/B drill: same cadence with ♭7 then ♮7; (2) V–i and vii°–i in minor across keys; (3) melodic-minor ascent/descent as a motive drill; (4) III+ quality drill (un-reserves augmented, fixing F5 legitimately — the code comment predicted this: "arrives with harmonic minor's III+", `curriculum.py:859-865`).
- **Plug-ins:** add `harmonic_minor`/`melodic_minor` to `_MODE_STEPS`; un-refuse minor in `functional_equivalence` (`harmonic_network.py:1131`); update `_MINOR_ROLES` (v weak → V strong when mode says so, `harmonic_roles.py:198-209`); functional journey **v2 minor panels** (the named roadmap item, `functional_network_plan.md:188-189`).

### G3 — Cadence taxonomy repair + the cadential 6/4
- **Objective:** a truthful cadence ontology: PAC vs IAC, half cadences from any predominant, Phrygian half, deceptive, plagal — and the cadential 6/4 as dominant function.
- **Prerequisites:** Cadences *completed*; Inversions (2nd) *started*; G2 for Phrygian.
- **Outcomes:** learner classifies cadences aurally and visually; plays I6/4–V–I hearing the 6/4 as a dominant embellishment; explains why "I6/4" ≠ tonic here.
- **Lessons & drills:** (1) PAC vs IAC — same V–I with soprano on 1̂ vs 3̂/5̂, ear-discrimination pairs; (2) half-cadence family: ii–V, IV–V, i–V, iv6–V (Phrygian); (3) cadential 6/4: play IV–I6/4–V7–I, then relabel the same sounds as IV–V(6-5/4-3)–I; (4) deceptive vs authentic reflex drill (V→? by ear); (5) fix F2/F7/F9 as part of shipping.
- **Plug-ins:** extend `CADENCE_CATALOGUE` (`harmonic_network.py:118`) + `_CADENCE_TYPES`; the `cadence_resolution_network_v1` template renders the new arcs automatically.

### G4 — True inversion & figured-bass grading
- **Objective:** the bass note *matters*: figured bass becomes an assessed skill, not a caption.
- **Prerequisites:** Inversions *started*.
- **Outcomes:** learner voices any triad (later V7) with a demanded bass; reads 5/3–6–6/4 (then 7–6/5–4/3–4/2) as performance instructions.
- **Lessons & drills:** existing 97 inversion leaves re-graded with lowest-note checking; "bass-line dictation": hear a progression, play only the bass; ii6 as *the* predominant voicing inside cadence drills (linking two currently unconnected categories).
- **Plug-ins:** thread `bass_pitch_class`/`strict_bass` from `lab.py:294-297` into `build_trainer_payload` + `harmony_trainer.js` matching; fixes F4.

### G5 — Applied chords (secondary dominants) — *flagship*
- **Objective:** tonicization: any major/minor triad can be preceded by *its own* dominant; V/V as a pivot of hearing.
- **Prerequisites:** G1 *completed* (V7 vocabulary), G3 *started*; Functions *completed*.
- **Outcomes:** learner spots the chromatic intruder in a progression visually and aurally, names the tonicized degree, and plays the resolution.
- **Lessons & drills:** the full worked example in §7; plus "dominant chains" (V/V/V…) as a circle-of-fifths performance drill.
- **Plug-ins:** widen `is_diatonic_roman` → `is_supported_roman` allowlist (`lab_spec.py:125`); **register `secondary_dominant_network_v1`** (stub already in `PLANNED_TEMPLATES`, `network_template.py:932`) and flip `secondary_dominant_of` from reserved to implemented; the cof detector even has a "dominant pressure hint (for future V/x logic)" waiting (`cof/tonal_detector.js:162`).

### G6 — Non-chord tones
- **Objective:** name what's *not* the chord: passing/neighbor tones, suspensions (4-3, 7-6, 9-8), anticipations, pedal points.
- **Prerequisites:** Voice Leading *completed*; G1 *started*.
- **Outcomes:** learner tags NCTs on a rendered score; performs suspension chains, hearing each dissonance prepared and resolved.
- **Lessons & drills:** click-the-NCT on score (new answer modality U2); play the resolution of a suspension; two-voice species-style preparation for A4.
- **Plug-ins:** new Lab concept `nct`; per-note (not per-chord) targets — the note-level SVG mapping (`verovio_map.py`) already supports it.

### G7 — Modulation to closely related keys
- **Objective:** pivot-chord modulation; tonicization (G5) vs true key change.
- **Prerequisites:** G5 *completed*; Circle of Fifths bridge.
- **Outcomes:** learner performs an 8–12-chord pivot modulation (I … pivot … V7–I in the new key), identifies the pivot's double meaning (IV in C = I in F), and hears where the key turns.
- **Lessons & drills:** guided pivot progressions to each of the five closely related keys; "where did it change?" ear drill (click the pivot).
- **Plug-ins:** **register `modulation_path_network_v1`** ("Reserved until pivot-chord / chromatic support exists", `network_template.py:917`) + `modulation_path_to` edges; functional journey v2 modulation paths (same named roadmap line as G2's minor panels). Fits within the 12-chord cap; longer excursions wait for U5.

### G8 — Voice-leading error detection
- **Objective:** parallel fifths/octaves, doubled leading tones, unresolved 7ths — detected and explained on the learner's own playing.
- **Prerequisites:** Voice Leading *completed*; G4.
- **Outcomes:** learner realizes 4-part cadences without forbidden parallels; reads error highlights as intervals, not vibes.
- **Lessons & drills:** SATB cadence drills with live interval checking between consecutive sonorities; "fix the phrase" — a rendered 4-part phrase with one planted error to find (U2 click modality).
- **Plug-ins:** interval checker over `expected_by_beat` pairs; feeds A4. The `voice_leading_path` scene type already exists (`graph_scene_generators.py:980`).

---

## 4. Advanced feature designs (A-series)

### A1 — Ear-Training Engine (cross-cutting; starts Phase 1)
- **Learning objective:** bidirectional symbol↔sound fluency — every visual drill acquires an aural twin, so audiation is trained on the same vocabulary, not a parallel curriculum.
- **Why it's cheap here:** FluidSynth + soundfont are loaded and idle (`view.py:149-158`); Verovio's `renderToMIDI()` is called and discarded (`view.py:180`); the MIDI grading stack needs zero changes for echo drills.
- **Lessons & drills (in ramp order):**
  1. *Echo-play* — hear the target chord/progression (notation hidden), play it back; existing pitch-class validator grades. **This is the Phase 1 deliverable.**
  2. *Quality ID* — hear a triad (later seventh), answer via MCQ buttons (U2).
  3. *Progression ID* — hear 4 diatonic chords, choose the roman sequence.
  4. *Cadence ID* — PAC / IAC / half / deceptive / plagal by ear (with G3).
  5. *Bass-line dictation* — play only the bass of what you hear (with G4).
  6. *Chromatic spotting* — hear the applied chord / mixture chord, locate and name it (with G5/A2).
- **Didactic principles:** sound-before-symbol ordering inside every lesson; same-content transfer (aural twin unlocks only after the visual leaf is *started*, and both count toward the same mastery record); interleaved review mixes aural and visual forms of one skill.
- **Progression path:** L1 echo triads → L2 qualities → L3 diatonic progressions → L4 cadences → L5 sevenths (G1) → L6 chromatic (G5/A2). Entry: Triads *completed*. Exit: feeds every later module's ear variants.

### A2 — Chromatic Harmony Suite
- **Learning objective:** command the chromatic predominant/dominant vocabulary of the common-practice era: modal mixture, Neapolitan sixth, augmented sixths, common-tone diminished sevenths, chromatic mediants.
- **Lessons & drills:**
  1. *Mixture* — borrowed iv, ♭VI, ♭VII, ♭III in major: A/B ear pairs (IV vs iv), "color the borrowed tone" score-click, performance drills.
  2. *Neapolitan* — ♭II6 as chromatic predominant: play iv6–N6–V–i; hear N6 vs iv6 discrimination.
  3. *Augmented sixths* — It/Fr/Ger approached as chromatic intensification of iv6→V: resolve-the-♯4̂ drill; Ger6 vs V7 ear trap (enharmonically identical sonority, opposite resolution) — a signature discrimination drill.
  4. *CT°7 and chromatic mediants* — the reserved `common_tone_diminished` edge (`network_template.py:100`) gets implemented; mediant color pairs (I→♭VI, I→III) by ear.
- **Didactic principles:** every chord introduced as an *alteration of a known function* (one-new-thing); resolution-first drilling (the chord is taught by where it goes); immediate spelling feedback because Aug6/N6 stress the enharmonic seam (`_enh_note` policy, `harmonic_network.py:1338-1346`).
- **Progression path:** entry gate G2+G5 *completed* → mixture → N6 → Aug6 → CT°7/mediants → exit: chromatic modulation (Ger6 as pivot).

### A3 — Modal Harmony & Interchange Lab
- **Learning objective:** the seven diatonic modes as tonal colors; modal cadences; interchange as a compositional palette.
- **Lessons & drills:** mode-ID by ear from characteristic tone (dorian ♮6, mixolydian ♭7, phrygian ♭2 — the app's Aeolian ♭VII–i cadence already seeds this); "one accidental away" drills morphing major↔mixolydian↔dorian; modal vamp performance (i–♭VII–i exists; add I–♭VII–IV–I etc.); interchange composition drill: recolor a diatonic progression with borrowed chords (bridges to A2).
- **Didactic principles:** anchor every mode to its one characteristic tone (minimal contrast pairs); reuse the existing scale/degree drill patterns (48-leaf scale category generalizes directly).
- **Progression path:** entry Scales+Functions *completed*, G2 *started* → church modes → modal cadences → interchange → exit: A2 mixture (interchange is its gateway).

### A4 — Counterpoint Studio
- **Learning objective:** species counterpoint foundations: intervals-in-motion, dissonance treatment, imitation.
- **Lessons & drills:** species I–III over given cantus (two-voice polyphonic engine + G8 interval checker + G6 NCT taxonomy do the grading); "fix the phrase" error hunts on lab-authored four-part phrases (one planted parallel/doubling error to find, U2 click modality); **unlock the reserved Schenkerian `reduction` concept** (`lab.py:639-644`) as a capstone "hear the skeleton" lesson series.
- **Didactic principles:** constraint-based drilling (rules as live feedback, not post-hoc grades); worked examples before free writing; graduated voice count (2 → 3 → 4).
- **Progression path:** entry G6+G8 *completed* → species I–III → error-hunts → reduction capstone. (Real-chorale ingestion and invention analysis depend on the score pipeline and move to the separate Score Soul repair plan.)

---

## 5. UI/UX enhancements (U-series)

| # | Enhancement | Concrete implementation anchor |
|---|---|---|
| U1 | **Target playback + playback cursor.** Play/tempo/loop transport in the trainer; cursor sweeps the score; noteheads flash as they sound. | All plumbing exists: sequence `TARGET_CHORDS` through the idle `MidiPlayer` (`noteon/noteoff`, `view.py:436-441`) with a QTimer, or use Verovio's timemap (`renderToMIDI` already called, output discarded, `view.py:180`); drive the existing `#cursor`/`jsSetCursorAbs` + `midi-ok` note classes (`cursor.js:45-95`). |
| U2 | **Answer modalities beyond hardware MIDI.** (a) Click-to-answer chord cards (cards are already clickable for navigation, `harmony_trainer.js:303-305` — add an answer mode); (b) MCQ strip for ID drills; (c) make the on-screen piano an *input* (it renders key states but has no pointer handler); (d) QWERTY fallback. Unlocks A1 levels 2–4, G5 spotting, G6 NCT tagging — and learners without a MIDI keyboard. | `keyboard_view.js` (display-only today); trainer panel in `harmony_trainer.js`. |
| U3 | **Home dashboard + mastery heatmap + review queue.** One landing surface aggregating curriculum rollups and journey stages; a 230-leaf heatmap colored by state; "due today" review strip; streaks. Also unify the one-process-per-tool launchers into a tabbed shell (the Lab demo already co-mounts curriculum+trainer+atlas — generalize that). | `curriculum_progress.py` rollups + `functional_journey.py` store exist but are separate systems — merge behind one progress service. |
| U4 | **Adaptive difficulty.** Replace the static 1–5 chip with a live model: per-axis Elo-lite (topic × key-distance × render), select next drill targeting ~80% success, ramp along the §2.2 axes. | `difficulty` currently display-only (`curriculum.js:365`); `attempts/bestScore` already persisted per leaf. |
| U5 | **Longer exercises (fix the 12-chord ceiling).** Root cause: page navigation reloads QWebEngine and wipes the injected controller, so nav is hidden (`run_harmony_trainer_demo.py:506-508,462-467`). Fix by re-injecting the controller on `pageChanged` (nav machinery is fully implemented, `view.py:82-88,221-229`) or rendering `breaks:none` into a scrolling viewport. Keep 12 as the default cap (F6 enforcement) with explicit opt-in for modulation/counterpoint excerpts. | |
| U6 | **Bridge modernization.** Replace the 400 ms `runJavaScript` polling in every launcher with QWebChannel push. Cuts latency for ear-drill grading and eliminates a whole class of race conditions. | `run_harmony_lab_demo.py:28-30` et al. |
| U7 | **Theme + accessibility consistency.** Unlock the hard-coded light panels (`curriculum.html:8`, `harmony_lab.html:8`) to match the score surface's full dark theme; one toggle; ARIA roles + keyboard navigation on cards/nodes/tabs (today only the curriculum tree is keyboard-navigable). | |
| U8 | **Feedback vocabulary.** One color language everywhere: broad-family colors (from `harmonic_roles.py`) shared by network nodes, chord cards, *and noteheads*; resolution arrows on the score (7̂→1̂, 4̂→3̂); explanatory error toasts wired to the §8 error taxonomy. | Legend contract already mirrored Py↔JS (`harmonic_network.py:196` ↔ `harmonic_network.js:132`). |

---

## 6. Prioritized backlog

Effort: S ≤ 2 days, M ≤ 2 weeks, L > 2 weeks.

| Rank | Item | Ref | Effort | Rationale / unlocks |
|---|---|---|---|---|
| 1 | Function-label reconciliation (single vocabulary via `harmonic_roles`) | F1 | S | Learners currently see contradictions; blocks all new prose |
| 2 | Re-tag axis progression; cadence enum alignment | F2, F7 | S | Wrong info shown today |
| 3 | Enforce spec cap + reject augmented specs | F5, F6 | S | Latent crash; invisible chords |
| 4 | Strict-bass grading for inversions | G4/F4 | M | 97 leaves become honest; figured bass real |
| 5 | Target playback + transport | U1 | M | Prereq for all ear training |
| 6 | Echo-play ear drills (aural twins v0) | A1 | M | Highest pedagogy-per-effort in the plan |
| 7 | Click/MCQ/on-screen-piano answer modalities | U2 | M | Unlocks ID drills; removes MIDI-hardware requirement |
| 8 | Review queue (SM-2-lite over `last_played`) + dashboard v0 | U3 | M | Retention machinery; visibility |
| 9 | **G1 seventh chords** (+ un-reserve network dom7) | G1 | L | Gateway to everything chromatic |
| 10 | **G2 harmonic/melodic minor** (+ journey minor panels) | G2 | L | Fixes the largest content limitation (F11) |
| 11 | G3 cadence taxonomy + cadential 6/4 | G3 | M | Repairs mis-framing; PAC/IAC |
| 12 | **G5 applied chords** (+ `secondary_dominant_network_v1`) | G5 | L | Closes the flagship corpus-gap rows |
| 13 | G6 non-chord tones | G6 | M | Suspension/passing-tone vocabulary; prerequisite for counterpoint |
| 14 | G7 modulation (+ `modulation_path_network_v1`) | G7 | M | Named v2 roadmap item |
| 15 | Curriculum gating unification + adaptive v1 | §2.5, U4 | M | Progress systems merge; live difficulty |
| 16 | A2 chromatic suite (mixture → N6 → Aug6 → CT°7) | A2 | L | Advanced core |
| 17 | G8 + A4 counterpoint studio | A4 | L | Species drills + error hunts; reduction unlock |
| 18 | A3 modal lab | A3 | M | Cheap generalization of scale machinery; U5/U6/U7 land alongside as touched |

---

## 7. Worked example — the flagship new drill

**"Spot the intruder" — identify the secondary dominant in a given chord progression** (G5, three stages).

**Spec** (new Lab concept; passes a widened `is_supported_roman` gate):

```json
{
  "schema": "harmony-lab/v1",
  "experiment_id": "applied_spot_v_of_v_c",
  "concept": "applied_chord",
  "key": "C", "mode": "major",
  "progression": ["I", "vi", "V7/V", "V", "I"],
  "render": "block",
  "stages": ["spot", "resolve", "ear"]
}
```

Five chords — comfortably inside `MAX_CHORDS_PER_SPEC = 12`.

**Stage 1 — Spot (visual).** The trainer renders C: I–vi–D7–G–C with roman numerals hidden on the third chord. Prompt: *"One of these chords doesn't live in C major. Click it."* The learner clicks a chord card (U2 answer mode). Feedback: the card turns amber, the F♯ notehead pulses on the score (existing `note-hl` class), and a one-liner appears: *"F♯ isn't in C major — it's the leading tone of G. D7 is **V7/V**: the dominant of the dominant."* In the graph pane, the `secondary_dominant_network_v1` scene lights the new `secondary_dominant_of` edge D7→G.

**Stage 2 — Resolve (performance).** *"Play the intruder, then resolve it."* Learner plays D7 → G on the MIDI keyboard; the unchanged pitch-class validator grades both chords, with the tritone (F♯+C → G+B) flagged green as it resolves. Arpeggio render variant for a second pass.

**Stage 3 — Ear (with A1/U1).** Playback plays the five chords, notation hidden. Learner clicks the position of the chromatic chord while listening, then answers an MCQ: *which degree got tonicized?* (V / IV / ii / vi).

**Difficulty ramp:** fixed position → random position; V7/V only → V7/IV, V7/ii, vii°7/V; C major → keys by circle-of-fifths distance; visual → ear-only. **Mastery:** completed at ≥80% first-attempt detection (existing threshold); mastered when the ear variant holds ≥95% over 3 sessions (existing criterion, `curriculum_progress.py:99-108`).

---

## 8. Success metrics

Instrument in Phase 1 (the progress store already records attempts/bestScore/last_played); targets are for the end of each phase.

**Learning effectiveness**
- First-attempt accuracy per leaf held in the 60–85% band by the adaptive selector (below 60% = mis-sequenced, above 85% = too easy).
- Median attempts-to-*completed* per category; any leaf >2× its category median is flagged as a content defect.
- Retention: ≥80% accuracy on review-queue items due ≥7 days after last practice.
- Transfer: accuracy delta between a leaf's visual and aural twin < 15 points at mastery (else ear training is lagging).
- Error taxonomy rates trending down: ♭7-for-♮7 in minor (G2), bass-note misses (G4), IV-for-ii function confusions (F1).

**Coverage honesty** (the plan's signature metric)
- % of corpus-annotation slices (`data/score_annotations/`) whose chord is *drillable*: today ~0% of seventh/chromatic slices; **target ≥80% after Phase 3**. A static data benchmark for now — it becomes learner-facing again when the separate Score Soul repair plan lands.
- Count of `reserved` seams flipped to implemented (dom7 nodes, `secondary_dominant_of`, `borrowed_from_parallel`, `modulation_path_to`, `common_tone_diminished`, reduction concept).

**Engagement**
- ≥3 practice sessions/week median; session length ≥15 min; mid-drill abandonment <10%; review-queue clearance ≥70% of due items.

**System health**
- Template/scene `validate()` violations in CI: 0. Py↔JS mirror drift tests green (see §9).

---

## 9. Engineering invariants this plan honors

1. **The 12-chord cap** stays the default; new modules chunk by key group as today (`_chunk_keys`). Only U5 may relax it, explicitly, per-spec.
2. **Honesty gates are load-bearing.** A chord occurrence never lands on a key node (`graph_scene.py:669`); a reserved relation is never marked implemented without a launchable drill (`network_template.py:314`). New vocabulary *extends* these gates, never bypasses them.
3. **Py↔JS lockstep pairs** (update both or neither; add drift tests): `NetNode.to_dict` ↔ `indexPayload`; scene role fields (`graph_scene.py:189` ↔ detail panel `harmonic_network.js:1565+`); fnet id reconstruction (`functional_network.py:137` ↔ `degreeNodeIdFor`).
4. **Enharmonic seam:** new chromatic spellings (Ger6, N6's ♭II) route through the `_enh_note` spelling policy; the F♯/G♭ and E♭/D♯ seams are where Aug6 drills will bite first.
5. **One function vocabulary:** `BROAD_FUNCTION` (`harmonic_network.py:100`), `ENGINE_FUNCTION_TO_GROUP` (`functional_network.py:80`), and `_LABEL_TO_BROAD` (`harmonic_roles.py:83`) must stay in agreement — F1's fix should make `harmonic_roles.py` the single source and derive the other two.
6. **fnet v1 vocabulary is frozen by contract** (`functional_network_template.py:14`): minor panels and modulation paths register as *new* templates through the registry seam (`:461`), not by widening v1.

---

## 10. Phase summary

| Phase | Contents | Exit criteria |
|---|---|---|
| **1 — Fix & Foundation** (~4–6 wks) | Backlog 1–8: label/taxonomy fixes, cap enforcement, strict-bass grading, playback, echo drills, answer modalities, review queue + dashboard v0 | No contradictory labels anywhere; every drill playable *and* hearable; a learner without MIDI hardware can complete an ID drill; review queue schedules from real `last_played` data |
| **2 — Chromatic Bridge** (~8–12 wks) | Backlog 9–15: G1→G2→G3→G5→G6→G7, gating unification, adaptive v1 | Every §1.3 table row for *diatonic sevenths, harmonic-minor V, and applied chords* has a live lesson + drill; `secondary_dominant_network_v1` and journey v2 shipped |
| **3 — Advanced Suites** (~10–14 wks, modular) | Backlog 16–18: A2 chromatic suite, A4 counterpoint studio, A3 modal | N6 taught (lesson + drills live); ≥80% corpus-annotation drillability (§8); four-part error-hunt drills live; reduction concept unlocked |

Each phase ships independently; within Phase 2 the G-modules land in prerequisite order but each is individually releasable.
