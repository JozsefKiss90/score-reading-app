"""Piano-technique ticket 01 — the ``technique`` Lab concept + phrase engine.

The concept compiles a multi-measure, single-key melodic phrase (the missing
shape between ``motive`` and the ten daily technique exercises).  These tests
pin, in order:

  * the validation edges (measure cap, degree range, note values, hand,
    fingering shape);
  * the compile shape (measure count, per-slot single-pc ``expected_by_beat``
    -- exactly ``_gen_motive``'s ordered-walk contract -- staff choice per
    hand, rest padding, honest guide text with the coach line);
  * the render/payload path (MusicXML + ordered ``arpeggio`` targets);
  * echo ineligibility (no 🎧 twin for technique leaves);
  * the ``cat:technique`` tracer leaf wired through the curriculum.

Ticket 02 layers the notation vocabulary on top: 16th-note slots, per-note
fingering numerals, two-note slurs and staccato/accent marks.  All of it is
opt-in presentation (grading is untouched); ``TestNotationMarks`` pins the
emitted MusicXML, including that a spec without the new params produces no
``<notations>`` at all.

Ticket 03 teaches the grader simultaneity: a phrase entry may be a tuple of
degrees (a dyad sounded together) and ``octaves: True`` doubles every step at
the written octave.  Each such measure carries ordered ``step_targets``
(pitch classes held concurrently + the minimum count of distinct keys), the
payload gains the additive ``steps`` field, and the notation stacks the
partners with ``<chord/>``.  ``TestSimultaneity*`` pins all three layers,
including that scalar phrases stay byte-identical (no ``steps`` key at all).
"""

import os
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harmony.atlas import scale_id  # noqa: E402
from harmony.echo_drills import is_echo_eligible  # noqa: E402
from harmony.lab import compile_lab  # noqa: E402
from harmony.lab_musicxml import build_lab_musicxml, build_lab_payload  # noqa: E402
from harmony.lab_spec import LabExperimentSpec  # noqa: E402


TRACER_LEAF = "ex:tech_warmup_five_finger_c_rh"

#: C major degrees 1..5 -> pitch classes (the five-finger position).
_C_PCS = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7}


def _spec(**kw) -> LabExperimentSpec:
    params = dict(
        phrase=[[1, 2, 3, 4, 5, 4, 3, 2], [1]],
        note_value="eighth",
        hand="rh",
    )
    params.update(kw.pop("parameters", {}))
    base = dict(
        experiment_id="tech_test", title="Technique test",
        concept="technique", mode="major", key="C major", render="melody",
        parameters=params,
    )
    base.update(kw)
    return LabExperimentSpec(**base)


class TestValidation(unittest.TestCase):
    """The spec-surface edges the ticket pins."""

    def test_valid_spec_validates(self):
        _spec().validate()   # must not raise

    def test_round_trips_through_dict(self):
        spec = _spec()
        spec.validate()
        again = LabExperimentSpec.from_dict(spec.to_dict())
        self.assertEqual(again.parameters["phrase"], spec.parameters["phrase"])

    def test_thirteen_measures_refused(self):
        with self.assertRaisesRegex(ValueError, "13"):
            _spec(parameters={"phrase": [[1]] * 13}).validate()

    def test_twelve_measures_accepted(self):
        _spec(parameters={"phrase": [[1]] * 12}).validate()

    def test_degree_30_refused(self):
        with self.assertRaisesRegex(ValueError, "1..29"):
            _spec(parameters={"phrase": [[1, 30]]}).validate()

    def test_degree_0_refused(self):
        with self.assertRaisesRegex(ValueError, "1..29"):
            _spec(parameters={"phrase": [[0, 1]]}).validate()

    def test_degree_29_accepted(self):
        _spec(parameters={"phrase": [[1, 29]]}).validate()

    def test_empty_phrase_refused(self):
        with self.assertRaisesRegex(ValueError, "phrase"):
            _spec(parameters={"phrase": []}).validate()

    def test_empty_measure_refused(self):
        with self.assertRaisesRegex(ValueError, "measure"):
            _spec(parameters={"phrase": [[1, 2], []]}).validate()

    def test_sixteenths_accepted(self):
        # ticket 02: a 4/4 bar holds sixteen 16ths.
        _spec(parameters={"note_value": "16th",
                          "phrase": [list(range(1, 17))]}).validate()

    def test_seventeen_sixteenths_refused(self):
        with self.assertRaises(ValueError):
            _spec(parameters={"note_value": "16th",
                              "phrase": [list(range(1, 18))]}).validate()

    def test_unknown_note_value_refused(self):
        with self.assertRaisesRegex(ValueError, "note_value"):
            _spec(parameters={"note_value": "32nd"}).validate()

    def test_measure_overflowing_its_slots_refused(self):
        # 5 quarters cannot fit a 4/4 bar; 9 eighths cannot either.
        with self.assertRaises(ValueError):
            _spec(parameters={"phrase": [[1, 2, 3, 4, 5]],
                              "note_value": "quarter"}).validate()
        with self.assertRaises(ValueError):
            _spec(parameters={"phrase": [[1, 2, 3, 4, 5, 4, 3, 2, 1]]}).validate()

    def test_unknown_hand_refused(self):
        with self.assertRaisesRegex(ValueError, "hand"):
            _spec(parameters={"hand": "both"}).validate()

    def test_fingering_shape_mismatch_refused(self):
        # one tuple per measure and one label per note -- both directions.
        with self.assertRaisesRegex(ValueError, "fingering"):
            _spec(parameters={"fingering": [["1", "2"]]}).validate()
        with self.assertRaisesRegex(ValueError, "fingering"):
            _spec(parameters={
                "fingering": [["1", "2", "3", "4", "5", "4", "3"], ["1"]],
            }).validate()

    def test_fingering_labels_restricted(self):
        with self.assertRaisesRegex(ValueError, "fingering"):
            _spec(parameters={
                "fingering": [["1", "2", "3", "4", "5", "4", "3", "6"], ["1"]],
            }).validate()

    def test_matching_fingering_accepted(self):
        _spec(parameters={
            "fingering": [["1", "2", "3", "4", "5", "4", "3", "2"], ["1"]],
        }).validate()

    def test_slurs_shape_mismatch_refused(self):
        # slurs mirror the phrase shape exactly as fingering does.
        with self.assertRaisesRegex(ValueError, "slurs"):
            _spec(parameters={"slurs": [["start", "stop"]]}).validate()

    def test_slur_vocab_restricted(self):
        with self.assertRaisesRegex(ValueError, "slur"):
            _spec(parameters={
                "slurs": [["legato", "", "", "", "", "", "", ""], [""]],
            }).validate()

    def test_articulations_shape_mismatch_refused(self):
        with self.assertRaisesRegex(ValueError, "articulations"):
            _spec(parameters={"articulations": [["staccato"]]}).validate()

    def test_articulation_vocab_restricted(self):
        with self.assertRaisesRegex(ValueError, "articulation"):
            _spec(parameters={
                "articulations": [["tenuto", "", "", "", "", "", "", ""],
                                  [""]],
            }).validate()

    def test_matching_slurs_and_articulations_accepted(self):
        _spec(parameters={
            "slurs": [["start", "stop", "start", "stop", "", "", "", ""],
                      [""]],
            "articulations": [["accent", "", "", "", "", "", "", "staccato"],
                              [""]],
        }).validate()

    def test_block_render_refused(self):
        with self.assertRaisesRegex(ValueError, "render"):
            _spec(render="block").validate()

    def test_melodic_minor_refused(self):
        # melodic minor stays motive-only (its scale form is direction-bound).
        with self.assertRaisesRegex(ValueError, "motive"):
            _spec(mode="melodic_minor", key="A minor").validate()

    def test_no_chord_drill_representation(self):
        self.assertEqual(_spec().to_exercise_specs(), [])


class TestCompile(unittest.TestCase):
    """The phrase engine's compile shape (the _gen_motive grading contract)."""

    def test_measure_count_matches_phrase(self):
        exp = compile_lab(_spec())
        self.assertEqual(len(exp.measures), 2)

    def test_expected_by_beat_single_ordered_pcs(self):
        exp = compile_lab(_spec())
        m0 = exp.measures[0]
        want = [_C_PCS[d] for d in (1, 2, 3, 4, 5, 4, 3, 2)]
        self.assertEqual(m0.expected_by_beat,
                         {i + 1: [pc] for i, pc in enumerate(want)})
        self.assertEqual(list(m0.target_pitch_classes), want)
        for pcs in m0.expected_by_beat.values():
            self.assertEqual(len(pcs), 1)
        self.assertEqual(exp.measures[1].expected_by_beat, {1: [0]})

    def test_rh_line_on_treble_staff(self):
        m0 = compile_lab(_spec()).measures[0]
        self.assertEqual(len([n for n in m0.staff1 if not n.is_rest]), 8)
        self.assertEqual(len(m0.staff2), 1)
        self.assertTrue(m0.staff2[0].is_rest)
        self.assertEqual(m0.staff2[0].note_type, "whole")
        # octave 4-centred: degree 1 in C major is C4
        self.assertEqual(m0.staff1[0].octave, 4)

    def test_lh_line_on_bass_staff_octaves_2_3(self):
        m0 = compile_lab(_spec(parameters={"hand": "lh"})).measures[0]
        self.assertEqual(len([n for n in m0.staff2 if not n.is_rest]), 8)
        self.assertEqual(len(m0.staff1), 1)
        self.assertTrue(m0.staff1[0].is_rest)
        # the same degrees two octaves down: degree 1 -> C2
        self.assertEqual(m0.staff2[0].octave, 2)
        # grading is octave-agnostic: same pitch classes as the RH line
        self.assertEqual(m0.expected_by_beat[1], [0])

    def test_short_measure_rest_padded(self):
        m1 = compile_lab(_spec()).measures[1]
        self.assertEqual(len(m1.staff1), 8)          # 1 note + 7 eighth rests
        self.assertEqual(len([n for n in m1.staff1 if n.is_rest]), 7)
        self.assertTrue(all(n.note_type == "eighth" for n in m1.staff1))

    def test_quarter_note_value_uses_four_slots(self):
        exp = compile_lab(_spec(parameters={"phrase": [[1, 2, 3]],
                                            "note_value": "quarter"}))
        m0 = exp.measures[0]
        self.assertEqual(len(m0.staff1), 4)          # 3 quarters + 1 rest
        self.assertTrue(all(n.note_type == "quarter" for n in m0.staff1))

    def test_sixteenth_note_value_uses_sixteen_slots(self):
        exp = compile_lab(_spec(parameters={"phrase": [list(range(1, 17))],
                                            "note_value": "16th"}))
        m0 = exp.measures[0]
        self.assertEqual(len(m0.staff1), 16)
        self.assertTrue(all(n.note_type == "16th" for n in m0.staff1))
        # note-by-note grading: one ordered pc per slot, keys 1..16
        self.assertEqual(sorted(m0.expected_by_beat), list(range(1, 17)))
        for pcs in m0.expected_by_beat.values():
            self.assertEqual(len(pcs), 1)

    def test_sixteenth_short_measure_rest_padded(self):
        m0 = compile_lab(_spec(parameters={"phrase": [[1, 2, 3]],
                                           "note_value": "16th"})).measures[0]
        self.assertEqual(len(m0.staff1), 16)         # 3 notes + 13 rests
        self.assertEqual(len([n for n in m0.staff1 if n.is_rest]), 13)
        self.assertTrue(all(n.note_type == "16th" for n in m0.staff1))

    def test_degrees_wrap_into_higher_octaves(self):
        exp = compile_lab(_spec(parameters={"phrase": [[1, 8, 15, 29]],
                                            "note_value": "quarter"}))
        notes = [n for n in exp.measures[0].staff1 if not n.is_rest]
        self.assertEqual([n.octave for n in notes], [4, 5, 6, 8])
        self.assertTrue(all(n.step == "C" for n in notes))

    def test_measures_are_melody_with_no_underlying_chord(self):
        for m in compile_lab(_spec()).measures:
            self.assertEqual(m.render, "melody")
            self.assertIsNone(m.underlying)
            self.assertIsNone(m.bass_pitch_class)

    def test_annotation_carries_key_fingering_and_coach(self):
        spec = _spec(parameters={
            "fingering": [["1", "2", "3", "4", "5", "4", "3", "2"], ["1"]],
            "coach": "Even, relaxed tone; let the wrist float.",
        })
        m0 = compile_lab(spec).measures[0]
        self.assertEqual(m0.annotation.atlas_scale_id, scale_id("C", "major"))
        self.assertIn("measure 1/2", m0.annotation.lab_note)
        self.assertIn("1 2 3 4 5 4 3 2", m0.annotation.lab_note)
        self.assertIn("let the wrist float", m0.annotation.lab_note)

    def test_musicxml_and_payload_render(self):
        exp = compile_lab(_spec())
        xml = build_lab_musicxml(exp)
        self.assertIn("<work-title>", xml)
        self.assertEqual(xml.count("<measure number="), 2)
        payload = build_lab_payload(exp)
        self.assertEqual(payload["render"], "arpeggio")   # the ordered walk
        self.assertEqual(payload["concept"], "technique")
        for t in payload["TARGET_CHORDS"]:
            self.assertEqual(t["render"], "arpeggio")
        self.assertEqual(payload["EXPECTED_MIDI_BY_MEASURE_OR_BEAT"]["0"]["1"],
                         [0])

    def test_harmonic_minor_phrase_compiles(self):
        exp = compile_lab(_spec(mode="harmonic_minor", key="A minor",
                                parameters={"phrase": [[5, 6, 7, 8]],
                                            "note_value": "quarter"}))
        notes = [n for n in exp.measures[0].staff1 if not n.is_rest]
        # harmonic minor's raised 7th: G# -> pc 8
        self.assertEqual([n.pitch_class for n in notes], [4, 5, 8, 9])


def _measure_notes(xml: str, staff: str = "1"):
    """All ``<note>`` elements of measure 1 on ``staff``, in document order."""
    measure = ET.fromstring(xml).find(".//measure")
    return [n for n in measure.findall("note") if n.findtext("staff") == staff]


def _sounding(notes):
    return [n for n in notes if n.find("rest") is None]


class TestNotationMarks(unittest.TestCase):
    """Ticket 02 -- 16th durations + fingering/slur/articulation MusicXML.

    Everything here is opt-in presentation: the last test pins that a spec
    without the new params emits no ``<notations>`` (the byte-identity
    guarantee for every existing exercise through the shared ``_note_xml``).
    """

    def test_sixteenth_measure_sums_to_sixty_four_ticks(self):
        xml = build_lab_musicxml(compile_lab(_spec(parameters={
            "phrase": [list(range(1, 17))], "note_value": "16th"})))
        notes = _measure_notes(xml)
        durs = [int(n.findtext("duration")) for n in notes]
        self.assertEqual(len(durs), 16)
        self.assertEqual(set(durs), {4})             # DIVISIONS=16 -> 16th = 4
        self.assertEqual(sum(durs), 64)              # exactly one 4/4 measure
        self.assertEqual({n.findtext("type") for n in notes}, {"16th"})

    def test_fingering_renders_on_correct_noteheads(self):
        xml = build_lab_musicxml(compile_lab(_spec(parameters={
            "fingering": [["1", "2", "3", "4", "5", "4", "3", "2"], ["1"]]})))
        line = _sounding(_measure_notes(xml))
        got = [n.findtext("notations/technical/fingering") for n in line]
        self.assertEqual(got, ["1", "2", "3", "4", "5", "4", "3", "2"])

    def test_slur_pair_renders_endpoints(self):
        xml = build_lab_musicxml(compile_lab(_spec(parameters={
            "slurs": [["start", "stop", "", "", "", "", "", ""], [""]]})))
        line = _sounding(_measure_notes(xml))
        self.assertEqual(line[0].find("notations/slur").get("type"), "start")
        self.assertEqual(line[0].find("notations/slur").get("number"), "1")
        self.assertEqual(line[1].find("notations/slur").get("type"), "stop")
        self.assertIsNone(line[2].find("notations"))

    def test_articulation_marks_render(self):
        xml = build_lab_musicxml(compile_lab(_spec(parameters={
            "articulations": [["accent", "staccato", "", "", "", "", "", ""],
                              [""]]})))
        line = _sounding(_measure_notes(xml))
        self.assertIsNotNone(line[0].find("notations/articulations/accent"))
        self.assertIsNotNone(line[1].find("notations/articulations/staccato"))
        self.assertIsNone(line[2].find("notations"))

    def test_one_notations_wrapper_holds_all_three(self):
        xml = build_lab_musicxml(compile_lab(_spec(parameters={
            "fingering": [["1", "2", "3", "4", "5", "4", "3", "2"], ["1"]],
            "slurs": [["start", "stop", "", "", "", "", "", ""], [""]],
            "articulations": [["staccato", "", "", "", "", "", "", ""],
                              [""]]})))
        n0 = _sounding(_measure_notes(xml))[0]
        self.assertEqual(len(n0.findall("notations")), 1)
        marks = n0.find("notations")
        self.assertIsNotNone(marks.find("slur"))
        self.assertIsNotNone(marks.find("articulations/staccato"))
        self.assertEqual(marks.findtext("technical/fingering"), "1")

    def test_notations_sit_after_staff_dtd_order(self):
        # MusicXML note child order puts <notations> after <staff>; Verovio
        # accepts either, the DTD only the latter.
        xml = build_lab_musicxml(compile_lab(_spec(parameters={
            "fingering": [["1", "2", "3", "4", "5", "4", "3", "2"], ["1"]]})))
        tags = [c.tag for c in _sounding(_measure_notes(xml))[0]]
        self.assertLess(tags.index("type"), tags.index("staff"))
        self.assertEqual(tags[-1], "notations")

    def test_rest_padding_and_idle_staff_carry_no_marks(self):
        xml = build_lab_musicxml(compile_lab(_spec(parameters={
            "phrase": [[1, 2, 3]], "note_value": "quarter",
            "fingering": [["1", "2", "3"]],
            "articulations": [["staccato", "staccato", "staccato"]]})))
        root = ET.fromstring(xml)
        marked = [n for n in root.iter("note") if n.find("notations") is not None]
        self.assertEqual(len(marked), 3)
        self.assertTrue(all(n.find("rest") is None for n in marked))

    def test_spec_without_marks_emits_no_notations(self):
        xml = build_lab_musicxml(compile_lab(_spec()))
        for fragment in ("<notations>", "<fingering", "<slur", "<articulations"):
            self.assertNotIn(fragment, xml)


class TestSimultaneityValidation(unittest.TestCase):
    """Ticket 03 -- dyad steps + octave doubling at the spec surface."""

    def test_dyad_phrase_validates(self):
        _spec(parameters={"phrase": [[[1, 3], [2, 4], 5]],
                          "note_value": "quarter"}).validate()

    def test_dyad_degrees_range_checked(self):
        with self.assertRaisesRegex(ValueError, "1..29"):
            _spec(parameters={"phrase": [[[1, 30]]],
                              "note_value": "quarter"}).validate()

    def test_duplicate_degrees_in_step_refused(self):
        with self.assertRaisesRegex(ValueError, "distinct"):
            _spec(parameters={"phrase": [[[3, 3]]],
                              "note_value": "quarter"}).validate()

    def test_octave_pair_written_as_degrees_seven_apart_validates(self):
        _spec(parameters={"phrase": [[[1, 8]]],
                          "note_value": "quarter"}).validate()

    def test_octaves_param_validates(self):
        _spec(parameters={"phrase": [[1, 2, 3, 4]], "octaves": True,
                          "note_value": "quarter"}).validate()

    def test_octaves_with_dyad_entry_refused(self):
        with self.assertRaisesRegex(ValueError, "octaves"):
            _spec(parameters={"phrase": [[[1, 3], 2]], "octaves": True,
                              "note_value": "quarter"}).validate()

    def test_octaves_degree_cap_respects_written_pair(self):
        # the written pair is (d, d+7): degree 22 tops out at 29, 23 spills
        _spec(parameters={"phrase": [[22]], "octaves": True,
                          "note_value": "quarter"}).validate()
        with self.assertRaisesRegex(ValueError, "octave"):
            _spec(parameters={"phrase": [[23]], "octaves": True,
                              "note_value": "quarter"}).validate()

    def test_dyads_occupy_one_slot_each(self):
        eight = [[i, i + 2] for i in range(1, 9)]
        _spec(parameters={"phrase": [eight]}).validate()
        with self.assertRaises(ValueError):
            _spec(parameters={"phrase": [eight + [[1, 3]]]}).validate()

    def test_dyad_fingering_tuple_accepted(self):
        _spec(parameters={"phrase": [[[1, 3], 2]], "note_value": "quarter",
                          "fingering": [[["1", "3"], "2"]]}).validate()

    def test_dyad_fingering_wrong_size_refused(self):
        with self.assertRaisesRegex(ValueError, "fingering"):
            _spec(parameters={"phrase": [[[1, 3], 2]], "note_value": "quarter",
                              "fingering": [[["1", "3", "5"], "2"]]}).validate()

    def test_tuple_mark_on_scalar_step_refused(self):
        with self.assertRaisesRegex(ValueError, "fingering"):
            _spec(parameters={"phrase": [[1, 2]], "note_value": "quarter",
                              "fingering": [[["1", "3"], "2"]]}).validate()

    def test_scalar_mark_on_dyad_step_accepted(self):
        # one label marks the whole step (attached to its first notehead)
        _spec(parameters={"phrase": [[[1, 3], [2, 4]]], "note_value": "quarter",
                          "slurs": [["start", "stop"]]}).validate()

    def test_dyad_mark_vocab_checked(self):
        with self.assertRaisesRegex(ValueError, "fingering"):
            _spec(parameters={"phrase": [[[1, 3]]], "note_value": "quarter",
                              "fingering": [[["1", "6"]]]}).validate()

    def test_dyads_round_trip_through_dict(self):
        spec = _spec(parameters={"phrase": [[[1, 3], 2]],
                                 "note_value": "quarter"})
        spec.validate()
        again = LabExperimentSpec.from_dict(spec.to_dict())
        again.validate()
        self.assertEqual(again.parameters["phrase"], spec.parameters["phrase"])


class TestSimultaneityCompile(unittest.TestCase):
    """Ticket 03 -- step targets, chord stacking, per-beat pc lists."""

    def _dyads(self, **params):
        base = {"phrase": [[[1, 3], [2, 4]]], "note_value": "quarter"}
        base.update(params)
        return compile_lab(_spec(parameters=base))

    def test_dyad_measure_carries_step_targets(self):
        m0 = self._dyads().measures[0]
        self.assertEqual(
            [(list(s.pcs), s.min_distinct) for s in m0.step_targets],
            [([0, 4], 2), ([2, 5], 2)])

    def test_dyad_flat_union_and_expected_by_beat(self):
        m0 = self._dyads().measures[0]
        self.assertEqual(list(m0.target_pitch_classes), [0, 4, 2, 5])
        self.assertEqual(m0.expected_by_beat, {1: [0, 4], 2: [2, 5]})

    def test_scalar_measures_have_no_step_targets(self):
        for m in compile_lab(_spec()).measures:
            self.assertIsNone(m.step_targets)

    def test_dyad_renders_chord_stacked(self):
        m0 = self._dyads().measures[0]
        notes = [n for n in m0.staff1 if not n.is_rest]
        self.assertEqual([n.is_chord_tone for n in notes],
                         [False, True, False, True])
        self.assertEqual([(n.step, n.octave) for n in notes],
                         [("C", 4), ("E", 4), ("D", 4), ("F", 4)])
        # two steps in a 4-slot quarter bar -> two padding rests
        self.assertEqual(len([n for n in m0.staff1 if n.is_rest]), 2)

    def test_octaves_double_every_step(self):
        exp = compile_lab(_spec(parameters={
            "phrase": [[1, 2]], "octaves": True, "note_value": "quarter"}))
        m0 = exp.measures[0]
        self.assertEqual(
            [(list(s.pcs), s.min_distinct) for s in m0.step_targets],
            [([0], 2), ([2], 2)])
        notes = [n for n in m0.staff1 if not n.is_rest]
        self.assertEqual([(n.step, n.octave, n.is_chord_tone) for n in notes],
                         [("C", 4, False), ("C", 5, True),
                          ("D", 4, False), ("D", 5, True)])
        self.assertEqual(m0.expected_by_beat, {1: [0], 2: [2]})
        self.assertEqual(list(m0.target_pitch_classes), [0, 2])

    def test_explicit_octave_dyad_demands_two_keys(self):
        exp = compile_lab(_spec(parameters={"phrase": [[[1, 8]]],
                                            "note_value": "quarter"}))
        s = exp.measures[0].step_targets[0]
        self.assertEqual((list(s.pcs), s.min_distinct), ([0], 2))

    def test_mixed_scalar_and_dyad_measure(self):
        exp = compile_lab(_spec(parameters={"phrase": [[1, [1, 3], 5]],
                                            "note_value": "quarter"}))
        self.assertEqual(
            [(list(s.pcs), s.min_distinct)
             for s in exp.measures[0].step_targets],
            [([0], 1), ([0, 4], 2), ([7], 1)])

    def test_lh_dyads_shift_both_notes(self):
        exp = compile_lab(_spec(parameters={"phrase": [[[1, 3]]],
                                            "note_value": "quarter",
                                            "hand": "lh"}))
        notes = [n for n in exp.measures[0].staff2 if not n.is_rest]
        self.assertEqual([(n.step, n.octave) for n in notes],
                         [("C", 2), ("E", 2)])

    def test_dyad_guide_text_names_both_notes(self):
        m0 = self._dyads().measures[0]
        self.assertIn("C4+E4", m0.annotation.lab_note)

    def test_dyad_fingering_renders_per_note(self):
        exp = compile_lab(_spec(parameters={
            "phrase": [[[1, 3], 2]], "note_value": "quarter",
            "fingering": [[["1", "3"], "2"]]}))
        notes = [n for n in exp.measures[0].staff1 if not n.is_rest]
        self.assertEqual([n.fingering for n in notes], ["1", "3", "2"])

    def test_scalar_mark_lands_on_first_notehead(self):
        exp = compile_lab(_spec(parameters={
            "phrase": [[[1, 3], [2, 4]]], "note_value": "quarter",
            "slurs": [["start", "stop"]]}))
        notes = [n for n in exp.measures[0].staff1 if not n.is_rest]
        self.assertEqual([n.slur for n in notes], ["start", "", "stop", ""])


class TestSimultaneityPayload(unittest.TestCase):
    """Ticket 03 -- the additive ``steps`` payload field + playback/render."""

    def _experiment(self, **params):
        base = {"phrase": [[[1, 3], [2, 4]]], "note_value": "quarter"}
        base.update(params)
        return compile_lab(_spec(parameters=base))

    def _payload(self, **params):
        return build_lab_payload(self._experiment(**params))

    def test_steps_emitted_with_flat_pitch_classes(self):
        t = self._payload()["TARGET_CHORDS"][0]
        # ``midis`` carries the same keys as notated, so the walk can demand
        # the written octave; ``pcs`` stays the octave-blind guide-text view.
        self.assertEqual(t["steps"],
                         [{"pcs": [0, 4], "minDistinct": 2, "midis": [60, 64]},
                          {"pcs": [2, 5], "minDistinct": 2, "midis": [62, 65]}])
        self.assertEqual(t["pitchClasses"], [0, 4, 2, 5])
        self.assertEqual(t["render"], "arpeggio")

    def test_scalar_targets_carry_no_steps_key(self):
        # backward/forward safety: old payloads unchanged, JS ignores unknowns
        payload = build_lab_payload(compile_lab(_spec()))
        for t in payload["TARGET_CHORDS"]:
            self.assertNotIn("steps", t)

    def test_octave_steps_min_distinct_two(self):
        # One pc, two written keys an octave apart — ``midis`` keeps both, so
        # the pair must be played as written rather than at any two C's.
        t = self._payload(phrase=[[1, 2]], octaves=True)["TARGET_CHORDS"][0]
        self.assertEqual(t["steps"],
                         [{"pcs": [0], "minDistinct": 2, "midis": [60, 72]},
                          {"pcs": [2], "minDistinct": 2, "midis": [62, 74]}])
        self.assertEqual(t["pitchClasses"], [0, 2])

    def test_expected_map_carries_both_pcs_per_beat(self):
        payload = self._payload()
        self.assertEqual(payload["EXPECTED_MIDI_BY_MEASURE_OR_BEAT"]["0"],
                         {"1": [0, 4], "2": [2, 5]})

    def test_playback_plan_sounds_dyads_together(self):
        from harmony.playback_plan import build_playback_plan
        plan = build_playback_plan(self._payload())
        dyads = [sorted(e.midis) for e in plan.events if len(e.midis) == 2]
        self.assertEqual(dyads, [[60, 64], [62, 65]])   # C4+E4, D4+F4

    def test_musicxml_stacks_dyads_with_chord_element(self):
        xml = build_lab_musicxml(self._experiment())
        self.assertEqual(xml.count("<chord/>"), 2)
        # the principal (non-chord) noteheads still fill the bar exactly
        principals = [n for n in _measure_notes(xml)
                      if n.find("chord") is None]
        self.assertEqual(sum(int(n.findtext("duration")) for n in principals),
                         64)


class TestHoldValidation(unittest.TestCase):
    """Ticket 04 -- the ``hold`` param (one entry per measure) + v2 opt-in."""

    def _hold_spec(self, **params):
        base = {"phrase": [[2, 3, 4, 5], [5, 4, 3, 2]],
                "note_value": "quarter", "hold": [[1], []]}
        base.update(params)
        return _spec(parameters=base)

    def test_hold_validates(self):
        self._hold_spec().validate()

    def test_hold_length_must_mirror_phrase(self):
        with self.assertRaisesRegex(ValueError, "hold"):
            self._hold_spec(hold=[[1]]).validate()
        with self.assertRaisesRegex(ValueError, "hold"):
            self._hold_spec(hold=[[1], [], [5]]).validate()

    def test_two_note_hold_refused(self):
        with self.assertRaisesRegex(ValueError, "hold"):
            self._hold_spec(hold=[[1, 5], []]).validate()

    def test_hold_degree_range_checked(self):
        with self.assertRaisesRegex(ValueError, "1..29"):
            self._hold_spec(hold=[[30], []]).validate()
        with self.assertRaisesRegex(ValueError, "1..29"):
            self._hold_spec(hold=[[0], []]).validate()

    def test_all_empty_hold_entries_equal_no_hold(self):
        self._hold_spec(hold=[[], []]).validate()

    def test_hold_graded_requires_a_hold(self):
        self._hold_spec(hold_graded=True).validate()
        with self.assertRaisesRegex(ValueError, "hold_graded"):
            self._hold_spec(hold=[[], []], hold_graded=True).validate()
        with self.assertRaisesRegex(ValueError, "hold_graded"):
            self._hold_spec(hold=(), hold_graded=True).validate()

    def test_hold_sharing_a_moving_pitch_class_refused(self):
        # The grader hears pitch classes only: a hold on the same class as a
        # moving note would grade itself (pressing the hold advances the
        # walk).  Same degree and octave-apart degrees both collide.
        with self.assertRaisesRegex(ValueError, "pitch class"):
            self._hold_spec(phrase=[[1, 2, 3, 4], [5]],
                            hold=[[1], []]).validate()
        with self.assertRaisesRegex(ValueError, "pitch class"):
            self._hold_spec(phrase=[[8, 9, 10], [5]],
                            hold=[[1], []]).validate()

    def test_hold_collision_checked_per_measure_only(self):
        # measure 2's moving line may reuse measure 1's held class freely.
        self._hold_spec(phrase=[[2, 3, 4, 5], [1, 2, 3]],
                        hold=[[1], []]).validate()

    def test_hold_round_trips_through_dict(self):
        spec = self._hold_spec(hold_graded=True)
        spec.validate()
        again = LabExperimentSpec.from_dict(spec.to_dict())
        again.validate()
        self.assertEqual(again.parameters["hold"], spec.parameters["hold"])
        self.assertTrue(again.parameters["hold_graded"])


class TestHoldCompile(unittest.TestCase):
    """Ticket 04 -- the hold as a second voice; grading stays the moving line."""

    def _compile(self, **params):
        base = {"phrase": [[2, 3, 4, 5], [5, 4, 3, 2]],
                "note_value": "quarter", "hold": [[1], []]}
        base.update(params)
        return compile_lab(_spec(parameters=base))

    def test_rh_hold_is_whole_note_second_voice_on_treble(self):
        m0 = self._compile().measures[0]
        self.assertEqual(len(m0.staff1_voice2), 1)
        held = m0.staff1_voice2[0]
        self.assertFalse(held.is_rest)
        self.assertEqual((held.step, held.octave, held.note_type),
                         ("C", 4, "whole"))
        self.assertEqual(m0.staff2_voice2, ())
        # the moving line still lives in voice 1
        self.assertEqual(len([n for n in m0.staff1 if not n.is_rest]), 4)

    def test_lh_hold_shifts_with_the_hand(self):
        m0 = self._compile(hand="lh").measures[0]
        self.assertEqual(len(m0.staff2_voice2), 1)
        self.assertEqual((m0.staff2_voice2[0].step, m0.staff2_voice2[0].octave),
                         ("C", 2))
        self.assertEqual(m0.staff1_voice2, ())

    def test_no_hold_measure_has_empty_second_voice(self):
        m1 = self._compile().measures[1]
        self.assertEqual(m1.staff1_voice2, ())
        self.assertEqual(m1.staff2_voice2, ())
        self.assertIsNone(m1.hold_pc)

    def test_grading_is_the_moving_line_only(self):
        # v1 AND v2: the hold pc appears in neither expected_by_beat nor
        # target_pitch_classes -- degree 1 hold under a 2..5 walk.
        m0 = self._compile().measures[0]
        self.assertEqual(m0.expected_by_beat,
                         {1: [2], 2: [4], 3: [5], 4: [7]})
        self.assertEqual(list(m0.target_pitch_classes), [2, 4, 5, 7])
        self.assertEqual(m0.hold_pc, 0)

    def test_hold_midi_still_sounds_in_the_payload_pitches(self):
        # midiPitches builds the runtime PITCH_MAP: the engraved hold C4=60
        # must be listed even though it is not a grading target.
        m0 = self._compile().measures[0]
        self.assertIn(60, m0.sounding_midis())

    def test_v1_guide_text_states_the_grading_honestly(self):
        note = self._compile().measures[0].annotation.lab_note
        self.assertIn("Hold C4", note)
        self.assertIn("Graded: the moving notes in order", note)
        self.assertIn("not graded yet: keeping the hold down", note)

    def test_v2_guide_text_promises_the_hold_check(self):
        m0 = self._compile(hold_graded=True).measures[0]
        note = m0.annotation.lab_note
        self.assertIn("Hold C4", note)
        self.assertIn("only while the hold is sounding", note)
        self.assertNotIn("not graded yet", note)
        self.assertTrue(m0.hold_graded)

    def test_hold_graded_only_marks_measures_with_a_hold(self):
        exp = self._compile(hold_graded=True)
        self.assertTrue(exp.measures[0].hold_graded)
        self.assertFalse(exp.measures[1].hold_graded)

    def test_no_hold_measure_text_carries_no_hold_line(self):
        note = self._compile().measures[1].annotation.lab_note
        self.assertNotIn("Hold", note)
        self.assertNotIn("hold", note)


class TestHoldMusicXml(unittest.TestCase):
    """Ticket 04 -- two-voice serialization + the no-hold byte identity."""

    def _xml(self, **params):
        base = {"phrase": [[2, 3, 4, 5], [5, 4, 3, 2]],
                "note_value": "quarter", "hold": [[1], []]}
        base.update(params)
        return build_lab_musicxml(compile_lab(_spec(parameters=base)))

    @staticmethod
    def _measures(xml):
        return ET.fromstring(xml).findall(".//measure")

    @staticmethod
    def _voice_ticks(measure):
        """{voice: summed duration} over every note of the measure."""
        out = {}
        for n in measure.findall("note"):
            if n.find("chord") is not None:
                continue                     # chord partners carry no new time
            v = n.findtext("voice")
            out[v] = out.get(v, 0) + int(n.findtext("duration"))
        return out

    def test_hold_measure_emits_two_backups_and_voice_three(self):
        m0 = self._measures(self._xml())[0]
        backups = m0.findall("backup")
        self.assertEqual(len(backups), 2)
        self.assertTrue(all(b.findtext("duration") == "64" for b in backups))
        held = [n for n in m0.findall("note") if n.findtext("voice") == "3"]
        self.assertEqual(len(held), 1)
        self.assertEqual(held[0].findtext("staff"), "1")
        self.assertEqual(held[0].findtext("type"), "whole")

    def test_hold_voice_precedes_the_bass_staff_stream(self):
        # document order: staff1 voice 1, backup, staff1 voice 3, backup,
        # staff2 voice 2 -- the second voice stays inside its staff's block.
        m0 = self._measures(self._xml())[0]
        seq = [(c.tag, c.findtext("voice")) for c in m0
               if c.tag in ("note", "backup")]
        voices = [v for tag, v in seq if tag == "note"]
        self.assertEqual(voices, ["1"] * 4 + ["3"] + ["2"])

    def test_each_voice_fills_the_bar_independently(self):
        for m in self._measures(self._xml()):
            for voice, ticks in self._voice_ticks(m).items():
                self.assertEqual(ticks, 64, f"voice {voice}")

    def test_lh_hold_uses_voice_four_on_staff_two(self):
        xml = self._xml(hand="lh")
        m0 = self._measures(xml)[0]
        self.assertEqual(len(m0.findall("backup")), 2)
        held = [n for n in m0.findall("note") if n.findtext("voice") == "4"]
        self.assertEqual(len(held), 1)
        self.assertEqual(held[0].findtext("staff"), "2")

    def test_no_hold_measure_keeps_the_single_backup_layout(self):
        m1 = self._measures(self._xml())[1]
        self.assertEqual(len(m1.findall("backup")), 1)
        self.assertEqual({n.findtext("voice") for n in m1.findall("note")},
                         {"1", "2"})

    def test_spec_without_holds_renders_byte_identically(self):
        # the regression the ticket pins: the hold machinery must be a no-op
        # for every spec that does not use it (empty entries included).
        plain = self._xml(hold=())
        self.assertEqual(self._xml(hold=[[], []]), plain)
        self.assertNotIn("<voice>3</voice>", plain)
        self.assertNotIn("<voice>4</voice>", plain)
        self.assertEqual(plain.count("<backup>"), 2)     # one per measure


class TestHoldPayload(unittest.TestCase):
    """Ticket 04 -- the additive ``hold`` target field (v2 only)."""

    def _payload(self, **params):
        base = {"phrase": [[2, 3, 4, 5], [5, 4, 3, 2]],
                "note_value": "quarter", "hold": [[1], []]}
        base.update(params)
        return build_lab_payload(compile_lab(_spec(parameters=base)))

    def test_v1_targets_carry_no_hold_key(self):
        for t in self._payload()["TARGET_CHORDS"]:
            self.assertNotIn("hold", t)

    def test_v2_hold_measure_names_its_pitch_class(self):
        targets = self._payload(hold_graded=True)["TARGET_CHORDS"]
        self.assertEqual(targets[0]["hold"], {"pc": 0})
        self.assertNotIn("hold", targets[1])

    def test_hold_never_enters_the_expected_map(self):
        # v1 and v2 alike: the ordered walk stays the moving line.
        for graded in (False, True):
            payload = self._payload(hold_graded=graded)
            self.assertEqual(payload["EXPECTED_MIDI_BY_MEASURE_OR_BEAT"]["0"],
                             {"1": [2], "2": [4], "3": [5], "4": [7]})
            self.assertEqual(payload["TARGET_CHORDS"][0]["pitchClasses"],
                             [2, 4, 5, 7])

    def test_hold_midi_listed_for_the_pitch_map(self):
        t = self._payload()["TARGET_CHORDS"][0]
        self.assertIn(60, t["midiPitches"])          # the engraved C4 hold


class TestEchoIneligibility(unittest.TestCase):
    def test_technique_is_not_echo_eligible(self):
        self.assertFalse(is_echo_eligible(_spec()))


class TestCurriculumTracer(unittest.TestCase):
    """The cat:technique category + the one tracer leaf, wired end to end."""

    @classmethod
    def setUpClass(cls):
        from harmony.curriculum import build_curriculum
        cls.root = build_curriculum()

    def test_category_present(self):
        node = self.root.find("cat:technique")
        self.assertIsNotNone(node)
        self.assertEqual(node.title, "Piano Technique")
        self.assertFalse(node.reserved)

    def test_tracer_leaf_launchable(self):
        leaf = self.root.find(TRACER_LEAF)
        self.assertIsNotNone(leaf)
        self.assertEqual(leaf.kind, "exercise")
        spec = leaf.lab_spec
        self.assertEqual(spec.concept, "technique")
        spec.validate()
        exp = compile_lab(spec)                       # curriculum -> lab compile
        self.assertEqual(len(exp.measures), 2)
        build_lab_musicxml(exp)                        # -> render
        payload = build_lab_payload(exp)               # -> ordered MIDI grading
        self.assertEqual(payload["render"], "arpeggio")

    def test_tracer_leaf_has_no_echo_button(self):
        # the JS gates the 🎧 button on the payload's echoEligible flag
        leaf = self.root.find(TRACER_LEAF)
        self.assertFalse(is_echo_eligible(leaf.lab_spec))
        self.assertFalse(leaf.to_payload()["echoEligible"])

    def test_tracer_leaf_renders_its_fingering(self):
        # the shipped warm-up carries fingering params; ticket 02 makes the
        # numerals real notation instead of guide text only.
        leaf = self.root.find(TRACER_LEAF)
        xml = build_lab_musicxml(compile_lab(leaf.lab_spec))
        self.assertIn("<technical><fingering>1</fingering></technical>", xml)

    def test_tracer_coach_line_shown_in_description(self):
        leaf = self.root.find(TRACER_LEAF)
        self.assertIn("wrist", leaf.description)

    def test_leaf_page_has_theory_and_advice(self):
        from harmony.curriculum_explanations import exercise_page
        leaf = self.root.find(TRACER_LEAF)
        page = exercise_page(leaf)
        self.assertTrue(page["musicTheory"].strip())
        self.assertTrue(page["practiceAdvice"])
        self.assertTrue(page["commonMistakes"])

    def test_objective_and_keywords_not_blank(self):
        leaf = self.root.find(TRACER_LEAF)
        self.assertTrue(leaf.learning_objective.strip())
        self.assertIn("technique", leaf.keywords)

    def test_progress_service_records_completion(self):
        import tempfile
        from pathlib import Path
        from harmony.progress_service import ProgressService
        with tempfile.TemporaryDirectory() as td:
            svc = ProgressService(curriculum_path=Path(td) / "cur.json",
                                  journey_path=Path(td) / "journey.json")
            svc.started(TRACER_LEAF, "2026-08-08T00:00:00+00:00")
            rec = svc.record(TRACER_LEAF, accuracy=1.0,
                             timestamp="2026-08-08T00:01:00+00:00")
            self.assertIn(rec.state, ("completed", "mastered"))
            self.assertIs(svc.progress.get(TRACER_LEAF), rec)


class TestConceptExplanation(unittest.TestCase):
    """The honest theory page (what technique drills grade and cannot)."""

    def test_explanation_registered_with_required_fields(self):
        from harmony.lab_explanations import (
            get_concept_explanation, _REQUIRED_CONCEPT_FIELDS)
        page = get_concept_explanation("technique")
        for field in _REQUIRED_CONCEPT_FIELDS:
            self.assertTrue(page[field], field)

    def test_explanation_states_grading_limits(self):
        from harmony.lab_explanations import get_concept_explanation
        page = get_concept_explanation("technique")
        text = " ".join([page["core_idea"]] + page["common_misconceptions"])
        self.assertIn("octave", text.lower())        # octaves indistinguishable
        self.assertIn("order", text.lower())         # the ordered walk

    def test_explanation_states_the_hold_limits(self):
        # ticket 04: the hold check is instant-based (never continuous) and
        # mod-12 (the held octave is not verified) -- said, not hidden.
        from harmony.lab_explanations import get_concept_explanation
        page = get_concept_explanation("technique")
        text = " ".join([page["core_idea"]] + page["common_misconceptions"])
        self.assertIn("hold", text.lower())
        self.assertIn("continuous", text.lower())
        self.assertNotIn("arrives with ticket 04", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
