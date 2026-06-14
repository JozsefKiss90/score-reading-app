"""Tests for the Interactive Harmony Atlas model layer (harmony.atlas).

The Atlas is the deterministic ontology + view layer above the Harmony Trainer.
These tests enforce its contract (the Atlas spec, "Implementation rules"):

  * single source of truth -- every value matches the theory engine; nothing is
    hard-coded (cross-checked against theory.diatonic_harmony);
  * deterministic -- repeated builds are identical;
  * every clickable node resolves to a HarmonyExerciseSpec that validates,
    compiles, and builds well-formed MusicXML;
  * graph integrity -- typed edges whose endpoints all exist;
  * synchronisation maps a trainer target onto the correct active nodes;
  * to_json round-trips; real-score analysis is reserved (raises).

Run from the project root::

    .venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -t .
"""

import json
import os
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from theory.diatonic_harmony import (  # noqa: E402
    generate_diatonic_triads,
    QUALITY_TO_INTERVAL_LAYER,
)
from harmony.exercise_spec import (  # noqa: E402
    HarmonyExerciseSpec,
    compile_exercise,
    MAX_CHORDS_PER_SPEC,
    DEFAULT_MAJOR_KEYS,
    DEFAULT_MINOR_KEYS,
)
from harmony.musicxml_builder import build_musicxml, build_trainer_payload  # noqa: E402
from harmony.atlas import (  # noqa: E402
    Atlas,
    build_atlas,
    ScoreAnalysis,
    HarmonyAnnotation,
    RELATIONS,
    scale_id,
    degree_id,
    triad_id,
    quality_id,
    layer_id,
    function_id,
)


class TestOntology(unittest.TestCase):
    def setUp(self):
        self.atlas = build_atlas()

    def test_deterministic_build(self):
        a, b = Atlas(), Atlas()
        self.assertEqual(list(a.nodes.keys()), list(b.nodes.keys()))
        self.assertEqual([e.to_dict() for e in a.edges],
                         [e.to_dict() for e in b.edges])

    def test_node_counts(self):
        kinds = {}
        for n in self.atlas.nodes.values():
            kinds[n.kind] = kinds.get(n.kind, 0) + 1
        self.assertEqual(kinds["scale"], 24)          # 12 major + 12 minor
        self.assertEqual(kinds["triad"], 24 * 7)      # 168 concrete triads
        self.assertEqual(kinds["degree"], 14)         # 7 per mode
        # quality + layer derive 1:1 from the theory table.
        self.assertEqual(kinds["quality"], len(QUALITY_TO_INTERVAL_LAYER))
        self.assertEqual(kinds["layer"], len(QUALITY_TO_INTERVAL_LAYER))

    def test_edges_are_typed_and_endpoints_exist(self):
        ids = set(self.atlas.nodes)
        for e in self.atlas.edges:
            self.assertIn(e.relation, RELATIONS, e)
            self.assertIn(e.source, ids, e)
            self.assertIn(e.target, ids, e)

    def test_graph_default_omits_triads_but_keeps_endpoints(self):
        g = self.atlas.graph(include_triads=False)
        ids = {n["id"] for n in g["nodes"]}
        self.assertFalse(any(n["kind"] == "triad" for n in g["nodes"]))
        for e in g["edges"]:
            self.assertIn(e["source"], ids)
            self.assertIn(e["target"], ids)

    def test_graph_full_includes_triads(self):
        g = self.atlas.graph(include_triads=True)
        self.assertEqual(len(g["nodes"]), len(self.atlas.nodes))


class TestSingleSourceOfTruth(unittest.TestCase):
    """Every Atlas value must equal what the theory engine produces."""

    def setUp(self):
        self.atlas = build_atlas()

    def test_triad_nodes_match_theory_engine(self):
        for mode, keys in (("major", DEFAULT_MAJOR_KEYS),
                           ("natural_minor", DEFAULT_MINOR_KEYS)):
            for key in keys:
                for t in generate_diatonic_triads(key, mode):
                    node = self.atlas.node(triad_id(key, mode, t.degree_index))
                    self.assertIsNotNone(node, (key, mode, t.degree_index))
                    self.assertEqual(node.data["roman"], t.roman)
                    self.assertEqual(node.data["chordSymbol"], t.chord_symbol)
                    self.assertEqual(node.data["quality"], t.chord_quality)
                    self.assertEqual(node.data["chordTones"], list(t.pitches))
                    self.assertEqual(node.data["intervalLayer"], t.interval_layer)
                    self.assertEqual(node.data["functionLabel"], t.function_label)

    def test_quality_layer_pairs_match_theory_table(self):
        for quality, layer in QUALITY_TO_INTERVAL_LAYER.items():
            self.assertIsNotNone(self.atlas.node(quality_id(quality)))
            self.assertEqual(self.atlas.node(quality_id(quality)).data["intervalLayer"],
                             layer)
            self.assertIsNotNone(self.atlas.node(layer_id(layer)))

    def test_global_map_is_invariant_pattern(self):
        self.assertEqual(
            [r["roman"] for r in self.atlas.global_map("major")],
            ["I", "ii", "iii", "IV", "V", "vi", "vii°"])
        self.assertEqual(
            [r["roman"] for r in self.atlas.global_map("natural_minor")],
            ["i", "ii°", "III", "iv", "v", "VI", "VII"])

    def test_transposition_cells_match_master_table(self):
        # G major V = D (D-F#-A); G major vii° = F#° -- from the user's master.md.
        tm = self.atlas.transposition_matrix("major")
        vrow = next(r for r in tm["rows"] if r["roman"] == "V")
        gcell = next(c for c in vrow["cells"] if c["key"] == "G")
        self.assertEqual(gcell["chordSymbol"], "D")
        self.assertEqual(gcell["chordTones"], ["D", "F#", "A"])
        viirow = next(r for r in tm["rows"] if r["roman"] == "vii°")
        self.assertEqual(
            next(c for c in viirow["cells"] if c["key"] == "G")["chordSymbol"], "F#°")


class TestClickableSpecs(unittest.TestCase):
    """Every node that is clickable must produce a real, playable exercise."""

    def setUp(self):
        self.atlas = build_atlas()
        self.specs = [n.spec for n in self.atlas.nodes.values() if n.spec is not None]

    def test_there_are_clickable_specs(self):
        # scales (24) + degrees (14) + triads (168) + cadences (10) at least.
        self.assertGreaterEqual(len(self.specs), 24 + 14 + 168 + 10)

    def test_all_specs_validate_compile_within_cap(self):
        for s in self.specs:
            s.validate()
            compiled = compile_exercise(s)
            self.assertGreater(len(compiled), 0, s.exercise_id)
            self.assertLessEqual(len(compiled), MAX_CHORDS_PER_SPEC, s.exercise_id)

    def test_all_specs_build_wellformed_musicxml(self):
        # Sample one spec per node-kind to keep the test fast but representative.
        seen_kind = {}
        for n in self.atlas.nodes.values():
            if n.spec and n.kind not in seen_kind:
                seen_kind[n.kind] = n.spec
        for kind, spec in seen_kind.items():
            ET.fromstring(build_musicxml(compile_exercise(spec)))

    def test_specs_round_trip_through_json(self):
        for s in self.specs:
            again = HarmonyExerciseSpec.from_dict(s.to_dict())
            self.assertEqual(again.exercise_id, s.exercise_id)
            self.assertEqual(again.drill, s.drill)


def _walk_specs(obj):
    """Yield every embedded spec dict (has exercise_id + drill) anywhere in ``obj``."""
    found = []

    def rec(o):
        if isinstance(o, dict):
            if "exercise_id" in o and "drill" in o:
                found.append(o)
            for v in o.values():
                rec(v)
        elif isinstance(o, list):
            for v in o:
                rec(v)

    rec(obj)
    return found


class TestEveryPayloadSpecRespectsCap(unittest.TestCase):
    """Not just node specs -- EVERY spec embedded in to_json() must stay readable.

    (Regression guard: quality/interval-layer view specs once passed all 12 keys,
    compiling to 36 chords -- far over the cap -- before being chunked.)
    """

    def test_all_embedded_specs_compile_within_cap(self):
        payload = build_atlas().to_json()
        specs = _walk_specs(payload)
        self.assertGreater(len(specs), 200)            # node + view specs
        for d in specs:
            spec = HarmonyExerciseSpec.from_dict(d)
            compiled = compile_exercise(spec)
            self.assertLessEqual(
                len(compiled), MAX_CHORDS_PER_SPEC,
                f"{d['exercise_id']} compiles to {len(compiled)} chords (> cap)")

    def test_quality_view_spec_is_chunked(self):
        atlas = build_atlas()
        qm = atlas.quality_matrix("major")
        major_cat = next(c for c in qm if c["quality"] == "major")
        # The view shows all 12 keys' entries, but the launchable spec is capped.
        self.assertEqual(len(major_cat["entries"]), 36)          # 3 per key x 12
        self.assertGreater(len(major_cat["specs"]), 1)           # split into chunks
        first = compile_exercise(HarmonyExerciseSpec.from_dict(major_cat["spec"]))
        self.assertLessEqual(len(first), MAX_CHORDS_PER_SPEC)


class TestSync(unittest.TestCase):
    def setUp(self):
        self.atlas = build_atlas()

    def test_sync_maps_trainer_target_to_active_nodes(self):
        spec = HarmonyExerciseSpec(exercise_id="g", title="G", drill="full_key",
                                   mode="major", key="G major")
        payload = build_trainer_payload(compile_exercise(spec))
        v_target = payload["TARGET_CHORDS"][4]   # V of G major = D major
        active = self.atlas.sync(v_target)["active"]
        self.assertEqual(active["scale"], scale_id("G", "major"))
        self.assertEqual(active["degree"], degree_id("major", "V"))
        self.assertEqual(active["triad"], triad_id("G", "major", 4))
        self.assertEqual(active["quality"], quality_id("major"))
        self.assertEqual(active["layer"], layer_id("M3+m3"))
        self.assertEqual(active["function"], function_id("major", "dominant"))

    def test_sync_active_ids_all_exist(self):
        spec = HarmonyExerciseSpec(exercise_id="am", title="Am", drill="full_key",
                                   mode="natural_minor", key="A minor")
        payload = build_trainer_payload(compile_exercise(spec))
        for t in payload["TARGET_CHORDS"]:
            for nid in self.atlas.sync(t)["activeIds"]:
                self.assertIn(nid, self.atlas.nodes)


class TestViewsAndProgress(unittest.TestCase):
    def setUp(self):
        self.atlas = build_atlas()

    def test_quality_matrix_diminished_is_one_per_key(self):
        qm = self.atlas.quality_matrix("major")
        dim = next(c for c in qm if c["quality"] == "diminished")
        self.assertEqual(len(dim["entries"]), 12)
        self.assertEqual(dim["intervalLayer"], "m3+m3")

    def test_function_map_dominant_group_in_c_major(self):
        fm = self.atlas.function_map("major")
        drow = next(r for r in fm["rows"] if r["functionLabel"] == "dominant")
        ccell = next(c for c in drow["cells"] if c["key"] == "C")
        self.assertEqual(sorted(ch["chordSymbol"] for ch in ccell["chords"]),
                         ["B°", "G"])

    def test_cadence_map_ii_v_i_and_all_keys(self):
        cm = self.atlas.cadence_map()
        ii_v_i = next(n for n in cm if n["label"] == "ii–V–I")
        self.assertEqual([c["chordSymbol"] for c in ii_v_i["referenceChords"]],
                         ["Dm", "G", "C"])
        self.assertEqual(len(ii_v_i["keysTable"]), 12)

    def test_cadence_map_has_canonical_set(self):
        labels = {n["label"] for n in self.atlas.cadence_map()}
        for required in ("I–IV–V–I", "ii–V–I", "vi–ii–V–I", "I–V–vi–IV",
                         "i–iv–v–i", "i–VI–VII–i"):
            self.assertIn(required, labels)

    def test_progress_categories_and_percent(self):
        pm = self.atlas.progress_map(completed_ids=set())
        names = [c["category"] for c in pm["categories"]]
        self.assertEqual(names, ["Scales", "Triads", "Functions", "Cadences"])
        self.assertEqual(pm["overallPercent"], 0.0)
        # Marking one scale done lifts the Scales category off zero.
        scales = next(n.spec for n in self.atlas.nodes_of_kind("scale") if n.spec)
        pm2 = self.atlas.progress_map(completed_ids={scales.exercise_id})
        scat = next(c for c in pm2["categories"] if c["category"] == "Scales")
        self.assertEqual(scat["completed"], 1)
        self.assertGreater(scat["percent"], 0.0)

    def test_learning_path_has_seven_levels(self):
        lp = self.atlas.learning_path()
        self.assertEqual([l["level"] for l in lp], [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(lp[0]["id"], "scales")
        self.assertEqual(lp[-1]["id"], "real_music")


class TestSerialisationAndReservedApi(unittest.TestCase):
    def setUp(self):
        self.atlas = build_atlas()

    def test_to_json_is_serialisable_and_complete(self):
        payload = self.atlas.to_json()
        text = json.dumps(payload)              # raises if not serialisable
        self.assertGreater(len(text), 0)
        for key in ("schema", "globalMap", "transpositionMatrix", "qualityMatrix",
                    "functionMap", "intervalLayerMap", "cadenceMap", "learningPath",
                    "progress", "graph"):
            self.assertIn(key, payload)

    def test_score_analysis_is_reserved(self):
        sa = ScoreAnalysis()
        for method in ("analyze_score", "extract_harmony", "extract_functions",
                       "extract_cadences"):
            with self.assertRaises(NotImplementedError):
                getattr(sa, method)("dummy.musicxml")

    def test_annotation_maps_to_triad_node(self):
        ann = HarmonyAnnotation(offset=0.0, measure=1, key="G major", mode="major",
                                roman="V")
        self.assertEqual(self.atlas.node_for_annotation(ann),
                         triad_id("G", "major", 4))


if __name__ == "__main__":
    unittest.main(verbosity=2)
