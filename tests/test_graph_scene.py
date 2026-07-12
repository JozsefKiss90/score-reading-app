"""Phase 1 tests for harmony/graph_scene.py -- the pure GraphScene contract + honesty gate.

Covers: round-trip (to_dict/from_dict), structural validation, and the crux invariant that a chord
occurrence can NEVER map onto a key node (plan sections 1, 3, 10).
"""

import unittest

from harmony.graph_scene import (
    GraphScene, GraphSceneNode, GraphSceneEdge, GraphScenePath, SceneOccurrence, SceneLayer,
    SceneValidationError, unsupported_scene,
)


def _key_node():
    return GraphSceneNode(id="hn:key:C", label="C major", entity_type="key", entity_role="anchor")


def _triad(roman, symbol, deg, quality="major"):
    return GraphSceneNode(id=f"hn:triad:C:major:{deg}", label=symbol, entity_type="triad",
                          roman=roman, chord_symbol=symbol, quality=quality, key_context="C major",
                          degree_index=deg)


def _occ(seq, node_id, roman, symbol, status="exact", primary=None, etype="triad"):
    return SceneOccurrence(occurrence_id=f"occ:{seq}", sequence_index=seq, node_id=node_id,
                           entity_type=etype, mapping_status=status,
                           primary_node_id=(primary if primary is not None else node_id),
                           roman=roman, chord_symbol=symbol)


class TestRoundTrip(unittest.TestCase):
    def _scene(self):
        return GraphScene(
            scene_id="scene:x", scene_type="diatonic_key_field", title="C field", subtitle="C major",
            source_kind="harmony_exercise", source_id="fk_C", pedagogical_goal="enumerate",
            semantic_scope="local_key", key_context="C major", mode="major",
            nodes=[_key_node(), _triad("I", "C", 0), _triad("V", "G", 4)],
            edges=[GraphSceneEdge(id="e1", source="hn:triad:C:major:0", target="hn:key:C",
                                  relation="belongs_to_key", layer="context"),
                   GraphSceneEdge(id="e2", source="hn:triad:C:major:4", target="hn:triad:C:major:0",
                                  relation="resolves_to", layer="theory")],
            paths=[GraphScenePath(id="p1", label="V-I", node_ids=("hn:triad:C:major:4",
                                                                   "hn:triad:C:major:0"))],
            occurrence_map=[_occ(0, "hn:triad:C:major:0", "I", "C"),
                            _occ(1, "hn:triad:C:major:4", "V", "G")],
            layer_definitions=[SceneLayer(id="theory", label="Theory", kind="theory",
                                          default_visible=False)])

    def test_scene_round_trips(self):
        s = self._scene()
        s.validate()
        again = GraphScene.from_dict(s.to_dict())
        again.validate()
        self.assertEqual(again.to_dict(), s.to_dict())

    def test_primitive_round_trips(self):
        for prim, cls in [(_key_node(), GraphSceneNode),
                          (GraphSceneEdge(id="e", source="a", target="b", relation="instance_of",
                                          layer="structure"), GraphSceneEdge),
                          (SceneOccurrence(occurrence_id="o", sequence_index=0, node_id="n",
                                           entity_type="triad", mapping_status="exact"),
                           SceneOccurrence),
                          (SceneLayer(id="theory", label="Theory", kind="theory"), SceneLayer)]:
            self.assertEqual(cls.from_dict(prim.to_dict()).to_dict(), prim.to_dict())


class TestHonestyGate(unittest.TestCase):
    def test_chord_occurrence_on_key_node_is_rejected(self):
        # An Am chord occurrence pointing at a key node -- the exact conflation the rework forbids.
        scene = GraphScene(
            scene_id="s", scene_type="diatonic_key_field", title="t", subtitle="",
            source_kind="harmony_exercise", source_id="x", pedagogical_goal="",
            semantic_scope="local_key",
            nodes=[GraphSceneNode(id="hn:key:A", label="A minor", entity_type="key")],
            occurrence_map=[_occ(0, "hn:key:A", "vi", "Am")])
        with self.assertRaises(SceneValidationError):
            scene.validate()

    def test_exact_occurrence_cannot_use_a_proxy_node(self):
        scene = GraphScene(
            scene_id="s", scene_type="diatonic_key_field", title="t", subtitle="",
            source_kind="harmony_exercise", source_id="x", pedagogical_goal="",
            semantic_scope="local_key",
            nodes=[GraphSceneNode(id="overlay:triad:C:major:1", label="Dm", entity_type="occurrence")],
            occurrence_map=[_occ(0, "overlay:triad:C:major:1", "ii", "Dm", status="exact",
                                 primary="overlay:triad:C:major:1")])
        with self.assertRaises(SceneValidationError):
            scene.validate()

    def test_edge_endpoints_must_exist(self):
        scene = GraphScene(
            scene_id="s", scene_type="diatonic_key_field", title="t", subtitle="",
            source_kind="harmony_exercise", source_id="x", pedagogical_goal="",
            semantic_scope="local_key", nodes=[_key_node()],
            edges=[GraphSceneEdge(id="e", source="hn:key:C", target="missing",
                                  relation="belongs_to_key", layer="context")])
        with self.assertRaises(SceneValidationError):
            scene.validate()

    def test_noncontiguous_sequence_rejected(self):
        scene = GraphScene(
            scene_id="s", scene_type="diatonic_key_field", title="t", subtitle="",
            source_kind="harmony_exercise", source_id="x", pedagogical_goal="",
            semantic_scope="local_key", nodes=[_triad("I", "C", 0)],
            occurrence_map=[_occ(0, "hn:triad:C:major:0", "I", "C"),
                            _occ(2, "hn:triad:C:major:0", "I", "C")])
        with self.assertRaises(SceneValidationError):
            scene.validate()


class TestUnsupportedScene(unittest.TestCase):
    def test_unsupported_is_empty_and_explained(self):
        s = unsupported_scene(scene_id="s:mot", title="Motive", source_kind="lab",
                              source_id="mot_C", reason="melodic motive has no harmonic graph yet")
        s.validate()
        self.assertEqual(s.scene_type, "unsupported")
        self.assertEqual(len(s.occurrence_map), 0)
        self.assertTrue(s.warnings)
        self.assertEqual(GraphScene.from_dict(s.to_dict()).to_dict(), s.to_dict())

    def test_unsupported_with_occurrences_is_rejected(self):
        s = unsupported_scene(scene_id="s", title="t", source_kind="lab", source_id="x",
                              reason="none")
        # mutate it into an illegal state: an unsupported scene must stay empty
        s.nodes = [_triad("I", "C", 0)]
        s.occurrence_map = [_occ(0, "hn:triad:C:major:0", "I", "C")]
        with self.assertRaises(SceneValidationError):
            s.validate()


if __name__ == "__main__":
    unittest.main()
