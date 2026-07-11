"""Phase 7 tests for inversion_space_network_v1 + project_lab_experiment (routed to the Lab).

Covers plan section 14.3 / 20.5: distinct C, C/E, C/G state nodes sharing one chord identity;
bass / figured-bass annotations; the Lab projection mapping one identity + three voicing states;
seek indexes aligned with Lab measure indexes; invariant chord function.
"""

import unittest

from harmony.harmonic_network import build_network, NetworkBuildContext
from harmony.network_template import get_template
from harmony.harmonic_flow import GraphDrillRequest
from harmony.network_launch import actions_for_selection, compile_graph_drill_action
from harmony.network_projection import project_lab_experiment
from harmony.lab_spec import spec_from_lab_request
from harmony.lab import compile_lab


INV = "inversion_space_network_v1"


def _inv_net(key="C", mode="major", degree="I"):
    return build_network(get_template(INV),
                         context=NetworkBuildContext(key=key, mode=mode, degree=degree))


class TestInversionTemplate(unittest.TestCase):
    def setUp(self):
        self.net = _inv_net()

    def test_identity_plus_three_states(self):
        self.assertEqual(self.net.counts()["nodesByKind"],
                         {"diatonic_triad": 1, "inversion_state": 3})

    def test_slash_labels_and_figured_bass(self):
        states = {n.data["inversion"]: n for n in self.net.nodes_of_kind("inversion_state")}
        self.assertEqual(states[0].label, "C")
        self.assertEqual(states[1].label, "C/E")
        self.assertEqual(states[2].label, "C/G")
        self.assertEqual(states[0].data["figuredBass"], "5/3")
        self.assertEqual(states[1].data["figuredBass"], "6")
        self.assertEqual(states[2].data["figuredBass"], "6/4")
        self.assertEqual(states[1].data["bassNote"], "E")

    def test_inversion_of_and_voice_leading_edges(self):
        rels = {}
        for e in self.net.edges:
            rels.setdefault(e.relation, 0)
            rels[e.relation] += 1
        self.assertEqual(rels["inversion_of"], 3)
        self.assertEqual(rels["voice_leads_to"], 2)

    def test_states_share_one_identity(self):
        roots = {n.spelling for n in self.net.nodes_of_kind("inversion_state")}
        self.assertEqual(roots, {"C"})

    def test_degree_parameterisation(self):
        net = _inv_net(key="G", mode="major", degree="V")
        labels = [n.label for n in net.nodes_of_kind("inversion_state")]
        self.assertEqual(labels, ["D", "D/F#", "D/A"])


class TestLabProjection(unittest.TestCase):
    def setUp(self):
        self.net = _inv_net()
        self.spec = spec_from_lab_request(
            {"labConcept": "inversion", "key": "C major", "mode": "major",
             "degree": "I", "inversions": [0, 1, 2]})

    def test_compile_lab_three_measures(self):
        experiment = compile_lab(self.spec)
        self.assertEqual(len(experiment.measures), 3)

    def test_projection_one_identity_three_states(self):
        proj = project_lab_experiment(self.spec, self.net)
        proj.validate()
        self.assertEqual(len(proj.steps), 3)
        self.assertEqual(proj.anchor_node_ids, ["hn:inv:C:major:0:identity"])
        self.assertTrue(all(s.mapping_type == "voicing_state" for s in proj.steps))
        self.assertTrue(all(s.mapping_status == "exact" for s in proj.steps))
        self.assertEqual([s.visual_node_id for s in proj.steps],
                         ["hn:inv:C:major:0:0", "hn:inv:C:major:0:1", "hn:inv:C:major:0:2"])

    def test_bass_changes_and_figured_bass(self):
        proj = project_lab_experiment(self.spec, self.net)
        self.assertEqual([s.bass_pitch_class for s in proj.steps], [0, 4, 7])
        self.assertEqual([s.figured_bass for s in proj.steps], ["5/3", "6", "6/4"])
        self.assertEqual([s.inversion for s in proj.steps], [0, 1, 2])

    def test_function_invariant(self):
        proj = project_lab_experiment(self.spec, self.net)
        self.assertEqual(len({s.function_label for s in proj.steps}), 1)
        # chord tones invariant (same identity, only bass reorders)
        self.assertEqual(len({frozenset(s.chord_tones) for s in proj.steps}), 1)

    def test_voicing_transitions_light_voice_leading(self):
        proj = project_lab_experiment(self.spec, self.net)
        self.assertTrue(all(t.sequence_relation == "voicing_next" for t in proj.transitions))
        self.assertTrue(all(t.theory_relation == "voice_leads_to" for t in proj.transitions))

    def test_seek_indexes_align_with_measure_indexes(self):
        experiment = compile_lab(self.spec)
        proj = project_lab_experiment(self.spec, self.net)
        for m, s in zip(experiment.measures, proj.steps):
            self.assertEqual(m.index, s.sequence_index)


class TestInversionLaunchActions(unittest.TestCase):
    def test_triad_node_offers_lab_inversion_action(self):
        core = build_network(get_template("core_triad_function_network_v1"))
        actions = actions_for_selection(
            GraphDrillRequest(template_id="core", interaction_kind="node",
                              selected_node_ids=("hn:triad:C:major:0",)), core)
        lab = [a for a in actions if a.target == "lab"]
        self.assertEqual(len(lab), 1)
        self.assertEqual(lab[0].request["labConcept"], "inversion")

    def test_inversion_template_node_action_has_lab_preview(self):
        net = _inv_net()
        actions = actions_for_selection(
            GraphDrillRequest(template_id=INV, interaction_kind="node",
                              selected_node_ids=("hn:inv:C:major:0:1",)), net)
        self.assertEqual(len(actions), 1)
        act = actions[0]
        self.assertEqual(act.target, "lab")
        self.assertEqual(act.spec_type, "lab_experiment")
        self.assertIsNotNone(act.spec)
        self.assertIsNotNone(act.preview_projection)
        self.assertEqual(len(act.preview_projection["steps"]), 3)

    def test_lab_request_builds_valid_lab_spec(self):
        net = _inv_net()
        act = compile_graph_drill_action(
            GraphDrillRequest(template_id=INV, interaction_kind="node",
                              selected_node_ids=("hn:inv:C:major:0:identity",)), net)
        self.assertEqual(act.target, "lab")
        spec = spec_from_lab_request(act.request)   # must not raise
        self.assertEqual(spec.concept, "inversion")


if __name__ == "__main__":
    unittest.main()
