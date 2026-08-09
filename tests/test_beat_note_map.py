"""Tests for the beat selector's notehead -> pitch mapping (beat_selector/verovio_map.py).

Two invariants:

1. Every notehead the page draws is labelled with the pitch the score actually
   notates, under the beat it is engraved in.  Pitches used to be matched to
   noteheads by comparing Verovio's millisecond clock against music21's tempo
   map -- two timelines that a single ``<sound tempo>`` disagreeing with the
   printed metronome mark is enough to pull apart, after which the Handel
   Passacaglia mislabelled 89% of its notes (A3 shown where the score has C4).

2. The mapper reads the score through ``getMEI()`` and never through Verovio's
   JSON-returning bindings.  Those segfault the whole process, with no Python
   traceback, once PyQt6 has been imported first -- which the app always does.
"""

import re
import unittest
from pathlib import Path

import verovio

from beat_selector.timing import (
    Measure,
    build_beats_by_measure,
    build_pitch_events_by_measure,
)
from beat_selector.verovio_map import (
    SVG_ADDITIONAL_ATTRIBUTES,
    VerovioNoteMapper,
    map_page_measures_to_indexes,
    read_mei_notes,
)
from model.score_loader import (
    build_measure_times,
    build_tempo_segments,
    load_notes_from_mxl,
)

RESOURCES = Path(__file__).resolve().parents[1] / "resources"

# ``<sound tempo="114">`` next to a printed quarter = 127, no key signature.
PASSACAGLIA = RESOURCES / "passacaglia-georg-friedrich-handel-arranged-by-alexander-motovilov.mxl"
# Anacrusis (numbered 0) plus dense chromatic accidentals.
PICKUP_SCORE = RESOURCES / "chopin-prelude-in-e-minor-opus-28-no-4.mxl"
# Carries <harmony> chord symbols, which are not sounding notes.
CHORD_SYMBOL_SCORE = RESOURCES / "the-well-tempered-clavier-book-1-prelude-1-in-c-major-by-johann-sebastian-bach.mxl"

_PITCH_RE = re.compile(r"^([A-G])([#b]{0,2})(-?\d+)$")
_STEPS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def pitch_to_midi(name):
    m = _PITCH_RE.match(name or "")
    if not m:
        return None
    return (int(m.group(3)) + 1) * 12 + _STEPS[m.group(1)] \
        + m.group(2).count("#") - m.group(2).count("b")


class Rendered:
    """One score taken through the same steps ScoreViewBeats takes."""

    def __init__(self, path):
        self.path = str(path)
        self.tk = verovio.toolkit()
        self.tk.setOptions({
            "pageHeight": 1800,
            "pageWidth": 1200,
            "scale": 40,
            "breaks": "auto",
            "adjustPageHeight": 1,
            "svgViewBox": 1,
            "svgAdditionalAttribute": list(SVG_ADDITIONAL_ATTRIBUTES),
        })
        self.tk.loadFile(self.path)
        self.tk.redoLayout()
        self.mei = self.tk.getMEI()

        segments = build_tempo_segments(self.path)
        self.measures = [
            Measure(i, int(m["number"]), float(m["start_ql"]), float(m["end_ql"]),
                    float(m["start_sec"]), float(m["end_sec"]))
            for i, m in enumerate(build_measure_times(self.path))
        ]
        self.beats = build_beats_by_measure(self.measures, segments)
        self.events = build_pitch_events_by_measure(self.measures, segments, self.path, self.path)

        self.page_svgs = [self.tk.renderToSVG(p + 1) for p in range(self.tk.getPageCount())]
        self.page_abs = map_page_measures_to_indexes(self.page_svgs, self.measures, dlog=lambda *a: None)

        self.note_map = self.run(VerovioNoteMapper(
            self.tk, self.measures, self.events, dlog=lambda *a: None,
        ))

    def run(self, mapper):
        out = {}
        for svg, abs_list in zip(self.page_svgs, self.page_abs):
            out.update(mapper.build_note_map_from_verovio(
                svg, abs_list, {i: self.beats[i] for i in abs_list if i < len(self.beats)},
            ))
        return out

    def by_beat(self, note_map=None):
        """(measure, beat) -> sorted list of MIDI numbers."""
        note_map = self.note_map if note_map is None else note_map
        out = {}
        for abs_m, by_beat in note_map.items():
            for beat, rows in by_beat.items():
                out[(int(abs_m), int(beat))] = sorted(pitch_to_midi(r.get("pitch")) for r in rows)
        return out

    def music21_by_beat(self):
        """The same shape, straight from the MusicXML -- an independent oracle."""
        starts = [m.start_ql for m in self.measures]
        out = {}
        for note in load_notes_from_mxl(self.path, self.path)[0]:
            q = float(note["start"])
            i = max(0, sum(1 for s in starts if s <= q) - 1)
            m = self.measures[i]
            n_beats = max(1, len(self.beats[i]))
            step = (m.end_ql - m.start_ql) / n_beats
            beat = max(1, min(n_beats, int((q - m.start_ql) / step + 1e-6) + 1))
            out.setdefault((i, beat), []).append(int(note["pitch"]))
        return {k: sorted(v) for k, v in out.items()}

    def pitches(self, abs_m, beat):
        return [r.get("pitch") for r in self.note_map[str(abs_m)][str(beat)]]


class TestNoteMapPitches(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.score = Rendered(PASSACAGLIA)

    def test_every_beat_holds_the_pitches_the_musicxml_notates(self):
        mine, truth = self.score.by_beat(), self.score.music21_by_beat()
        self.assertGreater(sum(len(v) for v in mine.values()), 900, "expected the whole piece")
        self.assertEqual({k: v for k, v in mine.items() if v}, truth)

    def test_opening_bar_matches_the_engraved_arpeggio(self):
        # Bar 1 left hand, straight from the MusicXML: A2 E3 | C4 A3 | E4 C4 | A3 C4.
        self.assertEqual(self.score.pitches(0, 1), ["A2", "E3"])
        self.assertEqual(self.score.pitches(0, 2), ["C4", "A3"])
        self.assertEqual(self.score.pitches(0, 3), ["E4", "C4"])
        self.assertEqual(self.score.pitches(0, 4), ["A3", "C4"])

    def test_every_bar_is_reachable_exactly_once(self):
        flat = [a for page in self.score.page_abs for a in page]
        self.assertEqual(sorted(flat), list(range(len(self.score.measures))))

    def test_rows_keep_the_payload_shape_the_page_expects(self):
        row = self.score.note_map["0"]["1"][0]
        self.assertEqual(sorted(row), ["id", "pitch", "t_rel", "x", "y"])


class TestNoteMapWithPickupAndAccidentals(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.score = Rendered(PICKUP_SCORE)

    def test_anacrusis_does_not_collapse_two_bars_onto_one_index(self):
        flat = [a for page in self.score.page_abs for a in page]
        self.assertEqual(sorted(flat), list(range(len(self.score.measures))))

    def test_pickup_bar_keeps_its_number(self):
        # music21 numbers an anacrusis 0; turning that into 1 would give two bars
        # the same number, and resolving "1" would then be ambiguous.
        self.assertEqual(self.score.measures[0].number, 0)
        self.assertEqual(self.score.measures[1].number, 1)

    def test_accidentals_are_spelled_and_sounded_correctly(self):
        spelled = [r.get("pitch") for by_beat in self.score.note_map.values()
                   for rows in by_beat.values() for r in rows]
        self.assertTrue(any("#" in p or "b" in p for p in spelled),
                        "score should exercise accidentals")
        mine, truth = self.score.by_beat(), self.score.music21_by_beat()
        self.assertEqual({k: v for k, v in mine.items() if v}, truth)


class TestMapperUsesOnlyCrashSafeBindings(unittest.TestCase):
    """
    Verovio's Python bindings that return JSON (getMIDIValuesForElement,
    getTimesForElement, getElementAttr, getOptions, renderToTimemap) segfault
    once PyQt6 has been imported first: PyQt6 puts its Qt6/bin on the DLL search
    path, that directory ships msvcp140/vcruntime140, and verovio's extension
    then binds to Qt's C++ runtime instead of the process's own.  The int- and
    string-returning entry points are unaffected.
    """

    class FakeToolkit:
        FORBIDDEN = ("getMIDIValuesForElement", "getTimesForElement", "getElementAttr",
                     "getOptions", "renderToTimemap", "getExpansionIdsForElement",
                     "getDescriptiveFeatures")

        def __init__(self, mei):
            self._mei = mei

        def getMEI(self):
            return self._mei

        def getTimeForElement(self, xml_id):  # returns int -- safe
            return 0

        def __getattr__(self, name):
            if name in TestMapperUsesOnlyCrashSafeBindings.FakeToolkit.FORBIDDEN:
                raise AssertionError(
                    f"{name}() segfaults the app once PyQt6 is loaded; "
                    "read the score through getMEI() instead"
                )
            raise AttributeError(name)

    @classmethod
    def setUpClass(cls):
        cls.score = Rendered(PASSACAGLIA)

    def test_note_map_is_unchanged_without_the_json_bindings(self):
        fake = self.FakeToolkit(self.score.mei)
        mapper = VerovioNoteMapper(fake, self.score.measures, self.score.events,
                                   dlog=lambda *a: None)
        self.assertEqual(self.score.by_beat(self.score.run(mapper)), self.score.by_beat())

    def test_the_guard_itself_fires(self):
        with self.assertRaises(AssertionError):
            self.FakeToolkit("").getElementAttr("x")


class TestMeiReader(unittest.TestCase):
    """read_mei_notes on a hand-built document -- no toolkit involved."""

    MEI = """<mei xmlns="http://www.music-encoding.org/ns/mei">
      <music><body><mdiv><score>
        <scoreDef><staffGrp>
          <staffDef n="1" ppq="4"/>
          <staffDef n="2" ppq="4" trans.semi="-2"/>
        </staffGrp></scoreDef>
        <section><measure n="1">
          <staff n="1">
            <layer n="1">
              <rest xml:id="rest1" dur.ppq="4" dur="4"/>
              <beam xml:id="beam1">
                <note xml:id="keysig" dur.ppq="2" dur="8" oct="4" pname="f" accid.ges="s"/>
                <note xml:id="written" dur.ppq="2" dur="8" oct="4" pname="g">
                  <accid xml:id="a1" accid="f"/>
                </note>
              </beam>
              <note xml:id="grace1" dur.ppq="0" dur="16" oct="5" pname="c" grace="unacc"/>
              <chord xml:id="chord1" dur.ppq="8" dur="2">
                <note xml:id="chordlo" oct="5" pname="c"/>
                <note xml:id="chordhi" oct="5" pname="e"/>
              </chord>
            </layer>
            <layer n="2">
              <note xml:id="voice2" dur.ppq="16" dur="1" oct="3" pname="a"/>
            </layer>
          </staff>
          <staff n="2">
            <layer n="1">
              <note xml:id="transposed" dur.ppq="16" dur="1" oct="4" pname="d"/>
            </layer>
          </staff>
        </measure>
        <measure n="2">
          <staff n="1"><layer n="1">
            <note xml:id="nextbar" dur.ppq="16" dur="1" oct="4" pname="c"/>
          </layer></staff>
        </measure></section>
      </score></mdiv></body></music></mei>"""

    @classmethod
    def setUpClass(cls):
        cls.notes = read_mei_notes(cls.MEI)

    def test_rest_pushes_the_following_notes(self):
        self.assertEqual(self.notes["keysig"]["onset_ql"], 1.0)
        self.assertEqual(self.notes["written"]["onset_ql"], 1.5)

    def test_key_signature_accidental_is_applied_and_spelled(self):
        self.assertEqual(self.notes["keysig"]["pitch"], "F#4")
        self.assertEqual(self.notes["keysig"]["midi"], 66)

    def test_written_accidental_is_applied_and_spelled_as_notated(self):
        # A child <accid accid="f"> is a flat, and must print Gb4, not F#4.
        self.assertEqual(self.notes["written"]["pitch"], "Gb4")
        self.assertEqual(self.notes["written"]["midi"], 66)

    def test_grace_note_takes_no_time_and_sits_on_its_principal(self):
        self.assertEqual(self.notes["grace1"]["grace"], "unacc")
        self.assertEqual(self.notes["grace1"]["onset_ql"], 2.0)
        self.assertEqual(self.notes["chordlo"]["onset_ql"], 2.0)

    def test_chord_notes_share_one_onset(self):
        self.assertEqual(self.notes["chordlo"]["onset_ql"], self.notes["chordhi"]["onset_ql"])
        self.assertEqual([self.notes["chordlo"]["midi"], self.notes["chordhi"]["midi"]], [72, 76])

    def test_each_layer_restarts_at_the_barline(self):
        self.assertEqual(self.notes["voice2"]["onset_ql"], 0.0)
        self.assertEqual(self.notes["voice2"]["measure"], 0)

    def test_onsets_are_relative_to_their_own_measure(self):
        self.assertEqual(self.notes["nextbar"]["measure"], 1)
        self.assertEqual(self.notes["nextbar"]["onset_ql"], 0.0)

    def test_transposing_staff_reports_sounding_pitch(self):
        self.assertEqual(self.notes["transposed"]["midi"], 60)
        self.assertEqual(self.notes["transposed"]["pitch"], "C4")

    def test_duration_falls_back_to_dur_and_dots(self):
        mei = self.MEI.replace('<note xml:id="nextbar" dur.ppq="16" dur="1"',
                               '<note xml:id="nextbar" dots="1" dur="4"')
        notes = read_mei_notes(mei)
        self.assertEqual(notes["nextbar"]["onset_ql"], 0.0)  # still parses without dur.ppq


class TestPageMeasureMapping(unittest.TestCase):
    """map_page_measures_to_indexes on hand-built SVG, no Verovio needed."""

    @staticmethod
    def measures(numbers):
        return [Measure(i, n, float(i * 4), float(i * 4 + 4), 0.0, 0.0)
                for i, n in enumerate(numbers)]

    @staticmethod
    def page(numbers):
        groups = "".join(f'<g class="measure" data-n="{n}"></g>' for n in numbers)
        return f'<svg xmlns="http://www.w3.org/2000/svg">{groups}</svg>'

    def test_unique_numbers_anchor_the_mapping(self):
        pages = map_page_measures_to_indexes(
            [self.page([1, 2]), self.page([3, 4])], self.measures([1, 2, 3, 4]),
        )
        self.assertEqual(pages, [[0, 1], [2, 3]])

    def test_duplicate_numbers_fall_back_to_engraved_order(self):
        # A repeated bar number must not point two measure groups at one index.
        pages = map_page_measures_to_indexes(
            [self.page([1, 1, 2])], self.measures([1, 1, 2]),
        )
        self.assertEqual(pages, [[0, 1, 2]])

    def test_unnumbered_measures_fall_back_to_engraved_order(self):
        svg = '<svg xmlns="http://www.w3.org/2000/svg">' + '<g class="measure"></g>' * 3 + "</svg>"
        self.assertEqual(map_page_measures_to_indexes([svg], self.measures([1, 2, 3])), [[0, 1, 2]])

    def test_indexes_never_run_past_the_last_measure(self):
        pages = map_page_measures_to_indexes([self.page([1, 2, 3, 4])], self.measures([1, 2]))
        self.assertEqual(pages, [[0, 1, 1, 1]])


class TestScoreLoaderInputs(unittest.TestCase):
    def test_chord_symbols_are_not_loaded_as_notes(self):
        notes, _bpm = load_notes_from_mxl(str(CHORD_SYMBOL_SCORE), str(CHORD_SYMBOL_SCORE))
        self.assertTrue(notes)
        # Chord symbols arrive as zero-length Chords; nobody plays them.
        self.assertEqual([n for n in notes if float(n["duration"]) == 0.0], [])
        # The prelude's opening bar is the C-major arpeggio over a held C4 --
        # the symbol "C" would add a phantom C3/E3/G3 on the downbeat.
        downbeat = sorted(n["pitch"] for n in notes if float(n["start"]) == 0.0)
        self.assertEqual(downbeat, [60])


if __name__ == "__main__":
    unittest.main()
