# 08 — Unified progress service + review queue + dashboard v0 (U3)

**What to build:** One landing surface for the whole platform. The curriculum progress store and the journey progress store merge behind a single progress service; an SM-2-lite scheduler builds a "due today" review strip from the already-persisted last-played data, interleaving categories; a heatmap shows all 230 leaves colored by mastery state; streaks are displayed. If v0 scope allows, the one-process-per-tool launchers unify into a tabbed shell (the Lab demo already co-mounts three panels — generalize that).

**Blocked by:** None — can start immediately.

**Status:** done

- [x] One progress service is the only reader/writer; both existing stores route through it.
- [x] The review queue schedules items due by an SM-2-lite rule over last-played; completing an item reschedules it.
- [x] The dashboard shows the 230-leaf mastery heatmap and a "due today" strip.
- [x] Existing per-leaf state transitions (not_started→started→completed→mastered) are unchanged.

**Plan:** docs/curriculum_expansion_plan.md §5 U3, §2.4

**Implementation notes (2026-08-05):**

- `harmony/progress_service.py` (new): `ProgressService` owns BOTH progress
  files (curriculum `.curriculum_progress.json` + journey
  `.functional_network_progress.json`), exposes the curriculum store's exact
  API so the Lab host routes through it unchanged, and hands out
  `.journey` (a `JourneyProgress`) for the Functional Network host. Files
  adopted as-is — no migration. Pure `dashboard_payload` builds the
  `harmony-dashboard/v1` JSON (heatmap + review + streak + journey + overall).
- `harmony/review_queue.py` (new, pure): SM-2-lite over already-persisted
  fields only (state base 1/3/7 d × ease 1.3–2.5 from `avg_accuracy`,
  ^(attempts−1), 60 d cap; due = `last_played` + interval). Rescheduling is
  implicit: recording the attempt moves `last_played`/`attempts`. The
  due-today strip interleaves top-level categories round-robin
  (most-overdue-first within each). Streaks merge both stores' dates.
- State-machine regression pinned: service-routed records byte-equal direct
  `record_attempt` results (`test_state_transitions_unchanged`).
- Heatmap is all **231** leaves (the ticket's "230" was approximate; count is
  derived, never hardcoded).
- UI: `beat_selector/dashboard.html/.js` (`Dashboard.init/setPayload/
  takeLaunch`; computes nothing — all numbers precomputed in Python).
  `run_dashboard_demo.py` = standalone read-only landing surface (5 s file
  re-read) + reusable `DashboardView`; the Lab workspace mounts it as the
  first right-tab ("Home") where due-card/heatmap clicks launch the leaf in
  the trainer (leaf ids ≡ launch ids, one mastery record).
- v0 scope cut: the optional tabbed launcher shell was NOT built (Home tab +
  live standalone view cover the landing surface); adaptive weighting is U4.
- Tests: `tests/test_review_queue.py` (21), `tests/test_progress_service.py`
  (12), `tests/dashboard_node_test.js` (17 assertions); offscreen live smoke
  renders 231 cells + streak line from the real files.
- Docs: `docs/progress_dashboard.md` (new).
- Two-axis code review applied: empty/reserved categories draw no heatmap
  row; default store paths anchored at the project root (shared constants,
  no cwd dependence, no re-spelled filenames); the service re-reads the
  journey store per dashboard payload so concurrent Functional Network
  sessions show up in the Lab's Home tab; `_stages_total` → `lru_cache`.
  Accepted as-is: `ProgressService`'s thin facade (the "single owner" seam
  is the point), per-panel bridge boilerplate (established idiom).
