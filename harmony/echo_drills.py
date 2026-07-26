"""Echo-play ear drills (plan A1 level 1, ticket 07) — pure model layer.

The first aural twin.  A *visual* trainer drill (triads, progressions,
cadence blocks) acquires an *echo* variant: the same spec with
``presentation="echo"``, so it compiles to the **same chords** and grades
through the **same pitch-class validator** — only the presentation changes
(the JS controller hides the notation during the listen phase and the host
auto-plays the target).  Sound-before-symbol, on the same vocabulary.

Three pure decisions live here (the hosts call them; no Qt, no filesystem):

* :func:`echo_variant` — derive the aural twin of a visual spec;
* :func:`is_echo_eligible` — which curriculum leaves own a twin (native
  ``drill``-concept leaves: the triad and cadence drill families);
* :func:`echo_unlocked` — the twin unlocks once the visual leaf is *started*
  (same-content transfer: hear what you have already seen).

Aural and visual attempts share **one mastery record per leaf** because the
host records echo completions under the same curriculum node id — see
``tests/test_echo_drills.py::SharedMasteryRecord``.

Later A1 levels (quality ID, progression ID, cadence ID, bass dictation,
chromatic spotting) ship inside their module tickets — this module is
echo-play only.
"""

from __future__ import annotations

from dataclasses import replace
from typing import List, Optional

from harmony.exercise_spec import HarmonyExerciseSpec
from harmony.lab_spec import LabExperimentSpec


#: Launcher group for the standalone trainer demo (appended there only, like
#: GROUP_IDENTIFY — the load-bearing default_exercise_groups() set is
#: untouched).
GROUP_ECHO = "Echo drills (play by ear)"

#: Progress states (harmony.curriculum_progress.STATES) that unlock the twin.
_UNLOCKED_STATES = frozenset({"started", "completed", "mastered"})


def echo_variant(spec: HarmonyExerciseSpec) -> HarmonyExerciseSpec:
    """The aural twin of a visual trainer spec.

    Same drill content (it compiles to the identical chord list), distinct
    identity (``*_echo`` id, "Echo: " title) so the two variants can coexist
    in a launcher list.  Raises ``ValueError`` for specs that cannot be
    echoed (non-``midi`` answer modes — you cannot play back an MCQ).
    """
    twin = replace(
        spec,
        exercise_id=spec.exercise_id + "_echo",
        title="Echo: " + spec.title,
        presentation="echo",
        description=("Listen first — the notation is hidden. Play back what "
                     "you hear; grading is exactly the visual drill's. "
                     + spec.description).strip(),
    )
    twin.validate()   # rejects non-midi answer modes via the schema rule
    return twin


def is_echo_eligible(lab_spec: Optional[LabExperimentSpec]) -> bool:
    """Does this curriculum leaf own an echo twin?

    v0 covers the native trainer drills (``concept == "drill"``): the triad
    families (full-key / degree / quality / arpeggio) and the cadence block
    drills.  Lab concepts (inversions, voice-leading, motives, ...) keep
    their notation-bound presentation for now.
    """
    if lab_spec is None or lab_spec.concept != "drill":
        return False
    try:
        inner = HarmonyExerciseSpec.from_dict(
            (lab_spec.parameters or {}).get("exercise") or {})
    except Exception:
        return False
    return inner.answer_mode == "midi" and inner.presentation == "visual"


def echo_unlocked(progress_state: Optional[str]) -> bool:
    """The echo twin unlocks once the visual leaf is at least *started*.

    Unknown / missing states stay locked (safe default): sound-before-symbol
    ordering holds *inside* the lesson, but the vocabulary itself is met
    visually first.
    """
    return progress_state in _UNLOCKED_STATES


def echo_demo_specs() -> List[HarmonyExerciseSpec]:
    """Launchable echo drills for the standalone trainer (:data:`GROUP_ECHO`).

    A deliberate *demo* sampler across the covered families — the real per-leaf
    twins are derived on demand from the curriculum leaves via
    :func:`echo_variant`.
    """
    visuals = [
        HarmonyExerciseSpec(
            exercise_id="demo_fullkey_c_major",
            title="All triads of C major",
            drill="full_key", mode="major", key="C major"),
        HarmonyExerciseSpec(
            exercise_id="demo_fullkey_a_minor",
            title="All triads of A natural minor",
            drill="full_key", mode="natural_minor", key="A minor"),
        HarmonyExerciseSpec(
            exercise_id="demo_degree_V_major",
            title="V across C, G, D, A major",
            drill="horizontal_degree", mode="major", degree="V",
            keys=["C", "G", "D", "A"]),
        HarmonyExerciseSpec(
            exercise_id="demo_cadence_v_i_c_major",
            title="V–I authentic cadence in C major",
            drill="function", mode="major", pattern=["V", "I"], keys=["C"]),
        HarmonyExerciseSpec(
            exercise_id="demo_function_ii_v_i_c_major",
            title="ii–V–I in C major",
            drill="function", mode="major", pattern=["ii", "V", "I"],
            keys=["C"]),
    ]
    return [echo_variant(v) for v in visuals]
