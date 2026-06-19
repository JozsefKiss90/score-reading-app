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
    transpose_degree_pattern,
    _mode_word,
)
from harmony.exercise_spec import (
    HarmonyExerciseSpec,
    compile_exercise,
    normalise_pattern,
    default_exercise_groups,
    MAX_CHORDS_PER_SPEC,
    GROUP_MAJOR_FULL_KEY,
    GROUP_MINOR_FULL_KEY,
    GROUP_DEGREE,
    GROUP_QUALITY,
    GROUP_FUNCTION,
    GROUP_ARPEGGIO,
)
from harmony.lab_spec import LabExperimentSpec
from harmony.lab import lab_demo_specs
from harmony.atlas import (
    scale_id, degree_id, triad_id, quality_id, function_id, layer_id, cadence_id,
    function_spec,
    _CADENCE_TYPES, _EXTRA_CADENCES, _REFERENCE_TONIC,
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
        if include_children:
            d["children"] = [c.to_payload() for c in self.children]
        return d


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


def _atlas_refs_for_native(hs: HarmonyExerciseSpec) -> List[str]:
    """Atlas node ids a native drill highlights -- derived from its compiled chords."""
    refs: List[str] = []
    compiled = compile_exercise(hs)
    for c in compiled.chords:
        t = c.triad
        key = t.key.split()[0]
        refs.append(scale_id(key, hs.mode))
        refs.append(degree_id(hs.mode, t.roman))
        refs.append(triad_id(key, hs.mode, t.degree_index))
        refs.append(quality_id(t.chord_quality))
        refs.append(function_id(hs.mode, t.function_label))
        refs.append(layer_id(t.interval_layer))
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
        tokens = list(p.get("pattern", []))
    elif spec.concept == "polyphonic_harmony":
        tokens = list(p.get("progression", []))
    if tokens:
        roman = normalise_pattern(tokens)
        for t in transpose_degree_pattern(roman, tonic, mode):
            refs.append(degree_id(mode, t.roman))
            refs.append(triad_id(tonic, mode, t.degree_index))
            refs.append(function_id(mode, t.function_label))
            refs.append(quality_id(t.chord_quality))
    return _dedup(refs)


def _circle_ref_key(tonic: str, mode: str) -> str:
    return f"key:{tonic}:{mode}"


def _circle_ref_degree(mode: str, roman: str) -> str:
    return f"degree:{mode}:{roman}"


def _circle_refs_for_native(hs: HarmonyExerciseSpec) -> List[str]:
    refs: List[str] = []
    for key in _spec_keys(hs):
        refs.append(_circle_ref_key(key, hs.mode))
    compiled = compile_exercise(hs)
    for c in compiled.chords:
        refs.append(_circle_ref_degree(hs.mode, c.triad.roman))
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
        tokens = list(p.get("pattern", []))
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
            refs.append(_circle_ref_degree(mode, r))
    return _dedup(refs)


# ---------------------------------------------------------------------------
# Leaf (exercise) builders
# ---------------------------------------------------------------------------

#: Roman-numeral -> harmonic-function word, so a word query ("predominant")
#: reaches the individual function/degree drills, not only their category.
_FUNCTION_WORDS = {
    "I": "tonic", "i": "tonic", "iii": "tonic", "III": "tonic",
    "vi": "tonic", "VI": "tonic",
    "ii": "predominant", "ii°": "predominant", "IV": "predominant", "iv": "predominant",
    "V": "dominant", "v": "dominant", "vii°": "dominant", "VII": "dominant",
}


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
        return (f"Identify and play every {hs.quality} triad across the keys in "
                f"this set.")
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
        return (f"Hear that {p.get('degree', 'I')} keeps its identity as the bass "
                f"moves through root position, first, and second inversion.")
    if spec.concept in ("cadence", "voice_leading"):
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
    return kws


# ---------------------------------------------------------------------------
# Cadence-type exercises (Atlas factories -- ids distinct from the native set)
# ---------------------------------------------------------------------------

def _cadence_type_specs() -> "List[tuple]":
    """``(label, mode, cadence_type, HarmonyExerciseSpec)`` for the cadence drills.

    Reuses the Atlas ``_CADENCE_TYPES`` / ``_EXTRA_CADENCES`` (authentic / plagal
    / half / deceptive / pop), realised in the reference key.  These ids
    (``atlas_function_*``) are disjoint from the native function-drill ids, so no
    exercise is duplicated.
    """
    out = []
    for toks, label, mode, ctype in list(_CADENCE_TYPES) + list(_EXTRA_CADENCES):
        ref_key = _REFERENCE_TONIC[mode]
        spec = function_spec(toks, label, mode, [ref_key])
        out.append((label, mode, ctype, spec))
    return out


def _exercise_node_from_cadence(label, mode, ctype, hs: HarmonyExerciseSpec,
                                parent: str, order: int) -> CurriculumNode:
    lab = _wrap_native(hs)
    node = CurriculumNode(
        id=f"ex:{lab.experiment_id}",
        parent=parent, kind="exercise",
        title=f"{label} cadence ({ctype})", order=order,
        subtitle=f"{'-'.join(hs.pattern or [])} in {hs.keys[0]} {_mode_word(mode)}",
        description=(f"The {ctype} cadence {'-'.join(hs.pattern or [])} in "
                     f"{hs.keys[0]} {_mode_word(mode)}."),
        learning_objective=(f"Recognise the {ctype} cadence by its bass motion and "
                            f"sense of arrival (or denied arrival)."),
        theory=(f"The {ctype} cadence ({'-'.join(hs.pattern or [])}) is defined by "
                f"its final bass motion and degree of closure: authentic = strong "
                f"arrival (V→I), plagal = the gentle 'amen' (IV→I), half = an "
                f"unfinished pause on V, deceptive = the surprise of V→vi."),
        difficulty=3, estimated_minutes=4,
        atlas_nodes=_dedup(_atlas_refs_for_native(hs)
                           + [cadence_id(f"{_cad_slug(label)}_{mode}")]),
        circle_nodes=_circle_refs_for_native(hs),
        keywords=[ctype, "cadence", label] + list(hs.pattern or []),
        exercise_count=1, lab_spec=lab,
    )
    return node


def _cad_slug(label: str) -> str:
    out = (label.replace("#", "s").replace("b", "f")
                .replace("°", "dim").replace("–", "_"))
    return "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in out)


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
    lab_inv = [s for s in lab_specs if s.concept == "inversion"]
    lab_vl = [s for s in lab_specs if s.concept in ("cadence", "voice_leading")]
    lab_vl_major = [s for s in lab_vl if s.mode == "major"]
    lab_vl_minor = [s for s in lab_vl if s.mode == "natural_minor"]
    lab_motive = [s for s in lab_specs if s.concept == "motive"]
    lab_poly = [s for s in lab_specs if s.concept == "polyphonic_harmony"]

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
    _FUNCTION_THEORY = ("Functional harmony groups chords as tonic (rest, I/vi/iii), "
                        "predominant (preparation, ii/IV) and dominant (tension, "
                        "V/vii°). A progression moves T → S → D → T; the dominant's "
                        "pull toward tonic is the engine of tonal music.")
    functions = cat("functions", "Functions",
                    "Tonic, predominant and dominant — harmony in motion.",
                    "Hear and play functional progressions (T / S / D).", 3,
                    keywords=["function", "tonic", "predominant", "dominant",
                              "progression"], theory=_FUNCTION_THEORY)
    l_fmaj = lesson(functions, "functions_major", "Major functional progressions",
                    "I–IV–V–I, ii–V–I, vi–ii–V–I across the keys.",
                    "Play the canonical major progressions and feel the pull home.",
                    3, theory="Tonic (I, vi, iii) is rest; predominant (ii, IV) "
                              "prepares; dominant (V, vii°) creates tension that "
                              "resolves to tonic.")
    fill_native(group(l_fmaj, "functions_major_drills", "Function drills (major)",
                      "The major function patterns across key-groups.", 3),
                _by(function_specs, mode="major"), 3)
    l_fmin = lesson(functions, "functions_minor", "Minor functional progressions",
                    "i–iv–v–i and i–VI–VII–i across the keys.",
                    "Play the canonical natural-minor progressions.", 3,
                    theory="In natural minor the dominant (v) is itself minor, so "
                           "its 7th is a whole-step subtonic rather than a leading "
                           "tone — the modal cadence sound. i–VI–VII–i is the "
                           "characteristic Aeolian loop.")
    fill_native(group(l_fmin, "functions_minor_drills", "Function drills (minor)",
                      "The minor function patterns across key-groups.", 3),
                _by(function_specs, mode="natural_minor"), 3)

    # ===================================================================
    # 5. CADENCES  (Atlas cadence-type drills: authentic/plagal/half/deceptive/pop)
    # ===================================================================
    cadences = cat("cadences", "Cadences",
                   "The punctuation of harmony: how phrases arrive (or don't).",
                   "Recognise authentic, plagal, half and deceptive cadences.", 3,
                   keywords=["cadence", "authentic", "plagal", "deceptive", "half"])
    l_cad = lesson(cadences, "cadence_types", "Two-chord cadences",
                   "Authentic (V–I), plagal (IV–I), half (I–V), deceptive (V–vi).",
                   "Tell the four core cadence types apart by sound.", 3,
                   theory="A cadence is defined by its final bass motion and its "
                          "sense of closure: authentic = strong arrival, plagal = "
                          "gentle 'amen', half = unfinished, deceptive = surprise.")
    cad_nodes = []
    for i, (label, mode, ctype, hs) in enumerate(_cadence_type_specs()):
        cad_nodes.append(_exercise_node_from_cadence(
            label, mode, ctype, hs, l_cad.id, i))
    _chain_siblings(cad_nodes)
    l_cad.children.extend(cad_nodes)
    # Cross-link the lab voice-leading cadences (same harmony, deeper view).
    l_cad.related = [f"lesson:voice_leading_cadences"]

    # ===================================================================
    # 6. INTERVALS  (theory + cross-links; owns NO exercise -> no duplication)
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
    # 7. INVERSIONS  (lab: 2)
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
                          "inversion (6), second inversion (6/4). The chord and its "
                          "function are unchanged.")
    fill_lab(group(l_inv, "inversion_experiments", "Inversion experiments",
                   "Invariant chord tones, a changing bass.", 2),
             lab_inv, 2)

    # ===================================================================
    # 8. VOICE LEADING  (lab: 8)
    # ===================================================================
    voice = cat("voice_leading", "Voice Leading",
                "How the individual voices move between chords.",
                "Connect chords smoothly: common tones held, tendency tones "
                "resolved.", 3,
                keywords=["voice leading", "satb", "leading tone", "common tone"])
    l_vl = lesson(voice, "voice_leading_cadences", "Voice-leading cadences",
                  "Cadences as four-part (SATB) voice motion.",
                  "Voice each cadence and resolve its tendency tones.", 3,
                  theory="Beyond naming chords, a cadence is voice motion: the "
                         "leading tone rises to the tonic, common tones are held, "
                         "and the bass leaps or steps characteristically.",
                  related=["lesson:cadence_types"])
    fill_lab(group(l_vl, "voice_leading_major", "Major cadences",
                   "V–I, IV–I, V–vi, ii–V–I as SATB voice leading.", 3),
             lab_vl_major, 3)
    fill_lab(group(l_vl, "voice_leading_minor", "Minor cadences",
                   "v–i, iv–v–i, VII–i, i–VI–VII–i in natural minor.", 3),
             lab_vl_minor, 3)

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
                   "Preview the reserved expansion: 7th chords, harmonic minor, "
                   "modal & jazz harmony, secondary dominants.", 5,
                   kind="reserved", reserved=True,
                   theory="These topics are reserved. The data model already shapes "
                          "for them: a new LabExperimentSpec (or a new theory mode) "
                          "is all each one needs.",
                   keywords=["advanced", "reserved", "future"])
    for i, (aid, title, blurb) in enumerate([
        ("sevenths", "Seventh chords",
         "Add the seventh: V7's tritone, the ii7–V7–I jazz cadence."),
        ("harmonic_minor", "Harmonic & melodic minor",
         "The raised leading tone, V (major) in minor, and III+."),
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
