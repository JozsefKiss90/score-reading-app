"""Tests for the Music Theory Laboratory (harmony.lab_spec / lab / lab_musicxml).

These run headless (no Qt / no display).  They enforce the lab's contract:

  * LabExperimentSpec validates accepted specs and rejects bad ones;
  * to_exercise_specs() compiles to the right HarmonyExerciseSpec(s) -- asserted
    against an engine-verified reference -- and stays within the readability cap;
  * compile_lab() is deterministic and respects the chord-tone invariants
    (inversions keep the upper tones, change only the bass; SATB reports the
    3 reduced triad pitch classes; motives transpose to the verified pitches;
    polyphonic slices imply the declared chord);
  * the lab payload carries the trainer's full target key set + the spec-mandated
    keys, and is MIDI-compatible (block vs ordered-tone arpeggio);
  * MusicXML is well-formed, fills every measure, renders through Verovio, and
    contains every expected pitch class;
  * the Phase-6 ScoreAnalysis contracts map onto Atlas nodes;
  * the lab theory/rendering modules are pure (no PyQt6).

Run from the project root::

    .venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -t .
"""

import os
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from theory.diatonic_harmony import note_pc, parse_pitch_class, LETTER_BASE_PC  # noqa: E402
from harmony.exercise_spec import (  # noqa: E402
    HarmonyExerciseSpec, compile_exercise, MAX_CHORDS_PER_SPEC,
)
from harmony.musicxml_builder import build_trainer_payload  # noqa: E402
from harmony.lab_spec import LabExperimentSpec, SCHEMA_VERSION  # noqa: E402
from harmony.lab import compile_lab, lab_demo_specs  # noqa: E402
from harmony.lab_musicxml import (  # noqa: E402
    build_lab_musicxml, build_lab_payload, build_lab_exercise,
)
from harmony.atlas import (  # noqa: E402
    build_atlas, Atlas, HarmonySlice, CadenceSpan, PolyphonicTexture,
    slice_to_annotation, texture_to_slices, cadence_span_to_spec,
    slices_from_lab_experiment, ScoreAnalysis, triad_id,
)


def _spelled_to_midi(name_oct):
    """'G4' / 'Bb3' / 'F#5' -> MIDI number."""
    m = name_oct
    step = m[0]
    i = 1
    alter = 0
    while i < len(m) and m[i] in "#b":
        alter += 1 if m[i] == "#" else -1
        i += 1
    octave = int(m[i:])
    return (octave + 1) * 12 + LETTER_BASE_PC[step] + alter


def _spelled(note):
    """A LabNote -> 'E4' / 'Bb3' / 'F#5'."""
    acc = "#" * note.alter if note.alter > 0 else "b" * (-note.alter)
    return f"{note.step}{acc}{note.octave}"


def _demo(eid):
    return next(s for s in lab_demo_specs() if s.experiment_id == eid)


# Engine-verified reference (see the design's verified theory table).
_CADENCE_SYMS = {
    ("V", "I"): ["G", "C"],
    ("IV", "I"): ["F", "C"],
    ("V", "vi"): ["G", "Am"],
    ("ii", "V", "I"): ["Dm", "G", "C"],
}
_MOTIVE_1353 = {"C": [0, 4, 7, 4], "G": [7, 11, 2, 11]}        # major
_MOTIVE_1353_AMIN = [9, 0, 4, 0]                                # A natural minor


# ---------------------------------------------------------------------------
class TestLabSpecValidation(unittest.TestCase):
    def test_each_demo_validates(self):
        for s in lab_demo_specs():
            s.validate()                     # raises on failure
            self.assertEqual(s.schema, SCHEMA_VERSION)

    def test_rejects_unknown_concept(self):
        with self.assertRaises(ValueError):
            LabExperimentSpec("x", "x", concept="quintal").validate()

    def test_rejects_render_incompatible_with_concept(self):
        with self.assertRaises(ValueError):
            LabExperimentSpec("x", "x", concept="motive", render="block",
                              parameters={"degrees": [1, 3]}).validate()

    def test_rejects_out_of_range_key(self):
        with self.assertRaises(ValueError):
            LabExperimentSpec("x", "x", concept="inversion", key="G# major",
                              parameters={"degree": "I"}).validate()

    def test_rejects_bad_inversion_index(self):
        with self.assertRaises(ValueError):
            LabExperimentSpec("x", "x", concept="inversion",
                              parameters={"degree": "I", "inversions": [3]}).validate()

    def test_rejects_motive_degree_out_of_range(self):
        with self.assertRaises(ValueError):
            LabExperimentSpec("x", "x", concept="motive", render="melody",
                              parameters={"degrees": [1, 8 + 7]}).validate()

    def test_rejects_polyphonic_length_mismatch(self):
        with self.assertRaises(ValueError):
            LabExperimentSpec(
                "x", "x", concept="polyphonic_harmony", render="polyphonic",
                parameters={"progression": ["I", "V"], "upper_degrees": [3]}
            ).validate()

    def test_rejects_strict_bass_on_motive(self):
        with self.assertRaises(ValueError):
            LabExperimentSpec("x", "x", concept="motive", render="melody",
                              parameters={"degrees": [1, 3], "strict_bass": True}
                              ).validate()

    def test_to_dict_from_dict_round_trip(self):
        for s in lab_demo_specs():
            again = LabExperimentSpec.from_dict(s.to_dict())
            self.assertEqual(again.experiment_id, s.experiment_id)
            self.assertEqual(again.concept, s.concept)
            self.assertEqual(again.render, s.render)
            self.assertEqual(again.parameters, s.parameters)

    def test_to_dict_stamps_schema(self):
        self.assertEqual(_demo("inv_C_I").to_dict()["schema"], SCHEMA_VERSION)


# ---------------------------------------------------------------------------
class TestToExerciseSpecs(unittest.TestCase):
    def _syms(self, spec):
        es = spec.to_exercise_specs()
        return es, [[c.triad.chord_symbol for c in compile_exercise(s).chords]
                    for s in es]

    def test_inversion_is_single_root_position_chord(self):
        es = _demo("inv_C_I").to_exercise_specs()
        self.assertEqual(len(es), 1)
        self.assertEqual(es[0].drill, "function")
        self.assertEqual(es[0].pattern, ["I"])
        self.assertEqual(es[0].keys, ["C"])
        self.assertEqual(len(compile_exercise(es[0]).chords), 1)

    def test_cadence_chord_symbols_match_reference(self):
        cases = [
            ("cad_V_I_C", ("V", "I")),
            ("cad_IV_I_C", ("IV", "I")),
            ("cad_V_vi_C", ("V", "vi")),
            ("cad_ii_V_I_C", ("ii", "V", "I")),
        ]
        for eid, pat in cases:
            es, syms = self._syms(_demo(eid))
            self.assertEqual(len(es), 1, eid)
            self.assertEqual(syms[0], _CADENCE_SYMS[pat], eid)

    def test_voice_leading_and_cadence_emit_same_drill(self):
        # ii-V-I as concept="voice_leading" still down-compiles to the function drill.
        es = _demo("cad_ii_V_I_C").to_exercise_specs()
        self.assertEqual([c.triad.chord_symbol for c in compile_exercise(es[0]).chords],
                         ["Dm", "G", "C"])

    def test_minor_cadences_match_reference(self):
        cases = {
            "cad_v_i_Am": ["Em", "Am"],
            "cad_iv_v_i_Am": ["Dm", "Em", "Am"],
            "cad_VII_i_Am": ["G", "Am"],
            "cad_i_VI_VII_i_Am": ["Am", "F", "G", "Am"],
        }
        for eid, want in cases.items():
            self.assertEqual(
                [c.triad.chord_symbol
                 for c in compile_exercise(_demo(eid).to_exercise_specs()[0]).chords],
                want, eid)

    def test_chromatic_and_secondary_tokens_rejected(self):
        for pat in (["bII", "I"], ["V/V", "I"], ["#iv", "I"]):
            with self.assertRaises(ValueError, msg=str(pat)):
                LabExperimentSpec("c", "c", concept="cadence", key="C major",
                                  render="block", parameters={"pattern": pat}).validate()

    def test_polyphonic_down_compiles_to_implied_progression(self):
        es = _demo("poly_I_V_I_C").to_exercise_specs()
        self.assertEqual(len(es), 1)
        self.assertEqual([c.triad.chord_symbol for c in compile_exercise(es[0]).chords],
                         ["C", "G", "C"])

    def test_motive_has_no_chord_drill(self):
        self.assertEqual(_demo("motive_1353_major").to_exercise_specs(), [])

    def test_reduction_empty_without_skeleton_and_drill_with(self):
        no_skel = LabExperimentSpec("r", "r", concept="reduction", key="C major")
        self.assertEqual(no_skel.to_exercise_specs(), [])
        with_skel = LabExperimentSpec(
            "r", "r", concept="reduction", key="C major",
            parameters={"skeleton": ["I", "V", "I"]})
        es = with_skel.to_exercise_specs()
        self.assertEqual(len(es), 1)
        self.assertEqual([c.triad.chord_symbol for c in compile_exercise(es[0]).chords],
                         ["C", "G", "C"])

    def test_every_demo_drill_within_cap(self):
        for s in lab_demo_specs():
            for es in s.to_exercise_specs():
                es.validate()
                self.assertLessEqual(len(compile_exercise(es).chords),
                                     MAX_CHORDS_PER_SPEC, es.exercise_id)


# ---------------------------------------------------------------------------
class TestCompileLab(unittest.TestCase):
    def test_deterministic(self):
        for s in lab_demo_specs():
            a, b = compile_lab(s), compile_lab(s)
            self.assertEqual([m.target_pitch_classes for m in a.measures],
                             [m.target_pitch_classes for m in b.measures], s.experiment_id)
            self.assertEqual(build_lab_musicxml(a), build_lab_musicxml(b), s.experiment_id)

    def test_all_demos_within_cap(self):
        for s in lab_demo_specs():
            self.assertLessEqual(len(compile_lab(s)), MAX_CHORDS_PER_SPEC, s.experiment_id)

    def test_reduction_compile_raises(self):
        spec = LabExperimentSpec("r", "r", concept="reduction", key="C major",
                                 parameters={"skeleton": ["I", "V", "I"]})
        with self.assertRaises(NotImplementedError):
            compile_lab(spec)

    # --- Phase 2 acceptance: inversion invariance + changing bass -----------
    def test_inversion_invariant_tones_and_changing_bass(self):
        exp = compile_lab(_demo("inv_C_I"))
        self.assertEqual(len(exp.measures), 3)
        # Same chord tones across all three inversions (invariant).
        for m in exp.measures:
            self.assertEqual(set(m.target_pitch_classes), {0, 4, 7})
            self.assertEqual(m.annotation.atlas_triad_id, triad_id("C", "major", 0))
        # The bass changes C -> E -> G; figured bass 5/3, 6, 6/4.
        self.assertEqual([m.bass_pitch_class for m in exp.measures], [0, 4, 7])
        self.assertEqual([m.annotation.bass_note for m in exp.measures], ["C", "E", "G"])
        self.assertEqual([m.annotation.figured_bass for m in exp.measures],
                         ["5/3", "6", "6/4"])
        self.assertEqual([m.annotation.inversion_label for m in exp.measures],
                         ["root position", "first inversion", "second inversion"])
        # The guide explains what is invariant.
        self.assertIn("invariant", exp.measures[1].annotation.lab_note.lower())

    def test_inversion_bass_note_rendered_on_bass_staff(self):
        exp = compile_lab(_demo("inv_C_I"))
        xml = build_lab_musicxml(exp)
        notes = _notes_by_measure(xml)
        for i, expected_pc in enumerate((0, 4, 7), start=1):  # C, E, G
            bass = [(s, a, o) for (s, a, o, staff, _) in notes[i] if staff == 2]
            self.assertEqual(len(bass), 1)
            s, a, o = bass[0]
            self.assertEqual(_midi(s, a, o) % 12, expected_pc)

    # --- Phase 3 acceptance: SATB voice leading -----------------------------
    def test_satb_reports_three_reduced_pitch_classes(self):
        exp = compile_lab(_demo("cad_V_I_C"))
        for m in exp.measures:
            self.assertEqual(len(m.target_pitch_classes), 3, "reduced triad, not 4 voices")

    def test_satb_no_voice_crossing_and_all_chord_tones(self):
        exp = compile_lab(_demo("cad_ii_V_I_C"))
        for m in exp.measures:
            voices = dict(m.annotation.voices)
            s, a, t, b = (_spelled_to_midi(voices[n])
                          for n in ("soprano", "alto", "tenor", "bass"))
            self.assertTrue(s >= a >= t >= b, (m.index, s, a, t, b))
            chord_pcs = set(m.target_pitch_classes)
            for midi in (s, a, t, b):
                self.assertIn(midi % 12, chord_pcs)

    def test_v_i_voice_leading_annotation(self):
        exp = compile_lab(_demo("cad_V_I_C"))
        tonic_chord = exp.measures[1]                    # the I after V
        self.assertEqual(tonic_chord.annotation.bass_motion, "G → C")
        self.assertEqual(tonic_chord.annotation.common_tones, ("G",))
        self.assertTrue(tonic_chord.annotation.tendency_tones)
        self.assertIn("leading tone", tonic_chord.annotation.tendency_tones[0].lower())

    def test_natural_minor_has_no_leading_tone(self):
        # v-i in A minor: G is the SUBTONIC (whole step), not a leading tone.
        exp = compile_lab(_demo("cad_v_i_Am"))
        tendency = exp.measures[1].annotation.tendency_tones
        self.assertTrue(tendency)
        text = tendency[0].lower()
        self.assertIn("subtonic", text)
        self.assertIn("no leading tone", text)          # explicitly modal, not a LT
        # It must NOT claim a leading-tone resolution (the major-mode phrasing).
        self.assertNotIn("leading tone g", text)
        self.assertNotIn("leading tone →", text)

    def test_deceptive_cadence_resolves_leading_tone_to_tonic(self):
        # V-vi: the leading tone B resolves UP to C (the tonic), not to A (vi root).
        exp = compile_lab(_demo("cad_V_vi_C"))
        tendency = exp.measures[1].annotation.tendency_tones
        self.assertTrue(tendency)
        text = tendency[0]
        self.assertIn("B → C", text)                     # to the tonic, not "B → A"
        self.assertNotIn("B → A", text)
        self.assertIn("deceptive", text.lower())

    # --- Phase 4 acceptance: motive transposition ---------------------------
    def test_motive_transposed_pitch_classes_major(self):
        exp = compile_lab(_demo("motive_1353_major"))
        self.assertEqual(len(exp.measures), 12)
        by_tonic = {m.tonic: list(m.target_pitch_classes) for m in exp.measures}
        self.assertEqual(by_tonic["C"], _MOTIVE_1353["C"])
        self.assertEqual(by_tonic["G"], _MOTIVE_1353["G"])

    def test_motive_transposed_pitch_classes_minor(self):
        spec = LabExperimentSpec(
            "m", "m", concept="motive", mode="natural_minor", key="A minor",
            render="melody", parameters={"degrees": [1, 3, 5, 3], "keys": ["A"]})
        exp = compile_lab(spec)
        self.assertEqual(list(exp.measures[0].target_pitch_classes), _MOTIVE_1353_AMIN)

    # --- Phase 5 acceptance: polyphonic implied harmony ---------------------
    def test_polyphonic_two_voices_imply_chord(self):
        exp = compile_lab(_demo("poly_I_V_I_C"))
        self.assertEqual(len(exp.measures), 3)
        for m, roman in zip(exp.measures, ("I", "V", "I")):
            self.assertEqual(len(m.staff1), 1)           # one upper voice
            self.assertEqual(len([n for n in m.staff2 if not n.is_rest]), 1)  # one bass
            self.assertEqual(m.annotation.implied_roman, roman)
            # The two sounding voices belong to the implied triad.
            self.assertEqual(m.annotation.atlas_triad_id,
                             triad_id("C", "major", 0 if roman == "I" else 4))

    def test_polyphonic_voices_match_verified_reference(self):
        # Octave-exact match to the engine-verified reference (regression for the
        # upper voice drifting an octave high per scale degree).
        def voices(eid):
            exp = compile_lab(_demo(eid))
            return [(_spelled(m.staff1[0]),
                     _spelled([n for n in m.staff2 if not n.is_rest][0]))
                    for m in exp.measures]
        self.assertEqual(voices("poly_I_V_I_C"),
                         [("E4", "C3"), ("D4", "G3"), ("E4", "C3")])
        self.assertEqual(voices("poly_ii_V_I_C"),
                         [("F4", "D3"), ("B3", "G3"), ("E4", "C3")])
        self.assertEqual(voices("poly_i_VII_i_Am"),
                         [("C4", "A3"), ("D4", "G3"), ("E4", "A3")])


# ---------------------------------------------------------------------------
class TestLabPayload(unittest.TestCase):
    def setUp(self):
        # A trainer target's exact key set, to assert parity against.
        ref = build_trainer_payload(compile_exercise(HarmonyExerciseSpec(
            exercise_id="r", title="r", drill="full_key", mode="major", key="C major")))
        self.ref_keys = set(ref["TARGET_CHORDS"][0].keys())

    def test_top_level_mandated_keys(self):
        payload = build_lab_payload(compile_lab(_demo("inv_C_I")))
        for k in ("TRAINER_MODE", "TARGET_CHORDS", "TARGET_BY_MEASURE",
                  "EXPECTED_MIDI_BY_MEASURE_OR_BEAT"):
            self.assertIn(k, payload)
        self.assertTrue(payload["TRAINER_MODE"])

    def test_every_target_superset_of_trainer_keys(self):
        for s in lab_demo_specs():
            payload = build_lab_payload(compile_lab(s))
            for t in payload["TARGET_CHORDS"]:
                self.assertTrue(self.ref_keys.issubset(set(t.keys())),
                                (s.experiment_id, self.ref_keys - set(t.keys())))

    def test_block_inversion_expected_is_pc_list(self):
        payload = build_lab_payload(compile_lab(_demo("inv_C_I")))
        for k in ("0", "1", "2"):
            self.assertEqual(sorted(payload["EXPECTED_MIDI_BY_MEASURE_OR_BEAT"][k]),
                             [0, 4, 7])
            self.assertEqual(payload["TARGET_BY_MEASURE"][k]["render"], "block")

    def test_strict_bass_inversion_is_ordered_bass_first(self):
        spec = LabExperimentSpec(
            "s", "s", concept="inversion", key="C major", render="block",
            parameters={"degree": "I", "inversions": [1], "strict_bass": True})
        payload = build_lab_payload(compile_lab(spec))
        t = payload["TARGET_CHORDS"][0]
        self.assertEqual(t["render"], "arpeggio")        # reuses the ordered branch
        # The JS validator reads pitchClasses (not EXPECTED_MIDI), so the bass-first
        # order MUST be in pitchClasses[0] == bassPitchClass (regression for the
        # bug where it lived only in EXPECTED_MIDI).
        self.assertEqual(t["pitchClasses"][0], t["bassPitchClass"])
        self.assertEqual(t["pitchClasses"], [4, 0, 7])   # E (bass) first, then C, G
        expected = payload["EXPECTED_MIDI_BY_MEASURE_OR_BEAT"]["0"]
        self.assertEqual(expected["1"], [4])             # bass E (pc 4) first
        self.assertEqual(set(expected["1"] + expected["2"] + expected["3"]), {0, 4, 7})

    def test_strict_bass_rejected_with_arpeggio(self):
        with self.assertRaises(ValueError):
            LabExperimentSpec(
                "s", "s", concept="inversion", key="C major", render="arpeggio",
                parameters={"degree": "I", "strict_bass": True}).validate()

    def test_motive_expected_is_per_beat(self):
        payload = build_lab_payload(compile_lab(_demo("motive_1353_major")))
        self.assertEqual(payload["EXPECTED_MIDI_BY_MEASURE_OR_BEAT"]["0"],
                         {"1": [0], "2": [4], "3": [7], "4": [4]})

    def test_satb_payload_pitch_classes_are_three(self):
        payload = build_lab_payload(compile_lab(_demo("cad_V_I_C")))
        for t in payload["TARGET_CHORDS"]:
            self.assertEqual(len(t["pitchClasses"]), 3)


# ---------------------------------------------------------------------------
_STEP_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _midi(step, alter, octave):
    return (octave + 1) * 12 + _STEP_PC[step] + alter


def _notes_by_measure(xml):
    root = ET.fromstring(xml)
    out = {}
    for measure in root.iter("measure"):
        num = int(measure.attrib["number"])
        notes = []
        for note in measure.findall("note"):
            pitch = note.find("pitch")
            if pitch is None:
                continue
            step = pitch.findtext("step")
            alter = int(pitch.findtext("alter") or 0)
            octave = int(pitch.findtext("octave"))
            staff = int(note.findtext("staff") or 1)
            is_chord = note.find("chord") is not None
            notes.append((step, alter, octave, staff, is_chord))
        out[num] = notes
    return out


class TestLabMusicXml(unittest.TestCase):
    def test_all_demos_well_formed(self):
        for s in lab_demo_specs():
            xml = build_lab_musicxml(compile_lab(s))
            root = ET.fromstring(xml)                    # raises if malformed
            self.assertEqual(len(list(root.iter("measure"))), len(compile_lab(s)))

    def test_each_staff_fills_the_measure(self):
        for s in lab_demo_specs():
            root = ET.fromstring(build_lab_musicxml(compile_lab(s)))
            for measure in root.iter("measure"):
                s1 = s2 = 0
                for note in measure.findall("note"):
                    if note.find("chord") is not None:
                        continue
                    dur = int(note.findtext("duration"))
                    if int(note.findtext("staff") or 1) == 1:
                        s1 += dur
                    else:
                        s2 += dur
                self.assertEqual(s1, 64, (s.experiment_id, measure.attrib["number"]))
                self.assertEqual(s2, 64, (s.experiment_id, measure.attrib["number"]))

    def test_every_target_pc_is_rendered(self):
        for s in lab_demo_specs():
            exp = compile_lab(s)
            xml = build_lab_musicxml(exp)
            payload = build_lab_payload(exp)
            notes = _notes_by_measure(xml)
            for t in payload["TARGET_CHORDS"]:
                rendered = {_midi(st, al, oc) % 12
                            for (st, al, oc, _, _) in notes[t["absMeasure"] + 1]}
                for pc in t["pitchClasses"]:
                    self.assertIn(pc % 12, rendered, (s.experiment_id, t["absMeasure"]))

    def test_motive_key_signature_changes_per_key(self):
        root = ET.fromstring(build_lab_musicxml(compile_lab(_demo("motive_1353_major"))))
        fifths = []
        for measure in root.iter("measure"):
            ks = measure.find(".//key/fifths")
            if ks is not None:
                fifths.append(int(ks.text))
        # 12 distinct key signatures across the 12 major keys.
        self.assertEqual(len(fifths), 12)

    def test_verovio_renders_each_render_type(self):
        try:
            import verovio
        except Exception as e:  # pragma: no cover
            self.skipTest(f"verovio not available: {e}")
        tk = verovio.toolkit()
        for eid in ("inv_C_I", "inv_C_V_arp", "cad_V_I_C", "cad_i_VI_VII_i_Am",
                    "motive_1353_major", "poly_I_V_I_C"):
            xml = build_lab_musicxml(compile_lab(_demo(eid)))
            self.assertTrue(tk.loadData(xml), f"verovio failed to load {eid}")
            svg = tk.renderToSVG(1)
            self.assertIn("<svg", svg)
            self.assertIn("note", svg)


# ---------------------------------------------------------------------------
class TestAtlasPhase6(unittest.TestCase):
    def setUp(self):
        self.atlas = build_atlas()

    def test_slice_maps_to_triad_node(self):
        sl = HarmonySlice(measure=1, key="G major", mode="major", roman="V")
        self.assertEqual(self.atlas.node_for_annotation(slice_to_annotation(sl)),
                         triad_id("G", "major", 4))

    def test_texture_to_slices_identifies_chords(self):
        tex = PolyphonicTexture(
            voices=[["G3", "C4"], ["E4", "E4"], ["C5", "G4"]],
            key="C major", mode="major")
        slices = texture_to_slices(tex)
        self.assertEqual(len(slices), 2)
        self.assertEqual(slices[0].roman, "I")

    def test_cadence_span_to_spec_is_playable(self):
        span = CadenceSpan(start_measure=1, end_measure=2, key="C major",
                           mode="major", pattern=["ii", "V", "I"])
        spec = cadence_span_to_spec(span)
        spec.validate()
        self.assertEqual([c.triad.chord_symbol for c in compile_exercise(spec).chords],
                         ["Dm", "G", "C"])
        self.assertLessEqual(len(compile_exercise(spec).chords), MAX_CHORDS_PER_SPEC)

    def test_synthetic_slices_resolve_to_recorded_nodes(self):
        exp = compile_lab(_demo("poly_ii_V_I_C"))
        slices = slices_from_lab_experiment(exp)
        self.assertEqual(len(slices), len(exp.measures))
        for sl, m in zip(slices, exp.measures):
            self.assertEqual(self.atlas.node_for_annotation(slice_to_annotation(sl)),
                             m.annotation.atlas_triad_id)

    def test_reserved_methods_raise(self):
        sa = ScoreAnalysis()
        for method in ("extract_textures", "extract_cadence_spans"):
            with self.assertRaises(NotImplementedError):
                getattr(sa, method)("dummy.musicxml")

    def test_atlas_unchanged_by_extension(self):
        # Regression guard: the Phase-6 extension adds NO ontology node and stays
        # deterministic (node counts / ids must match a freshly built Atlas).
        a, b = Atlas(), Atlas()
        self.assertEqual(list(a.nodes.keys()), list(b.nodes.keys()))
        kinds = {}
        for n in a.nodes.values():
            kinds[n.kind] = kinds.get(n.kind, 0) + 1
        self.assertEqual(kinds["scale"], 24)
        self.assertEqual(kinds["triad"], 24 * 7)
        self.assertEqual(kinds["degree"], 14)


# ---------------------------------------------------------------------------
class TestPurity(unittest.TestCase):
    def test_lab_modules_do_not_import_pyqt(self):
        code = (
            "import harmony.lab_spec, harmony.lab, harmony.lab_musicxml, sys; "
            "bad=[m for m in sys.modules if m.split('.')[0] in "
            "('PyQt6','verovio')]; "
            "assert not bad, bad; print('pure')")
        r = subprocess.run([sys.executable, "-c", code], cwd=PROJECT_ROOT,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("pure", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
