"""Tests for the Functional Degree Network (template + builder).

The Functional Degree Network is the practice-first sibling of the Harmonic
Network: every diatonic degree of a few major journey keys is a real graph
node, grouped by harmonic function, with cross-panel shared-triad identity
edges.  These tests enforce its contract:

  * template validation -- required fields, closed vocabularies, panel-layout
    invariants (7 degree offsets, one offset per function group, unique keys);
  * graph generation -- 28 degree + 12 function-group + 4 key-hub nodes; the
    rule-generated relationships (V->I, vii°->I, ii->V, IV->V, vi<->I,
    iii<->I, V->vi, fifth chain, in-key overlay);
  * shared_triad honesty -- every cross-panel edge joins two triads with
    IDENTICAL pitch-class sets (C:I ≡ G:IV ≡ F:V ...);
  * Atlas integration -- every node ref resolves to a real Atlas node;
  * launch status -- EVERY node is launchable (no reserved drills anywhere in
    this graph) and every spec respects the readability cap;
  * mediant honesty -- iii is grouped tonic but keeps its engine label and an
    explanation stating the ambiguity;
  * determinism + payload shape (progressive flag; v1 network untouched).

Run from the project root::

    .venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -t .
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from theory.diatonic_harmony import note_pc  # noqa: E402
from harmony.exercise_spec import (  # noqa: E402
    HarmonyExerciseSpec, compile_exercise, MAX_CHORDS_PER_SPEC,
)
from harmony.network_template import NodeClass, EdgeClass  # noqa: E402
from harmony.functional_network_template import (  # noqa: E402
    FunctionalNetworkTemplate, PanelLayoutRule,
    functional_degree_network_v1, get_template, load_template,
    NODE_KINDS, IMPLEMENTED_RELATIONS, RESERVED_RELATIONS, ALL_RELATIONS,
    GENERATION_RULES, FUNCTION_GROUPS,
)
from harmony.functional_network import (  # noqa: E402
    build_functional_network, build_functional_network_payload,
    functional_payload, degree_node_id, function_node_id, key_node_id,
    ENGINE_FUNCTION_TO_GROUP,
)


def _valid_template() -> FunctionalNetworkTemplate:
    return functional_degree_network_v1()


# ---------------------------------------------------------------------------
# 1. Template validation
# ---------------------------------------------------------------------------

class TestTemplateValidation(unittest.TestCase):
    def test_default_template_is_valid(self):
        tpl = get_template()
        tpl.validate()  # must not raise
        self.assertEqual(tpl.template_id, "functional_degree_network_v1")
        self.assertEqual(tpl.journey_keys, ["C", "G", "D", "F"])

    def test_required_fields_present(self):
        tpl = _valid_template()
        for field in ("template_id", "title", "description"):
            self.assertTrue(getattr(tpl, field))
        self.assertTrue(tpl.node_classes)
        self.assertTrue(tpl.edge_classes)
        self.assertTrue(tpl.layout_rules)

    def test_empty_template_id_fails(self):
        tpl = _valid_template()
        tpl.template_id = ""
        with self.assertRaises(ValueError):
            tpl.validate()

    def test_unknown_node_class_fails(self):
        tpl = _valid_template()
        tpl.node_classes.append(
            NodeClass("borrowed_chord", "Bogus", "emerald", "#000"))
        tpl.layout_rules.append(PanelLayoutRule("borrowed_chord"))
        with self.assertRaises(ValueError):
            tpl.validate()

    def test_unknown_edge_relation_fails_cleanly(self):
        tpl = _valid_template()
        tpl.edge_classes.append(EdgeClass("teleports_to", "Bogus"))
        with self.assertRaises(ValueError) as ctx:
            tpl.validate()
        self.assertIn("teleports_to", str(ctx.exception))

    def test_v1_vocabulary_is_not_widened(self):
        # The functional-network module must not inject ITS kinds/relations into the harmonic
        # network vocabulary (parallel module, not extension). NB: the harmonic network's own
        # bidirectional-mapping work independently added a `prepares` relation of its own, so
        # that name is no longer exclusive to this module and is not asserted here.
        from harmony import network_template as v1
        for kind in NODE_KINDS:
            self.assertNotIn(kind, v1.NODE_KINDS)
        for rel in ("function_member", "tonic_substitute",
                    "deceptive_to", "shared_triad", "in_key"):
            self.assertNotIn(rel, v1.ALL_RELATIONS)

    def test_unknown_generation_rule_fails(self):
        tpl = _valid_template()
        tpl.generation_rules.append("summon_demon")
        with self.assertRaises(ValueError):
            tpl.validate()

    def test_reserved_relation_cannot_be_implemented(self):
        tpl = _valid_template()
        tpl.edge_classes.append(
            EdgeClass("modulation_path_to", "Modulation", implemented=True))
        with self.assertRaises(ValueError):
            tpl.validate()

    def test_layout_rule_requires_matching_node_class(self):
        tpl = _valid_template()
        tpl.layout_rules.append(PanelLayoutRule("degree_triad"))  # duplicate
        with self.assertRaises(ValueError):
            tpl.validate()
        tpl2 = _valid_template()
        tpl2.node_classes = [nc for nc in tpl2.node_classes
                             if nc.kind != "key_hub"]
        with self.assertRaises(ValueError):
            tpl2.validate()

    def test_degree_offsets_must_cover_seven_degrees(self):
        tpl = _valid_template()
        tpl.degree_offsets = tpl.degree_offsets[:5]
        with self.assertRaises(ValueError):
            tpl.validate()

    def test_function_offsets_must_match_function_groups(self):
        tpl = _valid_template()
        del tpl.function_offsets["dominant"]
        with self.assertRaises(ValueError):
            tpl.validate()
        tpl2 = _valid_template()
        tpl2.function_offsets["mediant"] = [0.0, 0.0]
        with self.assertRaises(ValueError):
            tpl2.validate()

    def test_duplicate_journey_keys_fail(self):
        tpl = _valid_template()
        tpl.journey_keys = ["C", "G", "C"]
        with self.assertRaises(ValueError):
            tpl.validate()

    def test_empty_journey_keys_fail(self):
        tpl = _valid_template()
        tpl.journey_keys = []
        with self.assertRaises(ValueError):
            tpl.validate()

    def test_vocabulary_constants_are_disjoint(self):
        self.assertEqual(set(IMPLEMENTED_RELATIONS) & set(RESERVED_RELATIONS),
                         set())
        self.assertEqual(set(ALL_RELATIONS),
                         set(IMPLEMENTED_RELATIONS) | set(RESERVED_RELATIONS))

    def test_required_relations_all_declared(self):
        tpl = _valid_template()
        declared = set(tpl.relations())
        for r in IMPLEMENTED_RELATIONS:
            self.assertIn(r, declared, f"template must declare {r}")
        for r in RESERVED_RELATIONS:
            self.assertIn(r, declared, f"template must reserve {r}")

    def test_every_generation_rule_is_used(self):
        tpl = _valid_template()
        self.assertEqual(list(tpl.generation_rules), list(GENERATION_RULES))

    def test_round_trip_to_from_dict(self):
        tpl = _valid_template()
        again = load_template(tpl.to_dict())
        self.assertEqual(again.template_id, tpl.template_id)
        self.assertEqual(again.relations(), tpl.relations())
        self.assertEqual(again.journey_keys, tpl.journey_keys)
        self.assertEqual(again.degree_offsets, tpl.degree_offsets)
        self.assertEqual(again.function_offsets, tpl.function_offsets)

    def test_launch_rules_have_no_reserved_kinds(self):
        tpl = _valid_template()
        self.assertEqual(tpl.launch_rules["reserved_kinds"], [])
        self.assertEqual(set(tpl.launch_rules["launchable_kinds"]),
                         set(NODE_KINDS))


# ---------------------------------------------------------------------------
# 2. Graph generation
# ---------------------------------------------------------------------------

class TestGraphGeneration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.net = build_functional_network()
        cls.payload = cls.net.to_payload()

    def _kind(self, kind):
        return [n for n in self.net.nodes if n.kind == kind]

    def _has_edge(self, source, relation, target):
        return any(e.source == source and e.relation == relation
                   and e.target == target for e in self.net.edges)

    def test_node_counts(self):
        self.assertEqual(len(self._kind("degree_triad")), 28)
        self.assertEqual(len(self._kind("function_group")), 12)
        self.assertEqual(len(self._kind("key_hub")), 4)
        self.assertEqual(len(self.net.nodes), 44)

    def test_edge_counts_are_a_pinned_fingerprint(self):
        self.assertEqual(len(self.net.edges), 103)
        self.assertEqual(self.net.counts()["edgesByRelation"], {
            "function_member": 28,
            "resolves_to": 8,
            "prepares": 8,
            "tonic_substitute": 8,
            "deceptive_to": 4,
            "in_key": 28,
            "fifth_relation": 3,
            "shared_triad": 16,
        })

    def test_resolution_edges(self):
        for key in ("C", "G", "D", "F"):
            self.assertTrue(self._has_edge(degree_node_id(key, 4),
                                           "resolves_to",
                                           degree_node_id(key, 0)))
            self.assertTrue(self._has_edge(degree_node_id(key, 6),
                                           "resolves_to",
                                           degree_node_id(key, 0)))

    def test_preparation_edges(self):
        self.assertTrue(self._has_edge(degree_node_id("C", 1), "prepares",
                                       degree_node_id("C", 4)))
        self.assertTrue(self._has_edge(degree_node_id("C", 3), "prepares",
                                       degree_node_id("C", 4)))

    def test_substitute_and_deceptive_edges(self):
        self.assertTrue(self._has_edge(degree_node_id("C", 5),
                                       "tonic_substitute",
                                       degree_node_id("C", 0)))
        self.assertTrue(self._has_edge(degree_node_id("C", 2),
                                       "tonic_substitute",
                                       degree_node_id("C", 0)))
        self.assertTrue(self._has_edge(degree_node_id("C", 4), "deceptive_to",
                                       degree_node_id("C", 5)))

    def test_function_member_edges(self):
        # I/vi/iii -> T; ii/IV -> PD/S; V/vii° -> D (mediant grouped tonic).
        expect = {0: "tonic", 1: "predominant", 2: "tonic", 3: "predominant",
                  4: "dominant", 5: "tonic", 6: "dominant"}
        for i, group in expect.items():
            self.assertTrue(
                self._has_edge(degree_node_id("C", i), "function_member",
                               function_node_id("C", group)),
                f"C degree {i} should be a member of {group}")

    def test_fifth_relation_only_links_true_fifth_neighbours(self):
        # An honest edge: journey keys that are NOT one circle-step apart get
        # no fifth_relation edge (C and D are a major second apart).
        sparse = build_functional_network(keys=["C", "D"])
        self.assertEqual(
            [e for e in sparse.edges if e.relation == "fifth_relation"], [])
        dense = build_functional_network(keys=["C", "G"])
        fifths = [e for e in dense.edges if e.relation == "fifth_relation"]
        self.assertEqual(len(fifths), 1)
        self.assertEqual(fifths[0].source, key_node_id("C"))
        self.assertEqual(fifths[0].target, key_node_id("G"))

    def test_journey_keys_are_canonicalised(self):
        # "C major" and "C" must yield the same node ids (drill_node_ids and
        # the JS exact-id sync reconstruct ids from parse_key tonics).
        net = build_functional_network(keys=["C major", "G"])
        self.assertIsNotNone(net.node("fnet:deg:C:0"))
        self.assertIsNotNone(net.node("fnet:key:C"))
        hub = net.node(key_node_id("C"))
        self.assertEqual(hub.label, "C")
        self.assertNotIn("major major", hub.explanation)

    def test_fifth_chain_is_open_and_ordered(self):
        # F -> C -> G -> D (journey keys sorted by fifths; no wrap-around).
        self.assertTrue(self._has_edge(key_node_id("F"), "fifth_relation",
                                       key_node_id("C")))
        self.assertTrue(self._has_edge(key_node_id("C"), "fifth_relation",
                                       key_node_id("G")))
        self.assertTrue(self._has_edge(key_node_id("G"), "fifth_relation",
                                       key_node_id("D")))
        self.assertFalse(self._has_edge(key_node_id("D"), "fifth_relation",
                                        key_node_id("F")))

    def test_in_key_edges(self):
        for i in range(7):
            self.assertTrue(self._has_edge(degree_node_id("C", i), "in_key",
                                           key_node_id("C")))

    def test_shared_triad_edges_are_pitch_class_identical(self):
        # THE honesty invariant: every shared_triad edge joins two triads with
        # exactly the same pitch-class set.
        shared = [e for e in self.net.edges if e.relation == "shared_triad"]
        self.assertEqual(len(shared), 16)
        for e in shared:
            a = self.net.node(e.source)
            b = self.net.node(e.target)
            pcs_a = frozenset(note_pc(p) for p in a.data["pitches"])
            pcs_b = frozenset(note_pc(p) for p in b.data["pitches"])
            self.assertEqual(pcs_a, pcs_b, f"{e.id} joins different triads")
            self.assertNotEqual(a.data["panelKey"], b.data["panelKey"],
                                f"{e.id} joins nodes of the same panel")

    def test_shared_triad_canonical_examples(self):
        # C:I ≡ G:IV ≡ F:V (the C major triad's three jobs).
        def linked(a, b):
            return (self._has_edge(a, "shared_triad", b)
                    or self._has_edge(b, "shared_triad", a))
        self.assertTrue(linked(degree_node_id("C", 0), degree_node_id("G", 3)))
        self.assertTrue(linked(degree_node_id("C", 0), degree_node_id("F", 4)))
        self.assertTrue(linked(degree_node_id("G", 3), degree_node_id("F", 4)))
        # G triad: I of G ≡ V of C ≡ IV of D.
        self.assertTrue(linked(degree_node_id("G", 0), degree_node_id("C", 4)))
        self.assertTrue(linked(degree_node_id("G", 0), degree_node_id("D", 3)))

    def test_every_edge_endpoint_exists(self):
        ids = {n.id for n in self.net.nodes}
        for e in self.net.edges:
            self.assertIn(e.source, ids, e)
            self.assertIn(e.target, ids, e)
            self.assertIn(e.relation, IMPLEMENTED_RELATIONS, e)

    def test_no_reserved_relation_generates_edges(self):
        used = {e.relation for e in self.net.edges}
        self.assertEqual(used & set(RESERVED_RELATIONS), set())

    def test_deterministic_build(self):
        a = build_functional_network().to_payload()
        b = build_functional_network().to_payload()
        self.assertEqual(a["nodes"], b["nodes"])
        self.assertEqual(a["edges"], b["edges"])

    def test_panels_ordered_by_fifths(self):
        # Panels run left-to-right by key-signature fifths: F, C, G, D.
        xs = {k: self.net.node(key_node_id(k)).x for k in ("F", "C", "G", "D")}
        self.assertLess(xs["F"], xs["C"])
        self.assertLess(xs["C"], xs["G"])
        self.assertLess(xs["G"], xs["D"])

    def test_degrees_share_their_panels_x_band(self):
        # Every C-panel node stays within half a panel width of the C hub.
        tpl = self.net.template
        hub_x = self.net.node(key_node_id("C")).x
        for i in range(7):
            n = self.net.node(degree_node_id("C", i))
            self.assertLessEqual(abs(n.x - hub_x), tpl.panel_width / 2.0)

    def test_engine_function_mapping_is_total(self):
        # Every engine label observed on a degree node maps onto a group.
        for n in self.net.nodes:
            if n.kind != "degree_triad":
                continue
            self.assertIn(n.data["functionLabel"], ENGINE_FUNCTION_TO_GROUP)
            self.assertIn(n.data["functionGroup"], FUNCTION_GROUPS)


# ---------------------------------------------------------------------------
# 3. Mediant honesty
# ---------------------------------------------------------------------------

class TestMediantHonesty(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.net = build_functional_network()

    def test_iii_keeps_engine_label_but_groups_tonic(self):
        iii = self.net.node(degree_node_id("C", 2))
        self.assertEqual(iii.data["functionLabel"], "mediant")
        self.assertEqual(iii.data["functionGroup"], "tonic")

    def test_iii_explanation_states_the_ambiguity(self):
        iii = self.net.node(degree_node_id("C", 2))
        self.assertIn("ambiguous", iii.explanation)
        self.assertIn("two tones", iii.explanation)

    def test_tonic_group_mentions_the_grouping_choice(self):
        fn = self.net.node(function_node_id("C", "tonic"))
        self.assertIn("iii", fn.explanation)
        self.assertIn("substitute", fn.explanation)
        self.assertEqual(fn.data["members"], ["I", "iii", "vi"])


# ---------------------------------------------------------------------------
# 4. Atlas integration
# ---------------------------------------------------------------------------

class TestAtlasIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.net = build_functional_network()

    def test_all_atlas_refs_resolve_to_real_nodes(self):
        from harmony.atlas import build_atlas
        atlas = build_atlas()
        for n in self.net.nodes:
            self.assertTrue(n.atlas_refs,
                            f"{n.id} should carry at least one atlas ref")
            for ref in n.atlas_refs:
                self.assertIsNotNone(atlas.node(ref),
                                     f"{n.id} -> dangling atlas ref {ref}")

    def test_c_tonic_degree_refs(self):
        c1 = self.net.node(degree_node_id("C", 0))
        self.assertIn("triad:C:major:0", c1.atlas_refs)
        self.assertIn("degree:major:I", c1.atlas_refs)
        self.assertIn("function:major:tonic", c1.atlas_refs)

    def test_dominant_function_group_refs(self):
        fn = self.net.node(function_node_id("C", "dominant"))
        self.assertIn("function:major:dominant", fn.atlas_refs)

    def test_key_hub_scale_ref(self):
        hub = self.net.node(key_node_id("C"))
        self.assertIn("scale:C:major", hub.atlas_refs)


# ---------------------------------------------------------------------------
# 5. Launch status (EVERYTHING is launchable; the cap holds)
# ---------------------------------------------------------------------------

class TestLaunchStatus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.net = build_functional_network()

    def test_every_node_is_launchable_and_none_reserved(self):
        counts = self.net.counts()
        self.assertEqual(counts["launchableDrills"], 44)
        self.assertEqual(counts["reservedDrills"], 0)
        for n in self.net.nodes:
            self.assertTrue(n.trainer_specs, f"{n.id} has no drill")
            for t in n.trainer_specs:
                self.assertEqual(t["status"], "launchable", n.id)
                self.assertIsNotNone(t["spec"], n.id)

    def test_every_launchable_spec_respects_cap_and_round_trips(self):
        for item in self.net.launchables():
            spec = HarmonyExerciseSpec.from_dict(item["spec"])  # must not raise
            self.assertLessEqual(len(compile_exercise(spec)),
                                 MAX_CHORDS_PER_SPEC,
                                 f"{item['nodeId']}: {item['exerciseId']}")
            self.assertNotEqual(spec.drill, "seventh_chord")

    def test_degree_node_drills(self):
        # I launches the full key; every other degree launches roman–I.
        c_i = self.net.node(degree_node_id("C", 0))
        spec = HarmonyExerciseSpec.from_dict(c_i.trainer_specs[0]["spec"])
        self.assertEqual(spec.drill, "full_key")
        c_v = self.net.node(degree_node_id("C", 4))
        spec_v = HarmonyExerciseSpec.from_dict(c_v.trainer_specs[0]["spec"])
        self.assertEqual(spec_v.drill, "function")
        self.assertEqual(spec_v.pattern, ["V", "I"])
        self.assertEqual(spec_v.keys, ["C"])
        c_vii = self.net.node(degree_node_id("C", 6))
        spec_vii = HarmonyExerciseSpec.from_dict(c_vii.trainer_specs[0]["spec"])
        self.assertEqual(spec_vii.pattern, ["vii°", "I"])

    def test_function_group_drills_end_home(self):
        for key in ("C", "G", "D", "F"):
            for group in FUNCTION_GROUPS:
                n = self.net.node(function_node_id(key, group))
                spec = HarmonyExerciseSpec.from_dict(n.trainer_specs[0]["spec"])
                self.assertEqual(spec.drill, "function")
                self.assertEqual(spec.keys, [key])
                self.assertEqual(spec.pattern[-1], "I")

    def test_key_hub_drill_is_full_key(self):
        hub = self.net.node(key_node_id("G"))
        spec = HarmonyExerciseSpec.from_dict(hub.trainer_specs[0]["spec"])
        self.assertEqual(spec.drill, "full_key")
        self.assertEqual(spec.key, "G major")


# ---------------------------------------------------------------------------
# 6. Payload shape + backward compatibility
# ---------------------------------------------------------------------------

class TestPayloadShape(unittest.TestCase):
    def test_payload_schema_and_progressive_flag(self):
        payload = build_functional_network_payload()
        self.assertEqual(payload["schema"], "harmony-network/v1")
        self.assertIs(payload["progressive"], True)
        for key in ("template", "nodes", "edges", "legend", "launchables",
                    "counts"):
            self.assertIn(key, payload)
        self.assertEqual(payload["template"]["template_id"],
                         "functional_degree_network_v1")

    def test_plain_to_payload_is_not_flagged(self):
        # functional_payload() adds the flag; the raw container stays generic.
        net = build_functional_network()
        self.assertNotIn("progressive", net.to_payload())
        self.assertIs(functional_payload(net)["progressive"], True)

    def test_legend_visual_classes(self):
        payload = build_functional_network_payload()
        vis = {nc["visualClass"] for nc in payload["legend"]["nodeClasses"]}
        self.assertEqual(vis, {"emerald", "violet", "amber"})

    def test_every_node_has_required_fields_and_sublabel(self):
        payload = build_functional_network_payload()
        for n in payload["nodes"]:
            for field in ("id", "label", "kind", "pitchClass", "spelling",
                          "quality", "x", "y", "radius", "visualClass",
                          "explanation", "atlasRefs", "trainerSpecs", "data"):
                self.assertIn(field, n)
            self.assertTrue(n["data"].get("sublabel"), n["id"])
            self.assertTrue(n["id"].startswith("fnet:"), n["id"])

    def test_edge_visual_classes_reuse_the_existing_palette(self):
        # The renderer's colour/dash maps are keyed on these names; a new name
        # would silently render grey/solid.
        known = {"fifth", "relative", "dominant", "resolve", "leading",
                 "shared", "samepc", "function", "trainer", "atlas",
                 "reserved"}
        payload = build_functional_network_payload()
        for ec in payload["legend"]["edgeClasses"]:
            self.assertIn(ec["visualClass"], known, ec["relation"])

    def test_v1_network_is_untouched(self):
        from harmony.harmonic_network import build_network
        net = build_network()
        self.assertEqual(len(net.nodes), 48)
        self.assertEqual(len(net.edges), 240)

    def test_named_template_loads(self):
        payload = build_functional_network_payload(
            "functional_degree_network_v1")
        self.assertEqual(len(payload["nodes"]), 44)

    def test_unknown_template_rejected(self):
        with self.assertRaises(KeyError):
            build_functional_network_payload("bogus_template_v9")


if __name__ == "__main__":
    unittest.main(verbosity=2)
