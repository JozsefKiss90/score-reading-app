# 22 — Gating unification + adaptive difficulty v1 (U4)

**What to build:** Prerequisites become honest soft locks, and difficulty becomes live. The curriculum's advisory prerequisites are enforced as recommended-with-override locks, reusing the finish-any/finish-all gating the journey already implements — one gating system, not two. The static 1–5 difficulty chip is replaced by a per-axis Elo-lite model (topic × key-distance × render) that selects the next drill targeting ~80% first-attempt success and ramps along the plan's one-new-thing axes.

**Blocked by:** 08 — unified progress service.

**Status:** ready-for-agent

- [ ] Locked-but-overridable leaves render distinctly; overriding is possible and recorded.
- [ ] The journey's gating machinery is reused for curriculum prerequisites, not duplicated.
- [ ] The adaptive selector proposes next drills; per-axis difficulty estimates update from attempt history.
- [ ] First-attempt accuracy is instrumented toward the 60–85% band metric (§8).

**Plan:** docs/curriculum_expansion_plan.md §2.5, §5 U4, §8
