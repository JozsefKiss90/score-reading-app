"""Unified progress service — the one reader/writer for practice state (U3).

Two progress files exist today and stay exactly as they are on disk:

* ``.curriculum_progress.json`` — per-leaf
  :class:`~harmony.curriculum_progress.ExerciseProgress` records (the Lab
  workspace's store);
* ``.functional_network_progress.json`` — the functional journey's stage /
  drill / lit-node records (via
  :class:`~harmony.functional_journey.JourneyProgress`).

:class:`ProgressService` owns *both*: it is the only component that
constructs the underlying stores, exposes the curriculum store's exact API
(``load/save/record/started/payload/progress``) so the Lab host routes
through it unchanged, and hands out the journey wrapper (``.journey``) so
the Functional Network host does too.  No migration: the service adopts the
existing files as-is.

On top of the merged view it derives (purely — the host supplies the clock):

* the SM-2-lite review queue (:mod:`harmony.review_queue`);
* practice streaks over the union of both stores' last-played dates;
* :func:`dashboard_payload` — the home-dashboard JSON: the full-leaf
  mastery heatmap, the "due today" strip, streaks, journey summary and the
  overall curriculum roll-up.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

from harmony.curriculum import CurriculumNode, get_curriculum
from harmony.curriculum_progress import ExerciseProgress, ProgressStore, aggregate
from harmony.functional_journey import (
    DEFAULT_PROGRESS_FILENAME, DRILL_PREFIX, STAGE_PREFIX, JourneyProgress,
    journey_stages,
)
from harmony.functional_network import build_functional_network
from harmony.functional_network_template import get_template
from harmony.review_queue import (
    DEFAULT_QUEUE_LIMIT, build_review_queue, due_at, streaks,
)

DASHBOARD_SCHEMA_VERSION = "harmony-dashboard/v1"

#: Default store locations, anchored at the project root (NOT the cwd) so
#: every host resolves the same files no matter where it is launched from.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CURRICULUM_PROGRESS_PATH = _PROJECT_ROOT / ".curriculum_progress.json"
DEFAULT_JOURNEY_PROGRESS_PATH = _PROJECT_ROOT / DEFAULT_PROGRESS_FILENAME

_DONE_STATES = ("completed", "mastered")


class ProgressService:
    """The single owner of both progress stores (curriculum + journey)."""

    def __init__(self,
                 curriculum_path=DEFAULT_CURRICULUM_PROGRESS_PATH,
                 journey_path=DEFAULT_JOURNEY_PROGRESS_PATH) -> None:
        self._store = ProgressStore(curriculum_path)
        self._store.load()
        self.journey = JourneyProgress(ProgressStore(journey_path))

    # -- curriculum store facade (the Lab host's exact call sites) --------
    @property
    def progress(self) -> Dict[str, ExerciseProgress]:
        return self._store.progress

    def load(self) -> Dict[str, ExerciseProgress]:
        return self._store.load()

    def save(self) -> None:
        self._store.save()

    def record(self, node_id: str, *, accuracy: float, timing: float = 1.0,
               score: Optional[float] = None,
               timestamp: Optional[str] = None) -> ExerciseProgress:
        return self._store.record(node_id, accuracy=accuracy, timing=timing,
                                  score=score, timestamp=timestamp)

    def started(self, node_id: str,
                timestamp: Optional[str] = None) -> ExerciseProgress:
        return self._store.started(node_id, timestamp)

    def payload(self, root: Optional[CurriculumNode] = None) -> Dict:
        return self._store.payload(root)

    # -- unified reads ----------------------------------------------------
    def review_queue(self, now: datetime,
                     root: Optional[CurriculumNode] = None,
                     limit: int = DEFAULT_QUEUE_LIMIT) -> Dict:
        return build_review_queue(self.progress, root or get_curriculum(),
                                  now, limit)

    def dashboard_payload(self, now: datetime,
                          root: Optional[CurriculumNode] = None) -> Dict:
        # Re-read the journey store first: journey mutations save immediately
        # (possibly from a concurrent Functional Network session), so a fresh
        # load keeps the Home tab's journey chips honest.
        self.journey.store.load()
        return dashboard_payload(self.progress, self.journey,
                                 root or get_curriculum(), now)


# ---------------------------------------------------------------------------
# The dashboard payload (pure)
# ---------------------------------------------------------------------------

def dashboard_payload(progress: Dict[str, ExerciseProgress],
                      journey: JourneyProgress, root: CurriculumNode,
                      now: datetime) -> Dict:
    """The home-dashboard JSON: heatmap + review strip + streaks + journey."""
    stats = aggregate(root, progress)
    overall = stats.get(root.id, {})
    categories = []
    for category in root.children:
        leaves = category.leaves()
        if not leaves:
            continue         # empty / reserved categories draw no heatmap row
        cells = []
        for leaf in leaves:
            record = progress.get(leaf.id)
            due = due_at(record) if record else None
            cells.append({
                "id": leaf.id,
                "title": leaf.title,
                "state": record.state if record else "not_started",
                "attempts": record.attempts if record else 0,
                "dueAt": due.isoformat() if due else None,
            })
        categories.append({
            "id": category.id,
            "label": category.title,
            "percent": stats.get(category.id, {}).get("percent", 0.0),
            "leaves": cells,
        })

    journey_records = journey.store.progress
    return {
        "schema": DASHBOARD_SCHEMA_VERSION,
        "generatedAt": now.isoformat(),
        "heatmap": {
            "categories": categories,
            "totalLeaves": overall.get("total", 0),
            "counts": overall.get("counts", {}),
        },
        "review": build_review_queue(progress, root, now),
        "streak": streaks(_all_last_played(progress, journey_records), now),
        "journey": {
            "stagesCompleted": _done_count(journey_records, STAGE_PREFIX),
            "stagesTotal": _stages_total(),
            "drillsFinished": _done_count(journey_records, DRILL_PREFIX),
            "litNodes": len(journey.lit_node_ids()),
        },
        "overall": overall,
    }


def _all_last_played(progress: Dict[str, ExerciseProgress],
                     journey_records: Dict[str, ExerciseProgress]):
    return [p.last_played
            for records in (progress, journey_records)
            for p in records.values() if p.last_played]


def _done_count(records: Dict[str, ExerciseProgress], prefix: str) -> int:
    return sum(1 for nid, p in records.items()
               if nid.startswith(prefix) and p.state in _DONE_STATES)


@lru_cache(maxsize=1)
def _stages_total() -> int:
    """How many journey stages exist (derived from the default network, so
    the count can never drift from the journey builder).  Cached: the
    network build is pure and the answer is a constant per template."""
    return len(journey_stages(build_functional_network(get_template())))
