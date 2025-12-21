from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional


class VerovioNoteMapper:
    def __init__(self, toolkit, measures, events_by_index, dlog=print):
        self._tk = toolkit
        self.measures = measures
        self.events_by_index = events_by_index
        self.dlog = dlog

    def _collect_note_ids_by_measure_from_svg(self, svg: str, abs_indexes: list[int]) -> dict[int, list[str]]:
        out: dict[int, list[str]] = {}
        root = ET.fromstring(svg)

        measure_groups = []
        for g in root.iter():
            if g.tag.split("}")[-1] != "g":
                continue
            cls = g.attrib.get("class", "")
            if "measure" in cls.split() or cls == "measure":
                measure_groups.append(g)

        self.dlog(f"SVG measure groups found = {len(measure_groups)}; abs_indexes on page = {len(abs_indexes)}")

        for k, g in enumerate(measure_groups):
            if k >= len(abs_indexes):
                continue
            abs_m = abs_indexes[k]

            ids: list[str] = []
            for gg in g.iter():
                if gg.tag.split("}")[-1] != "g":
                    continue
                cls2 = gg.attrib.get("class", "")
                if "note" not in cls2.split():
                    continue
                nid = gg.attrib.get("id")
                if nid:
                    ids.append(nid)

            out[abs_m] = ids

        return out

    def build_note_map_from_verovio(self, page_svg: str, abs_indexes, beat_times_map) -> dict:
        """Build mapping: abs_measure -> beat_index(1-based) -> list[{id,pitch,x}].
        Heavy debug logging preserved from v0 for diagnosis.
        """
        note_map: dict[str, dict[str, list[dict]]] = {}

        # Parse current page SVG once and get note IDs per measure
        ids_by_abs = self._collect_note_ids_by_measure_from_svg(page_svg, abs_indexes)
        self.dlog(
            f"SVG note-id collection: measures={len(ids_by_abs)} "
            f"totalNotes={sum(len(v) for v in ids_by_abs.values())}"
        )

        for abs_m in abs_indexes:
            m = self.measures[abs_m]
            beats = beat_times_map.get(abs_m, [])

            # beats[] are already RELATIVE-to-measure (seconds)
            beat_starts_rel = [float(t) for t in beats]
            measure_dur_rel = float(m.end_sec - m.start_sec)
            beat_ends_rel = beat_starts_rel[1:] + [measure_dur_rel]

            note_map[str(abs_m)] = {str(i + 1): [] for i in range(len(beats))}

            ids = ids_by_abs.get(abs_m, [])
            if not ids:
                continue

            # --- Verovio-based measure anchor (ms) ---
            times_ms = []
            bucketed = 0
            pitch_ok = 0
            pitch_miss = 0

            for el_id in ids:
                try:
                    ms = int(self._tk.getTimeForElement(str(el_id)))
                    if ms >= 0:
                        times_ms.append(ms)
                except Exception:
                    pass

            if not times_ms:
                continue

            measure_start_ms = min(times_ms)
            self.dlog(
                f"abs_m={abs_m} measure_start_ms={measure_start_ms} "
                f"t_rel_range={[ (min(times_ms)-measure_start_ms)/1000.0, (max(times_ms)-measure_start_ms)/1000.0 ]} "
                f"beats={beat_starts_rel}"
            )

            # ---- MusicXML pitch events for this measure ----
            events = []
            if self.events_by_index and abs_m < len(self.events_by_index):
                events = self.events_by_index[abs_m]
                for e in events:
                    e["used"] = False

            def pick_pitch(t_rel: float, tol: float = 0.08):
                """Choose nearest unused MusicXML pitch event by measure-relative time."""
                if not events:
                    return None
                best = None
                best_dt = 1e18
                for e in events:
                    if e.get("used", False):
                        continue
                    dt = abs(float(e["t_rel"]) - float(t_rel))
                    if dt < best_dt:
                        best_dt = dt
                        best = e
                if best is not None and best_dt <= tol:
                    best["used"] = True
                    return best["pitch"]
                return None

            # ---- Build beat buckets ----
            for el_id in ids:
                try:
                    ms = int(self._tk.getTimeForElement(str(el_id)))
                except Exception:
                    continue
                if ms < 0:
                    continue

                t_rel = (ms - measure_start_ms) / 1000.0

                b_idx = None
                for i, (bs, be) in enumerate(zip(beat_starts_rel, beat_ends_rel), start=1):
                    if bs - 1e-6 <= t_rel < be - 1e-6:
                        b_idx = i
                        break
                if b_idx is None:
                    continue
                bucketed += 1

                pitch = pick_pitch(t_rel)
                if pitch is None:
                    pitch_miss += 1
                    continue
                pitch_ok += 1

                note_map[str(abs_m)][str(b_idx)].append({"id": el_id, "pitch": pitch, "x": None})

            self.dlog(f"abs_m={abs_m} bucketed={bucketed} pitch_ok={pitch_ok} pitch_miss={pitch_miss}")

            # sort each beat left->right by x (None-safe), then dump debug
            for b in note_map[str(abs_m)].keys():
                rows = note_map[str(abs_m)][b]
                rows.sort(key=lambda r: (1e18 if r.get("x") is None else r["x"]))

                print("\n--- VEROVIO NOTE_MAP DEBUG ---")
                print(f"abs_measure={abs_m} beat={b}")
                print("ids:", [r["id"] for r in rows])
                print("pitches:", [r["pitch"] for r in rows])
                print("x:", [r.get("x") for r in rows])
                print("--- END DEBUG ---\n")


        return note_map
