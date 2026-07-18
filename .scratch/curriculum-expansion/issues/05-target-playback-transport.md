# 05 — Target playback + transport (U1)

**What to build:** Every drill can be heard, not just seen. A transport (play/pause, tempo, loop) in the trainer plays the target chords through the already-loaded synth; the cursor sweeps the score in time; noteheads flash as they sound. This is the prerequisite for all ear training.

**Blocked by:** None — can start immediately.

**Status:** ready-for-human

- [x] A play button sounds the target progression at a chosen tempo; loop repeats it; pause/stop work.
- [x] The score cursor and notehead highlights track playback in sync.
- [x] Playback is available in every launcher that hosts the trainer.
- [x] The learner's own MIDI monitoring is unaffected when the transport is idle.

**Plan:** docs/curriculum_expansion_plan.md §5 U1, §2.1

## Comments

**Implemented** (branch `fable_refactor`):

- **Pure plan seam** (`harmony/playback_plan.py`, new): `build_playback_plan(payload)` turns a trainer/lab payload into beat-timed note events — one 4/4 measure per target, playing exactly what the score notates. Block: `midiPitches` + the new `bassMidi` field for the full measure (the lab's `voice_leading`/`polyphonic` concepts are whole-note notations too, so they block-play deliberately). Arpeggio/melody: bass held 4 beats while tones sound one slot each, driven by `EXPECTED_MIDI_BY_MEASURE_OR_BEAT` (first payload consumer of that field) — 4 quarter slots, or 8 eighth slots when the map extends past beat 4 (long motives). Playback follows *notation*, not grading: lab strict-bass measures grade as ordered walks (`render: "arpeggio"`) but play as the block chords they notate — the lab's `concept` field overrides `render`.
- **`bassMidi` payload field** (`harmony/musicxml_builder.py` `_target_for`, `harmony/lab_musicxml.py` `_lab_target_for`): the notated bass-staff whole note was absent from `midiPitches` in trainer payloads, so playback would have skipped a sounding notehead. Lab targets take the lowest staff-2 sounding note (None when the bass is a rest, e.g. melody motives), keeping the lab-superset-of-trainer-keys parity test green.
- **Qt transport engine** (`audio/target_playback.py`, new): `TargetTransport(QObject)` on a ~35 ms QTimer beat clock (wall-clock delta × bpm, so live tempo changes rescale in flight). Play / pause (silences but holds position; resume re-attacks held notes) / stop (rewind + `playbackClear`) / loop (wraps). Sounds through the score widget's already-loaded `MidiPlayer.fs` (guarded: missing soundfont ⇒ silent but cursor/flash still run), sweeps the cursor each tick via the page-global `jsSetCursorAbs` mapped into notated-measure seconds, and mirrors each onset into the controller's flash API. Idle ⇒ no timers, no synth, no JS (criterion 4); playing ⇒ never writes grading state either.
- **Notehead flash** (`beat_selector/harmony_trainer.js`): `playbackFlash(absMeasure, midis, durMs)` lights the noteheads that actually sound — octave-exact against `PITCH_MAP` (new `idsByMidiForMeasure`, sibling of the pc map), pc fallback otherwise — with a new amber `pb-live` SVG class distinct from learner green/red. Per-id stamps let overlapping flashes (held bass under per-beat tones) expire independently. `playbackClear()` un-lights everything and re-parks the cursor on the learner's current grading target.
- **Transport UI** (`run_harmony_trainer_demo.py`): ▶ Play/⏸ Pause toggle, ⏹, Loop checkbox, tempo spinner (30–240 bpm, default 80 = the notated tempo) in the `HarmonyTrainerWindow` top bar — so every launcher that hosts the trainer (standalone, Atlas, Lab, Harmonic Network, Functional Network, Curriculum) gets it for free (criterion 3). `_show_score` stops the transport before the widget swap and re-attaches after mount, covering `load_index`, `load_external_spec`, and `load_external_lab`.
- Docs: new §6 "Target playback (transport)" in `docs/harmony_trainer.md`.
- **Code review (two-axis) outcome**: the spec axis caught a real bug — the plan clamped beat-map keys to 1..4, so 5–8-degree motives (notated as eighths keyed 1..8, e.g. `motive_54321_minor`) silently dropped their tail and played quarters; fixed by deriving the slot grid from the map itself (regression-tested). Also fixed from review: resume and live tempo changes now re-issue notehead flashes for held notes (their JS timers expire on wall clock during a pause / were scheduled at the old tempo); the octave-exact JS map walker is now shared with the grading pc walker instead of cloned; transport JS strings use the repo's f-string convention. Accepted as-is with rationale: raw `fs.noteon/noteoff` access mirrors `view.py`'s own monitor path (`MidiPlayer` exposes no per-note API), and playback shares synth channel 0 with the learner's monitor — during playback a transport noteoff can clip an identical learner-held pitch; criterion 4 only covers idle, noted as a known limitation.
- Tests: `tests/test_playback_plan.py` (17, TDD'd first: bassMidi, block/arpeggio plans, concept-overrides-render, pc fallback, eighth-slot motives, tempo math) + `tests/test_target_playback.py` (13, deterministic white-box ticks: play/pause-resume/stop/loop, resume/tempo re-flash, idle-touches-nothing, cursor sweep in measure seconds, synthless operation) + `tests/harmony_trainer_playback_test.js` (20 assertions: octave-exact flash, independent expiry, clear + grading-state isolation).
