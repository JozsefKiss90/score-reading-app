from __future__ import annotations

import copy
import math
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple


class VerovioNoteMapper:
    """
    Build mapping: abs_measure -> beat_index(1-based) -> list[{id,pitch,x,y,t_rel}]

    Key design goal:
      - Beat bucketing uses Verovio timing (getTimeForElement)
      - Pitch assignment is *deterministic* across system breaks by using geometry
        (notehead y ordering) within each simultaneous onset cluster.
      - If the SVG contains explicit pitch attributes (data-pname/data-oct/data-accid),
        we will use them (highest confidence) and bypass MusicXML matching for those notes.

    This avoids the classic failure mode where time-only pitch matching depends on SVG DOM order,
    which changes after a system break.
    """

    def __init__(self, toolkit, measures, events_by_index, dlog=print):
        self._tk = toolkit
        self.measures = measures
        self.events_by_index = events_by_index
        self.dlog = dlog

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

        for abs_m in abs_indexes:
            m = self.measures[abs_m]
            beat_times = beat_times_map.get(str(abs_m)) or beat_times_map.get(abs_m) or []
            if not beat_times:
                beat_times = [0.0]

            rows = rows_by_abs.get(abs_m, [])
            note_map[str(abs_m)] = {str(i + 1): [] for i in range(len(beat_times))}

            # Resolve times (ms) for beat bucketing
            times_ms: Dict[str, int] = {}
            min_ms: Optional[int] = None
            for r in rows:
                nid = r["id"]
                try:
                    t = int(self._tk.getTimeForElement(nid))
                except Exception:
                    t = -1
                times_ms[nid] = t
                if t >= 0:
                    min_ms = t if min_ms is None else min(min_ms, t)

            measure_start_ms = min_ms or 0
            # Attach t_rel seconds onto rows
            for r in rows:
                t = times_ms.get(r["id"], -1)
                r["t_rel"] = None if t < 0 else max(0.0, (t - measure_start_ms) / 1000.0)

            # Bucket rows into beats using t_rel
            for r in rows:
                t_rel = r.get("t_rel")
                if t_rel is None:
                    bidx = 1
                else:
                    bidx = self._beat_index_for_t(t_rel, beat_times)
                note_map[str(abs_m)][str(bidx)].append(r)

            # Assign pitches: use explicit SVG pitch if present, else use MusicXML+geometry
            # Make a fresh, per-measure copy of pitch events so "used" flags do not leak across pages.
            events = copy.deepcopy(self.events_by_index[abs_m]) if abs_m < len(self.events_by_index) else []
            for b_str, bucket in note_map[str(abs_m)].items():
                b = int(b_str)
                b0 = beat_times[b - 1] if (b - 1) < len(beat_times) else 0.0
                b1 = beat_times[b] if b < len(beat_times) else float("inf")

                self._assign_pitches_for_bucket(bucket, events, b0, b1)

                # Stable ordering for UI: left->right, then top->bottom
                bucket.sort(key=lambda r: (
                    1e18 if r.get("x") is None else r["x"],
                    1e18 if r.get("y") is None else r["y"],
                ))

                # Debug (kept intentionally verbose)
                print("\n--- VEROVIO NOTE_MAP DEBUG ---")
                print(f"abs_measure={abs_m} beat={b}")
                print("ids:", [r["id"] for r in bucket])
                print("pitches:", [r.get("pitch") for r in bucket])
                print("x:", [r.get("x") for r in bucket])
                print("y:", [r.get("y") for r in bucket])
                print("t_rel:", [r.get("t_rel") for r in bucket])
                print("--- END DEBUG ---\n")

        return note_map

    # --- SVG parsing --------------------------------------------------------

    def _collect_note_rows_by_measure_from_svg(self, page_svg: str, abs_indexes: List[int]) -> Dict[int, List[dict]]:
        """
        For each abs_measure on the page, collect rows:
          {id, x, y, pitch?}
        Pitch is extracted from SVG only if present (optional feature of Verovio output).
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
        measure_groups: List[ET.Element] = []
        for g in root.iter(tag("g")):
            cls = g.attrib.get("class", "")
            typ = g.attrib.get("data-vrv-type") or g.attrib.get("data-type") or ""
            if typ == "measure" or "measure" in cls.split():
                measure_groups.append(g)

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
                pitch = self._read_pitch_from_svg_node(ng, parent, ns)

                rows_by_abs[abs_m].append({
                    "id": nid,
                    "x": x,
                    "y": y,
                    "pitch": pitch,
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
        We keep this conservative: only accept pitch attributes found on the note itself
        or its immediate notehead/stem children, not on generic containers.
        """
        def try_attrs(el: ET.Element) -> Optional[str]:
            for pk, ak, ok in self._PITCH_KEYS:
                pname = el.attrib.get(pk)
                octv = el.attrib.get(ok)
                if not (pname and octv):
                    continue

                acc_raw = el.attrib.get(ak)
                if acc_raw is None:
                    continue
                if str(acc_raw).strip() == "":
                    continue

                return self._format_pitch(pname, acc_raw, octv)
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
        base = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[pc]
        delta = acc.count("#") - acc.count("b")
        semitone = base + delta
        return (octv + 1) * 12 + semitone
