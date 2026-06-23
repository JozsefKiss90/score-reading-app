"""Regression tests for the curriculum coverage audit (Bug 4).

The audit (`harmony.curriculum_audit`) must report a *clean* curriculum: every
required cadence + inversion present, no duplicate ids, no broken Atlas / Circle
mappings, no empty explanations. This is the machine-checkable form of
acceptance criterion 6 ("the audit reports no missing required lesson").

Run from the project root::

    .venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -t .
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harmony.curriculum_audit import build_audit, render_markdown  # noqa: E402


class TestCurriculumAudit(unittest.TestCase):
    def setUp(self):
        self.audit = build_audit()

    def test_audit_is_clean(self):
        s = self.audit["summary"]
        self.assertEqual(s["missingRequiredCount"], 0, self.audit["required"])
        self.assertEqual(s["duplicateLeafIds"], [])
        self.assertEqual(s["duplicateExperimentIds"], [])
        self.assertEqual(s["incompleteCategories"], [])
        self.assertTrue(s["clean"])

    def test_required_cadences_and_inversions_fully_present(self):
        rc = self.audit["required"]["cadences"]
        self.assertEqual(rc["present"], rc["expected"])
        self.assertEqual(rc["expected"], 13)
        self.assertEqual(rc["twoChordTypes"], 6)
        self.assertEqual(rc["progressions"], 7)
        self.assertEqual(rc["missing"], [])
        ri = self.audit["required"]["inversions"]
        self.assertEqual(ri["present"], ri["expected"])
        self.assertEqual(ri["expected"], 96)
        self.assertEqual(ri["missing"], [])

    def test_no_category_has_unresolved_or_invalid_entries(self):
        for c in self.audit["categories"]:
            self.assertEqual(c["invalidLabSpec"], [], c["key"])
            self.assertEqual(c["invalidBridge"], [], c["key"])
            self.assertEqual(c["unresolvedAtlasMapping"], [], c["key"])
            self.assertEqual(c["unresolvedCircleMapping"], [], c["key"])
            self.assertEqual(c["duplicateExerciseIds"], [], c["key"])
            self.assertEqual(c["duplicateExperimentIds"], [], c["key"])
            # non-reserved categories must carry explanations + mappings.
            if not c["reserved"] and c["actualLeaves"]:
                self.assertEqual(c["emptyExplanations"], [], c["key"])
                self.assertEqual(c["missingAtlasMapping"], [], c["key"])
                self.assertEqual(c["missingCircleMapping"], [], c["key"])

    def test_audit_is_json_serialisable_and_renders(self):
        text = json.dumps(self.audit)            # raises if not serialisable
        self.assertGreater(len(text), 0)
        md = render_markdown(self.audit)
        self.assertIn("coverage audit", md.lower())
        self.assertIn("Cadences", md)
        self.assertIn("Inversions", md)


if __name__ == "__main__":
    unittest.main(verbosity=2)
