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

Minor panels (the v2 minor journey, ticket 15 / G2c) suffix the key token
with ``m`` -- ``fnet:deg:Am:4`` is the V of A minor -- so minor ids are
disjoint from every major id (the two journeys share one progress store) and
the JS sync can reconstruct them from ``target.key`` + ``target.mode``.
Minor panels generate their chords with **harmonic minor** (the real V /
vii°, ticket 13 / G2a) while the *key* context stays natural minor: Atlas
refs follow the natural-minor-twin honesty rule (chord-level nodes only on an
exact pitch match; the raised III+ / V / vii° claim only their quality).
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
from harmony.harmonic_roles import (
    ENGINE_FUNCTION_TO_INTERNAL_FAMILY,
    function_flow_short,
    internal_family_label,
)


#: How the engine's five per-degree ``function_label`` values collapse onto
#: the network's three merged function groups.  ``mediant`` is grouped with
#: the tonic substitutes (see the module docstring -- each iii node's
#: explanation states the ambiguity).
#:
#: Derived from the single vocabulary source (ticket 01 / plan section 9.5) -- never hand-edit;
#: change :data:`harmony.harmonic_roles._LABEL_TO_BROAD` instead.  A plain alias (not a copy),
#: so the two names can never diverge at runtime.
ENGINE_FUNCTION_TO_GROUP = ENGINE_FUNCTION_TO_INTERNAL_FAMILY

#: Per-degree functional role prose, appended to the engine's own per-triad
#: explanation.  Keyed by panel mode, then 0-based degree index.
_ROLE_PROSE_MAJOR = {
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

#: The minor-panel counterpart (harmonic-minor chord set, ticket 15 / G2c).
_ROLE_PROSE_MINOR = {
    0: ("This is home: the minor tonic. Every resolution and preparation "
        "arrow in this panel eventually points back here."),
    1: ("The supertonic ii° is minor's strongest predominant: diminished "
        "here (unlike major's ii), it still prepares V by falling a fifth "
        "onto it (ii° → V)."),
    2: ("The augmented III+ only exists because harmonic minor raises the "
        "7th inside the mediant. It shares two tones with i (hence its spot "
        "with the tonic substitutes) AND two with V -- a rare, unstable "
        "chord; composers usually prefer natural minor's plain III."),
    3: ("The subdominant iv prepares the dominant (iv → V) and can also "
        "move straight home (the plagal motion iv → i)."),
    4: ("THE point of harmonic minor: raising the 7th turns natural minor's "
        "weak v into a real major-triad dominant V, whose leading tone "
        "pulls home to i (authentic) or deceptively to VI."),
    5: ("The submediant VI is minor's classic tonic substitute (it shares "
        "two tones with i) and the goal of the deceptive resolution "
        "V → VI."),
    6: ("The leading-tone diminished vii° is a rootless dominant, built on "
        "harmonic minor's raised 7th: that tone pulls up a semitone to the "
        "tonic (vii° → i)."),
}

_ROLE_PROSE = {"major": _ROLE_PROSE_MAJOR, "minor": _ROLE_PROSE_MINOR}

#: Per-group drill patterns (label, roman tokens), keyed by panel mode.
#: Mirrors the Atlas function-map cell spec pattern, extended so every family
#: drill *ends home* and the tonic family includes the mediant it groups.
_GROUP_DRILLS = {
    "major": {
        "tonic": (["I", "vi", "iii", "I"],
                  f"{internal_family_label('tonic')} I–vi–iii–I"),
        "predominant": (["IV", "ii", "V", "I"],
                        f"{internal_family_label('predominant')} IV–ii–V–I"),
        "dominant": (["V", "vii°", "I"],
                     f"{internal_family_label('dominant')} V–vii°–I"),
    },
    "minor": {
        "tonic": (["i", "VI", "III+", "i"],
                  f"{internal_family_label('tonic')} i–VI–III+–i"),
        "predominant": (["iv", "ii°", "V", "i"],
                        f"{internal_family_label('predominant')} iv–ii°–V–i"),
        "dominant": (["V", "vii°", "i"],
                     f"{internal_family_label('dominant')} V–vii°–i"),
    },
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


def panel_mode(key_or_mode: str) -> str:
    """Collapse any key/mode string onto the two panel modes: ``"A minor"``,
    ``"natural_minor"`` and ``"harmonic_minor"`` are all ``"minor"`` panels
    (a raised 7 is a scale form of the same minor key); everything else is
    ``"major"``.  The single home of the ``"minor" in ...`` convention that
    the journey's drill mapping and the launcher's chord lighting share.
    """
    return "minor" if "minor" in (key_or_mode or "") else "major"


def panel_token(key: str, mode: str = "major") -> str:
    """The id token of a journey-key panel: the canonical tonic, suffixed
    ``m`` for minor panels (``"A", "minor"`` -> ``"Am"``).  The suffix keeps
    every minor id disjoint from every major id -- the two journeys share one
    progress store, and the JS sync rebuilds the token from ``target.mode``.
    """
    return canonical_key(key) + ("m" if mode == "minor" else "")


def degree_node_id(key: str, degree_index: int, mode: str = "major") -> str:
    return f"fnet:deg:{panel_token(key, mode)}:{degree_index}"


def function_node_id(key: str, group: str, mode: str = "major") -> str:
    return f"fnet:fn:{panel_token(key, mode)}:{group}"


def key_node_id(key: str, mode: str = "major") -> str:
    return f"fnet:key:{panel_token(key, mode)}"


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class _FunctionalBuilder:
    """Internal: turns a functional template + the theory engine into a graph."""

    def __init__(self, template: FunctionalNetworkTemplate, atlas: Atlas):
        self.t = template
        self.atlas = atlas
        #: Panel mode ("major"/"minor") and the three modes it implies:
        #: chords come from harmonic minor (the real V / vii°, G2a) while the
        #: KEY context -- Atlas/Circle refs, key-signature ordering -- stays
        #: natural minor (a raised 7 is a scale form, not a key signature).
        self.mode = template.mode           # also the prose word: "A minor"
        self.chord_mode = "harmonic_minor" if self.mode == "minor" else "major"
        self.ctx_mode = "natural_minor" if self.mode == "minor" else "major"
        # Panels are displayed left-to-right in circle-of-fifths order (F C G D
        # for the default journey) so fifth_relation edges join neighbours.
        # Pure layout: the *order key* comes from the engine, not a table.
        # Keys are canonicalised ("C major" -> "C") so labels, prose and node
        # ids all use the same tonic token the sync path reconstructs.
        self.keys = sorted((canonical_key(k) for k in template.journey_keys),
                           key=lambda k: key_signature_fifths(k, self.ctx_mode))
        self.n = len(self.keys)

        self.nodes: List[NetNode] = []
        self.edges: List[NetEdge] = []
        self._edge_seen: set = set()
        self._triads_cache: Dict[str, List[DiatonicTriad]] = {}

    # -- engine helpers --------------------------------------------------
    def _triads(self, key: str) -> List[DiatonicTriad]:
        if key not in self._triads_cache:
            self._triads_cache[key] = generate_diatonic_triads(
                key, self.chord_mode)
        return self._triads_cache[key]

    # -- id helpers (panel-mode aware) -----------------------------------
    def _deg_id(self, key: str, i: int) -> str:
        return degree_node_id(key, i, self.mode)

    def _fn_id(self, key: str, group: str) -> str:
        return function_node_id(key, group, self.mode)

    def _key_id(self, key: str) -> str:
        return key_node_id(key, self.mode)

    def _degree_atlas_refs(self, key: str, i: int,
                           triad: DiatonicTriad) -> List[str]:
        """Atlas refs for one degree node, honest per panel mode.

        Major panels claim triad + degree + function + quality as before.
        Minor panels follow the G2a natural-minor-twin precedent: the Atlas
        has no harmonic-minor nodes, so chord-level refs are claimed only
        when the chord exactly equals its natural-minor twin (i / ii° / iv /
        VI); the raised-leading-tone chords (III+ / V / vii°) claim nothing
        but their quality class.
        """
        if self.mode == "minor":
            nat = generate_diatonic_triads(key, "natural_minor")[i]
            twin = nat.pitches == triad.pitches
            candidates = (
                _resolve_triad_ref(self.atlas, key, "natural_minor", i)
                if twin else None,
                _present(self.atlas, degree_id("natural_minor", nat.roman))
                if twin else None,
                _present(self.atlas,
                         function_id("natural_minor", nat.function_label))
                if twin else None,
                _present(self.atlas, quality_id(triad.chord_quality)),
            )
        else:
            candidates = (
                _resolve_triad_ref(self.atlas, key, "major", i),
                _present(self.atlas, degree_id("major", triad.roman)),
                _present(self.atlas,
                         function_id("major", triad.function_label)),
                _present(self.atlas, quality_id(triad.chord_quality)),
            )
        return [r for r in candidates if r]

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
            scale = generate_scale(key, self.chord_mode)
            triads = self._triads(key)
            tonic_roman = triads[0].roman           # "I" major / "i" minor

            # ---- 7 degree-triad nodes ---------------------------------
            for i, triad in enumerate(triads):
                group = ENGINE_FUNCTION_TO_GROUP[triad.function_label]
                dx, dy = self.t.degree_offsets[i]
                if i == 0:
                    spec = full_key_spec(key, self.chord_mode)
                    label = (f"{key} {self.mode} — all 7 diatonic "
                             f"triads (home drill for {tonic_roman})")
                else:
                    spec = function_spec([triad.roman, tonic_roman],
                                         f"{triad.roman}–{tonic_roman}",
                                         self.chord_mode, [key])
                    label = (f"{triad.roman}–{tonic_roman} in {key} "
                             f"{self.mode} "
                             f"({triad.chord_symbol}→{triads[0].chord_symbol})")
                self.nodes.append(NetNode(
                    id=self._deg_id(key, i),
                    label=triad.roman, kind="degree_triad",
                    pitch_class=note_pc(triad.root), spelling=triad.root,
                    quality=triad.chord_quality,
                    key_contexts=[f"{triad.roman} of {key} {self.mode}"],
                    atlas_refs=self._degree_atlas_refs(key, i, triad),
                    circle_refs=[f"key:{key}:{self.ctx_mode}"],
                    trainer_specs=[_launch_entry(spec, label)],
                    lab_specs=([_lab_ref(
                        "cadence",
                        f"V–{tonic_roman} cadence in {key} {self.mode}")]
                               if i == 4 else []),
                    x=px + dx, y=py + dy, radius=lay_deg.node_radius,
                    visual_class=vc_deg,
                    explanation=(f"{triad.explanation_text} "
                                 f"{_ROLE_PROSE[self.mode][i]}"),
                    data={
                        "roman": triad.roman,
                        "degreeIndex": i,
                        "degreeNumber": triad.degree_number,
                        "functionLabel": triad.function_label,
                        "functionGroup": group,
                        "pitches": list(triad.pitches),
                        "intervalLayer": triad.interval_layer,
                        "panelKey": key,
                        "panelMode": self.mode,
                        "sublabel": triad.chord_symbol,
                    },
                ))

            # ---- 3 function-group nodes --------------------------------
            for group in FUNCTION_GROUPS:
                members = [t for t in triads
                           if ENGINE_FUNCTION_TO_GROUP[t.function_label] == group]
                romans = [t.roman for t in members]
                symbols = [t.chord_symbol for t in members]
                tokens, drill_label = _GROUP_DRILLS[self.mode][group]
                fx, fy = self.t.function_offsets[group]
                # The mediant/subdominant extras are guarded: the Atlas has
                # no natural_minor mediant function node, so minor panels
                # simply drop that ref.
                fn_refs = [r for r in (
                    _present(self.atlas, function_id(self.ctx_mode, group)),
                    _present(self.atlas, function_id(self.ctx_mode, "mediant"))
                    if group == "tonic" else None,
                    _present(self.atlas,
                             function_id(self.ctx_mode, "subdominant"))
                    if group == "predominant" else None,
                ) if r]
                mediant_roman = triads[2].roman     # "iii" major / "III+" minor
                mediant_note = (
                    f" The {mediant_roman} chord is grouped here as a tonic "
                    f"substitute; see its own node for why that call is "
                    f"ambiguous."
                    if group == "tonic" else "")
                self.nodes.append(NetNode(
                    id=self._fn_id(key, group),
                    label=FUNCTION_GROUP_SHORT[group], kind="function_group",
                    pitch_class=note_pc(key), spelling=key, quality="function",
                    key_contexts=[f"{FUNCTION_GROUP_LABELS[group]} of "
                                  f"{key} {self.mode}"],
                    atlas_refs=fn_refs,
                    circle_refs=[f"key:{key}:{self.ctx_mode}"],
                    trainer_specs=[_launch_entry(
                        function_spec(tokens, drill_label, self.chord_mode,
                                      [key]),
                        f"{FUNCTION_GROUP_LABELS[group]} in {key} "
                        f"{self.mode} ({'–'.join(tokens)})")],
                    lab_specs=[],
                    x=px + fx, y=py + fy, radius=lay_fn.node_radius,
                    visual_class=vc_fn,
                    explanation=(
                        f"The {FUNCTION_GROUP_LABELS[group].lower()} of {key} "
                        f"{self.mode}: "
                        f"{', '.join(f'{r} ({s})' for r, s in zip(romans, symbols))}. "
                        f"{_GROUP_PROSE[self.mode][group]}{mediant_note}"),
                    data={
                        "functionGroup": group,
                        "members": romans,
                        "memberSymbols": symbols,
                        "panelKey": key,
                        "panelMode": self.mode,
                        "sublabel": "·".join(romans),
                    },
                ))

            # ---- the key hub -------------------------------------------
            hx, hy = self.t.hub_offset
            chord_syms = [t.chord_symbol for t in triads]
            hub_refs = [r for r in (
                _resolve_scale_ref(self.atlas, key, self.ctx_mode),
                _resolve_triad_ref(self.atlas, key, self.ctx_mode, 0),
            ) if r]
            if self.mode == "minor":
                # The panel's chords come from harmonic minor -- say so
                # (the key signature phrase stays the natural-minor truth).
                scale_note = (
                    f"Chords come from harmonic minor: the 7th is raised to "
                    f"{scale.scale_pitches[6]}, which is what makes "
                    f"{chord_syms[4]} and {chord_syms[6]} real dominants. ")
                hub_cadence = f"ii°–V–i cadence in {key} minor"
            else:
                scale_note = ""
                hub_cadence = f"ii–V–I cadence in {key} major"
            self.nodes.append(NetNode(
                id=self._key_id(key),
                label=panel_token(key, self.mode), kind="key_hub",
                pitch_class=note_pc(key), spelling=key, quality=self.mode,
                key_contexts=[f"{key} {self.mode}"],
                atlas_refs=hub_refs,
                circle_refs=[f"key:{key}:{self.ctx_mode}"],
                trainer_specs=[_launch_entry(
                    full_key_spec(key, self.chord_mode),
                    f"{key} {self.mode} — all 7 diatonic triads")],
                lab_specs=[_lab_ref("cadence", hub_cadence)],
                x=px + hx, y=py + hy, radius=lay_hub.node_radius,
                visual_class=vc_hub,
                explanation=(
                    f"The {key} {self.mode} panel "
                    f"({_fifths_phrase(scale.fifths)}). {scale_note}"
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
                    "panelMode": self.mode,
                    "sublabel": self.mode,
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
                    self._deg_id(key, i), self._fn_id(key, group),
                    "function_member",
                    explanation=f"{triad.chord_symbol} ({triad.roman}) belongs "
                                f"to the {FUNCTION_GROUP_LABELS[group].lower()} "
                                f"of {key} {self.mode}.",
                    strength=0.4)

    def _rule_resolution_edges(self) -> None:
        for key in self.keys:
            triads = self._triads(key)
            v, vii, tonic = triads[4], triads[6], triads[0]
            self._add_edge(
                self._deg_id(key, 4), self._deg_id(key, 0), "resolves_to",
                explanation=f"{v.chord_symbol} resolves to {tonic.chord_symbol} "
                            f"({v.roman} → {tonic.roman}): the authentic "
                            f"resolution that defines "
                            f"{key} {self.mode}.",
                strength=1.0)
            self._add_edge(
                self._deg_id(key, 6), self._deg_id(key, 0), "resolves_to",
                explanation=f"{vii.chord_symbol} resolves to "
                            f"{tonic.chord_symbol} ({vii.roman} → "
                            f"{tonic.roman}): its leading "
                            f"tone {vii.root} pulls up a semitone to {key}.",
                strength=0.9)

    def _rule_preparation_edges(self) -> None:
        for key in self.keys:
            triads = self._triads(key)
            ii, iv, v = triads[1], triads[3], triads[4]
            self._add_edge(
                self._deg_id(key, 1), self._deg_id(key, 4), "prepares",
                explanation=f"{ii.chord_symbol} prepares {v.chord_symbol} "
                            f"({ii.roman} → {v.roman}): a falling fifth, the "
                            f"same motion {v.roman} "
                            f"makes onto {triads[0].roman}.",
                strength=0.8)
            self._add_edge(
                self._deg_id(key, 3), self._deg_id(key, 4), "prepares",
                explanation=f"{iv.chord_symbol} prepares {v.chord_symbol} "
                            f"({iv.roman} → {v.roman}): the subdominant "
                            f"stepping up to the "
                            f"dominant.",
                strength=0.7)

    def _rule_substitute_edges(self) -> None:
        for key in self.keys:
            triads = self._triads(key)
            tonic, iii, vi = triads[0], triads[2], triads[5]
            self._add_edge(
                self._deg_id(key, 5), self._deg_id(key, 0),
                "tonic_substitute",
                explanation=f"{vi.chord_symbol} shares two chord tones with "
                            f"{tonic.chord_symbol} and can stand in for it "
                            f"(the classic tonic substitute).",
                strength=0.6)
            self._add_edge(
                self._deg_id(key, 2), self._deg_id(key, 0),
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
                self._deg_id(key, 4), self._deg_id(key, 5), "deceptive_to",
                explanation=f"{v.chord_symbol} resolves deceptively to "
                            f"{vi.chord_symbol} instead of {key} ({v.roman} → "
                            f"{vi.roman}, the "
                            f"deceptive cadence): the ear expects home and "
                            f"gets its substitute.",
                strength=0.5)

    def _rule_in_key_edges(self) -> None:
        for key in self.keys:
            for i, triad in enumerate(self._triads(key)):
                self._add_edge(
                    self._deg_id(key, i), self._key_id(key), "in_key",
                    explanation=f"{triad.chord_symbol} is the {triad.roman} "
                                f"triad of {key} {self.mode}.",
                    strength=0.3)

    def _rule_fifth_relation_edges(self) -> None:
        # self.keys is sorted by key-signature fifths. An edge is only HONEST
        # when the neighbours really are one step apart on the circle (F -> C
        # -> G -> D for the default journey; D -> A -> E -> B for the minor
        # one); a sparser custom key set (e.g. C and D) gets no
        # fifth_relation edge rather than a false one.
        for i in range(self.n - 1):
            a, b = self.keys[i], self.keys[i + 1]
            if key_signature_fifths(b, self.ctx_mode) - \
                    key_signature_fifths(a, self.ctx_mode) != 1:
                continue
            self._add_edge(
                self._key_id(a), self._key_id(b), "fifth_relation",
                explanation=f"{b} {self.mode} is a perfect fifth above "
                            f"{a} {self.mode} "
                            f"(one step clockwise on the circle of fifths).",
                strength=0.8)

    def _rule_shared_triad_edges(self) -> None:
        # Pitch-class-set equality across panels: one triad shape, several
        # functional jobs (C:I ≡ G:IV ≡ F:V ...; Am is i at home and iv in E
        # minor).  This is what shows one triad doing two jobs at once.
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
                        self._deg_id(ka, ia), self._deg_id(kb, ib),
                        "shared_triad",
                        explanation=f"One shape, two jobs: {ta.chord_symbol} "
                                    f"is the {ta.roman} of {ka} "
                                    f"{self.mode} and the "
                                    f"{tb.roman} of {kb} {self.mode} — "
                                    f"the same "
                                    f"three pitches doing different "
                                    f"functional work.",
                        strength=0.6)


#: Per-group prose for the function-group node explanations, keyed by panel
#: mode.
_GROUP_PROSE = {
    "major": {
        "tonic": (f"{internal_family_label('tonic')} chords are points of rest: "
                  "phrases start and end here, and every dominant arrow in the "
                  "panel resolves into this cluster."),
        "predominant": (f"{internal_family_label('predominant')} chords (the "
                        "supertonic ii and the subdominant IV) set up the "
                        f"dominant: they are the approach lane of the "
                        f"{function_flow_short()} cycle (ii → V and IV → V)."),
        "dominant": (f"{internal_family_label('dominant')} chords carry the "
                     "tension: V and its rootless twin vii° both contain the "
                     "leading tone and pull home to I."),
    },
    "minor": {
        "tonic": (f"{internal_family_label('tonic')} chords are points of rest: "
                  "phrases start and end here, and every dominant arrow in the "
                  "panel resolves into this cluster."),
        "predominant": (f"{internal_family_label('predominant')} chords (the "
                        "diminished supertonic ii° and the subdominant iv) set "
                        f"up the dominant: they are the approach lane of the "
                        f"{function_flow_short()} cycle (ii° → V and iv → V)."),
        "dominant": (f"{internal_family_label('dominant')} chords carry the "
                     "tension: V and its rootless twin vii° both contain "
                     "harmonic minor's raised leading tone and pull home "
                     "to i."),
    },
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
