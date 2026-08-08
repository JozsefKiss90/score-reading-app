# 11 — Exercise 7: trill drills

**What to build:** Finger-pair trills stepping through the scale: measured alternations on
adjacent degrees, climbing an octave, then descending from the top with the alternation inverted,
for each finger pair — hands separate and hands together. Host: **Lab**, `lesson:tech_trills`.

**Blocked by:** 01 — phrase engine; 02 — fingering + 16ths (eighth-note v1 works without 16ths;
fingering is the pair label, wanted).

**Status:** ready-for-agent

## Content

C major. For finger pair (a,b) the measure cell on bottom degree d is the video's
"1-2-3-4 stop": alternate d, d+1 as four 16ths + quarter rest on the stop (with only eighths
available pre-02: 8 straight alternations fill the bar — acceptable v1, tighten to the
stop-pattern when 16ths land).

* **Phrase:** ascending cells d = 1..6, then descending cells starting on the **upper** note
  (alternation d+1, d) for d = 6..1 — 12 measures, exactly the cap.
* **Finger pairs → leaves:** 1-2, 2-3, 3-4, 4-5, hands separate:
  `ex:tech_trill_<12|23|34|45>_<rh|lh>` = 8 leaves. Fingering labels repeat the pair on every
  note (that's the display that matters).
* **Hands together (4 more leaves, v1-capable):** `ex:tech_trill_<pair>_both` — LH mirrors RH an
  octave below with the complementary pair (video: RH 1-2 against LH 5-4), playing the SAME pitch
  classes in unison octaves. The ordered pc walk grades this today (each expected pc is struck by
  both hands; the duplicate note-on is silently ignored — harmless), so no ticket-03 dependency;
  attack-together precision is coach-text ("attack exactly together — don't flam").
* Total **12 leaves**. Coach text: "Push the speed; stop cleanly on the hold" + graded/not-graded.

## Where

`_tech_trill_specs()` in `harmony/curriculum.py`; pair data in `harmony/technique_data.py`; pins
+12; `tests/test_technique.py`: cell construction (alternation + inversion at the top), 12-measure
cap exactness, both-hands leaf targets identical to the RH leaf's pcs.

- [ ] 12 leaves launch/render/grade; descent alternation starts on the upper note.
- [ ] Fingering pair labels render across the cells.
- [ ] Hands-together leaves grade cleanly with double-struck unisons.
- [ ] Pins updated; honesty text present.

## Grading honesty

Trill speed and evenness are the exercise's soul and are ungraded — the note walk verifies the
alternation pattern and the direction flip only. Say it plainly in the leaf text.
