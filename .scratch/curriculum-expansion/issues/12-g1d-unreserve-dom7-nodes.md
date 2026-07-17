# 12 — G1d: un-reserve the network dom7 nodes

**What to build:** The harmonic network's 12 dominant-seventh nodes stop being visual-only. Clicking a dom7 node launches a real V7 drill in that key; the reserved→launchable flip happens in the Python template layer and the JS runtime in lockstep. The graph was built waiting for this — the honesty rule (never flip a reserved seam without a launchable drill) is satisfied by ticket 09's drills.

**Blocked by:** 09 — G1a V7 tracer.

**Status:** ready-for-agent

- [ ] Every dom7 node in the network launches a V7 drill in its key.
- [ ] Reserved markers are removed in Python and JS together; the mirror drift test is green.
- [ ] Template validation passes: the flip is justified by an actually launchable drill.

**Plan:** docs/curriculum_expansion_plan.md §3 G1, §8 (reserved-seam count), §9.2–9.3
