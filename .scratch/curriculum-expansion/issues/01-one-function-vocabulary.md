# 01 — One function vocabulary (F1)

**What to build:** A learner sees exactly one name for each harmonic function, everywhere. Today the same IV is "subdominant" in engine labels, "predominant" in curriculum prose, and an `S` token in drills — all in one session. The new two-level role model (broad family + specific role) becomes the single vocabulary source, and every surface that renders a function name (engine labels, curriculum prose, drill tokens, graph legends and detail panels) derives from it.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] The two-level role model is the single source of function vocabulary; the engine's function map and the functional network's group map are derived from it, not maintained in parallel (plan §9.5).
- [ ] Curriculum prose, drill tokens, and Atlas/graph legends all render labels from the shared vocabulary — no surface hard-codes its own synonym.
- [ ] The internal family key vs presentation family label distinction is preserved (they are different strings by design).
- [ ] A drift test fails if any derived vocabulary disagrees with the source.

**Plan:** docs/curriculum_expansion_plan.md §1.2 F1, §9.5
