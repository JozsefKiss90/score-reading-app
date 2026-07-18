"""Content-truth regression tests (ticket 02: plan F2, F3-prose, F7).

Three learner-facing corrections, locked:

* F2 -- I-V-vi-IV is an *axis* progression (deceptive motion inside a loop),
  never labelled a deceptive cadence; the V-vi leaf stays the deceptive exemplar.
* F7 -- ONE cadence catalogue rendered as two variants (block / SATB voice
  leading) under the single Cadences category; cadence-type enums agree across
  layers (subtonic included); cadence node labels use one (roman) style.
* F3-prose -- the inversion lessons no longer claim unqualified tonic function
  for second inversion; the cadential 6/4 exception is named.

Run from the project root::

    .venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -t .
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harmony.harmonic_roles import CADENCE_TYPES  # noqa: E402
from harmony.atlas import build_atlas  # noqa: E402
from harmony.curriculum import (  # noqa: E402
    build_curriculum, _CADENCE_CATALOG, _CADENCE_TYPE_BLURB, _vl_specs_by_cadence,
)


def _catalog_types():
    return {tuple(tokens): ctype for tokens, _l, _m, ctype, _f in _CADENCE_CATALOG}


class TestAxisRetag(unittest.TestCase):
    """F2: the axis progression is not a deceptive cadence."""

    @classmethod
    def setUpClass(cls):
        cls.root = build_curriculum()
        cls.atlas = build_atlas()

    def test_catalogue_tags_axis_not_deceptive(self):
        types = _catalog_types()
        self.assertEqual(types[("I", "V", "vi", "IV")], "axis")
        # the two-chord V-vi leaf remains the deceptive exemplar
        self.assertEqual(types[("V", "vi")], "deceptive")

    def test_atlas_axis_node_not_deceptive(self):
        for n in self.atlas.nodes_of_kind("cadence"):
            if list(n.data.get("tokens", [])) == ["I", "V", "vi", "IV"]:
                self.assertEqual(n.data["cadenceType"], "axis", n.id)
                return
        self.fail("no I-V-vi-IV cadence node in the Atlas")

    def test_atlas_deceptive_exemplar_kept(self):
        types = [n for n in self.atlas.nodes_of_kind("cadence")
                 if n.data.get("cadenceType") == "deceptive"]
        self.assertEqual([list(n.data["tokens"]) for n in types], [["V", "vi"]])

    def test_curriculum_leaf_not_titled_deceptive(self):
        axis_leaves = []
        for lf in self.root.leaves():
            es = lf.lab_spec.to_exercise_specs()
            if es and tuple(es[0].pattern or ()) == ("I", "V", "vi", "IV"):
                axis_leaves.append(lf)
                # never LABELLED deceptive (title/keywords); prose may still
                # explain the V-vi deceptive *motion* inside the loop
                self.assertNotIn("deceptive", lf.title.lower(), lf.id)
                self.assertNotIn("deceptive", lf.keywords, lf.id)
        # both render variants exist; the block leaf's title carries the tag
        self.assertEqual(len(axis_leaves), 2)
        self.assertTrue(any("axis" in lf.title.lower() for lf in axis_leaves))

    def test_axis_blurb_explains_the_loop(self):
        # the blurb may (should) mention the deceptive V-vi motion *inside* the
        # loop -- what it must not do is present the loop as a cadence type.
        blurb = _CADENCE_TYPE_BLURB["axis"]
        self.assertIn("loop", blurb)
        self.assertNotIn("cadence type", blurb)


class TestCadenceTypeEnum(unittest.TestCase):
    """F7: one canonical cadence-type vocabulary, agreed across layers."""

    def test_canonical_set_includes_subtonic_and_axis(self):
        for t in ("authentic", "plagal", "half", "deceptive",
                  "subtonic", "aeolian", "axis"):
            self.assertIn(t, CADENCE_TYPES)

    def test_curriculum_catalogue_within_enum(self):
        used = set(_catalog_types().values())
        self.assertLessEqual(used, CADENCE_TYPES, used - CADENCE_TYPES)
        self.assertIn("subtonic", used)
        self.assertLessEqual(set(_CADENCE_TYPE_BLURB), CADENCE_TYPES)

    def test_atlas_cadence_nodes_within_enum(self):
        atlas = build_atlas()
        used = {n.data["cadenceType"] for n in atlas.nodes_of_kind("cadence")
                if n.data.get("cadenceType")}
        used.discard("other")   # heuristic fallback tag, not a taught type
        self.assertLessEqual(used, CADENCE_TYPES, used - CADENCE_TYPES)
        self.assertIn("subtonic", used)

    def test_network_catalogue_within_enum(self):
        from harmony.harmonic_network import CADENCE_CATALOGUE
        by_tokens = {}
        for romans, _label, ctype in (CADENCE_CATALOGUE["major"]
                                      + CADENCE_CATALOGUE["natural_minor"]):
            by_tokens[tuple(romans)] = ctype
            self.assertIn(ctype, CADENCE_TYPES, romans)
        # the modal subtonic close is tagged honestly here too
        self.assertEqual(by_tokens[("VII", "i")], "subtonic")

    def test_lab_demo_cadences_carry_enum_types(self):
        from harmony.lab import lab_demo_specs
        for s in lab_demo_specs():
            if s.concept in ("cadence", "voice_leading"):
                ctype = s.parameters.get("cadence_type", "")
                self.assertTrue(ctype, f"{s.experiment_id} has no cadence_type")
                self.assertIn(ctype, CADENCE_TYPES, s.experiment_id)

    def test_lab_spec_rejects_unknown_cadence_type(self):
        from harmony.lab_spec import LabExperimentSpec
        spec = LabExperimentSpec(
            experiment_id="bogus_type", title="x", concept="cadence",
            mode="major", key="C major", render="voice_leading",
            parameters={"pattern": ["V", "I"], "cadence_type": "sneaky"})
        with self.assertRaises(ValueError):
            spec.validate()

    def test_score_cadence_span_rejects_unknown_type(self):
        # "enums agree across curriculum and analysis spans" -- the analysis
        # span validates against the same canonical set, not just a comment.
        from harmony.score_analysis import ScoreCadenceSpan
        ScoreCadenceSpan("t", 1, 2, ["VII", "i"], "subtonic").validate()
        with self.assertRaises(ValueError):
            ScoreCadenceSpan("t", 1, 2, ["V", "I"], "sneaky").validate()


class TestOneCatalogueOneCategory(unittest.TestCase):
    """F7: the 13-entry catalogue lives once, as two render variants."""

    @classmethod
    def setUpClass(cls):
        cls.root = build_curriculum()
        cls.cadences = cls.root.find("cat:cadences")

    def test_voice_leading_category_is_gone(self):
        self.assertIsNone(self.root.find("cat:voice_leading"))

    def test_each_cadence_has_block_and_satb_variant(self):
        by_key = {}
        for lf in self.cadences.leaves():
            es = lf.lab_spec.to_exercise_specs()
            self.assertTrue(es, lf.id)
            by_key.setdefault((es[0].mode, tuple(es[0].pattern)), []).append(lf)
        self.assertEqual(len(by_key), 13)
        for key, leaves in sorted(by_key.items()):
            renders = sorted(lf.lab_spec.render for lf in leaves)
            self.assertEqual(renders, ["block", "voice_leading"], key)

    def test_variants_cross_link_each_other(self):
        by_key = {}
        for lf in self.cadences.leaves():
            es = lf.lab_spec.to_exercise_specs()
            by_key.setdefault((es[0].mode, tuple(es[0].pattern)), []).append(lf)
        for key, leaves in by_key.items():
            a, b = leaves
            self.assertIn(b.id, a.related, key)
            self.assertIn(a.id, b.related, key)

    def test_vl_concept_follows_catalogue_family_not_chord_count(self):
        vl = _vl_specs_by_cadence()
        for tokens, label, mode, _ctype, family in _CADENCE_CATALOG:
            spec = vl[(mode, tuple(tokens))]
            expected = "cadence" if family == "type" else "voice_leading"
            self.assertEqual(spec.concept, expected, label)

    def test_atlas_cadence_labels_use_one_roman_style(self):
        atlas = build_atlas()
        for n in atlas.nodes_of_kind("cadence"):
            self.assertIn("–", n.label,
                          f"{n.id} label {n.label!r} is not roman-chain style")


class TestCadential64Prose(unittest.TestCase):
    """F3-prose: second inversion is not presented as unqualified tonic function."""

    @classmethod
    def setUpClass(cls):
        cls.root = build_curriculum()

    def test_inversion_lesson_names_the_cadential_64_exception(self):
        lesson = self.root.find("lesson:chord_inversions")
        self.assertIn("cadential 6/4", lesson.theory)
        self.assertNotIn("function are unchanged", lesson.theory)

    def test_major_inversion_lesson_qualifies_the_claim(self):
        lesson = self.root.find("lesson:inversions_major")
        self.assertNotIn("function stay fixed", lesson.theory)

    def test_lab_explanation_misconception_is_qualified(self):
        from harmony.lab_explanations import get_concept_explanation
        exp = get_concept_explanation("inversion")
        text = " ".join(exp["common_misconceptions"]
                        + exp["atlas_connections"] + exp["next_steps"])
        self.assertIn("cadential 6/4", text)
        self.assertNotIn("it does not", text)
        self.assertNotIn("a later topic", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
