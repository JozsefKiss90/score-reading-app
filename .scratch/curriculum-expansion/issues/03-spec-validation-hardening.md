# 03 — Spec validation hardening (F5, F6)

**What to build:** Hand-authored or bridge-supplied exercise specs can no longer crash the renderer or silently overflow the visible page. Validation rejects augmented-quality specs (until III+ ships legitimately in ticket 14) and specs exceeding the 12-chord cap, each with a clear explanatory error.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] An augmented-quality spec fails validation with an explanatory error instead of compiling to zero chords and crashing the score builder.
- [ ] A 13-chord spec fails validation; no override exists yet (the explicit opt-in flag arrives with ticket 31).
- [ ] Tests cover both rejections and the happy path at exactly 12 chords, including specs arriving via custom JSON and the circle input.

**Plan:** docs/curriculum_expansion_plan.md §1.2 F5, F6
