# 31 — U5: longer exercises (lift the 12-chord ceiling, opt-in)

**What to build:** Specs longer than 12 chords become possible, explicitly. Fix the root cause — page navigation reloads the web view and wipes the injected controller — either by re-injecting the controller on page change (the nav machinery already exists) or by rendering without page breaks into a scrolling viewport. Twelve stays the default cap; exceeding it requires an explicit per-spec opt-in flag (completing ticket 03's enforcement story). Needed for extended modulation and counterpoint excerpts.

**Blocked by:** 03 — spec validation hardening (the cap this adds an override to).

**Status:** ready-for-agent

- [ ] A >12-chord spec with the explicit flag renders fully and grades across the entire exercise — no invisible chords.
- [ ] Without the flag, the cap is still enforced.
- [ ] The trainer controller survives page navigation (or navigation is eliminated by a scrolling render).

**Plan:** docs/curriculum_expansion_plan.md §5 U5, §9.1
