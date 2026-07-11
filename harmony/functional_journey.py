"""The staged journey (stage machine) for the Functional Degree Network.

Pure model + a thin persistence wrapper:

* :class:`JourneyStage` -- one guided stage: explanation, graph state
  (visible node ids / relations / emphasis), 1-2 launchable drills, and an
  unlock rule.
* :func:`journey_stages` -- builds the 7 stages *from a built network*, so
  node ids can never drift from the builder (unknown ids raise immediately).
* :class:`JourneyProgress` -- wraps
  :class:`harmony.curriculum_progress.ProgressStore` for per-stage
  started/completed records, per-drill finished records, and the set of
  permanently lit node ids.  The store file is
  ``.functional_network_progress.json`` (host-owned, like the curriculum's).
* :func:`drill_node_ids` -- which degree nodes a drill exercises (used by the
  host to light nodes when the trainer reports ``finished``).

Everything except the store is deterministic and headless (no clock: the host
passes timestamps in, mirroring :mod:`harmony.curriculum_progress`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from theory.diatonic_harmony import generate_diatonic_triads, parse_key
from harmony.exercise_spec import (
    HarmonyExerciseSpec,
    compile_exercise,
    MAX_CHORDS_PER_SPEC,
)
from harmony.atlas import full_key_spec, function_spec
from harmony.curriculum_progress import ProgressStore
from harmony.harmonic_network import HarmonicNetwork
from harmony.functional_network import (
    canonical_key,
    degree_node_id,
    function_node_id,
    key_node_id,
)
from harmony.functional_network_template import FUNCTION_GROUPS


#: Default progress file (project root, next to ``.curriculum_progress.json``).
DEFAULT_PROGRESS_FILENAME = ".functional_network_progress.json"

#: ProgressStore key prefixes.  Stage / drill records share the store with lit
#: *network node* records (``fnet:deg:...`` etc.); the prefixes keep the three
#: namespaces disjoint.
STAGE_PREFIX = "fnet:stage:"
DRILL_PREFIX = "fnet:drill:"

UNLOCK_RULES = ("finish_any", "finish_all")


# ---------------------------------------------------------------------------
# Stage model
# ---------------------------------------------------------------------------

@dataclass
class JourneyStage:
    """One guided stage: theory text + graph state + drills + unlock rule."""

    stage_id: str
    title: str
    explanation: str
    #: Node-id whitelist for ``setVisibleNodes`` (``None`` = no whitelist:
    #: everything is visible, as in the free-exploration stage).
    visible_node_ids: Optional[List[str]]
    #: Relations switched ON for this stage (all others are switched off).
    visible_relations: List[str]
    #: Nodes the stage focuses on; the host selects the first one so the
    #: right-hand JS panel shows the stage's focal theory.
    emphasis_node_ids: List[str]
    drills: List[HarmonyExerciseSpec] = field(default_factory=list)
    unlock: str = "finish_any"          # "finish_any" | "finish_all"

    def drill_ids(self) -> List[str]:
        return [d.exercise_id for d in self.drills]


def _slug(text: str) -> str:
    return text.replace("#", "s").replace("b", "f")


def _horizontal_v_spec(keys: List[str]) -> HarmonyExerciseSpec:
    """The stage-6 cross-key drill: the V triad across every journey key."""
    return HarmonyExerciseSpec(
        exercise_id=f"fnet_degree_V_{'_'.join(_slug(k) for k in keys)}",
        title=f"V across {', '.join(keys)} (major)",
        drill="horizontal_degree", render="block", mode="major",
        degree="V", keys=list(keys),
        description=(f"The dominant triad V transposed across "
                     f"{', '.join(keys)} — the same functional job in "
                     f"{len(keys)} different key{'s' if len(keys) != 1 else ''}."),
    )


def journey_stages(network: HarmonicNetwork) -> List[JourneyStage]:
    """The 7 guided stages, derived from ``network`` (ids can never drift).

    ``network`` must be a functional degree network
    (:func:`harmony.functional_network.build_functional_network`); every node
    id a stage references is checked against it and a missing id raises
    :class:`ValueError` immediately.
    """
    keys = [canonical_key(k) for k in network.template.journey_keys]
    if not keys:
        raise ValueError("network template has no journey keys")
    home = keys[0]                                   # the journey starts here
    second = keys[1] if len(keys) > 1 else home

    deg = lambda key, i: degree_node_id(key, i)      # noqa: E731
    fn = lambda key, g: function_node_id(key, g)     # noqa: E731

    home_degrees = [deg(home, i) for i in range(7)]
    home_functions = [fn(home, g) for g in FUNCTION_GROUPS]
    all_node_ids = [n.id for n in network.nodes]

    # For the stage-6 story, derive (from the engine, not a hardcoded claim)
    # which roman the home tonic triad plays inside the second journey key.
    home_tonic = generate_diatonic_triads(home, "major")[0]
    home_tonic_pcs = frozenset(home_tonic.pitch_classes)
    shared_roman = next(
        (t.roman for t in generate_diatonic_triads(second, "major")
         if frozenset(t.pitch_classes) == home_tonic_pcs), None)
    shared_example = (
        f" (the {home_tonic.chord_symbol} triad is I at home and "
        f"{shared_roman} in {second})" if shared_roman and second != home
        else "")

    stages = [
        JourneyStage(
            stage_id="meet_the_scale",
            title="Stage 1 — Meet the scale",
            explanation=(
                f"{home} major has seven diatonic triads, one built on each "
                f"scale degree. Right now they are seven unlit dots — play "
                f"the drill and watch each correct chord light its node for "
                f"good. Notice the layout is not scale order: chords sit "
                f"where they *work*, and the next stages reveal why."),
            visible_node_ids=list(home_degrees),
            visible_relations=[],
            emphasis_node_ids=[deg(home, 0)],
            drills=[full_key_spec(home, "major")],
            unlock="finish_any",
        ),
        JourneyStage(
            stage_id="three_jobs",
            title="Stage 2 — Three jobs",
            explanation=(
                "Every diatonic chord does one of three jobs: Tonic chords "
                "are home (I, with vi and iii as stand-ins), Predominant / "
                "Subdominant chords set up motion (ii, IV), and Dominant "
                "chords carry tension (V, vii°). The violet badges collect "
                "each family. Play I–IV–V–I and feel the full cycle: home → "
                "approach → tension → home."),
            visible_node_ids=home_degrees + home_functions,
            visible_relations=["function_member"],
            emphasis_node_ids=list(home_functions),
            drills=[function_spec(["I", "IV", "V", "I"], "I–IV–V–I",
                                  "major", [home])],
            unlock="finish_any",
        ),
        JourneyStage(
            stage_id="tension_home",
            title="Stage 3 — Tension → home",
            explanation=(
                f"Dominant chords contain the leading tone — a semitone "
                f"below the tonic — and that pull is what makes them resolve "
                f"to I. The red arrows show it: V → I is the authentic "
                f"resolution, and vii° → I is the same pull from a rootless "
                f"dominant. Play both resolutions in {home} major and watch "
                f"the arrows fire as you sit on the dominant."),
            visible_node_ids=home_degrees + home_functions,
            visible_relations=["function_member", "resolves_to"],
            emphasis_node_ids=[deg(home, 4), deg(home, 6)],
            drills=[
                function_spec(["V", "I"], "V–I", "major", [home]),
                function_spec(["vii°", "I"], "vii°–I", "major", [home]),
            ],
            unlock="finish_all",
        ),
        JourneyStage(
            stage_id="approach_chain",
            title="Stage 4 — The approach chain",
            explanation=(
                "Predominants exist to prepare the dominant: ii falls a "
                "fifth onto V (exactly the motion V makes onto I), and IV "
                "steps up to V. Chain them and you get one of the most "
                "common progressions in tonal music — ii–V–I. Play it and "
                "follow the arrows across the panel: approach, tension, "
                "home."),
            visible_node_ids=home_degrees + home_functions,
            visible_relations=["function_member", "resolves_to", "prepares"],
            emphasis_node_ids=[deg(home, 1), deg(home, 3)],
            drills=[function_spec(["ii", "V", "I"], "ii–V–I",
                                  "major", [home])],
            unlock="finish_any",
        ),
        JourneyStage(
            stage_id="substitutes",
            title="Stage 5 — Substitutes",
            explanation=(
                "vi and iii each share two chord tones with I, so they can "
                "stand in for home — that is why they orbit the tonic. The "
                "most famous use is the deceptive resolution V → vi: the ear "
                "expects home and lands on its substitute. iii is the "
                "ambiguous one (it also shares two tones with V). Play "
                "vi–ii–V–I to hear a substitute launch the whole cycle."),
            visible_node_ids=home_degrees + home_functions,
            visible_relations=["function_member", "resolves_to", "prepares",
                               "tonic_substitute", "deceptive_to"],
            emphasis_node_ids=[deg(home, 5), deg(home, 2)],
            drills=[function_spec(["vi", "ii", "V", "I"], "vi–ii–V–I",
                                  "major", [home])],
            unlock="finish_any",
        ),
        JourneyStage(
            stage_id="same_triad_new_key",
            title="Stage 6 — Same triad, new key",
            explanation=(
                f"Every journey key now has its panel — and grey links join "
                f"triads that are literally the same three notes doing "
                f"different jobs{shared_example}. Function is not a property "
                f"of a chord; it is a property of a chord *in a key*. Play V "
                f"across all {len(keys)} keys, then repeat ii–V–I in "
                f"{second} to feel a familiar cycle in a new home."),
            visible_node_ids=list(all_node_ids),
            visible_relations=["function_member", "resolves_to", "prepares",
                               "tonic_substitute", "deceptive_to",
                               "shared_triad", "fifth_relation"],
            emphasis_node_ids=[key_node_id(second), deg(second, 4)],
            drills=[
                _horizontal_v_spec(keys),
                function_spec(["ii", "V", "I"], "ii–V–I", "major", [second]),
            ],
            unlock="finish_all",
        ),
        JourneyStage(
            stage_id="free_exploration",
            title="Stage 7 — Free exploration",
            explanation=(
                "Everything is on the table: all keys, every relation, every "
                "drill. Click any node to launch its drill — a degree node "
                "pairs its chord with home (X–I; I plays the whole key), "
                "function badges drill their family, key hubs drill all "
                "seven triads. Toggle relations on the left to isolate one "
                "idea at a time. Nodes you light stay lit."),
            visible_node_ids=None,                    # no whitelist
            visible_relations=["function_member", "resolves_to", "prepares",
                               "tonic_substitute", "deceptive_to",
                               "shared_triad", "fifth_relation"],
            emphasis_node_ids=[key_node_id(home)],
            drills=[],
            unlock="finish_any",
        ),
    ]

    _validate_stages(stages, network)
    return stages


def _validate_stages(stages: List[JourneyStage],
                     network: HarmonicNetwork) -> None:
    """Every referenced node id / relation / unlock rule must exist."""
    known_ids = {n.id for n in network.nodes}
    implemented = set(network.template.implemented_relations())
    seen_stage_ids = set()
    for stage in stages:
        if stage.stage_id in seen_stage_ids:
            raise ValueError(f"duplicate stage id {stage.stage_id!r}")
        seen_stage_ids.add(stage.stage_id)
        if stage.unlock not in UNLOCK_RULES:
            raise ValueError(
                f"stage {stage.stage_id!r}: unknown unlock rule "
                f"{stage.unlock!r}; expected one of {UNLOCK_RULES}")
        for nid in (stage.visible_node_ids or []):
            if nid not in known_ids:
                raise ValueError(
                    f"stage {stage.stage_id!r} references unknown node {nid!r}")
        for nid in stage.emphasis_node_ids:
            if nid not in known_ids:
                raise ValueError(
                    f"stage {stage.stage_id!r} emphasises unknown node {nid!r}")
            if stage.visible_node_ids is not None and \
                    nid not in stage.visible_node_ids:
                raise ValueError(
                    f"stage {stage.stage_id!r} emphasises {nid!r} which its "
                    f"whitelist hides")
        for rel in stage.visible_relations:
            if rel not in implemented:
                raise ValueError(
                    f"stage {stage.stage_id!r} enables unknown/unimplemented "
                    f"relation {rel!r}")
        for spec in stage.drills:
            spec.validate()
            # The readability-cap invariant: every drill a stage can hand the
            # trainer must fit a single-page render. A long custom journey
            # (many keys) would otherwise push the stage-6 horizontal drill
            # past the cap silently.
            n = len(compile_exercise(spec))
            if n > MAX_CHORDS_PER_SPEC:
                raise ValueError(
                    f"stage {stage.stage_id!r}: drill {spec.exercise_id!r} "
                    f"compiles to {n} chords (> {MAX_CHORDS_PER_SPEC}); "
                    f"scope the journey smaller.")


# ---------------------------------------------------------------------------
# Drill -> exercised degree nodes (for lighting on `finished`)
# ---------------------------------------------------------------------------

def drill_node_ids(spec: HarmonyExerciseSpec) -> List[str]:
    """The ``fnet:deg:`` node ids a drill exercises, in playing order.

    Compiles the spec with the same compiler the trainer uses, so the mapping
    can never drift from what is actually played.  De-duplicated, order
    preserved.  Keys outside the journey simply produce ids that are not in
    the network -- the host's ``markCompleted`` ignores unknown ids.
    """
    out: List[str] = []
    seen = set()
    for chord in compile_exercise(spec).chords:
        tonic, _ = parse_key(chord.triad.key)
        nid = degree_node_id(tonic, chord.triad.degree_index)
        if nid not in seen:
            seen.add(nid)
            out.append(nid)
    return out


# ---------------------------------------------------------------------------
# Progress (persistence wrapper around ProgressStore)
# ---------------------------------------------------------------------------

class JourneyProgress:
    """Journey persistence: stage records, drill records, lit node ids.

    A thin, purpose-named wrapper around
    :class:`harmony.curriculum_progress.ProgressStore` -- the same JSON store
    the curriculum uses, pointed at its own file.  All timestamps are
    host-supplied (pure otherwise).  Every mutation saves immediately (the
    file is tiny).
    """

    def __init__(self, store: ProgressStore):
        self.store = store
        self.store.load()

    @classmethod
    def open(cls, path=DEFAULT_PROGRESS_FILENAME) -> "JourneyProgress":
        return cls(ProgressStore(path))

    # -- drills -----------------------------------------------------------
    def mark_drill_finished(self, exercise_id: str,
                            timestamp: Optional[str] = None) -> None:
        self.store.record(DRILL_PREFIX + exercise_id, accuracy=1.0,
                          timestamp=timestamp)
        self.store.save()

    def drill_finished(self, exercise_id: str) -> bool:
        p = self.store.progress.get(DRILL_PREFIX + exercise_id)
        return bool(p and p.state in ("completed", "mastered"))

    # -- stages -----------------------------------------------------------
    def mark_stage_started(self, stage_id: str,
                           timestamp: Optional[str] = None) -> None:
        self.store.started(STAGE_PREFIX + stage_id, timestamp)
        self.store.save()

    def mark_stage_completed(self, stage_id: str,
                             timestamp: Optional[str] = None) -> None:
        self.store.record(STAGE_PREFIX + stage_id, accuracy=1.0,
                          timestamp=timestamp)
        self.store.save()

    def stage_completed(self, stage_id: str) -> bool:
        p = self.store.progress.get(STAGE_PREFIX + stage_id)
        return bool(p and p.state in ("completed", "mastered"))

    def stage_satisfied(self, stage: JourneyStage) -> bool:
        """Has the stage's unlock rule been met (or the stage been completed)?

        A stage with no drills (free exploration) is trivially satisfied.
        """
        if self.stage_completed(stage.stage_id):
            return True
        if not stage.drills:
            return True
        done = [self.drill_finished(ex_id) for ex_id in stage.drill_ids()]
        return all(done) if stage.unlock == "finish_all" else any(done)

    def stage_unlocked(self, stages: List[JourneyStage], index: int) -> bool:
        """Stage 0 is always unlocked; stage *i* needs stages 0..i-1 satisfied."""
        if index <= 0:
            return True
        if index >= len(stages):
            return False
        return all(self.stage_satisfied(stages[j]) for j in range(index))

    def resume_stage_index(self, stages: List[JourneyStage]) -> int:
        """Where a returning player picks up: the first unsatisfied stage
        (or the last stage once everything is done)."""
        for i, stage in enumerate(stages):
            if not self.stage_satisfied(stage):
                return i
        return max(0, len(stages) - 1)

    # -- lit nodes ----------------------------------------------------------
    def mark_node_lit(self, node_id: str,
                      timestamp: Optional[str] = None) -> None:
        """Permanently light a network node (no-op for non-node ids)."""
        if not self._is_network_node_id(node_id):
            return
        if self.node_lit(node_id):
            return                        # already lit: keep the store quiet
        self.store.record(node_id, accuracy=1.0, timestamp=timestamp)
        self.store.save()

    def node_lit(self, node_id: str) -> bool:
        p = self.store.progress.get(node_id)
        return bool(p and p.state in ("completed", "mastered"))

    def lit_node_ids(self) -> List[str]:
        return sorted(
            nid for nid, p in self.store.progress.items()
            if self._is_network_node_id(nid)
            and p.state in ("completed", "mastered"))

    @staticmethod
    def _is_network_node_id(node_id: str) -> bool:
        return (node_id.startswith("fnet:")
                and not node_id.startswith(STAGE_PREFIX)
                and not node_id.startswith(DRILL_PREFIX))
