"""Drift tests: one function vocabulary (ticket 01, plan F1 / section 9.5).

`harmony.harmonic_roles` is the single source of function vocabulary.  Every
surface that renders a function name -- the harmonic network's collapse map, the
functional network's group map and labels, the circle payload's colour classes
and legend, the trainer's functional drill tokens, and the curriculum's prose
and search words -- must *derive* from it.  These tests fail if any derived
vocabulary is re-hardcoded and drifts from the source.

The INTERNAL 3-family key ("tonic"/"predominant"/"dominant" -- node ids, layout
bands, CSS colour classes) is deliberately distinct from the presentation
family labels ("Tonic-related family" etc.); the tests below assert both levels
and never conflate them.

Run from the project root::

    .venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -t .
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import harmony.harmonic_roles as hr  # noqa: E402
from theory.diatonic_harmony import (  # noqa: E402
    generate_diatonic_triads,
    _FUNCTION_LABELS_MAJOR,
    _FUNCTION_LABELS_MINOR,
)


class TestSourceVocabulary(unittest.TestCase):
    """The source itself: complete over the engine's labels, internally consistent."""

    def test_engine_labels_cover_the_theory_tables(self):
        self.assertEqual(
            hr.ENGINE_FUNCTION_LABELS,
            frozenset(_FUNCTION_LABELS_MAJOR) | frozenset(_FUNCTION_LABELS_MINOR))

    def test_collapse_map_covers_every_engine_label(self):
        self.assertEqual(set(hr.ENGINE_FUNCTION_TO_INTERNAL_FAMILY),
                         set(hr.ENGINE_FUNCTION_LABELS))

    def test_collapse_map_agrees_with_broad_function_family(self):
        # label -> internal family -> presentation family must equal the
        # direct label -> presentation family mapping (one vocabulary, two levels).
        for label, fam in hr.ENGINE_FUNCTION_TO_INTERNAL_FAMILY.items():
            self.assertEqual(hr.INTERNAL_FAMILY_TO_BROAD[fam],
                             hr.broad_function_family(label), label)

    def test_internal_and_presentation_families_stay_distinct(self):
        # The internal key is baked into node ids and must NOT be renamed; the
        # presentation label is a different string by design.
        self.assertEqual(hr.internal_family_to_broad("tonic"), "tonic_related")
        self.assertNotEqual(hr.internal_family_label("tonic"), "tonic")
        self.assertEqual(hr.internal_family_label("tonic"),
                         hr.BROAD_FAMILY_LABELS["tonic_related"])

    def test_function_token_exemplars_bear_their_names(self):
        # Each shorthand token family names the degree it resolves to: the
        # exemplar degree's specific role must carry the function name.
        for name, deg in hr.FUNCTION_EXEMPLAR_DEGREE.items():
            profile = hr.role_profile("major", deg)
            self.assertIn(name, profile.specific_role, (name, deg))

    def test_short_badges_defined_for_all_internal_families(self):
        self.assertEqual(set(hr.INTERNAL_FAMILY_SHORT),
                         set(hr.INTERNAL_FAMILY_TO_BROAD))


class TestDerivedMaps(unittest.TestCase):
    """The parallel maps named by plan section 9.5 are derived, not maintained."""

    def test_harmonic_network_broad_function_is_derived(self):
        from harmony.harmonic_network import BROAD_FUNCTION
        self.assertEqual(BROAD_FUNCTION, dict(hr.ENGINE_FUNCTION_TO_INTERNAL_FAMILY))

    def test_functional_network_group_map_is_derived(self):
        from harmony.functional_network import ENGINE_FUNCTION_TO_GROUP
        self.assertEqual(ENGINE_FUNCTION_TO_GROUP,
                         dict(hr.ENGINE_FUNCTION_TO_INTERNAL_FAMILY))

    def test_functional_network_labels_are_presentation_labels(self):
        from harmony.functional_network_template import (
            FUNCTION_GROUPS, FUNCTION_GROUP_LABELS, FUNCTION_GROUP_SHORT)
        for g in FUNCTION_GROUPS:
            self.assertEqual(FUNCTION_GROUP_LABELS[g], hr.internal_family_label(g))
            self.assertEqual(FUNCTION_GROUP_SHORT[g], hr.INTERNAL_FAMILY_SHORT[g])

    def test_circle_function_classes_are_derived(self):
        from harmony.circle_payload import (
            _FUNCTION_CLASS, _FUNCTION_CLASS_LABELS, _FAMILY_CLASS)
        # colour-class grouping mirrors the source collapse map exactly
        self.assertEqual(set(_FUNCTION_CLASS), set(hr.ENGINE_FUNCTION_TO_INTERNAL_FAMILY))
        for label, fam in hr.ENGINE_FUNCTION_TO_INTERNAL_FAMILY.items():
            self.assertEqual(_FUNCTION_CLASS[label], _FAMILY_CLASS[fam], label)
        # legend entries carry the shared presentation label + short badge
        by_class = {e["class"]: e for e in _FUNCTION_CLASS_LABELS}
        for fam, cls in _FAMILY_CLASS.items():
            self.assertEqual(by_class[cls]["label"], hr.internal_family_label(fam))
            self.assertEqual(by_class[cls]["short"], hr.INTERNAL_FAMILY_SHORT[fam])

    def test_trainer_function_tokens_are_derived(self):
        from harmony.exercise_spec import _FUNCTION_TOKEN_TO_ROMAN, _MAJOR_DEGREE_LABELS
        expected = {
            alias: _MAJOR_DEGREE_LABELS[hr.FUNCTION_EXEMPLAR_DEGREE[name]]
            for name, aliases in hr.FUNCTION_TOKEN_ALIASES.items()
            for alias in aliases
        }
        self.assertEqual(_FUNCTION_TOKEN_TO_ROMAN, expected)

    def test_curriculum_function_words_are_derived(self):
        from harmony.curriculum import _FUNCTION_WORDS
        expected = {}
        for tonic, mode in (("C", "major"), ("A", "natural_minor")):
            for t in generate_diatonic_triads(tonic, mode):
                expected[t.roman] = hr.ENGINE_FUNCTION_TO_INTERNAL_FAMILY[t.function_label]
        self.assertEqual(_FUNCTION_WORDS, expected)


class TestRenderedProse(unittest.TestCase):
    """Curriculum prose renders the shared vocabulary, not hand-kept synonyms."""

    @classmethod
    def setUpClass(cls):
        from harmony.curriculum import build_curriculum
        cls.root = build_curriculum()

    def test_functions_category_prose_is_generated(self):
        from harmony.curriculum import function_families_prose
        cat = self.root.find("cat:functions")
        self.assertEqual(cat.theory, function_families_prose("major"))

    def test_functions_prose_places_each_degree_in_its_source_family(self):
        cat = self.root.find("cat:functions")
        # the two-level story: family labels present, iii marked contextual,
        # and the old flat "tonic (rest, I/vi/iii)" claim gone.
        for needed in ("Tonic-related family", "Predominant family",
                       "Dominant family", "iii"):
            self.assertIn(needed, cat.theory, needed)
        self.assertNotIn("I/vi/iii", cat.theory)

    def test_function_lessons_share_the_generated_prose(self):
        from harmony.curriculum import function_families_prose
        for lid, mode in (("lesson:functions_major", "major"),
                          ("lesson:functions_minor", "natural_minor")):
            node = self.root.find(lid)
            self.assertEqual(node.theory, function_families_prose(mode), lid)

    def test_drill_theory_function_entry_uses_source_labels(self):
        from harmony.curriculum_explanations import _DRILL_THEORY
        text = _DRILL_THEORY["function"]
        for needed in (hr.internal_family_label("tonic"),
                       hr.internal_family_label("predominant"),
                       hr.internal_family_label("dominant")):
            self.assertIn(needed, text)

    def test_functional_network_group_prose_uses_source_labels(self):
        from harmony.functional_network import _GROUP_PROSE
        for fam, prose in _GROUP_PROSE.items():
            self.assertIn(hr.internal_family_label(fam), prose, fam)

    def test_journey_and_template_prose_use_source_labels(self):
        from harmony.functional_network_template import functional_degree_network_v1
        tpl = functional_degree_network_v1()
        fn_class = tpl.node_class("function_group")
        for fam in ("tonic", "predominant", "dominant"):
            self.assertIn(hr.internal_family_label(fam), fn_class.description)
        # the journey's "Three jobs" stage names the same three families
        from harmony.functional_network import build_functional_network
        from harmony.functional_journey import journey_stages
        stage = next(s for s in journey_stages(build_functional_network())
                     if s.stage_id == "three_jobs")
        for fam in ("tonic", "predominant", "dominant"):
            self.assertIn(hr.internal_family_label(fam), stage.explanation)


class TestJsMirrors(unittest.TestCase):
    """JS legend surfaces render from the payload, not their own synonym tables."""

    def _js(self, name):
        path = os.path.join(PROJECT_ROOT, "beat_selector", name)
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()

    def test_circle_js_has_no_hardcoded_function_legend(self):
        src = self._js("harmony_circle.js")
        self.assertNotIn('[["T", "Tonic"]', src)
        self.assertNotIn('"Pre/Sub"', src)
        # the legend + label lookups must come from the payload cheatsheet
        self.assertIn("functionClasses", src)

    def test_circle_js_has_no_hardcoded_collapse_map(self):
        src = self._js("harmony_circle.js")
        # the old funcLetterFor table spelled out the engine labels
        self.assertNotIn('mediant: "T"', src.replace("'", '"'))

    def test_circle_js_string_literals_carry_no_family_synonyms(self):
        # stronger than checking for the old literals: NO string literal in the
        # file may spell a capitalised family/role word -- display text must
        # come from the payload (lowercase CSS words like "dominant-baseline"
        # are styling, not vocabulary, and stay allowed).
        import re
        src = self._js("harmony_circle.js")
        literals = re.findall(r'"[^"\n]*"|\'[^\'\n]*\'', src)
        offenders = [s for s in literals if re.search(
            r"Tonic|Predominant|Subdominant|Dominant|Mediant|Submediant", s)]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
