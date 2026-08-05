"""SM-2-lite review scheduling over the persisted progress records (ticket 08).

The curriculum already persists everything a light spaced-repetition scheduler
needs per exercise leaf (:class:`harmony.curriculum_progress.ExerciseProgress`:
``state``, ``attempts``, ``avg_accuracy``, ``last_played``) — this module adds
**no stored fields**.  It derives, purely:

* an SM-2-lite review interval: a per-state base
  (:data:`BASE_INTERVAL_DAYS`) grown geometrically by an ease factor
  (1.3..2.5, mapped from the running accuracy — SuperMemo-2's ease bounds)
  per repetition, capped at :data:`MAX_INTERVAL_DAYS`;
* a due date (``last_played + interval``) and a "due today" queue that
  *interleaves* top-level curriculum categories (didactic principle 4:
  interleaving beats blocking) rather than draining one category first;
* practice streaks over the union of last-played dates.

Rescheduling is implicit: recording an attempt moves ``last_played`` (and
grows ``attempts``), so a completed review item schedules itself further out
— no queue state is stored anywhere.

Everything here is pure: the caller supplies ``now`` (tz-aware datetimes;
naive stored timestamps are read as UTC, matching the hosts' writers).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

from harmony.curriculum import CurriculumNode
from harmony.curriculum_progress import ExerciseProgress

SCHEMA_VERSION = "harmony-review-queue/v1"

#: Review interval bases (days) per leaf state.  A leaf that was merely
#: started needs to come back tomorrow; a mastered one can rest a week.
BASE_INTERVAL_DAYS = {"started": 1.0, "completed": 3.0, "mastered": 7.0}

#: SM-2 ease-factor bounds; the running accuracy interpolates between them.
MIN_EASE = 1.3
MAX_EASE = 2.5

MAX_INTERVAL_DAYS = 60.0
DEFAULT_QUEUE_LIMIT = 10


# ---------------------------------------------------------------------------
# Interval / due-date math (per record)
# ---------------------------------------------------------------------------

def ease_factor(avg_accuracy: float) -> float:
    """Map running accuracy 0..1 onto SM-2's ease bounds (clamping garbage)."""
    try:
        a = float(avg_accuracy)
    except (TypeError, ValueError):
        a = 0.0
    a = 0.0 if a < 0.0 else 1.0 if a > 1.0 else a
    return MIN_EASE + (MAX_EASE - MIN_EASE) * a


def interval_days(record: ExerciseProgress) -> Optional[float]:
    """The review interval for ``record``, or ``None`` if it is unscheduled
    (never practised: no state beyond ``not_started``)."""
    base = BASE_INTERVAL_DAYS.get(record.state)
    if base is None:
        return None
    reps = max(0, record.attempts - 1)
    return min(MAX_INTERVAL_DAYS, base * ease_factor(record.avg_accuracy) ** reps)


def due_at(record: ExerciseProgress) -> Optional[datetime]:
    """When ``record`` comes due (UTC), or ``None`` if unschedulable."""
    days = interval_days(record)
    played = _parse_ts(record.last_played)
    if days is None or played is None:
        return None
    return played + timedelta(days=days)


def _parse_ts(ts: Optional[str]) -> Optional[datetime]:
    """ISO-8601 -> tz-aware datetime (naive read as UTC); garbage -> None."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _as_utc(now: datetime) -> datetime:
    return now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# The due-today queue (interleaved across categories)
# ---------------------------------------------------------------------------

def build_review_queue(progress: Dict[str, ExerciseProgress],
                       root: CurriculumNode, now: datetime,
                       limit: int = DEFAULT_QUEUE_LIMIT) -> Dict:
    """The "due today" strip: every due leaf, interleaved across categories.

    Within a category items run most-overdue first; the queue then
    round-robins the categories (ordered by their most overdue item) so a
    session mixes qualities/degrees/cadences instead of blocking on one
    topic.  ``limit`` truncates the strip; ``dueCount`` always reports the
    full total.  Non-leaf ids in ``progress`` (journey stages, lit nodes)
    are simply not in the curriculum and are ignored.
    """
    now = _as_utc(now)
    by_category: Dict[str, List[Dict]] = {}
    for category in root.children:
        due: List[Dict] = []
        for leaf in category.leaves():
            record = progress.get(leaf.id)
            if record is None:
                continue
            due_ts = due_at(record)
            if due_ts is None or due_ts > now:
                continue
            overdue = (now - due_ts) / timedelta(days=1)
            due.append({
                "nodeId": leaf.id,
                "title": leaf.title,
                "categoryId": category.id,
                "category": category.title,
                "state": record.state,
                "lastPlayed": record.last_played,
                "intervalDays": round(interval_days(record), 2),
                "dueAt": due_ts.isoformat(),
                "overdueDays": round(overdue, 2),
            })
        if due:
            due.sort(key=lambda item: -item["overdueDays"])
            by_category[category.id] = due

    # Round-robin the categories, most-overdue category first.
    order = sorted(by_category,
                   key=lambda cid: -by_category[cid][0]["overdueDays"])
    interleaved: List[Dict] = []
    rank = 0
    while True:
        row = [by_category[cid][rank] for cid in order
               if rank < len(by_category[cid])]
        if not row:
            break
        interleaved.extend(row)
        rank += 1

    return {
        "schema": SCHEMA_VERSION,
        "generatedAt": now.isoformat(),
        "due": interleaved[:limit],
        "dueCount": len(interleaved),
    }


# ---------------------------------------------------------------------------
# Streaks (over the union of last-played dates)
# ---------------------------------------------------------------------------

def streaks(timestamps: Iterable[Optional[str]], now: datetime) -> Dict:
    """Practice streaks from last-played timestamps (any store's).

    ``current`` counts consecutive practice days ending today *or yesterday*
    (a streak survives until a full day is missed); ``best`` is the longest
    run ever visible in the data.  Only last-played survives per leaf, so
    old days a leaf was later replayed off of are forgotten — v0 accepts
    that (the plan's "SM-2-lite over already-persisted data").
    """
    now = _as_utc(now)
    days = sorted({ts.date() for ts in map(_parse_ts, timestamps) if ts})
    best = run = 0
    prev = None
    for day in days:
        run = run + 1 if prev is not None and day == prev + timedelta(days=1) \
            else 1
        best = max(best, run)
        prev = day
    today = now.date()
    current = 0
    if days and days[-1] >= today - timedelta(days=1):
        current = 1
        for earlier, later in zip(reversed(days[:-1]), reversed(days)):
            if later - earlier != timedelta(days=1):
                break
            current += 1
    return {
        "current": current,
        "best": best,
        "practicedToday": bool(days) and days[-1] == today,
    }
