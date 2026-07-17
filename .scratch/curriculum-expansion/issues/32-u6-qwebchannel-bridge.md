# 32 — U6: bridge modernization (polling → push)

**What to build:** Replace the 400 ms JavaScript-polling bridge in every launcher with QWebChannel push messaging. Grading feedback becomes push-driven — lower latency for ear-drill grading and a whole class of race conditions eliminated.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] All launchers communicate via the push channel; the polling code is gone.
- [ ] Grading round-trip latency is measurably lower; no regressions in drill flows.
- [ ] Existing Python↔JS payload contracts are unchanged (drift tests stay green).

**Plan:** docs/curriculum_expansion_plan.md §5 U6
