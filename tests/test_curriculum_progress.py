"""Tests for hierarchical progress tracking (harmony.curriculum_progress).

Headless + deterministic (timestamps are supplied by the test, not a clock).
They enforce:

  * the per-exercise state machine (not_started -> started -> completed -> mastered);
  * running-mean accuracy / timing;
  * roll-up from leaves to group / lesson / category / curriculum;
  * a completion percentage that reflects completed-or-mastered leaves;
  * JSON round-tripping through the ProgressStore.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harmony.curriculum import get_curriculum  # noqa: E402
from harmony.curriculum_progress import (  # noqa: E402
    ExerciseProgress, record_attempt, mark_started, aggregate, progress_payload,
    ProgressStore, PASS_SCORE,
)


def _first_group(root):
    """A small group with a handful of exercise leaves, for roll-up tests."""
    for n in root.walk():
        if n.kind == "group" and 2 <= len(n.children) <= 6 \
                and all(c.kind == "exercise" for c in n.children):
            return n
    raise AssertionError("no small group found")


class TestStateMachine(unittest.TestCase):
    def test_not_started_to_started(self):
        p = mark_started(None, "ex:x", timestamp="2026-01-01T00:00:00")
        self.assertEqual(p.state, "started")
        self.assertEqual(p.attempts, 0)
        self.assertEqual(p.last_played, "2026-01-01T00:00:00")

    def test_attempt_completes_when_passing(self):
        p = record_attempt(None, "ex:x", accuracy=0.9, timing=0.8, score=90)
        self.assertEqual(p.state, "completed")
        self.assertEqual(p.attempts, 1)
        self.assertEqual(p.best_score, 90)
        self.assertEqual(p.completion, 1.0)

    def test_low_score_is_started_not_completed(self):
        p = record_attempt(None, "ex:x", accuracy=0.4, score=40)
        self.assertEqual(p.state, "started")
        self.assertEqual(p.completion, 0.0)

    def test_mastery_requires_sustained_accuracy(self):
        p = None
        for _ in range(3):
            p = record_attempt(p, "ex:x", accuracy=0.98, score=98)
        self.assertEqual(p.state, "mastered")
        self.assertEqual(p.attempts, 3)

    def test_state_never_regresses(self):
        p = record_attempt(None, "ex:x", accuracy=1.0, score=100)
        self.assertEqual(p.state, "completed")
        p = record_attempt(p, "ex:x", accuracy=0.1, score=10)   # a bad attempt
        self.assertEqual(p.state, "completed")                  # stays completed
        self.assertEqual(p.best_score, 100)

    def test_running_means(self):
        p = record_attempt(None, "ex:x", accuracy=0.6, timing=0.5)
        p = record_attempt(p, "ex:x", accuracy=1.0, timing=1.0)
        self.assertAlmostEqual(p.avg_accuracy, 0.8)
        self.assertAlmostEqual(p.avg_timing, 0.75)

    def test_clamps_out_of_range(self):
        p = record_attempt(None, "ex:x", accuracy=1.5, timing=-0.2)
        self.assertEqual(p.avg_accuracy, 1.0)
        self.assertEqual(p.avg_timing, 0.0)


class TestAggregation(unittest.TestCase):
    def setUp(self):
        self.root = get_curriculum()
        self.group = _first_group(self.root)
        self.leaves = self.group.children

    def test_empty_progress_all_not_started(self):
        stats = aggregate(self.root, {})
        root_stats = stats[self.root.id]
        self.assertEqual(root_stats["total"], len(self.root.leaves()))
        self.assertEqual(root_stats["percent"], 0.0)
        self.assertEqual(root_stats["completed"], 0)
        self.assertEqual(root_stats["state"], "not_started")

    def test_partial_completion_percent(self):
        progress = {}
        # complete the first leaf of the group only
        first = self.leaves[0]
        progress[first.id] = record_attempt(None, first.id, accuracy=1.0, score=100)
        stats = aggregate(self.root, progress)
        g = stats[self.group.id]
        self.assertEqual(g["completed"], 1)
        self.assertEqual(g["total"], len(self.leaves))
        self.assertAlmostEqual(g["percent"], round(100.0 / len(self.leaves), 1))
        self.assertEqual(g["state"], "started")

    def test_full_group_completion(self):
        progress = {lf.id: record_attempt(None, lf.id, accuracy=1.0, score=100)
                    for lf in self.leaves}
        stats = aggregate(self.root, progress)
        self.assertEqual(stats[self.group.id]["percent"], 100.0)
        self.assertEqual(stats[self.group.id]["state"], "completed")

    def test_avg_metrics_over_played_only(self):
        progress = {}
        a, b = self.leaves[0], self.leaves[1]
        progress[a.id] = record_attempt(None, a.id, accuracy=0.8, timing=0.6, score=80)
        progress[b.id] = record_attempt(None, b.id, accuracy=1.0, timing=1.0, score=100)
        stats = aggregate(self.group, progress)
        g = stats[self.group.id]
        self.assertEqual(g["played"], 2)
        self.assertAlmostEqual(g["avgAccuracy"], 0.9)
        self.assertAlmostEqual(g["avgTiming"], 0.8)

    def test_last_played_is_max_timestamp(self):
        progress = {}
        a, b = self.leaves[0], self.leaves[1]
        progress[a.id] = record_attempt(None, a.id, accuracy=1.0, score=100,
                                        timestamp="2026-01-01T00:00:00")
        progress[b.id] = record_attempt(None, b.id, accuracy=1.0, score=100,
                                        timestamp="2026-06-01T00:00:00")
        stats = aggregate(self.group, progress)
        self.assertEqual(stats[self.group.id]["lastPlayed"], "2026-06-01T00:00:00")

    def test_payload_overall(self):
        payload = progress_payload({}, self.root)
        self.assertIn("overall", payload)
        self.assertEqual(payload["overall"]["id"], self.root.id)


class TestStore(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "progress.json")
            store = ProgressStore(path)
            store.record("ex:a", accuracy=1.0, score=100,
                         timestamp="2026-01-01T00:00:00")
            store.started("ex:b")
            store.save()

            reloaded = ProgressStore(path)
            reloaded.load()
            self.assertEqual(reloaded.progress["ex:a"].state, "completed")
            self.assertEqual(reloaded.progress["ex:a"].best_score, 100)
            self.assertEqual(reloaded.progress["ex:b"].state, "started")

    def test_missing_file_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            store = ProgressStore(os.path.join(d, "nope.json"))
            self.assertEqual(store.load(), {})

    def test_corrupt_file_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "bad.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("{not json")
            store = ProgressStore(path)
            self.assertEqual(store.load(), {})

    def test_exercise_progress_dict_round_trip(self):
        p = record_attempt(None, "ex:x", accuracy=0.9, score=90)
        again = ExerciseProgress.from_dict(p.to_dict())
        self.assertEqual(again.state, p.state)
        self.assertEqual(again.best_score, p.best_score)


if __name__ == "__main__":
    unittest.main(verbosity=2)
