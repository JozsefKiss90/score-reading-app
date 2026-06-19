"""Tests for the canonical curriculum ontology (harmony.curriculum).

These run headless (no Qt / no display).  They enforce the consolidation's
contract:

  * the tree is deterministic (same build -> identical ids / ordering / payload);
  * EVERY native trainer drill (the 102 of default_exercise_groups) is reachable
    as exactly one exercise leaf -- no duplication, no omission;
  * every exercise leaf owns exactly one LabExperimentSpec that compiles within
    the readability cap (MAX_CHORDS_PER_SPEC);
  * the drill passthrough round-trips losslessly to the original HarmonyExerciseSpec;
  * every node carries the required pedagogical envelope;
  * search jumps to the right nodes;
  * the module is pure (no PyQt6 / verovio).

Run from the project root::

    .venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -t .
"""

import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from harmony.exercise_spec import (  # noqa: E402
    all_default_specs, compile_exercise, MAX_CHORDS_PER_SPEC,
)
from harmony.lab_spec import LabExperimentSpec  # noqa: E402
from harmony.lab import lab_demo_specs  # noqa: E402
from harmony.curriculum import (  # noqa: E402
    build_curriculum, get_curriculum, to_json, search_curriculum,
    build_search_index, CurriculumNode, KINDS, SCHEMA_VERSION,
)


class TestStructure(unittest.TestCase):
    def setUp(self):
        self.root = build_curriculum()

    def test_root_is_curriculum(self):
        self.assertEqual(self.root.kind, "curriculum")
        self.assertIsNone(self.root.parent)
        self.assertTrue(self.root.children)

    def test_kinds_are_valid(self):
        for n in self.root.walk():
            self.assertIn(n.kind, KINDS, n.id)

    def test_parent_pointers_consistent(self):
        for n in self.root.walk():
            for c in n.children:
                self.assertEqual(c.parent, n.id, c.id)

    def test_expected_top_level_categories(self):
        titles = [c.title for c in self.root.children]
        for needed in ("Scales", "Chords (Triads)", "Degrees & Transposition",
                       "Functions", "Cadences", "Intervals & Interval Layers",
                       "Inversions", "Voice Leading", "Motives",
                       "Polyphonic Harmony", "Interactive Harmony Atlas",
                       "Circle of Fifths"):
            self.assertIn(needed, titles, needed)

    def test_orders_are_sequential_per_parent(self):
        for n in self.root.walk():
            for i, c in enumerate(n.children):
                self.assertEqual(c.order, i, (n.id, c.id))


class TestCoverage(unittest.TestCase):
    """Every native + lab exercise reachable exactly once; nothing duplicated."""

    def setUp(self):
        self.root = build_curriculum()
        self.leaves = self.root.leaves()

    def test_leaf_ids_unique(self):
        ids = [lf.id for lf in self.leaves]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_native_default_spec_reachable_once(self):
        native_ids = [hs.exercise_id for hs in all_default_specs()]
        self.assertEqual(len(native_ids), 102)            # the canonical 102
        covered = []
        for lf in self.leaves:
            for es in lf.lab_spec.to_exercise_specs():
                covered.append(es.exercise_id)
        for nid in native_ids:
            self.assertIn(nid, covered, nid)
        # each native id appears exactly once (no duplication)
        for nid in native_ids:
            self.assertEqual(covered.count(nid), 1, nid)

    def test_every_lab_demo_reachable(self):
        lab_ids = {s.experiment_id for s in lab_demo_specs()}
        leaf_lab_ids = {lf.lab_spec.experiment_id for lf in self.leaves}
        self.assertTrue(lab_ids.issubset(leaf_lab_ids),
                        lab_ids - leaf_lab_ids)

    def test_exercise_count_rolls_up(self):
        self.assertEqual(self.root.exercise_count, len(self.leaves))
        # a container's count == sum of its children's counts
        for n in self.root.walk():
            if n.children:
                self.assertEqual(n.exercise_count,
                                 sum(c.exercise_count for c in n.children), n.id)

    def test_native_partition_counts(self):
        # Scales(48) + Chords(7) + Degrees(28) + Functions(19) = 102 native
        by_title = {c.title: c.exercise_count for c in self.root.children}
        self.assertEqual(by_title["Scales"], 48)
        self.assertEqual(by_title["Chords (Triads)"], 7)
        self.assertEqual(by_title["Degrees & Transposition"], 28)
        self.assertEqual(by_title["Functions"], 19)


class TestLabSpecOwnership(unittest.TestCase):
    def setUp(self):
        self.root = build_curriculum()

    def test_every_leaf_owns_exactly_one_lab_spec(self):
        for lf in self.root.leaves():
            self.assertIsInstance(lf.lab_spec, LabExperimentSpec, lf.id)
            lf.lab_spec.validate()

    def test_non_leaves_have_no_lab_spec(self):
        for n in self.root.walk():
            if n.kind != "exercise":
                self.assertIsNone(n.lab_spec, n.id)

    def test_every_leaf_compiles_within_cap(self):
        for lf in self.root.leaves():
            for es in lf.lab_spec.to_exercise_specs():
                es.validate()
                n = len(compile_exercise(es))
                self.assertLessEqual(n, MAX_CHORDS_PER_SPEC, lf.id)

    def test_drill_passthrough_round_trips(self):
        native = {hs.exercise_id: hs for hs in all_default_specs()}
        for lf in self.root.leaves():
            if lf.lab_spec.concept != "drill":
                continue
            es = lf.lab_spec.to_exercise_specs()
            self.assertEqual(len(es), 1, lf.id)
            orig = native.get(es[0].exercise_id)
            if orig is None:
                continue   # cadence-type drills are not in the native default set
            a = [c.triad.chord_symbol for c in compile_exercise(orig).chords]
            b = [c.triad.chord_symbol for c in compile_exercise(es[0]).chords]
            self.assertEqual(a, b, lf.id)
            self.assertEqual(orig.render, es[0].render)
            self.assertEqual(orig.mode, es[0].mode)


class TestPedagogicalEnvelope(unittest.TestCase):
    def setUp(self):
        self.root = build_curriculum()

    def test_every_node_has_title_and_objective(self):
        for n in self.root.walk():
            self.assertTrue(n.title.strip(), n.id)
            # reserved nodes may omit an objective; everything else has one
            if not n.reserved:
                self.assertTrue(n.learning_objective.strip()
                                or n.subtitle.strip(), n.id)

    def test_difficulty_in_range(self):
        for n in self.root.walk():
            self.assertTrue(1 <= n.difficulty <= 5, (n.id, n.difficulty))

    def test_leaf_has_atlas_and_circle_refs(self):
        for lf in self.root.leaves():
            self.assertTrue(lf.atlas_nodes, lf.id)
            self.assertTrue(lf.circle_nodes, lf.id)

    def test_atlas_refs_resolve_in_ontology(self):
        from harmony.atlas import build_atlas
        atlas = build_atlas()
        for lf in self.root.leaves():
            for nid in lf.atlas_nodes:
                self.assertIsNotNone(atlas.node(nid), (lf.id, nid))

    def test_prereq_and_next_point_at_real_nodes(self):
        ids = {n.id for n in self.root.walk()}
        for n in self.root.walk():
            for pid in n.prerequisites:
                self.assertIn(pid, ids, (n.id, pid))
            if n.recommended_next is not None:
                self.assertIn(n.recommended_next, ids, n.id)
            for rid in n.related:
                self.assertIn(rid, ids, (n.id, rid))

    def test_estimated_minutes_positive_for_leaves(self):
        for lf in self.root.leaves():
            self.assertGreater(lf.estimated_minutes, 0, lf.id)


class TestDeterminism(unittest.TestCase):
    def test_two_builds_identical(self):
        import json
        a = json.dumps(to_json(build_curriculum()), sort_keys=True)
        b = json.dumps(to_json(build_curriculum()), sort_keys=True)
        self.assertEqual(a, b)

    def test_cached_singleton(self):
        self.assertIs(get_curriculum(), get_curriculum())

    def test_payload_schema(self):
        payload = to_json()
        self.assertEqual(payload["schema"], SCHEMA_VERSION)
        for k in ("tree", "index", "kinds"):
            self.assertIn(k, payload)


class TestSearch(unittest.TestCase):
    def setUp(self):
        self.root = build_curriculum()

    def _titles(self, q):
        return [self.root.find(h).title for h in search_curriculum(self.root, q)]

    def test_progression_query(self):
        hits = search_curriculum(self.root, "ii V I")
        self.assertTrue(hits)
        joined = " ".join(self.root.find(h).title for h in hits)
        self.assertIn("ii", joined)

    def test_function_query(self):
        self.assertTrue(search_curriculum(self.root, "predominant"))

    def test_key_query(self):
        hits = self._titles("C major")
        self.assertTrue(any("C major" in t or "C, " in t for t in hits))

    def test_cadence_query(self):
        hits = self._titles("authentic cadence")
        self.assertTrue(any("authentic" in t.lower() for t in hits))

    def test_quality_query(self):
        self.assertTrue(any("iminished" in t for t in self._titles("diminished")))

    def test_empty_query_returns_nothing(self):
        self.assertEqual(search_curriculum(self.root, ""), [])
        self.assertEqual(search_curriculum(self.root, "   "), [])

    def test_index_covers_every_node(self):
        index = build_search_index(self.root)
        self.assertEqual(len(index), len(list(self.root.walk())))
        for entry in index:
            self.assertTrue(entry["path"])         # breadcrumb present


class TestReservedBranches(unittest.TestCase):
    def setUp(self):
        self.root = build_curriculum()

    def test_reserved_categories_have_no_exercises(self):
        for cid in ("cat:advanced", "cat:reserved"):
            node = self.root.find(cid)
            self.assertIsNotNone(node, cid)
            self.assertEqual(node.exercise_count, 0, cid)
            self.assertTrue(node.reserved, cid)

    def test_bridge_categories_present(self):
        for cid in ("cat:atlas", "cat:circle"):
            self.assertIsNotNone(self.root.find(cid), cid)


class TestPurity(unittest.TestCase):
    def test_curriculum_modules_pure(self):
        code = (
            "import harmony.curriculum, harmony.curriculum_explanations, "
            "harmony.curriculum_progress, sys; "
            "bad=[m for m in sys.modules if m.split('.')[0] in "
            "('PyQt6','verovio')]; assert not bad, bad; print('pure')")
        r = subprocess.run([sys.executable, "-c", code], cwd=PROJECT_ROOT,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("pure", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
