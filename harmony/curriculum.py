"""The canonical curriculum ontology for the Music Theory Laboratory.

This module is the **architectural consolidation** of the Harmony-Trainer
ecosystem: it turns the original trainer exercise registry (the 102 drills of the
six drill families in :func:`harmony.exercise_spec.default_exercise_groups`) plus
the synthetic Music-Theory-Lab concepts (:func:`harmony.lab.lab_demo_specs`) and
the Atlas-derived cadence drills into ONE deterministic *educational tree*.

The Lab becomes the canonical **source**; the Harmony Trainer becomes the
**execution engine**.  Every exercise in the whole ecosystem is reachable as::

    CurriculumNode (kind="exercise")
        owns exactly one  LabExperimentSpec
            compiles to one or more  HarmonyExerciseSpec
                executed by  the Harmony Trainer

Design rules (shared with :mod:`harmony.atlas` / :mod:`harmony.exercise_spec`):

* **Single source of truth.**  Nothing here re-defines an exercise.  Native
  drills are read verbatim from ``default_exercise_groups`` and *wrapped* in a
  ``LabExperimentSpec(concept="drill")`` (the passthrough concept); lab concepts
  are read from ``lab_demo_specs``; cadence drills reuse the Atlas factories.  No
  exercise definition is duplicated -- every launchable ``exercise_id`` appears
  under exactly one curriculum node.
* **Deterministic & pure.**  Same inputs -> identical tree, ids, ordering.  No
  Qt / Verovio / MIDI, so it unit-tests headlessly and serialises to JSON
  (:func:`build_curriculum`/:meth:`CurriculumNode.to_payload`) for the web UI.
* **Cap-respecting.**  Every exercise leaf's ``lab_spec.to_exercise_specs()`` is
  asserted to compile within :data:`~harmony.exercise_spec.MAX_CHORDS_PER_SPEC`
  (see :data:`spec-builder-cap-invariant`).
* **Extensible.**  New material is added by appending a category builder / a new
  ``LabExperimentSpec`` -- never by reshaping the node schema.  The reserved
  branches (Atlas, Circle, Advanced Topics, Real-Score Analysis, Reduction) name
  the future expansion seams.

The rich human-readable *lesson / exercise pages* (definition, skills acquired,
common mistakes, practice advice, voice-leading notes, audio/visual objectives)
are assembled by the sibling pure module :mod:`harmony.curriculum_explanations`,
which also builds the full UI payload (:func:`build_curriculum_payload`).
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from theory.diatonic_harmony import (
    generate_diatonic_triads,
    transpose_degree_pattern,
    parse_seventh_token,
    seventh_tokens_for_mode,
    SEVENTH_QUALITY_LABELS,
    _mode_word,
)
from harmony.harmonic_roles import (
    BROAD_TO_INTERNAL_FAMILY,
    ENGINE_FUNCTION_TO_INTERNAL_FAMILY,
    function_flow_short,
    internal_family_label,
    role_profile,
)
from harmony.exercise_spec import (
    HarmonyExerciseSpec,
    compile_exercise,
    normalise_pattern,
    default_exercise_groups,
    degree_labels_for_mode,
    MAX_CHORDS_PER_SPEC,
    DEFAULT_MAJOR_KEYS,
    DEFAULT_MINOR_KEYS,
    _key_slug,
    _chunk_keys,
    _keys_label,
    _triads_of_quality,
    GROUP_MAJOR_FULL_KEY,
    GROUP_MINOR_FULL_KEY,
    GROUP_DEGREE,
    GROUP_QUALITY,
    GROUP_FUNCTION,
    GROUP_ARPEGGIO,
)
from harmony.lab_spec import LabExperimentSpec, split_figured_pattern
from harmony.echo_drills import is_echo_eligible
from harmony.lab import lab_demo_specs
from harmony.atlas import (
    scale_id, degree_id, triad_id, quality_id, function_id, layer_id,
    function_spec, build_atlas,
    _REFERENCE_TONIC,
)


SCHEMA_VERSION = "harmony-curriculum/v1"

#: The node kinds, deepest-first.  ``reserved`` marks a future-expansion node
#: that owns no launchable exercise yet (Atlas / Circle bridges, Advanced Topics,
#: Real-Score Analysis, Reduction, Augmented triads).
KINDS = ["curriculum", "category", "lesson", "group", "exercise", "reserved"]


# ---------------------------------------------------------------------------
# Node model
# ---------------------------------------------------------------------------

@dataclass
class CurriculumNode:
    """One node of the educational ontology.

    Every node (any kind) carries the pedagogical envelope: ``title`` /
    ``subtitle`` / ``learning_objective`` / ``difficulty`` / ``prerequisites`` /
    ``recommended_next`` / ``estimated_minutes`` / ``atlas_nodes`` /
    ``circle_nodes`` / ``theory``.  ``children`` holds the sub-tree (empty for a
    leaf); ``lab_spec`` is set **only** on ``exercise`` leaves -- the single
    LabExperimentSpec the node owns.
    """

    id: str
    parent: Optional[str]
    kind: str
    title: str
    order: int
    subtitle: str = ""
    description: str = ""
    learning_objective: str = ""
    difficulty: int = 1                       # 1 (easiest) .. 5
    estimated_minutes: int = 0
    prerequisites: List[str] = field(default_factory=list)   # node ids
    recommended_next: Optional[str] = None                   # node id
    related: List[str] = field(default_factory=list)         # node ids
    atlas_nodes: List[str] = field(default_factory=list)     # atlas node ids
    circle_nodes: List[str] = field(default_factory=list)    # circle refs (see _circle_*)
    theory: str = ""
    keywords: List[str] = field(default_factory=list)        # extra search terms
    reserved: bool = False
    exercise_count: int = 0                   # descendant exercise leaves (1 for a leaf)
    completion_state: str = "not_started"     # overlaid by curriculum_progress
    children: List["CurriculumNode"] = field(default_factory=list)
    lab_spec: Optional[LabExperimentSpec] = None

    #: Additive graph-scene metadata (plan section 4). Optional per-node hint/override the
    #: GraphSceneRouter honours *before* falling back to drill-family routing. Left unset on
    #: almost every node -- the router derives the scene from the compiled spec by default; a node
    #: sets ``graph_scene_type`` only to pin/override a scene, and ``graph_required`` to demand one.
    graph_scene_type: Optional[str] = None       # a harmony.graph_scene SCENE_TYPES value
    graph_scene_scope: Optional[str] = None       # a SEMANTIC_SCOPES value (advisory)
    graph_scene_options: Dict = field(default_factory=dict)
    graph_required: bool = False

    # -- traversal -------------------------------------------------------
    def walk(self):
        """Yield this node then every descendant (pre-order, deterministic)."""
        yield self
        for c in self.children:
            yield from c.walk()

    def leaves(self) -> List["CurriculumNode"]:
        return [n for n in self.walk() if n.kind == "exercise"]

    def find(self, node_id: str) -> Optional["CurriculumNode"]:
        for n in self.walk():
            if n.id == node_id:
                return n
        return None

    # -- serialisation ---------------------------------------------------
    def to_payload(self, include_children: bool = True) -> Dict:
        """A JSON-serialisable view of this node (recurses unless asked not to)."""
        d = {
            "id": self.id,
            "parent": self.parent,
            "kind": self.kind,
            "title": self.title,
            "order": self.order,
            "subtitle": self.subtitle,
            "description": self.description,
            "learningObjective": self.learning_objective,
            "difficulty": self.difficulty,
            "estimatedMinutes": self.estimated_minutes,
            "prerequisites": list(self.prerequisites),
            "recommendedNext": self.recommended_next,
            "related": list(self.related),
            "atlasNodes": list(self.atlas_nodes),
            "circleNodes": list(self.circle_nodes),
            "theory": self.theory,
            "keywords": list(self.keywords),
            "reserved": self.reserved,
            "exerciseCount": self.exercise_count,
            "completionState": self.completion_state,
        }
        if self.lab_spec is not None:
            d["labSpec"] = self.lab_spec.to_dict()
            d["exerciseSpecs"] = [s.to_dict() for s in self.lab_spec.to_exercise_specs()]
            d["echoEligible"] = is_echo_eligible(self.lab_spec)
        gs = self.graph_scene_metadata()
        if gs:
            d["graphScene"] = gs
        if include_children:
            d["children"] = [c.to_payload() for c in self.children]
        return d

    def graph_scene_metadata(self) -> Dict:
        """The additive ``graphScene`` payload block, or ``{}`` when the node pins no scene.

        Emitted into the node payload only when set, so nodes that rely on default drill-family
        routing keep an unchanged payload. The host passes this into the router's
        ``source_metadata`` (``graph_scene_type`` is routing precedence 1, plan section 4)."""
        if not self.graph_scene_type:
            return {}
        return {
            "type": self.graph_scene_type,
            "scope": self.graph_scene_scope,
            "options": dict(self.graph_scene_options),
            "required": bool(self.graph_required),
        }


# ---------------------------------------------------------------------------
# Difficulty / duration / theory templates (deterministic, per drill family)
# ---------------------------------------------------------------------------

#: Base difficulty + minutes-per-exercise heuristics per native drill family.
_DRILL_PROFILE = {
    "full_key":          {"difficulty": 1, "minutes": 3},
    "horizontal_degree": {"difficulty": 2, "minutes": 3},
    "quality":           {"difficulty": 2, "minutes": 4},
    "function":          {"difficulty": 3, "minutes": 4},
}

#: Base difficulty + minutes per lab concept.
_CONCEPT_PROFILE = {
    "inversion":          {"difficulty": 2, "minutes": 4},
    "voice_leading":      {"difficulty": 3, "minutes": 5},
    "cadence":            {"difficulty": 3, "minutes": 5},
    "motive":             {"difficulty": 2, "minutes": 4},
    "polyphonic_harmony": {"difficulty": 4, "minutes": 6},
    "drill":              {"difficulty": 2, "minutes": 3},
}


def _mode_short(mode: str) -> str:
    return "major" if mode == "major" else "minor"


def _spec_keys(hs: HarmonyExerciseSpec) -> List[str]:
    """The tonic list a native spec touches (single key, key list, or mode default)."""
    if hs.key:
        return [hs.key.split()[0]]
    if hs.keys:
        return list(hs.keys)
    from harmony.exercise_spec import DEFAULT_MAJOR_KEYS, DEFAULT_MINOR_KEYS
    return list(DEFAULT_MAJOR_KEYS if hs.mode == "major" else DEFAULT_MINOR_KEYS)


def _wrap_native(hs: HarmonyExerciseSpec) -> LabExperimentSpec:
    """Wrap a native trainer drill in the passthrough ``drill`` LabExperimentSpec."""
    tonic = _spec_keys(hs)[0]
    key = hs.key or f"{tonic} {_mode_short(hs.mode)}"
    spec = LabExperimentSpec(
        experiment_id=f"drill_{hs.exercise_id}",
        title=hs.title,
        concept="drill",
        mode=hs.mode,
        key=key,
        render=hs.render,
        parameters={"exercise": hs.to_dict()},
        description=hs.description,
    )
    spec.validate()
    return spec


# ---------------------------------------------------------------------------
# Atlas / Circle reference derivation (reuses the canonical id schemes)
# ---------------------------------------------------------------------------

def _dedup(seq) -> List[str]:
    out, seen = [], set()
    for x in seq:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _is_tetrad(t) -> bool:
    return len(t.pitches) > 3


def _degree_roman(t) -> str:
    """The Roman the DEGREE refs may claim: a tetrad projects onto its base
    degree (V7 is genuinely built on degree 5), never onto a triad node.

    The base-degree label comes from the mode's degree vocabulary by INDEX
    (``viiø7`` -> ``vii°``, ``Imaj7`` -> ``I``) — stripping characters from
    the tetrad's roman would fabricate labels no degree node owns.
    """
    if _is_tetrad(t):
        return degree_labels_for_mode(t.mode)[t.degree_index]
    return t.roman


def _key_context_mode(mode: str) -> str:
    """The Atlas/Circle KEY-context mode of a drill.

    A harmonic-minor drill still happens in the same minor *key* (the raised
    7th is a scale form, not a new key signature), so its key-level claims
    stay natural minor -- the Score Soul precedent: key context is claimed,
    chord nodes only on an exact match.
    """
    return "natural_minor" if mode == "harmonic_minor" else mode


def _natural_minor_twin(t) -> Optional["DiatonicTriad"]:
    """The natural-minor diatonic triad a harmonic-minor chord exactly equals,
    else ``None`` (the raised-leading-tone chords III+ / V / vii° match none)."""
    key = t.key.split()[0]
    nat = generate_diatonic_triads(key, "natural_minor")[t.degree_index]
    return nat if nat.pitches == t.pitches else None


def _atlas_refs_for_native(hs: HarmonyExerciseSpec) -> List[str]:
    """Atlas node ids a native drill highlights -- derived from its compiled chords.

    A tetrad (V7) maps only onto what the Atlas truly has: its scale, its
    scale-*degree* node (the chord is genuinely built on degree 5) and its
    function family.  It never claims the triad / quality / layer nodes -- the
    Atlas has no seventh-chord node kind, and landing G7 on the G-triad node
    would be exactly the dishonesty the ``base_roman`` rule forbids.

    A harmonic-minor drill (ticket 13) claims its minor KEY context plus, per
    chord, either the natural-minor node it exactly equals (i / ii° / iv / VI)
    or -- for the raised-leading-tone chords -- only the mode-less quality and
    layer classes.  The Atlas has no harmonic-minor scale/degree/triad nodes,
    and the natural-minor v / VII are different chords.
    """
    refs: List[str] = []
    compiled = compile_exercise(hs)
    ctx_mode = _key_context_mode(hs.mode)
    for c in compiled.chords:
        t = c.triad
        key = t.key.split()[0]
        refs.append(scale_id(key, ctx_mode))
        if hs.mode == "harmonic_minor":
            nat = None if _is_tetrad(t) else _natural_minor_twin(t)
            if nat is not None:
                refs.append(degree_id(ctx_mode, nat.roman))
                refs.append(triad_id(key, ctx_mode, t.degree_index))
                refs.append(function_id(ctx_mode, nat.function_label))
            if not _is_tetrad(t):
                refs.append(quality_id(t.chord_quality))
                refs.append(layer_id(t.interval_layer))
            continue
        refs.append(degree_id(hs.mode, _degree_roman(t)))
        if not _is_tetrad(t):
            refs.append(triad_id(key, hs.mode, t.degree_index))
            refs.append(quality_id(t.chord_quality))
            refs.append(layer_id(t.interval_layer))
        refs.append(function_id(hs.mode, t.function_label))
    return _dedup(refs)


def _atlas_refs_for_lab(spec: LabExperimentSpec) -> List[str]:
    """Atlas node ids a lab experiment highlights -- derived from its parameters."""
    mode = spec.mode
    tonic = spec.key.split()[0]
    refs: List[str] = [scale_id(tonic, mode)]
    p = spec.parameters
    tokens: List[str] = []
    if spec.concept == "inversion":
        tokens = [str(p.get("degree", "I"))]
    elif spec.concept in ("cadence", "voice_leading"):
        # Strip figured suffixes ("ii6") first; the refs point at the chord
        # identity, which the figure does not change.
        tokens = split_figured_pattern(list(p.get("pattern", [])))[0]
    elif spec.concept == "polyphonic_harmony":
        tokens = list(p.get("progression", []))
    if tokens:
        roman = normalise_pattern(tokens)
        for t in transpose_degree_pattern(roman, tonic, mode):
            refs.append(degree_id(mode, _degree_roman(t)))
            if not _is_tetrad(t):
                refs.append(triad_id(tonic, mode, t.degree_index))
                refs.append(quality_id(t.chord_quality))
            refs.append(function_id(mode, t.function_label))
    return _dedup(refs)


def _circle_ref_key(tonic: str, mode: str) -> str:
    return f"key:{tonic}:{mode}"


def _circle_ref_degree(mode: str, roman: str) -> str:
    return f"degree:{mode}:{roman}"


def _circle_refs_for_native(hs: HarmonyExerciseSpec) -> List[str]:
    refs: List[str] = []
    ctx_mode = _key_context_mode(hs.mode)
    for key in _spec_keys(hs):
        refs.append(_circle_ref_key(key, ctx_mode))
    compiled = compile_exercise(hs)
    for c in compiled.chords:
        if hs.mode == "harmonic_minor":
            nat = None if _is_tetrad(c.triad) else _natural_minor_twin(c.triad)
            if nat is not None:
                refs.append(_circle_ref_degree(ctx_mode, nat.roman))
            continue
        refs.append(_circle_ref_degree(hs.mode, _degree_roman(c.triad)))
    return _dedup(refs)


def _circle_refs_for_lab(spec: LabExperimentSpec) -> List[str]:
    mode = spec.mode
    tonic = spec.key.split()[0]
    refs = [_circle_ref_key(tonic, mode)]
    p = spec.parameters
    tokens: List[str] = []
    if spec.concept == "inversion":
        tokens = [str(p.get("degree", "I"))]
    elif spec.concept in ("cadence", "voice_leading"):
        tokens = split_figured_pattern(list(p.get("pattern", [])))[0]
    elif spec.concept == "polyphonic_harmony":
        tokens = list(p.get("progression", []))
    elif spec.concept == "motive":
        # a motive is monophonic; it sweeps every key of its mode
        from harmony.exercise_spec import DEFAULT_MAJOR_KEYS, DEFAULT_MINOR_KEYS
        keys = list(p.get("keys") or
                    (DEFAULT_MAJOR_KEYS if mode == "major" else DEFAULT_MINOR_KEYS))
        refs.extend(_circle_ref_key(k, mode) for k in keys)
    if tokens:
        for r in normalise_pattern(tokens):
            d = parse_seventh_token(r)
            refs.append(_circle_ref_degree(
                mode, degree_labels_for_mode(mode)[d] if d is not None else r))
    return _dedup(refs)


# ---------------------------------------------------------------------------
# Leaf (exercise) builders
# ---------------------------------------------------------------------------

def _function_words() -> Dict[str, str]:
    """Roman-numeral -> internal family word, so a word query ("predominant")
    reaches the individual function/degree drills, not only their category.

    Derived from the theory engine + the single vocabulary source (ticket 01 /
    plan F1) -- never hand-edit."""
    out: Dict[str, str] = {}
    for mode in ("major", "natural_minor"):
        for t in generate_diatonic_triads(_REFERENCE_TONIC[mode], mode):
            out[t.roman] = ENGINE_FUNCTION_TO_INTERNAL_FAMILY[t.function_label]
    return out


_FUNCTION_WORDS = _function_words()

#: What each broad family *does* in a progression (the pedagogical one-liners the
#: generated prose hangs the derived memberships on).
_FAMILY_SENSE = {"tonic": "rest", "predominant": "preparation", "dominant": "tension"}


def _roman_list(names: List[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def function_families_prose(mode: str = "major") -> str:
    """The functional-harmony story of ``mode``, rendered entirely from the shared
    two-level vocabulary (:mod:`harmony.harmonic_roles`) -- family labels, memberships
    and the contextual caveats all derive from :func:`role_profile`, so no curriculum
    prose can drift from the source (ticket 01 / plan F1)."""
    fams: "OrderedDict[str, List]" = OrderedDict(
        (f, []) for f in ("tonic", "predominant", "dominant"))
    modal: List = []
    for t in generate_diatonic_triads(_REFERENCE_TONIC[mode], mode):
        prof = role_profile(t.mode, t.degree_index, roman=t.roman,
                            scale_degree_name=t.scale_degree_name)
        fam = BROAD_TO_INTERNAL_FAMILY.get(prof.broad_family)
        (fams[fam] if fam else modal).append((t.roman, prof))
    parts = []
    for fam, members in fams.items():
        names = _roman_list(
            [r + (" (context-dependent)" if p.contextual else "")
             for r, p in members])
        parts.append(f"the {internal_family_label(fam)} means "
                     f"{_FAMILY_SENSE[fam]}: {names}")
    prose = ("Functional harmony groups chords into broad families — "
             + "; ".join(parts) + ".")
    if modal:
        prose += (" " + _roman_list(
            [f"{r} is the modal {p.specific_role}" for r, p in modal])
            + ", outside the three functional families.")
    prose += (f" A progression moves {function_flow_short()}; the dominant's pull "
              "toward the tonic is the engine of tonal music. The family is a "
              "grouping, not the chord's complete identity — each degree keeps its "
              "specific role alongside it.")
    notes = [p.family_membership_explanation
             for _r, p in [m for ms in fams.values() for m in ms] + modal
             if p.contextual]
    if notes:
        prose += " " + " ".join(notes)
    return prose


def _native_keywords(hs: HarmonyExerciseSpec) -> List[str]:
    kws = [hs.drill, hs.render, hs.mode, _mode_word(hs.mode)]
    kws.extend(_spec_keys(hs))
    if hs.degree:
        kws.append(hs.degree)
        if hs.degree in _FUNCTION_WORDS:
            kws.append(_FUNCTION_WORDS[hs.degree])
    if hs.quality:
        kws.append(hs.quality)
    if hs.pattern:
        kws.extend(hs.pattern)
        kws.append("".join(hs.pattern))
        kws.append("-".join(hs.pattern))
        # function words for each chord in the progression (reach by word query)
        kws.extend(_FUNCTION_WORDS[tok] for tok in hs.pattern if tok in _FUNCTION_WORDS)
    return kws


def _exercise_node_from_native(hs: HarmonyExerciseSpec, parent: str, order: int,
                               difficulty: int) -> CurriculumNode:
    lab = _wrap_native(hs)
    prof = _DRILL_PROFILE.get(hs.drill, {"difficulty": difficulty, "minutes": 3})
    n_chords = len(compile_exercise(hs))
    return CurriculumNode(
        id=f"ex:{lab.experiment_id}",
        parent=parent, kind="exercise", title=hs.title, order=order,
        subtitle=hs.description,
        description=hs.description,
        learning_objective=_native_objective(hs),
        difficulty=difficulty or prof["difficulty"],
        estimated_minutes=max(2, prof["minutes"]),
        atlas_nodes=_atlas_refs_for_native(hs),
        circle_nodes=_circle_refs_for_native(hs),
        keywords=_native_keywords(hs),
        exercise_count=1,
        lab_spec=lab,
    )


def _native_objective(hs: HarmonyExerciseSpec) -> str:
    if hs.drill == "full_key":
        return (f"Play all seven diatonic triads of {hs.key} as "
                f"{'arpeggios' if hs.render == 'arpeggio' else 'block chords'}.")
    if hs.drill == "horizontal_degree":
        return (f"Recognise and play the {hs.degree} triad in every "
                f"{_mode_word(hs.mode)} key (transpositional fluency).")
    if hs.drill == "quality":
        q = (hs.quality or "").replace("_", " ")
        noun = "chord" if "seventh" in q else f"{q} triad"
        label = f"{q} {noun}" if noun == "chord" else noun
        return f"Identify and play every {label} across the keys in this set."
    if hs.drill == "function":
        return (f"Play the {'-'.join(hs.pattern or [])} progression and hear its "
                f"functional motion (T / S / D).")
    return hs.description or hs.title


def _exercise_node_from_lab(spec: LabExperimentSpec, parent: str, order: int,
                            difficulty: int) -> CurriculumNode:
    prof = _CONCEPT_PROFILE.get(spec.concept, {"difficulty": difficulty, "minutes": 4})
    objective = _lab_objective(spec)
    subtitle = spec.description or objective   # never leave the subtitle blank
    return CurriculumNode(
        id=f"ex:{spec.experiment_id}",
        parent=parent, kind="exercise", title=spec.title, order=order,
        subtitle=subtitle,
        description=subtitle,
        learning_objective=objective,
        difficulty=difficulty or prof["difficulty"],
        estimated_minutes=max(2, prof["minutes"]),
        atlas_nodes=_atlas_refs_for_lab(spec),
        circle_nodes=_circle_refs_for_lab(spec),
        keywords=_lab_keywords(spec),
        exercise_count=1,
        lab_spec=spec,
    )


def _lab_objective(spec: LabExperimentSpec) -> str:
    p = spec.parameters
    if spec.concept == "inversion":
        if parse_seventh_token(str(p.get("degree", ""))) is not None:
            return (f"Voice {p.get('degree')} from each figure "
                    f"(7 · 6/5 · 4/3 · 4/2) with the demanded bass as the "
                    f"lowest sounding note.")
        return (f"Hear that {p.get('degree', 'I')} keeps its identity as the bass "
                f"moves through root position, first, and second inversion.")
    if spec.concept in ("cadence", "voice_leading"):
        if p.get("dictation") == "bass":
            return (f"Hear the {'-'.join(p.get('pattern', []))} progression "
                    f"and play back only its bass line.")
        return (f"Voice-lead the {'-'.join(p.get('pattern', []))} progression and "
                f"resolve its tendency tones.")
    if spec.concept == "motive":
        from harmony.lab import _CARET
        degs = "-".join(_CARET.get(d, f"^{d}") for d in p.get("degrees", []))
        return f"Transpose the motive {degs} through every {spec.mode.replace('_', ' ')} key."
    if spec.concept == "polyphonic_harmony":
        return (f"Hear two independent voices imply the "
                f"{'-'.join(p.get('progression', []))} progression.")
    return spec.description or spec.title


def _lab_keywords(spec: LabExperimentSpec) -> List[str]:
    p = spec.parameters
    kws = [spec.concept, spec.mode, _mode_word(spec.mode), spec.key.split()[0]]
    for fld in ("pattern", "progression"):
        if p.get(fld):
            kws.extend(p[fld])
            kws.append("-".join(p[fld]))
    if p.get("degree"):
        kws.append(str(p["degree"]))
    if p.get("degrees"):
        kws.append("-".join(str(d) for d in p["degrees"]))
    if spec.concept == "inversion":
        kws.append("inversion")
    if p.get("dictation"):
        kws.extend(["dictation", "bass line", "ear", "🎧"])
    return kws


# ---------------------------------------------------------------------------
# Cadence catalogue (the single source for the Cadences + Voice-leading layers)
# ---------------------------------------------------------------------------
#
# Each entry: ``(tokens, label, mode, cadence_type, family)`` where ``family`` is
# ``"type"`` (a two-chord cadence closure) or ``"progression"`` (a longer
# functional cadence).  Every entry has a matching Atlas cadence node (looked up
# by tokens, so the mapping always resolves) and -- where one exists -- reuses the
# lab cadence/voice-leading demo for its SATB version, so nothing is duplicated.
_CADENCE_CATALOG = [
    # -- major two-chord cadence types --
    (["V", "I"],  "V–I",  "major", "authentic", "type"),
    (["IV", "I"], "IV–I", "major", "plagal",    "type"),
    (["I", "V"],  "I–V",  "major", "half",      "type"),
    (["V", "vi"], "V–vi", "major", "deceptive", "type"),
    # -- natural-minor two-chord cadence types --
    (["v", "i"],   "v–i",   "natural_minor", "authentic", "type"),
    (["VII", "i"], "VII–i", "natural_minor", "subtonic",  "type"),
    # -- major functional cadence progressions --
    (["I", "IV", "V", "I"],  "I–IV–V–I",  "major", "authentic", "progression"),
    (["ii", "V", "I"],       "ii–V–I",    "major", "authentic", "progression"),
    (["vi", "ii", "V", "I"], "vi–ii–V–I", "major", "authentic", "progression"),
    # The axis loop is NOT a deceptive cadence: its V–vi motion is mid-loop and the
    # phrase ends on IV (ticket 02 / plan F2). V–vi above stays the deceptive exemplar.
    (["I", "V", "vi", "IV"], "I–V–vi–IV", "major", "axis", "progression"),
    # -- natural-minor functional cadence progressions --
    (["iv", "v", "i"],        "iv–v–i",     "natural_minor", "authentic", "progression"),
    (["i", "iv", "v", "i"],   "i–iv–v–i",   "natural_minor", "authentic", "progression"),
    (["i", "VI", "VII", "i"], "i–VI–VII–i", "natural_minor", "aeolian",   "progression"),
]

#: One-line description of each cadence type's sense of closure (function-path /
#: bass-motion prose is generated per cadence from the compiled chords).  Keys are
#: drawn from :data:`harmony.harmonic_roles.CADENCE_TYPES` (the canonical enum).
_CADENCE_TYPE_BLURB = {
    "authentic": "a strong arrival driven by the dominant resolving to the tonic",
    "plagal": "the gentle 'amen' of the subdominant falling to the tonic",
    "half": "an unfinished pause that comes to rest on the dominant",
    "deceptive": "the surprise of the dominant side-stepping to vi instead of I",
    "subtonic": "the modal ♭VII → i close (a whole-step subtonic, not a leading tone)",
    "aeolian": "the characteristic natural-minor i–VI–VII–i loop",
    "axis": "the pop axis loop — deceptive motion (V → vi) inside a repeating loop "
            "that ends on IV, not a phrase-final close",
}


def _cadence_block_spec(tokens, label, mode) -> HarmonyExerciseSpec:
    """The block (root-position) drill for a cadence, in the reference key.

    Reuses the Atlas :func:`function_spec` factory (single definition); the id
    (``atlas_function_*``) is disjoint from the native function-drill ids, so no
    exercise is duplicated.
    """
    return function_spec(tokens, label, mode, [_REFERENCE_TONIC[mode]])


def _cadence_block_leaf_id(tokens, label, mode) -> str:
    """The curriculum leaf id of a cadence's block drill (for cross-linking)."""
    return f"ex:{_wrap_native(_cadence_block_spec(tokens, label, mode)).experiment_id}"


def _exercise_node_from_cadence(entry, atlas, vl_leaf_id, parent: str,
                                order: int) -> CurriculumNode:
    """Build a block-cadence exercise leaf (Atlas-mapped, with derived prose)."""
    tokens, label, mode, ctype, family = entry
    hs = _cadence_block_spec(tokens, label, mode)
    lab = _wrap_native(hs)
    triads = [c.triad for c in compile_exercise(hs).chords]
    ref_key = triads[0].key                                    # e.g. "C major"
    chord_syms = "–".join(t.chord_symbol for t in triads)
    func_path = " → ".join(t.function_label for t in triads)
    bass_path = " → ".join(t.root for t in triads)
    kind_word = "cadence" if family == "type" else "progression"
    cad_nid = atlas.cadence_node_id(list(tokens), mode)        # always resolves
    return CurriculumNode(
        id=f"ex:{lab.experiment_id}", parent=parent, kind="exercise",
        title=f"{label} {ctype} {kind_word} in {ref_key}", order=order,
        subtitle=f"{label} = {chord_syms}  ({func_path})",
        description=(f"The {ctype} {kind_word} {label} in {ref_key}: "
                     f"{chord_syms}."),
        learning_objective=(f"Hear the {ctype} {kind_word} {label} — "
                            f"{_CADENCE_TYPE_BLURB.get(ctype, 'its functional motion')}."),
        theory=(f"{label} in {ref_key} is {chord_syms}. "
                f"Function path: {func_path}. Bass motion: {bass_path}. "
                f"This is {_CADENCE_TYPE_BLURB.get(ctype, 'a cadential motion')}."),
        difficulty=3, estimated_minutes=4,
        atlas_nodes=_dedup(_atlas_refs_for_native(hs)
                           + ([cad_nid] if cad_nid else [])),
        circle_nodes=_circle_refs_for_native(hs),
        keywords=[ctype, "cadence", kind_word, label] + list(tokens),
        related=[vl_leaf_id] if vl_leaf_id else [],
        exercise_count=1, lab_spec=lab,
    )


# ---------------------------------------------------------------------------
# Voice-leading (SATB) version of each cadence — reuses the lab demos, generates
# the rest, so every cadence has a voice-leading lab counterpart.
# ---------------------------------------------------------------------------

def _vl_concept(family: str) -> str:
    """The lab concept of a cadence's SATB render variant, from its catalogue family.

    A two-chord *type* studies the closure itself (``cadence`` -> the resolution
    scene); a longer *progression* studies the voice motion through it
    (``voice_leading`` -> the SATB path scene).  Driven by the catalogue's own
    family field, not by counting chords (ticket 02 / plan F7)."""
    return "cadence" if family == "type" else "voice_leading"


def _make_vl_spec(tokens, label, mode, ctype, family) -> LabExperimentSpec:
    """A four-part (SATB) voice-leading LabExperimentSpec for a cadence."""
    tonic = _REFERENCE_TONIC[mode]
    concept = _vl_concept(family)
    params: Dict = {"pattern": list(tokens)}
    if ctype:
        params["cadence_type"] = ctype
    spec = LabExperimentSpec(
        experiment_id=f"cad_{'_'.join(tokens)}_{_key_slug(tonic)}",
        title=f"{label} in {tonic} {_mode_word(mode)} (voice leading)",
        concept=concept, mode=mode, key=f"{tonic} {_mode_word(mode)}",
        render="voice_leading", parameters=params,
        description=f"The {label} cadence as four-part (SATB) voice leading.",
    )
    spec.validate()
    return spec


def _vl_specs_by_cadence() -> "Dict[tuple, LabExperimentSpec]":
    """``(mode, tokens) -> VL spec``: reuse the matching lab demo, else generate."""
    demos = {(s.mode, tuple(s.parameters.get("pattern", ()))): s
             for s in lab_demo_specs() if s.concept in ("cadence", "voice_leading")}
    out: "Dict[tuple, LabExperimentSpec]" = {}
    for tokens, label, mode, ctype, family in _CADENCE_CATALOG:
        key = (mode, tuple(tokens))
        out[key] = demos.get(key) or _make_vl_spec(tokens, label, mode, ctype, family)
    return out


def _ii6_cadence_spec() -> LabExperimentSpec:
    """The inversions↔cadences bridge drill (ticket 04 / plan G4).

    ii6 as *the* predominant voicing of the authentic cadence: the figured
    token demands F (the third of ii) as the lowest sounding note, so the
    figure is assessed, not decorative, and the bass walks 4̂–5̂–1̂.
    """
    spec = LabExperimentSpec(
        experiment_id="cad_ii6_V_I_C",
        title="ii6–V–I in C major — the first-inversion predominant",
        concept="cadence", mode="major", key="C major", render="block",
        parameters={"pattern": ["ii6", "V", "I"], "cadence_type": "authentic"},
        description=("The authentic cadence with its classic predominant "
                     "voicing: ii6 puts F in the bass so the bass line walks "
                     "4̂–5̂–1̂ (F–G–C). The figure 6 is graded — F must be "
                     "the lowest sounding note."),
    )
    spec.validate()
    return spec


# ---------------------------------------------------------------------------
# Seventh chords (ticket 09 / plan G1a): the V7 tracer drills
# ---------------------------------------------------------------------------
#
# The platform's first tetrad, in three drill families across all 12 major
# keys: *add-the-7th* (play V, then V7 — hear the added dissonance), *tritone
# resolution* (the two-voice 7̂→1̂ + 4̂→3̂ frame as a polyphonic experiment) and
# the full *V7→I*.  Native patterns chunk by key-group exactly like
# ``_function_specs`` (six 2-chord keys per 12-chord page).

_SEVENTH_PATTERNS = [
    (["V", "V7"], "V–V7", "add7",
     "Play the dominant triad, then add the diatonic seventh: the added "
     "note (scale degree 4) forms a tritone with the leading tone"),
    (["V7", "I"], "V7–I", "v7_i",
     "Resolve the full dominant seventh: its tritone closes as 7̂→1̂ and "
     "4̂→3̂ into the tonic"),
    # ticket 10 (G1b): the classic two-five-one with both sevenths sounding
    (["ii7", "V7", "I"], "ii7–V7–I", "ii7_v7_i",
     "The predominant seventh flows into the dominant seventh and resolves: "
     "ii7's seventh (1̂) is V7's fifth away from 7̂→1̂; the smoothest "
     "progression in tonal music"),
]


def _seventh_pattern_specs(tokens, label, slug, blurb,
                           render: str = "block") -> List[HarmonyExerciseSpec]:
    """The chunked 12-major-key specs of one seventh pattern family.

    ``render="block"`` keeps the ticket-09 exercise ids stable (progress
    records point at them); arpeggio variants get their own ``_arp`` ids.
    """
    keys = DEFAULT_MAJOR_KEYS
    chunks = _chunk_keys(keys, len(tokens))
    render_slug = "" if render == "block" else "_arp"
    render_word = "" if render == "block" else ", arpeggio"
    specs = []
    for ci, chunk in enumerate(chunks, start=1):
        keys_label = _keys_label(chunk, keys)
        suffix = "" if len(chunks) == 1 else f" (set {ci})"
        specs.append(HarmonyExerciseSpec(
            exercise_id=f"sevenths_{slug}{render_slug}_major_{ci}",
            title=f"{label} — {keys_label} (major{render_word}){suffix}",
            drill="function", render=render, mode="major",
            pattern=list(tokens), keys=list(chunk),
            description=f"{blurb} ({keys_label})."))
    return specs


#: The four seventh qualities the supported modes actually contain, in the
#: MCQ label order (Mm7, MM7, mm7, ø7).  The fully diminished °7 is absent on
#: purpose: it arrives with harmonic minor (plan G2).
_SEVENTH_QUALITY_ORDER = [
    "dominant_seventh", "major_seventh", "minor_seventh",
    "half_diminished_seventh",
]


def _seventh_quality_specs() -> List[HarmonyExerciseSpec]:
    """Seventh-quality drills across all 12 major keys (mirrors _quality_specs).

    One family per diatonic quality, chunked by key-group where the per-key
    chord count would overflow the one-page cap (MM7 has two per key, mm7
    three).
    """
    specs = []
    for quality in _SEVENTH_QUALITY_ORDER:
        label = SEVENTH_QUALITY_LABELS[quality]
        pretty = quality.replace("_", " ")
        per_key = len(_triads_of_quality(DEFAULT_MAJOR_KEYS[0], "major", quality))
        chunks = _chunk_keys(DEFAULT_MAJOR_KEYS, per_key)
        for ci, chunk in enumerate(chunks, start=1):
            keys_label = _keys_label(chunk, DEFAULT_MAJOR_KEYS)
            suffix = "" if len(chunks) == 1 else f" (set {ci})"
            specs.append(HarmonyExerciseSpec(
                exercise_id=f"sevenths_quality_{quality}_{ci}",
                title=f"{pretty.capitalize()} ({label}) chords — "
                      f"{keys_label} (major){suffix}",
                drill="quality", render="block", mode="major",
                quality=quality, keys=list(chunk),
                description=(f"Every diatonic {pretty} ({label}) chord "
                             f"across {keys_label}.")))
    return specs


#: Keys of the hear-a-seventh drills: three signatures (natural, sharp-side,
#: flat-side) — quality ID is key-independent, so variety beats coverage.
_SEVENTH_EAR_KEYS = ["C", "G", "Eb"]


def _seventh_ear_specs() -> List[HarmonyExerciseSpec]:
    """The hear-a-seventh quality-ID drills (echo + MCQ, ticket 10).

    All seven diatonic sevenths of one key, notation veiled; the learner
    names each quality from the five-option strip (Mm7 / mm7 / MM7 / ø7 /
    °7).  °7 is a distractor: no diatonic °7 exists until harmonic minor.
    """
    tokens = seventh_tokens_for_mode("major")
    specs = []
    for tonic in _SEVENTH_EAR_KEYS:
        specs.append(HarmonyExerciseSpec(
            exercise_id=f"sevenths_ear_quality_{_key_slug(tonic)}",
            title=f"Name that seventh — {tonic} major (by ear)",
            drill="function", render="block", mode="major",
            pattern=list(tokens), keys=[tonic],
            presentation="echo", answer_mode="mcq", mcq_focus="quality",
            description=(f"Listen to each diatonic seventh chord of {tonic} "
                         f"major and name its quality from the strip "
                         f"(Mm7 / mm7 / MM7 / ø7 / °7). The °7 option never "
                         f"sounds here — major has no diatonic fully "
                         f"diminished seventh (that is harmonic minor's "
                         f"vii°7).")))
    return specs


# ---------------------------------------------------------------------------
# Harmonic minor (ticket 13 / plan G2a): a real V in minor
# ---------------------------------------------------------------------------
#
# The raised leading tone gives minor keys the dominant machinery natural
# minor honestly could not claim: V (major), vii° (leading-tone diminished)
# and the i–iv–V–i frame, drilled across all 12 minor keys.  Native patterns
# chunk by key-group exactly like ``_seventh_pattern_specs``; being native
# MIDI drills they get echo (🎧) twins automatically.

_HARMONIC_MINOR_PATTERNS = [
    (["V", "i"], "V–i", "v_i",
     "The real minor-key dominant: harmonic minor's raised 7̂ is a leading "
     "tone, so V (major) resolves to i with the same pull as in major"),
    (["vii°", "i"], "vii°–i", "viio_i",
     "The leading-tone diminished triad on the raised 7̂ resolves up a "
     "semitone into the tonic"),
    (["i", "iv", "V", "i"], "i–iv–V–i", "i_iv_v_i",
     "The full tonal cadence in minor: tonic, subdominant, then the raised "
     "leading tone drives V home to i"),
]


def _harmonic_minor_pattern_specs(tokens, label, slug, blurb,
                                  render: str = "block") -> List[HarmonyExerciseSpec]:
    """The chunked 12-minor-key specs of one harmonic-minor pattern family."""
    keys = DEFAULT_MINOR_KEYS
    chunks = _chunk_keys(keys, len(tokens))
    specs = []
    for ci, chunk in enumerate(chunks, start=1):
        keys_label = _keys_label(chunk, keys)
        suffix = "" if len(chunks) == 1 else f" (set {ci})"
        specs.append(HarmonyExerciseSpec(
            exercise_id=f"hminor_{slug}_{ci}",
            title=f"{label} — {keys_label} (harmonic minor){suffix}",
            drill="function", render=render, mode="harmonic_minor",
            pattern=list(tokens), keys=list(chunk),
            description=f"{blurb} ({keys_label})."))
    return specs


#: The A/B "one accidental changes everything" pairs (reference key A minor,
#: matching the cadence catalogue's ``_REFERENCE_TONIC``): the SAME cadence
#: with the natural ♭7, then the raised ♮7.  Ordered A-then-B so the modal
#: sound is heard first and the leading tone arrives as the change.
_HM_AB_PAIRS = [
    ("bare", [
        (["v", "i"], "v–i", "natural_minor",
         "A: the modal close — v is minor, its ♭7 a whole step below the "
         "tonic, no leading-tone pull"),
        (["V", "i"], "V–i", "harmonic_minor",
         "B: one accidental changes everything — the raised ♮7 makes V "
         "major and gives the cadence a true leading tone"),
    ]),
    ("context", [
        (["i", "iv", "v", "i"], "i–iv–v–i", "natural_minor",
         "A: the full natural-minor progression — every chord inside the "
         "key signature, the close stays modal"),
        (["i", "iv", "V", "i"], "i–iv–V–i", "harmonic_minor",
         "B: the same progression with the raised ♮7 — only one note "
         "differs, and the arrival at i becomes conclusive"),
    ]),
]


def _hm_ab_specs(pair_slug: str) -> List[HarmonyExerciseSpec]:
    """The A/B lesson's paired specs (one pair per group), in A minor."""
    tonic = _REFERENCE_TONIC["natural_minor"]
    entries = dict(_HM_AB_PAIRS)[pair_slug]
    specs = []
    for tokens, label, mode, blurb in entries:
        ab = "a" if mode == "natural_minor" else "b"
        word = "natural" if mode == "natural_minor" else "harmonic"
        specs.append(HarmonyExerciseSpec(
            exercise_id=f"hminor_ab_{pair_slug}_{ab}_{_key_slug(tonic)}",
            title=f"{label} in {tonic} minor ({word} minor)",
            drill="function", render="block", mode=mode,
            pattern=list(tokens), keys=[tonic],
            description=f"{blurb}."))
    return specs


def _tritone_resolution_spec(tonic: str) -> LabExperimentSpec:
    """The two-voice tritone frame of one major key (polyphonic experiment).

    Slice 1 sounds only V7's tritone (bass 7̂, upper 4̂); slice 2 resolves it
    (bass rises 7̂→1̂ while the upper voice falls 4̂→3̂ into the tonic third).
    """
    spec = LabExperimentSpec(
        experiment_id=f"sevenths_tritone_{_key_slug(tonic)}",
        title=f"Tritone resolution in {tonic} major",
        concept="polyphonic_harmony", mode="major", key=f"{tonic} major",
        render="polyphonic",
        parameters={"progression": ["V7", "I"],
                    "upper_degrees": [4, 3],
                    "bass_degrees": [7, 8]},
        description=("V7's engine as a bare two-voice frame: the bass plays "
                     "the leading tone rising 7̂→1̂ while the upper voice "
                     "resolves 4̂→3̂ — the tritone closing into the tonic "
                     "third."),
    )
    spec.validate()
    return spec


def _tritone_curriculum_specs() -> List[LabExperimentSpec]:
    """The tritone-resolution frame in all 12 major keys."""
    return [_tritone_resolution_spec(tonic) for tonic in DEFAULT_MAJOR_KEYS]


# ---------------------------------------------------------------------------
# V7 figured bass + bass-line dictation (ticket 11 / plan G1c, G4, A1 level 5)
# ---------------------------------------------------------------------------

def _seventh_inversion_spec(tonic: str) -> LabExperimentSpec:
    """V7's four voicings (7 · 6/5 · 4/3 · 4/2) in one major key, bass-graded."""
    spec = LabExperimentSpec(
        experiment_id=f"sevenths_inv_{_key_slug(tonic)}",
        title=f"V7 figured-bass inversions in {tonic} major",
        concept="inversion", mode="major", key=f"{tonic} major", render="block",
        parameters={"degree": "V7", "inversions": [0, 1, 2, 3]},
        description=("Read each figure as a performance instruction: 7 puts "
                     "the root in the bass, 6/5 the third (the leading "
                     "tone), 4/3 the fifth, 4/2 the chordal seventh — and "
                     "each drill only passes with that note as the lowest "
                     "sounding one."),
    )
    spec.validate()
    return spec


#: The resolution walk: each V7 figure paired with its classic landing — the
#: outer-voice frame contracts stepwise, and 4/2's bass (the chordal seventh)
#: must fall into I6.
_FIGURED_RESOLUTION_PATTERN = ["V65", "I", "V43", "I", "V42", "I6"]


def _seventh_resolution_spec(tonic: str) -> LabExperimentSpec:
    """V6/5→I, V4/3→I and V4/2→I6 as one six-measure walk in one key."""
    spec = LabExperimentSpec(
        experiment_id=f"sevenths_figres_{_key_slug(tonic)}",
        title=f"Resolve V7 from every figure in {tonic} major",
        concept="cadence", mode="major", key=f"{tonic} major", render="block",
        parameters={"pattern": list(_FIGURED_RESOLUTION_PATTERN),
                    "cadence_type": "authentic"},
        description=("Each inversion resolves by its own bass logic: 6/5's "
                     "leading tone rises to the tonic, 4/3's fifth steps "
                     "either way, and 4/2's chordal seventh MUST fall — "
                     "which is why V4/2 lands on I6, never root-position I. "
                     "Every figured bass is graded as the lowest sounding "
                     "note."),
    )
    spec.validate()
    return spec


#: Bass-dictation keys: three signatures (natural, sharp-side, flat-side) —
#: hearing a bass line is key-independent, so variety beats coverage (matches
#: the hear-a-seventh drills' key choice).
_BASS_DICTATION_KEYS = ["C", "G", "Eb"]

#: ``(pattern, slug, what the bass line teaches)`` — from root motion through
#: a triad figure to the V7 figures, so dictation grows with the figured
#: vocabulary the visual drills just established.
_BASS_DICTATION_PATTERNS = [
    (["I", "IV", "V", "I"], "roots",
     "root motion: the bass walks 1̂–4̂–5̂–1̂"),
    (["ii6", "V", "I"], "ii6",
     "the figured predominant: ii6 bends the bass line to 4̂–5̂–1̂"),
    (["V65", "I", "V42", "I6"], "v7figs",
     "V7's figures: the leading tone rises 7̂–1̂, then the chordal "
     "seventh falls 4̂–3̂"),
]


def _bass_dictation_specs() -> List[LabExperimentSpec]:
    """The bass-line dictation drills (A1 level 5): 3 progressions × 3 keys."""
    specs = []
    for pattern, slug, blurb in _BASS_DICTATION_PATTERNS:
        for tonic in _BASS_DICTATION_KEYS:
            spec = LabExperimentSpec(
                experiment_id=f"bassdict_{slug}_{_key_slug(tonic)}",
                title=(f"Bass-line dictation: {'–'.join(pattern)} "
                       f"in {tonic} major"),
                concept="cadence", mode="major", key=f"{tonic} major",
                render="block",
                parameters={"pattern": list(pattern), "dictation": "bass"},
                description=(f"🎧 Hear the full {'–'.join(pattern)} "
                             f"progression, then play only its bass line — "
                             f"{blurb}. The notation stays hidden until you "
                             f"finish."),
            )
            spec.validate()
            specs.append(spec)
    return specs


# ---------------------------------------------------------------------------
# Inversion curriculum grid (Bug 3: I/ii/IV/V x 12 major + i/iv/v/VII x 12 minor)
# ---------------------------------------------------------------------------

#: The diatonic degrees the inversion curriculum systematically covers per mode.
_MAJOR_INV_DEGREES = ["I", "ii", "IV", "V"]
_MINOR_INV_DEGREES = ["i", "iv", "v", "VII"]


def _demo_spec(experiment_id: str) -> LabExperimentSpec:
    """The lab demo with this id (kept reachable from the curriculum)."""
    return next(s for s in lab_demo_specs() if s.experiment_id == experiment_id)


def _inversion_spec(mode: str, tonic: str, degree: str) -> LabExperimentSpec:
    """One block inversion experiment: root / first / second inversion of a degree."""
    key = f"{tonic} {_mode_word(mode)}"
    spec = LabExperimentSpec(
        experiment_id=f"inv_{mode}_{_key_slug(tonic)}_{degree}",
        title=f"Inversions of {degree} in {key}",
        concept="inversion", mode=mode, key=key, render="block",
        parameters={"degree": degree, "inversions": [0, 1, 2]},
        description=(f"{degree} in {key}: root position (5/3), first (6) and "
                     f"second (6/4) inversion — invariant chord tones, a changing "
                     f"bass."),
    )
    spec.validate()
    return spec


def _inversion_curriculum_specs(mode: str, degree: str) -> List[LabExperimentSpec]:
    """The 12-key inversion grid for one degree.

    The C-major I cell reuses the canonical ``inv_C_I`` demo (so it stays
    reachable and is never duplicated); every other cell is generated.
    """
    keys = DEFAULT_MAJOR_KEYS if mode == "major" else DEFAULT_MINOR_KEYS
    out: List[LabExperimentSpec] = []
    for tonic in keys:
        if mode == "major" and tonic == "C" and degree == "I":
            out.append(_demo_spec("inv_C_I"))
        else:
            out.append(_inversion_spec(mode, tonic, degree))
    return out


# ---------------------------------------------------------------------------
# Tree assembly
# ---------------------------------------------------------------------------

def _grouped_specs() -> "OrderedDict[str, List[HarmonyExerciseSpec]]":
    return default_exercise_groups()


def _by(specs, **pred) -> List[HarmonyExerciseSpec]:
    out = []
    for s in specs:
        if all(getattr(s, k) == v for k, v in pred.items()):
            out.append(s)
    return out


def _chain_siblings(nodes: List[CurriculumNode]) -> None:
    """Set recommended_next / prerequisites along an ordered sibling list."""
    for i, n in enumerate(nodes):
        if i + 1 < len(nodes):
            n.recommended_next = nodes[i + 1].id
        if i > 0:
            n.prerequisites = _dedup(n.prerequisites + [nodes[i - 1].id])


def _rollup(node: CurriculumNode) -> int:
    """Compute exercise_count for every non-leaf (descendant exercise leaves)."""
    if node.kind == "exercise":
        node.exercise_count = 1
        return 1
    total = sum(_rollup(c) for c in node.children)
    node.exercise_count = total
    return total


def build_curriculum() -> CurriculumNode:
    """Build the whole curriculum tree -- deterministic; the canonical source."""
    groups = _grouped_specs()
    major_full = groups[GROUP_MAJOR_FULL_KEY]
    minor_full = groups[GROUP_MINOR_FULL_KEY]
    degree_specs = groups[GROUP_DEGREE]
    quality_specs = groups[GROUP_QUALITY]
    function_specs = groups[GROUP_FUNCTION]
    arpeggios = groups[GROUP_ARPEGGIO]

    # Partition the arpeggio group back into its families (it mixes full_key + degree).
    arp_full_major = _by(arpeggios, drill="full_key", mode="major")
    arp_full_minor = _by(arpeggios, drill="full_key", mode="natural_minor")
    arp_deg_major = _by(arpeggios, drill="horizontal_degree", mode="major")
    arp_deg_minor = _by(arpeggios, drill="horizontal_degree", mode="natural_minor")

    lab_specs = lab_demo_specs()
    lab_motive = [s for s in lab_specs if s.concept == "motive"]
    lab_poly = [s for s in lab_specs if s.concept == "polyphonic_harmony"]

    # Cadence + voice-leading layers are driven by ONE canonical catalogue
    # (_CADENCE_CATALOG): the same 13 cadences appear as block drills and as
    # SATB voice-leading variants, cross-linked, under the single Cadences
    # category (F7).  The Atlas supplies every cadence node + the spec factories.
    atlas = build_atlas()
    vl_map = _vl_specs_by_cadence()
    vl_leaf_of = {(m, tuple(t)): f"ex:{vl_map[(m, tuple(t))].experiment_id}"
                  for t, _l, m, _c, _f in _CADENCE_CATALOG}
    block_leaf_of = {(m, tuple(t)): _cadence_block_leaf_id(t, _l, m)
                     for t, _l, m, _c, _f in _CADENCE_CATALOG}

    def fill_cadences(grp, entries):
        nodes = [
            _exercise_node_from_cadence(
                e, atlas, vl_leaf_of[(e[2], tuple(e[0]))], grp.id, i)
            for i, e in enumerate(entries)]
        _chain_siblings(nodes)
        grp.children.extend(nodes)

    def fill_vl(grp, specs):
        """Fill a voice-leading group: each SATB leaf cross-links its block twin
        and maps onto the SAME Atlas cadence node (one catalogue, two variants)."""
        nodes = [_exercise_node_from_lab(s, grp.id, i, 3)
                 for i, s in enumerate(specs)]
        for n in nodes:
            key = (n.lab_spec.mode, tuple(n.lab_spec.parameters.get("pattern", ())))
            if key in block_leaf_of:
                n.related = _dedup(n.related + [block_leaf_of[key]])
            cad_nid = atlas.cadence_node_id(list(key[1]), key[0])
            if cad_nid:
                n.atlas_nodes = _dedup(n.atlas_nodes + [cad_nid])
        _chain_siblings(nodes)
        grp.children.extend(nodes)

    cat_major = [e for e in _CADENCE_CATALOG if e[2] == "major"]
    cat_minor = [e for e in _CADENCE_CATALOG if e[2] == "natural_minor"]
    types_major = [e for e in cat_major if e[4] == "type"]
    types_minor = [e for e in cat_minor if e[4] == "type"]
    prog_major = [e for e in cat_major if e[4] == "progression"]
    prog_minor = [e for e in cat_minor if e[4] == "progression"]
    vl_major = [vl_map[(m, tuple(t))] for t, _l, m, _c, _f in _CADENCE_CATALOG
                if m == "major"]
    vl_minor = [vl_map[(m, tuple(t))] for t, _l, m, _c, _f in _CADENCE_CATALOG
                if m == "natural_minor"]

    root = CurriculumNode(
        id="cur", parent=None, kind="curriculum",
        title="Harmony Trainer Curriculum", order=0,
        subtitle="The canonical educational layer of the Harmony Trainer.",
        learning_objective=("Master diatonic harmony from scales through cadences, "
                            "voice leading and polyphony."),
        theory=("This curriculum reorganises the original Harmony-Trainer drills "
                "into a pedagogical ontology. Every leaf launches a real trainer "
                "exercise; the Atlas and Circle of Fifths map each concept."),
        keywords=["curriculum", "harmony", "diatonic", "theory"],
    )

    order = 0

    def cat(cid, title, subtitle, objective, difficulty, **kw) -> CurriculumNode:
        nonlocal order
        node = CurriculumNode(
            id=f"cat:{cid}", parent=root.id, kind=kw.pop("kind", "category"),
            title=title, order=order, subtitle=subtitle,
            learning_objective=objective, difficulty=difficulty,
            theory=kw.pop("theory", ""), reserved=kw.pop("reserved", False),
            atlas_nodes=kw.pop("atlas_nodes", []),
            circle_nodes=kw.pop("circle_nodes", []),
            keywords=kw.pop("keywords", []),
        )
        order += 1
        root.children.append(node)
        return node

    def lesson(parent: CurriculumNode, lid, title, subtitle, objective,
               difficulty, **kw) -> CurriculumNode:
        node = CurriculumNode(
            id=f"lesson:{lid}", parent=parent.id, kind=kw.pop("kind", "lesson"),
            title=title, order=len(parent.children), subtitle=subtitle,
            learning_objective=objective, difficulty=difficulty,
            estimated_minutes=kw.pop("minutes", 0),
            theory=kw.pop("theory", ""), reserved=kw.pop("reserved", False),
            atlas_nodes=kw.pop("atlas_nodes", []),
            circle_nodes=kw.pop("circle_nodes", []),
            related=kw.pop("related", []),
            keywords=kw.pop("keywords", []),
        )
        parent.children.append(node)
        return node

    def group(parent: CurriculumNode, gid, title, subtitle, difficulty) -> CurriculumNode:
        node = CurriculumNode(
            id=f"group:{gid}", parent=parent.id, kind="group",
            title=title, order=len(parent.children), subtitle=subtitle,
            difficulty=difficulty,
        )
        parent.children.append(node)
        return node

    def fill_native(grp: CurriculumNode, specs, difficulty) -> None:
        nodes = [_exercise_node_from_native(hs, grp.id, i, difficulty)
                 for i, hs in enumerate(specs)]
        _chain_siblings(nodes)
        grp.children.extend(nodes)

    def fill_lab(grp: CurriculumNode, specs, difficulty) -> None:
        nodes = [_exercise_node_from_lab(s, grp.id, i, difficulty)
                 for i, s in enumerate(specs)]
        _chain_siblings(nodes)
        grp.children.extend(nodes)

    # ===================================================================
    # 1. SCALES  (full_key drills: 48 = 12 major + 12 minor, block + arpeggio)
    # ===================================================================
    scales = cat("scales", "Scales",
                 "Diatonic scales and their seven triads, key by key.",
                 "Internalise the major and natural-minor scales as the ground of "
                 "all diatonic harmony.", 1,
                 keywords=["scale", "key", "diatonic"])
    l_maj = lesson(scales, "scales_major", "Major scales & triads",
                   "The seven diatonic triads of every major key.",
                   "Play and hear the full-key triad set of each major key.", 1,
                   theory="A major scale's diatonic triads are, in order, "
                          "I ii iii IV V vi vii° — major, minor, minor, major, "
                          "major, minor, diminished.")
    fill_native(group(l_maj, "scales_major_block", "Full-key drills (block)",
                       "All 7 triads of each major key, as block chords.", 1),
                major_full, 1)
    fill_native(group(l_maj, "scales_major_arp", "Arpeggios",
                       "All 7 triads of each major key, arpeggiated.", 1),
                arp_full_major, 1)
    l_min = lesson(scales, "scales_minor", "Minor scales & triads",
                   "The seven diatonic triads of every natural-minor key.",
                   "Play and hear the full-key triad set of each minor key.", 2,
                   theory="A natural-minor scale's diatonic triads are "
                          "i ii° III iv v VI VII.")
    fill_native(group(l_min, "scales_minor_block", "Full-key drills (block)",
                       "All 7 triads of each minor key, as block chords.", 2),
                minor_full, 2)
    fill_native(group(l_min, "scales_minor_arp", "Arpeggios",
                       "All 7 triads of each minor key, arpeggiated.", 2),
                arp_full_minor, 2)

    # ===================================================================
    # 2. CHORDS (TRIADS)  (quality drills: 7, major mode)
    # ===================================================================
    chords = cat("chords", "Chords (Triads)",
                 "The four triad qualities and how to recognise them.",
                 "Recognise major, minor, diminished and augmented triads by ear "
                 "and on the staff.", 2,
                 keywords=["triad", "quality", "chord"])
    l_qual = lesson(chords, "triad_qualities", "Triad qualities",
                    "Major, minor, diminished — and the reserved augmented.",
                    "Sort diatonic triads by quality across the keys.", 2,
                    theory="Triad quality is the stacking of thirds: major = M3+m3, "
                           "minor = m3+M3, diminished = m3+m3, augmented = M3+M3.")
    fill_native(group(l_qual, "triads_major", "Major triads",
                      "Every major triad across the keys.", 2),
                _by(quality_specs, quality="major"), 2)
    fill_native(group(l_qual, "triads_minor", "Minor triads",
                      "Every minor triad across the keys.", 2),
                _by(quality_specs, quality="minor"), 2)
    fill_native(group(l_qual, "triads_dim", "Diminished triads",
                      "Every diminished triad (the vii° / ii°) across the keys.", 3),
                _by(quality_specs, quality="diminished"), 3)
    # Augmented is non-diatonic — reserved until harmonic minor (III+) ships.
    group_aug = group(l_qual, "triads_aug", "Augmented triads (reserved)",
                      "Non-diatonic; appears with harmonic minor (III+).", 4)
    group_aug.reserved = True
    group_aug.theory = ("The augmented triad (M3+M3) is not diatonic to the major "
                        "or natural-minor scale; it arrives with harmonic minor's "
                        "III+ and is reserved for that future lesson.")

    # ===================================================================
    # 3. DEGREES / TRANSPOSITION  (horizontal_degree: 28, block + arpeggio)
    # ===================================================================
    _DEGREE_THEORY = ("A degree drill fixes one Roman numeral and transposes it "
                      "through all 12 keys. The spelling and pitches change, but "
                      "the chord's quality and harmonic function stay put — that "
                      "invariance is exactly what builds transpositional fluency.")
    degrees = cat("degrees", "Degrees & Transposition",
                  "One scale degree at a time, transposed through every key.",
                  "Gain transpositional fluency: the same Roman numeral in all 12 "
                  "keys.", 2, keywords=["degree", "transposition", "roman"],
                  theory=_DEGREE_THEORY)
    l_dmaj = lesson(degrees, "degrees_major", "Major degree transposition",
                    "Each major-key degree (I…vii°) across all 12 keys.",
                    "Play a chosen degree in every major key.", 2,
                    theory=_DEGREE_THEORY)
    fill_native(group(l_dmaj, "degrees_major_block", "Block",
                      "Each degree across all 12 major keys (block).", 2),
                _by(degree_specs, mode="major"), 2)
    fill_native(group(l_dmaj, "degrees_major_arp", "Arpeggio",
                      "Each degree across all 12 major keys (arpeggio).", 2),
                arp_deg_major, 2)
    l_dmin = lesson(degrees, "degrees_minor", "Minor degree transposition",
                    "Each minor-key degree (i…VII) across all 12 keys.",
                    "Play a chosen degree in every minor key.", 3,
                    theory=_DEGREE_THEORY)
    fill_native(group(l_dmin, "degrees_minor_block", "Block",
                      "Each degree across all 12 minor keys (block).", 3),
                _by(degree_specs, mode="natural_minor"), 3)
    fill_native(group(l_dmin, "degrees_minor_arp", "Arpeggio",
                      "Each degree across all 12 minor keys (arpeggio).", 3),
                arp_deg_minor, 3)

    # ===================================================================
    # 4. FUNCTIONS  (function drills: 19)
    # ===================================================================
    # All function prose is GENERATED from the shared two-level vocabulary
    # (ticket 01 / plan F1) -- see function_families_prose.
    functions = cat("functions", "Functions",
                    "The three broad function families — harmony in motion.",
                    f"Hear and play functional progressions ({function_flow_short()}).",
                    3,
                    keywords=["function", "tonic", "predominant", "dominant",
                              "progression"],
                    theory=function_families_prose("major"))
    l_fmaj = lesson(functions, "functions_major", "Major functional progressions",
                    "I–IV–V–I, ii–V–I, vi–ii–V–I across the keys.",
                    "Play the canonical major progressions and feel the pull home.",
                    3, theory=function_families_prose("major"))
    fill_native(group(l_fmaj, "functions_major_drills", "Function drills (major)",
                      "The major function patterns across key-groups.", 3),
                _by(function_specs, mode="major"), 3)
    l_fmin = lesson(functions, "functions_minor", "Minor functional progressions",
                    "i–iv–v–i and i–VI–VII–i across the keys.",
                    "Play the canonical natural-minor progressions.", 3,
                    theory=function_families_prose("natural_minor"))
    fill_native(group(l_fmin, "functions_minor_drills", "Function drills (minor)",
                      "The minor function patterns across key-groups.", 3),
                _by(function_specs, mode="natural_minor"), 3)

    # ===================================================================
    # 5. CADENCES  (ONE catalogue, two render variants: block + SATB voice
    #    leading — ticket 02 / plan F7; nothing is duplicated across categories)
    # ===================================================================
    cadences = cat("cadences", "Cadences",
                   "The punctuation of harmony: how phrases arrive (or don't) — "
                   "each cadence as block chords and as SATB voice leading.",
                   "Recognise the cadence types and the functional progressions "
                   "that close a phrase, then voice each one in four parts.", 3,
                   keywords=["cadence", "authentic", "plagal", "deceptive", "half",
                             "subtonic", "axis", "progression", "voice leading",
                             "satb"])
    l_cad = lesson(cadences, "cadence_types", "Two-chord cadences",
                   "Major: V–I, IV–I, I–V, V–vi.  Minor: v–i, VII–i.",
                   "Tell the core cadence types apart by their final bass motion "
                   "and sense of closure.", 3,
                   theory="A cadence type is defined by its final two-chord motion "
                          "and degree of closure: authentic = strong arrival (V→I), "
                          "plagal = the gentle 'amen' (IV→I), half = an unfinished "
                          "pause on V, deceptive = the surprise V→vi, subtonic = the "
                          "modal ♭VII→i (a whole-step subtonic, not a leading tone).",
                   related=["lesson:voice_leading_cadences"])
    fill_cadences(group(l_cad, "cadence_types_major", "Major cadence types",
                        "V–I, IV–I, I–V, V–vi (block, in C major).", 3),
                  types_major)
    fill_cadences(group(l_cad, "cadence_types_minor", "Minor cadence types",
                        "v–i and VII–i (block, in A natural minor).", 3),
                  types_minor)
    l_prog = lesson(cadences, "cadence_progressions", "Cadential progressions",
                    "Major: I–IV–V–I, ii–V–I, vi–ii–V–I, I–V–vi–IV.  "
                    "Minor: iv–v–i, i–iv–v–i, i–VI–VII–i.",
                    f"Hear a complete functional progression ({function_flow_short()}) "
                    "drive a phrase to its cadence.", 3,
                    theory="A cadential progression extends a two-chord cadence into "
                           "a full functional path: predominant prepares the "
                           "dominant, which resolves (or is deceptively denied) at "
                           "the tonic. The bass line carries the motion.",
                    related=["lesson:voice_leading_cadences",
                             "lesson:inversion_cadence_bridge"])
    fill_cadences(group(l_prog, "cadence_prog_major", "Major progressions",
                        "I–IV–V–I, ii–V–I, vi–ii–V–I, I–V–vi–IV (block, in C major).",
                        3), prog_major)
    fill_cadences(group(l_prog, "cadence_prog_minor", "Minor progressions",
                        "iv–v–i, i–iv–v–i, i–VI–VII–i (block, in A natural minor).",
                        3), prog_minor)
    # The SATB render variant of the SAME catalogue lives here too (F7: one
    # catalogue, two render variants under one category; the old separate
    # Voice Leading category duplicated all 13 cadences).
    l_vl = lesson(cadences, "voice_leading_cadences", "Voice-leading (SATB) cadences",
                  "Every cadence above (two-chord type + progression) as four-part "
                  "(SATB) voice motion.",
                  "Voice each cadence and resolve its tendency tones.", 3,
                  theory="Beyond naming chords, a cadence is voice motion: the "
                         "leading tone rises to the tonic, common tones are held, "
                         "and the bass leaps or steps characteristically. Each "
                         "voice-leading cadence pairs with its block version in "
                         "the lessons above.",
                  related=["lesson:cadence_types", "lesson:cadence_progressions"])
    fill_vl(group(l_vl, "voice_leading_major", "Major cadences",
                  "V–I, IV–I, I–V, V–vi, ii–V–I, I–IV–V–I, vi–ii–V–I, I–V–vi–IV "
                  "as SATB voice leading.", 3),
            vl_major)
    fill_vl(group(l_vl, "voice_leading_minor", "Minor cadences",
                  "v–i, VII–i, iv–v–i, i–iv–v–i, i–VI–VII–i in natural minor.", 3),
            vl_minor)

    # ===================================================================
    # 6. SEVENTH CHORDS  (tickets 09+10 / plan G1a+G1b — 32 leaves)
    # ===================================================================
    sevenths = cat("sevenths", "Seventh Chords",
                   "V7's tritone, the full quality vocabulary, and ii7–V7–I.",
                   "Build every diatonic seventh chord, tell the five "
                   "qualities apart by eye and ear, and resolve ii7–V7–I in "
                   "every major key.", 3,
                   keywords=["seventh", "seventh chord", "V7", "dominant seventh",
                             "tetrad", "tritone", "resolution", "ii7",
                             "maj7", "half-diminished"],
                   theory="A seventh chord stacks one more diatonic third on a "
                          "triad (1–3–5–7). The dominant seventh (V7 = M3+m3+m3) "
                          "is the first and most consequential: its third is the "
                          "leading tone and its seventh is scale degree 4, a "
                          "tritone apart — the dissonance whose resolution "
                          "(7̂→1̂, 4̂→3̂) defines the sound of arriving home. "
                          "Around it sit the other diatonic qualities: major "
                          "sevenths on I and IV, minor sevenths on ii, iii and "
                          "vi, and the half-diminished seventh on vii.")
    l_v7 = lesson(sevenths, "dominant_seventh", "The dominant seventh (V7)",
                  "Add the 7th, hear the tritone, resolve it to I — in all 12 "
                  "major keys.",
                  "Play V7 with its tritone under your fingers and resolve it "
                  "correctly to the tonic in every major key.", 3,
                  theory="V7 adds scale degree 4 to the dominant triad. That one "
                         "note changes everything: with the leading tone it "
                         "forms a tritone, so the chord stops being merely "
                         "bright and starts *demanding* resolution — the "
                         "leading tone rises 7̂→1̂ while the seventh falls "
                         "4̂→3̂, landing on the tonic third. Minor keys get "
                         "their true V7 from the raised leading tone — see "
                         "the Harmonic Minor category.",
                  related=["lesson:cadence_progressions",
                           "group:inv_major_dominant"],
                  keywords=["V7", "dominant seventh", "tritone", "leading tone"])
    fill_native(group(l_v7, "sevenths_add7", "Add the 7th (V → V7)",
                      "Play V, then V7: hear the added dissonance arrive.", 3),
                _seventh_pattern_specs(*_SEVENTH_PATTERNS[0]), 3)
    fill_lab(group(l_v7, "sevenths_tritone", "Tritone resolution (two voices)",
                   "The bare frame: bass 7̂→1̂ under upper 4̂→3̂, key by key.", 3),
             _tritone_curriculum_specs(), 3)
    fill_native(group(l_v7, "sevenths_v7_i", "Full resolution (V7 → I)",
                      "The complete dominant seventh resolving to the tonic.", 4),
                _seventh_pattern_specs(*_SEVENTH_PATTERNS[1]), 4)
    l_q7 = lesson(sevenths, "seventh_qualities", "The five seventh qualities",
                  "Mm7, MM7, mm7, ø7 — and the °7 that is not diatonic yet.",
                  "Tell the seventh-chord qualities apart under your fingers "
                  "and by ear, across every major key.", 4,
                  theory="Each diatonic degree owns one seventh quality, and "
                         "the quality is the stacked thirds: Mm7 (dominant, "
                         "M3+m3+m3) only on V; MM7 (major seventh, M3+m3+M3) "
                         "on I and IV; mm7 (minor seventh, m3+M3+m3) on ii, "
                         "iii and vi; ø7 (half-diminished, m3+m3+M3) on vii. "
                         "The fully diminished °7 (m3+m3+m3) is NOT diatonic "
                         "to major or natural minor — it arrives with "
                         "harmonic minor's raised leading tone.",
                  related=["lesson:dominant_seventh", "lesson:interval_layers"],
                  keywords=["seventh quality", "Mm7", "MM7", "mm7",
                            "half-diminished", "ø7", "maj7", "m7"])
    fill_native(group(l_q7, "sevenths_quality", "Quality drills (play)",
                      "Every chord of one seventh quality, key by key.", 4),
                _seventh_quality_specs(), 4)
    fill_native(group(l_q7, "sevenths_quality_ear", "Name that seventh (ear)",
                      "🎧 Hear each seventh chord and name its quality "
                      "(MCQ).", 4),
                _seventh_ear_specs(), 4)
    l_251 = lesson(sevenths, "sevenths_ii_v_i", "ii7–V7–I in every key",
                   "The smoothest progression in tonal music, block and "
                   "arpeggiated.",
                   "Play ii7–V7–I fluently in all 12 major keys.", 4,
                   theory="ii7 adds 1̂ to the predominant; that tone is held "
                          "into V7 (as its fifth) while the tritone forms, "
                          "then resolves 7̂→1̂ and 4̂→3̂. Every voice moves "
                          "by step or stays — which is why ii7–V7–I anchors "
                          "everything from chorales to jazz.",
                   related=["lesson:seventh_qualities",
                            "lesson:cadence_progressions"],
                   keywords=["ii7", "V7", "ii-V-I", "two-five-one",
                             "progression"])
    fill_native(group(l_251, "sevenths_ii7_v7_i_block", "Block chords",
                      "ii7–V7–I as block chords, key-group by key-group.", 4),
                _seventh_pattern_specs(*_SEVENTH_PATTERNS[2]), 4)
    fill_native(group(l_251, "sevenths_ii7_v7_i_arp", "Arpeggiated",
                      "ii7–V7–I arpeggiated: hear each chord tone arrive.", 4),
                _seventh_pattern_specs(*_SEVENTH_PATTERNS[2],
                                       render="arpeggio"), 4)
    l_7more = lesson(sevenths, "sevenths_more", "Seventh inversions & figured bass",
                     "V6/5, V4/3, V4/2 — the figures become performance "
                     "instructions.",
                     "Voice V7 from any figure with the demanded bass as the "
                     "lowest sounding note, and resolve each inversion by its "
                     "own bass logic.", 4,
                     theory="A seventh chord has four bass positions, and the "
                            "figures name them: 7 (root), 6/5 (third — the "
                            "leading tone), 4/3 (fifth), 4/2 (the chordal "
                            "seventh itself). Each figure implies its own "
                            "resolution: 6/5's bass rises a semitone to the "
                            "tonic, while 4/2's bass — the dissonant seventh "
                            "— must FALL by step, which is why V4/2 resolves "
                            "to I6, never to root-position I. Every figure "
                            "here is graded (plan G4's bass grading): the "
                            "drill only passes with the demanded note as the "
                            "lowest sounding one. Harmonic minor's raised "
                            "leading tone now builds the fully diminished "
                            "vii°7 (see the Harmonic Minor category); its "
                            "figured-bass drill is still reserved (plan G2b).",
                     related=["lesson:dominant_seventh",
                              "lesson:chord_inversions",
                              "lesson:bass_dictation"],
                     keywords=["V65", "V43", "V42", "V6/5", "V4/3", "V4/2",
                               "inversion", "figured bass", "third inversion"])
    l_7more.keywords.append("sevenths")
    fill_lab(group(l_7more, "sevenths_figured_inv", "V7 figured-bass inversions",
                   "All four voicings (7 · 6/5 · 4/3 · 4/2), key by key — the "
                   "figured bass is graded.", 4),
             [_seventh_inversion_spec(t) for t in DEFAULT_MAJOR_KEYS], 4)
    fill_lab(group(l_7more, "sevenths_figured_res", "Resolution by figure",
                   "V6/5→I, V4/3→I and V4/2→I6: each inversion resolves by "
                   "its own bass logic.", 4),
             [_seventh_resolution_spec(t) for t in DEFAULT_MAJOR_KEYS], 4)

    # ===================================================================
    # 6b. HARMONIC MINOR  (ticket 13 / plan G2a — 12 leaves)
    # ===================================================================
    hminor = cat("harmonic_minor", "Harmonic Minor",
                 "One accidental changes everything: a real V in minor.",
                 "Raise the 7th degree, hear the leading tone arrive, and "
                 "cadence V–i and vii°–i in every minor key.", 4,
                 keywords=["harmonic minor", "raised seventh", "raised 7",
                           "leading tone", "V in minor", "minor dominant",
                           "vii°", "natural 7"],
                 theory="Natural minor has no leading tone: its 7th degree "
                        "sits a whole step below the tonic, so its v is minor "
                        "and its cadences stay modal. Harmonic minor raises "
                        "that one degree by a semitone — an accidental, not a "
                        "key-signature change — and the dominant machinery of "
                        "major arrives in minor: V becomes a major triad "
                        "whose third is a true leading tone, vii° becomes the "
                        "leading-tone diminished chord, and V–i closes with "
                        "the same pull as V–I. The price of the raised 7̂ is "
                        "the augmented III+ mediant and an augmented-second "
                        "gap in the scale — melodic minor smooths that ascent "
                        "(a later lesson).")
    l_hm_ab = lesson(hminor, "hm_one_accidental",
                     "One accidental changes everything",
                     "The same cadence twice: ♭7 (modal), then ♮7 (tonal) — "
                     "hear what one semitone does.",
                     "Contrast the modal v–i with the tonal V–i in A minor "
                     "and hear the leading tone arrive.", 4,
                     theory="Play the A pair first: v–i, entirely inside the "
                            "key signature, the modal close of natural minor. "
                            "Then the B pair: the SAME cadence with the 7th "
                            "degree raised one semitone. That single "
                            "accidental turns v (minor) into V (major), gives "
                            "the chord a leading tone, and changes the "
                            "arrival at i from a modal shading into a tonal "
                            "conclusion. Each drill has a 🎧 echo twin — "
                            "play A's twin, then B's, to hear the contrast "
                            "with the notation veiled.",
                     related=["group:cadence_types_minor",
                              "lesson:cadence_types"],
                     keywords=["A/B", "flat 7", "natural 7", "subtonic",
                               "leading tone", "modal", "tonal"])
    fill_native(group(l_hm_ab, "hm_ab_bare", "The bare pair (v–i vs V–i)",
                      "Two chords each: the modal close, then the tonal "
                      "close.", 4),
                _hm_ab_specs("bare"), 4)
    fill_native(group(l_hm_ab, "hm_ab_context", "In context (i–iv–v–i vs i–iv–V–i)",
                      "The full progression twice — only one note differs.", 4),
                _hm_ab_specs("context"), 4)
    l_hm_dom = lesson(hminor, "hm_dominant", "The real dominant, key by key",
                      "V–i and vii°–i with the raised leading tone, across "
                      "all 12 minor keys.",
                      "Play V–i and vii°–i with the correct raised 7̂ in "
                      "every minor key.", 4,
                      theory="In each minor key the raised 7th is a different "
                             "accidental — G♯ in A minor, B♮ in C minor, F𝄪 "
                             "in G♯ minor — but the function is identical: a "
                             "semitone below the tonic, demanding resolution "
                             "upward. V places it as the chord's third; vii° "
                             "builds on it directly and resolves the same "
                             "way (vii°→i), a rootless dominant.",
                      related=["lesson:hm_one_accidental",
                               "lesson:dominant_seventh"],
                      keywords=["V-i", "vii°-i", "leading tone", "accidental",
                                "transposition"])
    fill_native(group(l_hm_dom, "hm_v_i", "V → i",
                      "The major dominant resolving home, key-group by "
                      "key-group.", 4),
                _harmonic_minor_pattern_specs(*_HARMONIC_MINOR_PATTERNS[0]), 4)
    fill_native(group(l_hm_dom, "hm_viio_i", "vii° → i",
                      "The leading-tone diminished triad resolving up a "
                      "semitone.", 4),
                _harmonic_minor_pattern_specs(*_HARMONIC_MINOR_PATTERNS[1]), 4)
    l_hm_cad = lesson(hminor, "hm_full_cadence", "i–iv–V–i in every minor key",
                      "The full tonal cadence of the minor mode.",
                      "Play i–iv–V–i with the raised 7̂ fluently in all 12 "
                      "minor keys.", 4,
                      theory="The frame is the minor-mode mirror of "
                             "I–IV–V–I: tonic, subdominant preparation, then "
                             "the harmonic-minor dominant driving home. Only "
                             "V carries the accidental — i and iv stay inside "
                             "the key signature, which is why the raised 7̂ "
                             "leaps out of the texture when it arrives.",
                      related=["lesson:hm_dominant",
                               "lesson:cadence_progressions"],
                      keywords=["i-iv-V-i", "cadence", "progression",
                                "minor keys"])
    fill_native(group(l_hm_cad, "hm_i_iv_v_i", "i–iv–V–i",
                      "The full cadence, three keys per page.", 4),
                _harmonic_minor_pattern_specs(*_HARMONIC_MINOR_PATTERNS[2]), 4)

    # ===================================================================
    # 7. INTERVALS  (theory + cross-links; owns NO exercise -> no duplication)
    # ===================================================================
    intervals = cat("intervals", "Intervals & Interval Layers",
                    "The stacked-thirds 'layer' beneath every triad quality.",
                    "Hear a triad as a stack of thirds (M3+m3 etc.).", 2,
                    kind="category",
                    keywords=["interval", "layer", "third", "M3", "m3"])
    l_int = lesson(intervals, "interval_layers", "Interval layers",
                   "M3+m3 (major), m3+M3 (minor), m3+m3 (diminished).",
                   "Connect each triad quality to its interval layer.", 2,
                   theory="Every triad is two stacked thirds. The order of the "
                          "major and minor third gives the quality: M3 then m3 = "
                          "major; m3 then M3 = minor; two m3 = diminished; two M3 = "
                          "augmented (non-diatonic).",
                   atlas_nodes=[layer_id("M3+m3"), layer_id("m3+M3"),
                                layer_id("m3+m3"), layer_id("M3+M3")],
                   related=["group:triads_major", "group:triads_minor",
                            "group:triads_dim"],
                   keywords=["M3+m3", "m3+M3", "m3+m3", "M3+M3"])
    l_int.reserved = False

    # ===================================================================
    # 8. INVERSIONS  (worked examples + systematic 12-key grid: Bug 3)
    # ===================================================================
    inversions = cat("inversions", "Inversions",
                     "The same chord with a different note in the bass.",
                     "Hear that inversion changes the bass and colour, never the "
                     "chord's identity.", 2,
                     keywords=["inversion", "figured bass", "6/3", "6/4"])
    l_inv = lesson(inversions, "chord_inversions", "Chord inversions",
                   "Root position, first (6) and second (6/4) inversion.",
                   "Compare the three bass positions of one chord.", 2,
                   theory="An inversion re-stacks the same chord tones so a "
                          "different one is in the bass: root position (5/3), first "
                          "inversion (6), second inversion (6/4). The chord's "
                          "identity is unchanged, and its function usually survives "
                          "too — but not always: in the cadential 6/4, a "
                          "second-inversion tonic shape over the dominant's bass "
                          "behaves as a dominant embellishment, not a stable tonic "
                          "(a dedicated lesson on it is coming). C major I therefore "
                          "reads C, C/E, C/G as the bass climbs root → third → "
                          "fifth.")
    fill_lab(group(l_inv, "inversion_intro", "Worked examples",
                   "An arpeggiated walk-through of one chord's three bass positions.",
                   2),
             [_demo_spec("inv_C_V_arp")], 2)
    l_inv_maj = lesson(inversions, "inversions_major", "Major inversions",
                       "Tonic I, predominant ii/IV and dominant V inverted across "
                       "every major key.",
                       "Invert the core major-key triads (I, ii, IV, V) in all 12 "
                       "keys.", 2,
                       theory="The bass climbs root → third → fifth for each degree; "
                              "the figured bass (5/3, 6, 6/4) and slash chord (e.g. "
                              "G, G/B, G/D for V in C) name the bass position while "
                              "the chord's identity stays fixed. Function usually "
                              "survives inversion too — the cadential 6/4 (second "
                              "inversion at a cadence) is the classic exception.")
    fill_lab(group(l_inv_maj, "inv_major_tonic", "Tonic I",
                   "I inverted in all 12 major keys.", 2),
             _inversion_curriculum_specs("major", "I"), 2)
    fill_lab(group(l_inv_maj, "inv_major_predominant", "Predominant ii / IV",
                   "ii and IV inverted in all 12 major keys.", 2),
             _inversion_curriculum_specs("major", "ii")
             + _inversion_curriculum_specs("major", "IV"), 2)
    fill_lab(group(l_inv_maj, "inv_major_dominant", "Dominant V",
                   "V inverted in all 12 major keys.", 2),
             _inversion_curriculum_specs("major", "V"), 2)
    l_inv_min = lesson(inversions, "inversions_minor", "Natural minor inversions",
                       "Tonic i, subdominant iv, dominant v and subtonic VII "
                       "inverted across every natural-minor key.",
                       "Invert the core minor-key triads (i, iv, v, VII) in all 12 "
                       "keys.", 2,
                       theory="The same three bass positions (5/3, 6, 6/4) apply in "
                              "minor; the natural-minor dominant v is itself minor "
                              "and VII is the major subtonic, so their inversions "
                              "colour the modal cadence sound.")
    fill_lab(group(l_inv_min, "inv_minor_tonic", "Tonic i",
                   "i inverted in all 12 natural-minor keys.", 2),
             _inversion_curriculum_specs("natural_minor", "i"), 2)
    fill_lab(group(l_inv_min, "inv_minor_subdominant", "Subdominant iv",
                   "iv inverted in all 12 natural-minor keys.", 2),
             _inversion_curriculum_specs("natural_minor", "iv"), 2)
    fill_lab(group(l_inv_min, "inv_minor_dominant", "Dominant / minor-dominant v",
                   "v inverted in all 12 natural-minor keys.", 2),
             _inversion_curriculum_specs("natural_minor", "v"), 2)
    fill_lab(group(l_inv_min, "inv_minor_subtonic", "Subtonic VII",
                   "VII inverted in all 12 natural-minor keys.", 2),
             _inversion_curriculum_specs("natural_minor", "VII"), 2)
    l_inv_cad = lesson(inversions, "inversion_cadence_bridge",
                       "ii6 at the cadence",
                       "The first inversion at work: ii6 as the classic "
                       "predominant voicing of the authentic cadence.",
                       "Play ii6–V–I with the demanded bass — the figure is a "
                       "performance instruction, not a caption.", 3,
                       theory="Inversions earn their keep at the cadence: "
                              "voicing the predominant as ii6 puts the fourth "
                              "scale degree in the bass, so the bass line walks "
                              "4̂–5̂–1̂ (in C: F–G–C) into the close — the "
                              "smoothest approach to the dominant. The figure 6 "
                              "here is assessed: the drill only passes when the "
                              "third of ii is the lowest sounding note.",
                       related=["lesson:cadence_progressions",
                                "lesson:chord_inversions"],
                       keywords=["ii6", "cadence", "predominant", "figured bass"])
    fill_lab(group(l_inv_cad, "inv_cadence_ii6", "ii6–V–I",
                   "The authentic cadence with a first-inversion predominant "
                   "(bass 4̂–5̂–1̂).", 3),
             [_ii6_cadence_spec()], 3)
    l_dict = lesson(inversions, "bass_dictation", "Bass-line dictation",
                    "🎧 Hear a progression, play only its bass line.",
                    "Track the bass by ear through root motion, figured "
                    "triads and V7's inversions.", 3,
                    theory="The bass line is where inversions live: root "
                           "motion leaps by fourths and fifths, while a "
                           "figure bends the line into steps (ii6 walks "
                           "4̂–5̂–1̂; V4/2's seventh falls into I6). "
                           "Dictation turns that reading skill into a "
                           "hearing skill — the full progression sounds, "
                           "the notation stays hidden, and only the bass "
                           "notes are graded (any octave, one per measure). "
                           "Finishing reveals the score for review.",
                    related=["lesson:chord_inversions",
                             "lesson:inversion_cadence_bridge",
                             "lesson:sevenths_more"],
                    keywords=["dictation", "bass line", "ear training",
                              "🎧", "bass", "aural"])
    fill_lab(group(l_dict, "bass_dictation_drills", "Dictation drills",
                   "🎧 Three bass-line vocabularies (roots, ii6, V7 figures) "
                   "in three keys.", 3),
             _bass_dictation_specs(), 3)

    # ===================================================================
    # 9. MOTIVES  (lab: 2)
    # ===================================================================
    motives = cat("motives", "Motives",
                  "A scale-degree shape that survives transposition.",
                  "Hear a melodic cell keep its identity in every key.", 2,
                  keywords=["motive", "transposition", "melody", "scale degree"])
    l_mot = lesson(motives, "motive_transposition", "Motive transposition",
                   "A degree pattern (e.g. 1–3–5–3) through all 12 keys.",
                   "Play one motive across the circle of fifths.", 2,
                   theory="A motive is a pattern of scale degrees. Transposing it "
                          "changes every pitch but preserves the interval shape — "
                          "and that shape is what a listener recognises.")
    fill_lab(group(l_mot, "motive_cells", "Motive cells",
                   "Tonic-arpeggio and stepwise-descent motives.", 2),
             lab_motive, 2)

    # ===================================================================
    # 10. POLYPHONIC HARMONY  (lab: 3)
    # ===================================================================
    poly = cat("polyphony", "Polyphonic Harmony",
               "Two independent voices that together imply chords.",
               "Hear harmony emerge horizontally from independent lines.", 4,
               keywords=["polyphony", "counterpoint", "two voice", "implied"])
    l_poly = lesson(poly, "two_voice_polyphony", "Two-voice polyphony",
                    "Bass + upper voice whose vertical slices imply a triad.",
                    "Name the chord that two moving voices imply.", 4,
                    theory="In counterpoint no single instant must spell a full "
                           "chord, yet each vertical slice of two voices implies a "
                           "harmony — this is how a Bach two-part invention projects "
                           "a chord progression through line.")
    fill_lab(group(l_poly, "polyphonic_examples", "Polyphonic examples",
                   "I–V–I, ii–V–I and a minor i–VII–i.", 4),
             lab_poly, 4)

    # ===================================================================
    # 11. ATLAS  (bridge — opens the Interactive Harmony Atlas)
    # ===================================================================
    atlas_cat = cat("atlas", "Interactive Harmony Atlas",
                    "The map of the whole diatonic system.",
                    "Navigate scales, degrees, qualities, functions and cadences "
                    "as one graph.", 2, kind="category",
                    theory="The Atlas is the navigation layer above the trainer: "
                           "every scale, degree, triad, quality, interval layer, "
                           "function and cadence is a clickable node that launches a "
                           "drill. Selecting a curriculum node highlights its Atlas "
                           "nodes, and clicking the Atlas filters the curriculum.",
                    keywords=["atlas", "map", "graph", "navigation"])
    atlas_cat.related = ["cat:scales", "cat:functions", "cat:cadences"]
    bridge_lesson = lesson(atlas_cat, "atlas_overview",
                           "Open the Atlas", "Browse the full harmonic graph.",
                           "Use the Atlas to explore relationships between drills.",
                           2, kind="reserved", reserved=True)
    bridge_lesson.keywords = ["atlas", "open atlas"]

    # ===================================================================
    # 12. CIRCLE OF FIFTHS  (bridge — opens the Interactive Circle)
    # ===================================================================
    circle_cat = cat("circle", "Circle of Fifths",
                     "Keys arranged by their signatures; relative minors inside.",
                     "Use the circle to see key relationships and launch key drills.",
                     1, kind="category",
                     theory="The circle of fifths orders the keys by accidental "
                            "count. Selecting a curriculum node highlights its keys "
                            "and degrees on the circle; clicking the circle filters "
                            "the curriculum to that key.",
                     keywords=["circle", "fifths", "key signature", "relative minor"])
    circle_lesson = lesson(circle_cat, "circle_overview", "Open the Circle",
                           "Browse keys and relative minors.",
                           "Launch a key's full-key drill from the circle.", 1,
                           kind="reserved", reserved=True)
    circle_lesson.keywords = ["circle", "open circle"]

    # ===================================================================
    # 13. ADVANCED TOPICS  (reserved — the future-expansion seams)
    # ===================================================================
    advanced = cat("advanced", "Advanced Topics (reserved)",
                   "Where the curriculum grows next.",
                   "Preview the reserved expansion: melodic minor, "
                   "modal & jazz harmony, secondary dominants.", 5,
                   kind="reserved", reserved=True,
                   theory="These topics are reserved. The data model already shapes "
                          "for them: a new LabExperimentSpec (or a new theory mode) "
                          "is all each one needs. (Seventh chords graduated with "
                          "the V7 tracer; harmonic minor with ticket 13.)",
                   keywords=["advanced", "reserved", "future"])
    for i, (aid, title, blurb) in enumerate([
        ("melodic_minor", "Melodic minor & III+",
         "The ascending/descending scale forms and the first legitimate "
         "augmented-triad drill."),
        ("modal", "Modal harmony",
         "Dorian, Phrygian, Lydian, Mixolydian colour."),
        ("jazz", "Jazz harmony",
         "Extensions, ii–V–I voicings, tritone substitution."),
        ("secondary", "Secondary dominants",
         "V/V and friends — tonicising a non-tonic degree."),
    ]):
        ln = lesson(advanced, f"adv_{aid}", title, blurb,
                    f"(Reserved) {blurb}", 5, kind="reserved", reserved=True,
                    theory=blurb, keywords=[aid, "reserved"])

    # ===================================================================
    # 14. RESERVED — Real-score analysis & reduction
    # ===================================================================
    reserved = cat("reserved", "Real Score Analysis & Reduction (reserved)",
                   "Analysing real music and its structural skeleton.",
                   "Preview the reserved score-analysis and Schenkerian-reduction "
                   "phases.", 5, kind="reserved", reserved=True,
                   theory="The Atlas ScoreAnalysis contract (HarmonySlice / "
                          "CadenceSpan / PolyphonicTexture) is shaped for this; only "
                          "the analysis algorithm is pending.",
                   keywords=["analysis", "reduction", "schenker", "reserved"])
    lesson(reserved, "real_score_analysis", "Real score analysis",
           "Map an imported score's chords onto the Atlas.",
           "(Reserved) Highlight a Bach/Mozart score's harmony in the Atlas.", 5,
           kind="reserved", reserved=True,
           theory="Feeds vertical slices through identify_triad_from_pitches and "
                  "lands each on an Atlas triad node.",
           keywords=["score", "analysis", "bach", "mozart"])
    lesson(reserved, "reduction", "Reduction (Schenkerian)",
           "Strip a passage to its structural harmonic skeleton.",
           "(Reserved) Expose the load-bearing chords beneath the surface.", 5,
           kind="reserved", reserved=True,
           theory="Reduction ranks chords by structural weight; a supplied skeleton "
                  "already down-compiles to a drill via the reduction concept.",
           keywords=["reduction", "schenker", "prolongation"])

    # -- finalise: chain categories, roll up counts ----------------------
    _chain_siblings(root.children)
    _rollup(root)
    return root


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def _search_terms(node: CurriculumNode) -> List[str]:
    bag = [node.title, node.subtitle, node.description, node.learning_objective]
    bag.extend(node.keywords)
    return [t.lower() for t in bag if t]


def build_search_index(root: CurriculumNode) -> List[Dict]:
    """A flat, JSON-serialisable search index: one entry per node."""
    # path titles (breadcrumb), for display + parent-aware matching
    parents: Dict[str, CurriculumNode] = {}
    for n in root.walk():
        for c in n.children:
            parents[c.id] = n

    def breadcrumb(n: CurriculumNode) -> List[str]:
        out, cur = [], n
        while cur is not None:
            out.append(cur.title)
            cur = parents.get(cur.id)
        return list(reversed(out))

    index = []
    for n in root.walk():
        crumbs = breadcrumb(n)
        index.append({
            "id": n.id,
            "kind": n.kind,
            "title": n.title,
            "path": crumbs,
            "pathText": " › ".join(crumbs),
            "terms": _dedup(_search_terms(n) + [t.lower() for t in crumbs]),
            "reserved": n.reserved,
            "exerciseCount": n.exercise_count,
        })
    return index


def search_curriculum(root: CurriculumNode, query: str, limit: int = 50) -> List[str]:
    """Return node ids matching ``query`` (token-AND over the search index)."""
    q = (query or "").strip().lower()
    if not q:
        return []
    tokens = [t for t in q.replace("-", " ").split() if t]
    index = build_search_index(root)
    scored = []
    for entry in index:
        haystack = " ".join(entry["terms"])
        title_l = entry["title"].lower()
        if all(tok in haystack for tok in tokens):
            # rank: exact title hit > exercise leaf > shallower path
            score = 0
            if q in title_l:
                score -= 100
            if entry["kind"] == "exercise":
                score -= 10
            score += len(entry["path"])
            scored.append((score, entry["id"]))
    scored.sort()
    return [nid for _, nid in scored[:limit]]


# ---------------------------------------------------------------------------
# Cached singleton + structural payload
# ---------------------------------------------------------------------------

#: Build once, deterministically, and cache (mirrors atlas.build_atlas()).
_TREE: Optional[CurriculumNode] = None


def get_curriculum() -> CurriculumNode:
    """Return the shared curriculum tree (built once; deterministic)."""
    global _TREE
    if _TREE is None:
        _TREE = build_curriculum()
    return _TREE


def to_json(root: Optional[CurriculumNode] = None) -> Dict:
    """The structural JSON payload (tree + search index).

    The rich lesson/exercise *pages* are added by
    :func:`harmony.curriculum_explanations.build_curriculum_payload`.
    """
    root = root or get_curriculum()
    return {
        "schema": SCHEMA_VERSION,
        "tree": root.to_payload(),
        "index": build_search_index(root),
        "kinds": list(KINDS),
    }
