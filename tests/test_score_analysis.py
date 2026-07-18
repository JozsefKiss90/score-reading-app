"""Tests for the real-score analysis contract (harmony/score_analysis.py)."""

import unittest

from harmony.score_analysis import (
    SCORE_ANALYSIS_SCHEMA,
    VALID_SOURCES,
    VALID_STATUS,
    ScoreAnalysisResult,
    ScoreCadenceSpan,
    ScoreFormSection,
    ScoreHarmonySlice,
    atlas_refs_for,
    atlas_sync_target,
    canon_mode,
    diatonic_triad_match,
    network_refs_for,
    network_target_for,
    resolve_slice_refs,
)
from harmony.atlas import build_atlas


def _slice(**kw):
    base = dict(score_id="t", measure=1, key="C major", mode="major")
    base.update(kw)
    s = ScoreHarmonySlice(**base)
    return resolve_slice_refs(s)


class TestSliceContract(unittest.TestCase):
    def test_schema_and_vocab(self):
        self.assertEqual(SCORE_ANALYSIS_SCHEMA, "score-analysis/v1")
        self.assertIn("manual", VALID_SOURCES)
        self.assertEqual(set(VALID_STATUS),
                         {"ok", "ambiguous", "unsupported_chromatic"})

    def test_validate_rejects_bad_source_status_confidence(self):
        with self.assertRaises(ValueError):
            ScoreHarmonySlice(score_id="t", measure=1, source="bogus").validate()
        with self.assertRaises(ValueError):
            ScoreHarmonySlice(score_id="t", measure=1, status="nope").validate()
        with self.assertRaises(ValueError):
            ScoreHarmonySlice(score_id="t", measure=1, confidence=2.0).validate()
        with self.assertRaises(ValueError):
            ScoreHarmonySlice(score_id="", measure=1).validate()

    def test_round_trip(self):
        s = _slice(roman="ii7", base_roman="ii", chord_symbol="Dm7",
                   inferred_root="D", function_label="supertonic",
                   explanation="x", status="ok")
        d = s.to_dict()
        s2 = ScoreHarmonySlice.from_dict(d)
        self.assertEqual(s2.to_dict(), d)

    def test_canon_mode(self):
        self.assertEqual(canon_mode("major"), "major")
        self.assertEqual(canon_mode("minor"), "natural_minor")
        self.assertEqual(canon_mode("natural_minor"), "natural_minor")
        self.assertEqual(canon_mode("harmonic minor"), "natural_minor")


class TestAtlasBridge(unittest.TestCase):
    """The Phase-8 acceptance: first BWV 846 slice maps C major I to tonic/triad."""

    def setUp(self):
        self.atlas = build_atlas()

    def test_tonic_maps_to_atlas_triad_and_function(self):
        s = _slice(roman="I", base_roman="I", chord_symbol="C",
                   inferred_root="C", function_label="tonic")
        self.assertIn("triad:C:major:0", s.atlas_refs)
        self.assertIn("function:major:tonic", s.atlas_refs)
        self.assertIn("scale:C:major", s.atlas_refs)
        for ref in s.atlas_refs:
            self.assertIsNotNone(self.atlas.node(ref),
                                 "atlas ref must exist: %s" % ref)

    def test_dominant_maps_to_degree4(self):
        s = _slice(measure=3, roman="V6/5", base_roman="V", chord_symbol="G7",
                   inferred_root="G", function_label="dominant")
        self.assertIn("triad:C:major:4", s.atlas_refs)
        self.assertIn("function:major:dominant", s.atlas_refs)

    def test_chromatic_chord_never_claims_a_diatonic_triad(self):
        # C7 = V7/IV: its triad coincides with I, but base_roman is None so it
        # must NOT light the tonic triad node (honesty).
        s = _slice(measure=20, roman="V7/IV", base_roman=None, chord_symbol="C7",
                   inferred_root="C", function_label="dominant",
                   status="unsupported_chromatic")
        self.assertNotIn("triad:C:major:0", s.atlas_refs)
        self.assertEqual([r for r in s.atlas_refs if r.startswith("triad:")], [])
        self.assertIn("scale:C:major", s.atlas_refs)

    def test_secondary_dominant_quality_is_major_not_minor(self):
        # D7 (V/V) underlying triad is D MAJOR -> must not match diatonic ii (Dm).
        self.assertIsNone(
            diatonic_triad_match("C major", "major", "D", "major"))
        self.assertIsNotNone(
            diatonic_triad_match("C major", "major", "D", "minor"))

    def test_minor_uses_natural_minor_node_ids(self):
        s = ScoreHarmonySlice(score_id="t", measure=1, key="C minor",
                              mode="minor", roman="i", base_roman="i",
                              chord_symbol="Cm", inferred_root="C",
                              function_label="tonic")
        resolve_slice_refs(s)
        self.assertIn("scale:C:natural_minor", s.atlas_refs)
        self.assertIn("triad:C:natural_minor:0", s.atlas_refs)

    def test_atlas_sync_target_diatonic_vs_chromatic(self):
        diatonic = _slice(roman="V", base_roman="V", chord_symbol="G",
                          inferred_root="G", function_label="dominant")
        t = atlas_sync_target(diatonic)
        active = self.atlas.sync(t)["active"]
        self.assertEqual(active["triad"], "triad:C:major:4")
        self.assertEqual(active["function"], "function:major:dominant")

        chromatic = _slice(roman="V7/V", base_roman=None, chord_symbol="D7",
                           inferred_root="D", status="unsupported_chromatic")
        ta = self.atlas.sync(atlas_sync_target(chromatic))["active"]
        self.assertIsNone(ta["triad"])         # honest: no triad
        self.assertEqual(ta["scale"], "scale:C:major")


class TestNetworkBridge(unittest.TestCase):
    def test_dominant_lights_dom7_node(self):
        s = _slice(roman="V7", base_roman="V", chord_symbol="G7",
                   inferred_root="G")
        self.assertIn("hn:dom7:G", s.network_refs)
        self.assertIn("hn:major:C", s.network_refs)

    def test_secondary_dominant_lights_its_own_dom7(self):
        s = _slice(roman="V7/V", chord_symbol="D7", inferred_root="D",
                   status="unsupported_chromatic")
        self.assertIn("hn:dom7:D", s.network_refs)

    def test_leading_tone_dim_lights_dim_node(self):
        s = _slice(roman="vii07", base_roman="vii°", chord_symbol="Bdim7",
                   inferred_root="B", status="unsupported_chromatic")
        self.assertIn("hn:dim:B", s.network_refs)

    def test_plain_triad_lights_only_key_node(self):
        s = _slice(roman="I", base_roman="I", chord_symbol="C", inferred_root="C")
        self.assertEqual(s.network_refs, ["hn:major:C"])

    def test_network_target_shape(self):
        s = _slice(roman="ii7", base_roman="ii", chord_symbol="Dm7",
                   inferred_root="D")
        t = network_target_for(s)
        self.assertEqual(set(t), {"key", "mode", "roman", "root", "quality"})
        self.assertEqual(t["quality"], "minor")

    def test_every_network_ref_is_a_real_node(self):
        # closes the asymmetry with atlas_refs (which are existence-checked):
        # every produced network ref must resolve to a real Harmonic-Network node.
        from harmony.harmonic_network import build_network
        from harmony.network_template import get_template
        payload = build_network(get_template(
            "dominant_diminished_relative_network_v1")).to_payload()
        node_ids = {n["id"] for n in payload["nodes"]}
        cases = [
            dict(roman="I", base_roman="I", chord_symbol="C", inferred_root="C"),
            dict(roman="V7", base_roman="V", chord_symbol="G7", inferred_root="G"),
            dict(roman="V7/V", chord_symbol="D7", inferred_root="D",
                 status="unsupported_chromatic"),
            dict(roman="vii07", base_roman="vii°", chord_symbol="Bdim7",
                 inferred_root="B", status="unsupported_chromatic"),
        ]
        for kw in cases:
            s = _slice(**kw)
            self.assertTrue(s.network_refs, "expected refs for %s" % kw["roman"])
            for ref in s.network_refs:
                self.assertIn(ref, node_ids,
                              "network ref %s must be a real node" % ref)

    def test_natural_minor_VII_is_not_treated_as_dominant(self):
        # the VII-vs-vii° trap: a major subtonic VII (Bb in C minor) must NOT
        # snap to a dom7 node -- only the key node lights.
        s = ScoreHarmonySlice(score_id="t", measure=5, key="C minor",
                              mode="minor", roman="VII", chord_symbol="Bb",
                              inferred_root="Bb")
        resolve_slice_refs(s)
        self.assertEqual(s.network_refs, ["hn:minor:C"])


class TestResultAndContainers(unittest.TestCase):
    def _result(self):
        r = ScoreAnalysisResult(score_id="t", title="Test", key="C", mode="major")
        r.slices = [
            _slice(measure=1, roman="I", base_roman="I", chord_symbol="C",
                   inferred_root="C", function_label="tonic"),
            _slice(measure=2, roman="V", base_roman="V", chord_symbol="G",
                   inferred_root="G", function_label="dominant"),
        ]
        r.sections = [ScoreFormSection("A", 1, 2, "C major", "desc")]
        r.cadences = [ScoreCadenceSpan("t", 1, 2, ["V", "I"], "authentic")]
        return r

    def test_validate_and_serialise(self):
        import json
        r = self._result()
        r.validate()
        d = r.to_dict()
        self.assertEqual(d["schema"], SCORE_ANALYSIS_SCHEMA)
        json.dumps(d)  # serialisable
        r2 = ScoreAnalysisResult.from_dict(d)
        self.assertEqual(r2.measure_count, 2)
        self.assertEqual(len(r2.slices), 2)
        # cadences and sections survive the round trip with their fields intact
        self.assertEqual(len(r2.cadences), 1)
        self.assertEqual(len(r2.sections), 1)
        self.assertEqual(r2.cadences[0].pattern, ["V", "I"])
        self.assertEqual(r2.cadences[0].cadence_type, "authentic")
        self.assertEqual(r2.sections[0].label, "A")
        self.assertEqual(r2.sections[0].tonal_area, "C major")

    def test_cadence_and_section_round_trip(self):
        c = ScoreCadenceSpan("t", 33, 34, ["V", "I"], "authentic",
                             chord_symbols=["G7", "C"], romans=["V7", "I"],
                             functions=["dominant", "tonic"], confidence=0.9,
                             explanation="PAC")
        self.assertEqual(ScoreCadenceSpan.from_dict(c.to_dict()).to_dict(),
                         c.to_dict())
        sec = ScoreFormSection("Coda", 31, 34, "C major", "tonic pedal close")
        self.assertEqual(ScoreFormSection.from_dict(sec.to_dict()).to_dict(),
                         sec.to_dict())

    def test_duplicate_measure_rejected(self):
        r = self._result()
        r.slices.append(_slice(measure=1, roman="I", base_roman="I"))
        with self.assertRaises(ValueError):
            r.validate()

    def test_measure_transition_changes_slice(self):
        r = self._result()
        s1 = r.slice_for_measure(1)
        s2 = r.slice_for_measure(2)
        self.assertNotEqual(s1.roman, s2.roman)
        self.assertNotEqual(s1.network_refs, s2.network_refs)

    def test_section_lookup(self):
        r = self._result()
        self.assertEqual(r.section_for_measure(1).label, "A")
        self.assertIsNone(r.section_for_measure(99))

    def test_cadence_resolves_to_atlas_node(self):
        r = self._result()
        ref = r.cadences[0].atlas_cadence_ref("major")
        # roman-style label (one label style across cadence nodes, plan F7)
        self.assertEqual(ref, "cadence:V_I_major")
        self.assertIsNotNone(build_atlas().node(ref))


class TestReservedAtlasUnbroken(unittest.TestCase):
    """The legacy reserved Atlas ScoreAnalysis must STILL raise (not implemented)."""

    def test_reserved_still_raises(self):
        from harmony.atlas import ScoreAnalysis
        sa = ScoreAnalysis()
        for meth in ("analyze_score", "extract_harmony", "extract_functions",
                     "extract_cadences"):
            with self.assertRaises(NotImplementedError):
                getattr(sa, meth)("x")


if __name__ == "__main__":
    unittest.main()
