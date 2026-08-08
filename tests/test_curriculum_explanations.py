"""Tests for the curriculum page generator (harmony.curriculum_explanations).

These run headless.  They enforce that the lesson / exercise pages are *derived*
(not hand-written per chord), complete, and cover every node:

  * every exercise leaf has a page whose harmonic analysis / preview matches its
    compiled chords;
  * the page's facts change when the spec changes (derivation, not hard-coding);
  * every lesson/category has a page with the required pedagogical fields;
  * the full payload assigns a page to every node and stays JSON-serialisable.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harmony.curriculum import get_curriculum  # noqa: E402
from harmony.exercise_spec import compile_exercise  # noqa: E402
from harmony.curriculum_explanations import (  # noqa: E402
    exercise_page, lesson_page, page_for, build_curriculum_payload,
)


def _find(root, pred):
    return next(n for n in root.walk() if pred(n))


class TestExercisePage(unittest.TestCase):
    def setUp(self):
        self.root = get_curriculum()

    def test_function_drill_page_derives_analysis(self):
        node = _find(self.root, lambda n: n.kind == "exercise"
                     and n.lab_spec.concept == "drill"
                     and (n.lab_spec.to_exercise_specs()[0].pattern == ["ii", "V", "I"]))
        page = exercise_page(node)
        self.assertEqual(page["kind"], "exercise")
        text = " ".join(page["harmonicAnalysis"])
        self.assertIn("ii = Dm", text)
        self.assertIn("V = G", text)
        self.assertIn("I = C", text)
        # voice-leading notes derived for a multi-chord drill
        self.assertTrue(page["voiceLeadingNotes"])
        # the trainer preview equals the compiled chords
        es = node.lab_spec.to_exercise_specs()[0]
        self.assertEqual(page["trainerPreview"]["count"],
                         len(compile_exercise(es).chords))

    def test_required_fields_present(self):
        node = _find(self.root, lambda n: n.kind == "exercise")
        page = exercise_page(node)
        for key in ("definition", "learningObjective", "musicTheory",
                    "harmonicAnalysis", "practiceAdvice", "voiceLeadingNotes",
                    "commonMistakes", "atlasMapping", "circleMapping",
                    "currentMapping", "trainerPreview", "launch"):
            self.assertIn(key, page, key)
        self.assertTrue(page["practiceAdvice"])
        self.assertTrue(page["launch"]["concept"])

    def test_motive_preview_has_degrees_not_chords(self):
        node = _find(self.root, lambda n: n.kind == "exercise"
                     and n.lab_spec.concept == "motive")
        page = exercise_page(node)
        self.assertEqual(page["trainerPreview"]["kind"], "motive")
        self.assertTrue(page["trainerPreview"]["degrees"])
        self.assertEqual(page["harmonicAnalysis"], [])   # no chord drill

    def test_technique_page_covered(self):
        # piano-technique ticket 01: the tracer leaf's page assembles with
        # theory + advice (a melodic phrase owns no chord analysis).
        node = _find(self.root, lambda n: n.kind == "exercise"
                     and n.lab_spec.concept == "technique")
        page = exercise_page(node)
        self.assertTrue(page["musicTheory"].strip())
        self.assertTrue(page["practiceAdvice"])
        self.assertTrue(page["commonMistakes"])
        self.assertEqual(page["harmonicAnalysis"], [])   # no chord drill
        self.assertIn("Coach:", page["definition"])      # the honesty line

    def test_facts_are_derived_not_hardcoded(self):
        # two full-key drills in different keys -> different analysis
        fullkeys = [n for n in self.root.walk() if n.kind == "exercise"
                    and n.lab_spec.concept == "drill"
                    and n.lab_spec.to_exercise_specs()[0].drill == "full_key"]
        c = next(n for n in fullkeys if "C major" in n.title)
        g = next(n for n in fullkeys if "G major" in n.title)
        self.assertNotEqual(exercise_page(c)["harmonicAnalysis"],
                            exercise_page(g)["harmonicAnalysis"])

    def test_atlas_mapping_parses_ids(self):
        node = _find(self.root, lambda n: n.kind == "exercise")
        for m in exercise_page(node)["atlasMapping"]:
            self.assertIn("kind", m)
            self.assertIn("label", m)


class TestLessonPage(unittest.TestCase):
    def setUp(self):
        self.root = get_curriculum()

    def test_lesson_page_fields(self):
        node = self.root.find("lesson:functions_major")
        page = lesson_page(node)
        for key in ("definition", "goal", "skillsAcquired", "commonMistakes",
                    "atlasLinks", "circleLinks", "recommendedOrder",
                    "relatedLessons", "estimatedPracticeTime", "audioObjective",
                    "visualObjective"):
            self.assertIn(key, page, key)
        self.assertTrue(page["skillsAcquired"])
        self.assertTrue(page["recommendedOrder"])
        self.assertGreater(page["estimatedPracticeTime"], 0)

    def test_category_page_aggregates_links(self):
        node = self.root.find("cat:scales")
        page = lesson_page(node)
        self.assertTrue(page["atlasLinks"])     # aggregated from descendants
        self.assertTrue(page["circleLinks"])

    def test_related_lessons_resolve_titles(self):
        node = self.root.find("lesson:voice_leading_cadences")
        page = lesson_page(node)
        for rel in page["relatedLessons"]:
            self.assertIn("title", rel)
            self.assertTrue(rel["title"])

    def test_page_for_dispatch(self):
        leaf = next(n for n in self.root.walk() if n.kind == "exercise")
        self.assertEqual(page_for(leaf)["kind"], "exercise")
        lesson = self.root.find("lesson:scales_major")
        self.assertEqual(page_for(lesson)["kind"], "lesson")


class TestFullPayload(unittest.TestCase):
    def test_payload_has_page_per_node(self):
        root = get_curriculum()
        payload = build_curriculum_payload()
        self.assertEqual(set(payload["pages"]), {n.id for n in root.walk()})

    def test_payload_json_serialisable(self):
        payload = build_curriculum_payload()
        s = json.dumps(payload)            # raises if anything is not serialisable
        self.assertGreater(len(s), 1000)

    def test_payload_deterministic(self):
        a = json.dumps(build_curriculum_payload(), sort_keys=True)
        b = json.dumps(build_curriculum_payload(), sort_keys=True)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main(verbosity=2)
