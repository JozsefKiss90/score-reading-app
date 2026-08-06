# 12 — G1d: un-reserve the network dom7 nodes

**What to build:** The harmonic network's 12 dominant-seventh nodes stop being visual-only. Clicking a dom7 node launches a real V7 drill in that key; the reserved→launchable flip happens in the Python template layer and the JS runtime in lockstep. The graph was built waiting for this — the honesty rule (never flip a reserved seam without a launchable drill) is satisfied by ticket 09's drills.

**Blocked by:** 09 — G1a V7 tracer.

**Status:** done

- [x] Every dom7 node in the network launches a V7 drill in its key.
- [x] Reserved markers are removed in Python and JS together; the mirror drift test is green.
- [x] Template validation passes: the flip is justified by an actually launchable drill.

**Plan:** docs/curriculum_expansion_plan.md §3 G1, §8 (reserved-seam count), §9.2–9.3

**Shipped (ticket 12):**
- `harmony/harmonic_network.py`: `_reserved_entry` deleted. Each of the 12
  legacy dom7 nodes carries one launchable `function_spec(["V7","I"])` drill in
  its key (48 launchable / 0 reserved); the functional-equivalence template's
  V7 node launches the same drill (entity_role `reference`→`instance`); the
  `trainer_drill_available` overlay now points dom7→tonic key (where the V7→I
  drill lives), mirroring the vii° edge.
- `harmony/network_template.py`: both templates move `dominant_seventh` into
  `launchable_kinds` (`reserved_kinds` now empty); node-class labels and
  descriptions updated ("V7 (reserved)" → "V7").
- `harmony/network_launch.py`: `_reserved_action` deleted; the dom7 node's
  primary action is the launchable V7→I drill, with the V→I triad kept as an
  honestly-labelled "seventh-less reduction" comparison.
- `harmony/network_projection.py`: a compiled V7 tetrad (degree 4, quality
  `dominant_seventh`) now maps **exact** onto its dom7 node; natural minor's
  VII7 stays a contextual proxy; the V *triad* stays approximate.
- `beat_selector/harmonic_network.js`: `RESERVED_DRILLS` gate removed in
  lockstep (launch queue + detail panel); mirror drift covered by
  `tests/harmonic_network_node_test.js`, which runs against the live Python
  payload (135 assertions green).
- `harmony/graph_scene_router.py`: the inversion-space tetrad refusal stays
  (that scene voices triads only) — its reason no longer cites G1d.
- Tests: `test_harmonic_network.py` (per-key V7 acceptance + flip-justified
  gate), `test_network_templates.py`, `test_network_launch.py`,
  `test_network_projection.py` (exact V7 / subtonic-VII7 honesty). Full suite
  1046 passed; all 17 JS node suites pass.
