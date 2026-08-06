"""V7 figured bass as graded performance instructions — ticket 11 / plan G1c.

The dominant seventh's inversions become *drills*: the figured tokens
``V65`` / ``V43`` / ``V42`` (and their slash spellings ``V6/5`` …) parse to
the V7 tetrad with a demanded bass, the Lab ``inversion`` concept widens to
seventh-token degrees (four voicings: 7 · 6/5 · 4/3 · 4/2), and every figured
measure grades its bass as the LOWEST sounding note through the ticket-04
strict-bass machinery.  Captions and grading are one thing: the figure shown
is derived from the same inversion that selects the graded bass.

Run from the project root::

    .venv/Scripts/python.exe -m unittest tests.test_figured_sevenths
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from theory.diatonic_harmony import note_pc  # noqa: E402
from harmony.lab import compile_lab  # noqa: E402
from harmony.lab_spec import (  # noqa: E402
    LabExperimentSpec,
    parse_figured_token,
    split_figured_pattern,
)
from harmony.lab_musicxml import build_lab_payload  # noqa: E402
from harmony.exercise_spec import compile_exercise  # noqa: E402


def _cadence(pattern, render="block", mode="major", key="C major"):
    return LabExperimentSpec(
        "t_fig7", "t", concept="cadence", key=key, mode=mode, render=render,
        parameters={"pattern": list(pattern), "cadence_type": "authentic"})


def _inversion(degree="V7", inversions=(0, 1, 2, 3), mode="major",
               key="C major", render="block"):
    return LabExperimentSpec(
        "t_inv7", "t", concept="inversion", key=key, mode=mode, render=render,
        parameters={"degree": degree, "inversions": list(inversions)})


class TestParseFiguredSeventhTokens(unittest.TestCase):
    """V65 / V43 / V42 (and slash spellings) parse to the V7 tetrad + inversion."""

    def test_dominant_seventh_figures_parse(self):
        for tok, inv in [("V65", 1), ("V6/5", 1), ("V43", 2), ("V4/3", 2),
                         ("V42", 3), ("V4/2", 3)]:
            self.assertEqual(parse_figured_token(tok), ("V7", inv), tok)

    def test_plain_seventh_token_keeps_root_position(self):
        self.assertEqual(parse_figured_token("V7"), ("V7", 0))

    def test_triad_figures_unchanged(self):
        self.assertEqual(parse_figured_token("ii6"), ("ii", 1))
        self.assertEqual(parse_figured_token("I64"), ("I", 2))
        self.assertEqual(parse_figured_token("V"), ("V", 0))

    def test_non_dominant_seventh_figures_left_for_rejection(self):
        # "ii65" is not in the G1c vocabulary: the token stays intact so the
        # roman gate rejects it explicitly (never silently downgraded).
        self.assertEqual(parse_figured_token("ii65"), ("ii65", 0))
        with self.assertRaises(ValueError):
            _cadence(["ii65", "V", "I"]).validate()

    def test_split_pattern_mixes_triad_and_seventh_figures(self):
        heads, invs = split_figured_pattern(["ii6", "V42", "I6"])
        self.assertEqual(heads, ["ii", "V7", "I"])
        self.assertEqual(invs, [1, 3, 1])


class TestFiguredSeventhValidation(unittest.TestCase):
    def test_v65_requires_major_mode(self):
        # Natural minor has no V7 (its degree-5 seventh is v7); the figured
        # form must refuse exactly like the plain token does.
        with self.assertRaises(ValueError):
            _cadence(["V65", "i"], mode="natural_minor", key="A minor").validate()

    def test_figured_sevenths_require_block_render(self):
        with self.assertRaises(ValueError):
            _cadence(["V65", "I"], render="voice_leading").validate()

    def test_block_figured_seventh_validates(self):
        _cadence(["V65", "I"]).validate()
        _cadence(["V42", "I6"]).validate()


class TestFiguredSeventhCadenceMeasures(unittest.TestCase):
    """Each figured V7 measure demands the inversion's bass, strictly."""

    def test_v65_demands_the_leading_tone_in_the_bass(self):
        m0, m1 = compile_lab(_cadence(["V65", "I"])).measures
        # G7 in C: the figure 6/5 puts the third (B, the leading tone) in
        # the bass, and only that measure is graded strictly.
        self.assertEqual(m0.annotation.roman, "V7")
        self.assertEqual(m0.annotation.bass_note, "B")
        self.assertEqual(m0.bass_pitch_class, note_pc("B"))
        self.assertEqual(m0.annotation.figured_bass, "6/5")
        self.assertEqual(m0.annotation.inversion, 1)
        self.assertTrue(m0.strict_bass)
        self.assertEqual(len(m0.target_pitch_classes), 4)
        self.assertFalse(m1.strict_bass)

    def test_v43_and_v42_bass_notes(self):
        m0, _ = compile_lab(_cadence(["V43", "I"])).measures
        self.assertEqual(m0.annotation.bass_note, "D")     # fifth of G7
        self.assertEqual(m0.annotation.figured_bass, "4/3")
        self.assertEqual(m0.annotation.inversion, 2)
        m0, _ = compile_lab(_cadence(["V42", "I"])).measures
        self.assertEqual(m0.annotation.bass_note, "F")     # seventh of G7
        self.assertEqual(m0.annotation.figured_bass, "4/2")
        self.assertEqual(m0.annotation.inversion, 3)

    def test_v42_resolves_to_i6_with_stepwise_bass(self):
        # The classic pairing: 4/2's bass (the chordal seventh, 4̂) resolves
        # down by step into I6's bass (3̂).
        m0, m1 = compile_lab(_cadence(["V42", "I6"])).measures
        self.assertEqual(m0.annotation.bass_note, "F")
        self.assertEqual(m1.annotation.bass_note, "E")
        self.assertTrue(m0.strict_bass)
        self.assertTrue(m1.strict_bass)
        self.assertEqual(m1.annotation.figured_bass, "6")
        self.assertEqual(m1.annotation.bass_motion, "F → E")

    def test_plain_v7_measure_is_not_bass_graded(self):
        # Root-position V7 (ticket 09) keeps octave-agnostic grading: no
        # figure was asked, so no figure is claimed and no bass is demanded.
        m0, _ = compile_lab(_cadence(["V7", "I"])).measures
        self.assertFalse(m0.strict_bass)
        self.assertIsNone(m0.annotation.figured_bass)
        self.assertIsNone(m0.annotation.inversion)


class TestCaptionsMatchGrading(unittest.TestCase):
    """Ticket checkbox 2: the figured-bass caption == exactly what is graded."""

    def test_payload_threads_figure_and_bass_together(self):
        payload = build_lab_payload(compile_lab(
            _cadence(["V65", "I", "V43", "I", "V42", "I6"])))
        expect = [("6/5", "B", True), (None, None, False),
                  ("4/3", "D", True), (None, None, False),
                  ("4/2", "F", True), ("6", "E", True)]
        for t, (fig, bass, strict) in zip(payload["TARGET_CHORDS"], expect):
            self.assertEqual(t["figuredBass"], fig, t["absMeasure"])
            self.assertEqual(t["strictBass"], strict, t["absMeasure"])
            if strict:
                self.assertEqual(t["bassNote"], bass)
                self.assertEqual(t["bassPitchClass"], note_pc(bass))


class TestSeventhInversionConcept(unittest.TestCase):
    """The Lab inversion concept widens to seventh degrees (V7, 4 voicings)."""

    def test_four_voicings_with_figures_and_strict_bass(self):
        exp = compile_lab(_inversion())
        self.assertEqual(len(exp.measures), 4)
        self.assertEqual([m.annotation.bass_note for m in exp.measures],
                         ["G", "B", "D", "F"])
        self.assertEqual([m.annotation.figured_bass for m in exp.measures],
                         ["7", "6/5", "4/3", "4/2"])
        self.assertEqual([m.annotation.inversion_label for m in exp.measures],
                         ["root position", "first inversion",
                          "second inversion", "third inversion"])
        for m in exp.measures:
            self.assertTrue(m.strict_bass, m.index)
            self.assertEqual(m.annotation.roman, "V7")
            self.assertEqual(len(m.target_pitch_classes), 4)
            self.assertEqual(m.bass_pitch_class,
                             note_pc(m.annotation.bass_note))

    def test_tetrad_claims_no_atlas_triad_node(self):
        for m in compile_lab(_inversion()).measures:
            self.assertIsNone(m.annotation.atlas_triad_id, m.index)
            self.assertIsNone(m.annotation.atlas_degree_id, m.index)

    def test_triad_inversions_unchanged(self):
        exp = compile_lab(_inversion(degree="V", inversions=(0, 1, 2)))
        self.assertEqual([m.annotation.figured_bass for m in exp.measures],
                         ["5/3", "6", "6/4"])

    def test_third_inversion_rejected_for_triads(self):
        with self.assertRaises(ValueError):
            _inversion(degree="V", inversions=(0, 1, 2, 3)).validate()

    def test_seventh_degree_rejected_outside_its_mode(self):
        with self.assertRaises(ValueError):
            _inversion(degree="V7", mode="natural_minor",
                       key="A minor").validate()

    def test_payload_grades_all_four_basses(self):
        payload = build_lab_payload(compile_lab(_inversion()))
        targets = payload["TARGET_CHORDS"]
        self.assertEqual([t["strictBass"] for t in targets], [True] * 4)
        self.assertEqual([t["bassNote"] for t in targets],
                         ["G", "B", "D", "F"])
        self.assertEqual([t["figuredBass"] for t in targets],
                         ["7", "6/5", "4/3", "4/2"])


class TestTrainerBridge(unittest.TestCase):
    """to_exercise_specs strips figures to the root-position seventh skeleton."""

    def test_cadence_bridge_pattern_and_id(self):
        specs = _cadence(["V65", "I"]).to_exercise_specs()
        self.assertEqual(specs[0].pattern, ["V7", "I"])
        self.assertIn("V65", specs[0].exercise_id)
        self.assertEqual(len(compile_exercise(specs[0])), 2)

    def test_figured_ids_stay_distinct(self):
        ids = {tuple(p): _cadence(list(p)).to_exercise_specs()[0].exercise_id
               for p in (("V65", "I"), ("V43", "I"), ("V42", "I6"),
                         ("V7", "I"))}
        self.assertEqual(len(set(ids.values())), 4, ids)

    def test_inversion_bridge_builds_the_seventh(self):
        specs = _inversion().to_exercise_specs()
        self.assertEqual(specs[0].pattern, ["V7"])
        self.assertEqual(len(compile_exercise(specs[0])), 1)


class TestSceneRouterHonesty(unittest.TestCase):
    """No triad scene may claim a V7 experiment (the base_roman rule)."""

    def test_seventh_inversion_refuses_the_triad_inversion_scene(self):
        from harmony.graph_scene_router import (GraphSceneRequest,
                                                decide_graph_scene,
                                                build_graph_scene)
        req = GraphSceneRequest(lab_spec=_inversion())
        decision = decide_graph_scene(req)
        self.assertEqual(decision.status, "unsupported")
        self.assertIn("triads only", decision.reason)
        scene = build_graph_scene(req)
        self.assertEqual(scene.scene_type, "unsupported")

    def test_metadata_cannot_force_the_triad_scene_either(self):
        from harmony.graph_scene_router import (GraphSceneRequest,
                                                decide_graph_scene)
        decision = decide_graph_scene(GraphSceneRequest(
            lab_spec=_inversion(),
            source_metadata={"graph_scene_type": "inversion_space"}))
        self.assertEqual(decision.status, "unsupported")

    def test_triad_inversions_keep_their_scene(self):
        from harmony.graph_scene_router import (GraphSceneRequest,
                                                decide_graph_scene)
        decision = decide_graph_scene(GraphSceneRequest(
            lab_spec=_inversion(degree="V", inversions=(0, 1, 2))))
        self.assertEqual(decision.status, "supported")
        self.assertEqual(decision.scene_type, "inversion_space")

    def test_figured_resolution_routes_to_the_cadence_scene(self):
        # The cadence path is honest already: the scene builds from the
        # root-position function skeleton, whose tetrads type as `seventh`.
        from harmony.graph_scene_router import (GraphSceneRequest,
                                                decide_graph_scene,
                                                build_graph_scene)
        req = GraphSceneRequest(lab_spec=_cadence(["V65", "I", "V42", "I6"]))
        decision = decide_graph_scene(req)
        self.assertEqual(decision.status, "supported")
        self.assertEqual(decision.scene_type, "cadence_resolution")
        scene = build_graph_scene(req)
        self.assertEqual(scene.scene_type, "cadence_resolution")


class TestCurriculumG1c(unittest.TestCase):
    """The G1c leaves: the sevenths_more seam goes live with figured drills."""

    @classmethod
    def setUpClass(cls):
        from harmony.curriculum import build_curriculum
        cls.root = build_curriculum()
        cls.cat = cls.root.find("cat:sevenths")

    def test_sevenths_more_lesson_is_now_live(self):
        more = self.root.find("lesson:sevenths_more")
        self.assertIsNotNone(more)
        self.assertFalse(more.reserved)
        self.assertFalse(any(ch.reserved for ch in more.children))

    def test_category_grew_to_56_leaves(self):
        # 32 (G1a+G1b) + 12 figured-inversion + 12 resolution-walk leaves.
        self.assertEqual(self.cat.exercise_count, 56)

    def test_figured_inversion_grid_covers_all_twelve_keys(self):
        grp = self.root.find("group:sevenths_figured_inv")
        self.assertIsNotNone(grp)
        leaves = list(grp.leaves())
        self.assertEqual(len(leaves), 12)
        keys = set()
        for lf in leaves:
            spec = lf.lab_spec
            self.assertEqual(spec.concept, "inversion", lf.id)
            self.assertEqual(spec.parameters["degree"], "V7", lf.id)
            self.assertEqual(list(spec.parameters["inversions"]),
                             [0, 1, 2, 3], lf.id)
            keys.add(spec.key.split()[0])
        self.assertEqual(len(keys), 12)

    def test_resolution_walk_covers_all_twelve_keys(self):
        grp = self.root.find("group:sevenths_figured_res")
        self.assertIsNotNone(grp)
        leaves = list(grp.leaves())
        self.assertEqual(len(leaves), 12)
        keys = set()
        for lf in leaves:
            spec = lf.lab_spec
            self.assertEqual(spec.concept, "cadence", lf.id)
            self.assertEqual(list(spec.parameters["pattern"]),
                             ["V65", "I", "V43", "I", "V42", "I6"], lf.id)
            keys.add(spec.key.split()[0])
        self.assertEqual(len(keys), 12)

    def test_every_new_leaf_compiles_and_grades_the_bass(self):
        for gid in ("group:sevenths_figured_inv", "group:sevenths_figured_res"):
            for lf in self.root.find(gid).leaves():
                payload = build_lab_payload(compile_lab(lf.lab_spec))
                strict = [t for t in payload["TARGET_CHORDS"] if t["strictBass"]]
                self.assertTrue(strict, lf.id)
                for t in strict:
                    self.assertIsNotNone(t["bassPitchClass"], lf.id)
                    self.assertTrue(t["figuredBass"], lf.id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
