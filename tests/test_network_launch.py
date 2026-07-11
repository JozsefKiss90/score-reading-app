"""Phase 5 tests for harmony/network_launch.py (Graph -> Drill actions).

Covers plan section 20.3: key-node tonic identity vs full field, function-family enumeration,
diminished vii°-I, resolution-edge progression, key-relation comparison (not progression),
reserved-action honesty, cap enforcement, and the compile/preview envelope.
"""

import unittest

from harmony.harmonic_network import build_network
from harmony.network_template import get_template
from harmony.harmonic_flow import GraphDrillRequest, LaunchAction
from harmony.network_launch import actions_for_selection, compile_graph_drill_action


CORE = "core_triad_function_network_v1"


def _core():
    return build_network(get_template(CORE))


def _legacy():
    return build_network(get_template())


def _node_req(nid, **kw):
    return GraphDrillRequest(template_id="t", interaction_kind="node",
                             selected_node_ids=(nid,), **kw)


def _edge_req(eid, **kw):
    return GraphDrillRequest(template_id="t", interaction_kind="edge",
                             selected_edge_ids=(eid,), **kw)


class TestKeyNodeActions(unittest.TestCase):
    def setUp(self):
        self.net = _core()
        self.actions = actions_for_selection(_node_req("hn:key:C"), self.net)

    def test_tonic_identity_differs_from_full_field(self):
        by_group = {a.semantic_group: a for a in self.actions if a.status == "launchable"}
        self.assertIn("node_identity", by_group)
        self.assertIn("tonal_field", by_group)
        tonic = by_group["node_identity"]
        field = by_group["tonal_field"]
        # one chord vs seven -- genuinely different actions
        self.assertEqual(len(tonic.preview_projection["steps"]), 1)
        self.assertEqual(len(field.preview_projection["steps"]), 7)
        self.assertNotEqual(tonic.spec["exercise_id"], field.spec["exercise_id"])

    def test_function_family_enumeration_present(self):
        fams = [a for a in self.actions if a.semantic_group == "functional_neighbourhood"]
        self.assertTrue(fams)
        # families are enumeration, not progression: their preview has no theory edges
        for a in fams:
            self.assertEqual(a.preview_projection["counts"]["theoryEdges"], 0)

    def test_cadence_actions_are_functional_paths(self):
        cads = [a for a in self.actions if a.semantic_group == "functional_path"]
        self.assertTrue(any(a.label.startswith("Cadence") for a in cads))

    def test_every_launchable_action_validates(self):
        for a in self.actions:
            if a.status == "launchable":
                a.validate()
                self.assertIsNotNone(a.spec)
                self.assertEqual(a.spec_type, "harmony_exercise")


class TestTriadNodeActions(unittest.TestCase):
    def test_triad_identity_arpeggio_and_inversion_lab(self):
        net = _core()
        actions = actions_for_selection(_node_req("hn:triad:C:major:4"), net)
        labels = [a.label for a in actions]
        self.assertTrue(any("Play G" in l for l in labels))
        self.assertTrue(any("Arpeggiate" in l for l in labels))
        # inversion routes to the Lab as a lab_experiment request
        lab = [a for a in actions if a.target == "lab"]
        self.assertEqual(len(lab), 1)
        self.assertEqual(lab[0].spec_type, "lab_experiment")
        self.assertEqual(lab[0].request["labConcept"], "inversion")
        self.assertEqual(lab[0].request["inversions"], [0, 1, 2])


class TestFunctionNodeActions(unittest.TestCase):
    def test_enumeration_and_route(self):
        net = _core()
        actions = actions_for_selection(_node_req("hn:function:major:dominant"), net)
        groups = {a.semantic_group for a in actions}
        self.assertIn("functional_neighbourhood", groups)   # enumeration
        self.assertIn("functional_path", groups)            # standard route


class TestDiminishedAndDom7(unittest.TestCase):
    def test_diminished_offers_vii_i(self):
        net = _legacy()
        actions = actions_for_selection(_node_req("hn:dim:B"), net)
        self.assertTrue(any("vii°" in a.label and a.status == "launchable" for a in actions))

    def test_dom7_reserved_and_approximation(self):
        net = _legacy()
        actions = actions_for_selection(_node_req("hn:dom7:G"), net)
        statuses = {a.status for a in actions}
        self.assertIn("reserved", statuses)        # V7 stays reserved
        self.assertIn("launchable", statuses)      # V->I approximation launchable
        reserved = [a for a in actions if a.status == "reserved"][0]
        self.assertIsNone(reserved.spec)
        self.assertIn("reserved", reserved.reason.lower())


class TestEdgeActions(unittest.TestCase):
    def test_resolution_edge_is_a_progression(self):
        net = _core()
        eid = "hn:triad:C:major:4|resolves_to|hn:triad:C:major:0"
        actions = actions_for_selection(_edge_req(eid), net)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].semantic_group, "functional_path")
        # the progression preview carries a real theory edge
        self.assertGreaterEqual(actions[0].preview_projection["counts"]["theoryEdges"], 1)

    def test_fifth_relation_is_comparison_not_progression(self):
        net = _legacy()
        eid = "hn:major:C|fifth_relation|hn:major:G"
        actions = actions_for_selection(_edge_req(eid), net)
        self.assertTrue(actions)
        for a in actions:
            self.assertNotEqual(a.semantic_group, "functional_path")
            self.assertEqual(a.semantic_group, "transposition_orbit")

    def test_relative_relation_is_comparison(self):
        net = _legacy()
        eid = "hn:major:C|relative_minor_of|hn:minor:A"
        actions = actions_for_selection(_edge_req(eid), net)
        self.assertTrue(actions)
        for a in actions:
            self.assertNotEqual(a.semantic_group, "functional_path")

    def test_legacy_dom7_resolution_edge_is_triad_progression(self):
        net = _legacy()
        eid = "hn:dom7:G|resolves_to|hn:major:C"
        actions = actions_for_selection(_edge_req(eid), net)
        self.assertTrue(actions)
        self.assertEqual(actions[0].semantic_group, "functional_path")
        # V-I into a MAJOR key is honest
        self.assertEqual(actions[0].spec["pattern"], ["V", "I"])

    def test_dim_resolving_into_minor_key_is_skipped(self):
        # review finding: B° -> C minor must NOT fabricate 'ii°-i' (D°-Cm); it is skipped
        net = _legacy()
        eid = "hn:dim:B|leading_tone_to|hn:minor:C"
        self.assertEqual(actions_for_selection(_edge_req(eid), net), [])

    def test_dom7_resolving_into_minor_key_is_skipped(self):
        net = _legacy()
        eid = "hn:dom7:G|resolves_to|hn:minor:C"
        self.assertEqual(actions_for_selection(_edge_req(eid), net), [])


class TestLabActionSpecs(unittest.TestCase):
    """review finding: launchable lab actions must carry a spec (else compile crashes)."""

    def test_triad_inversion_lab_action_carries_spec_and_compiles(self):
        net = build_network(get_template(CORE))
        req = GraphDrillRequest(template_id="core", interaction_kind="node",
                                selected_node_ids=("hn:triad:C:major:0",))
        lab = [a for a in actions_for_selection(req, net) if a.target == "lab"][0]
        self.assertEqual(lab.status, "launchable")
        self.assertIsNotNone(lab.spec)
        # compiling the chosen lab action must not raise (LaunchAction.validate needs a spec)
        act = compile_graph_drill_action(req, net, action_id=lab.id)
        self.assertEqual(act.id, lab.id)
        act.validate()

    def test_path_voice_leading_lab_carries_spec(self):
        net = build_network(get_template("cadence_resolution_network_v1"))
        pid = next(p.id for p in net.paths if p.label == "ii–V–I")
        req = GraphDrillRequest(template_id="cad", interaction_kind="path",
                                selected_path_id=pid)
        lab = [a for a in actions_for_selection(req, net) if a.target == "lab"][0]
        self.assertEqual(lab.status, "launchable")
        self.assertIsNotNone(lab.spec)
        lab.validate()


class TestPathActions(unittest.TestCase):
    def setUp(self):
        self.net = build_network(get_template("cadence_resolution_network_v1"))
        self.pid = next(p.id for p in self.net.paths if p.label == "ii–V–I")

    def test_path_offers_block_arpeggio_and_lab(self):
        req = GraphDrillRequest(template_id="cad", interaction_kind="path",
                                selected_path_id=self.pid)
        actions = actions_for_selection(req, self.net)
        targets = {a.target for a in actions}
        self.assertEqual(targets, {"trainer", "lab"})
        renders = {a.spec["render"] for a in actions if a.target == "trainer"}
        self.assertEqual(renders, {"block", "arpeggio"})
        lab = [a for a in actions if a.target == "lab"][0]
        self.assertEqual(lab.request["labConcept"], "voice_leading")

    def test_path_block_preview_shows_the_route_theory_edges(self):
        req = GraphDrillRequest(template_id="cad", interaction_kind="path",
                                selected_path_id=self.pid)
        block = next(a for a in actions_for_selection(req, self.net)
                     if a.target == "trainer" and a.spec["render"] == "block")
        self.assertEqual(len(block.preview_projection["steps"]), 3)
        self.assertEqual(block.preview_projection["counts"]["theoryEdges"], 2)

    def test_unknown_path_yields_nothing(self):
        req = GraphDrillRequest(template_id="cad", interaction_kind="path",
                                selected_path_id="path:nope")
        self.assertEqual(actions_for_selection(req, self.net), [])


class TestCompileEnvelope(unittest.TestCase):
    def test_compile_returns_validated_launchable(self):
        net = _core()
        act = compile_graph_drill_action(_node_req("hn:key:C"), net)
        self.assertIsInstance(act, LaunchAction)
        self.assertEqual(act.status, "launchable")
        act.validate()

    def test_compile_specific_action_id(self):
        net = _core()
        req = _node_req("hn:key:C")
        all_actions = actions_for_selection(req, net)
        target = next(a for a in all_actions if a.semantic_group == "tonal_field")
        act = compile_graph_drill_action(req, net, action_id=target.id)
        self.assertEqual(act.id, target.id)

    def test_unknown_node_yields_no_actions(self):
        net = _core()
        self.assertEqual(actions_for_selection(_node_req("hn:nope"), net), [])

    def test_invalid_request_rejected(self):
        net = _core()
        with self.assertRaises(ValueError):
            actions_for_selection(
                GraphDrillRequest(template_id="t", interaction_kind="node"), net)


if __name__ == "__main__":
    unittest.main()
