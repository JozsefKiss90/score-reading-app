"""Curriculum-driven GraphScene router: classify an exercise, pick a scene, fail closed.

This is the single place that answers *"which bounded harmonic graph should the UI show for the
active learning objective?"* -- replacing the old "one fixed graph, project everything onto it"
runtime.  It routes from **semantics**, never from a root pitch class (plan sections 4, 6):

    precedence
      1. explicit curriculum graph metadata   (source_metadata['graph_scene_type'])
      2. Lab concept                          (inversion / voice_leading / cadence / polyphonic)
      3. native trainer drill family          (full_key / horizontal_degree / quality / function)
      4. concrete pattern & key scope         (function pattern length; one-chord -> key field)
      5. source lesson / category             (source_metadata['category'])
      6. conservative structural fallback     (Explore -> legacy key-relation)
    else  -> fail closed (an honest 'unsupported' scene; NEVER the legacy graph as a catch-all)

The curriculum wraps every native trainer drill as ``LabExperimentSpec(concept='drill')``; such a
spec is *unwrapped* to its :class:`HarmonyExerciseSpec` and routed by drill family, so a Lab-hosted
native drill is never mis-routed as a Lab concept.

Pure / headless.  ``decide_graph_scene`` is the classification (testable in isolation);
``build_graph_scene`` calls it and dispatches to :mod:`harmony.graph_scene_generators`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from harmony.graph_scene import GraphScene, SCENE_TYPES, SCENE_SOURCE_KINDS
from harmony.graph_scene_generators import (
    SCENE_TEMPLATE,
    build_cadence_scene,
    build_exercise_scene,
    build_inversion_scene,
    build_legacy_scene,
    build_polyphonic_scene,
    build_unsupported,
    build_voice_leading_scene,
    context_from_spec,
)


# --------------------------------------------------------------------------------------------- #
# Request / decision contracts (plan section 4)
# --------------------------------------------------------------------------------------------- #

@dataclass(frozen=True)
class GraphSceneRequest:
    """Everything the router needs to choose a scene for the active exercise."""

    curriculum_node_id: Optional[str] = None
    lab_spec: Optional[object] = field(default=None, hash=False)          # LabExperimentSpec
    exercise_spec: Optional[object] = field(default=None, hash=False)     # HarmonyExerciseSpec
    source_metadata: Dict = field(default_factory=dict, hash=False)
    preferred_scene_type: Optional[str] = None


@dataclass(frozen=True)
class GraphSceneDecision:
    """The routing outcome: which scene, why, and the context needed to build it."""

    status: str                      # supported | unsupported | ambiguous
    scene_type: Optional[str]
    reason: str
    generator_id: Optional[str] = None
    required_context: Dict = field(default_factory=dict, hash=False)
    alternatives: Tuple[str, ...] = ()

    def to_dict(self) -> Dict:
        return {
            "status": self.status,
            "sceneType": self.scene_type,
            "reason": self.reason,
            "generatorId": self.generator_id,
            "requiredContext": dict(self.required_context),
            "alternatives": list(self.alternatives),
        }


# --------------------------------------------------------------------------------------------- #
# Classification tables
# --------------------------------------------------------------------------------------------- #

_LAB_CONCEPT_SCENE = {
    "inversion": "inversion_space",
    "voice_leading": "voice_leading_path",
    "polyphonic_harmony": "polyphonic_harmony_path",
    # cadence is render-dependent (handled in _lab_scene_type)
    # motive / reduction -> no harmonic-graph scene (None)
}

#: Scene types built from a native trainer HarmonyExerciseSpec.
_IMPLEMENTED_EXERCISE_SCENES = frozenset({
    "diatonic_key_field", "degree_transposition", "triad_quality_class", "functional_progression",
})
#: Scene types built from a Lab experiment.
_LAB_SCENES = frozenset({
    "inversion_space", "voice_leading_path", "polyphonic_harmony_path", "cadence_resolution",
})
#: Scene types this drill/lab router CANNOT build itself: ``score_harmonic_path`` is generated only
#: from an explicit score source (``build_score_scene``), and ``unsupported`` is a terminal state,
#: never a valid override target.  Naming either via metadata/preferred is ignored.
_ROUTER_UNBUILDABLE = frozenset({"score_harmonic_path", "unsupported"})


def _buildable(scene_type: Optional[str], ex, lab) -> bool:
    """True when this router has the input it needs to actually build ``scene_type``.

    Prevents ``decide`` from returning ``supported`` for a scene that ``build`` would then have to
    degrade to ``unsupported`` (e.g. curriculum metadata naming ``inversion_space`` with no lab)."""
    if scene_type in _IMPLEMENTED_EXERCISE_SCENES:
        return ex is not None
    if scene_type in _LAB_SCENES:
        return lab is not None
    if scene_type in _ROUTER_UNBUILDABLE:
        return False
    return True   # legacy_key_relation needs no input


def _effective_exercise_spec(request: GraphSceneRequest):
    """The HarmonyExerciseSpec to route by: an explicit one, or a native drill unwrapped from a
    ``concept='drill'`` Lab spec (the curriculum's native-drill wrapper)."""
    if request.exercise_spec is not None:
        return request.exercise_spec
    lab = request.lab_spec
    if lab is not None and getattr(lab, "concept", None) == "drill":
        try:
            specs = lab.to_exercise_specs()
        except Exception:
            specs = []
        return specs[0] if specs else None
    return None


def _lab_scene_type(concept: str, render: str) -> Optional[str]:
    if concept == "cadence":
        return "voice_leading_path" if render == "voice_leading" else "cadence_resolution"
    return _LAB_CONCEPT_SCENE.get(concept)


def _drill_scene_type(spec) -> Tuple[str, str]:
    drill = spec.drill
    if drill == "full_key":
        return "diatonic_key_field", "full_key drill -> the key's diatonic field"
    if drill == "horizontal_degree":
        return "degree_transposition", "horizontal_degree drill -> one degree across keys"
    if drill == "quality":
        return "triad_quality_class", "quality drill -> a triad-quality classification"
    if drill == "function":
        if len(spec.pattern or []) >= 2:
            return "functional_progression", "function drill (pattern >= 2) -> a progression path"
        return "diatonic_key_field", "one-chord function drill -> a bounded key field"
    return "unsupported", f"unknown drill {drill!r}"


def _ctx_dict(spec) -> Dict:
    if spec is None:
        return {}
    try:
        return context_from_spec(spec).to_dict()
    except Exception:
        return {}


def _decision(status, scene_type, reason, spec=None, alternatives=()) -> GraphSceneDecision:
    return GraphSceneDecision(
        status=status, scene_type=scene_type, reason=reason,
        generator_id=SCENE_TEMPLATE.get(scene_type or "", ""),
        required_context=_ctx_dict(spec), alternatives=tuple(alternatives))


# --------------------------------------------------------------------------------------------- #
# decide_graph_scene (the pure classification)
# --------------------------------------------------------------------------------------------- #

def _classify(request: GraphSceneRequest, ex, lab) -> GraphSceneDecision:
    meta = request.source_metadata or {}
    lab_concept = getattr(lab, "concept", None) if lab is not None else None

    # 1. explicit curriculum graph metadata wins -- but only when this router can actually build it
    #    (a metadata value naming a lab scene with no lab, or 'unsupported'/'score_harmonic_path',
    #    is ignored so we never claim 'supported' for something build must degrade).
    gm = meta.get("graph_scene_type")
    if gm in SCENE_TYPES and gm not in _ROUTER_UNBUILDABLE and _buildable(gm, ex, lab):
        return _decision("supported", gm, "curriculum graph metadata", ex)

    # 2. Lab concept (a real Lab experiment, not the native-drill wrapper)
    if lab is not None and lab_concept and lab_concept != "drill":
        st = _lab_scene_type(lab_concept, getattr(lab, "render", "") or "")
        if st is None:
            return _decision("unsupported", "unsupported",
                             f"Lab concept {lab_concept!r} has no harmonic-graph scene yet")
        return _decision("supported", st, f"Lab concept {lab_concept!r}")

    # 3 + 4. native trainer drill family (+ pattern/key scope)
    if ex is not None:
        st, reason = _drill_scene_type(ex)
        status = "supported" if st != "unsupported" else "unsupported"
        return _decision(status, st, reason, ex)

    # a native-drill wrapper that did not compile to an exercise -> fail closed, NEVER legacy
    if lab is not None and lab_concept == "drill":
        return _decision("unsupported", "unsupported",
                         "the native-drill wrapper did not compile to an exercise")

    # 5. source lesson / category (coarse hint when no spec is attached)
    cat = (meta.get("category") or "").lower()
    if cat in ("atlas", "circle", "explore", "relations"):
        return _decision("supported", "legacy_key_relation", f"source category {cat!r}")

    # 6. conservative structural fallback: no active exercise -> Explore key-relation graph
    if meta.get("explore") or (ex is None and lab is None):
        return _decision("supported", "legacy_key_relation", "no active exercise (Explore mode)")

    # fail closed
    return _decision("unsupported", "unsupported", "no routable exercise for a harmonic scene")


def decide_graph_scene(request: GraphSceneRequest) -> GraphSceneDecision:
    """Classify a request into a :class:`GraphSceneDecision` (never routes by root pitch class)."""
    ex = _effective_exercise_spec(request)
    lab = request.lab_spec
    semantic = _classify(request, ex, lab)

    preferred = request.preferred_scene_type
    # honour a manual/debug override only when it is a real, buildable, DIFFERENT scene -- otherwise
    # keep the semantic decision (never claim 'supported' for a scene build cannot construct).
    if (preferred and preferred in SCENE_TYPES and preferred not in _ROUTER_UNBUILDABLE
            and preferred != semantic.scene_type and _buildable(preferred, ex, lab)):
        # A manual override that disagrees with the semantics MUST warn, not silently mis-map.
        return GraphSceneDecision(
            status="ambiguous", scene_type=preferred,
            reason=(f"manual override to {preferred!r} disagrees with the semantic scene "
                    f"{semantic.scene_type!r} ({semantic.reason})"),
            generator_id=SCENE_TEMPLATE.get(preferred, preferred),
            required_context=semantic.required_context,
            alternatives=(semantic.scene_type,) if semantic.scene_type else ())
    return semantic


# --------------------------------------------------------------------------------------------- #
# build_graph_scene (dispatch to a generator; always fail closed to a scene, never crash)
# --------------------------------------------------------------------------------------------- #

def _src_kind(request: GraphSceneRequest) -> str:
    m = request.source_metadata or {}
    if m.get("source_kind") in SCENE_SOURCE_KINDS:
        return m["source_kind"]
    if request.curriculum_node_id:
        return "curriculum"
    lab = request.lab_spec
    if lab is not None and getattr(lab, "concept", None) not in (None, "drill"):
        return "lab"
    if _effective_exercise_spec(request) is not None:
        return "harmony_exercise"
    return "explore"


def _src_id(request: GraphSceneRequest) -> str:
    if request.curriculum_node_id:
        return request.curriculum_node_id
    ex = _effective_exercise_spec(request)
    if ex is not None:
        return ex.exercise_id
    if request.lab_spec is not None:
        return getattr(request.lab_spec, "experiment_id", "lab")
    return (request.source_metadata or {}).get("source_id", "explore")


def build_graph_scene(request: GraphSceneRequest) -> Optional[GraphScene]:
    """Route the request and build the concrete :class:`GraphScene`.

    Always returns a scene (never ``None`` in practice): an unroutable / not-yet-implemented /
    failed build degrades to an honest ``unsupported`` scene so the trainer keeps running with a
    graph that plainly states no suitable topology exists -- it never falls back to the legacy
    graph as a catch-all (plan section 1 "Fail closed").
    """
    try:
        decision = decide_graph_scene(request)
        ex = _effective_exercise_spec(request)
        lab = request.lab_spec
        src_kind, src_id = _src_kind(request), _src_id(request)
        warns = [decision.reason] if decision.status == "ambiguous" else None
        st = decision.scene_type

        if st == "unsupported" or st is None:
            return build_unsupported(source_kind=src_kind, source_id=src_id, reason=decision.reason)

        if st in _IMPLEMENTED_EXERCISE_SCENES and ex is not None:
            return build_exercise_scene(st, ex, source_kind=src_kind, source_id=src_id,
                                        extra_warnings=warns)

        if st == "inversion_space" and lab is not None:
            return build_inversion_scene(lab, source_kind=src_kind, source_id=src_id,
                                         extra_warnings=warns)

        if st == "cadence_resolution" and lab is not None:
            return build_cadence_scene(lab, source_kind=src_kind, source_id=src_id,
                                       extra_warnings=warns)

        if st == "voice_leading_path" and lab is not None:
            return build_voice_leading_scene(lab, source_kind=src_kind, source_id=src_id,
                                             extra_warnings=warns)

        if st == "polyphonic_harmony_path" and lab is not None:
            return build_polyphonic_scene(lab, source_kind=src_kind, source_id=src_id,
                                          extra_warnings=warns)

        if st == "legacy_key_relation":
            return build_legacy_scene(source_kind=src_kind, source_id=src_id, extra_warnings=warns)

        # Reached only if a scene was decided without its required source input (rare -- decide gates
        # on buildability) or a score scene slipped through (score is built from an explicit score
        # source via build_score_scene, never this drill router). Fail closed honestly.
        return build_unsupported(
            source_kind=src_kind, source_id=src_id,
            reason=(f"scene {st!r} needs a source input that isn't available to the drill router; "
                    f"{decision.reason}"))
    except Exception as exc:  # last-resort guard: a malformed spec must never crash the host
        return build_unsupported(source_kind="explore", source_id="error",
                                 reason=f"scene build failed: {exc}")


__all__ = [
    "GraphSceneRequest",
    "GraphSceneDecision",
    "decide_graph_scene",
    "build_graph_scene",
]
