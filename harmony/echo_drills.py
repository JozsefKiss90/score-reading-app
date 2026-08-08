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


#: Answer modes a visual drill can be echoed in, mapped to how the twin asks
#: its question once the notation is veiled.  ``midi`` is the original twin
#: (play back what you hear).  ``spot`` (ticket 19 / plan G5c) is the applied
#: ear stage: the same intruder hunt, answered by clicking *where* the
#: chromatic chord sounded — the one non-midi surface that survives the veil,
#: because bar positions name no chord.  ``mcq``/``card`` are excluded: an
#: authored echo+mcq drill is not a *twin* of a visual one (ticket 10), and
#: the card list is withheld while veiled.
_ECHOABLE_ANSWER_MODES = {
    "midi": ("Play back what you hear; grading is exactly the visual "
             "drill's."),
    "spot": ("Click the bar where the chord leaves the key, then name the "
             "degree it tonicises."),
}


def echo_variant(spec: HarmonyExerciseSpec) -> HarmonyExerciseSpec:
    """The aural twin of a visual trainer spec.

    Same drill content (it compiles to the identical chord list), distinct
    identity (``*_echo`` id, "Echo: " title) so the two variants can coexist
    in a launcher list.  Raises ``ValueError`` for specs whose answer surface
    cannot survive the veil (see :data:`_ECHOABLE_ANSWER_MODES`).
    """
    how = _ECHOABLE_ANSWER_MODES.get(spec.answer_mode)
    if how is None:
        raise ValueError(
            f"cannot derive an echo twin of an answer_mode="
            f"{spec.answer_mode!r} spec: an echo twin's answer surface must "
            f"survive the veil (midi playback, or the applied spot hunt)")
    twin = replace(
        spec,
        exercise_id=spec.exercise_id + "_echo",
        title="Echo: " + spec.title,
        presentation="echo",
        description=("Listen first — the notation is hidden. " + how + " "
                     + spec.description).strip(),
    )
    twin.validate()   # rejects answer modes the schema refuses under the veil
    return twin


def is_echo_eligible(lab_spec: Optional[LabExperimentSpec]) -> bool:
    """Does this curriculum leaf own an echo twin?

    Two families qualify.  The native trainer drills (``concept == "drill"``):
    the triad families (full-key / degree / quality / arpeggio) and the
    cadence block drills.  And the applied-chord *spot* leaves (ticket 19 /
    plan G5c), whose twin is the ear stage — the same intruder hunt heard
    rather than read, recorded under the same curriculum node id, which is
    what makes the ramp's visual→ear axis one mastery record instead of two
    leaves.  Other Lab concepts keep their notation-bound presentation.
    """
    if lab_spec is None:
        return False
    if lab_spec.concept == "applied_chord":
        stages = tuple((lab_spec.parameters or {}).get("stages") or ())
        return stages == ("spot",)
    if lab_spec.concept != "drill":
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
