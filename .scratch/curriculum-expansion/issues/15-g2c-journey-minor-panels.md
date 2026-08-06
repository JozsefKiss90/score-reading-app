# 15 — G2c: functional journey v2 minor panels

**What to build:** Minor-key staged journeys. The functional journey gains minor panels registered as *new* templates through the registry seam — the v1 vocabulary is frozen by contract and must not be widened. This is the named v2 roadmap item.

**Blocked by:** 13 — G2a harmonic minor.

**Status:** done

- [x] At least one minor-key journey panel (e.g. A minor) exists with stages mirroring the major panels, using the real minor V.
- [x] Panels register as new templates; the v1 template is untouched.
- [x] Exact-id sync between Python and JS holds (drift test green).

**Plan:** docs/curriculum_expansion_plan.md §3 G2, §9.6

**Shipped (ticket 15):**
- `harmony/functional_network_template.py`: new `mode` template field
  ("major"/"minor", validated, serialized, default major) and the
  `functional_degree_network_minor_v2` factory registered through the
  `TEMPLATES` seam — four minor panels (A, E, D, B: the relative minors of
  v1's journey), same frozen vocabulary/geometry, v1 factory untouched.
- `harmony/functional_network.py`: mode-aware builder — minor panels
  generate chords with `harmonic_minor` (the real V / vii°, i ii° III+ iv V
  VI vii°), node ids use `m`-suffixed key tokens (`fnet:deg:Am:4`, disjoint
  from every major id), Atlas refs follow the G2a natural-minor-twin honesty
  rule (chord nodes only on exact pitch match; III+/V/vii° claim quality
  only), key context claimed `natural_minor`. Fingerprint 44 nodes /
  91 edges (only 4 shared_triad — altered chords are panel-unique).
- `harmony/functional_journey.py`: `journey_stages` dispatches on
  `template.mode`; 7 minor stages mirror the major machine with
  `_minor`-suffixed stage ids (shared progress store stays collision-free)
  and all-harmonic-minor drills; `drill_node_ids` reads the panel mode off
  each compiled chord's key.
- `beat_selector/harmonic_network.js`: `highlightFromDegreeTarget` gates on
  `template.mode` (a minor target clears the major graph and vice versa)
  and rebuilds `m`-suffixed ids for minor payloads.
- `run_functional_network_demo.py`: `--minor` / `--template <id>` flags;
  per-chord lighting derives the panel mode from the target key.
- Tests: `tests/test_functional_minor.py` (39 tests) +
  minor payload section in `tests/functional_network_node_test.js`;
  docs/functional_network.md v2 section.
