"""Interactive Harmony Atlas -- the central theoretical navigation layer.

The Atlas is the visual + theoretical map that sits *above* the Harmony Trainer
(``harmony.exercise_spec`` / ``harmony.musicxml_builder``) and, later, above
cadence- and real-score analysis.  It turns the whole invariant tonal system
into an interactive graph: scales, scale degrees, interval layers, chord
qualities, harmonic functions, transposition, and cadences -- every element
clickable and resolvable to a *playable* :class:`HarmonyExerciseSpec`.

Design rules (the module's contract -- see the Atlas spec, "Implementation
rules"):

* **Single source of truth.**  Nothing here re-encodes a chord table, a quality,
  a Roman numeral, a function, or an interval layer.  Every value is *derived*
  from :mod:`theory.diatonic_harmony` (the pure theory engine) and every
  launchable exercise is a :class:`harmony.exercise_spec.HarmonyExerciseSpec`
  expanded by the existing compiler.  No hard-coded chord lists.
* **Deterministic.**  Same inputs -> identical nodes, edges, views, ids.
* **Pure.**  No Qt / Verovio / MIDI here, so it is unit-testable headlessly and
  serialises to JSON (:meth:`Atlas.to_json`) for any UI (the web Atlas renders
  this payload).
* **Extensible.**  The node/edge ontology (:class:`AtlasNode` / :class:`AtlasEdge`)
  and the reserved :class:`ScoreAnalysis` interface are shaped so that seventh
  chords, harmonic/melodic minor, modal harmony, and automatic score analysis
  (Bach/Mozart/Chopin -> highlight their position in the Atlas) slot in without
  an architectural redesign.

The cadence *progressions* (the token patterns such as ``["ii","V","I"]``) are
shared with the trainer: the canonical ones are imported from
:mod:`harmony.exercise_spec` so they have one definition; the Atlas only adds
the pop ``I-V-vi-IV`` and the two-chord cadence *types* (authentic / plagal /
half / deceptive), which are progressions, not theory tables.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

from theory.diatonic_harmony import (
    DiatonicTriad,
    generate_diatonic_triads,
    generate_scale,
    key_signature_fifths,
    identify_triad_from_pitches,
    note_pc,
    QUALITY_TO_INTERVAL_LAYER,
)
from harmony.exercise_spec import (
    HarmonyExerciseSpec,
    compile_exercise,
    DEFAULT_MAJOR_KEYS,
    DEFAULT_MINOR_KEYS,
    MAX_CHORDS_PER_SPEC,
    _FUNCTION_PATTERNS_MAJOR,
    _FUNCTION_PATTERNS_MINOR,
    _quality_specs as _es_quality_specs,
)
from harmony.harmonic_roles import function_flow_short


SCHEMA_VERSION = "harmony-atlas/v1"

#: The two modes the Atlas currently maps (extensible: harmonic/melodic minor,
#: modes, ... are added by extending the theory engine's ``_MODE_STEPS``).
MODES = ["major", "natural_minor"]

#: Reference tonics used to read the *invariant* per-degree pattern (Part I /
#: the global diatonic map). The pattern is identical in every key -- that is the
#: whole point -- so any key works; C major / A natural minor are the clearest.
_REFERENCE_TONIC = {"major": "C", "natural_minor": "A"}

#: Fixed MIDI span for the Global-map mini-keyboard (Part I keyboard view).
#: B3..G5 (59..79) is the *measured* union of **every** diatonic root-position
#: triad in all 24 keys (not only the two reference keys): Gb major IV = Cb-Eb-Gb
#: voices down to Cb4 (59) while D major vi = B-D-F# reaches F#5 (78); the board
#: extends one white key to G5 (79) so no black key hangs off the right edge.
#: The reference keys (C major / A natural minor) sit inside this span at 60..77,
#: and -- crucially -- so does the concrete triad of *any* synced trainer target,
#: so the single fixed keyboard retargets to the current concrete chord without
#: transposing it out of register (Bug 1 sync parity). (Verified by tests.)
KEYBOARD_RANGE_MIDI = (59, 79)
_BLACK_PCS = frozenset({1, 3, 6, 8, 10})
_SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
#: Black key width as a fraction of a white key (matches keyboard_view.js 0.62).
_BLACK_KEY_WIDTH_RATIO = 0.62

#: Chord-structure one-liners, keyed by triad quality (the m3/M3 stacking order
#: *is* the quality -- the pedagogical point of the deconstruction view).
_STRUCTURE_CAPTION = {
    "major": "Major triad — major third (M3) below, minor third (m3) above.",
    "minor": "Minor triad — minor third (m3) below, major third (M3) above.",
    "diminished": "Diminished triad — two stacked minor thirds (m3 + m3).",
    "augmented": "Augmented triad — two stacked major thirds (M3 + M3).",
}

#: Canonical cadences (Part VI). The major/minor progression patterns are shared
#: with the trainer (single definition); the Atlas adds the pop I-V-vi-IV and the
#: natural-minor iv-v-i (the canonical minor authentic progression, which is not
#: one of the shared trainer function patterns).
#: Each entry: (tokens, label, mode, cadence_type) with the type drawn from
#: :data:`harmony.harmonic_roles.CADENCE_TYPES`.  The axis loop is NOT tagged
#: "deceptive": its V-vi motion is mid-loop and the phrase ends on IV (ticket 02 /
#: plan F2); the V-vi two-chord type below stays the deceptive exemplar.
_EXTRA_CADENCES = [
    (["I", "V", "vi", "IV"], "I–V–vi–IV", "major", "axis"),
    (["iv", "v", "i"], "iv–v–i", "natural_minor", "authentic"),
]

#: Two-chord cadence *types* (Part IX progress dashboard tracks these).
#: Derived as function-drill patterns, not hard-coded chords.  The natural-minor
#: types (v-i, VII-i) join the four major types so every required cadence has an
#: Atlas node the curriculum can map to (Bug 2).
#: Labels use the SAME roman style as the progression cadences (ticket 02 / plan
#: F7: one label style) -- which also avoids the b->f flat substitution _slug()
#: applies to pitch-y words (e.g. "Subtonic" -> "Suftonic"); the word for each
#: type lives in ``cadenceType``, which the UI shows next to the label.
_CADENCE_TYPES = [
    (["V", "I"], "V–I", "major", "authentic"),
    (["IV", "I"], "IV–I", "major", "plagal"),
    (["I", "V"], "I–V", "major", "half"),
    (["V", "vi"], "V–vi", "major", "deceptive"),
    (["v", "i"], "v–i", "natural_minor", "authentic"),
    (["VII", "i"], "VII–i", "natural_minor", "subtonic"),
]

#: Heuristic cadence-type tag for the shared trainer progressions, by label.
_PROGRESSION_TYPE = {
    "I–IV–V–I": "authentic",
    "ii–V–I": "authentic",
    "vi–ii–V–I": "authentic",
    "i–iv–v–i": "authentic",
    "i–VI–VII–i": "aeolian",
}


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------

def _slug(text: str) -> str:
    """Identifier-safe token (``"Bb" -> "Bf"``, ``"vii°" -> "vii"``)."""
    out = (text.replace("#", "s").replace("b", "f")
               .replace("°", "dim").replace("–", "_"))
    return "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in out)


def _mode_short(mode: str) -> str:
    return "major" if mode == "major" else "minor"


def _mode_long(mode: str) -> str:
    if mode == "major":
        return "major"
    if mode == "harmonic_minor":
        return "harmonic minor"
    return "natural minor"


def _keys_for(mode: str) -> List[str]:
    return DEFAULT_MAJOR_KEYS if mode == "major" else DEFAULT_MINOR_KEYS


# ---------------------------------------------------------------------------
# Ontology: nodes and edges (Part X)
# ---------------------------------------------------------------------------

@dataclass
class AtlasNode:
    """A node in the harmonic ontology.

    ``kind`` is one of: ``scale``, ``degree``, ``triad``, ``quality``,
    ``function``, ``layer``, ``cadence``.  ``spec`` (when present) is the
    playable exercise generated when the node is clicked.  ``data`` holds
    kind-specific display fields (roman, chord symbol, tones, layer, ...).
    """

    id: str
    kind: str
    label: str
    data: Dict = field(default_factory=dict)
    spec: Optional[HarmonyExerciseSpec] = None

    def to_dict(self) -> Dict:
        d = {"id": self.id, "kind": self.kind, "label": self.label,
             "data": self.data}
        if self.spec is not None:
            d["spec"] = self.spec.to_dict()
        return d


@dataclass(frozen=True)
class AtlasEdge:
    """A typed, directed relationship between two nodes.

    ``relation`` is one of: ``belongs_to``, ``transposes_to``, ``same_quality``,
    ``same_function``, ``same_interval_layer``, ``precedes``, ``dominant_of``,
    ``subdominant_of``, ``tonic_of``.
    """

    source: str
    target: str
    relation: str

    def to_dict(self) -> Dict:
        return {"source": self.source, "target": self.target,
                "relation": self.relation}


RELATIONS = [
    "belongs_to", "transposes_to", "same_quality", "same_function",
    "same_interval_layer", "precedes", "dominant_of", "subdominant_of",
    "tonic_of",
]


# ---------------------------------------------------------------------------
# Stable node ids
# ---------------------------------------------------------------------------

def scale_id(key: str, mode: str) -> str:
    return f"scale:{key}:{mode}"


def degree_id(mode: str, roman: str) -> str:
    return f"degree:{mode}:{roman}"


def triad_id(key: str, mode: str, degree_index: int) -> str:
    return f"triad:{key}:{mode}:{degree_index}"


def quality_id(quality: str) -> str:
    return f"quality:{quality}"


def function_id(mode: str, function_label: str) -> str:
    return f"function:{mode}:{function_label}"


def layer_id(layer: str) -> str:
    return f"layer:{layer}"


def cadence_id(slug: str) -> str:
    return f"cadence:{slug}"


# ---------------------------------------------------------------------------
# Spec factories -- every clickable element resolves to one of these.
# These construct HarmonyExerciseSpec instances (the public trainer API);
# they never re-implement compilation or theory.
# ---------------------------------------------------------------------------

def full_key_spec(key: str, mode: str, render: str = "block") -> HarmonyExerciseSpec:
    short = _mode_short(mode)
    return HarmonyExerciseSpec(
        exercise_id=f"atlas_fullkey_{mode}_{_slug(key)}_{render}",
        title=f"{key} {short} — all 7 triads ({render})",
        drill="full_key", render=render, mode=mode, key=f"{key} {short}",
        description=f"All seven diatonic triads of {key} {_mode_long(mode)} ({render}).",
    )


def degree_spec(roman: str, mode: str, render: str = "block") -> HarmonyExerciseSpec:
    return HarmonyExerciseSpec(
        exercise_id=f"atlas_degree_{mode}_{_slug(roman)}_{render}",
        title=f"{roman} across all 12 {_mode_long(mode)} keys ({render})",
        drill="horizontal_degree", render=render, mode=mode, degree=roman,
        description=f"The {roman} triad transposed through all 12 {_mode_long(mode)} keys.",
    )


def quality_drills(mode: str) -> "Dict[str, List[HarmonyExerciseSpec]]":
    """Cap-respecting quality recognition drills, grouped by quality.

    Reuses :func:`harmony.exercise_spec._quality_specs`, so the readability
    chunking (every spec stays within :data:`MAX_CHORDS_PER_SPEC` -- a "major
    triads across keys" drill is split into several short specs) lives in exactly
    one place rather than being re-implemented here.  Returns ``quality -> [specs]``.
    """
    out: Dict[str, List[HarmonyExerciseSpec]] = {}
    for spec in _es_quality_specs(mode):
        out.setdefault(spec.quality, []).append(spec)
    return out


def function_spec(tokens: List[str], label: str, mode: str, keys: List[str],
                  render: str = "block") -> HarmonyExerciseSpec:
    keys_label = "all 12 keys" if len(keys) == len(_keys_for(mode)) else ", ".join(keys)
    return HarmonyExerciseSpec(
        exercise_id=f"atlas_function_{_slug(label)}_{mode}_{_slug('_'.join(keys))}",
        title=f"{label} — {keys_label} ({_mode_long(mode)})",
        drill="function", render=render, mode=mode, pattern=list(tokens), keys=list(keys),
        description=f"The {label} progression across {keys_label} ({_mode_long(mode)}).",
    )


# ---------------------------------------------------------------------------
# Node + edge construction
# ---------------------------------------------------------------------------

def _reference_triads(mode: str) -> List[DiatonicTriad]:
    """The 7 diatonic triads of the reference key -- the invariant degree pattern."""
    return generate_diatonic_triads(_REFERENCE_TONIC[mode], mode)


def _degree_romans(mode: str) -> List[str]:
    """Quality-cased Roman numerals per degree, derived from the theory engine."""
    return [t.roman for t in _reference_triads(mode)]


# ---------------------------------------------------------------------------
# Part I keyboard view: per-degree keyboard + interval deconstruction payload.
#
# The Global diatonic map is *key-invariant*, so the keyboard grounds it in the
# reference key (C major / A natural minor) and shows each degree's root-position
# triad. The two stacked thirds are deconstructed into their actual whole/half
# scale steps via the single intervening diatonic tone -- all derived from the
# theory engine (DiatonicTriad + note_pc); no chord theory is re-encoded here.
# ---------------------------------------------------------------------------

def _keyboard_keys() -> List[Dict]:
    """The invariant key geometry of the Global-map keyboard (built once).

    White keys are equal-width flex siblings in the UI; black keys carry a
    Python-computed ``leftPct``/``widthPct`` so the JS does *zero* positioning
    math (and the headless DOM test needs no measurement).
    """
    lo, hi = KEYBOARD_RANGE_MIDI
    white_midis = [m for m in range(lo, hi + 1) if m % 12 not in _BLACK_PCS]
    white_index = {m: i for i, m in enumerate(white_midis)}
    white_w = 100.0 / len(white_midis)
    black_w = white_w * _BLACK_KEY_WIDTH_RATIO
    keys: List[Dict] = []
    for m in range(lo, hi + 1):
        pc = m % 12
        is_black = pc in _BLACK_PCS
        key: Dict = {
            "midi": m, "pc": pc, "name": _SHARP_NAMES[pc],
            "octave": m // 12 - 1, "isBlack": is_black,
        }
        if is_black:
            # Centre the black key on the boundary above its white neighbour.
            center = (white_index[m - 1] + 1) * white_w
            key["leftPct"] = round(center - black_w / 2.0, 4)
            key["widthPct"] = round(black_w, 4)
        keys.append(key)
    return keys


def _third_payload(position: str, layer_name: str, from_name: str,
                   from_midi: int, to_name: str, to_midi: int,
                   step_name: str) -> Dict:
    """One stacked third, deconstructed into its two ordered whole/half steps.

    Step sizes come from the *actual* semitone deltas across the intervening
    diatonic tone (not from the interval name), so the whole/half ORDER is
    correct per degree (e.g. C major's V splits its m3 B-D as H+W, while ii
    splits its m3 D-F as W+H).
    """
    total = (note_pc(to_name) - note_pc(from_name)) % 12      # 3 (m3) or 4 (M3)
    s1 = (note_pc(step_name) - note_pc(from_name)) % 12       # 1 (H) or 2 (W)
    s2 = total - s1
    quality = {3: "minor", 4: "major"}.get(total, "other")

    def _step(size: int) -> Dict:
        return {"size": size, "name": "W" if size == 2 else "H"}

    return {
        "position": position,
        "name": layer_name,                # "M3" / "m3" -- straight from the engine
        "semitones": total,
        "quality": quality,
        "fromName": from_name, "fromMidi": from_midi,
        "toName": to_name, "toMidi": to_midi,
        "stepName": step_name, "stepMidi": from_midi + s1,
        "scalePath": [from_name, step_name, to_name],
        "steps": [_step(s1), _step(s2)],
        # endpoints + passing tone -- the keys to pulse when the block is hovered.
        "flashMidis": [from_midi, from_midi + s1, to_midi],
    }


def _keyboard_payload(t: DiatonicTriad) -> Dict:
    """Keyboard + interval-deconstruction payload for one diatonic degree."""
    names = list(t.pitches)               # [root, third, fifth] spelled
    midis = list(t.midi_pitches)          # root-position MIDI (root in octave 4)
    scale = t.scale_pitches               # parent scale's 7 spelled pitch classes
    i = t.degree_index
    lower_name, upper_name = t.interval_layer.split("+")   # e.g. "M3", "m3"
    # A diatonic third spans exactly two scale steps; the single passing tone is
    # the scale degree between the chord tones.
    lower = _third_payload("lower", lower_name, names[0], midis[0],
                           names[1], midis[1], scale[(i + 1) % 7])
    upper = _third_payload("upper", upper_name, names[1], midis[1],
                           names[2], midis[2], scale[(i + 3) % 7])
    return {
        "referenceKey": _REFERENCE_TONIC[t.mode],
        "referenceLabel": t.key,          # "C major" / "A natural minor" / "B natural minor"
        "roman": t.roman,                 # so a synced concrete chord captions its degree
        "chordSymbol": t.chord_symbol,    # "C" / "Bm" / "Gb" (concrete-triad caption)
        "quality": t.chord_quality,
        "intervalLayer": t.interval_layer,
        "chord": {
            "root":  {"midi": midis[0], "name": names[0], "pc": note_pc(names[0])},
            "third": {"midi": midis[1], "name": names[1], "pc": note_pc(names[1])},
            "fifth": {"midi": midis[2], "name": names[2], "pc": note_pc(names[2])},
        },
        "thirds": [lower, upper],
        "structure": _STRUCTURE_CAPTION.get(t.chord_quality, ""),
    }


def _build_nodes_and_edges() -> Tuple["OrderedDict[str, AtlasNode]", List[AtlasEdge]]:
    nodes: "OrderedDict[str, AtlasNode]" = OrderedDict()
    edges: List[AtlasEdge] = []
    edge_seen = set()

    def add_node(node: AtlasNode) -> None:
        nodes[node.id] = node

    def add_edge(source: str, target: str, relation: str) -> None:
        key = (source, target, relation)
        if key in edge_seen:
            return
        edge_seen.add(key)
        edges.append(AtlasEdge(source, target, relation))

    # --- quality + interval-layer nodes (derived 1:1 from the theory table) ---
    # Diatonic content only ever produces these three; augmented is reserved
    # (it appears once we add e.g. harmonic minor's III+), so we expose it as a
    # node but mark it non-diatonic so the UI can show it greyed/optional.
    for quality, layer in QUALITY_TO_INTERVAL_LAYER.items():
        diatonic = quality in ("major", "minor", "diminished")
        add_node(AtlasNode(
            id=quality_id(quality), kind="quality", label=quality,
            data={"intervalLayer": layer, "diatonic": diatonic},
        ))
        add_node(AtlasNode(
            id=layer_id(layer), kind="layer", label=layer,
            data={"quality": quality, "diatonic": diatonic},
        ))
        add_edge(quality_id(quality), layer_id(layer), "same_interval_layer")

    # --- degree nodes (abstract, per mode) + function nodes ------------------
    for mode in MODES:
        ref = _reference_triads(mode)
        for t in ref:
            d_id = degree_id(mode, t.roman)
            add_node(AtlasNode(
                id=d_id, kind="degree", label=t.roman,
                data={
                    "mode": mode,
                    "roman": t.roman,
                    "degreeNumber": t.degree_number,
                    "degreeIndex": t.degree_index,
                    "quality": t.chord_quality,
                    "intervalLayer": t.interval_layer,
                    "functionLabel": t.function_label,
                    "scaleDegreeName": t.scale_degree_name,
                },
                spec=degree_spec(t.roman, mode),
            ))
            f_id = function_id(mode, t.function_label)
            if f_id not in nodes:
                add_node(AtlasNode(
                    id=f_id, kind="function", label=t.function_label,
                    data={"mode": mode, "functionLabel": t.function_label,
                          "romans": []},
                ))
            nodes[f_id].data["romans"].append(t.roman)
            # degree -> quality / layer / function (invariant relationships)
            add_edge(d_id, quality_id(t.chord_quality), "same_quality")
            add_edge(d_id, layer_id(t.interval_layer), "same_interval_layer")
            add_edge(d_id, f_id, "same_function")

        # functional relationships at the degree level (T/S/D gravity).
        tonic_roman = ref[0].roman  # I or i
        for t in ref:
            d_id = degree_id(mode, t.roman)
            if t.degree_index == 0:
                continue
            fl = t.function_label
            if fl == "dominant":
                add_edge(d_id, degree_id(mode, tonic_roman), "dominant_of")
            elif fl in ("subdominant", "predominant"):
                add_edge(d_id, degree_id(mode, tonic_roman), "subdominant_of")
            elif fl == "tonic":
                add_edge(d_id, degree_id(mode, tonic_roman), "tonic_of")

    # --- scale + concrete triad nodes (24 keys x 7 degrees) ------------------
    for mode in MODES:
        keys = _keys_for(mode)
        for key in keys:
            scale = generate_scale(key, mode)
            s_id = scale_id(key, mode)
            add_node(AtlasNode(
                id=s_id, kind="scale", label=scale.key,
                data={
                    "key": key,
                    "mode": mode,
                    "tonic": scale.tonic,
                    "scalePitches": list(scale.scale_pitches),
                    "fifths": scale.fifths,
                },
                spec=full_key_spec(key, mode),
            ))
            for t in generate_diatonic_triads(key, mode):
                t_id = triad_id(key, mode, t.degree_index)
                add_node(AtlasNode(
                    id=t_id, kind="triad",
                    label=f"{t.chord_symbol} ({t.roman})",
                    data={
                        "key": key,
                        "mode": mode,
                        "roman": t.roman,
                        "degreeIndex": t.degree_index,
                        "degreeNumber": t.degree_number,
                        "root": t.root,
                        "chordSymbol": t.chord_symbol,
                        "quality": t.chord_quality,
                        "chordTones": list(t.pitches),
                        "intervalLayer": t.interval_layer,
                        "functionLabel": t.function_label,
                        "scaleDegreeName": t.scale_degree_name,
                    },
                    # Clicking a concrete chord practises its key in context;
                    # the focus index lets the UI/trainer jump to this chord.
                    spec=full_key_spec(key, mode),
                ))
                nodes[t_id].data["focusDegreeIndex"] = t.degree_index
                add_edge(t_id, s_id, "belongs_to")
                add_edge(t_id, degree_id(mode, t.roman), "belongs_to")
                add_edge(t_id, quality_id(t.chord_quality), "same_quality")
                add_edge(t_id, function_id(mode, t.function_label), "same_function")
                add_edge(t_id, layer_id(t.interval_layer), "same_interval_layer")

        # transposes_to: chain each degree across the circle of keys.
        for di in range(7):
            for i in range(len(keys) - 1):
                add_edge(triad_id(keys[i], mode, di),
                         triad_id(keys[i + 1], mode, di), "transposes_to")

    # --- cadence nodes (Part VI) + cadence types (Part IX) -------------------
    shared = ([(toks, lab, "major") for toks, lab in _FUNCTION_PATTERNS_MAJOR]
              + [(toks, lab, "natural_minor") for toks, lab in _FUNCTION_PATTERNS_MINOR])
    for toks, label, mode in shared:
        ctype = _PROGRESSION_TYPE.get(label, "other")
        _add_cadence(nodes, edges, edge_seen, add_node, add_edge,
                     toks, label, mode, ctype, family="progression")
    for toks, label, mode, ctype in _EXTRA_CADENCES:
        _add_cadence(nodes, edges, edge_seen, add_node, add_edge,
                     toks, label, mode, ctype, family="progression")
    for toks, label, mode, ctype in _CADENCE_TYPES:
        _add_cadence(nodes, edges, edge_seen, add_node, add_edge,
                     toks, label, mode, ctype, family="type")

    return nodes, edges


def _add_cadence(nodes, edges, edge_seen, add_node, add_edge,
                 tokens, label, mode, ctype, family) -> None:
    """Build a cadence node, derive its chords in the reference key, link precedes."""
    ref_key = _REFERENCE_TONIC[mode]
    # Realise the progression in the reference key for display + 'precedes' edges.
    spec = function_spec(tokens, label, mode, [ref_key])
    compiled = compile_exercise(spec)
    chords = [
        {"roman": c.triad.roman, "chordSymbol": c.triad.chord_symbol,
         "chordTones": list(c.triad.pitches), "functionLabel": c.triad.function_label,
         "degreeIndex": c.triad.degree_index}
        for c in compiled.chords
    ]
    cid = cadence_id(f"{_slug(label)}_{mode}")
    add_node(AtlasNode(
        id=cid, kind="cadence", label=label,
        data={
            "mode": mode,
            "tokens": list(tokens),
            "cadenceType": ctype,
            "family": family,                 # 'progression' | 'type'
            "referenceKey": ref_key,
            "chords": chords,
            "functionPath": [c["functionLabel"] for c in chords],
        },
        spec=spec,
    ))
    # precedes: chord i -> chord i+1 (functional motion), linking the abstract degrees.
    for a, b in zip(compiled.chords, compiled.chords[1:]):
        add_edge(degree_id(mode, a.triad.roman),
                 degree_id(mode, b.triad.roman), "precedes")


# ---------------------------------------------------------------------------
# Learning path (Part XI) and which level a spec belongs to
# ---------------------------------------------------------------------------

LEARNING_PATH = [
    {"level": 1, "id": "scales", "title": "Scales",
     "detail": "Hear and play each major / natural-minor scale."},
    {"level": 2, "id": "triads", "title": "Triads",
     "detail": "All seven diatonic triads of every key."},
    {"level": 3, "id": "interval_layers", "title": "Interval layers",
     "detail": "Recognise M3+m3 / m3+M3 / m3+m3 stacking."},
    {"level": 4, "id": "transposition", "title": "Transposition",
     "detail": "The same degree / pattern across all keys."},
    {"level": 5, "id": "functions", "title": "Functions",
     "detail": f"Function-family recognition ({function_flow_short()})."},
    {"level": 6, "id": "cadences", "title": "Cadences",
     "detail": "Authentic, plagal, deceptive and full progressions."},
    {"level": 7, "id": "real_music", "title": "Real music",
     "detail": "Harmonic analysis of real scores (future)."},
]

#: Map a drill type -> learning-path level id. (Quality drills exercise the
#: interval-layer/quality distinction; function drills exercise functions.)
_DRILL_TO_LEVEL = {
    "full_key": "triads",
    "horizontal_degree": "transposition",
    "quality": "interval_layers",
    "function": "functions",
}


def level_for_spec(spec: HarmonyExerciseSpec) -> str:
    """Which learning-path level a spec belongs to (Part XI / Part VII)."""
    return _DRILL_TO_LEVEL.get(spec.drill, "triads")


# ---------------------------------------------------------------------------
# Reserved real-score analysis interface (Part VIII) -- design only.
# ---------------------------------------------------------------------------

@dataclass
class HarmonyAnnotation:
    """One analysed vertical slice of a real score (reserved shape).

    The fields mirror a :class:`DiatonicTriad`/atlas-triad so that, once
    implemented, each annotation maps straight onto an Atlas ``triad`` node via
    :meth:`Atlas.node_for_annotation`.
    """

    offset: float                      # musical time / beat position
    measure: int
    key: Optional[str] = None
    mode: Optional[str] = None
    roman: Optional[str] = None
    chord_symbol: Optional[str] = None
    quality: Optional[str] = None
    chord_tones: List[str] = field(default_factory=list)
    function_label: Optional[str] = None
    interval_layer: Optional[str] = None
    cadence_type: Optional[str] = None


class ScoreAnalysis:
    """Reserved interface for real-score harmonic analysis (Part VIII).

    Implementations will feed vertical slices of an imported score through
    :func:`theory.diatonic_harmony.identify_triad_from_pitches` (already the
    seed) and return :class:`HarmonyAnnotation` objects that the Atlas can
    highlight in place.  Nothing is implemented yet -- the methods raise so the
    contract is explicit and callers can program against it now.

    Future inputs: Bach preludes, Mozart sonatas, Chopin preludes.
    """

    def analyze_score(self, score_path: str) -> List[HarmonyAnnotation]:
        raise NotImplementedError(
            "Real-score analysis is reserved (Part VIII). "
            "Will return ordered HarmonyAnnotation slices.")

    def extract_harmony(self, score_path: str) -> List[HarmonyAnnotation]:
        raise NotImplementedError(
            "extract_harmony is reserved (Part VIII). "
            "Will return per-slice chord identification.")

    def extract_functions(self, score_path: str) -> List[str]:
        raise NotImplementedError(
            "extract_functions is reserved (Part VIII). "
            "Will return the per-slice harmonic-function path.")

    def extract_cadences(self, score_path: str) -> List[Dict]:
        raise NotImplementedError(
            "extract_cadences is reserved (Part VIII). "
            "Will return detected cadence spans (type + location).")

    def extract_textures(self, score_path: str) -> "List[PolyphonicTexture]":
        raise NotImplementedError(
            "extract_textures is reserved (Part VIII). "
            "Will return the score's per-measure PolyphonicTexture (voices + "
            "vertical slices + implied harmonies); cf. the Music Theory Lab's "
            "synthetic polyphony (harmony.lab), which already emits this shape.")

    def extract_cadence_spans(self, score_path: str) -> "List[CadenceSpan]":
        raise NotImplementedError(
            "extract_cadence_spans is reserved (Part VIII). "
            "Will return detected CadenceSpan objects, each convertible to a "
            "launchable drill via cadence_span_to_spec().")


# ---------------------------------------------------------------------------
# The Atlas
# ---------------------------------------------------------------------------

class Atlas:
    """The whole harmonic map: ontology + views, all derived from theory."""

    def __init__(self) -> None:
        self.nodes, self.edges = _build_nodes_and_edges()

    # -- node access -----------------------------------------------------
    def node(self, node_id: str) -> Optional[AtlasNode]:
        return self.nodes.get(node_id)

    def nodes_of_kind(self, kind: str) -> List[AtlasNode]:
        return [n for n in self.nodes.values() if n.kind == kind]

    # -- Part I: global diatonic map ------------------------------------
    def global_map(self, mode: str) -> List[Dict]:
        """The invariant degree table for ``mode`` (degree, quality, layer, function)."""
        rows = []
        for t in _reference_triads(mode):
            n = self.nodes[degree_id(mode, t.roman)]
            rows.append({
                "nodeId": n.id,
                "roman": t.roman,
                "quality": t.chord_quality,
                "intervalLayer": t.interval_layer,
                "functionLabel": t.function_label,
                "scaleDegreeName": t.scale_degree_name,
                "spec": n.spec.to_dict() if n.spec else None,
                "keyboard": _keyboard_payload(t),
            })
        return rows

    # -- Part II: horizontal transposition matrix -----------------------
    def transposition_matrix(self, mode: str) -> Dict:
        """Rows = degrees, columns = keys; each cell is a concrete triad node.

        Each cell also carries the per-degree ``keyboard`` payload for its
        *concrete* triad (same shape as the Global map's reference keyboard), so
        the Global Diatonic Map can retarget its keyboard / interval
        deconstruction to the currently-synced concrete chord rather than staying
        frozen on the reference key (Bug 1 sync parity).
        """
        keys = _keys_for(mode)
        romans = _degree_romans(mode)
        # Build each key's seven triads once (pure/deterministic) so every cell
        # gets a real DiatonicTriad for its keyboard payload without re-generating.
        triads_by_key = {k: generate_diatonic_triads(k, mode) for k in keys}
        rows = []
        for di, roman in enumerate(romans):
            d_node = self.nodes[degree_id(mode, roman)]
            cells = []
            for key in keys:
                t = self.nodes[triad_id(key, mode, di)]
                cells.append({
                    "nodeId": t.id,
                    "key": key,
                    "roman": t.data["roman"],
                    "chordSymbol": t.data["chordSymbol"],
                    "chordTones": t.data["chordTones"],
                    "intervalLayer": t.data["intervalLayer"],
                    "spec": t.spec.to_dict() if t.spec else None,
                    "keyboard": _keyboard_payload(triads_by_key[key][di]),
                })
            rows.append({
                "degreeNodeId": d_node.id,
                "roman": roman,
                "rowSpec": d_node.spec.to_dict() if d_node.spec else None,
                "cells": cells,
            })
        return {"mode": mode, "keys": keys, "rows": rows}

    # -- Part III: quality matrix ---------------------------------------
    def quality_matrix(self, mode: str = "major") -> List[Dict]:
        """For each diatonic quality, every triad of that quality across keys.

        The view *shows* all 12 keys, but the launchable drill respects the
        readability cap: ``drills`` is the cap-respecting split (e.g. major-
        quality across 12 keys becomes several short specs) and ``spec`` is the
        first of those, so a click never launches an oversized exercise.
        """
        keys = _keys_for(mode)
        drills = quality_drills(mode)
        out = []
        for quality in ("major", "minor", "diminished"):
            entries = []
            for key in keys:
                for t in generate_diatonic_triads(key, mode):
                    if t.chord_quality != quality:
                        continue
                    entries.append({
                        "nodeId": triad_id(key, mode, t.degree_index),
                        "key": key,
                        "roman": t.roman,
                        "chordSymbol": t.chord_symbol,
                        "chordTones": list(t.pitches),
                    })
            chunks = drills.get(quality, [])
            out.append({
                "qualityNodeId": quality_id(quality),
                "quality": quality,
                "intervalLayer": QUALITY_TO_INTERVAL_LAYER[quality],
                "spec": chunks[0].to_dict() if chunks else None,
                "specs": [c.to_dict() for c in chunks],
                "entries": entries,
            })
        return out

    # -- Part IV: function map ------------------------------------------
    def function_map(self, mode: str) -> Dict:
        """Columns = keys, rows = function groups; each cell lists that function's chords."""
        keys = _keys_for(mode)
        ref = _reference_triads(mode)
        # Ordered, de-duplicated function labels as they first appear.
        order: List[str] = []
        for t in ref:
            if t.function_label not in order:
                order.append(t.function_label)
        # Romans per function (invariant), for the row's function-drill spec.
        romans_by_fn: Dict[str, List[str]] = {fl: [] for fl in order}
        for t in ref:
            romans_by_fn[t.function_label].append(t.roman)

        rows = []
        for fl in order:
            cells = []
            for key in keys:
                triads = [t for t in generate_diatonic_triads(key, mode)
                          if t.function_label == fl]
                cells.append({
                    "key": key,
                    "chords": [{"nodeId": triad_id(key, mode, t.degree_index),
                                "roman": t.roman, "chordSymbol": t.chord_symbol}
                               for t in triads],
                    "spec": function_spec(romans_by_fn[fl], fl, mode, [key]).to_dict(),
                })
            rows.append({
                "functionNodeId": function_id(mode, fl),
                "functionLabel": fl,
                "romans": romans_by_fn[fl],
                "cells": cells,
            })
        return {"mode": mode, "keys": keys, "rows": rows}

    # -- Part V: interval-layer map -------------------------------------
    def interval_layer_map(self) -> List[Dict]:
        """Each interval-layer formula, its quality, and a recognition drill."""
        drills = quality_drills("major")
        out = []
        for n in self.nodes_of_kind("layer"):
            quality = n.data["quality"]
            chunks = drills.get(quality, [])
            out.append({
                "layerNodeId": n.id,
                "intervalLayer": n.label,
                "quality": quality,
                "diatonic": n.data["diatonic"],
                # Recognition drill = the (cap-respecting) quality drill for that
                # quality in major mode. None for non-diatonic layers (augmented).
                "spec": (chunks[0].to_dict() if n.data["diatonic"] and chunks else None),
            })
        return out

    # -- Part VI: cadence map -------------------------------------------
    def cadence_map(self) -> List[Dict]:
        """Canonical cadences with Roman numerals, chords, type, and a drill."""
        out = []
        for n in self.nodes_of_kind("cadence"):
            keys = _keys_for(n.data["mode"])
            # The cadence realised in every key (Part VI: 'transposition to all keys').
            table = []
            for key in keys:
                compiled = compile_exercise(
                    function_spec(n.data["tokens"], n.label, n.data["mode"], [key]))
                table.append({
                    "key": key,
                    "chords": [c.triad.chord_symbol for c in compiled.chords],
                })
            out.append({
                "cadenceNodeId": n.id,
                "label": n.label,
                "mode": n.data["mode"],
                "family": n.data["family"],
                "cadenceType": n.data["cadenceType"],
                "tokens": n.data["tokens"],
                "referenceChords": n.data["chords"],
                "functionPath": n.data["functionPath"],
                "keysTable": table,
                "spec": n.spec.to_dict() if n.spec else None,
            })
        return out

    # -- Part XI: learning path -----------------------------------------
    def learning_path(self) -> List[Dict]:
        return [dict(level) for level in LEARNING_PATH]

    # -- Part IX: progress map ------------------------------------------
    def progress_map(self, completed_ids: Optional[set] = None) -> Dict:
        """A completion dashboard (Scales / Triads / Functions / Cadences).

        ``completed_ids`` is a set of completed ``exercise_id``s (the trainer /
        UI persists this).  Each category's launchable items are derived from
        the ontology nodes -- nothing hard-coded -- and a completion percentage
        is reported per category and overall.
        """
        completed = completed_ids or set()
        cadence_nodes = self.nodes_of_kind("cadence")
        categories: "OrderedDict[str, List[HarmonyExerciseSpec]]" = OrderedDict([
            ("Scales", [n.spec for n in self.nodes_of_kind("scale") if n.spec]),
            ("Triads", [n.spec for n in self.nodes_of_kind("degree") if n.spec]),
            ("Functions", [n.spec for n in cadence_nodes
                           if n.spec and n.data["family"] == "progression"]),
            ("Cadences", [n.spec for n in cadence_nodes
                          if n.spec and n.data["family"] == "type"]),
        ])

        out_cats = []
        for name, specs in categories.items():
            total = len(specs)
            done = sum(1 for s in specs if s.exercise_id in completed)
            out_cats.append({
                "category": name,
                "total": total,
                "completed": done,
                "percent": round(100.0 * done / total, 1) if total else 0.0,
                "items": [{"exerciseId": s.exercise_id, "title": s.title,
                           "done": s.exercise_id in completed, "spec": s.to_dict()}
                          for s in specs],
            })
        overall_total = sum(c["total"] for c in out_cats)
        overall_done = sum(c["completed"] for c in out_cats)
        return {
            "categories": out_cats,
            "overallPercent": round(100.0 * overall_done / overall_total, 1)
            if overall_total else 0.0,
        }

    # -- Part X: graph ---------------------------------------------------
    def graph(self, include_triads: bool = False) -> Dict:
        """The ontology as nodes + edges.

        By default the concrete per-key ``triad`` nodes (168 of them) are
        omitted so the visual graph stays legible -- the abstract
        degree/quality/function/layer/cadence/scale nodes carry the structure.
        Pass ``include_triads=True`` for the full ontology (used by analysis).
        """
        if include_triads:
            nodes = list(self.nodes.values())
            node_ids = set(self.nodes.keys())
            edges = self.edges
        else:
            nodes = [n for n in self.nodes.values() if n.kind != "triad"]
            node_ids = {n.id for n in nodes}
            edges = [e for e in self.edges
                     if e.source in node_ids and e.target in node_ids]
        return {
            "relations": RELATIONS,
            "nodes": [n.to_dict() for n in nodes],
            "edges": [e.to_dict() for e in edges],
        }

    # -- Part VII: synchronisation --------------------------------------
    def sync(self, target: Dict) -> Dict:
        """Given a trainer payload *target* (one chord), the active Atlas nodes.

        ``target`` is an entry from ``build_trainer_payload``'s ``TARGET_CHORDS``
        (key, mode, roman, quality, intervalLayer, functionLabel, ...).  Returns
        the ids the UI should highlight: current scale, degree, triad, quality,
        interval layer, function -- plus the learning-path level.
        """
        key = _tonic_of(target.get("key", ""))
        mode = target.get("mode") or "major"
        roman = target.get("roman")
        quality = target.get("quality")
        layer = target.get("intervalLayer")
        function = target.get("functionLabel")

        degree_index = target.get("degreeNumber")
        degree_index = (degree_index - 1) if isinstance(degree_index, int) else None

        active = {
            "scale": scale_id(key, mode) if key else None,
            "degree": degree_id(mode, roman) if roman else None,
            "triad": (triad_id(key, mode, degree_index)
                      if key and degree_index is not None else None),
            "quality": quality_id(quality) if quality else None,
            "layer": layer_id(layer) if layer else None,
            "function": function_id(mode, function) if function else None,
        }
        # Only report ids that actually exist in the ontology.
        active = {k: (v if v in self.nodes else None) for k, v in active.items()}
        # cadence position: if the target carries a cadence/group hint, leave for UI.
        return {
            "active": active,
            "activeIds": [v for v in active.values() if v],
            "level": _DRILL_TO_LEVEL.get(target.get("drill", ""), None),
        }

    def node_for_annotation(self, annotation: "HarmonyAnnotation") -> Optional[str]:
        """Map a future :class:`HarmonyAnnotation` onto a triad node id (Part VIII)."""
        if not (annotation.key and annotation.mode and annotation.roman):
            return None
        tonic = _tonic_of(annotation.key)
        for di, roman in enumerate(_degree_romans(annotation.mode)):
            if roman == annotation.roman:
                nid = triad_id(tonic, annotation.mode, di)
                return nid if nid in self.nodes else None
        return None

    # -- related edges (Music Theory Lab "Current Mapping") --------------
    def edges_for(self, node_ids) -> List[Dict]:
        """Every typed edge incident to any id in ``node_ids`` (deduped, ordered).

        Used by the lab's Current Mapping tab to show the relationships of the
        currently-highlighted nodes.  Purely additive; reads ``self.edges`` and
        does not change the ontology.
        """
        wanted = {nid for nid in (node_ids or []) if nid}
        out: List[Dict] = []
        seen = set()
        for e in self.edges:
            if e.source in wanted or e.target in wanted:
                key = (e.source, e.target, e.relation)
                if key in seen:
                    continue
                seen.add(key)
                out.append(e.to_dict())
        return out

    def cadence_node_id(self, tokens, mode: str) -> Optional[str]:
        """The cadence node id whose progression == ``tokens`` in ``mode`` (or None).

        Matches by the realised token list + mode (not by label/slug), so a lab
        cadence experiment can highlight its Atlas cadence node when one exists.
        """
        want = list(tokens or [])
        for n in self.nodes_of_kind("cadence"):
            if n.data.get("mode") == mode and list(n.data.get("tokens", [])) == want:
                return n.id
        return None

    # -- serialisation ---------------------------------------------------
    def to_json(self, completed_ids: Optional[set] = None) -> Dict:
        """The full JSON payload consumed by the web Atlas UI."""
        return {
            "schema": SCHEMA_VERSION,
            "modes": MODES,
            "keys": {"major": DEFAULT_MAJOR_KEYS, "natural_minor": DEFAULT_MINOR_KEYS},
            # key -> full-key spec, so any view can make a key chip launchable.
            "keySpecs": {m: {k: full_key_spec(k, m).to_dict() for k in _keys_for(m)}
                         for m in MODES},
            "globalMap": {m: self.global_map(m) for m in MODES},
            # Invariant key geometry for the Global-map keyboard (shared by all
            # rows; each row's "keyboard" only says which midis to highlight).
            "keyboardKeys": _keyboard_keys(),
            "transpositionMatrix": {m: self.transposition_matrix(m) for m in MODES},
            "qualityMatrix": {m: self.quality_matrix(m) for m in MODES},
            "functionMap": {m: self.function_map(m) for m in MODES},
            "intervalLayerMap": self.interval_layer_map(),
            "cadenceMap": self.cadence_map(),
            "learningPath": self.learning_path(),
            "progress": self.progress_map(completed_ids),
            "graph": self.graph(include_triads=False),
        }


def _tonic_of(key: str) -> str:
    """'Eb minor' / 'Eb' -> 'Eb' (tonic token only)."""
    return key.split()[0] if key else ""


# Module-level convenience: a single shared, deterministic Atlas instance.
_ATLAS: Optional[Atlas] = None


def build_atlas() -> Atlas:
    """Return the shared Atlas (built once; deterministic)."""
    global _ATLAS
    if _ATLAS is None:
        _ATLAS = Atlas()
    return _ATLAS


# ---------------------------------------------------------------------------
# Phase 6: real-score analysis data contracts (design only -- no analysis yet)
# ---------------------------------------------------------------------------
#
# These structures extend the reserved :class:`ScoreAnalysis` interface so that
# later automatic analysis (a Bach prelude, a Mozart sonata) and the Music Theory
# Lab's *synthetic* polyphony (:mod:`harmony.lab`) share ONE shape: each analysed
# vertical sonority becomes a :class:`HarmonySlice`, each detected progression a
# :class:`CadenceSpan`, each contrapuntal passage a :class:`PolyphonicTexture`.
# The module-level adapters convert these onto Atlas nodes / playable drills using
# only the existing helpers (:func:`HarmonyAnnotation` -> :meth:`Atlas.node_for_annotation`,
# :func:`function_spec`), so when real analysis is implemented it already lands on
# the Atlas with zero further plumbing.  Nothing here performs analysis.

@dataclass
class HarmonySlice:
    """One analysed vertical sonority of a score (or a synthetic lab slice).

    Field names follow the reserved Part VIII contract (measure / beat / notes /
    inferred_root / chord_symbol / roman / function / confidence / explanation)
    and add the key/mode/quality/layer/inversion needed to resolve the slice onto
    an Atlas triad node via :func:`slice_to_annotation` + :meth:`Atlas.node_for_annotation`.
    """

    measure: int
    beat: float = 0.0
    notes: List[str] = field(default_factory=list)   # spelled pitches, low -> high
    key: Optional[str] = None
    mode: Optional[str] = None
    inferred_root: Optional[str] = None
    chord_symbol: Optional[str] = None
    roman: Optional[str] = None
    quality: Optional[str] = None
    chord_tones: List[str] = field(default_factory=list)
    function: Optional[str] = None                    # broad T/S/D function label
    interval_layer: Optional[str] = None
    inversion: Optional[int] = None
    confidence: float = 1.0
    explanation: str = ""


@dataclass
class CadenceSpan:
    """A detected (or declared) cadential progression over a measure range."""

    start_measure: int
    end_measure: int
    key: str
    mode: str
    pattern: List[str]                                # tokens, e.g. ["ii","V","I"]
    cadence_type: str = ""    # one of harmony.harmonic_roles.CADENCE_TYPES (subtonic/axis included)
    chords: List[str] = field(default_factory=list)   # chord symbols, in order
    functions: List[str] = field(default_factory=list)  # function labels, in order


@dataclass
class PolyphonicTexture:
    """A contrapuntal passage: independent voices + their verticalised slices."""

    voices: List[List[str]]                           # per-voice spelled pitch sequence
    key: Optional[str] = None
    mode: Optional[str] = None
    measure_offset: int = 0                           # absolute measure of slice 0
    vertical_slices: List[List[str]] = field(default_factory=list)  # per-onset pitches
    implied_harmonies: List[str] = field(default_factory=list)      # per-onset roman/symbol


def slice_to_annotation(sl: "HarmonySlice") -> HarmonyAnnotation:
    """Convert a :class:`HarmonySlice` to a :class:`HarmonyAnnotation`.

    The result feeds the existing :meth:`Atlas.node_for_annotation`, so a slice
    with ``key``/``mode``/``roman`` resolves to the same ``triad`` node the
    trainer/lab flow highlights.
    """
    return HarmonyAnnotation(
        offset=sl.beat,
        measure=sl.measure,
        key=sl.key,
        mode=sl.mode,
        roman=sl.roman,
        chord_symbol=sl.chord_symbol,
        quality=sl.quality,
        chord_tones=list(sl.chord_tones),
        function_label=sl.function,
        interval_layer=sl.interval_layer,
    )


def texture_to_slices(texture: "PolyphonicTexture") -> List["HarmonySlice"]:
    """Verticalise a :class:`PolyphonicTexture` into ordered :class:`HarmonySlice`s.

    Uses :func:`theory.diatonic_harmony.identify_triad_from_pitches` (the
    documented analysis seed) to label a slice when it has three distinct pitch
    classes and a key context; otherwise the harmonic fields are left ``None``
    (no guessing).
    """
    slices_pitches = texture.vertical_slices
    if not slices_pitches and texture.voices:
        # Zip the voices into per-onset vertical slices (truncating to the
        # shortest voice, the well-defined common prefix).
        length = min(len(v) for v in texture.voices)
        slices_pitches = [[v[i] for v in texture.voices] for i in range(length)]

    out: List[HarmonySlice] = []
    for i, pitches in enumerate(slices_pitches):
        sl = HarmonySlice(
            measure=texture.measure_offset + i,
            notes=list(pitches),
            key=texture.key,
            mode=texture.mode,
        )
        if texture.key and len({_pc_of(p) for p in pitches}) >= 3:
            analysis = identify_triad_from_pitches(list(pitches), key=texture.key)
            sl.inferred_root = analysis.root
            sl.chord_symbol = analysis.chord_symbol
            sl.roman = analysis.roman
            sl.quality = (analysis.chord_quality
                          if analysis.chord_quality != "unknown" else None)
            sl.function = analysis.function_label
            sl.interval_layer = analysis.interval_layer or None
            sl.chord_tones = list(pitches)
            sl.explanation = analysis.explanation_text
        if i < len(texture.implied_harmonies):
            sl.roman = sl.roman or texture.implied_harmonies[i]
        out.append(sl)
    return out


def cadence_span_to_spec(span: "CadenceSpan") -> HarmonyExerciseSpec:
    """Convert a :class:`CadenceSpan` into a launchable, cap-guarded drill.

    Reuses :func:`function_spec` (the Atlas factory) so the detected cadence
    becomes the same kind of playable ``function`` exercise the cadence map
    already produces; raises if it would exceed the readability cap.
    """
    label = "–".join(span.pattern)
    spec = function_spec(span.pattern, label, span.mode, [_tonic_of(span.key)])
    spec.validate()
    n = len(compile_exercise(spec))
    if n > MAX_CHORDS_PER_SPEC:
        raise ValueError(
            f"cadence span compiles to {n} chords (> {MAX_CHORDS_PER_SPEC})")
    return spec


def slices_from_lab_experiment(experiment) -> List["HarmonySlice"]:
    """Turn a synthetic ``LabExperiment`` (e.g. polyphonic) into HarmonySlices.

    Proves the Part VIII contract end-to-end *today*: the lab's per-measure
    annotation (which carries the implied/underlying triad's Roman, quality,
    function, and the precomputed ``atlas_triad_id``) is emitted in the same
    :class:`HarmonySlice` shape future real analysis will produce, so
    :func:`slice_to_annotation` + :meth:`Atlas.node_for_annotation` resolve each
    slice to the very node the experiment recorded.  Duck-typed (no import of
    :mod:`harmony.lab`, so the Atlas stays independent of the lab).
    """
    out: List[HarmonySlice] = []
    for measure in getattr(experiment, "measures", []):
        a = measure.annotation
        roman = a.implied_roman or a.roman
        out.append(HarmonySlice(
            measure=measure.index,
            notes=[n.step + ("#" * n.alter if n.alter > 0 else "b" * (-n.alter))
                   for n in (measure.staff1 + measure.staff2) if not n.is_rest],
            key=a.key,
            mode=measure.mode,
            inferred_root=a.root,
            chord_symbol=a.implied_chord or a.chord_symbol,
            roman=roman,
            quality=a.quality,
            chord_tones=list(a.chord_tones),
            function=a.function_label,
            interval_layer=a.interval_layer,
        ))
    return out


def _pc_of(name: str) -> int:
    """Pitch class of a spelled pitch name (octave ignored) -- analysis helper."""
    from theory.diatonic_harmony import note_pc
    return note_pc(name)
