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
    panel_mode,
)
from harmony.functional_network_template import FUNCTION_GROUPS, FUNCTION_GROUP_LABELS


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


def _horizontal_v_spec(keys: List[str],
                       mode: str = "major") -> HarmonyExerciseSpec:
    """The stage-6 cross-key drill: the V triad across every journey key.

    In the minor journey V is drilled in ``harmonic_minor`` (the real minor
    dominant, ticket 13); its exercise id carries the mode so the two
    journeys' drill records stay disjoint in the shared progress store.
    """
    n_keys = f"{len(keys)} different key{'s' if len(keys) != 1 else ''}"
    if mode == "minor":
        return HarmonyExerciseSpec(
            exercise_id=(f"fnet_degree_V_minor_"
                         f"{'_'.join(_slug(k) for k in keys)}"),
            title=f"V across {', '.join(keys)} (minor)",
            drill="horizontal_degree", render="block", mode="harmonic_minor",
            degree="V", keys=list(keys),
            description=(f"The real minor dominant V (harmonic minor) "
                         f"transposed across {', '.join(keys)} — the same "
                         f"functional job in {n_keys}."),
        )
    return HarmonyExerciseSpec(
        exercise_id=f"fnet_degree_V_{'_'.join(_slug(k) for k in keys)}",
        title=f"V across {', '.join(keys)} (major)",
        drill="horizontal_degree", render="block", mode="major",
        degree="V", keys=list(keys),
        description=(f"The dominant triad V transposed across "
                     f"{', '.join(keys)} — the same functional job in "
                     f"{n_keys}."),
    )


def journey_stages(network: HarmonicNetwork) -> List[JourneyStage]:
    """The 7 guided stages, derived from ``network`` (ids can never drift).

    ``network`` must be a functional degree network
    (:func:`harmony.functional_network.build_functional_network`); every node
    id a stage references is checked against it and a missing id raises
    :class:`ValueError` immediately.  A ``mode="minor"`` template (the v2
    minor journey, ticket 15 / G2c) gets the mirrored minor stage machine;
    everything else gets the original major stages.
    """
    if network.template.mode == "minor":
        return _minor_journey_stages(network)
    return _major_journey_stages(network)


def _major_journey_stages(network: HarmonicNetwork) -> List[JourneyStage]:
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
                f"Every diatonic chord does one of three jobs: the "
                f"{FUNCTION_GROUP_LABELS['tonic']} is home (I, with vi and iii "
                f"as stand-ins), the {FUNCTION_GROUP_LABELS['predominant']} "
                f"sets up motion (ii and the subdominant IV), and the "
                f"{FUNCTION_GROUP_LABELS['dominant']} carries tension (V, "
                f"vii°). The violet badges collect each family. Play I–IV–V–I "
                f"and feel the full cycle: home → approach → tension → home."),
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


def _minor_journey_stages(network: HarmonicNetwork) -> List[JourneyStage]:
    """The minor journey's 7 stages (ticket 15 / G2c), mirroring the major
    machine stage for stage: same reveal order, same unlock rules, minor
    vocabulary (i / ii° / III+ / iv / V / VI / vii°) and the harmonic-minor
    story.  Stage ids carry a ``_minor`` suffix so both journeys can share
    one progress store without colliding.
    """
    keys = [canonical_key(k) for k in network.template.journey_keys]
    if not keys:
        raise ValueError("network template has no journey keys")
    home = keys[0]                                   # the journey starts here
    second = keys[1] if len(keys) > 1 else home

    deg = lambda key, i: degree_node_id(key, i, "minor")      # noqa: E731
    fn = lambda key, g: function_node_id(key, g, "minor")     # noqa: E731
    hub = lambda key: key_node_id(key, "minor")               # noqa: E731

    home_degrees = [deg(home, i) for i in range(7)]
    home_functions = [fn(home, g) for g in FUNCTION_GROUPS]
    all_node_ids = [n.id for n in network.nodes]

    # As in the major machine, derive (from the engine) which roman the home
    # tonic triad plays inside the second journey key.
    home_tonic = generate_diatonic_triads(home, "harmonic_minor")[0]
    home_tonic_pcs = frozenset(home_tonic.pitch_classes)
    shared_roman = next(
        (t.roman for t in generate_diatonic_triads(second, "harmonic_minor")
         if frozenset(t.pitch_classes) == home_tonic_pcs), None)
    shared_example = (
        f" (the {home_tonic.chord_symbol} triad is i at home and "
        f"{shared_roman} in {second} minor)" if shared_roman and second != home
        else "")

    hm = "harmonic_minor"
    stages = [
        JourneyStage(
            stage_id="meet_the_scale_minor",
            title="Stage 1 — Meet the minor scale",
            explanation=(
                f"{home} minor also has seven diatonic triads — but this "
                f"journey builds them from HARMONIC minor: the 7th degree is "
                f"raised, which turns the dominant into a real major triad "
                f"(the payoff comes in stage 3). Play the drill and watch "
                f"each correct chord light its node for good. The layout is "
                f"not scale order: chords sit where they *work*."),
            visible_node_ids=list(home_degrees),
            visible_relations=[],
            emphasis_node_ids=[deg(home, 0)],
            drills=[full_key_spec(home, hm)],
            unlock="finish_any",
        ),
        JourneyStage(
            stage_id="three_jobs_minor",
            title="Stage 2 — Three jobs in minor",
            explanation=(
                f"Minor keys run on the same three jobs as major: the "
                f"{FUNCTION_GROUP_LABELS['tonic']} is home (i, with VI and "
                f"the rare III+ as stand-ins), the "
                f"{FUNCTION_GROUP_LABELS['predominant']} sets up motion (the "
                f"diminished ii° and the subdominant iv), and the "
                f"{FUNCTION_GROUP_LABELS['dominant']} carries tension (V, "
                f"vii°). Play i–iv–V–i and feel the full minor cycle: home → "
                f"approach → tension → home."),
            visible_node_ids=home_degrees + home_functions,
            visible_relations=["function_member"],
            emphasis_node_ids=list(home_functions),
            drills=[function_spec(["i", "iv", "V", "i"], "i–iv–V–i",
                                  hm, [home])],
            unlock="finish_any",
        ),
        JourneyStage(
            stage_id="tension_home_minor",
            title="Stage 3 — The real minor V",
            explanation=(
                f"This is why harmonic minor exists. Natural minor's v has "
                f"no leading tone and barely pulls anywhere; raise the 7th "
                f"and V becomes a major triad whose leading tone drags the "
                f"ear home — the same authentic V → i pull major keys have. "
                f"vii°, built on that raised tone, is the rootless twin. "
                f"Play both resolutions in {home} minor and watch the red "
                f"arrows fire."),
            visible_node_ids=home_degrees + home_functions,
            visible_relations=["function_member", "resolves_to"],
            emphasis_node_ids=[deg(home, 4), deg(home, 6)],
            drills=[
                function_spec(["V", "i"], "V–i", hm, [home]),
                function_spec(["vii°", "i"], "vii°–i", hm, [home]),
            ],
            unlock="finish_all",
        ),
        JourneyStage(
            stage_id="approach_chain_minor",
            title="Stage 4 — The approach chain",
            explanation=(
                "Minor's predominants prepare the dominant exactly as in "
                "major: ii° falls a fifth onto V (diminished here, but the "
                "bass motion is the same), and iv steps up to V. Chain them "
                "and you get minor's ii°–V–i — the workhorse cadence of "
                "minor-key music. Play it and follow the arrows: approach, "
                "tension, home."),
            visible_node_ids=home_degrees + home_functions,
            visible_relations=["function_member", "resolves_to", "prepares"],
            emphasis_node_ids=[deg(home, 1), deg(home, 3)],
            drills=[function_spec(["ii°", "V", "i"], "ii°–V–i",
                                  hm, [home])],
            unlock="finish_any",
        ),
        JourneyStage(
            stage_id="substitutes_minor",
            title="Stage 5 — Substitutes",
            explanation=(
                "VI shares two chord tones with i and is minor's classic "
                "tonic substitute — the goal of the deceptive resolution "
                "V → VI, which stings more in minor because VI is a major "
                "chord. III+ also orbits the tonic, but it is a rare, "
                "unstable augmented chord that only exists because the "
                "raised 7th sits inside the mediant. Play VI–ii°–V–i to "
                "hear a substitute launch the whole cycle."),
            visible_node_ids=home_degrees + home_functions,
            visible_relations=["function_member", "resolves_to", "prepares",
                               "tonic_substitute", "deceptive_to"],
            emphasis_node_ids=[deg(home, 5), deg(home, 2)],
            drills=[function_spec(["VI", "ii°", "V", "i"], "VI–ii°–V–i",
                                  hm, [home])],
            unlock="finish_any",
        ),
        JourneyStage(
            stage_id="same_triad_new_key_minor",
            title="Stage 6 — Same triad, new minor key",
            explanation=(
                f"Every minor journey key now has its panel — and grey links "
                f"join triads that are literally the same three notes doing "
                f"different jobs{shared_example}. Fewer links than the major "
                f"journey: harmonic minor's raised-7th chords are unique to "
                f"their key. Play V across all {len(keys)} keys, then repeat "
                f"ii°–V–i in {second} minor to feel a familiar cycle in a "
                f"new home."),
            visible_node_ids=list(all_node_ids),
            visible_relations=["function_member", "resolves_to", "prepares",
                               "tonic_substitute", "deceptive_to",
                               "shared_triad", "fifth_relation"],
            emphasis_node_ids=[hub(second), deg(second, 4)],
            drills=[
                _horizontal_v_spec(keys, "minor"),
                function_spec(["ii°", "V", "i"], "ii°–V–i", hm, [second]),
            ],
            unlock="finish_all",
        ),
        JourneyStage(
            stage_id="free_exploration_minor",
            title="Stage 7 — Free exploration",
            explanation=(
                "Everything is on the table: all minor keys, every relation, "
                "every drill. Click any node to launch its drill — a degree "
                "node pairs its chord with home (X–i; i plays the whole "
                "key), function badges drill their family, key hubs drill "
                "all seven harmonic-minor triads. Toggle relations on the "
                "left to isolate one idea at a time. Nodes you light stay "
                "lit."),
            visible_node_ids=None,                    # no whitelist
            visible_relations=["function_member", "resolves_to", "prepares",
                               "tonic_substitute", "deceptive_to",
                               "shared_triad", "fifth_relation"],
            emphasis_node_ids=[hub(home)],
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

    The panel mode is read off each compiled chord's key ("A minor" -> the
    ``m``-suffixed minor ids), so a harmonic-minor drill lands on the minor
    journey's nodes and a major drill on the major journey's.
    """
    out: List[str] = []
    seen = set()
    for chord in compile_exercise(spec).chords:
        tonic, key_mode = parse_key(chord.triad.key)
        nid = degree_node_id(tonic, chord.triad.degree_index,
                             panel_mode(key_mode))
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
