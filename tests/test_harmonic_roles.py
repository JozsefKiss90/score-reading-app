"""Tests for the harmonic-role profile model (plan section 11.1).

The crux of the whole correction: a chord's SPECIFIC scale-degree role (mediant, subdominant,
leading-tone diminished) is a separate field from its BROAD function family (tonic-related,
predominant, dominant).  These tests pin the major-mode pedagogical defaults (plan section 3.1),
the honest label->family mapping, and mode-aware natural-minor handling (plan section 2.4).
"""

import unittest

from theory.diatonic_harmony import generate_diatonic_triads
from harmony import harmonic_roles as hr


# Roman -> (specific_role, broad_family, membership_type) expected for C major (plan section 11.1).
_MAJOR_EXPECT = {
    0: ("tonic proper", "tonic_related", "primary"),
    1: ("predominant", "predominant", "primary"),
    2: ("mediant", "tonic_related", "related"),
    3: ("subdominant", "predominant", "preparatory"),
    4: ("dominant", "dominant", "primary"),
    5: ("submediant", "tonic_related", "substitute"),
    6: ("leading-tone diminished", "dominant", "leading_tone"),
}


class TestMajorRoleProfiles(unittest.TestCase):
    def test_major_degree_specific_role_and_family(self):
        romans = [t.roman for t in generate_diatonic_triads("C", "major")]
        for deg, (role, family, mtype) in _MAJOR_EXPECT.items():
            p = hr.role_profile("major", deg, roman=romans[deg])
            self.assertEqual(p.specific_role, role, f"deg {deg} specific_role")
            self.assertEqual(p.broad_family, family, f"deg {deg} broad_family")
            self.assertEqual(p.family_membership_type, mtype, f"deg {deg} membership_type")
            self.assertIn(p.broad_family, hr.BROAD_FUNCTION_FAMILIES)
            self.assertIn(p.family_membership_type, hr.FAMILY_MEMBERSHIP_TYPES)
            self.assertIn(p.family_membership_strength, hr.FAMILY_MEMBERSHIP_STRENGTH)

    def test_specific_role_and_broad_family_are_separate_fields(self):
        # iii: the mediant is tonic-RELATED, not the tonic proper. The two levels must not collapse.
        p = hr.role_profile("major", 2, roman="iii")
        self.assertEqual(p.specific_role, "mediant")
        self.assertEqual(p.broad_family, "tonic_related")
        self.assertNotEqual(p.specific_role, p.broad_family)
        # and it must never read simply "tonic"
        self.assertNotEqual(p.specific_role, "tonic")
        self.assertNotEqual(p.broad_family, "tonic")

    def test_mediant_is_contextual(self):
        p = hr.role_profile("major", 2, roman="iii")
        self.assertTrue(p.contextual)
        self.assertEqual(p.family_membership_strength, "context_dependent")
        self.assertIn("context", p.family_membership_explanation.lower())

    def test_iv_subdominant_not_overwritten_by_predominant(self):
        # IV: specific role stays "subdominant"; the family is "predominant" (plan section 2.2).
        p = hr.role_profile("major", 3, roman="IV")
        self.assertEqual(p.specific_role, "subdominant")
        self.assertEqual(p.broad_family, "predominant")
        self.assertIn("subdominant", p.family_membership_explanation.lower())

    def test_scale_degree_name_matches_theory_engine(self):
        for t in generate_diatonic_triads("C", "major"):
            p = hr.role_profile_for_triad(t)
            self.assertEqual(p.scale_degree_name, t.scale_degree_name)

    def test_broad_family_consistent_with_engine_function_label(self):
        for t in generate_diatonic_triads("C", "major"):
            p = hr.role_profile_for_triad(t)
            self.assertEqual(p.broad_family, hr.broad_function_family(t.function_label))

    def test_labels_present_and_distinct(self):
        p = hr.role_profile("major", 5, roman="vi")
        self.assertEqual(p.broad_family_label, "Tonic-related family")
        self.assertIn("substitute", p.specific_role_label.lower())


class TestBroadFunctionFamilyMapping(unittest.TestCase):
    def test_engine_labels_map_as_expected(self):
        self.assertEqual(hr.broad_function_family("tonic"), "tonic_related")
        self.assertEqual(hr.broad_function_family("mediant"), "tonic_related")
        self.assertEqual(hr.broad_function_family("predominant"), "predominant")
        self.assertEqual(hr.broad_function_family("subdominant"), "predominant")
        self.assertEqual(hr.broad_function_family("dominant"), "dominant")

    def test_fine_names_do_not_default_to_tonic(self):
        # The old BROAD_FUNCTION.get(..., "tonic") mis-bucketed these as tonic; the new mapping does
        # not (plan section Q4 caveat / honesty).
        self.assertEqual(hr.broad_function_family("supertonic"), "predominant")
        self.assertEqual(hr.broad_function_family("submediant"), "tonic_related")
        self.assertEqual(hr.broad_function_family("leading-tone"), "dominant")
        self.assertEqual(hr.broad_function_family("subtonic"), "dominant")

    def test_unknown_label_is_honest_contextual_not_tonic(self):
        self.assertEqual(hr.broad_function_family("N6"), "modal_or_contextual")
        self.assertEqual(hr.broad_function_family(""), "modal_or_contextual")

    def test_internal_family_to_broad(self):
        self.assertEqual(hr.internal_family_to_broad("tonic"), "tonic_related")
        self.assertEqual(hr.internal_family_to_broad("predominant"), "predominant")
        self.assertEqual(hr.internal_family_to_broad("dominant"), "dominant")


class TestMinorModeAwareness(unittest.TestCase):
    def test_minor_v_is_contextual_not_strong_dominant(self):
        # plan section 2.4: do not assert natural-minor v has major-V status.
        p = hr.role_profile("natural_minor", 4, roman="v")
        self.assertEqual(p.specific_role, "dominant")
        self.assertTrue(p.contextual)
        self.assertEqual(p.family_membership_strength, "context_dependent")

    def test_minor_VII_family_is_modal_or_contextual(self):
        # plan section 2.4: the modal subtonic VII is NOT a functional dominant of i.
        p = hr.role_profile("natural_minor", 6, roman="VII")
        self.assertEqual(p.specific_role, "subtonic")
        self.assertEqual(p.broad_family, "modal_or_contextual")
        self.assertTrue(p.contextual)

    def test_minor_tonic_is_primary(self):
        p = hr.role_profile("natural_minor", 0, roman="i")
        self.assertEqual(p.broad_family, "tonic_related")
        self.assertEqual(p.family_membership_type, "primary")
        self.assertFalse(p.contextual)

    def test_minor_scale_degree_names_from_engine(self):
        for t in generate_diatonic_triads("A", "natural_minor"):
            p = hr.role_profile_for_triad(t)
            self.assertEqual(p.scale_degree_name, t.scale_degree_name)


class TestSerialization(unittest.TestCase):
    def test_to_dict_camel_case_keeps_levels_separate(self):
        d = hr.role_profile("major", 2, roman="iii").to_dict()
        self.assertEqual(d["specificRole"], "mediant")
        self.assertEqual(d["broadFamily"], "tonic_related")
        self.assertEqual(d["broadFamilyLabel"], "Tonic-related family")
        self.assertIn("familyMembershipType", d)
        self.assertIn("familyMembershipExplanation", d)
        self.assertTrue(d["contextual"])
        # the two abstraction levels are distinct keys, never merged
        self.assertNotEqual(d["specificRole"], d["broadFamily"])


if __name__ == "__main__":
    unittest.main()
