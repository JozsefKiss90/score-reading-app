# Unified progress service, review queue & home dashboard (ticket 08, U3)

## 1. Goal

One landing surface for the whole platform, built on one progress owner:

* a **unified progress service** — the single reader/writer over the two
  progress files that already existed (curriculum leaves + functional
  journey); both hosts route through it, no migration, byte-compatible files;
* an **SM-2-lite review queue** — spaced repetition scheduled purely from the
  already-persisted per-leaf data (`state`, `attempts`, `avg_accuracy`,
  `last_played`), interleaving top-level categories;
* a **home dashboard v0** — practice streak, "due today" strip, functional
  journey summary, and a mastery heatmap with one cell per exercise leaf
  (247 today; the count is always derived, never hardcoded).

## 2. Architecture

```
harmony/review_queue.py (pure)         harmony/progress_service.py
  ease_factor / interval_days /          ProgressService  — owns BOTH stores:
  due_at        (SM-2-lite math)           · curriculum ProgressStore
  build_review_queue (interleaved          · JourneyProgress (.journey)
    due-today strip)                       curriculum-store facade: load/save/
  streaks (union of last-played            record/started/payload/progress
    dates, current + best)               dashboard_payload (pure) — heatmap +
                                           review + streak + journey + overall
        │                                        │
        ▼                                        ▼
beat_selector/dashboard.html/.js  ◄──  run_dashboard_demo.py (standalone,
  Dashboard.init/setPayload/takeLaunch     read-only, 5 s file re-read)
  renders everything precomputed       run_harmony_lab_demo.py ("Home" tab,
  from Python; clicks enqueue node ids     clicks launch the leaf in the trainer)
```

* **Single reader/writer.** `run_harmony_lab_demo.py` constructs a
  `ProgressService` instead of a raw `ProgressStore`;
  `run_functional_network_demo.py` obtains its `JourneyProgress` from the
  service (`ProgressService(journey_path=...).journey`). Nothing else opens
  the progress files. Default store paths are anchored at the **project
  root** (`DEFAULT_CURRICULUM_PROGRESS_PATH` /
  `DEFAULT_JOURNEY_PROGRESS_PATH`), not the cwd, so every host resolves the
  same files. The service re-reads the journey store on each
  `dashboard_payload` call, so a concurrent Functional Network session's
  stage completions show up in the Lab's Home tab.
* **Leaf state machine unchanged.** The service delegates verbatim to
  `curriculum_progress.record_attempt` / `mark_started`
  (`not_started → started → completed → mastered`); a regression test pins
  service-routed results to direct `record_attempt` results.

## 3. SM-2-lite scheduling (no new stored fields)

* Interval base per state: started 1 d · completed 3 d · mastered 7 d.
* Ease factor: `1.3 + 1.2 × avg_accuracy` (SuperMemo-2's ease bounds),
  raised to `attempts − 1`, capped at 60 days.
* `due = last_played + interval`; unplayed leaves are never due.
* **Rescheduling is implicit**: completing a review records an attempt, which
  moves `last_played` forward and grows `attempts` — the item leaves the
  queue with a longer interval. No queue state is stored anywhere.
* The strip **interleaves categories** (didactic principle 4): items sort
  most-overdue-first within a category, then the queue round-robins the
  categories. `dueCount` always reports the full total past the limit (10).
* Streaks merge both stores' `last_played` dates; `current` survives until a
  full day is missed. v0 honesty: only *last*-played survives per leaf, so a
  day is forgotten if every leaf played then was later replayed — accepted by
  the plan ("SM-2-lite over the already-persisted last-played data").

## 4. Py↔JS contract

`harmony-dashboard/v1` (from `dashboard_payload`): `heatmap`
(categories → leaves with `id/title/state/attempts/dueAt`, `counts`,
`totalLeaves`; leafless/reserved categories draw no row), `review` (`harmony-review-queue/v1`: interleaved `due` +
`dueCount`), `streak` (`current/best/practicedToday`), `journey`
(`stagesCompleted/stagesTotal/drillsFinished/litNodes` — the total is derived
from `journey_stages`, so it can never drift), `overall` (root roll-up).
The JS computes nothing — every number is Python-derived, so the payload is
the single source of truth. Cell/card clicks enqueue the leaf's curriculum
node id (`Dashboard.takeLaunch()`); leaf ids equal the Lab's launch ids
(`ex:<experiment_id>`), so dashboard launches record onto the same mastery
records. Heatmap state colors reuse the curriculum tree's palette (amber
started / green completed / violet mastered).

## 5. Files

- `harmony/review_queue.py` — pure scheduler + streaks.
- `harmony/progress_service.py` — the service + pure `dashboard_payload`.
- `beat_selector/dashboard.html/.js` — the panel (DOM-decoupled helpers).
- `run_dashboard_demo.py` — standalone launcher + reusable `DashboardView`.
- Hosts: `run_harmony_lab_demo.py` (service + Home tab),
  `run_functional_network_demo.py` (journey via service).
- Tests: `tests/test_review_queue.py`, `tests/test_progress_service.py`,
  `tests/dashboard_node_test.js`.

## 6. Deferred (v0 scope cuts)

- The **tabbed shell** unifying the one-process-per-tool launchers ("if v0
  scope allows"): not done; the Lab workspace's Home tab is the landing
  surface for now, and the standalone dashboard re-reads the files live.
- Per-category interleaving is round-robin only; no priority weighting by
  difficulty or adaptive scheduling (that is U4 / ticket 22).
- The standalone dashboard is read-only (the trainer lives in the Lab).
