# 13 — Exercise 9: finger independence (hold one, play four)

**What to build:** The held-note independence study the video calls "amongst the most helpful
exercises there are": in a fixed five-finger position, hold one finger down and play the other
four — then rotate which finger holds. This is the drill where ticket 04's **hold enforcement**
is the whole product: without it, the app cannot tell whether the note stayed down. Host:
**Lab**, `lesson:tech_independence`.

**Blocked by:** 01 — phrase engine; 04 — second voice + hold enforcement (v2 is the point here);
02 — fingering.

**Status:** ready-for-agent

## Content

C major five-finger position (C–G), one measure per held finger:

* Measure for held degree h: hold h (whole note, second voice); voice 1 plays the other four
  degrees ascending as quarters (e.g. hold 3: play 1, 2, 4, 5). Five measures (h = 1..5), then
  five more with the movers **descending** — 10 measures per leaf, inside the cap.
* Fingering labels: the held finger on the whole note, movers on the quarters (finger = degree in
  position).
* **2 leaves:** `ex:tech_independence_<rh|lh>` (LH in bass register, mirrored voices).
* Grading: v1 = movers in order; **v2 = `hold` payload per measure** — a mover step refuses while
  the held pc is absent from the active set (ticket 04 semantics). Ship v1 immediately if 04's v2
  lags; flip the leaves to hold-enforced in the same ticket once available (single checkbox).
* Coach text: "Keep the held key silently depressed to the keybed; play the others clearly —
  harder than it sounds, especially holding 3 or 4" + graded/not-graded (state explicitly whether
  the hold is enforced yet).

## Where

`_tech_independence_specs()` in `harmony/curriculum.py`; pins +2; `tests/test_technique.py`:
measure-per-held-finger structure (movers exclude the held degree), hold payload per measure,
LH register.

- [ ] 10-measure leaves render hold + four movers per measure on the right staves.
- [ ] v2: releasing the hold blocks further movers until re-pressed; guide says which note to hold.
- [ ] Fingering labels correct per measure; pins updated; honesty text present.

## Grading honesty

With v2 this is the rare technique drill whose *physical* demand (the sustained hold) is actually
machine-verified — at note-on instants, mod-12 (per ticket 04's stated limits). Finger choice
remains display-only.
