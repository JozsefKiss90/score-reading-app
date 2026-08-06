"""Regression tests for the expanded cadence curriculum (Bug 2).

Locks the corrective-maintenance contract: the Cadences category covers every
required cadence both as two-chord *types* and as longer functional
*progressions*, in separate groups, each with a resolvable Atlas mapping, a
voice-leading counterpart, and a valid Trainer bridge -- with no duplicate ids.

Run from the project root::

    .venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -t .
"""

import os
import sys
import unittest
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harmony.exercise_spec import compile_exercise, MAX_CHORDS_PER_SPEC  # noqa: E402
from harmony.atlas import build_atlas  # noqa: E402
from harmony.curriculum import build_curriculum  # noqa: E402


#: The cadence coverage this maintenance pass mandates (Bug 2), by (tokens, mode).
_REQUIRED_TYPES = [
    (("V", "I"), "major"), (("IV", "I"), "major"),
    (("I", "V"), "major"), (("V", "vi"), "major"),
    (("v", "i"), "natural_minor"), (("VII", "i"), "natural_minor"),
]
_REQUIRED_PROGRESSIONS = [
    (("I", "IV", "V", "I"), "major"), (("ii", "V", "I"), "major"),
    (("vi", "ii", "V", "I"), "major"), (("I", "V", "vi", "IV"), "major"),
    (("iv", "v", "i"), "natural_minor"), (("i", "iv", "v", "i"), "natural_minor"),
    (("i", "VI", "VII", "i"), "natural_minor"),
]


class TestCadenceCurriculum(unittest.TestCase):
    #: The six catalogue groups.  Since ticket 16 the Cadences category also
    #: holds taxonomy lessons (PAC vs IAC, the half-cadence family, the
    #: cadential 6/4, the ear reflex, orbits) that deliberately share patterns
    #: and bridge skeletons; this file locks the CATALOGUE contract, so leaves
    #: are collected from the catalogue groups only (the taxonomy leaves are
    #: covered by tests.test_cadence_taxonomy).
    _BLOCK_GROUPS = ("group:cadence_types_major", "group:cadence_types_minor",
                     "group:cadence_prog_major", "group:cadence_prog_minor")
    _VL_GROUPS = ("group:voice_leading_major", "group:voice_leading_minor")

    def setUp(self):
        self.root = build_curriculum()
        self.atlas = build_atlas()
        self.cadences = self.root.find("cat:cadences")
        self.assertIsNotNone(self.cadences)
        # The category holds both render variants of each cadence (F7); the
        # block drills live outside the SATB voice-leading lesson.
        self.block_leaves = [lf for g in self._BLOCK_GROUPS
                             for lf in self.root.find(g).leaves()]
        self.vl_leaves = [lf for g in self._VL_GROUPS
                          for lf in self.root.find(g).leaves()]
        self.catalogue_leaves = self.block_leaves + self.vl_leaves
        # (mode, tokens) -> block leaf, from each cadence leaf's bridge pattern.
        self.by_cadence = {}
        for lf in self.block_leaves:
            es = lf.lab_spec.to_exercise_specs()
            self.assertEqual(len(es), 1, lf.id)
            self.by_cadence[(es[0].mode, tuple(es[0].pattern))] = lf

    def test_contains_all_required_cadence_patterns(self):
        for tokens, mode in _REQUIRED_TYPES + _REQUIRED_PROGRESSIONS:
            self.assertIn((mode, tokens), self.by_cadence,
                          f"missing cadence {tokens} ({mode})")

    def test_two_chord_and_progression_are_separate_groups(self):
        types = self.root.find("lesson:cadence_types")
        progs = self.root.find("lesson:cadence_progressions")
        self.assertIsNotNone(types)
        self.assertIsNotNone(progs)
        # Two-chord lesson holds only 2-chord cadences.
        for lf in types.leaves():
            self.assertEqual(len(lf.lab_spec.to_exercise_specs()[0].pattern), 2, lf.id)
        # Progression lesson holds only longer (>=3 chord) cadences.
        for lf in progs.leaves():
            self.assertGreaterEqual(
                len(lf.lab_spec.to_exercise_specs()[0].pattern), 3, lf.id)
        # The required split lands in the right lesson.
        type_keys = {(es[0].mode, tuple(es[0].pattern)) for es in
                     (lf.lab_spec.to_exercise_specs() for lf in types.leaves())}
        for tokens, mode in _REQUIRED_TYPES:
            self.assertIn((mode, tokens), type_keys)
        prog_keys = {(es[0].mode, tuple(es[0].pattern)) for es in
                     (lf.lab_spec.to_exercise_specs() for lf in progs.leaves())}
        for tokens, mode in _REQUIRED_PROGRESSIONS:
            self.assertIn((mode, tokens), prog_keys)

    def test_no_duplicate_ids(self):
        # Leaf and experiment ids are unique across the WHOLE category …
        leaf_ids = [lf.id for lf in self.cadences.leaves()]
        self.assertEqual(len(leaf_ids), len(set(leaf_ids)))
        exp_ids = [lf.lab_spec.experiment_id for lf in self.cadences.leaves()]
        self.assertEqual(len(exp_ids), len(set(exp_ids)))
        # … while bridge-skeleton uniqueness is a catalogue contract: the
        # taxonomy leaves share skeletons on purpose (three PAC/IAC voicings
        # of one V–I; the 6/4 relabel drill is the same sounds relabelled).
        bridge_ids = [lf.lab_spec.to_exercise_specs()[0].exercise_id
                      for lf in self.catalogue_leaves]
        self.assertEqual([i for i, c in Counter(bridge_ids).items() if c > 1], [])

    def test_every_cadence_has_resolvable_atlas_mapping(self):
        for lf in self.catalogue_leaves:
            cad_refs = [n for n in lf.atlas_nodes if n.startswith("cadence:")]
            self.assertTrue(cad_refs, f"{lf.id} has no cadence atlas mapping")
            for nid in cad_refs:
                self.assertIsNotNone(self.atlas.node(nid), (lf.id, nid))

    def test_every_cadence_compiles_to_valid_trainer_output(self):
        for (mode, tokens), lf in self.by_cadence.items():
            es = lf.lab_spec.to_exercise_specs()[0]
            es.validate()
            compiled = compile_exercise(es)
            self.assertEqual(len(compiled), len(tokens), lf.id)
            self.assertLessEqual(len(compiled), MAX_CHORDS_PER_SPEC, lf.id)

    def test_each_cadence_links_to_a_voice_leading_counterpart(self):
        # F7: both variants live under Cadences; each block leaf must link to
        # an SATB leaf of the same pattern (and vice versa).
        vl_ids = {lf.id for lf in self.vl_leaves}
        block_ids = {lf.id for lf in self.block_leaves}
        for lf in self.block_leaves:
            related_vl = [r for r in lf.related if r in vl_ids]
            self.assertTrue(related_vl, f"{lf.id} has no voice-leading link")
        for lf in self.vl_leaves:
            related_block = [r for r in lf.related if r in block_ids]
            self.assertTrue(related_block, f"{lf.id} has no block-cadence link")

    def test_voice_leading_covers_every_cadence(self):
        # One SATB voice-leading variant per block cadence (13), same category.
        vl_keys = set()
        for lf in self.vl_leaves:
            self.assertEqual(lf.lab_spec.render, "voice_leading", lf.id)
            es = lf.lab_spec.to_exercise_specs()
            if es:
                vl_keys.add((es[0].mode, tuple(es[0].pattern)))
        for tokens, mode in _REQUIRED_TYPES + _REQUIRED_PROGRESSIONS:
            self.assertIn((mode, tokens), vl_keys, f"VL missing {tokens} ({mode})")

    def test_theory_states_function_path_and_bass_motion(self):
        # The derived function-path/bass-motion prose is the block variant's
        # contract; the SATB variants carry the voice-leading concept prose.
        for lf in self.block_leaves:
            self.assertIn("Function path:", lf.theory, lf.id)
            self.assertIn("Bass motion:", lf.theory, lf.id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
