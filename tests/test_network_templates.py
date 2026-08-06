"""Phase 4 tests for the core_triad_function_network_v1 template + builder refactor.

Covers template validation, node kinds / semantic levels, stable ids and counts, Atlas-ref
existence, deterministic builds, build-context (key/mode) parameterisation, the additive payload
keys (context / paths), and the exact-triad projection acceptance (plan section 14.1).
"""

import unittest

from harmony.harmonic_network import build_network, NetworkBuildContext
from harmony.network_template import (
    get_template,
    NODE_KINDS,
    IMPLEMENTED_RELATIONS,
    VISUAL_CLASSES,
    core_triad_function_network_v1,
)
from harmony.network_projection import project_harmony_exercise
from harmony.atlas import build_atlas, full_key_spec


CORE = "core_triad_function_network_v1"


class TestCoreTemplateSchema(unittest.TestCase):
    def test_registered_and_valid(self):
        tpl = get_template(CORE)
        tpl.validate()
        self.assertEqual(tpl.template_id, CORE)
        self.assertEqual(tpl.layout_strategy, "key_local")
        self.assertEqual(tpl.node_generation_rules,
                         ["core_key_center_node", "core_diatonic_triad_nodes",
                          "core_function_family_nodes"])

    def test_new_kinds_and_relations_registered(self):
        for kind in ("key_center", "diatonic_triad", "function_family"):
            self.assertIn(kind, NODE_KINDS)
        for rel in ("belongs_to_key", "member_of_function", "prepares"):
            self.assertIn(rel, IMPLEMENTED_RELATIONS)

    def test_node_class_semantic_metadata(self):
        tpl = core_triad_function_network_v1()
        levels = {nc.kind: nc.semantic_level for nc in tpl.node_classes}
        self.assertEqual(levels["key_center"], "key")
        self.assertEqual(levels["diatonic_triad"], "chord")
        self.assertEqual(levels["function_family"], "function")
        roles = {nc.kind: nc.entity_role for nc in tpl.node_classes}
        self.assertEqual(roles["key_center"], "anchor")
        self.assertEqual(roles["diatonic_triad"], "instance")
        for nc in tpl.node_classes:
            self.assertIn(nc.visual_class, VISUAL_CLASSES)

    def test_bad_semantic_level_rejected(self):
        tpl = core_triad_function_network_v1()
        tpl.node_classes[0].semantic_level = "wormhole"
        with self.assertRaises(ValueError):
            tpl.validate()


class TestCoreBuild(unittest.TestCase):
    def setUp(self):
        self.net = build_network(get_template(CORE))

    def test_node_inventory(self):
        self.assertEqual(self.net.counts()["nodesByKind"],
                         {"key_center": 1, "diatonic_triad": 7, "function_family": 3})
        self.assertEqual(len(self.net.nodes), 11)

    def test_stable_node_ids(self):
        ids = {n.id for n in self.net.nodes}
        self.assertIn("hn:key:C", ids)
        for deg in range(7):
            self.assertIn(f"hn:triad:C:major:{deg}", ids)
        for fam in ("tonic", "dominant", "predominant"):
            self.assertIn(f"hn:function:major:{fam}", ids)

    def test_key_node_is_not_a_chord(self):
        key = self.net.node("hn:key:C")
        self.assertEqual(key.semantic_level, "key")
        self.assertEqual(key.entity_role, "anchor")
        # the tonic CHORD is a separate node
        tonic_chord = self.net.node("hn:triad:C:major:0")
        self.assertEqual(tonic_chord.semantic_level, "chord")
        self.assertNotEqual(key.id, tonic_chord.id)

    def test_edge_fingerprint(self):
        self.assertEqual(self.net.counts()["edgesByRelation"], {
            "belongs_to_key": 7,
            "member_of_function": 7,
            "prepares": 2,
            "resolves_to": 4,
            "leading_tone_to": 1,
        })

    def test_no_duplicate_edges(self):
        seen = set()
        for e in self.net.edges:
            key = (e.source, e.target, e.relation)
            self.assertNotIn(key, seen)
            seen.add(key)

    def test_triad_canonical_refs_exist_in_atlas(self):
        atlas = build_atlas()
        for n in self.net.nodes_of_kind("diatonic_triad"):
            self.assertTrue(n.canonical_ref.startswith("triad:"))
            self.assertIsNotNone(atlas.node(n.canonical_ref),
                                 f"{n.canonical_ref} missing from atlas")

    def test_every_triad_is_launchable(self):
        for n in self.net.nodes_of_kind("diatonic_triad"):
            self.assertTrue(n.trainer_specs)
            self.assertEqual(n.trainer_specs[0]["status"], "launchable")

    def test_deterministic(self):
        a = build_network(get_template(CORE))
        b = build_network(get_template(CORE))
        self.assertEqual([n.id for n in a.nodes], [n.id for n in b.nodes])
        self.assertEqual([(e.source, e.target, e.relation) for e in a.edges],
                         [(e.source, e.target, e.relation) for e in b.edges])

    def test_payload_carries_context_and_paths(self):
        payload = self.net.to_payload()
        self.assertIn("context", payload)
        self.assertIn("paths", payload)
        self.assertEqual(payload["context"]["key"], "C")
        self.assertEqual(payload["context"]["mode"], "major")


class TestCoreContextParameterisation(unittest.TestCase):
    def test_a_minor_context(self):
        net = build_network(get_template(CORE),
                            context=NetworkBuildContext(key="A", mode="natural_minor"))
        ids = {n.id for n in net.nodes}
        self.assertIn("hn:key:A", ids)
        self.assertIn("hn:triad:A:natural_minor:0", ids)
        # minor function families use the minor mode id
        self.assertIn("hn:function:natural_minor:dominant", ids)
        atlas = build_atlas()
        for n in net.nodes_of_kind("diatonic_triad"):
            self.assertIsNotNone(atlas.node(n.canonical_ref))

    def test_context_reflected_in_payload(self):
        net = build_network(get_template(CORE),
                            context=NetworkBuildContext(key="G", mode="major"))
        self.assertEqual(net.to_payload()["context"]["key"], "G")


class TestCoreExactProjection(unittest.TestCase):
    """Plan section 14.1 acceptance: exact mapping for all seven triads."""

    def test_c_major_full_key_all_exact(self):
        net = build_network(get_template(CORE))
        proj = project_harmony_exercise(full_key_spec("C", "major"), net)
        proj.validate()
        self.assertEqual(len(proj.steps), 7)
        self.assertTrue(all(s.mapping_status == "exact" for s in proj.steps))
        # Dm maps to the ii triad node, NOT the C key node
        self.assertEqual(proj.step_at_index(1).visual_node_id, "hn:triad:C:major:1")
        self.assertEqual(proj.counts()["byMappingStatus"], {"exact": 7})
        # enumeration still asserts NO theoretical resolution edges
        self.assertEqual(proj.counts()["theoryEdges"], 0)

    def test_a_minor_full_key_all_exact(self):
        net = build_network(get_template(CORE),
                            context=NetworkBuildContext(key="A", mode="natural_minor"))
        proj = project_harmony_exercise(full_key_spec("A", "natural_minor"), net)
        proj.validate()
        self.assertEqual(len(proj.steps), 7)
        self.assertTrue(all(s.mapping_status == "exact" for s in proj.steps))
        self.assertTrue(all(s.mode == "natural_minor" for s in proj.steps))


CADENCE = "cadence_resolution_network_v1"


class TestCadenceTemplate(unittest.TestCase):
    def setUp(self):
        self.net = build_network(get_template(CADENCE))

    def test_reuses_core_nodes(self):
        # same 11 nodes as the core template (no chord duplicated per path)
        self.assertEqual(self.net.counts()["nodesByKind"],
                         {"key_center": 1, "diatonic_triad": 7, "function_family": 3})

    def test_major_path_catalogue(self):
        labels = [p.label for p in self.net.paths]
        for expected in ("V–I", "IV–I", "V–vi", "ii–V", "IV–V",
                         "ii–V–I", "I–IV–V–I", "vi–ii–V–I"):
            self.assertIn(expected, labels)
        self.assertEqual(len(self.net.paths), 10)

    def test_paths_reference_real_nodes_and_edges(self):
        node_ids = {n.id for n in self.net.nodes}
        edge_ids = {e.id for e in self.net.edges}
        for p in self.net.paths:
            self.assertEqual(len(p.node_ids), len(p.romans))
            for nid in p.node_ids:
                self.assertIn(nid, node_ids)
            for eid in p.edge_ids:
                self.assertIn(eid, edge_ids)

    def test_theory_edges_only_where_supported(self):
        by_label = {p.label: p for p in self.net.paths}
        # ii-V-I: both ii->V and V->I are supported motions
        self.assertEqual(len(by_label["ii–V–I"].edge_ids), 2)
        # I-V-vi-IV: only V->vi is a supported canonical motion (I->V, vi->IV are not)
        self.assertEqual(len(by_label["I–V–vi–IV"].edge_ids), 1)

    def test_payload_carries_paths(self):
        payload = self.net.to_payload()
        self.assertEqual(len(payload["paths"]), 10)
        self.assertEqual(payload["paths"][0]["mode"], "major")

    def test_transposition_gives_fresh_key_scoped_paths(self):
        g = build_network(get_template(CADENCE),
                          context=NetworkBuildContext(key="G", mode="major"))
        ids = {p.id for p in g.paths}
        self.assertTrue(any(":G:major" in pid for pid in ids))
        for p in g.paths:
            for nid in p.node_ids:
                self.assertTrue(nid.startswith("hn:triad:G:major:"))

    def test_minor_catalogue(self):
        a = build_network(get_template(CADENCE),
                          context=NetworkBuildContext(key="A", mode="natural_minor"))
        labels = {p.label for p in a.paths}
        self.assertEqual(labels, {"v–i", "VII–i", "iv–v–i", "i–iv–v–i", "i–VI–VII–i"})


class TestPhase8Templates(unittest.TestCase):
    """Post-MVP orbit / class / equivalence templates (plan section 14.4)."""

    def test_all_three_registered_and_build(self):
        for tid in ("transposition_orbit_network_v1", "quality_class_network_v1",
                    "functional_equivalence_network_v1"):
            net = build_network(get_template(tid))
            self.assertTrue(net.nodes)

    def test_transposition_orbit_structure_and_projection(self):
        from harmony.atlas import degree_spec
        net = build_network(get_template("transposition_orbit_network_v1"))
        self.assertEqual(net.counts()["nodesByKind"], {"degree_class": 1, "diatonic_triad": 12})
        self.assertTrue(all(e.relation == "instance_of" for e in net.edges))
        proj = project_harmony_exercise(degree_spec("V", "major"), net)
        proj.validate()
        self.assertEqual(len(proj.steps), 12)
        self.assertEqual(proj.counts()["byMappingStatus"], {"exact": 12})
        # transposition, never modulation
        self.assertTrue(all(t.sequence_relation == "transpose_next" for t in proj.transitions))
        self.assertEqual(proj.counts()["theoryEdges"], 0)

    def test_transposition_orbit_degree_and_keys_context(self):
        net = build_network(get_template("transposition_orbit_network_v1"),
                            context=NetworkBuildContext(degree="ii", mode="major",
                                                        keys=("C", "G", "D")))
        self.assertIn("hn:degree:major:ii", {n.id for n in net.nodes})
        self.assertEqual(len(net.nodes_of_kind("diatonic_triad")), 3)

    def test_quality_class_structure_and_projection(self):
        from harmony.exercise_spec import HarmonyExerciseSpec
        net = build_network(get_template("quality_class_network_v1"))
        self.assertEqual(net.counts()["nodesByKind"], {"quality_class": 3, "diatonic_triad": 7})
        qids = {n.id for n in net.nodes_of_kind("quality_class")}
        self.assertEqual(qids, {"hn:quality:major", "hn:quality:minor", "hn:quality:diminished"})
        spec = HarmonyExerciseSpec(exercise_id="q", title="maj", drill="quality",
                                   quality="major", mode="major", keys=["C"])
        proj = project_harmony_exercise(spec, net)
        proj.validate()
        self.assertEqual(proj.semantic_group, "quality_class")
        self.assertEqual(proj.sequence_semantics, "class_enumeration")
        self.assertEqual(proj.counts()["byMappingStatus"].get("exact"), 3)
        self.assertEqual(proj.counts()["theoryEdges"], 0)

    def test_functional_equivalence_honesty(self):
        net = build_network(get_template("functional_equivalence_network_v1"))
        self.assertEqual(net.counts()["nodesByKind"],
                         {"function_family": 1, "diatonic_triad": 1,
                          "dominant_seventh": 1, "diminished_triad": 1})
        # ticket 12: the seventh chord launches the real V7->I drill, exactly
        # like the V triad and vii° (the reserved marker is gone).
        from harmony.exercise_spec import HarmonyExerciseSpec as _Spec
        v7 = net.node("hn:dom7:G")
        self.assertEqual(v7.trainer_specs[0]["status"], "launchable")
        v7_spec = _Spec.from_dict(v7.trainer_specs[0]["spec"])
        self.assertEqual(v7_spec.pattern, ["V7", "I"])
        self.assertEqual(v7_spec.keys, ["C"])
        self.assertEqual(net.node("hn:triad:C:major:4").trainer_specs[0]["status"], "launchable")
        self.assertEqual(net.node("hn:dim:B").trainer_specs[0]["status"], "launchable")
        rels = {e.relation for e in net.edges}
        self.assertEqual(rels, {"member_of_function", "substitutes_for", "same_function"})

    def test_functional_equivalence_minor_uses_harmonic_minor_dominants(self):
        # Ticket 13 (G2a): minor keys no longer refuse -- the dominant trio is
        # drawn from HARMONIC minor (raised leading tone), never from the
        # natural-minor degrees (minor v / subtonic VII), which would be the
        # dishonest reading the old major-only refusal prevented.
        from harmony.exercise_spec import HarmonyExerciseSpec as _Spec
        net = build_network(get_template("functional_equivalence_network_v1"),
                            context=NetworkBuildContext(key="A", mode="natural_minor"))
        self.assertEqual(net.counts()["nodesByKind"],
                         {"function_family": 1, "diatonic_triad": 1,
                          "dominant_seventh": 1, "diminished_triad": 1})
        v = net.node("hn:triad:A:harmonic_minor:4")
        self.assertEqual(v.label, "E")            # E major, not E minor
        self.assertEqual(v.quality, "major")
        v_spec = _Spec.from_dict(v.trainer_specs[0]["spec"])
        self.assertEqual(v_spec.mode, "harmonic_minor")
        self.assertEqual(v_spec.pattern, ["V", "i"])
        v7 = net.node("hn:dom7:E")
        self.assertEqual(v7.trainer_specs[0]["status"], "launchable")
        v7_spec = _Spec.from_dict(v7.trainer_specs[0]["spec"])
        self.assertEqual(v7_spec.pattern, ["V7", "i"])
        self.assertEqual(v7_spec.mode, "harmonic_minor")
        dim = net.node("hn:dim:G#")
        self.assertEqual(dim.label, "G#°")        # raised leading tone
        self.assertEqual(dim.trainer_specs[0]["status"], "launchable")
        # No chord node may claim a natural-minor atlas TRIAD (Em / G are
        # different chords); the family node's natural-minor dominant
        # *function* ref is honest -- the key itself is still A minor.
        for n in net.nodes:
            for ref in n.atlas_refs:
                self.assertFalse(
                    ref.startswith("triad:") and ":natural_minor:" in ref,
                    f"{n.id} claims natural-minor triad {ref}")

    def test_deterministic(self):
        for tid in ("transposition_orbit_network_v1", "quality_class_network_v1",
                    "functional_equivalence_network_v1"):
            a = build_network(get_template(tid))
            b = build_network(get_template(tid))
            self.assertEqual([n.id for n in a.nodes], [n.id for n in b.nodes])
            self.assertEqual([(e.source, e.target, e.relation) for e in a.edges],
                             [(e.source, e.target, e.relation) for e in b.edges])


class TestLegacyUnchanged(unittest.TestCase):
    def test_legacy_still_48_nodes_240_edges(self):
        net = build_network()  # default legacy
        self.assertEqual(len(net.nodes), 48)
        self.assertEqual(len(net.edges), 240)
        self.assertIsNone(net.context)   # legacy is not key-local


class TestBuilderRuleGuards(unittest.TestCase):
    """review finding: a rule with no builder method must fail cleanly, not with AttributeError."""

    def test_missing_builder_method_raises_valueerror_not_attributeerror(self):
        from harmony.harmonic_network import _NetworkBuilder
        from harmony.atlas import build_atlas
        b = _NetworkBuilder(get_template(CORE), build_atlas())
        with self.assertRaises(ValueError):
            b.run_rule("no_such_rule_exists")
        with self.assertRaises(ValueError):
            b.run_node_rule("no_such_node_rule")


if __name__ == "__main__":
    unittest.main()
