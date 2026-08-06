"""Tests for the Functional Degree Network's minor journey panels (ticket 15 / G2c).

Minor-key staged journeys register as a *new* template through the registry
seam (``functional_degree_network_minor_v2``); the frozen v1 vocabulary and the
v1 template itself are untouched.  These tests enforce the v2 contract:

  * template registration -- ``mode="minor"``, journey keys A/E/D/B (the
    relative minors of v1's C/G/F/D: no enharmonic seam), v1 untouched;
  * node ids -- minor panels use ``m``-suffixed key tokens
    (``fnet:deg:Am:4``), disjoint from every major id, so both journeys can
    share one progress store and the JS exact-id sync can address them;
  * the real minor V -- panels are generated with ``harmonic_minor`` chords
    (i, ii°, III+, iv, V, VI, vii°), so V is E major in A minor (G2a);
  * ref honesty (the G2a / Score Soul precedent) -- the KEY context is claimed
    natural minor; chord-level Atlas nodes only on an exact natural-minor
    pitch match (i / ii° / iv / VI); the raised chords (III+ / V / vii°) claim
    only their quality class;
  * shared_triad honesty across minor panels; the fifths chain D->A->E->B;
  * journey stages -- 7 minor stages mirroring the major machine, stage ids
    suffixed ``_minor`` (disjoint progress-store namespace), all drills in
    ``harmonic_minor`` mode and within the readability cap;
  * drill -> node mapping (``drill_node_ids``) lands on the minor ids.

Run from the project root::

    .venv/Scripts/python.exe -m unittest tests.test_functional_minor
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from theory.diatonic_harmony import note_pc  # noqa: E402
from harmony.exercise_spec import (  # noqa: E402
    HarmonyExerciseSpec, compile_exercise, MAX_CHORDS_PER_SPEC,
)
from harmony.functional_network_template import (  # noqa: E402
    TEMPLATES, get_template, load_template,
    functional_degree_network_v1, functional_degree_network_minor_v2,
    FUNCTION_GROUPS,
)
from harmony.functional_network import (  # noqa: E402
    build_functional_network, build_functional_network_payload,
    degree_node_id, function_node_id, key_node_id,
)
from harmony.functional_journey import journey_stages, drill_node_ids  # noqa: E402


MINOR_TEMPLATE_ID = "functional_degree_network_minor_v2"


def _minor_net():
    return build_functional_network(get_template(MINOR_TEMPLATE_ID))


# ---------------------------------------------------------------------------
# 1. Template registration (the registry seam; v1 untouched)
# ---------------------------------------------------------------------------

class TestMinorTemplate(unittest.TestCase):
    def test_registered_through_the_registry_seam(self):
        self.assertIn(MINOR_TEMPLATE_ID, TEMPLATES)
        tpl = get_template(MINOR_TEMPLATE_ID)
        tpl.validate()          # must not raise
        self.assertEqual(tpl.template_id, MINOR_TEMPLATE_ID)
        self.assertEqual(tpl.mode, "minor")
        self.assertEqual(tpl.journey_keys, ["A", "E", "D", "B"])

    def test_template_id_keeps_the_fnet_routing_prefix(self):
        # harmonic_network.js routes exact-id sync on this prefix.
        self.assertTrue(MINOR_TEMPLATE_ID.startswith(
            "functional_degree_network"))

    def test_v1_template_is_untouched(self):
        tpl = get_template()
        self.assertEqual(tpl.template_id, "functional_degree_network_v1")
        self.assertEqual(tpl.mode, "major")
        self.assertEqual(tpl.journey_keys, ["C", "G", "D", "F"])

    def test_unknown_mode_fails_validation(self):
        tpl = functional_degree_network_minor_v2()
        tpl.mode = "dorian"
        with self.assertRaises(ValueError):
            tpl.validate()

    def test_mode_round_trips_through_serialisation(self):
        tpl = functional_degree_network_minor_v2()
        again = load_template(tpl.to_dict())
        self.assertEqual(again.mode, "minor")
        self.assertEqual(again.journey_keys, tpl.journey_keys)
        # a v1-era dict without the field defaults to major
        d = functional_degree_network_v1().to_dict()
        d.pop("mode", None)
        self.assertEqual(load_template(d).mode, "major")

    def test_vocabularies_are_not_widened(self):
        # The minor template uses exactly the frozen v1 vocabularies.
        from harmony.functional_network_template import (
            NODE_KINDS, ALL_RELATIONS, GENERATION_RULES,
        )
        tpl = functional_degree_network_minor_v2()
        self.assertEqual(sorted(tpl.kinds()), sorted(NODE_KINDS))
        for rel in tpl.relations():
            self.assertIn(rel, ALL_RELATIONS)
        for rule in tpl.generation_rules:
            self.assertIn(rule, GENERATION_RULES)


# ---------------------------------------------------------------------------
# 2. Minor graph generation (ids, the real minor V, edges)
# ---------------------------------------------------------------------------

class TestMinorGraph(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.net = _minor_net()

    def _has_edge(self, source, relation, target):
        return any(e.source == source and e.relation == relation
                   and e.target == target for e in self.net.edges)

    def test_node_counts_mirror_the_major_journey(self):
        kinds = {}
        for n in self.net.nodes:
            kinds[n.kind] = kinds.get(n.kind, 0) + 1
        self.assertEqual(kinds, {"degree_triad": 28, "function_group": 12,
                                 "key_hub": 4})

    def test_minor_ids_use_m_suffixed_tokens(self):
        self.assertIsNotNone(self.net.node("fnet:deg:Am:0"))
        self.assertIsNotNone(self.net.node("fnet:deg:Am:4"))
        self.assertIsNotNone(self.net.node("fnet:fn:Am:dominant"))
        self.assertIsNotNone(self.net.node("fnet:key:Am"))
        self.assertEqual(degree_node_id("A", 4, "minor"), "fnet:deg:Am:4")
        self.assertEqual(function_node_id("A", "dominant", "minor"),
                         "fnet:fn:Am:dominant")
        self.assertEqual(key_node_id("A", "minor"), "fnet:key:Am")

    def test_minor_ids_are_disjoint_from_major_ids(self):
        major_ids = {n.id for n in build_functional_network().nodes}
        minor_ids = {n.id for n in self.net.nodes}
        self.assertEqual(major_ids & minor_ids, set())
        # the un-suffixed A-major-style id must NOT exist here
        self.assertIsNone(self.net.node("fnet:deg:A:0"))

    def test_default_id_helpers_stay_major(self):
        # Existing call sites pass no mode; v1 ids must be byte-identical.
        self.assertEqual(degree_node_id("C", 4), "fnet:deg:C:4")
        self.assertEqual(function_node_id("C", "tonic"), "fnet:fn:C:tonic")
        self.assertEqual(key_node_id("C"), "fnet:key:C")

    def test_the_real_minor_v(self):
        # The whole point of G2c: V in A minor is E MAJOR (harmonic minor).
        v = self.net.node("fnet:deg:Am:4")
        self.assertEqual(v.label, "V")
        self.assertEqual(v.quality, "major")
        self.assertEqual(v.data["pitches"], ["E", "G#", "B"])
        vii = self.net.node("fnet:deg:Am:6")
        self.assertEqual(vii.label, "vii°")
        self.assertEqual(vii.quality, "diminished")
        self.assertEqual(vii.data["pitches"], ["G#", "B", "D"])

    def test_seven_harmonic_minor_degrees(self):
        romans = [self.net.node(degree_node_id("A", i, "minor")).label
                  for i in range(7)]
        self.assertEqual(romans, ["i", "ii°", "III+", "iv", "V", "VI", "vii°"])

    def test_function_groups_mirror_major(self):
        # tonic = {i, III+, VI}, PD/S = {ii°, iv}, D = {V, vii°}.
        fn = self.net.node("fnet:fn:Am:tonic")
        self.assertEqual(fn.data["members"], ["i", "III+", "VI"])
        pd = self.net.node("fnet:fn:Am:predominant")
        self.assertEqual(pd.data["members"], ["ii°", "iv"])
        d = self.net.node("fnet:fn:Am:dominant")
        self.assertEqual(d.data["members"], ["V", "vii°"])

    def test_resolution_preparation_deceptive_edges(self):
        deg = lambda k, i: degree_node_id(k, i, "minor")  # noqa: E731
        for key in ("A", "E", "D", "B"):
            self.assertTrue(self._has_edge(deg(key, 4), "resolves_to",
                                           deg(key, 0)))
            self.assertTrue(self._has_edge(deg(key, 6), "resolves_to",
                                           deg(key, 0)))
            self.assertTrue(self._has_edge(deg(key, 1), "prepares",
                                           deg(key, 4)))
            self.assertTrue(self._has_edge(deg(key, 3), "prepares",
                                           deg(key, 4)))
            self.assertTrue(self._has_edge(deg(key, 4), "deceptive_to",
                                           deg(key, 5)))

    def test_edge_counts_are_a_pinned_fingerprint(self):
        # Harmonic minor's altered chords are panel-unique, so only 4 triads
        # recur across panels (Am, Dm, Em, C#°) vs the major journey's 16.
        self.assertEqual(self.net.counts()["edgesByRelation"], {
            "function_member": 28,
            "resolves_to": 8,
            "prepares": 8,
            "tonic_substitute": 8,
            "deceptive_to": 4,
            "in_key": 28,
            "fifth_relation": 3,
            "shared_triad": 4,
        })
        self.assertEqual(len(self.net.edges), 91)

    def test_fifth_chain_runs_d_a_e_b(self):
        key = lambda k: key_node_id(k, "minor")  # noqa: E731
        self.assertTrue(self._has_edge(key("D"), "fifth_relation", key("A")))
        self.assertTrue(self._has_edge(key("A"), "fifth_relation", key("E")))
        self.assertTrue(self._has_edge(key("E"), "fifth_relation", key("B")))

    def test_panels_ordered_by_minor_fifths(self):
        xs = {k: self.net.node(key_node_id(k, "minor")).x
              for k in ("D", "A", "E", "B")}
        self.assertLess(xs["D"], xs["A"])
        self.assertLess(xs["A"], xs["E"])
        self.assertLess(xs["E"], xs["B"])

    def test_shared_triads_are_pitch_class_identical(self):
        shared = [e for e in self.net.edges if e.relation == "shared_triad"]
        self.assertEqual(len(shared), 4)
        for e in shared:
            a, b = self.net.node(e.source), self.net.node(e.target)
            self.assertEqual(
                frozenset(note_pc(p) for p in a.data["pitches"]),
                frozenset(note_pc(p) for p in b.data["pitches"]), e.id)

    def test_shared_triad_canonical_examples(self):
        # A minor's tonic Am is E minor's iv; D minor's tonic Dm is A's iv.
        deg = lambda k, i: degree_node_id(k, i, "minor")  # noqa: E731

        def linked(a, b):
            return (self._has_edge(a, "shared_triad", b)
                    or self._has_edge(b, "shared_triad", a))
        self.assertTrue(linked(deg("A", 0), deg("E", 3)))
        self.assertTrue(linked(deg("D", 0), deg("A", 3)))

    def test_deterministic_build(self):
        a = _minor_net().to_payload()
        b = _minor_net().to_payload()
        self.assertEqual(a["nodes"], b["nodes"])
        self.assertEqual(a["edges"], b["edges"])

    def test_major_fingerprint_is_untouched(self):
        major = build_functional_network()
        self.assertEqual(len(major.nodes), 44)
        self.assertEqual(len(major.edges), 103)
        self.assertEqual(
            major.counts()["edgesByRelation"]["shared_triad"], 16)


# ---------------------------------------------------------------------------
# 3. Ref honesty (the G2a natural-minor-twin precedent)
# ---------------------------------------------------------------------------

class TestMinorRefHonesty(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.net = _minor_net()

    def test_all_atlas_refs_resolve(self):
        from harmony.atlas import build_atlas
        atlas = build_atlas()
        for n in self.net.nodes:
            self.assertTrue(n.atlas_refs,
                            f"{n.id} should carry at least one atlas ref")
            for ref in n.atlas_refs:
                self.assertIsNotNone(atlas.node(ref),
                                     f"{n.id} -> dangling atlas ref {ref}")

    def test_natural_minor_twins_claim_chord_nodes(self):
        # i / ii° / iv / VI equal their natural-minor twins exactly.
        i = self.net.node("fnet:deg:Am:0")
        self.assertIn("triad:A:natural_minor:0", i.atlas_refs)
        self.assertIn("degree:natural_minor:i", i.atlas_refs)
        self.assertIn("function:natural_minor:tonic", i.atlas_refs)
        iv = self.net.node("fnet:deg:Am:3")
        self.assertIn("triad:A:natural_minor:3", iv.atlas_refs)

    def test_raised_chords_claim_only_their_quality(self):
        # III+ / V / vii° match no natural-minor chord: quality class only.
        for idx, quality in ((2, "augmented"), (4, "major"),
                             (6, "diminished")):
            n = self.net.node(degree_node_id("A", idx, "minor"))
            self.assertIn(f"quality:{quality}", n.atlas_refs)
            for ref in n.atlas_refs:
                self.assertFalse(
                    ref.startswith(("triad:", "degree:")),
                    f"{n.id} dishonestly claims {ref}")

    def test_key_context_is_natural_minor(self):
        hub = self.net.node("fnet:key:Am")
        self.assertIn("scale:A:natural_minor", hub.atlas_refs)
        for n in self.net.nodes:
            self.assertEqual(n.circle_refs,
                             [f"key:{n.data['panelKey']}:natural_minor"])

    def test_function_group_refs(self):
        fn = self.net.node("fnet:fn:Am:dominant")
        self.assertIn("function:natural_minor:dominant", fn.atlas_refs)


# ---------------------------------------------------------------------------
# 4. Launch status (everything launchable, harmonic_minor, cap holds)
# ---------------------------------------------------------------------------

class TestMinorLaunchStatus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.net = _minor_net()

    def test_every_node_is_launchable_and_none_reserved(self):
        counts = self.net.counts()
        self.assertEqual(counts["launchableDrills"], 44)
        self.assertEqual(counts["reservedDrills"], 0)

    def test_every_spec_is_harmonic_minor_and_capped(self):
        for item in self.net.launchables():
            spec = HarmonyExerciseSpec.from_dict(item["spec"])
            self.assertEqual(spec.mode, "harmonic_minor",
                             f"{item['nodeId']}: {item['exerciseId']}")
            self.assertLessEqual(len(compile_exercise(spec)),
                                 MAX_CHORDS_PER_SPEC,
                                 f"{item['nodeId']}: {item['exerciseId']}")

    def test_degree_node_drills_end_on_i(self):
        v = self.net.node("fnet:deg:Am:4")
        spec = HarmonyExerciseSpec.from_dict(v.trainer_specs[0]["spec"])
        self.assertEqual(spec.drill, "function")
        self.assertEqual(spec.pattern, ["V", "i"])
        self.assertEqual(spec.keys, ["A"])

    def test_tonic_and_hub_drill_the_full_harmonic_minor_key(self):
        for nid in ("fnet:deg:Am:0", "fnet:key:Am"):
            spec = HarmonyExerciseSpec.from_dict(
                self.net.node(nid).trainer_specs[0]["spec"])
            self.assertEqual(spec.drill, "full_key")
            self.assertEqual(spec.mode, "harmonic_minor")
            romans = [c.triad.roman for c in compile_exercise(spec).chords]
            self.assertEqual(romans,
                             ["i", "ii°", "III+", "iv", "V", "VI", "vii°"])

    def test_function_group_drills_end_home(self):
        for key in ("A", "E", "D", "B"):
            for group in FUNCTION_GROUPS:
                n = self.net.node(function_node_id(key, group, "minor"))
                spec = HarmonyExerciseSpec.from_dict(
                    n.trainer_specs[0]["spec"])
                self.assertEqual(spec.drill, "function")
                self.assertEqual(spec.pattern[-1], "i")


# ---------------------------------------------------------------------------
# 5. Payload shape (progressive; template mode exported for the JS sync)
# ---------------------------------------------------------------------------

class TestMinorPayload(unittest.TestCase):
    def test_payload_is_progressive_and_carries_the_mode(self):
        payload = build_functional_network_payload(MINOR_TEMPLATE_ID)
        self.assertEqual(payload["schema"], "harmony-network/v1")
        self.assertIs(payload["progressive"], True)
        self.assertEqual(payload["template"]["template_id"],
                         MINOR_TEMPLATE_ID)
        self.assertEqual(payload["template"]["mode"], "minor")
        self.assertEqual(len(payload["nodes"]), 44)

    def test_major_payload_carries_major_mode(self):
        payload = build_functional_network_payload()
        self.assertEqual(payload["template"]["mode"], "major")


# ---------------------------------------------------------------------------
# 6. The minor journey stages
# ---------------------------------------------------------------------------

class TestMinorJourney(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.net = _minor_net()
        cls.stages = journey_stages(cls.net)

    def test_seven_stages_with_minor_suffixed_ids(self):
        self.assertEqual([s.stage_id for s in self.stages], [
            "meet_the_scale_minor", "three_jobs_minor", "tension_home_minor",
            "approach_chain_minor", "substitutes_minor",
            "same_triad_new_key_minor", "free_exploration_minor",
        ])

    def test_stage_ids_are_disjoint_from_the_major_journey(self):
        major = journey_stages(build_functional_network())
        self.assertEqual({s.stage_id for s in self.stages}
                         & {s.stage_id for s in major}, set())
        # drill exercise ids must not collide either (shared progress store)
        minor_drills = {d.exercise_id for s in self.stages for d in s.drills}
        major_drills = {d.exercise_id for s in major for d in s.drills}
        self.assertEqual(minor_drills & major_drills, set())

    def test_stage_one_shows_exactly_the_home_minor_degrees(self):
        s1 = self.stages[0]
        self.assertEqual(sorted(s1.visible_node_ids),
                         sorted(degree_node_id("A", i, "minor")
                                for i in range(7)))
        self.assertEqual(len(s1.drills), 1)
        self.assertEqual(s1.drills[0].drill, "full_key")
        self.assertEqual(s1.drills[0].mode, "harmonic_minor")

    def test_every_drill_is_harmonic_minor_within_cap(self):
        for s in self.stages:
            for d in s.drills:
                self.assertEqual(d.mode, "harmonic_minor",
                                 f"{s.stage_id}: {d.exercise_id}")
                n = len(compile_exercise(d))
                self.assertLessEqual(n, MAX_CHORDS_PER_SPEC,
                                     f"{s.stage_id}: {d.exercise_id}")
                self.assertGreater(n, 0)

    def test_stage_drill_inventory_mirrors_major(self):
        self.assertEqual([len(s.drills) for s in self.stages],
                         [1, 1, 2, 1, 1, 2, 0])
        s6 = self.stages[5]
        self.assertEqual(s6.drills[0].drill, "horizontal_degree")
        self.assertEqual(s6.drills[0].mode, "harmonic_minor")
        self.assertEqual(s6.drills[0].degree, "V")
        self.assertEqual(s6.drills[0].keys, ["A", "E", "D", "B"])
        self.assertEqual(s6.drills[1].keys, ["E"])

    def test_resolution_stage_uses_the_real_minor_v(self):
        s3 = self.stages[2]
        self.assertEqual(s3.drills[0].pattern, ["V", "i"])
        self.assertEqual(s3.drills[1].pattern, ["vii°", "i"])
        self.assertEqual(s3.unlock, "finish_all")

    def test_predominant_patterns_use_minor_romans(self):
        self.assertEqual(self.stages[3].drills[0].pattern, ["ii°", "V", "i"])
        self.assertEqual(self.stages[4].drills[0].pattern,
                         ["VI", "ii°", "V", "i"])

    def test_reveal_grows_monotonically(self):
        prev = None
        for s in self.stages:
            if s.visible_node_ids is None:
                continue
            cur = set(s.visible_node_ids)
            if prev is not None:
                self.assertTrue(prev <= cur,
                                f"{s.stage_id} hides previously shown nodes")
            prev = cur

    def test_last_stage_drops_the_whitelist(self):
        self.assertIsNone(self.stages[-1].visible_node_ids)
        self.assertEqual(self.stages[-1].drills, [])

    def test_explanations_are_minor_specific(self):
        s1 = self.stages[0]
        self.assertIn("minor", s1.explanation.lower())
        # the tension stage tells the harmonic-minor story
        self.assertIn("harmonic minor", self.stages[2].explanation.lower())


# ---------------------------------------------------------------------------
# 7. Drill -> minor node mapping
# ---------------------------------------------------------------------------

class TestMinorDrillNodeIds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stages = journey_stages(_minor_net())

    def test_v_i_maps_to_minor_ids(self):
        ids = drill_node_ids(self.stages[2].drills[0])      # V–i in A minor
        self.assertEqual(ids, ["fnet:deg:Am:4", "fnet:deg:Am:0"])

    def test_full_key_covers_all_seven_minor_nodes(self):
        ids = drill_node_ids(self.stages[0].drills[0])
        self.assertEqual(ids, [degree_node_id("A", i, "minor")
                               for i in range(7)])

    def test_horizontal_v_spans_the_minor_journey_keys(self):
        ids = drill_node_ids(self.stages[5].drills[0])
        self.assertEqual(ids, [degree_node_id(k, 4, "minor")
                               for k in ("A", "E", "D", "B")])

    def test_major_drills_still_map_to_major_ids(self):
        major_stages = journey_stages(build_functional_network())
        ids = drill_node_ids(major_stages[2].drills[0])     # V–I in C
        self.assertEqual(ids, ["fnet:deg:C:4", "fnet:deg:C:0"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
