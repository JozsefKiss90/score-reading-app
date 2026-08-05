"""Tests for the SM-2-lite review scheduler (harmony.review_queue).

Headless + deterministic: the clock is always supplied by the test.  They
enforce the ticket-08 contract:

  * an SM-2-lite interval derived ONLY from already-persisted fields
    (state, attempts, avg_accuracy, last_played) — no new stored fields;
  * "due" means last_played + interval <= now; unplayed leaves are never due;
  * completing (re-recording) an item moves last_played forward, so the item
    reschedules itself out of the queue;
  * the due-today queue interleaves top-level curriculum categories
    (didactic principle: interleaving over blocking) and respects the limit;
  * practice streaks over the union of last-played dates.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harmony.curriculum import get_curriculum  # noqa: E402
from harmony.curriculum_progress import (  # noqa: E402
    ExerciseProgress, record_attempt,
)
from harmony.review_queue import (  # noqa: E402
    BASE_INTERVAL_DAYS, MAX_INTERVAL_DAYS, SCHEMA_VERSION,
    build_review_queue, due_at, ease_factor, interval_days, streaks,
)


NOW = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _record(state="completed", attempts=1, avg_accuracy=1.0,
            last_played=None, node_id="ex:x") -> ExerciseProgress:
    return ExerciseProgress(node_id=node_id, state=state, attempts=attempts,
                            avg_accuracy=avg_accuracy,
                            last_played=last_played)


class IntervalTest(unittest.TestCase):
    def test_unplayed_records_have_no_interval(self):
        self.assertIsNone(interval_days(_record(state="not_started",
                                                attempts=0)))
        # A record with attempts but no timestamp cannot be scheduled either.
        self.assertIsNone(due_at(_record(last_played=None)))

    def test_base_intervals_by_state(self):
        for state, base in BASE_INTERVAL_DAYS.items():
            rec = _record(state=state, attempts=1, avg_accuracy=0.0,
                          last_played=_iso(NOW))
            self.assertEqual(interval_days(rec), base,
                             f"single-attempt {state} should sit at its base")

    def test_interval_grows_with_attempts_and_accuracy(self):
        lo = interval_days(_record(attempts=3, avg_accuracy=0.5,
                                   last_played=_iso(NOW)))
        hi = interval_days(_record(attempts=3, avg_accuracy=1.0,
                                   last_played=_iso(NOW)))
        more = interval_days(_record(attempts=6, avg_accuracy=1.0,
                                     last_played=_iso(NOW)))
        self.assertGreater(hi, lo)
        self.assertGreater(more, hi)

    def test_interval_is_capped(self):
        rec = _record(state="mastered", attempts=50, avg_accuracy=1.0,
                      last_played=_iso(NOW))
        self.assertEqual(interval_days(rec), MAX_INTERVAL_DAYS)

    def test_ease_factor_bounds(self):
        self.assertAlmostEqual(ease_factor(0.0), 1.3)
        self.assertAlmostEqual(ease_factor(1.0), 2.5)
        # Garbage clamps rather than raises (records come from a JSON file).
        self.assertAlmostEqual(ease_factor(7.5), 2.5)

    def test_due_at_and_overdue(self):
        played = NOW - timedelta(days=5)
        rec = _record(state="completed", attempts=1, avg_accuracy=0.0,
                      last_played=_iso(played))
        due = due_at(rec)
        self.assertEqual(due, played + timedelta(days=3))
        self.assertLess(due, NOW)          # 5 days ago + 3-day interval: due

    def test_naive_timestamps_are_treated_as_utc(self):
        rec = _record(last_played=NOW.replace(tzinfo=None).isoformat())
        self.assertEqual(due_at(rec).tzinfo, timezone.utc)


class QueueTest(unittest.TestCase):
    def setUp(self):
        self.root = get_curriculum()
        self.leaves = self.root.leaves()

    def _leaf_in(self, cat_id, offset=0):
        cat = next(c for c in self.root.children if c.id == cat_id)
        return cat.leaves()[offset]

    def test_empty_progress_yields_empty_queue(self):
        q = build_review_queue({}, self.root, NOW)
        self.assertEqual(q["schema"], SCHEMA_VERSION)
        self.assertEqual(q["due"], [])
        self.assertEqual(q["dueCount"], 0)

    def test_due_item_carries_schedule_fields(self):
        leaf = self.leaves[0]
        played = NOW - timedelta(days=10)
        progress = {leaf.id: _record(node_id=leaf.id,
                                     last_played=_iso(played))}
        q = build_review_queue(progress, self.root, NOW)
        self.assertEqual(q["dueCount"], 1)
        item = q["due"][0]
        self.assertEqual(item["nodeId"], leaf.id)
        self.assertEqual(item["title"], leaf.title)
        self.assertEqual(item["categoryId"], "cat:scales")
        self.assertEqual(item["state"], "completed")
        self.assertGreater(item["overdueDays"], 6.9)
        self.assertIn("dueAt", item)
        self.assertIn("intervalDays", item)

    def test_future_items_are_not_due(self):
        leaf = self.leaves[0]
        progress = {leaf.id: _record(node_id=leaf.id, state="mastered",
                                     attempts=5, avg_accuracy=1.0,
                                     last_played=_iso(NOW))}
        q = build_review_queue(progress, self.root, NOW)
        self.assertEqual(q["dueCount"], 0)

    def test_completing_an_item_reschedules_it(self):
        """The ticket's core loop: due -> record attempt now -> no longer due."""
        leaf = self.leaves[0]
        played = NOW - timedelta(days=10)
        rec = record_attempt(None, leaf.id, accuracy=1.0,
                             timestamp=_iso(played))
        progress = {leaf.id: rec}
        self.assertEqual(
            build_review_queue(progress, self.root, NOW)["dueCount"], 1)
        record_attempt(rec, leaf.id, accuracy=1.0, timestamp=_iso(NOW))
        self.assertEqual(
            build_review_queue(progress, self.root, NOW)["dueCount"], 0)

    def test_queue_interleaves_categories(self):
        """Two due items per category must alternate, not block."""
        a1 = self._leaf_in("cat:scales", 0)
        a2 = self._leaf_in("cat:scales", 1)
        b1 = self._leaf_in("cat:chords", 0)
        b2 = self._leaf_in("cat:chords", 1)
        played = _iso(NOW - timedelta(days=30))
        progress = {leaf.id: _record(node_id=leaf.id, last_played=played)
                    for leaf in (a1, a2, b1, b2)}
        q = build_review_queue(progress, self.root, NOW)
        cats = [item["categoryId"] for item in q["due"]]
        self.assertEqual(len(cats), 4)
        self.assertNotEqual(cats[0], cats[1],
                            "adjacent queue items should switch category")
        self.assertNotEqual(cats[2], cats[3])

    def test_most_overdue_first_within_a_category(self):
        older = self._leaf_in("cat:scales", 0)
        newer = self._leaf_in("cat:scales", 1)
        progress = {
            older.id: _record(node_id=older.id,
                              last_played=_iso(NOW - timedelta(days=30))),
            newer.id: _record(node_id=newer.id,
                              last_played=_iso(NOW - timedelta(days=5))),
        }
        q = build_review_queue(progress, self.root, NOW)
        self.assertEqual([i["nodeId"] for i in q["due"]],
                         [older.id, newer.id])

    def test_limit_is_respected(self):
        played = _iso(NOW - timedelta(days=30))
        progress = {leaf.id: _record(node_id=leaf.id, last_played=played)
                    for leaf in self.leaves[:20]}
        q = build_review_queue(progress, self.root, NOW, limit=5)
        self.assertEqual(len(q["due"]), 5)
        self.assertEqual(q["dueCount"], 20)   # the count reports ALL due items

    def test_unknown_node_ids_are_ignored(self):
        progress = {"fnet:stage:xyz": _record(
            node_id="fnet:stage:xyz",
            last_played=_iso(NOW - timedelta(days=30)))}
        q = build_review_queue(progress, self.root, NOW)
        self.assertEqual(q["dueCount"], 0)


class StreakTest(unittest.TestCase):
    def test_empty(self):
        s = streaks([], NOW)
        self.assertEqual(s, {"current": 0, "best": 0,
                             "practicedToday": False})

    def test_current_streak_ending_today(self):
        ts = [_iso(NOW - timedelta(days=d)) for d in (0, 1, 2)]
        s = streaks(ts, NOW)
        self.assertEqual(s["current"], 3)
        self.assertEqual(s["best"], 3)
        self.assertTrue(s["practicedToday"])

    def test_streak_alive_if_practiced_yesterday(self):
        ts = [_iso(NOW - timedelta(days=d)) for d in (1, 2)]
        s = streaks(ts, NOW)
        self.assertEqual(s["current"], 2)
        self.assertFalse(s["practicedToday"])

    def test_gap_breaks_current_but_not_best(self):
        ts = [_iso(NOW - timedelta(days=d)) for d in (0, 4, 5, 6, 7)]
        s = streaks(ts, NOW)
        self.assertEqual(s["current"], 1)
        self.assertEqual(s["best"], 4)

    def test_stale_practice_means_no_current_streak(self):
        ts = [_iso(NOW - timedelta(days=d)) for d in (3, 4)]
        s = streaks(ts, NOW)
        self.assertEqual(s["current"], 0)
        self.assertEqual(s["best"], 2)

    def test_duplicate_timestamps_one_day(self):
        ts = [_iso(NOW), _iso(NOW - timedelta(hours=1)), "not-a-date", None]
        s = streaks(ts, NOW)
        self.assertEqual(s["current"], 1)
        self.assertEqual(s["best"], 1)


if __name__ == "__main__":
    unittest.main()
