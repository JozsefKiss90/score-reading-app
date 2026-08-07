# 18 — G5b: secondary-dominant network template

**What to build:** The planned secondary-dominant network template registers for real: `secondary_dominant_network_v1` moves from the planned-stubs list into the registry, and the `secondary_dominant_of` relation flips reserved→implemented. During a spot drill, the graph pane lights the applied edge (e.g. D7→G).

**Blocked by:** 17 — G5a applied-chord tracer (the honesty gate requires a launchable drill before the flip).

**Status:** ready-for-human

- [x] The template is registered, renders, and passes validation.
- [x] `secondary_dominant_of` is implemented only where a launchable drill exists.
- [x] The scene lights the applied-dominant edge during the drill; Python and JS stay in lockstep (drift test green).

**Implementation notes (2026-08-08):** shipped on `fable_refactor`.

`secondary_dominant_network_v1` builds the key centre + seven diatonic triads
(reusing the core node rules) + one `applied_dominant` node per buildable token
of the mode (`applied_tokens_for_mode`, i.e. both `V/x` and `V7/x`). **The
honesty gate is structural:** a node is emitted only if its `V(7)/x → x`
resolution drill compiles, so no `secondary_dominant_of` edge can outrun the
content; and applied nodes carry no `belongs_to_key` edge — the *missing* link
is how the graph states the chord is chromatic. Two of seven degrees never get
an applied node (the tonic, whose applied dominant is the home V, and the
diminished degree, which cannot act as a momentary tonic).

The relation left `RESERVED_RELATIONS` and the legacy circle template stopped
naming it (its "Reserved:" strip stays honest). Ticket 17's fail-closed router
became precedence rule 0: an applied chord takes `secondary_dominant_path` and
**nothing else** — metadata hints and manual overrides still cannot put it on a
diatonic scene. The scene draws the diatonic row with the intruder lifted above
it; its applied arrow is drawn only where the template independently supports
the token→target pair, and lands in the occurrence's `theoryEdgeIds`, so the JS
lights it while the intruder plays.

**Review outcomes.** Both review axes independently caught one real defect: the
scene claimed `next_theory_relation="secondary_dominant_of"` for the step to the
*next* chord even when the tonicised target was further ahead (`V7/V–I–V`). Fixed
— the relation is claimed only when the target IS the next occurrence, while the
arrow still points at the real target; regression test
`test_a_delayed_resolution_is_never_claimed_as_the_next_relation`.

Leaving `RESERVED_RELATIONS` would have dropped the schema-level "no relation
without content" gate, so `validate()` gained a replacement: a template may only
mark `secondary_dominant_of` implemented if it declares the `applied_dominant`
node class *and* runs both `secondary_dominant_*` rules — the rules that gate the
node on a launchable drill. A reported flake in `test_applied_nodes_are_not_diatonic`
did not reproduce (50 rebuilds + 3 runs, all 7 `belongs_to_key` edges); it was a
mid-edit snapshot of the working tree during the review.

Also hardened: `network_projection._resolve_chord` used to have no applied case,
so `V7/V`'s letter-offset `degree_index` (1 in C) would have mapped D7 onto the
`Dm` node — it now maps to its own applied node or an `overlay:applied:` proxy,
never a diatonic one. Py↔JS lockstep: the `applied` edge visual class exists in
`edgeColor` + `EDGE_STYLE` + the CSS, covered by the dash drift guard (test K),
plus new JS tests R (template payload renders) and J (the scene lights the edge).

Two adjacent changes were required by the flip rather than chosen: `network_launch`
gained an `_applied_node_actions` branch (without it an applied node fell into the
diatonic triad branch and would have been offered "tonic family neighbours"), and
the projector fix above (without it the launch panel's preview projection put D7
on the `Dm` node). Known cost: the scene builds two networks per render (~50 ms vs
~4 ms for the diatonic progression scene) — acceptable at once-per-drill-change,
worth revisiting if scenes ever rebuild per chord.

**Plan:** docs/curriculum_expansion_plan.md §3 G5, §9.2–9.3
