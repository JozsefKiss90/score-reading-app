"""Tests for the real-score importer (harmony/score_import.py) + the BWV 846/999
curated sidecars."""

import unittest

from harmony.score_import import (
    MeasureData,
    build_analysis,
    ensure_local_bwv846,
    extract_measures,
    load_analysis_from_sidecar,
    load_annotations,
    load_bwv846_analysis,
    load_bwv846_score,
    annotation_path,
)
from harmony.score_heuristic import infer_slice


class TestLoaderReadsBwv846(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_local_bwv846()
        cls.score = load_bwv846_score()
        cls.measures = extract_measures(cls.score)

    def test_measure_count_and_time(self):
        # music21's authentic corpus edition is 34 bars (no Schwencke bar).
        self.assertGreaterEqual(len(self.measures), 30)
        self.assertEqual(self.measures[0].number, 1)

    def test_first_measure_is_c_major_triad(self):
        m1 = self.measures[0]
        self.assertEqual(set(m1.pitch_class_names), {"C", "E", "G"})
        self.assertTrue(m1.bass.startswith("C"))

    def test_chromatic_bars_have_accidentals(self):
        by_num = {m.number: m for m in self.measures}
        # m6 carries the first F# (the V7/V); m1 is diatonic.
        self.assertIn("F#", by_num[6].accidentals)
        self.assertEqual(by_num[1].accidentals, [])


class TestSidecarsLoad(unittest.TestCase):
    def test_bwv846_sidecar_loads(self):
        ann = load_annotations(annotation_path("bwv846_prelude_c_major"))
        self.assertEqual(ann["score_id"], "bwv846_prelude_c_major")
        self.assertTrue(len(ann["slices"]) >= 8)

    def test_bwv999_sidecar_loads(self):
        ann = load_annotations(annotation_path("bwv999_prelude_c_minor"))
        self.assertEqual(ann["mode"], "minor")
        self.assertIn("readiness", ann)  # honest score-file-pending note


class TestBuildAnalysisBwv846(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = load_bwv846_analysis()

    def test_validates_and_covers_first_eight(self):
        self.result.validate()
        for m in range(1, 9):
            self.assertIsNotNone(self.result.slice_for_measure(m),
                                 "measure %d must be annotated" % m)

    def test_notes_filled_from_score(self):
        m1 = self.result.slice_for_measure(1)
        self.assertTrue(m1.notes, "slice should carry extracted note content")
        self.assertEqual(set(m1.chord_tones), {"C", "E", "G"})

    def test_first_slice_maps_to_atlas_tonic_triad(self):
        m1 = self.result.slice_for_measure(1)
        self.assertIn("triad:C:major:0", m1.atlas_refs)
        self.assertIn("function:major:tonic", m1.atlas_refs)
        self.assertIn("hn:major:C", m1.network_refs)

    def test_chromatic_measures_are_the_expected_nine(self):
        self.assertEqual(self.result.chromatic_measures(),
                         [6, 10, 12, 14, 20, 22, 23, 27, 31])

    def test_chromatic_slices_are_marked_honestly(self):
        for m in (6, 10, 12, 20, 22, 27, 31):
            s = self.result.slice_for_measure(m)
            self.assertEqual(s.status, "unsupported_chromatic")
            # no chromatic chord claims a diatonic triad node it shouldn't:
            if s.base_roman is None:
                self.assertEqual(
                    [r for r in s.atlas_refs if r.startswith("triad:")], [])

    def test_measure_transition_changes_network_target(self):
        a = self.result.slice_for_measure(1).network_target()
        b = self.result.slice_for_measure(3).network_target()
        self.assertNotEqual(a["roman"], b["roman"])

    def test_ambiguous_measure_marked_honestly(self):
        # m29 is a dominant 11-suspension (no third) -> ambiguous, NOT chromatic,
        # and it must not claim a diatonic triad node.
        m29 = self.result.slice_for_measure(29)
        self.assertEqual(m29.status, "ambiguous")
        self.assertNotIn(29, self.result.chromatic_measures())
        self.assertEqual(
            [r for r in m29.atlas_refs if r.startswith("triad:")], [])


class TestHeuristicBranches(unittest.TestCase):
    """The conservative heuristic's honesty branches (Phase 7 / AC7)."""

    def _md(self, number, pcs, bass):
        return MeasureData(number=number, pitch_class_names=list(pcs),
                           notes=list(pcs), bass=bass, quarter_length=4.0,
                           accidentals=[p for p in pcs
                                        if p not in {"C", "D", "E", "F", "G", "A", "B"}])

    def test_chromatic_measure_is_unsupported(self):
        from harmony.score_analysis import resolve_slice_refs
        s = infer_slice("t", self._md(6, ["C", "D", "F#", "A"], "C4"), "C", "major")
        self.assertEqual(s.status, "unsupported_chromatic")
        self.assertEqual(s.confidence, 0.0)
        self.assertTrue(s.explanation)
        self.assertIsNone(s.roman)
        resolve_slice_refs(s)
        self.assertEqual([r for r in s.atlas_refs if r.startswith("triad:")], [])

    def test_multiple_full_triads_is_ambiguous(self):
        # {C,D,F,A} fits both ii(D,F,A) and IV(F,A,C); bass C disambiguates neither
        s = infer_slice("t", self._md(2, ["C", "D", "F", "A"], "C4"), "C", "major")
        self.assertEqual(s.status, "ambiguous")
        self.assertIsNone(s.roman)

    def test_no_complete_triad_is_ambiguous(self):
        s = infer_slice("t", self._md(29, ["C", "D", "F", "G"], "G2"), "C", "major")
        self.assertEqual(s.status, "ambiguous")
        self.assertLess(s.confidence, 0.66)

    def test_empty_measure_is_ambiguous(self):
        s = infer_slice("t", self._md(99, [], None), "C", "major")
        self.assertEqual(s.status, "ambiguous")
        self.assertEqual(s.confidence, 0.0)

    def test_clear_diatonic_triad_with_bass_root_is_confident(self):
        s = infer_slice("t", self._md(13, ["D", "F", "A"], "D4"), "C", "major")
        self.assertEqual(s.status, "ok")
        self.assertEqual(s.roman, "ii")
        self.assertGreaterEqual(s.confidence, 0.66)


class TestBwv999HonestChromatic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # No score file bundled -> sidecar-only build (still valid).
        cls.result = load_analysis_from_sidecar("bwv999_prelude_c_minor")

    def test_validates_minor(self):
        self.result.validate()
        self.assertEqual(self.result.mode, "minor")

    def test_diatonic_minor_maps(self):
        i = self.result.slice_for_measure(1)
        self.assertIn("triad:C:natural_minor:0", i.atlas_refs)
        self.assertIn("hn:minor:C", i.network_refs)

    def test_unsupported_chromatic_events_marked(self):
        chrom = self.result.chromatic_measures()
        self.assertTrue(chrom, "BWV 999 must expose chromatic events")
        # the harmonic-minor dominant (m2) is honestly flagged
        m2 = self.result.slice_for_measure(2)
        self.assertEqual(m2.status, "unsupported_chromatic")
        self.assertTrue(m2.explanation)
        # and it does not fake a diatonic triad node
        self.assertEqual([r for r in m2.atlas_refs if r.startswith("triad:")], [])


class TestHeuristicNeverOverwritesCurated(unittest.TestCase):
    def test_heuristic_only_fills_unannotated(self):
        ann = load_annotations(annotation_path("bwv846_prelude_c_major"))
        # drop the curated slice for measure 5 so the heuristic must fill it
        ann["slices"] = [s for s in ann["slices"] if s["measure"] != 5]
        ensure_local_bwv846()
        measures = extract_measures(load_bwv846_score())
        result = build_analysis(ann, measures, heuristic=True)
        m5 = result.slice_for_measure(5)
        self.assertIsNotNone(m5)
        self.assertEqual(m5.source, "heuristic")
        # a still-curated measure keeps source manual
        self.assertEqual(result.slice_for_measure(1).source, "manual")


if __name__ == "__main__":
    unittest.main()
