"""Phase 9 tests for the score-analysis projection adapter (harmony/network_projection.py).

Adapts a curated ScoreHarmonySlice stream to the DrillGraphProjection contract, reusing the
score_analysis mapping helpers. Preserves curated/heuristic status; never invents harmonic
certainty; the honesty gate is base_roman (a chromatic chord whose triad merely coincides with a
diatonic one must NOT claim it). Does not destabilise the Score Soul Graph.
"""

import unittest

from harmony.harmonic_network import build_network
from harmony.network_template import get_template
from harmony.network_projection import (
    project_score_analysis,
    harmonic_step_from_score_slice,
)
from harmony.score_analysis import ScoreHarmonySlice, ScoreAnalysisResult


def _slice(**kw):
    kw.setdefault("score_id", "demo")
    return ScoreHarmonySlice(**kw)


def _result(slices, **kw):
    kw.setdefault("score_id", "demo")
    kw.setdefault("key", "C major")
    kw.setdefault("mode", "major")
    return ScoreAnalysisResult(slices=slices, **kw)


def _core():
    return build_network(get_template("core_triad_function_network_v1"))


def _legacy():
    return build_network(get_template())


class TestScoreProjectionCore(unittest.TestCase):
    def setUp(self):
        self.res = _result([
            _slice(measure=1, key="C major", mode="major", base_roman="I", roman="I",
                   inferred_root="C", chord_symbol="C", function_label="tonic"),
            _slice(measure=2, key="C major", mode="major", base_roman="ii", roman="ii",
                   inferred_root="D", chord_symbol="Dm", function_label="predominant"),
            _slice(measure=3, key="C major", mode="major", base_roman="V", roman="V",
                   inferred_root="G", chord_symbol="G", function_label="dominant"),
        ])
        self.proj = project_score_analysis(self.res, _core())

    def test_diatonic_slices_map_exact(self):
        self.proj.validate()
        self.assertEqual(len(self.proj.steps), 3)
        self.assertTrue(all(s.mapping_status == "exact" for s in self.proj.steps))
        self.assertEqual(self.proj.step_at_index(1).visual_node_id, "hn:triad:C:major:1")

    def test_score_time_semantics_no_inferred_theory(self):
        self.assertEqual(self.proj.drill_family, "score")
        self.assertEqual(self.proj.sequence_semantics, "score_time")
        # curated status preserved: no automatic harmonic-motion edges between slices
        self.assertEqual(self.proj.counts()["theoryEdges"], 0)
        self.assertTrue(all(t.sequence_relation == "drill_next" for t in self.proj.transitions))

    def test_source_is_score(self):
        self.assertTrue(all(s.source_kind == "score" for s in self.proj.steps))


class TestScoreHonesty(unittest.TestCase):
    def test_chromatic_slice_is_unsupported(self):
        # a secondary dominant (V7/V = D7) has no diatonic reading -> unsupported, not a false node
        res = _result([
            _slice(measure=1, key="C major", mode="major", base_roman="V", roman="V",
                   inferred_root="G", chord_symbol="G"),
            _slice(measure=2, key="C major", mode="major", base_roman=None, roman="V7/V",
                   inferred_root="D", chord_symbol="D7", status="unsupported_chromatic"),
        ])
        proj = project_score_analysis(res, _core())
        proj.validate()
        chrom = proj.step_at_index(1)
        self.assertEqual(chrom.mapping_status, "unsupported")
        self.assertTrue(chrom.visual_node_id.startswith("overlay:score:"))
        self.assertIsNone(chrom.primary_network_node)

    def test_coinciding_chromatic_does_not_claim_diatonic_node(self):
        # THE honesty case: C7 = V7/IV in C major. Its TRIAD is C major = I, but base_roman is
        # None (it is not a diatonic reading), so it must NOT map to the tonic node.
        res = _result([
            _slice(measure=1, key="C major", mode="major", base_roman=None, roman="V7/IV",
                   inferred_root="C", chord_symbol="C7", status="unsupported_chromatic"),
        ])
        proj = project_score_analysis(res, _core())
        proj.validate()
        step = proj.step_at_index(0)
        self.assertEqual(step.mapping_status, "unsupported")
        self.assertNotEqual(step.visual_node_id, "hn:triad:C:major:0")
        self.assertIsNone(step.primary_network_node)

    def test_unparseable_slice_key_degrades_not_crashes(self):
        # review finding: a bad key (German 'H') on ONE slice must degrade to unsupported,
        # never abort the whole projection.
        res = _result([
            _slice(measure=1, key="C major", mode="major", base_roman="I", inferred_root="C",
                   chord_symbol="C"),
            _slice(measure=2, key="H major", mode="major", base_roman="I", inferred_root="C",
                   chord_symbol="C", status="ok"),
        ])
        proj = project_score_analysis(res, _core())    # must not raise
        proj.validate()
        self.assertEqual(len(proj.steps), 2)
        self.assertEqual(proj.step_at_index(1).mapping_status, "unsupported")
        self.assertTrue(proj.step_at_index(1).visual_node_id)

    def test_every_slice_is_visible(self):
        res = _result([
            _slice(measure=1, key="C major", mode="major", base_roman="I", inferred_root="C",
                   chord_symbol="C"),
            _slice(measure=2, key="C major", mode="major", base_roman=None,
                   chord_symbol="Ger+6", status="unsupported_chromatic"),
        ])
        proj = project_score_analysis(res, _legacy())
        proj.validate()
        self.assertTrue(all(s.visual_node_id for s in proj.steps))
        self.assertEqual(proj.counts()["byMappingStatus"].get("unsupported"), 1)


class TestScoreKeyChanges(unittest.TestCase):
    def test_key_change_is_a_group_boundary_no_theory(self):
        res = _result([
            _slice(measure=1, key="C major", mode="major", base_roman="I", inferred_root="C",
                   chord_symbol="C"),
            _slice(measure=2, key="C major", mode="major", base_roman="V", inferred_root="G",
                   chord_symbol="G"),
            _slice(measure=3, key="G major", mode="major", base_roman="I", inferred_root="G",
                   chord_symbol="G"),
        ])
        proj = project_score_analysis(res, _core())
        proj.validate()
        self.assertEqual(proj.counts()["groups"], 2)
        boundaries = [t for t in proj.transitions if t.is_group_boundary]
        self.assertEqual(len(boundaries), 1)
        # never an asserted theory edge across the key change
        self.assertTrue(all(t.theory_relation is None for t in proj.transitions))


class TestScoreLegacyProxies(unittest.TestCase):
    def test_diatonic_slices_proxy_on_legacy(self):
        res = _result([
            _slice(measure=1, key="C major", mode="major", base_roman="I", inferred_root="C",
                   chord_symbol="C"),
            _slice(measure=2, key="C major", mode="major", base_roman="vii°", inferred_root="B",
                   chord_symbol="B°", function_label="dominant"),
        ])
        proj = project_score_analysis(res, _legacy())
        proj.validate()
        by_roman = {s.roman: s for s in proj.steps}
        self.assertEqual(by_roman["I"].mapping_status, "contextual")   # no exact triad in legacy
        self.assertEqual(by_roman["vii°"].mapping_status, "exact")     # exact dim node reused
        self.assertEqual(by_roman["vii°"].visual_node_id, "hn:dim:B")


class TestStepAdapter(unittest.TestCase):
    def test_step_and_proxy_returned(self):
        net = _core()
        sl = _slice(measure=1, key="C major", mode="major", base_roman="I", inferred_root="C",
                    chord_symbol="C")
        sl.atlas_refs = ["scale:C:major", "triad:C:major:0"]  # curated refs preserved
        step, proxy = harmonic_step_from_score_slice(
            sl, net, sequence_index=0, group_index=0, index_in_group=0)
        self.assertEqual(step.mapping_status, "exact")
        self.assertIsNone(proxy)                                # exact -> no proxy
        self.assertIn("triad:C:major:0", step.atlas_refs)       # slice atlas_refs reused

    def test_atlas_refs_reused_from_slice(self):
        net = _core()
        res = _result([_slice(measure=1, key="C major", mode="major", base_roman="V",
                              inferred_root="G", chord_symbol="G")])
        proj = project_score_analysis(res, net)
        self.assertTrue(any("triad:" in r for r in proj.steps[0].atlas_refs))


class TestDoesNotDestabiliseScoreAnalysis(unittest.TestCase):
    def test_curated_refs_not_clobbered(self):
        # resolve_refs is idempotent: a slice with curated refs keeps them
        sl = _slice(measure=1, key="C major", mode="major", base_roman="I", inferred_root="C",
                    chord_symbol="C", atlas_refs=["curated:ref"])
        res = _result([sl])
        project_score_analysis(res, _core())
        self.assertEqual(sl.atlas_refs, ["curated:ref"])

    def test_result_still_validates_after_projection(self):
        res = _result([_slice(measure=1, key="C major", mode="major", base_roman="I",
                              inferred_root="C", chord_symbol="C")])
        project_score_analysis(res, _core())
        res.validate()  # the score contract is untouched


if __name__ == "__main__":
    unittest.main()
