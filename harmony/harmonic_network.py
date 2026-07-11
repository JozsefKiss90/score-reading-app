"""Build a Harmonic Network graph from a topological template.

This is the **graph builder** for the Harmonic Network / Tonal Graph layer.  It
consumes a :class:`~harmony.network_template.HarmonicNetworkTemplate` and emits a
deterministic, JSON-serialisable payload (``schema: harmony-network/v1``) of
nodes + edges + legend + launchables, ready for ``beat_selector/harmonic_network.js``.

Design rules (shared with the rest of the Harmony Trainer / Atlas / Circle):

* **No duplicated theory tables.**  Every chord, scale, relative minor, dominant
  seventh root, leading-tone diminished triad, quality, interval layer and
  key-signature is *derived* from :mod:`theory.diatonic_harmony`.  The template
  only supplies the display order (circle of fifths) and the layout rings.
* **Deterministic & pure.**  No Qt / Verovio / MIDI; serialises straight to JS
  and unit-tests headlessly.  No ``Date``/``random``.
* **Reuse the existing system.**  Launchable drills are real
  :class:`~harmony.exercise_spec.HarmonyExerciseSpec` objects built by the Atlas
  spec factories (``full_key_spec`` / ``function_spec``); every one is guarded to
  stay within :data:`~harmony.exercise_spec.MAX_CHORDS_PER_SPEC`.  Atlas/Circle
  references resolve against the live :class:`~harmony.atlas.Atlas` ontology.
* **Honest about limits.**  The engine is triad-based, so dominant-seventh nodes
  carry a *reserved* seventh-chord drill (never a launchable one) and link to the
  closest available *triad* drill (the V→I resolution) instead.

The first template (``dominant_diminished_relative_network_v1``) reconstructs the
topology of the Brian-Callipari-style reference image as a formal theory graph.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from theory.diatonic_harmony import (
    DiatonicTriad,
    generate_scale,
    generate_diatonic_triads,
    key_signature_fifths,
    note_pc,
    roman_token_to_index,
)
from harmony.harmonic_flow import HarmonicPath
from harmony.exercise_spec import (
    HarmonyExerciseSpec,
    compile_exercise,
    MAX_CHORDS_PER_SPEC,
)
from harmony.atlas import (
    Atlas,
    build_atlas,
    scale_id,
    degree_id,
    triad_id,
    quality_id,
    function_id,
    layer_id,
    full_key_spec,
    function_spec,
)
from harmony.network_template import (
    HarmonicNetworkTemplate,
    get_template,
)


SCHEMA_VERSION = "harmony-network/v1"

#: Network-relevant trainer groups: graph node kind -> trainer-dropdown group
#: name.  Used by :meth:`HarmonicNetwork.trainer_groups` (and the standalone
#: ``run_harmonic_network_demo`` launcher) to scope the embedded Harmony Trainer
#: to ONLY the drills the graph actually visualises.  Reserved seventh-chord
#: drills are excluded because they are not launchable.
NETWORK_GROUP_BY_KIND = OrderedDict([
    ("major_key", "Network — Major keys"),
    ("minor_key", "Network — Relative minors"),
    ("diminished_triad", "Network — Leading-tone diminished"),
    ("dominant_seventh", "Network — Dominant resolutions"),
    # bidirectional-mapping (key-local) templates:
    ("key_center", "Network — Key drills"),
    ("diatonic_triad", "Network — Diatonic triads"),
    ("function_family", "Network — Function families"),
])

#: The seven fine ``DiatonicTriad.function_label`` values collapsed to the three broad function
#: families the core template groups by (plan section 10.1).
BROAD_FUNCTION = {
    "tonic": "tonic",
    "mediant": "tonic",
    "predominant": "predominant",
    "subdominant": "predominant",
    "dominant": "dominant",
}

#: Layout order of the three function families (top, lower-right, lower-left).
FUNCTION_LAYOUT_ORDER = ["tonic", "dominant", "predominant"]

#: Canonical relations that count as harmonic motion (a path edge may reference one).
_PATH_MOTION_RELATIONS = frozenset({
    "resolves_to", "leading_tone_to", "prepares", "prolongs", "dominant_of",
})

#: Cadence catalogue per mode: (Roman pattern, label, cadence type). Chord content is derived
#: from the theory engine for the active key; this is only the degree pattern (plan section 14.2).
CADENCE_CATALOGUE = {
    "major": [
        (("V", "I"), "V–I", "authentic"),
        (("IV", "I"), "IV–I", "plagal"),
        (("V", "vi"), "V–vi", "deceptive"),
        (("ii", "V", "I"), "ii–V–I", "authentic"),
        (("IV", "V", "I"), "IV–V–I", "authentic"),
        (("I", "IV", "V", "I"), "I–IV–V–I", "authentic"),
        (("vi", "ii", "V", "I"), "vi–ii–V–I", "authentic"),
        (("I", "V", "vi", "IV"), "I–V–vi–IV", "mixed"),
    ],
    "natural_minor": [
        (("v", "i"), "v–i", "authentic"),
        (("VII", "i"), "VII–i", "authentic"),
        (("iv", "v", "i"), "iv–v–i", "authentic"),
        (("i", "iv", "v", "i"), "i–iv–v–i", "authentic"),
        (("i", "VI", "VII", "i"), "i–VI–VII–i", "mixed"),
    ],
}


def _path_slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text).strip("_").lower()


# ---------------------------------------------------------------------------
# Stable, parseable node ids ( "<kind-tag>:<root-spelling>" )
# ---------------------------------------------------------------------------

def major_node_id(tonic: str) -> str:
    return f"hn:major:{tonic}"


def minor_node_id(tonic: str) -> str:
    return f"hn:minor:{tonic}"


def dom7_node_id(root: str) -> str:
    return f"hn:dom7:{root}"


def dim_node_id(root: str) -> str:
    return f"hn:dim:{root}"


def edge_id(source: str, target: str, relation: str) -> str:
    return f"{source}|{relation}|{target}"


# ---------------------------------------------------------------------------
# Node / edge dataclasses (schema fields)
# ---------------------------------------------------------------------------

@dataclass
class NetNode:
    id: str
    label: str
    kind: str
    pitch_class: int
    spelling: str
    quality: str
    key_contexts: List[str] = field(default_factory=list)
    atlas_refs: List[str] = field(default_factory=list)
    circle_refs: List[str] = field(default_factory=list)
    trainer_specs: List[Dict] = field(default_factory=list)
    lab_specs: List[Dict] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    radius: float = 18.0
    visual_class: str = "pink"
    explanation: str = ""
    data: Dict = field(default_factory=dict)
    #: Ontological metadata (plan section 7). Blank on the legacy classes; set on the
    #: bidirectional-mapping templates so the UI can tell a key anchor from a chord instance.
    semantic_level: str = ""      # key | chord | function | class | voicing | path
    entity_role: str = ""         # anchor | instance | family | state | reference
    canonical_ref: str = ""       # the Atlas id this node mirrors (e.g. triad:C:major:1)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "pitchClass": self.pitch_class,
            "spelling": self.spelling,
            "quality": self.quality,
            "keyContexts": list(self.key_contexts),
            "atlasRefs": list(self.atlas_refs),
            "circleRefs": list(self.circle_refs),
            "trainerSpecs": list(self.trainer_specs),
            "labSpecs": list(self.lab_specs),
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "radius": self.radius,
            "visualClass": self.visual_class,
            "explanation": self.explanation,
            "data": dict(self.data),
            "semanticLevel": self.semantic_level,
            "entityRole": self.entity_role,
            "canonicalRef": self.canonical_ref,
        }


@dataclass(frozen=True)
class NetEdge:
    id: str
    source: str
    target: str
    relation: str
    direction: str               # "directed" | "undirected"
    explanation: str
    strength: float
    visual_class: str
    default_visible: bool

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "direction": self.direction,
            "explanation": self.explanation,
            "strength": self.strength,
            "visualClass": self.visual_class,
            "defaultVisible": self.default_visible,
        }


# ---------------------------------------------------------------------------
# Atlas / Circle reference resolution (spelling-tolerant)
# ---------------------------------------------------------------------------

def _resolve_scale_ref(atlas: Atlas, tonic: str, mode: str) -> Optional[str]:
    """The Atlas scale node id for ``tonic``/``mode``, tolerating enharmonics.

    Prefers the exact spelling (``scale:C:major``); otherwise finds the Atlas
    scale node of the same pitch class (e.g. ``F#`` major → ``scale:Gb:major``,
    ``D#`` minor → ``scale:Eb:natural_minor``), since the Atlas ships one
    practical spelling per key.
    """
    want = scale_id(tonic, mode)
    if atlas.node(want):
        return want
    pc = note_pc(tonic)
    for n in atlas.nodes_of_kind("scale"):
        parts = n.id.split(":")
        if len(parts) == 3 and parts[2] == mode and note_pc(parts[1]) == pc:
            return n.id
    return None


def _resolve_triad_ref(atlas: Atlas, tonic: str, mode: str, degree: int) -> Optional[str]:
    """The Atlas triad node id for the given key/degree, tolerating enharmonics."""
    want = triad_id(tonic, mode, degree)
    if atlas.node(want):
        return want
    pc = note_pc(tonic)
    for n in atlas.nodes_of_kind("triad"):
        parts = n.id.split(":")
        if (len(parts) == 4 and parts[2] == mode and parts[3] == str(degree)
                and note_pc(parts[1]) == pc):
            return n.id
    return None


def _present(atlas: Atlas, node_id: Optional[str]) -> Optional[str]:
    return node_id if (node_id and atlas.node(node_id)) else None


# ---------------------------------------------------------------------------
# Launch entries (cap-guarded; honest about reserved drills)
# ---------------------------------------------------------------------------

def _launch_entry(spec: HarmonyExerciseSpec, label: str) -> Dict:
    """A launchable trainer entry, guarded against the readability cap.

    Every spec the network hands the trainer must compile within
    :data:`MAX_CHORDS_PER_SPEC` (single-page Verovio render).  We compile here
    and raise rather than ever emit an oversized exercise.
    """
    spec.validate()
    n = len(compile_exercise(spec))
    if n > MAX_CHORDS_PER_SPEC:
        raise ValueError(
            f"network drill {spec.exercise_id!r} compiles to {n} chords "
            f"(> {MAX_CHORDS_PER_SPEC}); scope it smaller.")
    return {
        "status": "launchable",
        "label": label,
        "exerciseId": spec.exercise_id,
        "drill": spec.drill,
        "chords": n,
        "spec": spec.to_dict(),
    }


def _reserved_entry(label: str, reason: str) -> Dict:
    """A reserved (not-yet-implemented) drill entry -- never launchable."""
    return {
        "status": "reserved",
        "label": label,
        "reason": reason,
        "drill": "seventh_chord",
        "spec": None,
    }


def _lab_ref(concept: str, title: str, status: str = "reference") -> Dict:
    """A pointer to a Music Theory Lab experiment (descriptive in v1)."""
    return {"concept": concept, "title": title, "status": status}


# ---------------------------------------------------------------------------
# Layout (deterministic, template-driven)
# ---------------------------------------------------------------------------

def _spoke_xy(index: int, n_spokes: int, radius: float,
              angle_offset: float) -> "tuple[float, float]":
    """``(x, y)`` for spoke ``index`` clockwise from the top (12 o'clock).

    Screen coordinates (y grows downward), centred at the origin.  Spoke 0 is at
    the top; each subsequent spoke is ``360/n`` degrees clockwise.  ``radius`` is
    the ring distance; ``angle_offset`` nudges the node along the ring (used to
    place a relative minor just clockwise of its major key).
    """
    deg = (360.0 / n_spokes) * index + angle_offset
    rad = math.radians(deg)
    x = radius * math.sin(rad)
    y = -radius * math.cos(rad)
    return x, y


# ---------------------------------------------------------------------------
# Build context (parameterised, key-local templates)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NetworkBuildContext:
    """Parameters a key-local template builds against (plan section 13.1).

    The circle template ignores this (it builds all 12 keys from ``center_keys``); the
    triad/function/inversion templates read ``key``/``mode``/``degree`` to build a local graph.
    """

    key: str = "C"
    mode: str = "major"
    degree: Optional[str] = None
    quality: Optional[str] = None
    pattern: "tuple" = ()
    keys: "tuple" = ()

    def to_dict(self) -> Dict:
        return {
            "key": self.key,
            "mode": self.mode,
            "degree": self.degree,
            "quality": self.quality,
            "pattern": list(self.pattern),
            "keys": list(self.keys),
        }


# ---------------------------------------------------------------------------
# The network
# ---------------------------------------------------------------------------

@dataclass
class HarmonicNetwork:
    template: HarmonicNetworkTemplate
    nodes: List[NetNode]
    edges: List[NetEdge]
    context: Optional[NetworkBuildContext] = None
    paths: List = field(default_factory=list)     # List[HarmonicPath] (cadence template)

    def node(self, node_id: str) -> Optional[NetNode]:
        return self._by_id().get(node_id)

    def _by_id(self) -> Dict[str, NetNode]:
        cache = getattr(self, "_id_cache", None)
        if cache is None or len(cache) != len(self.nodes):
            cache = {n.id: n for n in self.nodes}
            object.__setattr__(self, "_id_cache", cache)
        return cache

    def nodes_of_kind(self, kind: str) -> List[NetNode]:
        return [n for n in self.nodes if n.kind == kind]

    def nodes_of_level(self, level: str) -> List[NetNode]:
        return [n for n in self.nodes if getattr(n, "semantic_level", "") == level]

    def node_by_atlas_triad_ref(self, ref: str) -> Optional[NetNode]:
        for n in self.nodes:
            if n.kind == "diatonic_triad" and (
                    getattr(n, "canonical_ref", "") == ref or ref in (n.atlas_refs or [])):
                return n
        return None

    # -- payload ---------------------------------------------------------
    def legend(self) -> Dict:
        """Consumer-facing legend (camelCase, like the rest of the payload).

        ``template.to_dict()`` keeps the dataclass' snake_case field names for
        faithful round-tripping; the legend is the UI contract, so it mirrors the
        camelCase the JS / node payloads use.
        """
        return {
            "nodeClasses": [{
                "kind": nc.kind, "label": nc.label, "visualClass": nc.visual_class,
                "color": nc.color, "description": nc.description,
            } for nc in self.template.node_classes],
            "edgeClasses": [{
                "relation": ec.relation, "label": ec.label, "directed": ec.directed,
                "implemented": ec.implemented, "visualClass": ec.visual_class,
                "defaultVisible": ec.default_visible, "description": ec.description,
            } for ec in self.template.edge_classes],
        }

    def launchables(self) -> List[Dict]:
        """Flat list of every trainer entry (launchable + reserved) with its node."""
        out: List[Dict] = []
        for n in self.nodes:
            for entry in n.trainer_specs:
                item = dict(entry)
                item["nodeId"] = n.id
                item["nodeLabel"] = n.label
                item["kind"] = n.kind
                out.append(item)
        return out

    def trainer_groups(self) -> "OrderedDict[str, List[HarmonyExerciseSpec]]":
        """Graph-relevant trainer groups: only drills the graph visualises.

        Returns an ordered ``group name -> [HarmonyExerciseSpec]`` map built
        purely from this network's launchable entries, grouped by the kind of
        graph node they belong to (see :data:`NETWORK_GROUP_BY_KIND`).  An entry
        is included only when it is

          * ``status == "launchable"`` (reserved seventh-chord drills are
            excluded -- they carry no spec), and
          * backed by a non-null spec that round-trips through
            :meth:`HarmonyExerciseSpec.from_dict` (i.e. compiles/validates).

        Every spec therefore traces back to at least one graph node.  This is the
        scoped replacement for ``default_exercise_groups()`` inside the Harmonic
        Network window; the standalone Harmony Trainer is untouched.
        """
        groups: "OrderedDict[str, List[HarmonyExerciseSpec]]" = OrderedDict(
            (name, []) for name in NETWORK_GROUP_BY_KIND.values())
        seen: set = set()
        for n in self.nodes:
            group_name = NETWORK_GROUP_BY_KIND.get(n.kind)
            if not group_name:
                continue
            for entry in n.trainer_specs:
                if entry.get("status") != "launchable":
                    continue                 # reserved seventh-chord drills dropped
                spec_dict = entry.get("spec")
                if not spec_dict:
                    continue
                ex_id = spec_dict.get("exercise_id")
                if ex_id in seen:
                    continue
                try:
                    spec = HarmonyExerciseSpec.from_dict(spec_dict)
                except Exception:
                    continue                 # never surface a broken spec
                seen.add(ex_id)
                groups[group_name].append(spec)
        # Drop any group that ended up empty (keeps the dropdown honest).
        return OrderedDict((k, v) for k, v in groups.items() if v)

    def counts(self) -> Dict:
        kinds: Dict[str, int] = {}
        for n in self.nodes:
            kinds[n.kind] = kinds.get(n.kind, 0) + 1
        relations: Dict[str, int] = {}
        for e in self.edges:
            relations[e.relation] = relations.get(e.relation, 0) + 1
        launchable = sum(
            1 for n in self.nodes for t in n.trainer_specs
            if t.get("status") == "launchable")
        reserved = sum(
            1 for n in self.nodes for t in n.trainer_specs
            if t.get("status") == "reserved")
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "nodesByKind": kinds,
            "edgesByRelation": relations,
            "launchableDrills": launchable,
            "reservedDrills": reserved,
        }

    def to_payload(self) -> Dict:
        return {
            "schema": SCHEMA_VERSION,
            "template": self.template.to_dict(),
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "legend": self.legend(),
            "launchables": self.launchables(),
            "counts": self.counts(),
            "context": self.context.to_dict() if self.context else None,
            "paths": [p.to_dict() for p in self.paths],
        }


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class _NetworkBuilder:
    """Internal: turns a template + the theory engine into nodes and edges."""

    def __init__(self, template: HarmonicNetworkTemplate, atlas: Atlas,
                 context: Optional["NetworkBuildContext"] = None):
        self.t = template
        self.atlas = atlas
        self.ctx = context or NetworkBuildContext(
            key=(template.context_schema.get("key", "C")
                 if template.context_schema else "C"),
            mode=(template.context_schema.get("mode", "major")
                  if template.context_schema else "major"),
        )
        self.keys = list(template.center_keys)
        self.n = len(self.keys)

        self.nodes: List[NetNode] = []
        self.edges: List[NetEdge] = []
        self._edge_seen: set = set()

        # id lookups, filled while building nodes
        self.major_by_idx: List[str] = []
        self.minor_by_idx: List[str] = []
        self.dom7_by_idx: List[str] = []
        self.dim_by_idx: List[str] = []
        self.major_by_pc: Dict[int, str] = {}
        self.minor_by_pc: Dict[int, str] = {}
        self.dom7_by_pc: Dict[int, str] = {}
        self.dim_by_pc: Dict[int, str] = {}
        self._scale_cache: Dict[str, object] = {}
        self._triads_cache: Dict[str, List[DiatonicTriad]] = {}

        # key-local template state (core / cadence / inversion templates)
        self.core_key_center_id: Optional[str] = None
        self.core_triad_by_deg: Dict[int, str] = {}
        self.core_triad_family: Dict[int, str] = {}
        self.core_function_by_label: Dict[str, str] = {}
        self.inv_anchor_id: Optional[str] = None
        self.inv_state_ids: List[str] = []

    # -- engine helpers --------------------------------------------------
    def _scale(self, key: str):
        if key not in self._scale_cache:
            self._scale_cache[key] = generate_scale(key, "major")
        return self._scale_cache[key]

    def _triads(self, key: str) -> List[DiatonicTriad]:
        if key not in self._triads_cache:
            self._triads_cache[key] = generate_diatonic_triads(key, "major")
        return self._triads_cache[key]

    def _add_node(self, node: NetNode) -> None:
        self.nodes.append(node)

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

    # -- node construction ----------------------------------------------
    def build_nodes(self) -> None:
        lay_major = self.t.layout_for("major_key")
        lay_minor = self.t.layout_for("minor_key")
        lay_dom = self.t.layout_for("dominant_seventh")
        lay_dim = self.t.layout_for("diminished_triad")
        vc_major = self.t.node_class("major_key").visual_class
        vc_minor = self.t.node_class("minor_key").visual_class
        vc_dom = self.t.node_class("dominant_seventh").visual_class
        vc_dim = self.t.node_class("diminished_triad").visual_class

        for i, key in enumerate(self.keys):
            scale = self._scale(key)
            triads = self._triads(key)
            fifths = scale.fifths
            rel_min = scale.scale_pitches[5]          # submediant = relative minor
            dom = triads[4]                            # V triad -> dominant root
            vii = triads[6]                            # vii° leading-tone triad
            chord_syms = [t.chord_symbol for t in triads]

            # ---- major key node (pink, outer ring) -----------------------
            mid = major_node_id(key)
            mx, my = _spoke_xy(i, self.n, lay_major.radius, lay_major.angle_offset)
            scale_ref = _resolve_scale_ref(self.atlas, key, "major")
            tonic_triad_ref = _resolve_triad_ref(self.atlas, key, "major", 0)
            self._add_node(NetNode(
                id=mid, label=key, kind="major_key",
                pitch_class=note_pc(key), spelling=key, quality="major",
                key_contexts=[f"{key} major"],
                atlas_refs=[r for r in (scale_ref, tonic_triad_ref) if r],
                circle_refs=[f"key:{key}:major"],
                trainer_specs=[_launch_entry(
                    full_key_spec(key, "major"),
                    f"{key} major — all 7 diatonic triads")],
                lab_specs=[_lab_ref("cadence",
                                    f"ii–V–I cadence in {key} major")],
                x=mx, y=my, radius=lay_major.node_radius, visual_class=vc_major,
                explanation=(
                    f"{key} major sits on the circle of fifths "
                    f"({_fifths_phrase(fifths)}). Its relative minor is "
                    f"{rel_min}m, its dominant seventh is {dom.root}7, and its "
                    f"leading-tone diminished triad is {vii.chord_symbol}. "
                    f"Diatonic triads: {' '.join(chord_syms)}."),
                data={
                    "fifths": fifths,
                    "relativeMinor": f"{rel_min}m",
                    "dominantSeventh": f"{dom.root}7",
                    "leadingDiminished": vii.chord_symbol,
                    "scale": list(scale.scale_pitches),
                    "triads": chord_syms,
                    "roman": "I",
                },
            ))
            self.major_by_idx.append(mid)
            self.major_by_pc[note_pc(key)] = mid

            # ---- relative minor node (blue, outer ring, offset) ----------
            nid = minor_node_id(rel_min)
            nx, ny = _spoke_xy(i, self.n, lay_minor.radius, lay_minor.angle_offset)
            min_scale_ref = _resolve_scale_ref(self.atlas, rel_min, "natural_minor")
            # The minor key's OWN functional dominant + leading-tone diminished
            # come from its parallel major (V / vii° of the same-tonic major) --
            # e.g. A minor's dominant is A-major's V = E7 and its leading-tone
            # diminished is A-major's vii° = G#°.  NOT the relative major's
            # dom/vii (which are this key's bVII7 and ii°).
            par = self._triads(rel_min)
            min_dom = par[4]
            min_vii = par[6]
            self._add_node(NetNode(
                id=nid, label=f"{rel_min}m", kind="minor_key",
                pitch_class=note_pc(rel_min), spelling=rel_min, quality="minor",
                key_contexts=[f"{rel_min} minor (relative minor of {key} major)"],
                atlas_refs=[r for r in (min_scale_ref,) if r],
                circle_refs=[f"key:{rel_min}:minor"],
                trainer_specs=[_launch_entry(
                    full_key_spec(rel_min, "natural_minor"),
                    f"{rel_min} natural minor — all 7 diatonic triads")],
                lab_specs=[_lab_ref("cadence",
                                    f"i–iv–v–i cadence in {rel_min} minor")],
                x=nx, y=ny, radius=lay_minor.node_radius, visual_class=vc_minor,
                explanation=(
                    f"{rel_min} minor is the relative minor of {key} major: it "
                    f"shares the same key signature and pitch content "
                    f"({_fifths_phrase(fifths)}). Its functional dominant (with a "
                    f"raised leading tone) is {min_dom.root}7, and its "
                    f"leading-tone diminished triad is {min_vii.chord_symbol}."),
                data={
                    "fifths": fifths,
                    "relativeMajor": key,
                    "dominantSeventh": f"{min_dom.root}7",
                    "leadingDiminished": min_vii.chord_symbol,
                    "roman": "i",
                },
            ))
            self.minor_by_idx.append(nid)
            self.minor_by_pc[note_pc(rel_min)] = nid

            # ---- dominant seventh node (yellow) --------------------------
            did = dom7_node_id(dom.root)
            dx, dy = _spoke_xy(i, self.n, lay_dom.radius, lay_dom.angle_offset)
            v_triad_ref = _resolve_triad_ref(self.atlas, key, "major", 4)
            v_degree_ref = _present(self.atlas, degree_id("major", "V"))
            v_func_ref = _present(self.atlas, function_id("major", "dominant"))
            # Closest available triad drill: the V→I resolution in this key.
            v_i_spec = function_spec(["V", "I"], "V–I", "major", [key])
            self._add_node(NetNode(
                id=did, label=f"{dom.root}7", kind="dominant_seventh",
                pitch_class=note_pc(dom.root), spelling=dom.root,
                quality="dominant7",
                key_contexts=[f"V7 of {key} major", f"V7 of {key} minor"],
                atlas_refs=[r for r in (v_triad_ref, v_degree_ref, v_func_ref) if r],
                circle_refs=[f"key:{key}:major"],
                trainer_specs=[
                    _reserved_entry(
                        f"Dominant seventh drill ({dom.root}7)",
                        "Seventh-chord exercises are not implemented yet — the "
                        "theory engine is triad-based."),
                    _launch_entry(
                        v_i_spec,
                        f"Closest triad drill: {dom.root} major as V resolving "
                        f"to {key} (V→I)"),
                ],
                lab_specs=[_lab_ref("voice_leading",
                                    f"Dominant resolution V→I in {key} major")],
                x=dx, y=dy, radius=lay_dom.node_radius, visual_class=vc_dom,
                explanation=(
                    f"{dom.root}7 is the dominant seventh (V7) of {key} major; it "
                    f"resolves to {key} (and to {key} minor). Without its root it "
                    f"is {vii.chord_symbol} — the leading-tone diminished triad — "
                    f"so {dom.root}7 and {vii.chord_symbol} share the dominant "
                    f"function. Seventh-chord drills are reserved; the closest "
                    f"available drill is the V→I triad resolution in {key} major."),
                data={
                    "resolvesTo": [key, f"{key}m"],
                    "rootTriad": dom.root,
                    "function": "dominant",
                    "reservedSeventh": True,
                    "rootlessEquals": vii.chord_symbol,
                },
            ))
            self.dom7_by_idx.append(did)
            self.dom7_by_pc[note_pc(dom.root)] = did

            # ---- leading-tone diminished triad node (purple, central) ----
            xid = dim_node_id(vii.root)
            xx, xy = _spoke_xy(i, self.n, lay_dim.radius, lay_dim.angle_offset)
            vii_triad_ref = _resolve_triad_ref(self.atlas, key, "major", 6)
            vii_degree_ref = _present(self.atlas, degree_id("major", "vii°"))
            dim_quality_ref = _present(self.atlas, quality_id("diminished"))
            # vii° IS a diatonic triad -> a real launchable triad drill exists.
            vii_i_spec = function_spec(["vii°", "I"], "vii°–I", "major", [key])
            self._add_node(NetNode(
                id=xid, label=vii.chord_symbol, kind="diminished_triad",
                pitch_class=note_pc(vii.root), spelling=vii.root,
                quality="diminished",
                key_contexts=[f"vii° of {key} major",
                              f"vii° (leading-tone) of {key} minor"],
                atlas_refs=[r for r in (vii_triad_ref, vii_degree_ref,
                                        dim_quality_ref) if r],
                circle_refs=[f"key:{key}:major"],
                trainer_specs=[_launch_entry(
                    vii_i_spec,
                    f"Leading-tone resolution vii°→I in {key} major "
                    f"({vii.chord_symbol}→{key})")],
                lab_specs=[_lab_ref("cadence",
                                    f"Leading-tone resolution vii°→I in {key}")],
                x=xx, y=xy, radius=lay_dim.node_radius, visual_class=vc_dim,
                explanation=(
                    f"{vii.chord_symbol} is the leading-tone (vii°) diminished "
                    f"triad of {key} major: {'–'.join(vii.pitches)} "
                    f"({vii.interval_layer}). Its leading tone {vii.root} resolves "
                    f"up to {key}. It is a rootless {dom.root}7 and functions as a "
                    f"dominant, resolving to {key} major and {key} minor. A real "
                    f"diatonic triad drill is available (vii°→I in {key})."),
                data={
                    "leadingToneTo": [key, f"{key}m"],
                    "roman": "vii°",
                    "pitches": list(vii.pitches),
                    "intervalLayer": vii.interval_layer,
                },
            ))
            self.dim_by_idx.append(xid)
            self.dim_by_pc[note_pc(vii.root)] = xid

    # -- node construction (one method per node-generation rule) ---------
    def run_node_rule(self, rule: str) -> None:
        method = getattr(self, f"_node_{rule}", None)
        if method is None:
            raise ValueError(
                f"template lists node generation rule {rule!r} with no builder method "
                f"_node_{rule}")
        method()

    def _node_legacy_key_dom_dim_nodes(self) -> None:
        """The reference-image 48-node builder (compat wrapper)."""
        self.build_nodes()

    def _triad_atlas_refs(self, t: DiatonicTriad, tonic: str, mode: str) -> List[str]:
        refs: List[str] = []
        for r in (
            _resolve_scale_ref(self.atlas, tonic, mode),
            _resolve_triad_ref(self.atlas, tonic, mode, t.degree_index),
            _present(self.atlas, degree_id(mode, t.roman)),
            _present(self.atlas, quality_id(t.chord_quality)),
            _present(self.atlas, function_id(mode, t.function_label)),
            _present(self.atlas, layer_id(t.interval_layer)),
        ):
            if r and r not in refs:
                refs.append(r)
        return refs

    def _node_core_key_center_node(self) -> None:
        tonic, mode = self.ctx.key, self.ctx.mode
        lay = self.t.layout_for("key_center")
        vc = self.t.node_class("key_center").visual_class
        triads = generate_diatonic_triads(tonic, mode)
        key_label = triads[0].key
        scale_ref = _resolve_scale_ref(self.atlas, tonic, mode)
        node_id = f"hn:key:{tonic}"
        self.core_key_center_id = node_id
        self._add_node(NetNode(
            id=node_id,
            label=key_label,
            kind="key_center",
            pitch_class=note_pc(tonic),
            spelling=tonic,
            quality="",
            key_contexts=[key_label],
            atlas_refs=[scale_ref] if scale_ref else [],
            x=0.0, y=0.0, radius=lay.node_radius,
            visual_class=vc,
            explanation=(f"{key_label} — the tonal centre / scale context. A key anchor; the "
                         f"tonic chord is the {triads[0].chord_symbol} triad node, not this node."),
            data={"key": tonic, "mode": mode, "keyLabel": key_label},
            semantic_level="key", entity_role="anchor",
            canonical_ref=scale_ref or "",
        ))

    def _node_core_diatonic_triad_nodes(self) -> None:
        tonic, mode = self.ctx.key, self.ctx.mode
        lay = self.t.layout_for("diatonic_triad")
        vc = self.t.node_class("diatonic_triad").visual_class
        triads = generate_diatonic_triads(tonic, mode)
        for t in triads:
            deg = t.degree_index
            x, y = _spoke_xy(deg, 7, lay.radius, lay.angle_offset)
            triad_ref = _resolve_triad_ref(self.atlas, tonic, mode, deg)
            node_id = f"hn:triad:{tonic}:{mode}:{deg}"
            self.core_triad_by_deg[deg] = node_id
            self.core_triad_family[deg] = BROAD_FUNCTION.get(t.function_label, "tonic")
            spec = function_spec([t.roman], t.chord_symbol, mode, [tonic])
            self._add_node(NetNode(
                id=node_id,
                label=t.chord_symbol,
                kind="diatonic_triad",
                pitch_class=note_pc(t.root),
                spelling=t.root,
                quality=t.chord_quality,
                key_contexts=[t.key],
                atlas_refs=self._triad_atlas_refs(t, tonic, mode),
                trainer_specs=[_launch_entry(spec, f"Play {t.chord_symbol} ({t.roman})")],
                x=x, y=y, radius=lay.node_radius,
                visual_class=vc,
                explanation=t.explanation_text,
                data={
                    "key": tonic, "mode": mode, "roman": t.roman, "sublabel": t.roman,
                    "degreeIndex": deg, "degreeNumber": t.degree_number, "root": t.root,
                    "chordSymbol": t.chord_symbol, "quality": t.chord_quality,
                    "functionLabel": t.function_label,
                    "functionFamily": self.core_triad_family[deg],
                    "intervalLayer": t.interval_layer,
                    "chordTones": list(t.pitches),
                },
                semantic_level="chord", entity_role="instance",
                canonical_ref=(triad_ref or triad_id(tonic, mode, deg)),
            ))

    def _node_core_function_family_nodes(self) -> None:
        tonic, mode = self.ctx.key, self.ctx.mode
        lay = self.t.layout_for("function_family")
        vc = self.t.node_class("function_family").visual_class
        triads = generate_diatonic_triads(tonic, mode)
        members: "OrderedDict[str, List[DiatonicTriad]]" = OrderedDict(
            (fam, []) for fam in FUNCTION_LAYOUT_ORDER)
        for t in triads:
            members[BROAD_FUNCTION.get(t.function_label, "tonic")].append(t)
        for i, fam in enumerate(FUNCTION_LAYOUT_ORDER):
            fam_triads = members[fam]
            x, y = _spoke_xy(i, len(FUNCTION_LAYOUT_ORDER), lay.radius, lay.angle_offset)
            node_id = f"hn:function:{mode}:{fam}"
            self.core_function_by_label[fam] = node_id
            fam_ref = _present(self.atlas, function_id(mode, fam))
            romans = [t.roman for t in fam_triads]
            entries: List[Dict] = []
            if romans:
                spec = function_spec(romans, f"{fam.title()} family", mode, [tonic])
                entries = [_launch_entry(spec, f"{fam.title()} family — enumerate "
                                               f"{', '.join(romans)}")]
            self._add_node(NetNode(
                id=node_id,
                label=f"{fam.title()} function",
                kind="function_family",
                pitch_class=-1,
                spelling="",
                quality="",
                key_contexts=[triads[0].key],
                atlas_refs=[fam_ref] if fam_ref else [],
                trainer_specs=entries,
                x=x, y=y, radius=lay.node_radius,
                visual_class=vc,
                explanation=(f"The {fam} function in {triads[0].key}: "
                             f"{', '.join(romans)}. Family membership is a grouping, "
                             f"not a progression."),
                data={"mode": mode, "functionLabel": fam,
                      "members": romans, "sublabel": ", ".join(romans)},
                semantic_level="function", entity_role="family",
                canonical_ref=fam_ref or "",
            ))

    # -- inversion template node rules -----------------------------------
    def _ctx_degree_index(self) -> int:
        if self.ctx.degree:
            try:
                return roman_token_to_index(self.ctx.degree)
            except Exception:
                return 0
        return 0

    def _node_inversion_identity_node(self) -> None:
        tonic, mode = self.ctx.key, self.ctx.mode
        deg = self._ctx_degree_index()
        triads = generate_diatonic_triads(tonic, mode)
        t = triads[deg]
        lay = self.t.layout_for("diatonic_triad")
        vc = self.t.node_class("diatonic_triad").visual_class
        triad_ref = _resolve_triad_ref(self.atlas, tonic, mode, deg)
        anchor_id = f"hn:inv:{tonic}:{mode}:{deg}:identity"
        self.inv_anchor_id = anchor_id
        self._add_node(NetNode(
            id=anchor_id, label=t.chord_symbol, kind="diatonic_triad",
            pitch_class=note_pc(t.root), spelling=t.root, quality=t.chord_quality,
            key_contexts=[t.key], atlas_refs=self._triad_atlas_refs(t, tonic, mode),
            x=0.0, y=0.0, radius=lay.node_radius, visual_class=vc,
            explanation=(f"{t.chord_symbol} ({t.roman} in {t.key}) — the invariant chord "
                         f"identity. Its function does not change across inversions."),
            data={"key": tonic, "mode": mode, "roman": t.roman, "degreeIndex": deg,
                  "chordSymbol": t.chord_symbol, "chordTones": list(t.pitches),
                  "sublabel": t.roman},
            semantic_level="chord", entity_role="reference",
            canonical_ref=(triad_ref or triad_id(tonic, mode, deg)),
        ))

    def _node_inversion_state_nodes(self) -> None:
        tonic, mode = self.ctx.key, self.ctx.mode
        deg = self._ctx_degree_index()
        triads = generate_diatonic_triads(tonic, mode)
        t = triads[deg]
        lay = self.t.layout_for("inversion_state")
        vc = self.t.node_class("inversion_state").visual_class
        triad_ref = _resolve_triad_ref(self.atlas, tonic, mode, deg)
        figured = {0: "5/3", 1: "6", 2: "6/4"}
        labels = {0: "root position", 1: "first inversion", 2: "second inversion"}
        self.inv_state_ids = []
        for inv in (0, 1, 2):
            x, y = _spoke_xy(inv, 3, lay.radius, lay.angle_offset)
            bass = t.pitches[inv]                      # [root, third, fifth][inv]
            slash = t.chord_symbol if inv == 0 else f"{t.chord_symbol}/{bass}"
            sid = f"hn:inv:{tonic}:{mode}:{deg}:{inv}"
            self.inv_state_ids.append(sid)
            self._add_node(NetNode(
                id=sid, label=slash, kind="inversion_state",
                pitch_class=note_pc(t.root), spelling=t.root, quality=t.chord_quality,
                key_contexts=[t.key], atlas_refs=self._triad_atlas_refs(t, tonic, mode),
                x=x, y=y, radius=lay.node_radius, visual_class=vc,
                explanation=(f"{labels[inv]}: bass {bass}, figured bass {figured[inv]}. "
                             f"Same chord identity as {t.chord_symbol}."),
                data={"inversion": inv, "figuredBass": figured[inv],
                      "inversionLabel": labels[inv], "bassNote": bass,
                      "bassPitchClass": note_pc(bass), "roman": t.roman,
                      "chordSymbol": t.chord_symbol, "sublabel": figured[inv],
                      "key": tonic, "mode": mode, "degreeIndex": deg},
                semantic_level="voicing", entity_role="state",
                canonical_ref=(triad_ref or triad_id(tonic, mode, deg)),
            ))

    # -- edge construction (one method per generation rule) --------------
    def run_rule(self, rule: str) -> None:
        method = getattr(self, f"_rule_{rule}", None)
        if method is None:
            raise ValueError(
                f"template lists generation rule {rule!r} with no builder method _rule_{rule}")
        method()

    def _rule_inversion_adjacency_edges(self) -> None:
        anchor = self.inv_anchor_id
        if anchor:
            for sid in self.inv_state_ids:
                self._add_edge(sid, anchor, "inversion_of",
                               explanation="A voicing of the same chord identity.",
                               strength=0.6)
        for a, b in zip(self.inv_state_ids, self.inv_state_ids[1:]):
            self._add_edge(a, b, "voice_leads_to",
                           explanation="Smooth voice-leading to the next inversion.",
                           strength=0.5)

    def _rule_diatonic_membership_edges(self) -> None:
        """Each triad belongs_to_key its key centre and is member_of_function its family."""
        key_id = self.core_key_center_id
        for deg, tid in self.core_triad_by_deg.items():
            if key_id:
                self._add_edge(tid, key_id, "belongs_to_key",
                               explanation="This triad is diatonic to the key.",
                               strength=0.5)
            fam = self.core_triad_family.get(deg)
            fam_id = self.core_function_by_label.get(fam)
            if fam_id:
                self._add_edge(tid, fam_id, "member_of_function",
                               explanation=f"Member of the {fam} function family.",
                               strength=0.5)

    def _rule_core_function_motion_edges(self) -> None:
        """The supported functional motions between triad nodes (never enumeration).

        Degree-indexed so it works in both modes: predominants (ii/IV) prepare the dominant
        (V), the dominant resolves to the tonic (V->I), the leading-tone triad resolves up
        (vii°->I), plus the plagal IV->I and deceptive V->vi. In natural minor the analogous
        degrees apply (VII->i is a subtonic resolution, not a leading-tone one).
        """
        d = self.core_triad_by_deg
        mode = self.ctx.mode

        def link(src_deg, dst_deg, relation, why, strength):
            a, b = d.get(src_deg), d.get(dst_deg)
            if a and b:
                self._add_edge(a, b, relation, explanation=why, strength=strength)

        # predominant -> dominant
        link(1, 4, "prepares", "ii prepares the dominant.", 0.7)
        link(3, 4, "prepares", "IV prepares the dominant.", 0.7)
        # dominant -> tonic
        link(4, 0, "resolves_to", "The dominant resolves to the tonic.", 1.0)
        # leading-tone / subtonic -> tonic
        if mode == "major":
            link(6, 0, "leading_tone_to", "The leading-tone triad resolves up to the tonic.", 0.9)
            link(6, 0, "resolves_to", "vii° resolves to the tonic.", 0.9)
        else:
            link(6, 0, "resolves_to", "The subtonic resolves to the tonic (minor).", 0.8)
        # plagal + deceptive
        link(3, 0, "resolves_to", "Plagal motion (IV -> I).", 0.6)
        link(4, 5, "resolves_to", "Deceptive motion (V -> vi).", 0.6)

    def _rule_major_circle_by_fifths(self) -> None:
        for i in range(self.n):
            a = self.major_by_idx[i]
            b = self.major_by_idx[(i + 1) % self.n]
            ka, kb = self.keys[i], self.keys[(i + 1) % self.n]
            self._add_edge(a, b, "fifth_relation",
                           explanation=f"{kb} major is a perfect fifth above "
                                       f"{ka} major (clockwise on the circle "
                                       f"of fifths).",
                           strength=0.8)

    def _rule_relative_minor_edges(self) -> None:
        for i in range(self.n):
            maj = self.major_by_idx[i]
            mino = self.minor_by_idx[i]
            mk, mn = self.keys[i], self.nodes_label(mino)
            self._add_edge(maj, mino, "relative_minor_of",
                           explanation=f"{mn} is the relative minor of {mk} "
                                       f"major (same key signature).",
                           strength=0.7)
            self._add_edge(mino, maj, "relative_major_of",
                           explanation=f"{mk} major is the relative major of "
                                       f"{mn}.",
                           strength=0.7)

    def _enh_note(self, target_id: str, key: str) -> str:
        """Note an enharmonic spelling when a same-pitch-class minor target is
        spelled differently from the natural ``{key} minor`` name (the circle's
        sharp/flat seam: e.g. Eb minor is shown here as the D#m node)."""
        sp = self.nodes_spelling(target_id)
        if sp == key:
            return ""
        return (f" — the {self.nodes_label(target_id)} node is its enharmonic "
                f"spelling")

    def _rule_dominant_seventh_resolution_edges(self) -> None:
        for i in range(self.n):
            dom = self.dom7_by_idx[i]
            maj = self.major_by_idx[i]
            key = self.keys[i]
            root = self.nodes_label(dom)
            # functional label twin (default-off layer)
            self._add_edge(dom, maj, "dominant_of",
                           explanation=f"{root} is the dominant seventh (V7) of "
                                       f"{key} major.",
                           strength=1.0)
            # the primary resolution arrow (default on)
            self._add_edge(dom, maj, "resolves_to",
                           explanation=f"{root} resolves to {key} major (V7 → I).",
                           strength=1.0)
            # cross-field resolution to the same-tonic minor (the crossing arc)
            minor_target = self.minor_by_pc.get(note_pc(key))
            if minor_target:
                self._add_edge(dom, minor_target, "resolves_to",
                               explanation=f"{root} also resolves to {key} minor "
                                           f"(V7 → i, with a raised leading tone)"
                                           f"{self._enh_note(minor_target, key)}.",
                               strength=0.85)

    def _rule_leading_tone_diminished_edges(self) -> None:
        for i in range(self.n):
            dim = self.dim_by_idx[i]
            maj = self.major_by_idx[i]
            key = self.keys[i]
            sym = self.nodes_label(dim)
            self._add_edge(dim, maj, "leading_tone_to",
                           explanation=f"{sym} is the leading-tone diminished "
                                       f"triad (vii°) of {key} major; its "
                                       f"leading tone resolves up to {key}.",
                           strength=1.0)
            # the resolution arrow twin (default-off, leading_tone already shows it)
            self._add_edge(dim, maj, "resolves_to",
                           explanation=f"{sym} resolves to {key} major (vii° → I).",
                           strength=0.9)
            minor_target = self.minor_by_pc.get(note_pc(key))
            if minor_target:
                self._add_edge(dim, minor_target, "leading_tone_to",
                               explanation=f"{sym} is also the leading-tone "
                                           f"diminished of {key} minor (vii° → i)"
                                           f"{self._enh_note(minor_target, key)}.",
                               strength=0.8)

    def _rule_same_function_edges(self) -> None:
        for i in range(self.n):
            dom = self.dom7_by_idx[i]
            dim = self.dim_by_idx[i]
            key = self.keys[i]
            self._add_edge(dom, dim, "same_function",
                           explanation=f"In {key}, the dominant seventh "
                                       f"{self.nodes_label(dom)} and the "
                                       f"leading-tone diminished "
                                       f"{self.nodes_label(dim)} share the "
                                       f"dominant function (vii° is a rootless "
                                       f"V7).",
                           strength=0.5)

    def _rule_shared_scale_edges(self) -> None:
        # Diatonic minor triads of a major key (ii / iii / vi) -> their minor-key
        # nodes.  Optional, default-off layer (would otherwise clutter the field).
        roman_by_degree = {1: "ii", 2: "iii", 5: "vi"}
        for i in range(self.n):
            maj = self.major_by_idx[i]
            key = self.keys[i]
            scale = self._scale(key)
            triads = self._triads(key)
            for deg, roman in roman_by_degree.items():
                root_pc = note_pc(scale.scale_pitches[deg])
                minor_target = self.minor_by_pc.get(root_pc)
                if minor_target:
                    # name the chord with its spelling-correct diatonic symbol in
                    # `key` (F# major's iii is A#m, NOT the Bbm node's label).
                    diat_sym = triads[deg].chord_symbol
                    tgt = self.nodes_label(minor_target)
                    enh = ("" if tgt == diat_sym
                           else f" (the {tgt} node is its enharmonic spelling)")
                    self._add_edge(
                        maj, minor_target, "shares_scale_with",
                        explanation=f"{diat_sym} is diatonic in {key} major (the "
                                    f"{roman} chord) — they share scale "
                                    f"content{enh}.",
                        strength=0.4)

    def _rule_same_pitch_class_edges(self) -> None:
        # Cross-class overlay: a major key linked to every other node whose root
        # is the same pitch class.  Default-off ("find this pitch elsewhere").
        for i in range(self.n):
            maj = self.major_by_idx[i]
            pc = note_pc(self.keys[i])
            for other in (self.minor_by_pc.get(pc), self.dom7_by_pc.get(pc),
                          self.dim_by_pc.get(pc)):
                if other:
                    self._add_edge(
                        maj, other, "same_pitch_class",
                        explanation=f"{self.nodes_label(maj)} and "
                                    f"{self.nodes_label(other)} share the same "
                                    f"root pitch class.",
                        strength=0.3)

    def _rule_integration_overlays(self) -> None:
        for i in range(self.n):
            dom = self.dom7_by_idx[i]
            dim = self.dim_by_idx[i]
            maj = self.major_by_idx[i]
            key = self.keys[i]
            # closest launchable triad drill for the (reserved) dominant seventh
            root_major = self.major_by_pc.get(note_pc(self.nodes_spelling(dom)))
            if root_major:
                self._add_edge(
                    dom, root_major, "trainer_drill_available",
                    explanation=f"Closest available Harmony Trainer drill for "
                                f"{self.nodes_label(dom)}: the "
                                f"{self.nodes_spelling(dom)} major triad "
                                f"(as V of {key}).",
                    strength=0.4)
            # vii° → I is a real triad drill, living in key K
            self._add_edge(
                dim, maj, "trainer_drill_available",
                explanation=f"A launchable vii°→I triad drill is available in "
                            f"{key} major.",
                strength=0.4)
            # Atlas concept availability
            self._add_edge(
                dom, maj, "atlas_node_available",
                explanation=f"Atlas: the V degree / dominant function of {key} "
                            f"major.",
                strength=0.3)
            self._add_edge(
                dim, maj, "atlas_node_available",
                explanation=f"Atlas: the vii° degree / diminished quality of "
                            f"{key} major.",
                strength=0.3)

    # -- tiny helpers ----------------------------------------------------
    def nodes_label(self, node_id: str) -> str:
        n = next((x for x in self.nodes if x.id == node_id), None)
        return n.label if n else node_id

    def nodes_spelling(self, node_id: str) -> str:
        n = next((x for x in self.nodes if x.id == node_id), None)
        return n.spelling if n else node_id


def build_network(template: Optional[HarmonicNetworkTemplate] = None,
                  atlas: Optional[Atlas] = None,
                  context: Optional[NetworkBuildContext] = None) -> HarmonicNetwork:
    """Build a :class:`HarmonicNetwork` from a template (default: the v1 reference).

    Pure & deterministic: the same template + context always yields the same nodes/edges.
    ``context`` parameterises key-local templates (core / cadence / inversion); the circle
    template ignores it.  A template with no ``node_generation_rules`` uses the legacy 4-kind
    builder for backward compatibility.
    """
    tpl = template or get_template()
    tpl.validate()
    builder = _NetworkBuilder(tpl, atlas or build_atlas(), context)
    if tpl.node_generation_rules:
        for rule in tpl.node_generation_rules:
            builder.run_node_rule(rule)
        ctx_out = builder.ctx           # key-local templates carry their context
    else:
        builder.build_nodes()           # legacy default (reference template)
        ctx_out = None                  # the circle template is not key-local
    for rule in tpl.generation_rules:
        builder.run_rule(rule)
    paths = _build_paths(builder, tpl)
    return HarmonicNetwork(template=tpl, nodes=builder.nodes, edges=builder.edges,
                           context=ctx_out, paths=paths)


def _build_paths(builder: "_NetworkBuilder", tpl: HarmonicNetworkTemplate) -> List:
    """Build first-class :class:`HarmonicPath` arcs for a path-carrying template.

    The cadence template reuses the core triad nodes; each catalogue entry becomes an ordered
    path over those nodes, recording only the canonical theory edges that independently exist
    along the route (so the path never asserts an unsupported resolution).
    """
    if tpl.launch_rules.get("path_catalogue") != "cadence":
        return []
    ctx = builder.ctx
    catalogue = CADENCE_CATALOGUE.get(ctx.mode, [])
    if not catalogue or not builder.core_triad_by_deg:
        return []
    triads = generate_diatonic_triads(ctx.key, ctx.mode)
    key_label = triads[0].key
    edge_by_pair = {(e.source, e.target): e for e in builder.edges}

    paths: List[HarmonicPath] = []
    for romans, label, cadence_type in catalogue:
        try:
            degs = [roman_token_to_index(r) for r in romans]
        except Exception:
            continue
        node_ids = [builder.core_triad_by_deg.get(d) for d in degs]
        if any(n is None for n in node_ids):
            continue
        edge_ids: List[str] = []
        for a, b in zip(node_ids, node_ids[1:]):
            e = edge_by_pair.get((a, b))
            if e and e.relation in _PATH_MOTION_RELATIONS:
                edge_ids.append(e.id)
        pid = f"path:{_path_slug(label)}:{ctx.key}:{ctx.mode}"
        paths.append(HarmonicPath(
            id=pid, label=label, key_context=key_label, mode=ctx.mode,
            node_ids=tuple(node_ids), edge_ids=tuple(edge_ids), romans=tuple(romans),
            cadence_type=cadence_type, semantic_group="functional_path",
            launch_action_ids=(f"act:path:{pid}:block", f"act:path:{pid}:arp",
                               f"act:path:{pid}:lab"),
        ))
    return paths


def build_network_payload(template_id: Optional[str] = None) -> Dict:
    """Convenience: build the default (or named) network and return its payload."""
    tpl = get_template(template_id) if template_id else get_template()
    return build_network(tpl).to_payload()


# ---------------------------------------------------------------------------
# Small phrasing helper
# ---------------------------------------------------------------------------

def _fifths_phrase(fifths: int) -> str:
    if fifths == 0:
        return "no sharps or flats"
    if fifths > 0:
        return f"{fifths} sharp{'s' if fifths != 1 else ''}"
    return f"{-fifths} flat{'s' if fifths != -1 else ''}"
