"""Tests for the unified progress service (harmony.progress_service).

Ticket 08 (U3): one service owns BOTH progress files — the curriculum's
leaf records and the functional journey's stage/drill/lit records — and is
the only reader/writer; the existing stores route through it.  On top of the
merged view it builds the dashboard payload: the full-leaf mastery heatmap,
the SM-2-lite "due today" strip, streaks, and the journey summary.

Headless + deterministic: temp files for both stores, test-supplied clock.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harmony.curriculum import get_curriculum  # noqa: E402
from harmony.curriculum_progress import (  # noqa: E402
    ProgressStore, record_attempt,
)
from harmony.functional_journey import JourneyProgress  # noqa: E402
from harmony.progress_service import (  # noqa: E402
    DASHBOARD_SCHEMA_VERSION, ProgressService, dashboard_payload,
)


NOW = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class ServiceRoutingTest(unittest.TestCase):
    """The service is the single reader/writer over both existing stores."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.cur_path = Path(self.dir.name) / "curriculum.json"
        self.jou_path = Path(self.dir.name) / "journey.json"
        self.svc = ProgressService(self.cur_path, self.jou_path)

    def tearDown(self):
        self.dir.cleanup()

    def test_curriculum_facade_matches_progress_store_api(self):
        """The lab host's call sites (load/record/started/payload/save/progress)
        all exist and behave like the raw store's."""
        leaf = get_curriculum().leaves()[0]
        self.svc.load()
        self.svc.started(leaf.id, _iso(NOW))
        self.assertEqual(self.svc.progress[leaf.id].state, "started")
        self.svc.record(leaf.id, accuracy=1.0, score=100.0,
                        timestamp=_iso(NOW))
        self.assertEqual(self.svc.progress[leaf.id].state, "completed")
        payload = self.svc.payload()
        self.assertIn("stats", payload)
        self.svc.save()
        # The write landed in the curriculum file only.
        raw = json.loads(self.cur_path.read_text(encoding="utf-8"))
        self.assertIn(leaf.id, raw["progress"])
        self.assertFalse(self.jou_path.exists())

    def test_state_transitions_unchanged(self):
        """Regression (ticket checkbox): routing through the service must not
        alter the leaf state machine — same result as a direct record_attempt."""
        direct = record_attempt(None, "ex:x", accuracy=1.0,
                                timestamp=_iso(NOW))
        direct = record_attempt(direct, "ex:x", accuracy=1.0,
                                timestamp=_iso(NOW))
        direct = record_attempt(direct, "ex:x", accuracy=1.0,
                                timestamp=_iso(NOW))
        via = None
        for _ in range(3):
            via = self.svc.record("ex:x", accuracy=1.0, timestamp=_iso(NOW))
        self.assertEqual(via.to_dict(), direct.to_dict())
        self.assertEqual(via.state, "mastered")

    def test_journey_routes_through_the_service(self):
        jp = self.svc.journey
        self.assertIsInstance(jp, JourneyProgress)
        jp.mark_drill_finished("some_drill", _iso(NOW))
        jp.mark_stage_completed("meet_the_scale", _iso(NOW))
        jp.mark_node_lit("fnet:deg:C:0", _iso(NOW))
        raw = json.loads(self.jou_path.read_text(encoding="utf-8"))
        self.assertIn("fnet:drill:some_drill", raw["progress"])
        self.assertIn("fnet:stage:meet_the_scale", raw["progress"])
        # ... and never leaks into the curriculum file.
        self.assertNotIn("fnet:drill:some_drill",
                         (json.loads(self.cur_path.read_text(encoding="utf-8"))
                          .get("progress", {})
                          if self.cur_path.exists() else {}))

    def test_reload_round_trip(self):
        leaf = get_curriculum().leaves()[0]
        self.svc.record(leaf.id, accuracy=1.0, timestamp=_iso(NOW))
        self.svc.save()
        self.svc.journey.mark_node_lit("fnet:deg:C:0", _iso(NOW))
        again = ProgressService(self.cur_path, self.jou_path)
        self.assertEqual(again.progress[leaf.id].state, "completed")
        self.assertEqual(again.journey.lit_node_ids(), ["fnet:deg:C:0"])

    def test_existing_store_files_are_adopted_unchanged(self):
        """Pre-service files (written by the old direct-store hosts) load as-is:
        merging behind the service must not require a migration."""
        store = ProgressStore(self.cur_path)
        store.record("ex:legacy", accuracy=1.0, timestamp=_iso(NOW))
        store.save()
        JourneyProgress(ProgressStore(self.jou_path)).mark_drill_finished(
            "legacy_drill", _iso(NOW))
        svc = ProgressService(self.cur_path, self.jou_path)
        self.assertEqual(svc.progress["ex:legacy"].state, "completed")
        self.assertTrue(svc.journey.drill_finished("legacy_drill"))


class DashboardPayloadTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.svc = ProgressService(Path(self.dir.name) / "c.json",
                                   Path(self.dir.name) / "j.json")
        self.root = get_curriculum()
        self.leaves = self.root.leaves()

    def tearDown(self):
        self.dir.cleanup()

    def test_heatmap_covers_every_leaf_grouped_by_category(self):
        payload = self.svc.dashboard_payload(NOW)
        self.assertEqual(payload["schema"], DASHBOARD_SCHEMA_VERSION)
        heatmap = payload["heatmap"]
        cat_ids = [c["id"] for c in heatmap["categories"]]
        self.assertEqual(
            cat_ids, [c.id for c in self.root.children if c.leaves()])
        total = sum(len(c["leaves"]) for c in heatmap["categories"])
        self.assertEqual(total, len(self.leaves))
        self.assertEqual(heatmap["totalLeaves"], len(self.leaves))
        cell = heatmap["categories"][0]["leaves"][0]
        for key in ("id", "title", "state", "attempts"):
            self.assertIn(key, cell)
        self.assertEqual(heatmap["counts"]["not_started"], len(self.leaves))

    def test_empty_categories_draw_no_heatmap_row(self):
        """Leafless / reserved categories (cat:intervals, cat:atlas, ...)
        would render as a header over an empty grid — they are skipped."""
        empty = [c.id for c in self.root.children if not c.leaves()]
        self.assertTrue(empty, "fixture assumes some empty categories exist")
        heatmap = self.svc.dashboard_payload(NOW)["heatmap"]
        rendered = {c["id"] for c in heatmap["categories"]}
        self.assertFalse(rendered.intersection(empty))

    def test_heatmap_reflects_recorded_states(self):
        a, b = self.leaves[0], self.leaves[1]
        self.svc.started(a.id, _iso(NOW))
        self.svc.record(b.id, accuracy=1.0, timestamp=_iso(NOW))
        heatmap = self.svc.dashboard_payload(NOW)["heatmap"]
        states = {cell["id"]: cell["state"]
                  for c in heatmap["categories"] for cell in c["leaves"]}
        self.assertEqual(states[a.id], "started")
        self.assertEqual(states[b.id], "completed")
        self.assertEqual(heatmap["counts"]["started"], 1)
        self.assertEqual(heatmap["counts"]["completed"], 1)

    def test_review_strip_and_reschedule(self):
        leaf = self.leaves[0]
        self.svc.record(leaf.id, accuracy=1.0,
                        timestamp=_iso(NOW - timedelta(days=10)))
        payload = self.svc.dashboard_payload(NOW)
        self.assertEqual(payload["review"]["dueCount"], 1)
        self.assertEqual(payload["review"]["due"][0]["nodeId"], leaf.id)
        # Completing it now reschedules it out of the strip.
        self.svc.record(leaf.id, accuracy=1.0, timestamp=_iso(NOW))
        payload = self.svc.dashboard_payload(NOW)
        self.assertEqual(payload["review"]["dueCount"], 0)

    def test_streak_merges_both_stores(self):
        """A journey-only practice day still counts toward the streak."""
        self.svc.record(self.leaves[0].id, accuracy=1.0, timestamp=_iso(NOW))
        self.svc.journey.mark_drill_finished(
            "d", _iso(NOW - timedelta(days=1)))
        streak = self.svc.dashboard_payload(NOW)["streak"]
        self.assertEqual(streak["current"], 2)
        self.assertTrue(streak["practicedToday"])

    def test_dashboard_sees_concurrent_journey_writes(self):
        """A Functional Network session writes the journey file while the Lab
        holds its own service: the Lab's next dashboard payload must see it
        (the service re-reads the journey store per payload)."""
        other = ProgressService(self.svc._store.path,
                                self.svc.journey.store.path)
        other.journey.mark_stage_completed("meet_the_scale", _iso(NOW))
        journey = self.svc.dashboard_payload(NOW)["journey"]
        self.assertEqual(journey["stagesCompleted"], 1)

    def test_journey_summary(self):
        self.svc.journey.mark_stage_completed("meet_the_scale", _iso(NOW))
        self.svc.journey.mark_drill_finished("d1", _iso(NOW))
        self.svc.journey.mark_node_lit("fnet:deg:C:0", _iso(NOW))
        journey = self.svc.dashboard_payload(NOW)["journey"]
        self.assertEqual(journey["stagesCompleted"], 1)
        self.assertEqual(journey["drillsFinished"], 1)
        self.assertEqual(journey["litNodes"], 1)
        self.assertGreaterEqual(journey["stagesTotal"], 7)

    def test_payload_is_json_serialisable(self):
        self.svc.record(self.leaves[0].id, accuracy=1.0, timestamp=_iso(NOW))
        payload = self.svc.dashboard_payload(NOW)
        json.dumps(payload)   # must not raise
        self.assertIn("overall", payload)
        self.assertIn("generatedAt", payload)

    def test_pure_function_matches_service_method(self):
        """dashboard_payload() the pure function == the service wrapper."""
        self.svc.record(self.leaves[0].id, accuracy=1.0,
                        timestamp=_iso(NOW - timedelta(days=10)))
        pure = dashboard_payload(
            self.svc.progress, self.svc.journey, self.root, NOW)
        self.assertEqual(pure, self.svc.dashboard_payload(NOW))


if __name__ == "__main__":
    unittest.main()
