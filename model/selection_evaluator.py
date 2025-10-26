from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterable, Set, Tuple, List


@dataclass
class SelectionEvaluator:
    """
    Holds the expected MIDI set for the current selection,
    and compares that against currently-held keys.
    """
    expected: Set[int] = field(default_factory=set)
    down_now: Set[int] = field(default_factory=set)

    def set_expected(self, midis: Iterable[int]):
        self.expected = {int(x) for x in midis}

    # Simple API for external selection logic:
    def select_measures(self, measures: Iterable[int], per_measure_map):
        mids: Set[int] = set()
        for m in measures:
            mids |= per_measure_map.get(int(m), set())
        self.set_expected(mids)

    def select_beats(self, beats: List[tuple[int, int]], per_beat_map):
        mids: Set[int] = set()
        for m, b in beats:
            mids |= per_beat_map.get((int(m), int(b)), set())
        self.set_expected(mids)

    def note_on(self, midi: int):
        self.down_now.add(int(midi))

    def note_off(self, midi: int):
        self.down_now.discard(int(midi))

    def status(self) -> Tuple[Set[int], Set[int]]:
        hits = self.expected & self.down_now
        misses = self.expected - hits
        return hits, misses
