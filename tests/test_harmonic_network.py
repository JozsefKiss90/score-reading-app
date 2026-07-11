"""Tests for the Harmonic Network / Tonal Graph layer.

The Harmonic Network is a deterministic, template-driven *relational* graph over
the existing tonal system (Circle of Fifths -> Atlas -> Lab/Curriculum). These
tests enforce its contract:

  * template validation -- required fields, closed vocabularies (unknown node
    classes / edge relations / generation rules fail cleanly);
  * graph generation -- 12 major + 12 minor + 12 dominant-seventh + 12
    diminished nodes; the rule-generated relationships (C<->Am, G7->C, B°->C,
    D7->G, F#°->G) exist;
  * Atlas integration -- node Atlas references resolve to real Atlas node ids;
  * launch status -- triad/full-key drills are launchable and respect the
    readability cap; seventh-chord drills are *reserved*, never launchable;
  * determinism + payload shape; the reference image's node inventory is fully
    reconstructed (every major/minor/V7/vii° node is present).

Run from the project root::

    .venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -t .
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from theory.diatonic_harmony import note_pc  # noqa: E402
from harmony.exercise_spec import (  # noqa: E402
    HarmonyExerciseSpec, compile_exercise, MAX_CHORDS_PER_SPEC,
)
from harmony.network_template import (  # noqa: E402
    HarmonicNetworkTemplate, NodeClass, EdgeClass, LayoutRule,
    get_template, load_template, dominant_diminished_relative_network_v1,
    NODE_KINDS, IMPLEMENTED_RELATIONS, RESERVED_RELATIONS, ALL_RELATIONS,
    GENERATION_RULES,
    PLANNED_TEMPLATES, list_planned_templates, list_templates,
)
from harmony.harmonic_network import (  # noqa: E402
    build_network, build_network_payload, HarmonicNetwork,
    major_node_id, minor_node_id, dom7_node_id, dim_node_id,
    NETWORK_GROUP_BY_KIND,
)


def _valid_template() -> HarmonicNetworkTemplate:
    return dominant_diminished_relative_network_v1()


# ---------------------------------------------------------------------------
# 1. Template validation
# ---------------------------------------------------------------------------

class TestTemplateValidation(unittest.TestCase):
    def test_default_template_is_valid(self):
        tpl = get_template()
        tpl.validate()  # must not raise
        self.assertEqual(tpl.template_id,
                         "dominant_diminished_relative_network_v1")
        self.assertEqual(len(tpl.center_keys), 12)

    def test_required_fields_present(self):
        tpl = _valid_template()
        for field in ("template_id", "title", "description"):
            self.assertTrue(getattr(tpl, field))
        self.assertTrue(tpl.node_classes)
        self.assertTrue(tpl.edge_classes)
        self.assertTrue(tpl.layout_rules)

    def test_empty_template_id_fails(self):
        tpl = _valid_template()
        tpl.template_id = ""
        with self.assertRaises(ValueError):
            tpl.validate()

    def test_unknown_node_class_fails(self):
        tpl = _valid_template()
        tpl.node_classes.append(
            NodeClass("augmented_sixth", "Bogus", "pink", "#000"))
        tpl.layout_rules.append(LayoutRule("augmented_sixth", "outer", 1.0))
        with self.assertRaises(ValueError):
            tpl.validate()

    def test_unknown_edge_relation_fails_cleanly(self):
        tpl = _valid_template()
        tpl.edge_classes.append(EdgeClass("teleports_to", "Bogus"))
        with self.assertRaises(ValueError) as ctx:
            tpl.validate()
        self.assertIn("teleports_to", str(ctx.exception))

    def test_unknown_generation_rule_fails(self):
        tpl = _valid_template()
        tpl.generation_rules.append("summon_demon")
        with self.assertRaises(ValueError):
            tpl.validate()

    def test_reserved_relation_cannot_be_implemented(self):
        tpl = _valid_template()
        tpl.edge_classes.append(
            EdgeClass("tritone_substitute_of", "Tritone sub", implemented=True))
        with self.assertRaises(ValueError):
            tpl.validate()

    def test_layout_rule_requires_matching_node_class(self):
        tpl = _valid_template()
        tpl.layout_rules.append(LayoutRule("minor_key", "inner", 2.0))  # dup ok-ish
        # remove a node class so a layout rule is orphaned
        tpl2 = _valid_template()
        tpl2.layout_rules.append(LayoutRule("dominant_seventh", "x", 1.0))
        tpl2.node_classes = [nc for nc in tpl2.node_classes
                             if nc.kind != "dominant_seventh"]
        with self.assertRaises(ValueError):
            tpl2.validate()

    def test_vocabulary_constants_are_disjoint(self):
        self.assertEqual(set(IMPLEMENTED_RELATIONS) & set(RESERVED_RELATIONS), set())
        self.assertEqual(set(ALL_RELATIONS),
                         set(IMPLEMENTED_RELATIONS) | set(RESERVED_RELATIONS))

    def test_required_relations_all_declared(self):
        # The legacy reference template declares its own eleven implemented relations plus
        # every reserved relation. (The shared IMPLEMENTED_RELATIONS vocabulary is a superset
        # now that key-local templates add membership/motion relations.)
        from harmony.network_template import LEGACY_IMPLEMENTED_RELATIONS
        tpl = _valid_template()
        declared = set(tpl.relations())
        for r in LEGACY_IMPLEMENTED_RELATIONS:
            self.assertIn(r, declared, f"template must declare {r}")
        for r in RESERVED_RELATIONS:
            self.assertIn(r, declared, f"template must reserve {r}")

    def test_round_trip_to_from_dict(self):
        tpl = _valid_template()
        again = load_template(tpl.to_dict())
        self.assertEqual(again.template_id, tpl.template_id)
        self.assertEqual(again.relations(), tpl.relations())
        self.assertEqual(again.center_keys, tpl.center_keys)


# ---------------------------------------------------------------------------
# 2. Graph generation
# ---------------------------------------------------------------------------

class TestGraphGeneration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.net = build_network()
        cls.payload = cls.net.to_payload()

    def _kind(self, kind):
        return [n for n in self.net.nodes if n.kind == kind]

    def _has_edge(self, source, relation, target):
        return any(e.source == source and e.relation == relation
                   and e.target == target for e in self.net.edges)

    def test_node_counts(self):
        self.assertEqual(len(self._kind("major_key")), 12)
        self.assertEqual(len(self._kind("minor_key")), 12)
        self.assertEqual(len(self._kind("dominant_seventh")), 12)
        self.assertEqual(len(self._kind("diminished_triad")), 12)
        self.assertEqual(len(self.net.nodes), 48)

    def test_reference_image_node_inventory(self):
        # Every node visible in the reference image is reconstructed.
        labels = {n.label for n in self.net.nodes}
        for maj in ["C", "G", "D", "A", "E", "B", "F#", "Db", "Ab", "Eb", "Bb", "F"]:
            self.assertIn(maj, labels)
        for mino in ["Am", "Em", "Bm", "F#m", "C#m", "G#m", "D#m", "Bbm",
                     "Fm", "Cm", "Gm", "Dm"]:
            self.assertIn(mino, labels)
        for dom in ["G7", "D7", "A7", "E7", "B7", "F#7", "C#7", "Ab7", "Eb7",
                    "Bb7", "F7", "C7"]:
            self.assertIn(dom, labels)
        for dim in ["B°", "F#°", "C#°", "G#°", "D#°", "A#°", "E#°", "C°", "G°",
                    "D°", "A°", "E°"]:
            self.assertIn(dim, labels)

    def test_relative_minor_edges(self):
        self.assertTrue(self._has_edge(major_node_id("C"), "relative_minor_of",
                                       minor_node_id("A")))
        self.assertTrue(self._has_edge(minor_node_id("A"), "relative_major_of",
                                       major_node_id("C")))

    def test_dominant_resolution_edges(self):
        self.assertTrue(self._has_edge(dom7_node_id("G"), "resolves_to",
                                       major_node_id("C")))
        self.assertTrue(self._has_edge(dom7_node_id("D"), "resolves_to",
                                       major_node_id("G")))
        self.assertTrue(self._has_edge(dom7_node_id("A"), "resolves_to",
                                       major_node_id("D")))
        # functional-label twin
        self.assertTrue(self._has_edge(dom7_node_id("G"), "dominant_of",
                                       major_node_id("C")))

    def test_leading_tone_diminished_edges(self):
        self.assertTrue(self._has_edge(dim_node_id("B"), "leading_tone_to",
                                       major_node_id("C")))
        self.assertTrue(self._has_edge(dim_node_id("F#"), "leading_tone_to",
                                       major_node_id("G")))
        self.assertTrue(self._has_edge(dim_node_id("C#"), "leading_tone_to",
                                       major_node_id("D")))

    def test_dominant_and_diminished_resolve_to_parallel_minor(self):
        # the characteristic crossing arcs: G7 / B° also point at C minor (Cm).
        self.assertTrue(self._has_edge(dom7_node_id("G"), "resolves_to",
                                       minor_node_id("C")))
        self.assertTrue(self._has_edge(dim_node_id("B"), "leading_tone_to",
                                       minor_node_id("C")))

    def test_fifth_cycle_is_closed(self):
        fifths = [e for e in self.net.edges if e.relation == "fifth_relation"]
        self.assertEqual(len(fifths), 12)
        # F (last) connects back to C (first) -> a closed 12-cycle
        self.assertTrue(self._has_edge(major_node_id("F"), "fifth_relation",
                                       major_node_id("C")))

    def test_same_function_links_v7_and_viidim(self):
        self.assertTrue(self._has_edge(dom7_node_id("G"), "same_function",
                                       dim_node_id("B")))

    def test_every_edge_endpoint_exists(self):
        ids = {n.id for n in self.net.nodes}
        for e in self.net.edges:
            self.assertIn(e.source, ids, e)
            self.assertIn(e.target, ids, e)
            self.assertIn(e.relation, IMPLEMENTED_RELATIONS, e)

    def test_no_reserved_relation_generates_edges(self):
        used = {e.relation for e in self.net.edges}
        self.assertEqual(used & set(RESERVED_RELATIONS), set())

    def test_deterministic_build(self):
        a = build_network().to_payload()
        b = build_network().to_payload()
        self.assertEqual(a["nodes"], b["nodes"])
        self.assertEqual(a["edges"], b["edges"])

    def test_layout_coordinates_are_deterministic_and_ringed(self):
        # major ring is outermost; diminished ring is innermost.
        def radius(n):
            return (n.x ** 2 + n.y ** 2) ** 0.5
        maj_r = radius(self.net.node(major_node_id("C")))
        dom_r = radius(self.net.node(dom7_node_id("G")))
        dim_r = radius(self.net.node(dim_node_id("B")))
        self.assertGreater(maj_r, dom_r)
        self.assertGreater(dom_r, dim_r)
        # C major sits at the top (12 o'clock): x≈0, y<0.
        c = self.net.node(major_node_id("C"))
        self.assertAlmostEqual(c.x, 0.0, places=5)
        self.assertLess(c.y, 0.0)


# ---------------------------------------------------------------------------
# 3. Atlas integration
# ---------------------------------------------------------------------------

class TestAtlasIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.net = build_network()

    def _node(self, node_id):
        return cls_node(self.net, node_id)

    def test_c_major_has_scale_ref(self):
        c = self.net.node(major_node_id("C"))
        self.assertIn("scale:C:major", c.atlas_refs)

    def test_b_dim_has_quality_and_degree_refs(self):
        b = self.net.node(dim_node_id("B"))
        self.assertIn("quality:diminished", b.atlas_refs)
        self.assertIn("degree:major:vii°", b.atlas_refs)

    def test_g7_links_to_existing_v_triad_and_function(self):
        g7 = self.net.node(dom7_node_id("G"))
        # the closest available Atlas concepts: the V triad / degree / function
        self.assertIn("triad:C:major:4", g7.atlas_refs)   # G major as V in C
        self.assertIn("degree:major:V", g7.atlas_refs)
        self.assertIn("function:major:dominant", g7.atlas_refs)

    def test_all_atlas_refs_resolve_to_real_nodes(self):
        from harmony.atlas import build_atlas
        atlas = build_atlas()
        for n in self.net.nodes:
            for ref in n.atlas_refs:
                self.assertIsNotNone(atlas.node(ref),
                                     f"{n.id} -> dangling atlas ref {ref}")

    def test_sharp_spelled_keys_resolve_enharmonic_atlas_scale(self):
        # F# major (the image's spelling) maps to the Atlas's Gb-major scale node.
        fs = self.net.node(major_node_id("F#"))
        scale_refs = [r for r in fs.atlas_refs if r.startswith("scale:")]
        self.assertTrue(scale_refs)
        self.assertEqual(note_pc(scale_refs[0].split(":")[1]), note_pc("F#"))


def cls_node(net, node_id):
    return net.node(node_id)


# ---------------------------------------------------------------------------
# 3b. Minor-key functional harmony (regression: a minor node must name its OWN
#     dominant / leading-tone diminished, not the relative major's).
# ---------------------------------------------------------------------------

class TestMinorFunctionalHarmony(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.net = build_network()

    def _has_edge(self, source, relation, target):
        return any(e.source == source and e.relation == relation
                   and e.target == target for e in self.net.edges)

    def test_a_minor_dominant_and_leading_tone(self):
        am = self.net.node(minor_node_id("A"))
        # A minor's dominant is E7 (not C major's G7); its vii° is G#° (not B°).
        self.assertEqual(am.data["dominantSeventh"], "E7")
        self.assertEqual(am.data["leadingDiminished"], "G#°")
        self.assertIn("E7", am.explanation)
        self.assertNotIn("G7", am.explanation)

    def test_minor_node_dominant_matches_resolving_dom7_edge(self):
        # Every minor node's stated dominant is (enharmonically) the dom7 node the
        # graph connects to it via resolves_to. At the circle's sharp/flat seam
        # the spellings differ (C# minor's dominant G#7 == the graph's Ab7 node),
        # so compare by pitch class -- the honest invariant.
        for n in self.net.nodes:
            if n.kind != "minor_key":
                continue
            stated_pc = note_pc(n.data["dominantSeventh"][:-1])   # "G#7" -> pc(G#)
            resolvers = [e.source for e in self.net.edges
                         if e.relation == "resolves_to" and e.target == n.id]
            dom_pcs = {self.net.node(s).pitch_class for s in resolvers
                       if self.net.node(s).kind == "dominant_seventh"}
            self.assertIn(stated_pc, dom_pcs,
                          f"{n.label}: stated dominant "
                          f"{n.data['dominantSeventh']} (pc {stated_pc}) not "
                          f"enharmonic to any dom7 resolving to it ({dom_pcs})")

    def test_c_minor_dominant_is_g7(self):
        # parallel/relative coincidence: C minor's dominant is also G7.
        cm = self.net.node(minor_node_id("C"))
        self.assertEqual(cm.data["dominantSeventh"], "G7")
        self.assertEqual(cm.data["leadingDiminished"], "B°")


# ---------------------------------------------------------------------------
# 3c. Enharmonic-correct edge labels (regression for shares_scale_with prose).
# ---------------------------------------------------------------------------

class TestEnharmonicEdgeLabels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.net = build_network()

    def test_shares_scale_uses_correct_diatonic_spelling(self):
        # F# major's iii is A#m, NOT Bbm; Db major's ii is Ebm, NOT D#m.
        for e in self.net.edges:
            if e.relation != "shares_scale_with":
                continue
            src = self.net.node(e.source).label
            if src == "F#" and "(the iii chord)" in e.explanation:
                self.assertIn("A#m is diatonic", e.explanation)
                self.assertNotIn("Bbm is diatonic", e.explanation)
            if src == "Db" and "(the ii chord)" in e.explanation:
                self.assertIn("Ebm is diatonic", e.explanation)
                self.assertNotIn("D#m is diatonic", e.explanation)


# ---------------------------------------------------------------------------
# 4. Launch status (triad launchable; seventh reserved)
# ---------------------------------------------------------------------------

class TestLaunchStatus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.net = build_network()

    def _launchable(self, node):
        return [t for t in node.trainer_specs if t["status"] == "launchable"]

    def _reserved(self, node):
        return [t for t in node.trainer_specs if t["status"] == "reserved"]

    def test_major_key_drill_is_launchable(self):
        c = self.net.node(major_node_id("C"))
        launch = self._launchable(c)
        self.assertTrue(launch)
        spec = HarmonyExerciseSpec.from_dict(launch[0]["spec"])
        self.assertEqual(spec.drill, "full_key")
        self.assertLessEqual(len(compile_exercise(spec)), MAX_CHORDS_PER_SPEC)

    def test_minor_key_drill_is_launchable(self):
        am = self.net.node(minor_node_id("A"))
        launch = self._launchable(am)
        self.assertTrue(launch)
        spec = HarmonyExerciseSpec.from_dict(launch[0]["spec"])
        self.assertEqual(spec.mode, "natural_minor")

    def test_diminished_triad_drill_is_launchable(self):
        b = self.net.node(dim_node_id("B"))
        launch = self._launchable(b)
        self.assertTrue(launch)
        spec = HarmonyExerciseSpec.from_dict(launch[0]["spec"])
        # a real diatonic triad drill (vii°->I), never a seventh-chord drill
        self.assertEqual(spec.drill, "function")

    def test_seventh_chord_drill_is_reserved_not_launchable(self):
        g7 = self.net.node(dom7_node_id("G"))
        reserved = self._reserved(g7)
        self.assertTrue(reserved, "G7 must expose a reserved seventh drill")
        self.assertIsNone(reserved[0]["spec"])
        self.assertEqual(reserved[0]["drill"], "seventh_chord")

    def test_dominant_node_offers_closest_triad_drill(self):
        g7 = self.net.node(dom7_node_id("G"))
        launch = self._launchable(g7)
        self.assertTrue(launch, "G7 must offer the closest available triad drill")
        spec = HarmonyExerciseSpec.from_dict(launch[0]["spec"])
        # the V->I resolution in C major (triad surrogate), NOT a seventh chord
        self.assertEqual(spec.drill, "function")
        self.assertEqual(spec.pattern, ["V", "I"])
        self.assertEqual(spec.keys, ["C"])

    def test_no_launchable_spec_claims_to_be_a_seventh_chord(self):
        for n in self.net.nodes:
            for t in n.trainer_specs:
                if t["status"] == "launchable":
                    self.assertIsNotNone(t["spec"])
                    self.assertNotEqual(t["drill"], "seventh_chord")

    def test_every_launchable_spec_respects_cap(self):
        for n in self.net.nodes:
            for t in n.trainer_specs:
                if t["status"] != "launchable":
                    continue
                spec = HarmonyExerciseSpec.from_dict(t["spec"])
                compiled = compile_exercise(spec)
                self.assertLessEqual(len(compiled), MAX_CHORDS_PER_SPEC,
                                     f"{n.id}: {t['exerciseId']} too long")

    def test_payload_launchables_and_counts(self):
        payload = self.net.to_payload()
        counts = payload["counts"]
        self.assertEqual(counts["reservedDrills"], 12)     # one per dominant 7th
        self.assertEqual(counts["nodesByKind"]["dominant_seventh"], 12)
        # every launchable in the flat list has a real spec; reserved have none
        for item in payload["launchables"]:
            if item["status"] == "launchable":
                self.assertIsNotNone(item["spec"])
            else:
                self.assertIsNone(item["spec"])


# ---------------------------------------------------------------------------
# 5. Payload shape + backward compatibility
# ---------------------------------------------------------------------------

class TestPayloadShape(unittest.TestCase):
    def test_payload_schema_and_keys(self):
        payload = build_network_payload()
        self.assertEqual(payload["schema"], "harmony-network/v1")
        for key in ("template", "nodes", "edges", "legend", "launchables", "counts"):
            self.assertIn(key, payload)
        # legend carries the four visual classes
        vis = {nc["visualClass"] for nc in payload["legend"]["nodeClasses"]}
        self.assertEqual(vis, {"pink", "blue", "yellow", "purple"})

    def test_every_node_has_required_fields(self):
        payload = build_network_payload()
        for n in payload["nodes"]:
            for field in ("id", "label", "kind", "pitchClass", "spelling",
                          "quality", "x", "y", "radius", "visualClass",
                          "explanation", "atlasRefs", "trainerSpecs"):
                self.assertIn(field, n)

    def test_named_template_loads(self):
        payload = build_network_payload(
            "dominant_diminished_relative_network_v1")
        self.assertEqual(len(payload["nodes"]), 48)

    def test_existing_layers_still_import(self):
        # The network is purely additive; existing entry points must keep working.
        from harmony.atlas import build_atlas
        from harmony.circle_payload import build_circle_payload
        from harmony.exercise_spec import default_exercise_groups
        self.assertTrue(build_atlas().nodes)
        self.assertEqual(build_circle_payload()["schema"], "harmony-circle/v1")
        self.assertTrue(default_exercise_groups())


# ---------------------------------------------------------------------------
# 6. Graph-relevant trainer groups (PATCH 3) -- the embedded trainer must only
#    expose drills the graph actually visualises.
# ---------------------------------------------------------------------------

class TestNetworkTrainerGroups(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.net = build_network()
        cls.groups = cls.net.trainer_groups()
        # every exercise_id that any graph node advertises as launchable
        cls.node_launchable_ids = {
            t["spec"]["exercise_id"]
            for n in cls.net.nodes for t in n.trainer_specs
            if t.get("status") == "launchable" and t.get("spec")
        }

    def test_groups_are_the_network_relevance_groups(self):
        # The legacy reference network populates exactly its four legacy-kind groups
        # (NETWORK_GROUP_BY_KIND also carries key-local groups now, but the legacy graph has
        # no nodes of those kinds, so trainer_groups drops them as empty).
        legacy_group_names = {
            NETWORK_GROUP_BY_KIND[k] for k in
            ("major_key", "minor_key", "diminished_triad", "dominant_seventh")
        }
        self.assertEqual(set(self.groups.keys()), legacy_group_names)
        self.assertTrue(set(self.groups.keys()) <= set(NETWORK_GROUP_BY_KIND.values()))

    def test_group_sizes_cover_every_key(self):
        # 12 major + 12 minor + 12 leading-tone dim + 12 dominant resolutions.
        for name, specs in self.groups.items():
            self.assertEqual(len(specs), 12, f"{name} should have 12 drills")
        total = sum(len(v) for v in self.groups.values())
        self.assertEqual(total, 48)

    def test_only_network_launchables_appear(self):
        # Every dropdown spec traces back to a launchable graph-node entry.
        for specs in self.groups.values():
            for spec in specs:
                self.assertIn(spec.exercise_id, self.node_launchable_ids,
                              f"{spec.exercise_id} is not a graph-node launchable")

    def test_no_reserved_seventh_chord_drill_in_dropdown(self):
        for specs in self.groups.values():
            for spec in specs:
                self.assertNotEqual(spec.drill, "seventh_chord")
                self.assertIn(spec.drill, {"full_key", "function"})

    def test_every_dropdown_spec_compiles_within_cap(self):
        for specs in self.groups.values():
            for spec in specs:
                compiled = compile_exercise(spec)
                self.assertLessEqual(len(compiled), MAX_CHORDS_PER_SPEC)

    def test_groups_are_far_smaller_than_full_default_set(self):
        # Regression for the original bug: the network trainer must not surface
        # the full ~100-exercise generic registry.
        from harmony.exercise_spec import all_default_specs
        self.assertLess(48, len(all_default_specs()))


# ---------------------------------------------------------------------------
# 7. Python launch bridge (PATCH 1) -- what the JS queues must load cleanly.
# ---------------------------------------------------------------------------

class TestPythonLaunchBridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.net = build_network()

    def test_every_launchable_spec_round_trips_like_on_launch(self):
        # HarmonicNetworkWindow._on_launch does HarmonyExerciseSpec.from_dict(d).
        # Every launchable entry the JS could queue must survive that unchanged.
        launchable = 0
        for item in self.net.launchables():
            if item["status"] == "launchable":
                launchable += 1
                spec = HarmonyExerciseSpec.from_dict(item["spec"])  # must not raise
                self.assertEqual(spec.drill, item["drill"])
                self.assertTrue(item["spec"].get("drill"),
                                "queued dict must carry a 'drill' the host checks")
            else:
                self.assertIsNone(item["spec"])
        self.assertEqual(launchable, 48)

    def test_reserved_entries_are_never_launchable(self):
        reserved = [i for i in self.net.launchables() if i["status"] == "reserved"]
        self.assertEqual(len(reserved), 12)         # one per dominant seventh
        for item in reserved:
            self.assertIsNone(item["spec"])
            self.assertEqual(item["drill"], "seventh_chord")


# ---------------------------------------------------------------------------
# 8. Planned-template registry (PATCH 5) -- stubs must not break get_template().
# ---------------------------------------------------------------------------

class TestPlannedTemplates(unittest.TestCase):
    def test_default_get_template_still_works(self):
        tpl = get_template()
        self.assertEqual(tpl.template_id,
                         "dominant_diminished_relative_network_v1")
        # named lookup of the buildable template also still works
        self.assertEqual(
            get_template("dominant_diminished_relative_network_v1").template_id,
            "dominant_diminished_relative_network_v1")

    def test_planned_stubs_have_required_metadata(self):
        self.assertTrue(PLANNED_TEMPLATES)
        for pt in list_planned_templates():
            for field in ("template_id", "title", "description", "rationale",
                          "status", "priority", "dependencies"):
                self.assertIn(field, pt)
            self.assertEqual(pt["status"], "planned")

    def test_planned_templates_are_not_buildable(self):
        # A planned stub is metadata-only -> get_template must reject it cleanly.
        for pt in PLANNED_TEMPLATES:
            with self.assertRaises(KeyError):
                get_template(pt.template_id)

    def test_audited_candidates_are_present(self):
        # The post-MVP candidates remain planned stubs after the core template graduates.
        ids = {pt.template_id for pt in PLANNED_TEMPLATES}
        for expected in ("transposition_orbit_network_v1",
                         "quality_class_network_v1",
                         "functional_equivalence_network_v1"):
            self.assertIn(expected, ids)
        # core has graduated into the buildable registry
        self.assertNotIn("core_triad_function_network_v1", ids)

    def test_list_templates_mixes_implemented_and_planned(self):
        statuses = {t["template_id"]: t["status"] for t in list_templates()}
        self.assertEqual(statuses["dominant_diminished_relative_network_v1"],
                         "implemented")
        self.assertEqual(statuses["core_triad_function_network_v1"], "implemented")
        self.assertEqual(statuses["quality_class_network_v1"], "planned")


# ---------------------------------------------------------------------------
# 9. Regression: deterministic node/edge counts (PATCH 6).
# ---------------------------------------------------------------------------

class TestRegressionCounts(unittest.TestCase):
    def test_build_network_node_edge_counts_are_deterministic(self):
        a, b = build_network(), build_network()
        self.assertEqual(len(a.nodes), 48)
        self.assertEqual(len(b.nodes), 48)
        self.assertEqual(len(a.edges), len(b.edges))
        ca, cb = a.counts(), b.counts()
        self.assertEqual(ca, cb)
        self.assertEqual(ca["launchableDrills"], 48)
        self.assertEqual(ca["reservedDrills"], 12)

    def test_edge_counts_are_a_pinned_fingerprint(self):
        # Literal totals so adding/removing a generation rule is actually caught
        # (a two-build comparison alone would not notice -- both builds change).
        net = build_network()
        self.assertEqual(len(net.nodes), 48)
        self.assertEqual(len(net.edges), 240)
        self.assertEqual(net.counts()["nodesByKind"], {
            "major_key": 12, "minor_key": 12,
            "dominant_seventh": 12, "diminished_triad": 12,
        })
        self.assertEqual(net.counts()["edgesByRelation"], {
            "fifth_relation": 12,
            "relative_minor_of": 12, "relative_major_of": 12,
            "dominant_of": 12, "resolves_to": 36,
            "leading_tone_to": 24, "same_function": 12,
            "shares_scale_with": 36, "same_pitch_class": 36,
            "trainer_drill_available": 24, "atlas_node_available": 24,
        })

    def test_launchables_partition_into_launchable_and_reserved(self):
        net = build_network()
        for item in net.launchables():
            self.assertIn(item["status"], {"launchable", "reserved"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
