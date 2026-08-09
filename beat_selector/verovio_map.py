from __future__ import annotations

import copy
import math
import re
import xml.etree.ElementTree as ET
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


_STEP_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_SHARP_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

_MEI_NS = "{http://www.music-encoding.org/ns/mei}"
_XML_ID = "{http://www.w3.org/XML/1998/namespace}id"

# MEI @accid / @accid.ges values -> semitone offset from the natural letter.
_MEI_ACCID = {
    "s": 1, "f": -1, "n": 0, "x": 2, "ss": 2, "ff": -2,
    "xs": 3, "sx": 3, "ts": 3, "tf": -3, "nf": -1, "ns": 1,
}

# @dur -> length in quarter notes, before dots.
_MEI_DUR_QUARTERS = {"long": 16.0, "breve": 8.0, "maxima": 32.0}

# Layer children that carry no time of their own.  Anything not listed here and
# not durational is recursed into, so an unrecognised container (beam, tuplet,
# bTrem, graceGrp, ...) still yields its notes.
_MEI_TIMELESS = frozenset({"accid", "artic", "dot", "verse", "syl", "clef",
                           "keySig", "meterSig", "barLine", "label"})
_MEI_DURATIONAL = frozenset({"rest", "space", "mRest", "mSpace", "multiRest"})

# Verovio has to be asked for these before the page is rendered, or they are
# simply absent from the SVG: `measure@n` anchors the page -> measure mapping,
# the `note@*` keys feed the last-resort written-pitch read.
SVG_ADDITIONAL_ATTRIBUTES = (
    "measure@n",
    "note@pname",
    "note@oct",
    "note@pname.ges",
    "note@oct.ges",
    "note@accid",
    "note@accid.ges",
)


def _mei_local(el: ET.Element) -> str:
    return el.tag.split("}")[-1]


def _mei_dur_ppq(el: ET.Element, ppq: int) -> int:
    """Ticks this element occupies, from @dur.ppq or, failing that, @dur + @dots."""
    raw = el.get("dur.ppq")
    if raw is not None:
        try:
            return int(raw)
        except ValueError:
            pass

    dur = (el.get("dur") or "").strip()
    if not dur:
        return 0
    quarters = _MEI_DUR_QUARTERS.get(dur)
    if quarters is None:
        try:
            quarters = 4.0 / float(dur)
        except (ValueError, ZeroDivisionError):
            return 0
    try:
        dots = int(el.get("dots") or 0)
    except ValueError:
        dots = 0
    quarters *= 2.0 - 2.0 ** (-dots)
    return int(round(quarters * ppq))


def read_mei_notes(mei_xml: str) -> Dict[str, dict]:
    """
    Index every note in a Verovio MEI document by its ``xml:id`` — the same id the
    rendered SVG puts on that notehead.

    Returns ``id -> {measure, onset_ql, midi, pitch, grace}``, where ``onset_ql``
    is the notated onset in quarter notes *from the start of its measure*.

    Why parse MEI rather than ask the toolkit per note: Verovio's Python bindings
    that return JSON (``getMIDIValuesForElement``, ``getTimesForElement``,
    ``getElementAttr``, ``getOptions``, ``renderToTimemap``) segfault once PyQt6
    has been imported first.  ``PyQt6/__init__.py`` prepends its ``Qt6/bin`` to
    the DLL search path, that directory ships ``msvcp140.dll`` / ``vcruntime140``,
    and verovio's extension then binds to Qt's C++ runtime instead of the one the
    rest of the process uses — two heaps, one of which frees what the other
    allocated.  The plain ``int``/``std::string`` entry points (``getMEI``,
    ``renderToSVG``, ``getTimeForElement``) are unaffected.  Do not "simplify"
    this back to the per-element JSON calls: it takes the whole app down with no
    Python traceback.
    """
    root = ET.fromstring(mei_xml)

    ppq_by_staff: Dict[Optional[str], int] = {}
    trans_by_staff: Dict[Optional[str], int] = {}
    default_ppq: Optional[int] = None

    for sd in root.iter(_MEI_NS + "scoreDef"):
        raw = sd.get("ppq")
        if raw:
            try:
                default_ppq = int(raw)
            except ValueError:
                pass
    for sd in root.iter(_MEI_NS + "staffDef"):
        n = sd.get("n")
        raw = sd.get("ppq")
        if raw:
            try:
                ppq_by_staff[n] = int(raw)
            except ValueError:
                pass
        raw = sd.get("trans.semi")
        if raw:
            try:
                trans_by_staff[n] = int(raw)
            except ValueError:
                pass

    notes: Dict[str, dict] = {}
    for m_idx, measure in enumerate(root.iter(_MEI_NS + "measure")):
        for staff in measure.iter(_MEI_NS + "staff"):
            n = staff.get("n")
            ppq = ppq_by_staff.get(n) or default_ppq or 1
            trans = trans_by_staff.get(n, 0)
            for layer in staff.iter(_MEI_NS + "layer"):
                # Every layer restarts at the barline (MusicXML's <backup>).
                _mei_walk_layer(layer, 0, m_idx, ppq, trans, notes)

    return notes


def _mei_walk_layer(el: ET.Element, cursor: int, m_idx: int, ppq: int,
                    trans: int, notes: Dict[str, dict]) -> int:
    for child in el:
        tag = _mei_local(child)
        if tag == "note":
            _mei_add_note(child, cursor, m_idx, ppq, trans, notes)
            cursor += _mei_dur_ppq(child, ppq)
        elif tag == "chord":
            span = _mei_dur_ppq(child, ppq)
            for note in child.iter(_MEI_NS + "note"):
                _mei_add_note(note, cursor, m_idx, ppq, trans, notes)
                if not span:
                    span = _mei_dur_ppq(note, ppq)
            cursor += span
        elif tag in _MEI_DURATIONAL:
            cursor += _mei_dur_ppq(child, ppq)
        elif tag in _MEI_TIMELESS:
            continue
        else:
            cursor = _mei_walk_layer(child, cursor, m_idx, ppq, trans, notes)
    return cursor


def _mei_add_note(note: ET.Element, cursor: int, m_idx: int, ppq: int,
                  trans: int, notes: Dict[str, dict]) -> None:
    nid = note.get(_XML_ID)
    if not nid:
        return

    # `.ges` is the sounding value where it differs from the written one (ottava).
    pname = note.get("pname.ges") or note.get("pname")
    octv = note.get("oct.ges")
    if octv in (None, ""):
        octv = note.get("oct")
    step = _STEP_SEMITONES.get(str(pname or "").strip().upper())
    if step is None or octv in (None, ""):
        return
    try:
        octave = int(str(octv).strip())
    except ValueError:
        return

    # A key-signature or carried accidental lands in @accid.ges; a written one
    # becomes a child <accid>.  Either way it is the sounding alteration.
    alter = note.get("accid.ges")
    if alter is None:
        for ch in note:
            if _mei_local(ch) == "accid":
                alter = ch.get("accid.ges") or ch.get("accid")
                break
    if alter is None:
        alter = note.get("accid")
    delta = _MEI_ACCID.get(str(alter or "").strip(), 0)

    midi = (octave + 1) * 12 + step + delta + trans
    if trans:
        # Written spelling is not what sounds; the played pitch is what matters.
        pitch = f"{_SHARP_NAMES[midi % 12]}{midi // 12 - 1}"
    else:
        acc = "#" * delta if delta > 0 else "b" * (-delta)
        pitch = f"{str(pname).strip().upper()}{acc}{octave}"

    notes[nid] = {
        "measure": m_idx,
        "onset_ql": cursor / float(ppq or 1),
        "midi": midi,
        "pitch": pitch,
        "grace": note.get("grace"),
    }


def iter_measure_groups(root: ET.Element) -> Iterable[ET.Element]:
    """Yield the measure <g> elements of a Verovio page, in engraved order."""
    ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
    for g in root.iter(f"{ns}g"):
        typ = g.attrib.get("data-vrv-type") or g.attrib.get("data-type") or ""
        if typ == "measure" or "measure" in g.attrib.get("class", "").split():
            yield g


def map_page_measures_to_indexes(page_svgs: Sequence[str], measures, dlog=print) -> List[List[int]]:
    """
    Map each page's measure groups onto absolute indexes into `measures`.

    Verovio engraves every bar exactly once, in order, so a running count is the
    reliable mapping.  A measure number overrides it only when that number picks
    out exactly one bar: repeats, second endings and pickups all produce
    duplicate numbers, and resolving one of those would point two different bars
    at the same index — which silently merges their noteheads.
    """
    counts: Dict[int, int] = {}
    for m in measures:
        counts[m.number] = counts.get(m.number, 0) + 1
    num_to_abs: Dict[int, int] = {m.number: m.index for m in measures if counts[m.number] == 1}

    last = max(0, len(measures) - 1)
    seq = 0
    pages: List[List[int]] = []

    for svg in page_svgs:
        abs_list: List[int] = []
        try:
            root = ET.fromstring(svg)
            for g in iter_measure_groups(root):
                n_attr = g.attrib.get("n") or g.attrib.get("data-n") or ""
                num = None
                try:
                    if n_attr:
                        num = int(str(n_attr).strip().split()[0])
                except ValueError:
                    num = None

                abs_idx = num_to_abs.get(num, seq) if num is not None else seq
                abs_idx = max(0, min(abs_idx, last))
                abs_list.append(abs_idx)
                seq = abs_idx + 1
        except ET.ParseError as e:
            dlog("[VerovioNoteMapper] SVG parse error:", e)
            count = svg.count('data-vrv-type="measure"') or svg.count('class="measure"') or 1
            abs_list = [max(0, min(seq + i, last)) for i in range(count)]
            seq += count

        pages.append(abs_list)

    return pages


class VerovioNoteMapper:
    """
    Build mapping: abs_measure -> beat_index(1-based) -> list[{id,pitch,x,y,t_rel}]

    Both halves of that mapping come from the MEI Verovio engraved the page from
    (see :func:`read_mei_notes`), keyed by the SVG element id — so the notehead
    the user sees and the pitch the sidebar prints are the same object:

      - pitch is resolved the way Verovio resolves it (key signature, written
        and carried accidentals, ottava, transposition), then spelled the way
        the score writes it: ``Bb4``, not ``A#4``;
      - the onset is the *notated* position in quarter notes into its measure,
        which is what beat bucketing needs, and what a grace note's engraved
        position says even though playback nudges it off the beat.

    Wall-clock seconds are deliberately not used for matching.  Verovio's MIDI
    clock and the app's tempo map do not have to agree: one ``<sound
    tempo="114">`` next to a printed ``quarter = 127`` metronome mark is enough
    to drift a bar's last eighth by ~190 ms, far outside any sane matching
    window.  The old time-window matcher then paired noteheads with the wrong
    pitches and, because it consumed pitch events as it went, the error cascaded
    through the rest of the measure.

    Fallbacks, in order, for a note that is not in the MEI index:
      2. MusicXML pitch events, matched by onset cluster + notehead geometry.
      3. Verovio's ``data-pname``/``data-oct`` SVG attributes.  These carry the
         *written* letter only — no key signature — so they are a last resort.
    """

    def __init__(self, toolkit, measures, events_by_index, dlog=print,
                 debug_beats: bool = False, mei_xml: Optional[str] = None):
        self._tk = toolkit
        self.measures = measures
        self.events_by_index = events_by_index
        self.dlog = dlog
        self.debug_beats = bool(debug_beats)
        self._mei_xml = mei_xml
        self._mei_notes: Optional[Dict[str, dict]] = None

    def mei_notes(self) -> Dict[str, dict]:
        """Notes of the loaded score indexed by SVG/MEI id; read once, then cached."""
        if self._mei_notes is not None:
            return self._mei_notes

        xml = self._mei_xml
        if xml is None:
            try:
                xml = self._tk.getMEI()
            except Exception as e:
                self.dlog("[VerovioNoteMapper] getMEI() failed:", e)
                xml = ""
        try:
            self._mei_notes = read_mei_notes(xml) if xml else {}
        except ET.ParseError as e:
            self.dlog("[VerovioNoteMapper] MEI parse error:", e)
            self._mei_notes = {}

        self.dlog(f"[VerovioNoteMapper] MEI notes indexed: {len(self._mei_notes)}")
        return self._mei_notes

    # translate(x, y) scale(...)
    _RE_TRANSLATE = re.compile(r"translate\(([-0-9.]+)[ ,]+([-0-9.]+)\)")

    # Pitch in SVG, if enabled via verovio's additional-attributes
    _PITCH_KEYS = (
        ("data-pname", "data-accid", "data-oct"),
        ("data-pname.ges", "data-accid.ges", "data-oct.ges"),
        ("pname", "accid", "oct"),
        ("pname.ges", "accid.ges", "oct.ges"),
    )

    # --- Public API ---------------------------------------------------------

    def build_note_map_from_verovio(self, page_svg: str, abs_indexes, beat_times_map) -> dict:
        """Return JSON-serializable mapping for the current page."""
        note_map: dict[str, dict[str, list[dict]]] = {}

        rows_by_abs = self._collect_note_rows_by_measure_from_svg(page_svg, abs_indexes)
        self.dlog(
            f"[VerovioNoteMapper] SVG note-id collection: measures={len(rows_by_abs)} "
            f"totalNotes={sum(len(v) for v in rows_by_abs.values())}"
        )

        mei_notes = self.mei_notes()
        tally = {"mei": 0, "musicxml": 0, "svg": 0, "unresolved": 0}

        # Two measure groups can be clamped onto one index at the end of a score
        # Verovio engraves longer than music21 parsed it; their rows already share
        # one bucket list, so the index is only worth walking once.
        for abs_m in dict.fromkeys(abs_indexes):
            beat_times = beat_times_map.get(str(abs_m)) or beat_times_map.get(abs_m) or []
            if not beat_times:
                beat_times = [0.0]
            n_beats = len(beat_times)

            rows = rows_by_abs.get(abs_m, [])
            note_map[str(abs_m)] = {str(i + 1): [] for i in range(n_beats)}

            step_ql = self._beat_step_ql(abs_m, n_beats)

            # --- Pitch and onset, from the engraved MEI ----------------------
            for r in rows:
                info = mei_notes.get(r["id"])
                if info is None:
                    continue
                r["q_rel"] = float(info["onset_ql"])
                r["pitch"] = info["pitch"]
                r["source"] = "mei"

            # Millisecond fallback anchor, for any notehead the MEI index missed.
            stragglers = [r for r in rows if r.get("q_rel") is None]
            times_ms = {r["id"]: self._toolkit_time_ms(r["id"]) for r in stragglers}
            valid_ms = [t for t in times_ms.values() if t is not None]
            measure_start_ms = min(valid_ms) if valid_ms else 0

            for r in rows:
                q_rel = r.get("q_rel")
                if q_rel is not None:
                    r["t_rel"] = self._q_to_measure_seconds(q_rel, beat_times, step_ql)
                    continue
                t_ms = times_ms.get(r["id"])
                r["t_rel"] = None if t_ms is None else max(0.0, (t_ms - measure_start_ms) / 1000.0)

            # --- Bucket into beats -------------------------------------------
            for r in rows:
                if r.get("q_rel") is not None:
                    bidx = self._beat_index_for_q(r["q_rel"], step_ql, n_beats)
                elif r.get("t_rel") is not None:
                    bidx = self._beat_index_for_t(r["t_rel"], beat_times)
                else:
                    bidx = 1
                note_map[str(abs_m)][str(bidx)].append(r)

            # --- Fallbacks for anything still without a pitch ------------------
            # Make a fresh, per-measure copy of pitch events so "used" flags do not leak across pages.
            events = copy.deepcopy(self.events_by_index[abs_m]) if abs_m < len(self.events_by_index) else []
            self._reserve_events_for_resolved_rows(rows, events)

            for b_str, bucket in note_map[str(abs_m)].items():
                b = int(b_str)
                b0 = beat_times[b - 1] if (b - 1) < len(beat_times) else 0.0
                b1 = beat_times[b] if b < len(beat_times) else float("inf")

                needy = [r for r in bucket if not r.get("pitch")]
                if needy:
                    self._assign_pitches_for_bucket(bucket, events, b0, b1)
                    for r in needy:
                        if r.get("pitch"):
                            r["source"] = "musicxml"
                        elif r.get("svg_pitch"):
                            # Written letter only: no key signature, no carried accidental.
                            r["pitch"] = r["svg_pitch"]
                            r["source"] = "svg"

                # Stable ordering for UI: left->right, then top->bottom
                bucket.sort(key=lambda r: (
                    1e18 if r.get("x") is None else r["x"],
                    1e18 if r.get("y") is None else r["y"],
                ))

                for r in bucket:
                    tally[r.pop("source", None) or "unresolved"] += 1
                    r.pop("svg_pitch", None)
                    r.pop("q_rel", None)

                if self.debug_beats:
                    self.dlog(
                        f"[VerovioNoteMapper] abs_measure={abs_m} beat={b} "
                        f"ids={[r['id'] for r in bucket]} pitches={[r.get('pitch') for r in bucket]} "
                        f"t_rel={[r.get('t_rel') for r in bucket]}"
                    )

        self.dlog(
            f"[VerovioNoteMapper] pitch sources: mei={tally['mei']} "
            f"musicxml={tally['musicxml']} svg={tally['svg']} unresolved={tally['unresolved']}"
        )
        return note_map

    # --- Verovio toolkit queries -------------------------------------------

    def _toolkit_time_ms(self, nid: str) -> Optional[int]:
        """
        Onset in milliseconds on Verovio's own clock.

        This one returns a plain int, so unlike the JSON-returning entry points
        it is safe to call with PyQt6 loaded (see :func:`read_mei_notes`).
        """
        try:
            t = int(self._tk.getTimeForElement(nid))
        except Exception:
            return None
        return t if t >= 0 else None

    # --- SVG parsing --------------------------------------------------------

    def _collect_note_rows_by_measure_from_svg(self, page_svg: str, abs_indexes: List[int]) -> Dict[int, List[dict]]:
        """
        For each abs_measure on the page, collect rows:
          {id, x, y, svg_pitch?}
        `svg_pitch` is only the written letter (see _read_pitch_from_svg_node) and
        is used as a last resort, after the toolkit and the MusicXML events.
        """
        # Parse SVG XML
        try:
            root = ET.fromstring(page_svg)
        except Exception as e:
            self.dlog("[VerovioNoteMapper] ERROR parsing SVG:", e)
            return {}

        # Namespace handling
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"

        def tag(t: str) -> str:
            return f"{ns}{t}"

        # Locate measure groups in visual order
        measure_groups: List[ET.Element] = list(iter_measure_groups(root))

        # Map page measure groups -> abs indexes (provided by caller, in the same order)
        # If counts mismatch, clamp to min length (avoids crashes).
        n = min(len(measure_groups), len(abs_indexes))
        rows_by_abs: Dict[int, List[dict]] = {abs_indexes[i]: [] for i in range(n)}

        # Precompute parent map for upward pitch search
        parent = {}
        for p in root.iter():
            for c in list(p):
                parent[c] = p

        for i in range(n):
            abs_m = abs_indexes[i]
            mg = measure_groups[i]

            # Verovio note groups are typically <g class="note" id="...">
            for ng in mg.iter(tag("g")):
                if "id" not in ng.attrib:
                    continue
                if "note" not in ng.attrib.get("class", "").split():
                    continue

                nid = ng.attrib["id"]
                x, y = self._notehead_xy(ng, ns)
                svg_pitch = self._read_pitch_from_svg_node(ng, parent, ns)

                rows_by_abs[abs_m].append({
                    "id": nid,
                    "x": x,
                    "y": y,
                    "pitch": None,
                    "svg_pitch": svg_pitch,
                })

        return rows_by_abs

    def _notehead_xy(self, note_g: ET.Element, ns_prefix: str) -> Tuple[Optional[float], Optional[float]]:
        """
        Extract an (x, y) anchor for a note from the notehead's <use transform="translate(x,y)...">.
        Returns (None, None) if not found.
        """
        def tag(t: str) -> str:
            return f"{ns_prefix}{t}" if ns_prefix else t

        # Prefer notehead use
        for g in note_g.findall(".//" + tag("g")):
            if g.attrib.get("class") == "notehead":
                for use in g.findall("./" + tag("use")):
                    tr = use.attrib.get("transform", "")
                    m = self._RE_TRANSLATE.search(tr)
                    if m:
                        return float(m.group(1)), float(m.group(2))

        # Fallback: any descendant use with translate
        for use in note_g.findall(".//" + tag("use")):
            tr = use.attrib.get("transform", "")
            m = self._RE_TRANSLATE.search(tr)
            if m:
                return float(m.group(1)), float(m.group(2))

        return None, None

    def _read_pitch_from_svg_node(
        self,
        node: ET.Element,
        parent_map: Dict[ET.Element, ET.Element],
        ns_prefix: str,
    ) -> Optional[str]:
        """
        Attempt to read pitch from SVG attributes (if Verovio was configured to emit them).

        Verovio emits `data-pname`/`data-oct` for every note but only emits an
        accidental attribute when the note carries one: a key-signature sharp
        lives in `@accid.ges`, a written one in a child `<accid>` element, and
        neither survives into these attributes.  So the letter is reliable and
        the accidental is not — which is why this is the last resort, behind the
        toolkit's sounding MIDI and the MusicXML events.
        """
        def try_attrs(el: ET.Element) -> Optional[str]:
            for pk, ak, ok in self._PITCH_KEYS:
                pname = el.attrib.get(pk)
                octv = el.attrib.get(ok)
                if not (pname and octv):
                    continue
                return self._format_pitch(pname, el.attrib.get(ak) or "", octv)
            return None

        # 1) On the note group itself
        p = try_attrs(node)
        if p:
            return p

        # 2) On direct-ish children (notehead/stem/accid)
        if ns_prefix:
            tag_g = f"{ns_prefix}g"
        else:
            tag_g = "g"
        for ch in list(node):
            if ch.tag != tag_g:
                continue
            cls = ch.attrib.get("class", "")
            if cls not in ("notehead", "stem", "accid", "dots", "flag"):
                continue
            p = try_attrs(ch)
            if p:
                return p
            for gg in ch.iter():
                if gg is ch:
                    continue
                p = try_attrs(gg)
                if p:
                    return p

        # 3) Optional: walk up 2 levels if the note is wrapped (chord)
        cur = node
        for _ in range(2):
            par = parent_map.get(cur)
            if par is None:
                break
            cls = par.attrib.get("class", "")
            if "chord" in cls.split():
                p = try_attrs(par)
                if p:
                    return p
            cur = par

        return None

    # --- Pitch assignment using MusicXML events + geometry ------------------

    def _reserve_events_for_resolved_rows(self, rows: List[dict], events: List[dict]) -> None:
        """
        Mark the MusicXML events already spoken for by rows the toolkit resolved.

        The fallback matcher hands out events on a first-unused basis, so without
        this it would re-issue a pitch that a resolved notehead already owns.
        Matching is by MIDI number, not by name: the toolkit spells from the
        score ("Bb4") while the events are spelled with sharps ("A#4").
        """
        for r in rows:
            if not r.get("pitch"):
                continue
            midi = self._pitch_to_midi(r.get("pitch"))
            t = r.get("t_rel")
            best = None
            best_dt = None
            for e in events:
                if e.get("used"):
                    continue
                if self._pitch_to_midi(e.get("pitch")) != midi:
                    continue
                dt = 0.0 if t is None else abs(float(e.get("t_rel", 0.0)) - float(t))
                if best is None or dt < best_dt:
                    best = e
                    best_dt = dt
            if best is not None:
                best["used"] = True

    def _assign_pitches_for_bucket(self, rows: List[dict], events: List[dict], beat_start: float, beat_end: float) -> None:
        """
        Assign r["pitch"] for any row with pitch==None using events in [beat_start, beat_end).
        Deterministic for chords: within each onset cluster, pair notehead y-order with pitch midi-order.
        """
        # If SVG already has pitches for all notes, nothing to do.
        if all(r.get("pitch") for r in rows):
            return

        # Consider events that fall in this beat interval (with small slack)
        slack = 0.03
        cand = [e for e in events if (beat_start - slack) <= float(e.get("t_rel", 0.0)) < (beat_end + slack)]

        # Cluster rows by onset time
        rows_with_t = [r for r in rows if r.get("pitch") is None and r.get("t_rel") is not None]
        rows_no_t = [r for r in rows if r.get("pitch") is None and r.get("t_rel") is None]

        # If we have no timing at all, fall back to "first unused"
        if not rows_with_t:
            for r in rows_no_t:
                p = self._pick_first_unused(cand, events)
                r["pitch"] = p
            return

        row_clusters = self._cluster_by_time(rows_with_t, tol=0.04, get_time=lambda r: float(r["t_rel"]))
        evt_clusters = self._cluster_by_time(cand, tol=0.04, get_time=lambda e: float(e.get("t_rel", 0.0)))

        # For each row-cluster, find nearest event-cluster by time and pair deterministically
        for rc in row_clusters:
            rc_t = sum(float(r["t_rel"]) for r in rc) / max(1, len(rc))
            ec = self._nearest_cluster(evt_clusters, rc_t, max_dt=0.08)

            if not ec:
                # fallback: per-row nearest unused by time
                for r in rc:
                    r["pitch"] = self._pick_nearest_unused_by_time(events, float(r["t_rel"]))
                continue

            # Split rows in this onset by geometry and pair with pitches by midi
            # Sort noteheads top->bottom (smaller y is higher on staff)
            rc_sorted = sorted(rc, key=lambda r: (1e18 if r.get("y") is None else r["y"], 1e18 if r.get("x") is None else r["x"]))
            # Use only unused events in the matching cluster
            ec_unused = [e for e in ec if not e.get("used")]
            if not ec_unused:
                for r in rc_sorted:
                    r["pitch"] = self._pick_nearest_unused_by_time(events, float(r["t_rel"]))
                continue

            ec_sorted = sorted(ec_unused, key=lambda e: -self._pitch_to_midi(e.get("pitch")))

            k = min(len(rc_sorted), len(ec_sorted))
            for i in range(k):
                r = rc_sorted[i]
                e = ec_sorted[i]
                r["pitch"] = e.get("pitch")
                e["used"] = True

            # If counts mismatch, assign remaining rows using nearest unused in-time
            for r in rc_sorted[k:]:
                r["pitch"] = self._pick_nearest_unused_by_time(events, float(r["t_rel"]))

        # Any rows still missing pitch (e.g., no timing) -> fallback
        for r in rows:
            if not r.get("pitch"):
                r["pitch"] = self._pick_first_unused(cand, events)

    def _cluster_by_time(self, items: List, tol: float, get_time) -> List[List]:
        items_sorted = sorted(items, key=get_time)
        clusters: List[List] = []
        cur: List = []
        cur_t: Optional[float] = None
        for it in items_sorted:
            t = float(get_time(it))
            if cur_t is None or abs(t - cur_t) <= tol:
                cur.append(it)
                cur_t = t if cur_t is None else (cur_t + t) / 2.0
            else:
                clusters.append(cur)
                cur = [it]
                cur_t = t
        if cur:
            clusters.append(cur)
        return clusters

    def _nearest_cluster(self, clusters: List[List], t: float, max_dt: float) -> Optional[List]:
        best = None
        best_dt = None
        for c in clusters:
            ct = sum(float(e.get("t_rel", 0.0)) for e in c) / max(1, len(c))
            dt = abs(ct - t)
            if best is None or dt < best_dt:
                best = c
                best_dt = dt
        if best is None or best_dt is None or best_dt > max_dt:
            return None
        return best

    def _pick_nearest_unused_by_time(self, events: List[dict], t: float) -> Optional[str]:
        best = None
        best_dt = None
        for e in events:
            if e.get("used"):
                continue
            et = float(e.get("t_rel", 0.0))
            dt = abs(et - t)
            if best is None or dt < best_dt:
                best = e
                best_dt = dt
        if best is None:
            return None
        best["used"] = True
        return best.get("pitch")

    def _pick_first_unused(self, preferred: List[dict], all_events: List[dict]) -> Optional[str]:
        for e in preferred:
            if not e.get("used"):
                e["used"] = True
                return e.get("pitch")
        for e in all_events:
            if not e.get("used"):
                e["used"] = True
                return e.get("pitch")
        return None

    # --- Helpers ------------------------------------------------------------

    def _beat_step_ql(self, abs_m: int, n_beats: int) -> float:
        """
        Quarter notes per beat in this measure.

        Derived from the same bar length that produced `beat_times`, so the beat
        columns the UI draws and the beat a note lands in cannot drift apart.
        """
        m = self.measures[abs_m] if 0 <= abs_m < len(self.measures) else None

        bar_ql = 0.0
        if m is not None:
            bar_ql = float(m.end_ql) - float(m.start_ql)
        if bar_ql <= 0:
            bar_ql = float(max(1, n_beats))

        return bar_ql / max(1, n_beats)

    def _beat_index_for_q(self, q_rel: float, step_ql: float, n_beats: int) -> int:
        """1-based beat index for an onset given in quarter notes into the measure."""
        if step_ql <= 0:
            return 1
        idx = int(math.floor((q_rel / step_ql) + 1e-6))
        return max(1, min(int(n_beats), idx + 1))

    def _q_to_measure_seconds(self, q_rel: float, beat_times: List[float], step_ql: float) -> Optional[float]:
        """
        Convert an onset in quarter notes into the measure to seconds *on the
        app's tempo map*, by interpolating the beat grid it handed us.

        This keeps the fallback matcher comparing like with like: `events` carry
        seconds from music21's tempo segments, which need not match Verovio's
        MIDI clock.
        """
        if q_rel is None or not beat_times:
            return None
        if step_ql <= 0:
            return float(beat_times[0])

        pos = q_rel / step_ql  # position in beats
        i = int(math.floor(pos))
        if i < 0:
            return float(beat_times[0])
        if i >= len(beat_times) - 1:
            if len(beat_times) < 2:
                return float(beat_times[-1])
            step = max(1e-9, float(beat_times[-1]) - float(beat_times[-2]))
            return float(beat_times[-1]) + (pos - (len(beat_times) - 1)) * step

        a = float(beat_times[i])
        b = float(beat_times[i + 1])
        return a + (b - a) * (pos - i)

    def _beat_index_for_t(self, t_rel: float, beat_times: List[float]) -> int:
        """
        beat_times is a list of beat start offsets (seconds) within the measure, length = beats.
        Return a 1-based beat index.
        """
        if not beat_times:
            return 1
        # Find last beat start <= t_rel
        idx = 0
        for i in range(len(beat_times)):
            if t_rel + 1e-9 >= float(beat_times[i]):
                idx = i
            else:
                break
        return idx + 1

    def _format_pitch(self, pname: str, acc: str, octv: str) -> str:
        p = str(pname).strip().upper()
        o = str(octv).strip()
        a = self._acc_to_ascii(acc)
        return f"{p}{a}{o}"

    def _acc_to_ascii(self, acc: str) -> str:
        a = (acc or "").strip().lower()
        # Common Verovio/MEI encodings
        if a in ("s", "#", "sharp"):
            return "#"
        if a in ("f", "b", "flat"):
            return "b"
        if a in ("n", "nat", "natural", ""):
            return ""
        if a in ("x", "ss", "dblsharp", "double-sharp"):
            return "##"
        if a in ("ff", "dblflat", "double-flat"):
            return "bb"
        # Some exports use "1"/"-1"
        if a == "1":
            return "#"
        if a == "-1":
            return "b"
        return ""  # conservative

    def _pitch_to_midi(self, pitch: Optional[str]) -> int:
        """
        Convert pitch name like 'F#4' or 'Bb3' into MIDI number.
        Unknown pitches return -inf-like value so sorting is stable.
        """
        if not pitch:
            return -10**9
        s = str(pitch).strip()
        m = re.match(r"^([A-Ga-g])([#b]{0,2})(-?\d+)$", s)
        if not m:
            return -10**9
        pc = m.group(1).upper()
        acc = m.group(2)
        octv = int(m.group(3))
        base = _STEP_SEMITONES[pc]
        delta = acc.count("#") - acc.count("b")
        semitone = base + delta
        return (octv + 1) * 12 + semitone
