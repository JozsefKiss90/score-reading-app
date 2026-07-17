# 18 — G5b: secondary-dominant network template

**What to build:** The planned secondary-dominant network template registers for real: `secondary_dominant_network_v1` moves from the planned-stubs list into the registry, and the `secondary_dominant_of` relation flips reserved→implemented. During a spot drill, the graph pane lights the applied edge (e.g. D7→G).

**Blocked by:** 17 — G5a applied-chord tracer (the honesty gate requires a launchable drill before the flip).

**Status:** ready-for-agent

- [ ] The template is registered, renders, and passes validation.
- [ ] `secondary_dominant_of` is implemented only where a launchable drill exists.
- [ ] The scene lights the applied-dominant edge during the drill; Python and JS stay in lockstep (drift test green).

**Plan:** docs/curriculum_expansion_plan.md §3 G5, §9.2–9.3
