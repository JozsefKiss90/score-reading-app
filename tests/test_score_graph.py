"""Tests for the score-specific graph / mandala (harmony/score_graph.py)."""

import json
import unittest

from harmony.score_graph import (
    EDGE_RELATIONS,
    NODE_TYPES,
    SCORE_GRAPH_SCHEMA,
    build_score_graph,
)
from harmony.score_import import load_bwv846_analysis


class TestScoreGraphBwv846(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = load_bwv846_analysis()
        cls.graph = build_score_graph(cls.result)
        cls.payload = cls.graph.to_payload()

    def test_schema_and_serialisable(self):
        self.assertEqual(self.payload["schema"], SCORE_GRAPH_SCHEMA)
        json.dumps(self.payload)

    def test_has_measure_nodes(self):
        measures = self.graph.measure_nodes()
        self.assertEqual(len(measures), self.result.measure_count)
        self.assertEqual(measures[0].id, "measure:1")

    def test_has_follows_edges(self):
        follows = self.graph.edges_of_relation("follows")
        # one fewer than the number of measures
        self.assertEqual(len(follows), self.result.measure_count - 1)
        # they chain consecutive measures
        ids = {(e.source, e.target) for e in follows}
        self.assertIn(("measure:1", "measure:2"), ids)

    def test_all_node_types_present(self):
        present = {n.type for n in self.graph.nodes}
        for t in ("score", "form_section", "measure", "harmony_slice", "chord",
                  "roman", "function", "cadence", "key_area", "atlas_ref",
                  "network_ref"):
            self.assertIn(t, present, "missing node type %s" % t)
        for t in present:
            self.assertIn(t, NODE_TYPES)

    def test_all_edge_relations_present(self):
        present = {e.relation for e in self.graph.edges}
        for r in ("occurs_in", "follows", "prolongs", "resolves_to", "prepares",
                  "cadential_member_of", "maps_to_atlas", "maps_to_network",
                  "belongs_to_section"):
            self.assertIn(r, present, "missing relation %s" % r)
        for r in present:
            self.assertIn(r, EDGE_RELATIONS)

    def test_edges_have_valid_endpoints(self):
        ids = {n.id for n in self.graph.nodes}
        for e in self.graph.edges:
            self.assertIn(e.source, ids)
            self.assertIn(e.target, ids)

    def test_cadence_node_maps_to_atlas_cadence(self):
        cads = self.graph.nodes_of_type("cadence")
        self.assertTrue(cads)
        refs = [c.data.get("atlasRef") for c in cads]
        self.assertIn("cadence:Authentic_major", refs)

    def test_resolves_to_includes_dominant_to_tonic(self):
        res = self.graph.edges_of_relation("resolves_to")
        self.assertTrue(res)
        # m3 (V6/5) resolves to m4 (I)
        ids = {(e.source, e.target) for e in res}
        self.assertIn(("measure:3", "measure:4"), ids)

    def test_chromatic_measure_node_visual_class(self):
        node = self.graph.node("measure:6")
        self.assertEqual(node.visual_class, "chromatic")

    def test_ambiguous_measure_node_visual_class(self):
        # m29 is an ambiguous dominant suspension
        node = self.graph.node("measure:29")
        self.assertEqual(node.visual_class, "ambiguous")

    def test_atlas_and_network_bridge_edges_exist(self):
        self.assertTrue(self.graph.edges_of_relation("maps_to_atlas"))
        self.assertTrue(self.graph.edges_of_relation("maps_to_network"))

    def test_deterministic(self):
        g2 = build_score_graph(load_bwv846_analysis())
        self.assertEqual(json.dumps(g2.to_payload()),
                         json.dumps(self.payload))


class TestScoreGraphBwv999(unittest.TestCase):
    """Minor-key, sidecar-only build path + a cadence with no Atlas node."""

    @classmethod
    def setUpClass(cls):
        from harmony.score_import import load_analysis_from_sidecar
        cls.result = load_analysis_from_sidecar("bwv999_prelude_c_minor")
        cls.graph = build_score_graph(cls.result)

    def test_builds_and_serialisable(self):
        json.dumps(self.graph.to_payload())
        self.assertTrue(self.graph.measure_nodes())

    def test_chromatic_minor_measures_marked(self):
        for m in (2, 9, 10, 11):
            self.assertEqual(self.graph.node("measure:%d" % m).visual_class,
                             "chromatic")

    def test_half_cadence_without_atlas_node_does_not_crash(self):
        cads = self.graph.nodes_of_type("cadence")
        self.assertTrue(cads)
        # the [iv, V] half cadence has no matching Atlas cadence node -> None
        self.assertIsNone(cads[0].data.get("atlasRef"))


if __name__ == "__main__":
    unittest.main()
