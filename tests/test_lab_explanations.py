"""Tests for the Music Theory Laboratory explanation layer (harmony.lab_explanations).

These run headless (no Qt / no display).  They enforce the explanation
contract (Parts 4-7 of the lab-workspace spec):

  * every implemented concept has a complete, non-empty theory explanation;
  * experiment explanations are *assembled from the compiled experiment* -- the
    inversion explanation names the invariant tones and the changing bass, the
    cadence explanation gives the function path + bass motion, the motive
    explanation gives the degree pattern + transposed notes, the polyphonic
    explanation gives the implied harmony;
  * specific musical facts are derived (Part 7): a key/chord/tone string is never
    hand-written -- changing the spec changes the prose;
  * per-measure "Current Mapping" payloads carry valid Atlas node ids (that exist
    in the ontology) and the related edges;
  * the explanation module is pure (no PyQt6).

Run from the project root::

    .venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -t .
"""

import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from harmony.lab import compile_lab, lab_demo_specs  # noqa: E402
from harmony.lab_spec import LabExperimentSpec, spec_from_lab_request  # noqa: E402
from harmony.atlas import build_atlas, triad_id  # noqa: E402
from harmony.lab_explanations import (  # noqa: E402
    CONCEPT_KEYS,
    canonical_concept,
    get_concept_explanation,
    all_concept_explanations,
    get_experiment_explanation,
    get_measure_explanation,
    mapping_from_target,
    _REQUIRED_CONCEPT_FIELDS,
)


def _demo(eid):
    return next(s for s in lab_demo_specs() if s.experiment_id == eid)


# ---------------------------------------------------------------------------
class TestConceptExplanations(unittest.TestCase):
    def test_every_concept_has_explanation(self):
        for concept in CONCEPT_KEYS:
            ex = get_concept_explanation(concept)
            self.assertEqual(ex["concept"], concept)

    def test_required_fields_present_and_nonempty(self):
        for concept in CONCEPT_KEYS:
            ex = get_concept_explanation(concept)
            for field in _REQUIRED_CONCEPT_FIELDS:
                self.assertIn(field, ex, (concept, field))
                self.assertTrue(ex[field], (concept, field))   # no empty string/list

    def test_no_empty_title_definition_core_idea(self):
        for concept in CONCEPT_KEYS:
            ex = get_concept_explanation(concept)
            for field in ("title", "short_definition", "core_idea"):
                self.assertTrue(ex[field].strip(), (concept, field))

    def test_list_fields_are_lists(self):
        list_fields = ["what_to_listen_for", "what_to_play", "theory_terms",
                       "atlas_connections", "common_misconceptions", "next_steps"]
        for concept in CONCEPT_KEYS:
            ex = get_concept_explanation(concept)
            for field in list_fields:
                self.assertIsInstance(ex[field], list, (concept, field))

    def test_aliases_map_to_canonical(self):
        self.assertEqual(canonical_concept("cadence"), "voice_leading")
        self.assertEqual(canonical_concept("voice_leading_cadence"), "voice_leading")
        self.assertEqual(canonical_concept("polyphonic"), "polyphonic_harmony")
        self.assertEqual(canonical_concept("real_score_analysis"), "reduction")
        for selector in ("inversion", "voice_leading_cadence", "motive",
                         "polyphonic_harmony", "real_score_analysis"):
            ex = get_concept_explanation(selector)
            self.assertTrue(ex["title"])

    def test_unknown_concept_raises(self):
        with self.assertRaises(ValueError):
            get_concept_explanation("quintal_harmony")

    def test_all_concept_explanations_covers_every_key(self):
        self.assertEqual(set(all_concept_explanations()), set(CONCEPT_KEYS))


# ---------------------------------------------------------------------------
class TestExperimentExplanations(unittest.TestCase):
    def test_inversion_includes_invariant_tones_and_changing_bass(self):
        spec = _demo("inv_C_I")
        ee = get_experiment_explanation(spec, compile_lab(spec))
        self.assertEqual(ee["concept"], "inversion")
        # Invariant tones derived from the chord (C-E-G), not hand-written.
        self.assertTrue(any("C-E-G" in inv for inv in ee["invariants"]))
        self.assertTrue(any("root identity C" in inv for inv in ee["invariants"]))
        # The changing bass C -> E -> G appears across the change list.
        changes = " ".join(ee["changes"])
        for note in ("bass C", "bass E", "bass G"):
            self.assertIn(note, changes)
        # Practice prose compares the three slash positions.
        practice = " ".join(ee["practice"])
        self.assertIn("C/E", practice)
        self.assertIn("C/G", practice)
        self.assertEqual(len(ee["sections"]), 3)

    def test_cadence_includes_function_path_and_bass_motion(self):
        spec = _demo("cad_V_I_C")
        ee = get_experiment_explanation(spec, compile_lab(spec))
        self.assertEqual(ee["concept"], "voice_leading")
        facts = {f["label"]: f["value"] for f in ee["facts"]}
        self.assertIn("Function path", facts)
        self.assertIn("dominant", facts["Function path"])
        self.assertIn("tonic", facts["Function path"])
        # Bass motion G -> C appears in the per-chord detail (derived).
        joined = " ".join(line for s in ee["sections"] for line in s["lines"])
        self.assertIn("G → C", joined)
        self.assertIn("leading tone", joined.lower())

    def test_motive_includes_degree_pattern_and_transposed_notes(self):
        spec = _demo("motive_1353_major")
        ee = get_experiment_explanation(spec, compile_lab(spec))
        self.assertEqual(ee["concept"], "motive")
        facts = {f["label"]: f["value"] for f in ee["facts"]}
        self.assertIn("Degree pattern", facts)
        self.assertIn("^1", facts["Degree pattern"])
        # 12 keys, each section names the transposed notes.
        self.assertEqual(len(ee["sections"]), 12)
        c_section = next(s for s in ee["sections"] if s["title"].startswith("C "))
        self.assertIn("C-E-G-E", " ".join(c_section["lines"]))
        g_section = next(s for s in ee["sections"] if s["title"].startswith("G "))
        self.assertIn("G-B-D-B", " ".join(g_section["lines"]))
        self.assertIn("transpositionPath", ee)
        self.assertEqual(ee["transpositionPath"][0], "C")

    def test_polyphonic_includes_implied_harmony(self):
        spec = _demo("poly_I_V_I_C")
        ee = get_experiment_explanation(spec, compile_lab(spec))
        self.assertEqual(ee["concept"], "polyphonic_harmony")
        facts = {f["label"]: f["value"] for f in ee["facts"]}
        self.assertIn("Implied progression", facts)
        self.assertEqual(facts["Implied progression"], "I-V-I")
        joined = " ".join(line for s in ee["sections"] for line in s["lines"])
        self.assertIn("Implies", joined)
        self.assertIn("Atlas triad node", joined)

    def test_reduction_explanation_is_reserved_prose(self):
        spec = LabExperimentSpec("r", "Reserved", concept="reduction", key="C major")
        # reduction does not compile_lab; explanation works off the spec alone.
        class _Empty:
            measures = []
            title = "Reserved"
        ee = get_experiment_explanation(spec, _Empty())
        self.assertEqual(ee["concept"], "reduction")
        self.assertIn("reserved", ee["summary"].lower())

    def test_every_demo_experiment_explanation_has_summary(self):
        for spec in lab_demo_specs():
            ee = get_experiment_explanation(spec, compile_lab(spec))
            self.assertTrue(ee["summary"].strip(), spec.experiment_id)
            self.assertTrue(ee["title"])
            self.assertTrue(ee["facts"])

    def test_facts_are_derived_not_hardcoded(self):
        # Same concept, different key -> the key fact changes (proves derivation).
        a = get_experiment_explanation(_demo("inv_C_I"), compile_lab(_demo("inv_C_I")))
        spec_g = LabExperimentSpec(
            "inv_G_I", "Inversions of G major I", concept="inversion",
            key="G major", render="block", parameters={"degree": "I"})
        b = get_experiment_explanation(spec_g, compile_lab(spec_g))
        self.assertNotEqual(a["summary"], b["summary"])
        self.assertIn("G major", b["key"])
        self.assertTrue(any("G-B-D" in inv for inv in b["invariants"]))


# ---------------------------------------------------------------------------
class TestMeasureMapping(unittest.TestCase):
    def setUp(self):
        self.atlas = build_atlas()

    def test_measure_atlas_ids_exist_in_ontology(self):
        for spec in lab_demo_specs():
            exp = compile_lab(spec)
            for m in exp.measures:
                mp = get_measure_explanation(m, atlas=self.atlas)
                for nid in mp["atlasNodeIds"].values():
                    self.assertIsNotNone(self.atlas.node(nid),
                                         (spec.experiment_id, nid))

    def test_inversion_measure_mapping_payload(self):
        exp = compile_lab(_demo("inv_C_I"))
        mp = get_measure_explanation(exp.measures[1], atlas=self.atlas,
                                     experiment_title=exp.title)
        self.assertEqual(mp["concept"], "inversion")
        self.assertEqual(mp["measureNumber"], 2)
        self.assertEqual(mp["key"], "C major")
        self.assertEqual(mp["roman"], "I")
        self.assertEqual(mp["chordSymbol"], "C")
        self.assertEqual(mp["tones"], ["C", "E", "G"])
        self.assertIsNotNone(mp["inversion"])
        self.assertEqual(mp["inversion"]["label"], "first inversion")
        self.assertEqual(mp["inversion"]["figuredBass"], "6")
        self.assertEqual(mp["inversion"]["slash"], "C/E")
        self.assertEqual(mp["atlasNodeIds"]["triad"], triad_id("C", "major", 0))
        self.assertTrue(mp["atlasEdges"])           # related edges attached

    def test_cadence_measure_mapping_has_bass_motion(self):
        exp = compile_lab(_demo("cad_V_I_C"))
        mp = get_measure_explanation(exp.measures[1])
        self.assertEqual(mp["concept"], "voice_leading")
        self.assertIsNotNone(mp["cadence"])
        self.assertEqual(mp["cadence"]["bassMotion"], "G → C")
        self.assertEqual(mp["cadence"]["commonTones"], ["G"])
        self.assertTrue(mp["cadence"]["tendencyTones"])

    def test_motive_measure_mapping_has_notes(self):
        exp = compile_lab(_demo("motive_1353_major"))
        mp = get_measure_explanation(exp.measures[0])
        self.assertEqual(mp["concept"], "motive")
        self.assertIsNotNone(mp["motive"])
        self.assertEqual(mp["motive"]["notes"], ["C", "E", "G", "E"])

    def test_polyphonic_measure_mapping_has_implied(self):
        exp = compile_lab(_demo("poly_I_V_I_C"))
        mp = get_measure_explanation(exp.measures[1])
        self.assertEqual(mp["concept"], "polyphonic_harmony")
        self.assertIsNotNone(mp["polyphony"])
        self.assertEqual(mp["polyphony"]["impliedRoman"], "V")

    def test_mapping_from_target_round_trips_lab_payload(self):
        # The runtime fallback path: build a mapping from a lab payload target.
        from harmony.lab_musicxml import build_lab_payload
        payload = build_lab_payload(compile_lab(_demo("inv_C_I")))
        target = payload["TARGET_BY_MEASURE"]["1"]
        mp = mapping_from_target(target, atlas=self.atlas)
        self.assertEqual(mp["roman"], "I")
        self.assertEqual(mp["chordSymbol"], "C")
        self.assertIsNotNone(mp["inversion"])
        self.assertEqual(mp["inversion"]["label"], "first inversion")
        self.assertEqual(mp["atlasNodeIds"]["triad"], triad_id("C", "major", 0))
        self.assertTrue(mp["atlasEdges"])


# ---------------------------------------------------------------------------
class TestAtlasHelpers(unittest.TestCase):
    def setUp(self):
        self.atlas = build_atlas()

    def test_edges_for_returns_incident_edges(self):
        edges = self.atlas.edges_for([triad_id("C", "major", 0)])
        self.assertTrue(edges)
        for e in edges:
            self.assertIn("source", e)
            self.assertIn("relation", e)
            self.assertTrue(e["source"] == triad_id("C", "major", 0)
                            or e["target"] == triad_id("C", "major", 0))

    def test_edges_for_empty_input(self):
        self.assertEqual(self.atlas.edges_for([]), [])
        self.assertEqual(self.atlas.edges_for([None]), [])

    def test_cadence_node_id_matches_tokens(self):
        self.assertEqual(self.atlas.cadence_node_id(["ii", "V", "I"], "major"),
                         "cadence:ii_V_I_major")
        self.assertIsNotNone(self.atlas.node(
            self.atlas.cadence_node_id(["ii", "V", "I"], "major")))
        self.assertIsNone(self.atlas.cadence_node_id(["bogus"], "major"))


# ---------------------------------------------------------------------------
class TestLabRequestBridge(unittest.TestCase):
    def test_inversion_request(self):
        spec = spec_from_lab_request(
            {"labConcept": "inversion", "key": "C major", "mode": "major", "degree": "I"})
        spec.validate()
        self.assertEqual(spec.concept, "inversion")
        self.assertEqual(spec.parameters["degree"], "I")

    def test_cadence_request_defaults(self):
        spec = spec_from_lab_request(
            {"labConcept": "cadence", "key": "C major", "mode": "major"})
        self.assertEqual(spec.parameters["pattern"], ["V", "I"])
        exp = compile_lab(spec)
        self.assertEqual(len(exp.measures), 2)

    def test_voice_leading_minor_request(self):
        spec = spec_from_lab_request(
            {"labConcept": "voice_leading", "key": "A minor", "mode": "natural_minor"})
        self.assertEqual(spec.parameters["pattern"], ["iv", "v", "i"])
        compile_lab(spec)               # raises if invalid

    def test_motive_request(self):
        spec = spec_from_lab_request(
            {"labConcept": "motive", "key": "G major", "mode": "major"})
        self.assertEqual(spec.concept, "motive")
        self.assertEqual(len(compile_lab(spec).measures), 12)

    def test_invalid_request_raises(self):
        with self.assertRaises(ValueError):
            spec_from_lab_request({"labConcept": "nonsense"})
        with self.assertRaises(ValueError):
            spec_from_lab_request("not a dict")


# ---------------------------------------------------------------------------
class TestPurity(unittest.TestCase):
    def test_lab_explanations_is_pure(self):
        code = (
            "import harmony.lab_explanations, sys; "
            "bad=[m for m in sys.modules if m.split('.')[0] in ('PyQt6','verovio')]; "
            "assert not bad, bad; print('pure')")
        r = subprocess.run([sys.executable, "-c", code], cwd=PROJECT_ROOT,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("pure", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
