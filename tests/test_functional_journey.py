"""Tests for the Functional Degree Network's staged journey.

Enforces the stage machine's contract:

  * exactly 7 stages, unique ids, in the plan's order;
  * every stage references only node ids that exist in the built network and
    only implemented relations (journey_stages validates -- and raises -- on
    drift, which these tests also exercise directly);
  * the guided reveal grows monotonically (each stage's whitelist contains
    the previous stage's, until the whitelist is dropped entirely);
  * every drill compiles within the readability cap;
  * unlock logic (finish_any / finish_all) against a real ProgressStore file
    in a temp directory: satisfaction, chained unlocking, resume index;
  * drill -> exercised-node mapping (drill_node_ids);
  * lit-node persistence with the stage/drill namespace guard.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harmony.exercise_spec import (  # noqa: E402
    compile_exercise, MAX_CHORDS_PER_SPEC,
)
from harmony.curriculum_progress import ProgressStore  # noqa: E402
from harmony.functional_network import (  # noqa: E402
    build_functional_network, degree_node_id,
)
from harmony.functional_journey import (  # noqa: E402
    JourneyStage, JourneyProgress, journey_stages, drill_node_ids,
    _validate_stages, STAGE_PREFIX, DRILL_PREFIX, UNLOCK_RULES,
)
from harmony.atlas import full_key_spec  # noqa: E402


NET = build_functional_network()
STAGES = journey_stages(NET)


class TestStageDefinitions(unittest.TestCase):
    def test_seven_stages_in_plan_order(self):
        self.assertEqual([s.stage_id for s in STAGES], [
            "meet_the_scale", "three_jobs", "tension_home", "approach_chain",
            "substitutes", "same_triad_new_key", "free_exploration",
        ])

    def test_every_stage_has_title_and_explanation(self):
        for s in STAGES:
            self.assertTrue(s.title, s.stage_id)
            self.assertGreater(len(s.explanation), 80, s.stage_id)
            self.assertIn(s.unlock, UNLOCK_RULES)

    def test_stage_one_shows_exactly_the_home_degrees(self):
        s1 = STAGES[0]
        self.assertEqual(sorted(s1.visible_node_ids),
                         sorted(degree_node_id("C", i) for i in range(7)))
        self.assertEqual(s1.visible_relations, [])

    def test_reveal_grows_monotonically(self):
        prev = None
        for s in STAGES:
            if s.visible_node_ids is None:
                continue                      # free exploration: no whitelist
            cur = set(s.visible_node_ids)
            if prev is not None:
                self.assertTrue(prev <= cur,
                                f"{s.stage_id} hides previously shown nodes")
            prev = cur
        # relations also only accumulate
        prev_rel = set()
        for s in STAGES[:-1]:
            cur_rel = set(s.visible_relations)
            self.assertTrue(prev_rel <= cur_rel,
                            f"{s.stage_id} drops previously taught relations")
            prev_rel = cur_rel

    def test_stage_six_shows_everything(self):
        s6 = STAGES[5]
        self.assertEqual(sorted(s6.visible_node_ids),
                         sorted(n.id for n in NET.nodes))
        self.assertIn("shared_triad", s6.visible_relations)
        self.assertIn("fifth_relation", s6.visible_relations)

    def test_last_stage_drops_the_whitelist(self):
        s7 = STAGES[-1]
        self.assertIsNone(s7.visible_node_ids)
        self.assertEqual(s7.drills, [])

    def test_every_drill_compiles_within_cap(self):
        for s in STAGES:
            for d in s.drills:
                n = len(compile_exercise(d))
                self.assertLessEqual(n, MAX_CHORDS_PER_SPEC,
                                     f"{s.stage_id}: {d.exercise_id}")
                self.assertGreater(n, 0)

    def test_stage_drill_inventory(self):
        # 1 full-key, 1 cycle, 2 resolutions, 1 approach, 1 substitute cycle,
        # 2 cross-key, 0 free-exploration.
        self.assertEqual([len(s.drills) for s in STAGES],
                         [1, 1, 2, 1, 1, 2, 0])
        self.assertEqual(STAGES[5].drills[0].drill, "horizontal_degree")
        self.assertEqual(STAGES[5].drills[0].keys, ["C", "G", "D", "F"])
        self.assertEqual(STAGES[5].drills[1].keys, ["G"])

    def test_two_drill_stages_require_finish_all(self):
        for s in STAGES:
            if len(s.drills) >= 2:
                self.assertEqual(s.unlock, "finish_all", s.stage_id)

    def test_emphasis_nodes_are_visible(self):
        for s in STAGES:
            for nid in s.emphasis_node_ids:
                self.assertIsNotNone(NET.node(nid), f"{s.stage_id}: {nid}")
                if s.visible_node_ids is not None:
                    self.assertIn(nid, s.visible_node_ids, s.stage_id)

    def test_validation_rejects_unknown_node(self):
        bogus = JourneyStage(
            stage_id="bogus", title="x", explanation="x",
            visible_node_ids=["fnet:deg:C:99"], visible_relations=[],
            emphasis_node_ids=[])
        with self.assertRaises(ValueError):
            _validate_stages([bogus], NET)

    def test_validation_rejects_unknown_relation(self):
        bogus = JourneyStage(
            stage_id="bogus", title="x", explanation="x",
            visible_node_ids=None, visible_relations=["teleports_to"],
            emphasis_node_ids=[])
        with self.assertRaises(ValueError):
            _validate_stages([bogus], NET)

    def test_validation_rejects_hidden_emphasis(self):
        bogus = JourneyStage(
            stage_id="bogus", title="x", explanation="x",
            visible_node_ids=[degree_node_id("C", 0)], visible_relations=[],
            emphasis_node_ids=[degree_node_id("C", 1)])
        with self.assertRaises(ValueError):
            _validate_stages([bogus], NET)

    def test_validation_rejects_bad_unlock_rule(self):
        bogus = JourneyStage(
            stage_id="bogus", title="x", explanation="x",
            visible_node_ids=None, visible_relations=[],
            emphasis_node_ids=[], unlock="finish_maybe")
        with self.assertRaises(ValueError):
            _validate_stages([bogus], NET)

    def test_validation_enforces_the_readability_cap(self):
        from harmony.atlas import function_spec
        oversized = JourneyStage(
            stage_id="bogus", title="x", explanation="x",
            visible_node_ids=None, visible_relations=[],
            emphasis_node_ids=[],
            drills=[function_spec(["I"] * (MAX_CHORDS_PER_SPEC + 1),
                                  "too-long", "major", ["C"])])
        with self.assertRaises(ValueError) as ctx:
            _validate_stages([oversized], NET)
        self.assertIn("chords", str(ctx.exception))

    def test_horizontal_drill_description_derives_its_key_count(self):
        self.assertIn("4 different keys", STAGES[5].drills[0].description)
        from harmony.functional_network import build_functional_network
        small = journey_stages(build_functional_network(keys=["C", "G"]))
        self.assertIn("2 different keys", small[5].drills[0].description)
        self.assertNotIn("four", small[5].drills[0].description)

    def test_journey_over_non_canonical_keys_still_validates(self):
        # "C major" spelling normalises to the same ids the network uses.
        from harmony.functional_network import build_functional_network
        net = build_functional_network(keys=["C major", "G"])
        stages = journey_stages(net)          # must not raise
        self.assertIn(degree_node_id("C", 0), stages[0].visible_node_ids)


class TestDrillNodeIds(unittest.TestCase):
    def test_function_drill_maps_to_degree_nodes_in_order(self):
        ids = drill_node_ids(STAGES[3].drills[0])       # ii–V–I in C
        self.assertEqual(ids, [degree_node_id("C", 1), degree_node_id("C", 4),
                               degree_node_id("C", 0)])

    def test_full_key_drill_covers_all_seven(self):
        ids = drill_node_ids(full_key_spec("C", "major"))
        self.assertEqual(ids, [degree_node_id("C", i) for i in range(7)])

    def test_horizontal_drill_spans_the_journey_keys(self):
        ids = drill_node_ids(STAGES[5].drills[0])       # V across C G D F
        self.assertEqual(ids, [degree_node_id(k, 4)
                               for k in ("C", "G", "D", "F")])

    def test_deduplicates_repeated_degrees(self):
        ids = drill_node_ids(STAGES[1].drills[0])       # I–IV–V–I in C
        self.assertEqual(ids, [degree_node_id("C", 0), degree_node_id("C", 3),
                               degree_node_id("C", 4)])


class TestJourneyProgress(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "progress.json")
        self.jp = JourneyProgress(ProgressStore(self.path))

    def tearDown(self):
        self.tmp.cleanup()

    def _reload(self) -> JourneyProgress:
        return JourneyProgress(ProgressStore(self.path))

    def test_initial_state(self):
        self.assertTrue(self.jp.stage_unlocked(STAGES, 0))
        self.assertFalse(self.jp.stage_unlocked(STAGES, 1))
        self.assertFalse(self.jp.stage_unlocked(STAGES, len(STAGES)))
        self.assertEqual(self.jp.resume_stage_index(STAGES), 0)
        self.assertEqual(self.jp.lit_node_ids(), [])

    def test_finish_any_satisfies_single_drill_stage(self):
        s1 = STAGES[0]
        self.assertFalse(self.jp.stage_satisfied(s1))
        self.jp.mark_drill_finished(s1.drills[0].exercise_id,
                                    "2026-07-06T10:00:00")
        self.assertTrue(self.jp.stage_satisfied(s1))
        self.assertTrue(self.jp.stage_unlocked(STAGES, 1))
        self.assertEqual(self.jp.resume_stage_index(STAGES), 1)

    def test_finish_all_requires_every_drill(self):
        s3 = STAGES[2]
        self.assertEqual(s3.unlock, "finish_all")
        self.jp.mark_drill_finished(s3.drills[0].exercise_id)
        self.assertFalse(self.jp.stage_satisfied(s3))
        self.jp.mark_drill_finished(s3.drills[1].exercise_id)
        self.assertTrue(self.jp.stage_satisfied(s3))

    def test_unlock_requires_the_whole_chain(self):
        # Satisfying stage 3 alone must NOT unlock stage 4: stages 1-2 gate it.
        s3 = STAGES[2]
        self.jp.mark_drill_finished(s3.drills[0].exercise_id)
        self.jp.mark_drill_finished(s3.drills[1].exercise_id)
        self.assertFalse(self.jp.stage_unlocked(STAGES, 3))
        self.jp.mark_drill_finished(STAGES[0].drills[0].exercise_id)
        self.jp.mark_drill_finished(STAGES[1].drills[0].exercise_id)
        self.assertTrue(self.jp.stage_unlocked(STAGES, 3))

    def test_stage_with_no_drills_is_trivially_satisfied(self):
        self.assertTrue(self.jp.stage_satisfied(STAGES[-1]))

    def test_explicit_stage_completion_also_satisfies(self):
        s1 = STAGES[0]
        self.jp.mark_stage_completed(s1.stage_id, "2026-07-06T10:00:00")
        self.assertTrue(self.jp.stage_satisfied(s1))
        self.assertTrue(self.jp.stage_completed(s1.stage_id))

    def test_resume_lands_on_last_stage_when_everything_done(self):
        for s in STAGES:
            for d in s.drills:
                self.jp.mark_drill_finished(d.exercise_id)
        self.assertEqual(self.jp.resume_stage_index(STAGES), len(STAGES) - 1)

    def test_progress_persists_across_reload(self):
        s1 = STAGES[0]
        self.jp.mark_stage_started(s1.stage_id, "2026-07-06T09:00:00")
        self.jp.mark_drill_finished(s1.drills[0].exercise_id,
                                    "2026-07-06T10:00:00")
        self.jp.mark_node_lit("fnet:deg:C:0", "2026-07-06T10:00:01")
        again = self._reload()
        self.assertTrue(again.drill_finished(s1.drills[0].exercise_id))
        self.assertTrue(again.stage_satisfied(s1))
        self.assertEqual(again.lit_node_ids(), ["fnet:deg:C:0"])

    def test_lit_nodes_ignore_stage_and_drill_records(self):
        self.jp.mark_stage_completed("meet_the_scale")
        self.jp.mark_drill_finished("some_drill")
        self.jp.mark_node_lit("fnet:deg:G:4")
        # namespace guards: stage/drill prefixed ids never count as lit nodes,
        # and mark_node_lit refuses non-network ids outright.
        self.jp.mark_node_lit(STAGE_PREFIX + "bogus")
        self.jp.mark_node_lit(DRILL_PREFIX + "bogus")
        self.jp.mark_node_lit("hn:major:C")
        self.assertEqual(self.jp.lit_node_ids(), ["fnet:deg:G:4"])

    def test_node_lit_is_idempotent(self):
        self.jp.mark_node_lit("fnet:deg:C:0")
        attempts = self.jp.store.progress["fnet:deg:C:0"].attempts
        self.jp.mark_node_lit("fnet:deg:C:0")
        self.assertEqual(self.jp.store.progress["fnet:deg:C:0"].attempts,
                         attempts)

    def test_corrupt_store_degrades_to_empty(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        again = self._reload()
        self.assertEqual(again.lit_node_ids(), [])
        self.assertEqual(again.resume_stage_index(STAGES), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
