# 08 — Unified progress service + review queue + dashboard v0 (U3)

**What to build:** One landing surface for the whole platform. The curriculum progress store and the journey progress store merge behind a single progress service; an SM-2-lite scheduler builds a "due today" review strip from the already-persisted last-played data, interleaving categories; a heatmap shows all 230 leaves colored by mastery state; streaks are displayed. If v0 scope allows, the one-process-per-tool launchers unify into a tabbed shell (the Lab demo already co-mounts three panels — generalize that).

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] One progress service is the only reader/writer; both existing stores route through it.
- [ ] The review queue schedules items due by an SM-2-lite rule over last-played; completing an item reschedules it.
- [ ] The dashboard shows the 230-leaf mastery heatmap and a "due today" strip.
- [ ] Existing per-leaf state transitions (not_started→started→completed→mastered) are unchanged.

**Plan:** docs/curriculum_expansion_plan.md §5 U3, §2.4
