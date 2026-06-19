"""Hierarchical progress tracking for the curriculum (pure model + JSON store).

The Music Theory Laboratory tracks practice progress against the curriculum
ontology (:mod:`harmony.curriculum`).  Each *exercise leaf* accumulates an
:class:`ExerciseProgress` record (state, attempts, best score, last played,
running average accuracy / timing); the tree rolls those up to per-group,
per-lesson, per-category and per-curriculum completion -- the hierarchical
progress panel the workspace shows.

Split of concerns:

* The **math is pure** (:func:`record_attempt`, :func:`aggregate`,
  :func:`progress_payload`): no clock, no filesystem -- the host passes the
  timestamp in, so the functions are deterministic and headlessly testable.
* The **store** (:class:`ProgressStore`) is the only impure part: it (de)serialises
  the progress map to a small JSON file the host owns.

State machine (per exercise leaf):

    not_started  --(any attempt)-->        started
    started      --(score >= pass)-->       completed
    completed    --(accuracy >= mastery &   mastered
                    attempts >= min)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, Optional

from harmony.curriculum import CurriculumNode, get_curriculum


SCHEMA_VERSION = "harmony-curriculum-progress/v1"

#: Default thresholds (0..1 for accuracy/timing; 0..100 for score).
PASS_SCORE = 80.0          # an attempt at/above this completes the exercise
MASTERY_ACCURACY = 0.95    # sustained accuracy for mastery
MASTERY_MIN_ATTEMPTS = 3   # ... over at least this many attempts

STATES = ["not_started", "started", "completed", "mastered"]


# ---------------------------------------------------------------------------
# Per-exercise record
# ---------------------------------------------------------------------------

@dataclass
class ExerciseProgress:
    """The accumulated practice record for one curriculum exercise leaf."""

    node_id: str
    state: str = "not_started"
    attempts: int = 0
    best_score: float = 0.0
    last_played: Optional[str] = None          # ISO-8601 string (host-supplied)
    avg_accuracy: float = 0.0                   # 0..1, running mean over attempts
    avg_timing: float = 0.0                     # 0..1, running mean over attempts
    completion: float = 0.0                     # 0..1 (1.0 once completed/mastered)

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "ExerciseProgress":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


def record_attempt(progress: Optional[ExerciseProgress], node_id: str, *,
                   accuracy: float, timing: float = 1.0, score: Optional[float] = None,
                   timestamp: Optional[str] = None,
                   pass_score: float = PASS_SCORE,
                   mastery_accuracy: float = MASTERY_ACCURACY,
                   mastery_min_attempts: int = MASTERY_MIN_ATTEMPTS,
                   ) -> ExerciseProgress:
    """Fold one attempt into ``progress`` (created if ``None``) and return it.

    ``accuracy`` / ``timing`` are 0..1; ``score`` defaults to ``accuracy*100``.
    Running means are updated incrementally so the record stays O(1) in storage.
    Pure: the caller supplies ``timestamp`` (no clock here).
    """
    p = progress or ExerciseProgress(node_id=node_id)
    accuracy = _clamp01(accuracy)
    timing = _clamp01(timing)
    if score is None:
        score = accuracy * 100.0

    n = p.attempts
    p.avg_accuracy = (p.avg_accuracy * n + accuracy) / (n + 1)
    p.avg_timing = (p.avg_timing * n + timing) / (n + 1)
    p.attempts = n + 1
    p.best_score = max(p.best_score, float(score))
    if timestamp is not None:
        p.last_played = timestamp

    # state transitions (monotonic — never regress below a reached milestone)
    reached = max(STATES.index(p.state), STATES.index("started"))
    if p.best_score >= pass_score:
        reached = max(reached, STATES.index("completed"))
    if (p.best_score >= pass_score and p.avg_accuracy >= mastery_accuracy
            and p.attempts >= mastery_min_attempts):
        reached = max(reached, STATES.index("mastered"))
    p.state = STATES[reached]
    p.completion = 1.0 if reached >= STATES.index("completed") else 0.0
    return p


def mark_started(progress: Optional[ExerciseProgress], node_id: str,
                 timestamp: Optional[str] = None) -> ExerciseProgress:
    """Mark an exercise as launched/started without recording an attempt result."""
    p = progress or ExerciseProgress(node_id=node_id)
    if p.state == "not_started":
        p.state = "started"
    if timestamp is not None:
        p.last_played = timestamp
    return p


def _clamp01(x: float) -> float:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if x < 0 else 1.0 if x > 1 else x


# ---------------------------------------------------------------------------
# Aggregation (roll the leaf records up the tree)
# ---------------------------------------------------------------------------

def aggregate(node: CurriculumNode,
              progress: Dict[str, ExerciseProgress]) -> Dict:
    """Roll up ``progress`` (keyed by leaf node id) under ``node``.

    Returns ``{nodeId: stats}`` for ``node`` and every descendant, where stats =
    counts per state, attempts, best/avg metrics over *played* leaves, and a
    completion percentage (completed-or-mastered leaves / total leaves).
    """
    out: Dict[str, Dict] = {}
    _aggregate_into(node, progress, out)
    return out


def _aggregate_into(node: CurriculumNode, progress, out) -> Dict:
    if node.kind == "exercise":
        p = progress.get(node.id)
        stats = _leaf_stats(node, p)
        out[node.id] = stats
        return stats

    counts = {s: 0 for s in STATES}
    total = 0
    attempts = 0
    best_sum = 0.0
    acc_sum = 0.0
    timing_sum = 0.0
    played = 0
    last_played: Optional[str] = None

    for c in node.children:
        cs = _aggregate_into(c, progress, out)
        if c.kind == "exercise":
            total += 1
            counts[cs["state"]] += 1
            attempts += cs["attempts"]
            best_sum += cs["bestScore"]
            if cs["attempts"] > 0:
                played += 1
                acc_sum += cs["avgAccuracy"]
                timing_sum += cs["avgTiming"]
            last_played = _max_ts(last_played, cs["lastPlayed"])
        else:
            total += cs["total"]
            for s in STATES:
                counts[s] += cs["counts"][s]
            attempts += cs["attempts"]
            best_sum += cs["bestScore"] * cs["total"]
            played += cs["played"]
            acc_sum += cs["avgAccuracy"] * cs["played"]
            timing_sum += cs["avgTiming"] * cs["played"]
            last_played = _max_ts(last_played, cs["lastPlayed"])

    done = counts["completed"] + counts["mastered"]
    stats = {
        "id": node.id,
        "kind": node.kind,
        "total": total,
        "counts": counts,
        "completed": done,
        "started": counts["started"],
        "notStarted": counts["not_started"],
        "mastered": counts["mastered"],
        "attempts": attempts,
        "played": played,
        "bestScore": round(best_sum / total, 2) if total else 0.0,
        "avgAccuracy": round(acc_sum / played, 4) if played else 0.0,
        "avgTiming": round(timing_sum / played, 4) if played else 0.0,
        "percent": round(100.0 * done / total, 1) if total else 0.0,
        "lastPlayed": last_played,
        # representative state for the container (worst-of completed→not_started)
        "state": _container_state(counts, total),
    }
    out[node.id] = stats
    return stats


def _leaf_stats(node: CurriculumNode, p: Optional[ExerciseProgress]) -> Dict:
    if p is None:
        return {"id": node.id, "kind": "exercise", "state": "not_started",
                "attempts": 0, "bestScore": 0.0, "avgAccuracy": 0.0,
                "avgTiming": 0.0, "completion": 0.0, "lastPlayed": None,
                "percent": 0.0}
    return {"id": node.id, "kind": "exercise", "state": p.state,
            "attempts": p.attempts, "bestScore": round(p.best_score, 2),
            "avgAccuracy": round(p.avg_accuracy, 4),
            "avgTiming": round(p.avg_timing, 4),
            "completion": p.completion, "lastPlayed": p.last_played,
            "percent": round(p.completion * 100.0, 1)}


def _container_state(counts: Dict[str, int], total: int) -> str:
    if total == 0:
        return "not_started"
    if counts["mastered"] == total:
        return "mastered"
    if counts["completed"] + counts["mastered"] == total:
        return "completed"
    if counts["not_started"] == total:
        return "not_started"
    return "started"


def _max_ts(a: Optional[str], b: Optional[str]) -> Optional[str]:
    if a is None:
        return b
    if b is None:
        return a
    return a if a >= b else b   # ISO-8601 strings sort chronologically


def progress_payload(progress: Dict[str, ExerciseProgress],
                     root: Optional[CurriculumNode] = None) -> Dict:
    """JSON payload for the hierarchical progress panel."""
    root = root or get_curriculum()
    stats = aggregate(root, progress)
    return {
        "schema": SCHEMA_VERSION,
        "stats": stats,
        "overall": stats.get(root.id, {}),
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

class ProgressStore:
    """A tiny JSON-file store for the per-exercise progress map (the impure edge)."""

    def __init__(self, path) -> None:
        self.path = Path(path)
        self.progress: Dict[str, ExerciseProgress] = {}

    def load(self) -> Dict[str, ExerciseProgress]:
        self.progress = {}
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                for nid, d in (raw.get("progress") or {}).items():
                    self.progress[nid] = ExerciseProgress.from_dict(d)
            except Exception:
                self.progress = {}
        return self.progress

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": SCHEMA_VERSION,
            "progress": {nid: p.to_dict() for nid, p in self.progress.items()},
        }
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                             encoding="utf-8")

    # -- convenience pass-throughs (the host calls these) ----------------
    def record(self, node_id: str, *, accuracy: float, timing: float = 1.0,
               score: Optional[float] = None,
               timestamp: Optional[str] = None) -> ExerciseProgress:
        p = record_attempt(self.progress.get(node_id), node_id,
                           accuracy=accuracy, timing=timing, score=score,
                           timestamp=timestamp)
        self.progress[node_id] = p
        return p

    def started(self, node_id: str, timestamp: Optional[str] = None) -> ExerciseProgress:
        p = mark_started(self.progress.get(node_id), node_id, timestamp)
        self.progress[node_id] = p
        return p

    def payload(self, root: Optional[CurriculumNode] = None) -> Dict:
        return progress_payload(self.progress, root)
