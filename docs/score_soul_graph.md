# Score Soul Graph / Live Harmonic Network Analysis

A controlled, curated, measure-level harmonic reading of **one real score at a
time**, synchronised live with the Atlas and the Harmonic Network. The pilot
score is **BWV 846** (Bach's C-major Prelude, WTC I); **BWV 999** (C-minor
Prelude) is annotation-ready as the second pilot.

This is deliberately **not** a universal Bach analyser. Curated annotations are
the source of truth; a conservative heuristic only cross-checks / fills blanks;
chromatic events the diatonic-triad engine cannot honestly model are **marked,
not faked**.

> The general **Harmonic Network** is the tonal *universe*. The **Score Soul
> Graph** is one piece's *path* through that universe — its "mandala".

## Layers (all pure/deterministic/headless except the launcher + web UI)

| Module | Role |
|---|---|
| `harmony/score_analysis.py` | The contract: `ScoreHarmonySlice`, `ScoreCadenceSpan`, `ScoreFormSection`, `ScoreAnalysisResult` (schema `score-analysis/v1`) + the Atlas/Network bridge (`atlas_refs_for`, `network_refs_for`, `atlas_sync_target`, `resolve_slice_refs`). Never mutates the Atlas/Network node sets — it only references ids that exist. Separate from (and does not touch) the reserved `atlas.ScoreAnalysis` placeholder. |
| `harmony/score_import.py` | music21 importer (`.mxl/.musicxml/.xml`) → per-measure `MeasureData`; merges a curated sidecar (source of truth) with extracted notes → `ScoreAnalysisResult`. Bundles BWV 846 locally (`ensure_local_bwv846`). |
| `harmony/score_heuristic.py` | Phase 7: conservative pitch-class-set vs diatonic-triad coverage inference. Marks chromatic → `unsupported_chromatic`, multi-fit → `ambiguous`, prefers root-in-bass. **Never overwrites curated annotations.** |
| `harmony/score_graph.py` | The radial "mandala" (schema `score-graph/v1`). 11 node types, 9 edge relations. **All layout computed in Python** (JS does zero math). |
| `data/score_annotations/*.json` | Curated sidecars: `bwv846_prelude_c_major.json` (34 bars), `bwv999_prelude_c_minor.json` (12 bars, score-file pending). |
| `beat_selector/score_soul.{html,css,js}` | `window.ScoreSoul` — left navigator (sections/measures/cadences) + trainer-style chord card + the mandala SVG. DOM-guarded (headless-safe). |
| `run_score_harmonic_network_demo.py` | 3-pane launcher. **Reuses** `ScoreViewBeats`, `HarmonicNetworkView`, `AtlasView` unchanged. |

## Live sync (per measure)

The launcher owns a single `set_measure(m)` entry point. On every measure change:

1. **Score cursor** → `ScoreViewBeats.set_music_time(measures[m].start_sec)` (auto-paginates).
2. **Harmonic Network** → `HarmonicNetworkView.highlight_from_trainer(slice.network_target())`
   — `{key, mode, roman, root, quality}`. The Python `network_refs_for` mirrors the JS
   `highlightFromTrainerTarget` resolution exactly, so stored refs == live highlight.
3. **Atlas** → `AtlasView.set_sync(atlas.sync(atlas_sync_target(slice))["active"])`.
4. **Score Soul** → `ScoreSoul.setCurrentMeasure(m)` (chord card + mandala constellation).

User clicks (measure list / mandala node) flow back via `ScoreSoul.takeSelection()` (a drained queue polled at 200 ms) → `set_measure`.

## Honesty model

A slice is `status="ok"` only when every pitch class is diatonic to the score
key. Otherwise it is `unsupported_chromatic` (secondary dominant / applied
diminished 7th / harmonic-minor / Neapolitan) or `ambiguous` (no single triad).
A chromatic chord **never** claims a diatonic-triad Atlas node unless the curator
sets an explicit `base_roman` for a chord that genuinely contains that diatonic
triad (e.g. the leading-tone `vii°` inside a `vii°7`). The network still
highlights the applied dom7/dim node by pitch class, illustrating the chord
without pretending it is diatonic.

### BWV 846 coverage (34 bars, all annotated)

- Diatonic bars: I, ii(7), V(6/5/7), vi(7), IV(7), cadential I6/4 — full Atlas + Network mapping.
- Chromatic bars (honestly marked): **6, 10** V7/V · **12** vii°7/ii · **14, 23** vii°7 · **20, 31** V7/IV · **22, 27** vii°7/V.
- Ambiguous: **29** (dominant 11-suspension, no third).
- Cadences: opening V6/5–I (m3–4) and the closing PAC (m33–34) → both resolve to the Atlas `cadence:Authentic_major` node.

### BWV 999 readiness

Not in the music21 corpus, so the sidecar is curated from analytical knowledge
and **not yet verified against an imported score** (drop a
`data/scores/bwv999_prelude_c_minor.mxl` to enable live rendering). The diatonic
C-natural-minor bars (i, iv, III, VI, VII, ii°) map; the harmonic-minor dominant,
the Neapolitan, and the secondary dominant are flagged `unsupported_chromatic` —
this is the roadmap signal for a future harmonic-minor + secondary-dominant layer.

## Tests

`tests/test_score_analysis.py`, `tests/test_score_import.py`,
`tests/test_score_graph.py` (pytest) + `tests/score_soul_node_test.js` (headless
`window.ScoreSoul` against the real Python payload). The full suite stays green
(410 Python + 9 JS suites); no existing file was modified.

## Non-goals (unchanged)

No universal Bach analysis, counterpoint engine, Schenkerian reduction,
harmonic-minor engine, secondary-dominant trainer drills, or seventh-chord
trainer exercises. Those remain reserved/roadmap.
