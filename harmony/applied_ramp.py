"""The applied-chord difficulty ramp (ticket 19 / plan G5c) -- pure content.

Ticket 17 shipped one rung of plan §7's ramp: ``V7/x`` in C major, at fixed
positions, answered by eye.  The plan's ramp has four axes, and three of them
are *content* decisions this module derives (the fourth, visual -> ear, is a
presentation decision that lives in the Lab concept + the trainer):

* **position** -- :func:`applied_progression` places the intruder anywhere in
  a progression it builds around it (the chord before it comes from the key's
  own cushion; the chord after it is always the target, because an applied
  chord that never resolves teaches nothing);
* **key distance** -- :func:`keys_by_fifths_distance` walks outward on the
  circle of fifths, derived from each key's signature rather than a list
  anyone could mis-keep;
* **target set** -- the vocabulary itself comes from
  :func:`~theory.diatonic_harmony.applied_tokens_for_mode` (and its
  :func:`~theory.diatonic_harmony.applied_target_options` view), which now
  spans applied dominants *and* applied leading-tone chords.

:func:`dominant_chain` is the module's other half: the plan's "dominant
chains (V/V/V...) as a circle-of-fifths performance drill", derived by
walking the descending-fifths chain of tonicisations rather than typed out.

Everything here is pure (no Qt, no I/O) and returns Roman-numeral token
lists that :func:`~theory.diatonic_harmony.transpose_degree_pattern` can
render into any key -- the curriculum wraps them into specs.
"""

from __future__ import annotations

from typing import List

from theory.diatonic_harmony import (
    APPLIED_DOMINANT_HEADS,
    build_applied_chord,
    build_seventh_chord,
    exemplar_key,
    generate_diatonic_triads,
    key_signature_fifths,
    parse_applied_token,
    transpose_degree_pattern,
    _canon_mode,
)
from harmony.exercise_spec import (
    DEFAULT_MAJOR_KEYS,
    DEFAULT_MINOR_KEYS,
)


#: Degrees (0-based) the opening cushion draws on, in order: tonic, submediant,
#: subdominant, mediant.  Deliberately no dominant and no leading-tone chord --
#: the cushion's job is to establish the key quietly and then hand over to the
#: intruder, and the tail owns the cadence.
_CUSHION_DEGREES = (0, 5, 3, 2)

#: The most chords a progression may put before the intruder.
MAX_INTRUDER_POSITION = len(_CUSHION_DEGREES)


def _degree_labels(mode: str) -> List[str]:
    """The mode's seven Roman labels, spelled as the engine builds them."""
    mode = _canon_mode(mode)
    return [t.roman for t in generate_diatonic_triads(exemplar_key(mode), mode)]


def applied_progression(token: str, position: int,
                        mode: str = "major") -> List[str]:
    """A diatonic progression with ``token`` as its only chromatic chord.

    ``position`` is the intruder's 0-based index -- the *position axis* of the
    ramp.  The progression is built around it: ``position`` chords of the
    key's cushion open it, the applied chord and its target follow (the
    resolution is not optional -- the spot explanation and the resolve stage
    both promise it), and a cadential tail closes on the tonic::

        applied_progression("V7/V", 2)  -> ["I", "vi", "V7/V", "V", "I"]
        applied_progression("V7/V", 1)  -> ["I", "V7/V", "V", "I"]
        applied_progression("V7/ii", 2) -> ["I", "vi", "V7/ii", "ii", "V", "I"]

    The length therefore follows the position (4-8 chords, always inside the
    one-page cap) instead of padding with repeats.  Every token is spelled in
    ``mode``'s own vocabulary, so a minor progression opens on ``i`` and
    cadences on that mode's dominant.
    """
    parsed = parse_applied_token(token)
    if parsed is None:
        raise ValueError(
            f"{token!r} is not an applied chord token (V/x, V7/x, vii°7/x)")
    target = parsed[1]
    if not 1 <= position <= MAX_INTRUDER_POSITION:
        raise ValueError(
            f"intruder position {position} is out of range: the progression "
            f"opens in the key (position >= 1) and the cushion holds at most "
            f"{MAX_INTRUDER_POSITION} chords")
    labels = _degree_labels(mode)
    tonic, dominant = labels[0], labels[4]
    # The cushion never restates the target (it would blunt the tonicisation
    # by sounding the goal chord before its dominant does).
    cushion = [labels[d] for d in _CUSHION_DEGREES if labels[d] != target]
    if position > len(cushion):
        raise ValueError(
            f"{mode} has no {position}-chord cushion that avoids {target}")
    # The tail is the cadence, minus whatever the target already sounds: after
    # a tonicised dominant, V–I would repeat the target, so ii/IV/vi targets
    # cadence through V and a V target goes straight home.
    tail = [t for t in (dominant, tonic) if t != target]
    return cushion[:position] + [token, target] + tail


def keys_by_fifths_distance(mode: str = "major",
                            max_distance: int = 2) -> List[str]:
    """Practical keys within ``max_distance`` steps of the circle of fifths.

    The *key axis* of the ramp: C, then the one-accidental neighbours (G, F),
    then the two-accidental ones (D, Bb), and so on -- ordered by distance,
    sharp side first inside a ring.  Distance is read off each key's own
    signature (:func:`~theory.diatonic_harmony.key_signature_fifths`), so the
    order can never drift from the notation the learner sees.
    """
    mode = _canon_mode(mode)
    pool = DEFAULT_MAJOR_KEYS if mode == "major" else DEFAULT_MINOR_KEYS
    ranked = []
    for key in pool:
        fifths = key_signature_fifths(key, mode)
        if abs(fifths) > max_distance:
            continue
        # sharp side (positive) before flat side at the same distance
        ranked.append((abs(fifths), 0 if fifths >= 0 else 1, key))
    return [key for _, _, key in sorted(ranked)]


def dominant_chain(depth: int, mode: str = "major") -> List[str]:
    """A chain of ``depth`` dominants, each resolving a fifth into the next.

    The plan's circle-of-fifths performance drill.  The chain is *derived*, not
    typed: the home dominant tonicises the tonic, the chord before it tonicises
    the dominant, and so on around the circle -- each link's target one step
    anticlockwise -- until a degree the engine refuses to tonicise (the
    diminished one) ends it::

        dominant_chain(3) -> ["I", "V7/ii", "V7/V", "V7", "I"]
                             #  C    A7       D7      G7    C

    Every applied chord's *target* is the next chord's root, so the chain is
    heard as a run of leading tones: each dominant is answered by another
    dominant standing where its momentary tonic would be, until the last one
    resolves for real.
    """
    if depth < 1:
        raise ValueError("a dominant chain needs at least one dominant (V7)")
    mode = _canon_mode(mode)
    exemplar = exemplar_key(mode)
    labels = _degree_labels(mode)
    try:
        # The home dominant seventh is the chain's last link; without it (a
        # natural-minor v7 is not a dominant seventh) there is no chain.
        build_seventh_chord("V7", exemplar, mode)
    except ValueError as exc:
        raise ValueError(
            f"{mode} has no dominant seventh to chain into: {exc}") from exc
    chain = ["V7"]
    degree = 0                       # the degree the last link tonicises
    while len(chain) < depth:
        degree = (degree + 4) % 7    # one step anticlockwise on the circle
        token = f"{APPLIED_DOMINANT_HEADS[1]}/{labels[degree]}"
        try:
            build_applied_chord(token, exemplar, mode)
        except ValueError as exc:
            raise ValueError(
                f"the {mode} dominant chain ends at {len(chain)} links: "
                f"{labels[degree]} cannot be tonicised ({exc})") from exc
        chain.insert(0, token)
    return [labels[0]] + chain + [labels[0]]


def chain_label(chain: List[str], key: str, mode: str = "major") -> str:
    """``"C–E7–A7–D7–G7–C"`` — a chain's chord symbols, for titles and prose."""
    return "–".join(c.chord_symbol
                    for c in transpose_degree_pattern(chain, key, mode))
