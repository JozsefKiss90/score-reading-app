"""Piano-technique ticket 06 — arpeggios in groups of four.

Part A (trainer): ``HarmonyExerciseSpec.arp_octave_root`` makes an
arpeggio-rendered chord a four-tone accent cell — the root returns an octave
up as the 4th quarter, so the accent (and the thumb) lands on a different
chord tone each cycle.  The tests pin, in order:

  * the spec surface: additive flag, default False, byte-stable ``to_dict``
    for unflagged specs, tolerant ``from_dict``, the render/mcq gates;
  * the MusicXML: 4 quarters, the 4th the root an octave up, no rest padding;
  * the payload: ``pitchClasses`` ``[r, 3rd, 5th, r]``, ``midiPitches``
    ``+12``, four expected beats (the ordered walk grades the cell with no
    JS change);
  * the opt-in group: ``technique_arpeggio_demo_specs`` — 2 specs (major +
    minor), 12 keys each, flag on — while ``default_exercise_groups()``
    stays exactly its pinned 102-drill self.

Part B (lab): two-octave arpeggio *runs* as ``cat:technique`` leaves — the
13-note up/down cycle played twice in eighths, RH measures then LH measures
in one leaf (``hand`` becomes per-measure), standard fingerings from
``harmony/technique_data.py``, an accent mark on every 4th note.
"""

import os
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harmony.exercise_spec import (  # noqa: E402
    GROUP_TECH_ARPEGGIO,
    HarmonyExerciseSpec,
    compile_exercise,
    default_exercise_groups,
    technique_arpeggio_demo_specs,
)
from harmony.lab import compile_lab  # noqa: E402
from harmony.lab_spec import LabExperimentSpec  # noqa: E402
from harmony.musicxml_builder import (  # noqa: E402
    build_musicxml,
    build_trainer_payload,
)


def _cell_spec(**kw) -> HarmonyExerciseSpec:
    base = dict(
        exercise_id="tech_arp_cell_test",
        title="Accent-cell test",
        drill="horizontal_degree", degree="I", render="arpeggio",
        mode="major", keys=["C"], arp_octave_root=True,
    )
    base.update(kw)
    return HarmonyExerciseSpec(**base)


class TestSpecSurface(unittest.TestCase):
    def test_flag_defaults_false(self):
        spec = HarmonyExerciseSpec(
            exercise_id="x", title="x", drill="full_key", key="C major")
        self.assertFalse(spec.arp_octave_root)

    def test_unflagged_to_dict_is_byte_stable(self):
        # The pinned 102-drill set serialises exactly as before the flag.
        spec = HarmonyExerciseSpec(
            exercise_id="x", title="x", drill="full_key", key="C major")
        self.assertNotIn("arp_octave_root", spec.to_dict())

    def test_flagged_spec_round_trips(self):
        spec = _cell_spec()
        spec.validate()
        again = HarmonyExerciseSpec.from_dict(spec.to_dict())
        self.assertTrue(again.arp_octave_root)

    def test_from_dict_tolerates_absence(self):
        d = _cell_spec().to_dict()
        d.pop("arp_octave_root")
        self.assertFalse(HarmonyExerciseSpec.from_dict(d).arp_octave_root)

    def test_flag_requires_arpeggio_render(self):
        with self.assertRaisesRegex(ValueError, "arpeggio"):
            _cell_spec(render="block").validate()

    def test_flag_refuses_quality_mcq(self):
        # A 4-pc triad cell would read as a tetrad to the quality question.
        with self.assertRaisesRegex(ValueError, "mcq_focus"):
            _cell_spec(answer_mode="mcq", mcq_focus="quality").validate()


class TestMusicXML(unittest.TestCase):
    def _voice1_notes(self, spec):
        xml = build_musicxml(compile_exercise(spec))
        root = ET.fromstring(xml)
        measure = root.find(".//measure")
        notes, rests = [], 0
        for n in measure.findall("note"):
            if n.find("voice").text != "1":
                continue
            if n.find("rest") is not None:
                rests += 1
                continue
            p = n.find("pitch")
            notes.append((p.find("step").text, int(p.find("octave").text)))
        return notes, rests

    def test_cell_is_four_quarters_no_rests(self):
        notes, rests = self._voice1_notes(_cell_spec())
        self.assertEqual(notes, [("C", 4), ("E", 4), ("G", 4), ("C", 5)])
        self.assertEqual(rests, 0)

    def test_unflagged_arpeggio_unchanged(self):
        notes, rests = self._voice1_notes(_cell_spec(arp_octave_root=False))
        self.assertEqual(notes, [("C", 4), ("E", 4), ("G", 4)])
        self.assertEqual(rests, 1)


class TestPayload(unittest.TestCase):
    def _target(self, spec):
        payload = build_trainer_payload(compile_exercise(spec))
        return payload, payload["TARGET_CHORDS"][0]

    def test_pitch_classes_return_to_root(self):
        _, t = self._target(_cell_spec())
        self.assertEqual(t["pitchClasses"], [0, 4, 7, 0])
        self.assertEqual(t["midiPitches"], [60, 64, 67, 72])
        self.assertEqual(len(t["chordTones"]), 4)
        self.assertEqual(t["chordTones"][0], t["chordTones"][3])

    def test_expected_beats_cover_the_cell(self):
        payload, _ = self._target(_cell_spec())
        expected = payload["EXPECTED_MIDI_BY_MEASURE_OR_BEAT"]["0"]
        self.assertEqual(expected,
                         {"1": [0], "2": [4], "3": [7], "4": [0]})

    def test_unflagged_payload_unchanged(self):
        _, t = self._target(_cell_spec(arp_octave_root=False))
        self.assertEqual(t["pitchClasses"], [0, 4, 7])
        self.assertEqual(t["midiPitches"], [60, 64, 67])


class TestDemoGroup(unittest.TestCase):
    def test_two_specs_twelve_keys_each(self):
        specs = technique_arpeggio_demo_specs()
        self.assertEqual(len(specs), 2)
        modes = {s.mode for s in specs}
        self.assertEqual(modes, {"major", "natural_minor"})
        for s in specs:
            s.validate()
            self.assertEqual(s.drill, "horizontal_degree")
            self.assertEqual(s.render, "arpeggio")
            self.assertTrue(s.arp_octave_root)
            self.assertEqual(len(compile_exercise(s)), 12)

    def test_every_target_is_a_four_tone_cell(self):
        for s in technique_arpeggio_demo_specs():
            payload = build_trainer_payload(compile_exercise(s))
            for t in payload["TARGET_CHORDS"]:
                self.assertEqual(len(t["pitchClasses"]), 4, t["key"])
                self.assertEqual(t["pitchClasses"][0], t["pitchClasses"][3])

    def test_group_name_is_the_tickets(self):
        self.assertEqual(GROUP_TECH_ARPEGGIO,
                         "Technique: arpeggio cells (groups of four)")

    def test_default_groups_do_not_carry_the_flag(self):
        # The opt-in group never leaks into the pinned default set.
        for specs in default_exercise_groups().values():
            for s in specs:
                self.assertFalse(s.arp_octave_root, s.exercise_id)


def _lab_spec(**kw) -> LabExperimentSpec:
    params = dict(
        phrase=[[1, 2, 3], [3, 2, 1]],
        note_value="eighth",
        hand=["rh", "lh"],
    )
    params.update(kw.pop("parameters", {}))
    base = dict(
        experiment_id="tech_hand_test", title="Hand test",
        concept="technique", mode="major", key="C major", render="melody",
        parameters=params,
    )
    base.update(kw)
    return LabExperimentSpec(**base)


class TestPerMeasureHand(unittest.TestCase):
    """Ticket 06 B: ``hand`` may be per-measure, so one leaf holds RH
    measures then LH measures (the ordered walk crosses staves naturally
    since only one line sounds at a time)."""

    def test_per_measure_hand_validates(self):
        _lab_spec().validate()   # must not raise

    def test_wrong_length_refused(self):
        with self.assertRaisesRegex(ValueError, "hand"):
            _lab_spec(parameters={"hand": ["rh"]}).validate()

    def test_unknown_entry_refused(self):
        with self.assertRaisesRegex(ValueError, "hand"):
            _lab_spec(parameters={"hand": ["rh", "both"]}).validate()

    def test_scalar_hand_still_validates(self):
        _lab_spec(parameters={"hand": "lh"}).validate()

    def test_staves_follow_the_per_measure_hand(self):
        spec = _lab_spec()
        spec.validate()
        m_rh, m_lh = compile_lab(spec).measures
        # RH measure: line on the treble staff, bass staff idle.
        self.assertFalse(any(n.is_rest for n in m_rh.staff1[:3]))
        self.assertTrue(all(n.is_rest for n in m_rh.staff2))
        # LH measure: line on the bass staff, treble staff idle.
        self.assertTrue(all(n.is_rest for n in m_lh.staff1))
        self.assertFalse(any(n.is_rest for n in m_lh.staff2[:3]))

    def test_lh_measures_sit_two_octaves_down(self):
        spec = _lab_spec()
        spec.validate()
        m_rh, m_lh = compile_lab(spec).measures
        self.assertEqual(m_rh.staff1[0].octave, 4)   # C4
        self.assertEqual(m_lh.staff2[2].octave, 2)   # degree 1 -> C2

    def test_hand_groups_split_the_leaf(self):
        spec = _lab_spec()
        spec.validate()
        m_rh, m_lh = compile_lab(spec).measures
        self.assertIn("right hand", m_rh.group)
        self.assertIn("left hand", m_lh.group)
        self.assertNotEqual(m_rh.group, m_lh.group)

    def test_grading_contract_untouched(self):
        spec = _lab_spec()
        spec.validate()
        m_rh, m_lh = compile_lab(spec).measures
        self.assertEqual(m_rh.target_pitch_classes, (0, 2, 4))
        self.assertEqual(m_lh.target_pitch_classes, (4, 2, 0))


class TestFingeringTable(unittest.TestCase):
    """harmony/technique_data.py — the standard two-octave arpeggio table."""

    def _table(self):
        from harmony.technique_data import ARPEGGIO_FINGERINGS
        return ARPEGGIO_FINGERINGS

    def test_covers_24_keys_both_hands(self):
        from harmony.exercise_spec import (
            DEFAULT_MAJOR_KEYS, DEFAULT_MINOR_KEYS)
        table = self._table()
        for tonic in DEFAULT_MAJOR_KEYS:
            self.assertIn((tonic, "major"), table, tonic)
        for tonic in DEFAULT_MINOR_KEYS:
            self.assertIn((tonic, "minor"), table, tonic)
        self.assertEqual(len(table), 24)

    def test_seven_valid_labels_per_hand(self):
        for key, hands in self._table().items():
            for hand in ("rh", "lh"):
                labels = hands[hand]
                self.assertEqual(len(labels), 7, key)
                for lab in labels:
                    self.assertIn(lab, ("1", "2", "3", "4", "5"), key)

    def test_c_major_oracle(self):
        # The ticket's spot-check: RH 1-2-3-1-2-3-5, LH 5-4-2-1-4-2-1.
        table = self._table()
        self.assertEqual(table[("C", "major")]["rh"],
                         ("1", "2", "3", "1", "2", "3", "5"))
        self.assertEqual(table[("C", "major")]["lh"],
                         ("5", "4", "2", "1", "4", "2", "1"))

    def test_a_minor_oracle(self):
        # White-key minor arpeggios share the white-key major pattern.
        table = self._table()
        self.assertEqual(table[("A", "minor")]["rh"],
                         ("1", "2", "3", "1", "2", "3", "5"))


class TestArpeggioRunLeaves(unittest.TestCase):
    """The 24 ``ex:tech_arp_run_*`` leaves under ``lesson:tech_arpeggios``."""

    @classmethod
    def setUpClass(cls):
        from harmony.curriculum import build_curriculum
        cls.root = build_curriculum()

    def _leaves(self):
        lesson = self.root.find("lesson:tech_arpeggios")
        self.assertIsNotNone(lesson)
        out = []
        for grp in lesson.children:
            out.extend(c for c in grp.children if c.kind == "exercise")
        return out

    def test_24_leaves(self):
        leaves = self._leaves()
        self.assertEqual(len(leaves), 24)
        ids = {l.id for l in leaves}
        self.assertIn("ex:tech_arp_run_c_major", ids)
        self.assertIn("ex:tech_arp_run_a_minor", ids)

    def test_leaf_compiles_renders_grades(self):
        leaf = self.root.find("ex:tech_arp_run_c_major")
        spec = leaf.lab_spec
        spec.validate()
        exp = compile_lab(spec)
        self.assertEqual(len(exp.measures), 8)         # 4 RH + 4 LH
        # RH measures then LH measures, as two groups.
        groups = [m.group for m in exp.measures]
        self.assertIn("right hand", groups[0])
        self.assertIn("left hand", groups[4])
        self.assertEqual(len(set(groups)), 2)
        from harmony.lab_musicxml import build_lab_musicxml, build_lab_payload
        xml = build_lab_musicxml(exp)
        self.assertIn("<accent/>", xml)
        self.assertIn("<technical><fingering>", xml)
        payload = build_lab_payload(exp)
        self.assertEqual(payload["render"], "arpeggio")

    def test_run_walks_two_octaves_up_and_down_twice(self):
        leaf = self.root.find("ex:tech_arp_run_c_major")
        exp = compile_lab(leaf.lab_spec)
        # C major tonic arpeggio pcs: C E G, up 2 octaves and back = 13
        # notes, cycled twice = 26 per hand.
        cycle = [0, 4, 7, 0, 4, 7, 0, 7, 4, 0, 7, 4, 0]
        rh = [pc for m in exp.measures[:4] for pc in m.target_pitch_classes]
        lh = [pc for m in exp.measures[4:] for pc in m.target_pitch_classes]
        self.assertEqual(rh, cycle + cycle)
        self.assertEqual(lh, cycle + cycle)

    def test_accent_on_every_fourth_note(self):
        leaf = self.root.find("ex:tech_arp_run_c_major")
        arts = leaf.lab_spec.parameters["articulations"]
        flat = [a for m in arts for a in m]
        self.assertEqual(len(flat), 52)                # 26 notes x 2 hands
        for hand_stream in (flat[:26], flat[26:]):
            for i, a in enumerate(hand_stream):
                self.assertEqual(a, "accent" if i % 4 == 0 else "", i)

    def test_fingering_follows_the_table(self):
        leaf = self.root.find("ex:tech_arp_run_c_major")
        fingering = leaf.lab_spec.parameters["fingering"]
        flat = [f for m in fingering for f in m]
        self.assertEqual(flat[:13],
                         ["1", "2", "3", "1", "2", "3", "5",
                          "3", "2", "1", "3", "2", "1"])
        self.assertEqual(flat[26:39],
                         ["5", "4", "2", "1", "4", "2", "1",
                          "2", "4", "1", "2", "4", "5"])

    def test_coach_text_in_description(self):
        leaf = self.root.find("ex:tech_arp_run_c_major")
        self.assertIn("Accent the first of each four", leaf.description)
        self.assertIn("not graded", leaf.description)

    def test_leaf_count_fingerprint(self):
        # 381 (ticket 19 + technique tracer) + 24 arpeggio runs = 405, + 7
        # Chord Progression Foundations leaves = 412; the Python pin lives in
        # tests/test_applied_chords.py, the JS mirror in
        # tests/curriculum_node_test.js.
        self.assertEqual(self.root.exercise_count, 412)


if __name__ == "__main__":
    unittest.main()
