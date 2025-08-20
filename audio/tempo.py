from music21 import tempo as m21tempo, converter

def build_tempo_segments(self, mxl_path: str):
        from music21 import tempo as m21tempo, converter
        try:
            score = converter.parse(mxl_path)
            highest_ql = float(score.flat.highestTime)

            # Collect one MetronomeMark per unique offset across the full score
            marks = {}
            for mm in score.recurse().getElementsByClass(m21tempo.MetronomeMark):
                try:
                    off = float(mm.getOffsetBySite(score))
                except Exception:
                    off = float(mm.offset or 0.0)
                qpm = float(mm.getQuarterBPM() or 60.0)
                key = round(off, 6)
                if key not in marks:
                    marks[key] = qpm

            items = sorted(marks.items(), key=lambda t: t[0])
            if not items:
                items = [(0.0, 60.0)]
            if items[0][0] > 0.0:
                items.insert(0, (0.0, items[0][1]))

            # Build segments with absolute seconds
            segs = []
            t_sec = 0.0
            for i, (off, bpm) in enumerate(items):
                next_off = items[i + 1][0] if i + 1 < len(items) else highest_ql
                dur_q = max(0.0, (next_off - off))
                end_sec = t_sec + (dur_q * 60.0 / bpm)
                segs.append({
                    "start_ql": off, "end_ql": next_off,
                    "bpm": bpm, "start_sec": t_sec, "end_sec": end_sec
                })
                t_sec = end_sec
            return segs
        except Exception as e:
            print("Tempo parse error:", e)
            return [{"start_ql": 0.0, "end_ql": 1e9, "bpm": 60.0, "start_sec": 0.0, "end_sec": 1e9}]
        
def _bpm_at_seconds(self, sec: float) -> float:
        for s in self.tempo_segments:
            if s["start_sec"] <= sec < s["end_sec"]:
                return s["bpm"]
        return self.tempo_segments[-1]["bpm"] if self.tempo_segments else 60.0
