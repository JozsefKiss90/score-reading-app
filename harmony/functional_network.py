"""Build a Functional Degree Network graph from a functional template.

This is the **graph builder** for the Functional Degree Network -- the
practice-first sibling of :mod:`harmony.harmonic_network`.  It consumes a
:class:`~harmony.functional_network_template.FunctionalNetworkTemplate` and
emits the *same* ``harmony-network/v1`` payload schema (it reuses
:class:`~harmony.harmonic_network.NetNode` / ``NetEdge`` / ``_launch_entry``
verbatim), so ``beat_selector/harmonic_network.js`` renders it unmodified.

Design rules (shared with the whole Harmony Trainer / Atlas / Network system):

* **No duplicated theory tables.**  Every triad, roman numeral, function
  label, pitch and explanation is *derived* from
  :mod:`theory.diatonic_harmony.generate_diatonic_triads`.  The template only
  supplies panel layout and vocabularies.
* **Deterministic & pure.**  No Qt / Verovio / MIDI; serialises straight to
  JS and unit-tests headlessly.
* **Every node is launchable.**  Everything here is triad-based, so there are
  *no reserved drills anywhere in this graph* (unlike the v1 network's
  dominant-seventh nodes).  Every spec is guarded through ``_launch_entry``
  to stay within :data:`~harmony.exercise_spec.MAX_CHORDS_PER_SPEC`.
* **Honest about the mediant.**  The engine labels iii ``mediant``; the graph
  groups it with the tonic substitutes and each iii node's explanation states
  the ambiguity (it shares two tones with both I and V).

Node ids are stable and parseable (the exact-id trainer sync depends on them):

* ``fnet:deg:<key>:<degree_index>``  (``fnet:deg:C:4`` = the V of C major)
* ``fnet:fn:<key>:<function_group>`` (``fnet:fn:C:dominant``)
* ``fnet:key:<key>``                 (``fnet:key:C``)
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from theory.diatonic_harmony import (
    DiatonicTriad,
    generate_scale,
    generate_diatonic_triads,
    key_signature_fifths,
    note_pc,
    parse_key,
)
from harmony.atlas import (
    Atlas,
    build_atlas,
    degree_id,
    function_id,
    quality_id,
    full_key_spec,
    function_spec,
)
from harmony.harmonic_network import (
    HarmonicNetwork,
    NetNode,
    NetEdge,
    edge_id,
    _launch_entry,
    _lab_ref,
    _resolve_scale_ref,
    _resolve_triad_ref,
    _present,
    _fifths_phrase,
)
from harmony.functional_network_template import (
    FunctionalNetworkTemplate,
    functional_degree_network_v1,
    get_template,
    FUNCTION_GROUPS,
    FUNCTION_GROUP_SHORT,
    FUNCTION_GROUP_LABELS,
)


#: How the engine's five per-degree ``function_label`` values collapse onto
#: the network's three merged function groups.  ``mediant`` is grouped with
#: the tonic substitutes (see the module docstring -- each iii node's
#: explanation states the ambiguity).
ENGINE_FUNCTION_TO_GROUP = {
    "tonic": "tonic",
    "mediant": "tonic",
    "predominant": "predominant",
    "subdominant": "predominant",
    "dominant": "dominant",
}

#: Per-degree functional role prose (major mode), appended to the engine's own
#: per-triad explanation.  Keyed by 0-based degree index.
_ROLE_PROSE = {
    0: ("This is home: the tonic. Every resolution and preparation arrow in "
        "this panel eventually points back here."),
    1: ("The supertonic ii is the strongest predominant: it prepares V by "
        "falling a fifth onto it (ii → V), exactly like V falls onto I."),
    2: ("The mediant iii is the most ambiguous diatonic triad: it shares two "
        "tones with I (so this graph groups it with the tonic substitutes) "
        "AND two tones with V (so it can lean dominant). The grouping here "
        "is a pedagogical choice, not a hard fact."),
    3: ("The subdominant IV prepares the dominant (IV → V) and can also move "
        "straight home (the plagal motion IV → I)."),
    4: ("The dominant V is the engine of tonal tension: it resolves to I "
        "(authentic), or deceptively to vi. Watch the V → I arrow while you "
        "play it."),
    5: ("The submediant vi is the classic tonic substitute (it shares two "
        "tones with I) and the goal of the deceptive resolution V → vi."),
    6: ("The leading-tone diminished vii° is a rootless dominant: its "
        "leading tone pulls up a semitone to the tonic (vii° → I)."),
}

#: Per-group drill patterns (label, roman tokens).  Mirrors the Atlas
#: function-map cell spec pattern, extended so every family drill *ends home*
#: and the tonic family includes the mediant it groups.
_GROUP_DRILLS = {
    "tonic": (["I", "vi", "iii", "I"], "Tonic family I–vi–iii–I"),
    "predominant": (["IV", "ii", "V", "I"], "Predominant family IV–ii–V–I"),
    "dominant": (["V", "vii°", "I"], "Dominant family V–vii°–I"),
}


# ---------------------------------------------------------------------------
# Stable, parseable node ids (the exact-id trainer sync depends on these)
# ---------------------------------------------------------------------------

def canonical_key(key: str) -> str:
    """The canonical tonic token for a journey key (``"C major"`` -> ``"C"``).

    Node ids embed this token, and everything that later *reconstructs* an id
    (``drill_node_ids``, the JS ``highlightFromDegreeTarget``) derives the
    tonic through ``parse_key`` -- so ids must be built the same way, or a
    non-canonical spelling in ``journey_keys`` would silently kill the
    lighting mechanic.
    """
    tonic, _ = parse_key(key)
    return tonic


def degree_node_id(key: str, degree_index: int) -> str:
    return f"fnet:deg:{canonical_key(key)}:{degree_index}"


def function_node_id(key: str, group: str) -> str:
    return f"fnet:fn:{canonical_key(key)}:{group}"


def key_node_id(key: str) -> str:
    return f"fnet:key:{canonical_key(key)}"


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class _FunctionalBuilder:
    """Internal: turns a functional template + the theory engine into a graph."""

    def __init__(self, template: FunctionalNetworkTemplate, atlas: Atlas):
        self.t = template
        self.atlas = atlas
        # Panels are displayed left-to-right in circle-of-fifths order (F C G D
        # for the default journey) so fifth_relation edges join neighbours.
        # Pure layout: the *order key* comes from the engine, not a table.
        # Keys are canonicalised ("C major" -> "C") so labels, prose and node
        # ids all use the same tonic token the sync path reconstructs.
        self.keys = sorted((canonical_key(k) for k in template.journey_keys),
                           key=lambda k: key_signature_fifths(k, "major"))
        self.n = len(self.keys)

        self.nodes: List[NetNode] = []
        self.edges: List[NetEdge] = []
        self._edge_seen: set = set()
        self._triads_cache: Dict[str, List[DiatonicTriad]] = {}

    # -- engine helpers --------------------------------------------------
    def _triads(self, key: str) -> List[DiatonicTriad]:
        if key not in self._triads_cache:
            self._triads_cache[key] = generate_diatonic_triads(key, "major")
        return self._triads_cache[key]

    def _panel_origin(self, panel_index: int) -> Tuple[float, float]:
        """The centre of panel ``panel_index`` (panels in a centred row)."""
        x = (panel_index - (self.n - 1) / 2.0) * self.t.panel_width
        return x, 0.0

    def _add_edge(self, source: str, target: str, relation: str, *,
                  explanation: str, strength: float) -> None:
        if source == target:
            return
        key = (source, target, relation)
        if key in self._edge_seen:
            return
        ec = self.t.edge_class(relation)
        if not ec.implemented:
            return  # reserved relations are named but generate no edges yet
        self._edge_seen.add(key)
        self.edges.append(NetEdge(
            id=edge_id(source, target, relation),
            source=source, target=target, relation=relation,
            direction="directed" if ec.directed else "undirected",
            explanation=explanation, strength=strength,
            visual_class=ec.visual_class, default_visible=ec.default_visible,
        ))

    # -- node construction ------------------------------------------------
    def build_nodes(self) -> None:
        lay_deg = self.t.layout_for("degree_triad")
        lay_fn = self.t.layout_for("function_group")
        lay_hub = self.t.layout_for("key_hub")
        vc_deg = self.t.node_class("degree_triad").visual_class
        vc_fn = self.t.node_class("function_group").visual_class
        vc_hub = self.t.node_class("key_hub").visual_class

        for pi, key in enumerate(self.keys):
            px, py = self._panel_origin(pi)
            scale = generate_scale(key, "major")
            triads = self._triads(key)

            # ---- 7 degree-triad nodes ---------------------------------
            for i, triad in enumerate(triads):
                group = ENGINE_FUNCTION_TO_GROUP[triad.function_label]
                dx, dy = self.t.degree_offsets[i]
                if i == 0:
                    spec = full_key_spec(key, "major")
                    label = (f"{key} major — all 7 diatonic triads "
                             f"(home drill for I)")
                else:
                    spec = function_spec([triad.roman, "I"],
                                         f"{triad.roman}–I", "major", [key])
                    label = (f"{triad.roman}–I in {key} major "
                             f"({triad.chord_symbol}→{triads[0].chord_symbol})")
                atlas_refs = [r for r in (
                    _resolve_triad_ref(self.atlas, key, "major", i),
                    _present(self.atlas, degree_id("major", triad.roman)),
                    _present(self.atlas,
                             function_id("major", triad.function_label)),
                    _present(self.atlas, quality_id(triad.chord_quality)),
                ) if r]
                self.nodes.append(NetNode(
                    id=degree_node_id(key, i),
                    label=triad.roman, kind="degree_triad",
                    pitch_class=note_pc(triad.root), spelling=triad.root,
                    quality=triad.chord_quality,
                    key_contexts=[f"{triad.roman} of {key} major"],
                    atlas_refs=atlas_refs,
                    circle_refs=[f"key:{key}:major"],
                    trainer_specs=[_launch_entry(spec, label)],
                    lab_specs=([_lab_ref("cadence",
                                         f"V–I cadence in {key} major")]
                               if i == 4 else []),
                    x=px + dx, y=py + dy, radius=lay_deg.node_radius,
                    visual_class=vc_deg,
                    explanation=(f"{triad.explanation_text} {_ROLE_PROSE[i]}"),
                    data={
                        "roman": triad.roman,
                        "degreeIndex": i,
                        "degreeNumber": triad.degree_number,
                        "functionLabel": triad.function_label,
                        "functionGroup": group,
                        "pitches": list(triad.pitches),
                        "intervalLayer": triad.interval_layer,
                        "panelKey": key,
                        "sublabel": triad.chord_symbol,
                    },
                ))

            # ---- 3 function-group nodes --------------------------------
            for group in FUNCTION_GROUPS:
                members = [t for t in triads
                           if ENGINE_FUNCTION_TO_GROUP[t.function_label] == group]
                romans = [t.roman for t in members]
                symbols = [t.chord_symbol for t in members]
                tokens, drill_label = _GROUP_DRILLS[group]
                fx, fy = self.t.function_offsets[group]
                fn_refs = [r for r in (
                    _present(self.atlas, function_id("major", group)),
                    _present(self.atlas, function_id("major", "mediant"))
                    if group == "tonic" else None,
                    _present(self.atlas, function_id("major", "subdominant"))
                    if group == "predominant" else None,
                ) if r]
                mediant_note = (
                    " The iii chord is grouped here as a tonic substitute; "
                    "see its own node for why that call is ambiguous."
                    if group == "tonic" else "")
                self.nodes.append(NetNode(
                    id=function_node_id(key, group),
                    label=FUNCTION_GROUP_SHORT[group], kind="function_group",
                    pitch_class=note_pc(key), spelling=key, quality="function",
                    key_contexts=[f"{FUNCTION_GROUP_LABELS[group]} of "
                                  f"{key} major"],
                    atlas_refs=fn_refs,
                    circle_refs=[f"key:{key}:major"],
                    trainer_specs=[_launch_entry(
                        function_spec(tokens, drill_label, "major", [key]),
                        f"{FUNCTION_GROUP_LABELS[group]} in {key} major "
                        f"({'–'.join(tokens)})")],
                    lab_specs=[],
                    x=px + fx, y=py + fy, radius=lay_fn.node_radius,
                    visual_class=vc_fn,
                    explanation=(
                        f"The {FUNCTION_GROUP_LABELS[group].lower()} of {key} "
                        f"major: {', '.join(f'{r} ({s})' for r, s in zip(romans, symbols))}. "
                        f"{_GROUP_PROSE[group]}{mediant_note}"),
                    data={
                        "functionGroup": group,
                        "members": romans,
                        "memberSymbols": symbols,
                        "panelKey": key,
                        "sublabel": "·".join(romans),
                    },
                ))

            # ---- the key hub -------------------------------------------
            hx, hy = self.t.hub_offset
            chord_syms = [t.chord_symbol for t in triads]
            hub_refs = [r for r in (
                _resolve_scale_ref(self.atlas, key, "major"),
                _resolve_triad_ref(self.atlas, key, "major", 0),
            ) if r]
            self.nodes.append(NetNode(
                id=key_node_id(key),
                label=key, kind="key_hub",
                pitch_class=note_pc(key), spelling=key, quality="major",
                key_contexts=[f"{key} major"],
                atlas_refs=hub_refs,
                circle_refs=[f"key:{key}:major"],
                trainer_specs=[_launch_entry(
                    full_key_spec(key, "major"),
                    f"{key} major — all 7 diatonic triads")],
                lab_specs=[_lab_ref("cadence",
                                    f"ii–V–I cadence in {key} major")],
                x=px + hx, y=py + hy, radius=lay_hub.node_radius,
                visual_class=vc_hub,
                explanation=(
                    f"The {key} major panel ({_fifths_phrase(scale.fifths)}). "
                    f"Its seven diatonic triads are laid out by harmonic "
                    f"function below: tonic cluster at the bottom "
                    f"({chord_syms[0]}, {chord_syms[5]}, {chord_syms[2]}), "
                    f"predominants on the left ({chord_syms[1]}, "
                    f"{chord_syms[3]}), dominants on the right "
                    f"({chord_syms[4]}, {chord_syms[6]})."),
                data={
                    "fifths": scale.fifths,
                    "scale": list(scale.scale_pitches),
                    "triads": chord_syms,
                    "panelKey": key,
                    "sublabel": "major",
                },
            ))

    # -- edge construction (one method per generation rule) --------------
    def run_rule(self, rule: str) -> None:
        getattr(self, f"_rule_{rule}")()

    def _rule_function_member_edges(self) -> None:
        for key in self.keys:
            for i, triad in enumerate(self._triads(key)):
                group = ENGINE_FUNCTION_TO_GROUP[triad.function_label]
                self._add_edge(
                    degree_node_id(key, i), function_node_id(key, group),
                    "function_member",
                    explanation=f"{triad.chord_symbol} ({triad.roman}) belongs "
                                f"to the {FUNCTION_GROUP_LABELS[group].lower()} "
                                f"of {key} major.",
                    strength=0.4)

    def _rule_resolution_edges(self) -> None:
        for key in self.keys:
            triads = self._triads(key)
            v, vii, tonic = triads[4], triads[6], triads[0]
            self._add_edge(
                degree_node_id(key, 4), degree_node_id(key, 0), "resolves_to",
                explanation=f"{v.chord_symbol} resolves to {tonic.chord_symbol} "
                            f"(V → I): the authentic resolution that defines "
                            f"{key} major.",
                strength=1.0)
            self._add_edge(
                degree_node_id(key, 6), degree_node_id(key, 0), "resolves_to",
                explanation=f"{vii.chord_symbol} resolves to "
                            f"{tonic.chord_symbol} (vii° → I): its leading "
                            f"tone {vii.root} pulls up a semitone to {key}.",
                strength=0.9)

    def _rule_preparation_edges(self) -> None:
        for key in self.keys:
            triads = self._triads(key)
            ii, iv, v = triads[1], triads[3], triads[4]
            self._add_edge(
                degree_node_id(key, 1), degree_node_id(key, 4), "prepares",
                explanation=f"{ii.chord_symbol} prepares {v.chord_symbol} "
                            f"(ii → V): a falling fifth, the same motion V "
                            f"makes onto I.",
                strength=0.8)
            self._add_edge(
                degree_node_id(key, 3), degree_node_id(key, 4), "prepares",
                explanation=f"{iv.chord_symbol} prepares {v.chord_symbol} "
                            f"(IV → V): the subdominant stepping up to the "
                            f"dominant.",
                strength=0.7)

    def _rule_substitute_edges(self) -> None:
        for key in self.keys:
            triads = self._triads(key)
            tonic, iii, vi = triads[0], triads[2], triads[5]
            self._add_edge(
                degree_node_id(key, 5), degree_node_id(key, 0),
                "tonic_substitute",
                explanation=f"{vi.chord_symbol} shares two chord tones with "
                            f"{tonic.chord_symbol} and can stand in for it "
                            f"(the classic tonic substitute).",
                strength=0.6)
            self._add_edge(
                degree_node_id(key, 2), degree_node_id(key, 0),
                "tonic_substitute",
                explanation=f"{iii.chord_symbol} shares two chord tones with "
                            f"{tonic.chord_symbol} — a weaker, more ambiguous "
                            f"tonic substitute (it also shares two tones with "
                            f"{triads[4].chord_symbol}).",
                strength=0.5)

    def _rule_deceptive_edges(self) -> None:
        for key in self.keys:
            triads = self._triads(key)
            v, vi = triads[4], triads[5]
            self._add_edge(
                degree_node_id(key, 4), degree_node_id(key, 5), "deceptive_to",
                explanation=f"{v.chord_symbol} resolves deceptively to "
                            f"{vi.chord_symbol} instead of {key} (V → vi, the "
                            f"deceptive cadence): the ear expects home and "
                            f"gets its substitute.",
                strength=0.5)

    def _rule_in_key_edges(self) -> None:
        for key in self.keys:
            for i, triad in enumerate(self._triads(key)):
                self._add_edge(
                    degree_node_id(key, i), key_node_id(key), "in_key",
                    explanation=f"{triad.chord_symbol} is the {triad.roman} "
                                f"triad of {key} major.",
                    strength=0.3)

    def _rule_fifth_relation_edges(self) -> None:
        # self.keys is sorted by key-signature fifths. An edge is only HONEST
        # when the neighbours really are one step apart on the circle (F -> C
        # -> G -> D for the default journey); a sparser custom key set (e.g.
        # C and D) gets no fifth_relation edge rather than a false one.
        for i in range(self.n - 1):
            a, b = self.keys[i], self.keys[i + 1]
            if key_signature_fifths(b, "major") - \
                    key_signature_fifths(a, "major") != 1:
                continue
            self._add_edge(
                key_node_id(a), key_node_id(b), "fifth_relation",
                explanation=f"{b} major is a perfect fifth above {a} major "
                            f"(one step clockwise on the circle of fifths).",
                strength=0.8)

    def _rule_shared_triad_edges(self) -> None:
        # Pitch-class-set equality across panels: one triad shape, several
        # functional jobs (C:I ≡ G:IV ≡ F:V ...).  This is what shows a G
        # triad being I in G and V in C simultaneously.
        by_pcset: Dict[frozenset, List[Tuple[str, int, DiatonicTriad]]] = {}
        for key in self.keys:
            for i, triad in enumerate(self._triads(key)):
                pcset = frozenset(triad.pitch_classes)
                by_pcset.setdefault(pcset, []).append((key, i, triad))
        for entries in by_pcset.values():
            for a in range(len(entries)):
                for b in range(a + 1, len(entries)):
                    ka, ia, ta = entries[a]
                    kb, ib, tb = entries[b]
                    if ka == kb:
                        continue  # same panel: nothing cross-key to show
                    self._add_edge(
                        degree_node_id(ka, ia), degree_node_id(kb, ib),
                        "shared_triad",
                        explanation=f"One shape, two jobs: {ta.chord_symbol} "
                                    f"is the {ta.roman} of {ka} major and the "
                                    f"{tb.roman} of {kb} major — the same "
                                    f"three pitches doing different "
                                    f"functional work.",
                        strength=0.6)


#: Per-group prose for the function-group node explanations.
_GROUP_PROSE = {
    "tonic": ("Tonic-family chords are points of rest: phrases start and end "
              "here, and every dominant arrow in the panel resolves into this "
              "cluster."),
    "predominant": ("Predominant (subdominant-family) chords set up the "
                    "dominant: they are the approach lane of the T → PD → D "
                    "→ T cycle (ii → V and IV → V)."),
    "dominant": ("Dominant-family chords carry the tension: V and its "
                 "rootless twin vii° both contain the leading tone and pull "
                 "home to I."),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_functional_network(
        template: Optional[FunctionalNetworkTemplate] = None,
        atlas: Optional[Atlas] = None,
        keys: Optional[List[str]] = None) -> HarmonicNetwork:
    """Build the functional degree network (default: the v1 journey template).

    ``keys`` is a convenience for the default topology over a different major
    key set (``build_functional_network(keys=["C", "G"])``); it is ignored
    when an explicit ``template`` is passed.  Returns a
    :class:`~harmony.harmonic_network.HarmonicNetwork` (the shared graph
    container), so ``to_payload()`` / ``launchables()`` / ``counts()`` work
    unchanged.  Pure & deterministic.
    """
    tpl = template or (functional_degree_network_v1(keys) if keys
                       else get_template())
    tpl.validate()
    builder = _FunctionalBuilder(tpl, atlas or build_atlas())
    builder.build_nodes()
    for rule in tpl.generation_rules:
        builder.run_rule(rule)
    return HarmonicNetwork(template=tpl, nodes=builder.nodes,
                           edges=builder.edges)


def functional_payload(network: HarmonicNetwork) -> Dict:
    """The network's JS payload, flagged ``progressive`` (nodes start unlit).

    ``harmonic_network.js`` renders any node whose id is not in its completed
    set with the ``node--unlit`` class when ``payload.progressive`` is true --
    the practice mechanic that makes playing light the graph up.
    """
    payload = network.to_payload()
    payload["progressive"] = True
    return payload


def build_functional_network_payload(template_id: Optional[str] = None) -> Dict:
    """Convenience: build the default (or named) functional network payload."""
    tpl = get_template(template_id) if template_id else get_template()
    return functional_payload(build_functional_network(tpl))
