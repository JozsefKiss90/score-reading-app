"""Graph -> Drill: turn a graph selection into launchable drill actions.

The mirror of :mod:`harmony.network_projection`.  Given a
:class:`~harmony.harmonic_flow.GraphDrillRequest` (a node / edge / path / constellation
selection) and a built :class:`~harmony.harmonic_network.HarmonicNetwork`, it returns typed
:class:`~harmony.harmonic_flow.LaunchAction` envelopes -- each carrying a validated native
:class:`~harmony.exercise_spec.HarmonyExerciseSpec` dict *and* a preview
:class:`~harmony.harmonic_flow.DrillGraphProjection` so the user sees the constellation, order and
theory-vs-sequence distinction before anything launches (plan section 10.4).

Design rules honoured here:

    * a **key node** offers distinct actions -- *play the tonic chord* (node_identity) is NOT the
      same as *explore all seven triads* (tonal_field) or *tonic family* (functional_neighbourhood);
    * **key-relation edges** (fifth / relative) compile to a *comparison / transposition* drill,
      never an asserted chord progression;
    * **harmonic-motion edges** (resolves_to / prepares / leading_tone_to) compile to a real
      function progression only when both endpoints resolve to supported diatonic triads;
    * a **dominant-seventh node** launches the real V7→I resolution drill (ticket 12 / G1d);
      the V→I triad drill stays alongside it, honestly labelled as the seventh-less reduction.

No theory is re-encoded: every spec comes from the ``harmony.atlas`` factories.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from harmony.exercise_spec import (
    HarmonyExerciseSpec,
    MAX_CHORDS_PER_SPEC,
    compile_exercise,
)
from harmony.harmonic_flow import LaunchAction, GraphDrillRequest
from harmony.harmonic_network import HarmonicNetwork, BROAD_FUNCTION, FUNCTION_LAYOUT_ORDER
from harmony.network_projection import project_harmony_exercise, project_lab_experiment
from harmony.atlas import full_key_spec, function_spec
from theory.diatonic_harmony import generate_diatonic_triads


# Relations that are genuine harmonic *motion* (become a 2-item progression drill).
_MOTION_RELATIONS = frozenset({
    "resolves_to", "leading_tone_to", "prepares", "prolongs", "dominant_of",
})
# Relations between whole keys (become a comparison / transposition, never a progression).
_KEY_RELATIONS = frozenset({"fifth_relation", "relative_minor_of", "relative_major_of"})
# Equivalence relations (become a comparison / classification).
_EQUIVALENCE_RELATIONS = frozenset({"same_function", "same_pitch_class", "shares_scale_with"})


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text).strip("_").lower()


def _parse_key_token(tok: str) -> Tuple[str, str]:
    """``'C'`` -> ``('C','major')``; ``'Am'`` / ``'Cm'`` -> ``(tonic, 'natural_minor')``."""
    tok = tok.strip()
    if len(tok) > 1 and tok.endswith("m") and not tok.endswith("dim"):
        return tok[:-1], "natural_minor"
    return tok, "major"


def _key_context_for(node) -> Optional[Tuple[str, str]]:
    """Best ``(tonic, mode)`` for the key a node lives in, or ``None``."""
    data = getattr(node, "data", {}) or {}
    kind = node.kind
    if kind in ("key_center", "diatonic_triad") or getattr(node, "semantic_level", "") in (
            "key", "chord"):
        if data.get("key"):
            return data["key"], data.get("mode", "major")
    if kind == "major_key":
        return node.spelling, "major"
    if kind == "minor_key":
        return node.spelling, "natural_minor"
    if kind == "dominant_seventh":
        targets = data.get("resolvesTo") or []
        if targets:
            return _parse_key_token(targets[0])
    if kind == "diminished_triad":
        targets = data.get("leadingToneTo") or []
        if targets:
            return _parse_key_token(targets[0])
    return None


def _family_tokens(tonic: str, mode: str) -> "Dict[str, List[str]]":
    """Broad function family -> member Roman tokens for a key (order tonic/dominant/predominant)."""
    fams: Dict[str, List[str]] = {fam: [] for fam in FUNCTION_LAYOUT_ORDER}
    for t in generate_diatonic_triads(tonic, mode):
        fams[BROAD_FUNCTION.get(t.function_label, "tonic")].append(t.roman)
    return fams


# --------------------------------------------------------------------------------------------- #
# Action construction
# --------------------------------------------------------------------------------------------- #

def _trainer_action(action_id: str, label: str, spec: HarmonyExerciseSpec, group: str,
                    interaction_kind: str, network: HarmonicNetwork, *,
                    key_context: Optional[str] = None,
                    reason: str = "") -> LaunchAction:
    """Build a launchable (or cap-unavailable) trainer action with a preview projection."""
    try:
        spec.validate()
        n = len(compile_exercise(spec))
    except Exception as exc:  # malformed spec -> unavailable, never crash the panel
        return LaunchAction(id=action_id, label=label, target="trainer", status="unavailable",
                            semantic_group=group, interaction_kind=interaction_kind,
                            reason=f"invalid spec: {exc}")
    if n > MAX_CHORDS_PER_SPEC:
        return LaunchAction(id=action_id, label=label, target="trainer", status="unavailable",
                            semantic_group=group, interaction_kind=interaction_kind,
                            reason=f"compiles to {n} chords (> cap {MAX_CHORDS_PER_SPEC})")
    override = {"thematic_group": group, "title": label}
    if key_context:
        override["key_context"] = key_context
    try:
        preview = project_harmony_exercise(spec, network, semantic_override=override).to_dict()
    except Exception:
        preview = None
    return LaunchAction(
        id=action_id, label=label, target="trainer", status="launchable",
        semantic_group=group, interaction_kind=interaction_kind,
        spec_type="harmony_exercise", spec=spec.to_dict(), reason=reason,
        preview_projection=preview,
    )


# --------------------------------------------------------------------------------------------- #
# Node actions (plan section 10.1)
# --------------------------------------------------------------------------------------------- #

def _node_actions(node, network: HarmonicNetwork, request: GraphDrillRequest) -> List[LaunchAction]:
    level = getattr(node, "semantic_level", "")
    kind = node.kind
    if node.id.startswith("hn:inv:"):
        return _inversion_node_actions(node, network, request)
    if kind in ("key_center", "major_key", "minor_key") or level == "key":
        return _key_node_actions(node, network, request)
    if kind == "diatonic_triad" or level == "chord":
        return _triad_node_actions(node, network, request)
    if kind == "function_family" or level == "function":
        return _function_node_actions(node, network, request)
    if kind == "dominant_seventh":
        return _dom7_node_actions(node, network, request)
    if kind == "diminished_triad":
        return _dim_node_actions(node, network, request)
    return []


def _key_node_actions(node, network, request) -> List[LaunchAction]:
    ctx = _key_context_for(node)
    if not ctx:
        return []
    tonic, mode = ctx
    key_label = f"{tonic} {'minor' if mode != 'major' else 'major'}"
    render = request.render
    out: List[LaunchAction] = []

    # 1. play the tonic chord (node identity) -- distinct from the full field
    tonic_roman = generate_diatonic_triads(tonic, mode)[0].roman
    out.append(_trainer_action(
        f"act:node:{node.id}:tonic", f"Play the {key_label} tonic chord",
        function_spec([tonic_roman], f"{key_label} tonic", mode, [tonic], render=render),
        "node_identity", "node", network, key_context=key_label,
        reason="one chord: the tonic triad (not the whole key field)"))

    # 2. explore all seven diatonic triads (tonal field)
    out.append(_trainer_action(
        f"act:node:{node.id}:field", f"Explore all seven {key_label} triads",
        full_key_spec(tonic, mode, render=render), "tonal_field", "node", network,
        key_context=key_label))

    # 3-5. function families (enumeration, NOT progression)
    fams = _family_tokens(tonic, mode)
    for fam in FUNCTION_LAYOUT_ORDER:
        toks = fams[fam]
        if not toks:
            continue
        out.append(_trainer_action(
            f"act:node:{node.id}:fam_{fam}", f"{fam.title()} family ({', '.join(toks)})",
            function_spec(toks, f"{fam.title()} family in {key_label}", mode, [tonic],
                          render=render),
            "functional_neighbourhood", "node", network, key_context=key_label,
            reason="family enumeration, not a progression"))

    # 6. common cadence paths (real functional motion)
    for pattern, label in _CADENCE_PATTERNS.get(mode, []):
        out.append(_trainer_action(
            f"act:node:{node.id}:cad_{_slug(label)}", f"Cadence: {label}",
            function_spec(list(pattern), f"{label} in {key_label}", mode, [tonic], render=render),
            "functional_path", "node", network, key_context=key_label))
    return out


_CADENCE_PATTERNS = {
    "major": [(("V", "I"), "V–I"), (("IV", "I"), "IV–I"),
              (("ii", "V", "I"), "ii–V–I")],
    "natural_minor": [(("v", "i"), "v–i"), (("iv", "i"), "iv–i"),
                      (("ii°", "v", "i"), "ii°–v–i")],
}


def _triad_node_actions(node, network, request) -> List[LaunchAction]:
    data = node.data or {}
    ctx = _key_context_for(node)
    if not ctx:
        return []
    tonic, mode = ctx
    roman = data.get("roman", "I")
    symbol = data.get("chordSymbol", node.label)
    key_label = data.get("key", tonic)
    out: List[LaunchAction] = []

    out.append(_trainer_action(
        f"act:node:{node.id}:identity", f"Play {symbol} ({roman})",
        function_spec([roman], symbol, mode, [tonic], render="block"),
        "node_identity", "node", network))
    out.append(_trainer_action(
        f"act:node:{node.id}:arp", f"Arpeggiate {symbol}",
        function_spec([roman], symbol, mode, [tonic], render="arpeggio"),
        "node_identity", "node", network))

    # function-family neighbours (enumeration)
    fam = data.get("functionFamily") or BROAD_FUNCTION.get(data.get("functionLabel", "tonic"),
                                                           "tonic")
    toks = _family_tokens(tonic, mode).get(fam, [])
    if toks:
        out.append(_trainer_action(
            f"act:node:{node.id}:neighbours", f"{fam.title()} family neighbours",
            function_spec(toks, f"{fam.title()} family", mode, [tonic]),
            "functional_neighbourhood", "node", network,
            reason="the chords sharing this chord's function"))

    # play all inversions in the Lab (routed in phase 7 -> network_lab)
    out.append(_inversion_lab_action(node, tonic, mode, roman, symbol))
    return out


def _lab_action(action_id: str, label: str, req: Dict, semantic_group: str,
                interaction_kind: str, reason: str, network=None,
                want_preview: bool = False) -> LaunchAction:
    """Build a lab-target action carrying a VALIDATED LabExperimentSpec dict (never spec=None,
    which would fail LaunchAction.validate()), plus an optional lab preview projection."""
    spec_dict = None
    preview = None
    status = "unavailable"
    try:
        from harmony.lab_spec import spec_from_lab_request
        lab_spec = spec_from_lab_request(req)
        spec_dict = lab_spec.to_dict()
        status = "launchable"
        if want_preview and network is not None:
            try:
                preview = project_lab_experiment(lab_spec, network).to_dict()
            except Exception:
                preview = None
    except Exception as exc:
        reason = (f"{reason} (unavailable: {exc})" if reason else f"unavailable: {exc}")
    return LaunchAction(
        id=action_id, label=label, target="lab", status=status,
        semantic_group=semantic_group, interaction_kind=interaction_kind,
        spec_type="lab_experiment", spec=spec_dict, request=req, reason=reason,
        preview_projection=preview)


def _inversion_lab_action(node, tonic: str, mode: str, roman: str, symbol: str) -> LaunchAction:
    """A Lab inversion action from a triad node (the core network has no voicing-state nodes, so
    the graph preview appears once the inversion template is loaded)."""
    req = {
        "labConcept": "inversion",
        "key": f"{tonic} {'minor' if mode != 'major' else 'major'}",
        "mode": mode,
        "degree": roman,
        "inversions": [0, 1, 2],
    }
    return _lab_action(
        f"act:node:{node.id}:inversions", f"Inversions of {symbol} (Lab)", req,
        "inversion_space", "node",
        "root / 1st / 2nd inversion voicing states in the Music Theory Lab")


def _inversion_node_actions(node, network, request) -> List[LaunchAction]:
    """A node in the inversion template -> a Lab inversion experiment with a voicing preview."""
    ctx = getattr(network, "context", None)
    data = node.data or {}
    tonic = (ctx.key if ctx else data.get("key", "C"))
    mode = (ctx.mode if ctx else data.get("mode", "major"))
    degree = (ctx.degree if ctx and ctx.degree else data.get("roman", "I"))
    key_label = f"{tonic} {'minor' if mode != 'major' else 'major'}"
    symbol = data.get("chordSymbol", node.label)
    req = {"labConcept": "inversion", "key": key_label, "mode": mode,
           "degree": degree, "inversions": [0, 1, 2]}
    return [_lab_action(
        f"act:node:{node.id}:inversions", f"Inversions of {symbol} (Lab)", req,
        "inversion_space", "node",
        "root / 1st / 2nd inversion voicing states in the Music Theory Lab",
        network=network, want_preview=True)]


def _function_node_actions(node, network, request) -> List[LaunchAction]:
    data = node.data or {}
    ctx_key = node.key_contexts[0] if node.key_contexts else None
    mode = data.get("mode", "major")
    members = data.get("members") or []
    fam = data.get("functionLabel", "tonic")
    # derive tonic from the key context label
    tonic = ctx_key.split()[0] if ctx_key else "C"
    out: List[LaunchAction] = []
    if members:
        out.append(_trainer_action(
            f"act:node:{node.id}:enumerate", f"{fam.title()} family ({', '.join(members)})",
            function_spec(members, f"{fam.title()} family", mode, [tonic]),
            "functional_neighbourhood", "node", network,
            reason="family enumeration, not a progression"))
    # standard functional route through this family into the tonic
    route = _FAMILY_ROUTE.get((mode, fam))
    if route:
        out.append(_trainer_action(
            f"act:node:{node.id}:route", f"Functional route: {'–'.join(route)}",
            function_spec(list(route), f"{'–'.join(route)}", mode, [tonic]),
            "functional_path", "node", network))
    return out


_FAMILY_ROUTE = {
    ("major", "predominant"): ("ii", "V", "I"),
    ("major", "dominant"): ("V", "I"),
    ("major", "tonic"): ("I", "IV", "V", "I"),
    ("natural_minor", "predominant"): ("ii°", "v", "i"),
    ("natural_minor", "dominant"): ("v", "i"),
    ("natural_minor", "tonic"): ("i", "iv", "v", "i"),
}


def _dom7_node_actions(node, network, request) -> List[LaunchAction]:
    """V7 node: the real V7->I resolution drill (ticket 12) + the V->I triad reduction."""
    ctx = _key_context_for(node)
    if not ctx:
        return []
    tonic, mode = ctx
    if mode != "major":
        # The drillable V7 lives in major; the minor-key V7 needs harmonic
        # minor's raised leading tone (plan G2).
        return []
    return [
        _trainer_action(
            f"act:node:{node.id}:v7",
            f"Dominant seventh drill ({node.spelling}7): V7→I into {tonic}",
            function_spec(["V7", "I"], "V7–I", "major", [tonic]),
            "functional_path", "node", network, key_context=f"{tonic} major",
            reason="the real dominant-seventh resolution"),
        _trainer_action(
            f"act:node:{node.id}:v_i", f"V→I into {tonic} (triad reduction)",
            function_spec(["V", "I"], "V–I", "major", [tonic]),
            "functional_equivalence", "node", network,
            reason="the V triad is the V7 without its seventh (comparison)"),
    ]


def _dim_node_actions(node, network, request) -> List[LaunchAction]:
    ctx = _key_context_for(node)
    out: List[LaunchAction] = []
    if ctx:
        tonic, mode = ctx
        tonic_roman = "I" if mode == "major" else "i"
        lead = "vii°" if mode == "major" else "ii°"
        out.append(_trainer_action(
            f"act:node:{node.id}:vii_i", f"Leading-tone resolution {lead}→{tonic_roman}",
            function_spec([lead, tonic_roman], f"{lead}–{tonic_roman}", mode, [tonic]),
            "functional_path", "node", network))
    return out


# --------------------------------------------------------------------------------------------- #
# Edge actions (plan section 10.2)
# --------------------------------------------------------------------------------------------- #

def _edge_actions(edge_ids, network: HarmonicNetwork,
                  request: GraphDrillRequest) -> List[LaunchAction]:
    out: List[LaunchAction] = []
    by_id = {e.id: e for e in network.edges}
    for eid in edge_ids:
        edge = by_id.get(eid)
        if edge is None:
            continue
        out.extend(_actions_for_edge(edge, network, request))
    return out


def _actions_for_edge(edge, network, request) -> List[LaunchAction]:
    src = network.node(edge.source)
    dst = network.node(edge.target)
    if src is None or dst is None:
        return []
    if edge.relation in _MOTION_RELATIONS:
        act = _edge_progression_action(edge, src, dst, network)
        return [act] if act else []
    if edge.relation in _KEY_RELATIONS:
        act = _edge_comparison_action(edge, src, dst, network)
        return [act] if act else []
    if edge.relation in _EQUIVALENCE_RELATIONS:
        act = _edge_equivalence_action(edge, src, dst, network)
        return [act] if act else []
    return []


def _edge_progression_action(edge, src, dst, network) -> Optional[LaunchAction]:
    """A harmonic-motion edge -> a real 2-item function progression, when both endpoints
    resolve to supported diatonic triads in one key."""
    # both endpoints are exact diatonic triads in the same key context
    if src.kind == "diatonic_triad" and dst.kind == "diatonic_triad":
        sk, sm = src.data.get("key"), src.data.get("mode")
        dk, dm = dst.data.get("key"), dst.data.get("mode")
        if sk and sk == dk and sm == dm:
            romans = [src.data["roman"], dst.data["roman"]]
            label = "–".join(romans)
            return _trainer_action(
                f"act:edge:{_slug(edge.id)}", f"Progression: {label}",
                function_spec(romans, label, sm, [sk]),
                "functional_path", "edge", network, key_context=f"{sk} {sm}")
    # legacy: a dominant/diminished node resolving into a key node -> the triad cadence.
    # Restricted to MAJOR target keys, where the V / vii° spellings are genuinely diatonic. Into a
    # (natural) minor key the leading-tone dominant is not diatonic, and fabricating a roman would
    # substitute a different chord/function (e.g. B° -> "ii°" = D° in C minor), so we skip it.
    if dst.kind in ("major_key", "key_center"):
        tonic, mode = _key_context_for(dst) or (dst.spelling, "major")
        if mode != "major":
            return None
        if src.kind == "dominant_seventh":
            romans = ["V", "I"]
        elif src.kind == "diminished_triad":
            romans = ["vii°", "I"]
        else:
            return None
        label = "–".join(romans)
        return _trainer_action(
            f"act:edge:{_slug(edge.id)}", f"Resolution: {label} into {tonic}",
            function_spec(romans, label, mode, [tonic]),
            "functional_path", "edge", network, key_context=f"{tonic} {mode}",
            reason="triad approximation of the resolution")
    return None


def _edge_comparison_action(edge, src, dst, network) -> Optional[LaunchAction]:
    """A key-relation edge -> a comparison / transposition, explicitly NOT a progression."""
    a = _key_context_for(src)
    b = _key_context_for(dst)
    if not a or not b:
        return None
    (ta, ma), (tb, mb) = a, b
    if edge.relation == "fifth_relation" and ma == mb:
        # same-degree comparison across the two keys (transposition orbit)
        return _trainer_action(
            f"act:edge:{_slug(edge.id)}", f"Compare tonics: {ta} vs {tb} (transposition)",
            function_spec(["I" if ma == "major" else "i"], f"{ta} vs {tb}", ma, [ta, tb]),
            "transposition_orbit", "edge", network,
            reason="a transposition comparison, NOT a modulation")
    # relative relations share one scale -> compare via the shared diatonic field of the major key
    major_tonic, major_mode = (ta, ma) if ma == "major" else (tb, mb)
    if major_mode != "major":
        return None
    return _trainer_action(
        f"act:edge:{_slug(edge.id)}", f"Shared diatonic field of {ta}/{tb}",
        full_key_spec(major_tonic, "major"), "functional_equivalence", "edge", network,
        reason="relative keys share one scale — a comparison, not a progression")


def _edge_equivalence_action(edge, src, dst, network) -> Optional[LaunchAction]:
    """An equivalence edge -> a comparison / classification (not a progression)."""
    if edge.relation == "same_function":
        ctx = _key_context_for(src) or _key_context_for(dst)
        if ctx:
            tonic, mode = ctx
            toks = _family_tokens(tonic, mode).get("dominant", [])
            if toks:
                return _trainer_action(
                    f"act:edge:{_slug(edge.id)}", f"Dominant-function alternatives ({', '.join(toks)})",
                    function_spec(toks, "Dominant alternatives", mode, [tonic]),
                    "functional_equivalence", "edge", network,
                    reason="chords sharing the dominant function")
    return None


# --------------------------------------------------------------------------------------------- #
# Public entry points
# --------------------------------------------------------------------------------------------- #

def actions_for_selection(request: GraphDrillRequest,
                          network: HarmonicNetwork) -> List[LaunchAction]:
    """Every valid :class:`LaunchAction` for a graph selection (plan section 10)."""
    request.validate()
    kind = request.interaction_kind
    if kind == "node":
        out: List[LaunchAction] = []
        for nid in request.selected_node_ids:
            node = network.node(nid)
            if node is not None:
                out.extend(_node_actions(node, network, request))
        return out
    if kind == "edge":
        return _edge_actions(request.selected_edge_ids, network, request)
    if kind == "path":
        return _path_actions(request, network)
    if kind == "constellation":
        # a constellation is treated as its member nodes
        out = []
        for nid in request.selected_node_ids:
            node = network.node(nid)
            if node is not None:
                out.extend(_node_actions(node, network, request))
        return out
    return []


def _path_actions(request: GraphDrillRequest, network: HarmonicNetwork) -> List[LaunchAction]:
    """Path launch actions (cadence template, phase 6). Empty until paths exist on the network."""
    path = next((p for p in getattr(network, "paths", []) if p.id == request.selected_path_id),
                None)
    if path is None:
        return []
    return _actions_for_path(path, network, request)


def _actions_for_path(path, network, request) -> List[LaunchAction]:
    """A cadence path -> block + arpeggio trainer drills and a voice-leading Lab experiment."""
    tonic = path.key_context.split()[0]
    mode = path.mode
    romans = list(path.romans)
    out: List[LaunchAction] = [
        _trainer_action(
            f"act:path:{path.id}:block", f"Play {path.label} (block)",
            function_spec(romans, path.label, mode, [tonic], render="block"),
            "functional_path", "path", network, key_context=path.key_context),
        _trainer_action(
            f"act:path:{path.id}:arp", f"Arpeggiate {path.label}",
            function_spec(romans, path.label, mode, [tonic], render="arpeggio"),
            "functional_path", "path", network, key_context=path.key_context),
        _voice_leading_lab_action(path),
    ]
    return out


def _voice_leading_lab_action(path) -> LaunchAction:
    """A voice-leading Lab experiment for a cadence path (carries a validated LabExperimentSpec)."""
    request = {
        "labConcept": "voice_leading",
        "key": path.key_context,
        "mode": path.mode,
        "progression": list(path.romans),
        "pattern": list(path.romans),
        "cadence_type": path.cadence_type,
    }
    return _lab_action(
        f"act:path:{path.id}:lab", f"Voice-leading of {path.label} (Lab)", request,
        "functional_path", "path",
        "voice-leading of the cadence in the Music Theory Lab")


def compile_graph_drill_action(request: GraphDrillRequest, network: HarmonicNetwork,
                               action_id: Optional[str] = None) -> Optional[LaunchAction]:
    """Compile a selection into ONE action (the chosen ``action_id`` or the first launchable).

    Re-validates the spec and rebuilds a fresh preview projection -- the host calls this the
    moment before it launches (plan section 12.3).
    """
    actions = actions_for_selection(request, network)
    if not actions:
        return None
    if action_id is not None:
        chosen = next((a for a in actions if a.id == action_id), None)
        if chosen is None:
            return None
    else:
        chosen = next((a for a in actions if a.status == "launchable"), actions[0])
    if chosen.status == "launchable":
        chosen.validate()
    return chosen


__all__ = [
    "actions_for_selection",
    "compile_graph_drill_action",
]
