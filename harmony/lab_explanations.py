"""Structured explanation layer for the Music Theory Laboratory.

This is the **pure** prose-assembly layer that turns the lab's structured data
into rich, human-readable explanations for the workspace UI.  It provides three
public entry points (Part 4 of the lab-workspace spec):

* :func:`get_concept_explanation` -- per *concept* theory (a definition, the core
  idea, what to listen / play for, theory terms, Atlas connections, common
  misconceptions, next steps).  This is the one place general theory **prose** is
  allowed to be handwritten.
* :func:`get_experiment_explanation` -- a per *experiment* explanation assembled
  from a compiled :class:`~harmony.lab.LabExperiment` (key, scale, chord tones,
  what stays invariant, what changes, how to practise).
* :func:`get_measure_explanation` -- a per *measure* "Current Mapping" payload
  assembled from one :class:`~harmony.lab.LabMeasure` (Roman, chord, tones, the
  concept-specific fields, and the precomputed Atlas node ids + related edges).

Data-source rule (Part 7): **general theory prose may be handwritten, but every
specific musical fact is derived from the compiled experiment / measure /
annotation (and the Atlas payload), never hand-written per chord.**  So a line
like *"In C major, I is C, built from C-E-G"* is assembled from
``measure.key_display`` / ``annotation.roman`` / ``annotation.chord_symbol`` /
``annotation.chord_tones`` -- there is no hand-written "C major" paragraph.

It is pure (standard library + :mod:`theory.diatonic_harmony` display helpers +
the lab/Atlas dataclasses), so it is unit-testable headlessly and serialises to
JSON for the web UI.  No Qt / Verovio / MIDI.

The concept pages mirror :data:`harmony.lab_spec.CONCEPTS` (``technique``
joined with the piano-technique ticket 01); ``reduction`` /
``real_score_analysis`` is the reserved placeholder (its theory explanation
describes the future Schenkerian-reduction phase and is explicit that it is not
implemented yet).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from theory.diatonic_harmony import _mode_word


# ---------------------------------------------------------------------------
# Concept keys + aliasing
# ---------------------------------------------------------------------------

#: Canonical concept keys for the theory layer.
CONCEPT_KEYS = ["inversion", "voice_leading", "motive", "polyphonic_harmony",
                "reduction", "applied_chord", "technique"]

#: Map every name a caller might pass (spec.concept values, the run-demo concept
#: catalogue selector ids) onto a canonical concept key.
_CONCEPT_ALIASES = {
    "inversion": "inversion",
    "voice_leading": "voice_leading",
    "voice_leading_cadence": "voice_leading",
    "cadence": "voice_leading",
    "motive": "motive",
    "polyphonic_harmony": "polyphonic_harmony",
    "polyphonic": "polyphonic_harmony",
    "reduction": "reduction",
    "real_score_analysis": "reduction",
    "applied_chord": "applied_chord",
    "secondary_dominant": "applied_chord",
    "technique": "technique",
}


def canonical_concept(concept: str) -> str:
    """Map a spec/selector concept name onto a canonical theory key.

    Raises :class:`ValueError` for an unknown concept so a typo never silently
    yields an empty explanation.
    """
    key = _CONCEPT_ALIASES.get((concept or "").strip())
    if key is None:
        raise ValueError(
            f"unknown lab concept {concept!r}; expected one of "
            f"{sorted(set(_CONCEPT_ALIASES))}")
    return key


# ---------------------------------------------------------------------------
# Part 4: concept theory (the only handwritten prose)
# ---------------------------------------------------------------------------

#: Per-concept theory.  Each dict has exactly the required field set: title,
#: short_definition, core_idea, what_to_listen_for[], what_to_play[],
#: theory_terms[], atlas_connections[], common_misconceptions[], next_steps[].
_CONCEPT_EXPLANATIONS: Dict[str, Dict] = {
    "inversion": {
        "title": "Inversions",
        "short_definition": (
            "An inversion changes which chord tone is in the bass; it does not "
            "change which chord it is."),
        "core_idea": (
            "A chord's identity is its set of chord tones and its root, not its "
            "lowest note. Re-stacking the same tones so a different one sits in "
            "the bass gives root position, first inversion, or second inversion "
            "of the very same chord. The bass and the spacing change; the chord "
            "membership and the harmonic function do not."),
        "what_to_listen_for": [
            "The chord still sounds like the same harmony even as the bass moves.",
            "Root position feels the most stable / grounded.",
            "First inversion (third in the bass) feels lighter and more mobile.",
            "Second inversion (fifth in the bass) feels unstable, leaning to resolve.",
        ],
        "what_to_play": [
            "Play all the chord tones in any octave to confirm the harmony.",
            "Then play the required bass note first, then the rest.",
            "Compare the three bass positions back to back and hear the colour change.",
        ],
        "theory_terms": [
            "root position", "first inversion", "second inversion",
            "figured bass (5/3, 6, 6/4)", "bass note", "chord tone", "root",
        ],
        "atlas_connections": [
            "Every inversion maps to the same Atlas triad node (same key, degree).",
            "The triad's quality and interval layer are invariant across inversions.",
            "Its harmonic function usually survives inversion - the cadential 6/4 "
            "is the exception (see below).",
        ],
        "common_misconceptions": [
            "\"C/E is a new chord\" - no, it is still a C major chord, E in the bass.",
            "\"The lowest note is always the root\" - only in root position.",
            "\"Inversion never changes the chord's function\" - usually true, but "
            "in the cadential 6/4 a second-inversion tonic shape over the "
            "dominant's bass behaves as a dominant embellishment, not a tonic.",
        ],
        "next_steps": [
            "Hear how a 6/4 chord wants to resolve: the cadential 6/4 leans onto "
            "the dominant beneath it (a dedicated lesson is coming).",
            "Carry inversions into voice-leading: a smooth bass line uses inversions.",
        ],
    },
    "voice_leading": {
        "title": "Voice-leading cadences",
        "short_definition": (
            "A cadence is directed motion between chords - voices resolving - not "
            "just a pair of chord labels."),
        "core_idea": (
            "Naming chords (V then I) is only the first layer. What makes a "
            "cadence is how the individual voices move: the dominant pulls toward "
            "the tonic, the bass leaps or steps by a characteristic interval, "
            "common tones are held, and tendency tones resolve by step. Triads "
            "give the skeleton; the voice leading gives the gravity. Seventh "
            "chords (a later topic) add an even stronger tendency-tone pull."),
        "what_to_listen_for": [
            "The dominant -> tonic 'arrival' (or its deliberate denial in a deceptive cadence).",
            "The leading tone rising a half step to the tonic (in major).",
            "Common tones that stay put while other voices move.",
            "The bass motion that defines the cadence (e.g. V-I leaps a fourth/fifth).",
        ],
        "what_to_play": [
            "Play each chord of the progression as a block, then connect them.",
            "Hold the common tone between two chords and move only the other voices.",
            "Resolve the leading tone up by step into the tonic chord.",
        ],
        "theory_terms": [
            "cadence", "dominant", "tonic", "leading tone", "tendency tone",
            "common tone", "bass motion", "authentic", "plagal", "half", "deceptive",
        ],
        "atlas_connections": [
            "Each chord is an Atlas degree/triad node; the progression is a path.",
            "The cadence is an Atlas cadence node (its function path is T/S/D motion).",
            "Function colour (tonic / predominant / dominant) drives the sense of arrival.",
        ],
        "common_misconceptions": [
            "\"A cadence is just the last two chords\" - it is how the voices resolve.",
            "\"The leading tone resolves to the next chord's root\" - it resolves to the tonic pitch.",
            "\"Natural minor V-i has a leading tone\" - its v is minor; the 7th is a whole-step subtonic.",
        ],
        "next_steps": [
            "Add the dominant seventh and hear the tritone resolve (a later topic).",
            "Voice a four-part SATB cadence with no parallels (a later topic).",
        ],
    },
    "motive": {
        "title": "Motive transposition",
        "short_definition": (
            "A motive is a pattern of scale degrees; transposing it keeps the "
            "pattern while every absolute pitch changes."),
        "core_idea": (
            "A melodic cell such as 1-3-5-3 is defined by its scale-degree shape, "
            "not by particular pitches. Move it to another key and the absolute "
            "notes all change, but the degree pattern - and therefore the "
            "identity of the motive - is invariant. Traversing keys around the "
            "circle of fifths shows the same shape re-spelled in every key, and "
            "the degree pattern is what a listener recognises."),
        "what_to_listen_for": [
            "The same tune 'shape' in a higher or lower key.",
            "The intervals between notes stay the same even though the notes differ.",
            "How the motive sits against the underlying scale of each key.",
        ],
        "what_to_play": [
            "Play the motive in one key, then the same degrees in the next key.",
            "Follow the circle of fifths and play it in several keys in a row.",
            "Sing the scale-degree numbers while you play to feel the invariant shape.",
        ],
        "theory_terms": [
            "scale degree", "motive", "transposition", "transpositional invariance",
            "interval", "circle of fifths", "absolute pitch vs degree",
        ],
        "atlas_connections": [
            "Each rendering selects a different Atlas scale node (one per key).",
            "The degree pattern is independent of key - the Atlas transposition matrix shows this.",
            "A motive implies, but does not state, the surrounding harmony.",
        ],
        "common_misconceptions": [
            "\"Transposing changes the melody\" - it changes the pitches, not the shape.",
            "\"The motive is a chord\" - it is a melodic degree pattern, not a stacked harmony.",
            "\"Degree 1 is always C\" - degree 1 is the tonic of whichever key you are in.",
        ],
        "next_steps": [
            "Harmonise the motive and hear the same shape over changing chords.",
            "Vary the rhythm while keeping the degree pattern (motivic development).",
        ],
    },
    "polyphonic_harmony": {
        "title": "Polyphonic harmony",
        "short_definition": (
            "Independent melodic voices can imply chords - harmony emerges "
            "horizontally, not only from stacked block chords."),
        "core_idea": (
            "In a contrapuntal texture, no single instant needs to spell a full "
            "chord, yet the simultaneous notes of two or more independent voices "
            "imply a harmony at each vertical slice. A bass line and an upper "
            "voice can together outline a triad and even a harmonic function. "
            "This is why Bach-like two-voice writing is not 'just two melodies' - "
            "it projects a chord progression through line."),
        "what_to_listen_for": [
            "Two independent lines that still suggest a chord at each beat.",
            "The implied root motion in the bass under the upper line.",
            "Moments where the two voices share a chord tone vs outline different ones.",
        ],
        "what_to_play": [
            "Play the bass and the upper voice together; name the chord they imply.",
            "Play each line alone, then together, and hear the harmony appear.",
            "Compare the implied chord to its full block triad.",
        ],
        "theory_terms": [
            "polyphony", "counterpoint", "voice", "vertical slice",
            "implied harmony", "implied function", "two-voice texture",
        ],
        "atlas_connections": [
            "Each vertical slice resolves to an Atlas triad node (the implied chord).",
            "The implied per-measure progression is the same as a block-chord drill.",
            "The function path of the implied chords reads on the Atlas function map.",
        ],
        "common_misconceptions": [
            "\"Two melodies have no harmony\" - their vertical slices imply chords.",
            "\"You need three notes for a chord\" - two voices can imply a full triad.",
            "\"The implied chord is whatever the bass plays\" - both voices define it.",
        ],
        "next_steps": [
            "Add a third voice and complete the implied triads explicitly.",
            "Analyse a real two-part invention's implied harmony (a later topic).",
        ],
    },
    "reduction": {
        "title": "Reduction (reserved)",
        "short_definition": (
            "Reduction strips a passage down to its structural harmonic skeleton "
            "- the load-bearing chords beneath the surface."),
        "core_idea": (
            "Not every chord in a real piece is structurally equal: many are "
            "passing or embellishing motions that prolong a few underlying "
            "harmonies. Reduction exposes that skeleton, showing the long-range "
            "tonal motion behind the surface detail. This is the entry point for "
            "Schenkerian analysis and for analysing real scores (Bach, Mozart). "
            "It is reserved here - the data model and the Atlas score-analysis "
            "contract are shaped for it, but the reduction algorithm is not "
            "implemented yet."),
        "what_to_listen_for": [
            "Which chords feel structural vs which feel like passing decoration.",
            "The long-range tonic-to-dominant-to-tonic arc beneath the surface.",
        ],
        "what_to_play": [
            "(Reserved.) A supplied reduced skeleton can be played as a chord drill.",
        ],
        "theory_terms": [
            "reduction", "structural harmony", "prolongation",
            "Schenkerian analysis", "passing chord", "harmonic skeleton",
        ],
        "atlas_connections": [
            "A reduced skeleton compiles to the same Atlas/trainer chord drill.",
            "Real-score analysis will map each structural chord onto an Atlas node.",
            "Reserved ScoreAnalysis contracts (HarmonySlice / CadenceSpan) feed this.",
        ],
        "common_misconceptions": [
            "\"Every chord matters equally\" - reduction ranks them by structural weight.",
            "\"Reduction is implemented here\" - it is reserved; only a supplied skeleton plays.",
        ],
        "next_steps": [
            "Implement ScoreAnalysis to emit HarmonySlice / CadenceSpan from a score.",
            "Add the reduction algorithm; it slots into the existing contract.",
        ],
    },
    "applied_chord": {
        "title": "Applied chords (secondary dominants)",
        "short_definition": (
            "An applied chord is the dominant-function chord OF another chord: "
            "V7/V is the dominant seventh built on the fifth of the dominant, "
            "vii°7/V the diminished seventh on its leading tone - both briefly "
            "treating that chord as a tonic."),
        "core_idea": (
            "Any major or minor triad can be preceded by its own dominant - a "
            "chord borrowed from the key it would be tonic of - either its "
            "dominant (V/x, V7/x) or its leading-tone seventh (vii°7/x). The "
            "applied chord imports a chromatic tone (the target's leading "
            "tone: F# in C major's V7/V AND its vii°7/V), which is exactly "
            "what makes it audible as an intruder, and its tritone resolves "
            "into the target just as V7 resolves into I. This is tonicisation "
            "- a momentary lean toward another key - not yet modulation: the "
            "home key never actually changes."),
        "what_to_listen_for": [
            "The chromatic tone that does not belong to the home scale.",
            "The extra pull toward the tonicised chord (a dominant in miniature).",
            "The tritone (applied third + seventh) collapsing into the target.",
        ],
        "what_to_play": [
            "Spot: click the one chord of the progression that leaves the key.",
            "Resolve: play the applied chord, then its target, and feel the "
            "leading tone rise by a semitone.",
            "Arpeggiate the applied chord and stop on the chromatic tone.",
            "Ear (🎧): with the notation hidden, click the bar the "
            "chromatic chord sounded in, then name the degree it tonicised.",
            "Chains: play a run of dominants (E7-A7-D7-G7-C) down the circle "
            "of fifths, each one tonicising the next.",
        ],
        "theory_terms": [
            "applied dominant", "secondary dominant", "tonicisation",
            "leading tone", "tritone resolution", "chromaticism",
        ],
        "atlas_connections": [
            "The applied chord claims NO diatonic Atlas node: D7 in C major is "
            "not ii - the base_roman honesty rule keeps it off the graph.",
            "The secondary-dominant network scene (plan G5b) owns the "
            "V7/x -> x edge; the applied leading-tone chords borrow the same "
            "arrow to a target that network already calls tonicisable.",
            "The resolve pair mirrors the circle of fifths: every applied "
            "dominant is one fifths-step of borrowed gravity.",
        ],
        "common_misconceptions": [
            "\"D7 in C major is some kind of ii\" - the chromatic F# disqualifies "
            "it; it is V7/V, the dominant of the dominant.",
            "\"An applied chord changes the key\" - tonicisation is momentary; "
            "modulation (a real key change) is a later topic.",
            "\"Any chromatic chord is an applied chord\" - only chords built "
            "as the dominant (V, V7) or the leading-tone seventh (vii°7) of a "
            "diatonic major/minor triad are.",
            "\"vii°7/V is just a diminished chord\" - it is a FULLY diminished "
            "seventh on the target's leading tone, and it resolves to that "
            "target as firmly as V7/V does.",
        ],
        "next_steps": [
            "Non-chord tones: the other reason a note can sit outside the "
            "chord (G6).",
            "Modulation: what happens when the tonicisation stops being "
            "momentary (G7).",
        ],
    },
    "technique": {
        "title": "Piano technique",
        "short_definition": (
            "A technique drill is a multi-measure melodic phrase in one key "
            "— a finger pattern graded note by note, in order."),
        "core_idea": (
            "Technique lives in the fingers, but the grader lives in MIDI — "
            "so be clear about what each side owns. The phrase engine "
            "compiles a single-key line (a five-finger cell, a scale run, an "
            "arpeggio walk) and grades it as an ordered pitch-class walk: "
            "play the expected steps in order and the walk advances. A step "
            "may demand more than one concurrent key — a dyad, or an octave "
            "doubling (two distinct keys on one pitch class) — checked at "
            "the moment a key goes down, plus one rule on top: at least one "
            "of the step's keys must be struck after the previous step "
            "completed (the re-attack rule), so a held chord never plays "
            "the next step for free. What it cannot hear is just as "
            "important: wrong notes never count against you (no penalty, no "
            "reset — at most a red flash), registers are indistinguishable "
            "(a pitch class matches in any octave), releases never fail you "
            "(letting go just means a two-note step is not yet complete), "
            "and striking exactly together is not measured — two notes "
            "struck well apart but overlapping still pass, because the "
            "grader discards attack timestamps. Legato, tone, dynamics and "
            "steadiness of tempo are not assessed. Those live in the coach "
            "line, which is instruction, never assessment."),
        "what_to_listen_for": [
            "Evenness: every note the same length and weight as its neighbours.",
            "The turnaround (top of the pattern) staying as relaxed as the start.",
            "Whether the coached gesture (wrist, accent, tempo intent) survives "
            "the whole phrase.",
        ],
        "what_to_play": [
            "Play the phrase slowly, exactly in order — the grader follows "
            "the order, not the speed.",
            "Use the printed fingering; the pattern is the fingering.",
            "Repeat hands separately before joining them (later exercises "
            "add the left hand).",
        ],
        "theory_terms": [
            "five-finger position", "scale run", "fingering",
            "scale degree", "phrase", "even articulation",
        ],
        "atlas_connections": [
            "Each phrase claims its key's scale node only — a melodic line "
            "lands on no chord node.",
            "The degrees of the phrase are the same 1..7 (and octave copies) "
            "every scale drill walks.",
        ],
        "common_misconceptions": [
            "\"The trainer punished my wrong note\" — it did not: a stray "
            "key may flash red, but grading ignores it completely; only the "
            "expected next note advances the walk.",
            "\"I must play the written octave\" — grading is octave-blind; "
            "the notation shows the intended register, the grader hears "
            "pitch classes (an octave-doubling step counts distinct keys, "
            "not registers — any two octaves of the class pass).",
            "\"The trainer heard my two notes as together\" — it checked "
            "that they overlapped when the later one went down, not that "
            "they were struck at the same instant; true attack-together "
            "grading needs note-on timestamps the grader currently "
            "discards.",
            "\"Passing the drill means the technique is right\" — the grader "
            "checks order and concurrency only; tone, legato and relaxation "
            "are the coach line's job (holding notes for their written "
            "length arrives with ticket 04).",
        ],
        "next_steps": [
            "16th-note values and rendered fingering numbers (ticket 02).",
            "Hold enforcement — notes kept down for their written length "
            "(ticket 04).",
            "The dyad exercises this unlocks: thirds, ricochet sixths, "
            "octave scales, hands together (tickets 05/08/09/10).",
        ],
    },
}

_REQUIRED_CONCEPT_FIELDS = [
    "title", "short_definition", "core_idea", "what_to_listen_for",
    "what_to_play", "theory_terms", "atlas_connections",
    "common_misconceptions", "next_steps",
]


def get_concept_explanation(concept: str) -> Dict:
    """Return the structured theory explanation for ``concept`` (a fresh copy)."""
    key = canonical_concept(concept)
    base = _CONCEPT_EXPLANATIONS[key]
    out = {"concept": key}
    for field in _REQUIRED_CONCEPT_FIELDS:
        val = base[field]
        out[field] = list(val) if isinstance(val, list) else val
    return out


def all_concept_explanations() -> Dict[str, Dict]:
    """``{canonical_concept: explanation}`` for every implemented concept."""
    return {k: get_concept_explanation(k) for k in CONCEPT_KEYS}


# ---------------------------------------------------------------------------
# Small display helpers (derive prose from structured data)
# ---------------------------------------------------------------------------

def _mode_word_of(mode: str) -> str:
    try:
        return _mode_word(mode)
    except Exception:
        return "natural minor" if mode == "natural_minor" else "major"


def _key_display(measure) -> str:
    return measure.key_display


def _fact(label: str, value) -> Dict:
    return {"label": label, "value": value}


def _slash_label(chord_symbol: Optional[str], bass_note: Optional[str],
                 inversion: Optional[int]) -> str:
    """``"C"`` (root) / ``"C/E"`` (inverted) -- the practical slash-chord name."""
    sym = chord_symbol or ""
    if inversion and bass_note:
        return f"{sym}/{bass_note}"
    return sym


# ---------------------------------------------------------------------------
# Part 5: experiment-level explanation (assembled from the compiled experiment)
# ---------------------------------------------------------------------------

def get_experiment_explanation(spec, experiment) -> Dict:
    """Assemble a rich explanation of one compiled lab experiment.

    ``spec`` is the :class:`~harmony.lab_spec.LabExperimentSpec`; ``experiment``
    is the :class:`~harmony.lab.LabExperiment` returned by
    :func:`harmony.lab.compile_lab`.  Every specific musical fact is read from
    ``experiment.measures`` / their annotations -- only the framing prose is
    templated.
    """
    concept = canonical_concept(spec.concept)
    measures = list(getattr(experiment, "measures", []))
    first = measures[0] if measures else None
    mode_word = _mode_word_of(spec.mode)
    scale = list(first.scale_pitches) if first else []

    base = {
        "concept": concept,
        "conceptLabel": _CONCEPT_EXPLANATIONS[concept]["title"],
        "title": getattr(experiment, "title", spec.title),
        "key": first.key_display if first else spec.key,
        "mode": spec.mode,
        "modeWord": mode_word,
        "scale": scale,
        "measureCount": len(measures),
        "facts": [],
        "invariants": [],
        "changes": [],
        "sections": [],
        "practice": [],
        "summary": "",
    }

    builder = {
        "inversion": _explain_inversion,
        "voice_leading": _explain_cadence,
        "motive": _explain_motive,
        "polyphonic_harmony": _explain_polyphonic,
        "reduction": _explain_reduction,
    }[concept]
    builder(base, spec, measures)
    return base


def _explain_inversion(base, spec, measures) -> None:
    if not measures:
        return
    ann = measures[0].annotation
    tones = list(ann.chord_tones)
    base["facts"] = [
        _fact("Key", base["key"]),
        _fact("Scale", " ".join(base["scale"])),
        _fact("Degree", ann.roman),
        _fact("Chord", ann.chord_symbol),
        _fact("Chord tones", "-".join(tones)),
        _fact("Interval layer", ann.interval_layer),
        _fact("Function", ann.function_label),
    ]
    base["invariants"] = [
        f"chord tones {'-'.join(tones)}",
        f"root identity {ann.root}",
        f"{ann.function_label} function",
    ]
    changes = []
    sections = []
    practice_slashes = []
    for m in measures:
        a = m.annotation
        slash = _slash_label(a.chord_symbol, a.bass_note, a.inversion)
        practice_slashes.append(slash)
        changes.append(
            f"bass {a.bass_note} ({a.inversion_label}, figured bass {a.figured_bass})")
        sections.append({
            "title": f"{a.inversion_label} - {slash}",
            "lines": [
                f"Bass: {a.bass_note}",
                f"Figured bass: {a.figured_bass}",
                f"Sounding tones: {'-'.join(a.chord_tones)} (unchanged)",
                a.lab_note,
            ],
        })
    base["changes"] = changes + ["the inversion label and figured bass",
                                 "the sonority / sense of stability"]
    base["sections"] = sections
    base["practice"] = [
        "Play all the chord tones in any octave to confirm the harmony.",
        "Then require the bass note first, then the remaining tones.",
        "Compare the bass positions: " + ", ".join(practice_slashes) + ".",
    ]
    base["summary"] = (
        f"In {base['key']}, {ann.roman} is {ann.chord_symbol}, built from "
        f"{'-'.join(tones)}. Across the experiment the chord tones and the "
        f"{ann.function_label} function stay invariant while only the bass "
        f"changes ({' -> '.join(m.annotation.bass_note for m in measures)}).")


def _explain_cadence(base, spec, measures) -> None:
    if not measures:
        return
    romans = [m.annotation.roman for m in measures]
    label = "-".join(romans)
    function_path = [m.annotation.function_label for m in measures]
    cadence_type = next((m.annotation.cadence_type for m in measures
                         if m.annotation.cadence_type), None) \
        or (spec.parameters.get("cadence_type") or None)
    base["facts"] = [
        _fact("Key", base["key"]),
        _fact("Progression", label),
        _fact("Roman numerals", " - ".join(romans)),
        _fact("Function path", " -> ".join(function_path)),
    ]
    if cadence_type:
        base["facts"].append(_fact("Cadence type", cadence_type))

    sections = []
    bass_steps = []
    for i, m in enumerate(measures):
        a = m.annotation
        lines = [
            f"{a.roman} = {a.chord_symbol} ({a.function_label})",
            f"Chord tones: {'-'.join(a.chord_tones)}",
        ]
        if a.bass_motion:
            lines.append(f"Bass motion: {a.bass_motion}")
            bass_steps.append(a.bass_motion)
        if a.common_tones:
            lines.append("Common tone(s): " + "-".join(a.common_tones))
        if a.tendency_tones:
            lines.extend(a.tendency_tones)
        sections.append({"title": f"Chord {i + 1}: {a.roman}", "lines": lines})
    base["sections"] = sections
    base["invariants"] = [f"function path {' -> '.join(function_path)}",
                          f"key {base['key']}"]
    base["changes"] = ["the chord at each step (the Roman numerals)",
                       "the bass position and the active voices"]
    base["practice"] = [
        "Play each chord as a block, then connect them in time.",
        "Hold the common tone(s) and move only the other voices.",
        "Resolve the tendency tone(s) by step into the chord of arrival.",
    ]
    last = measures[-1].annotation
    base["summary"] = (
        f"{label} in {base['key']} is a directed progression: the function path "
        f"{' -> '.join(function_path)}"
        + (f" forms a(n) {cadence_type} cadence" if cadence_type else "")
        + (f", arriving on {last.roman} ({last.chord_symbol})." if last else "."))


def _explain_motive(base, spec, measures) -> None:
    if not measures:
        return
    a0 = measures[0].annotation
    motive_label = a0.motive_label or a0.roman
    degree_labels = list(a0.degree_labels)
    base["facts"] = [
        _fact("Motive (degrees)", motive_label),
        _fact("Degree pattern", " ".join(degree_labels)),
        _fact("Mode", base["modeWord"]),
        _fact("Keys", str(len(measures))),
    ]
    base["invariants"] = [
        f"the degree pattern {motive_label}",
        "the interval shape between the notes",
    ]
    base["changes"] = ["every absolute pitch (one rendering per key)",
                       "the key signature / scale of each key"]
    sections = []
    path = []
    for m in measures:
        a = m.annotation
        path.append(m.tonic)
        notes = _motive_notes_from_measure(m)
        sections.append({
            "title": f"{m.key_display}",
            "lines": [
                f"Degrees {motive_label} -> notes {'-'.join(notes)}",
            ],
        })
    base["sections"] = sections
    base["transpositionPath"] = path
    base["facts"].append(_fact("Transposition path", " -> ".join(path)))
    base["practice"] = [
        "Play the motive in one key, then the same degrees in the next.",
        "Follow the transposition path and play it key by key.",
        "Sing the degree numbers to feel the invariant shape.",
    ]
    base["summary"] = (
        f"The motive {motive_label} keeps its scale-degree shape while it is "
        f"transposed through {len(measures)} {base['modeWord']} keys "
        f"({' -> '.join(path)}); the pattern is invariant, the pitches are not.")


def _motive_notes_from_measure(measure) -> List[str]:
    """Spelled note names (no octave) of the sounding melodic notes of a measure."""
    out = []
    for n in measure.staff1:
        if n.is_rest:
            continue
        acc = "#" * n.alter if n.alter > 0 else "b" * (-n.alter)
        out.append(f"{n.step}{acc}")
    return out


def _explain_polyphonic(base, spec, measures) -> None:
    if not measures:
        return
    romans = [m.annotation.implied_roman or m.annotation.roman for m in measures]
    label = "-".join(romans)
    base["facts"] = [
        _fact("Key", base["key"]),
        _fact("Implied progression", label),
        _fact("Voices", "two independent lines (bass + upper)"),
        _fact("Function path",
              " -> ".join(m.annotation.function_label for m in measures)),
    ]
    base["invariants"] = ["two independent voices throughout",
                          f"key {base['key']}"]
    base["changes"] = ["the implied chord at each slice",
                       "the vertical interval between the two voices"]
    sections = []
    for i, m in enumerate(measures):
        a = m.annotation
        voices = ", ".join(f"{name} {pitch}" for name, pitch in a.voices) \
            if a.voices else ""
        lines = [
            f"Vertical slice: {voices}" if voices else "Vertical slice",
            f"Implies: {a.implied_chord or a.chord_symbol} "
            f"({a.implied_roman or a.roman}, {a.function_label})",
            f"Atlas triad node: {a.atlas_triad_id}",
        ]
        sections.append({"title": f"Slice {i + 1}: {a.implied_roman or a.roman}",
                         "lines": lines})
    base["sections"] = sections
    base["practice"] = [
        "Play the bass and upper voice together; name the implied chord.",
        "Play each line alone, then together, and hear the harmony appear.",
        "Compare each implied chord with its full block triad.",
    ]
    base["summary"] = (
        f"Two independent voices in {base['key']} imply the progression {label}: "
        f"each vertical slice outlines a triad even though no full chord is "
        f"stated, so the texture projects harmony horizontally.")


def _explain_reduction(base, spec, measures) -> None:
    base["facts"] = [
        _fact("Key", base["key"]),
        _fact("Status", "reserved - not implemented yet"),
    ]
    base["invariants"] = ["(reserved)"]
    base["changes"] = ["(reserved)"]
    base["sections"] = [{
        "title": "Reserved",
        "lines": [
            "Reduction exposes the structural harmonic skeleton of a passage.",
            "A supplied skeleton compiles to a chord drill, but compile_lab is "
            "not implemented for reduction yet.",
        ],
    }]
    base["practice"] = ["(Reserved.)"]
    base["summary"] = (
        "Reduction is the reserved Schenkerian-analysis phase; the data model "
        "and the Atlas score-analysis contract are shaped for it, but the "
        "reduction algorithm is not implemented yet.")


# ---------------------------------------------------------------------------
# Part 6: per-measure "Current Mapping" payload
# ---------------------------------------------------------------------------

def _concept_of_measure(measure) -> str:
    """Infer the canonical concept of a single measure from its annotation."""
    a = measure.annotation
    if a.motive_label:
        return "motive"
    if a.implied_roman:
        return "polyphonic_harmony"
    if a.inversion is not None:
        return "inversion"
    if a.voices or a.bass_motion or a.common_tones or a.tendency_tones or a.cadence_type:
        return "voice_leading"
    return "inversion"


def get_measure_explanation(measure, atlas=None, experiment_title: str = "") -> Dict:
    """Build the per-measure "Current Mapping" payload from one LabMeasure.

    Every field is read from the measure / its annotation (the precomputed Atlas
    node ids included), so this is the Python-derived source of truth for the
    Current Mapping tab and the live current-measure explanation.  Pass ``atlas``
    to also attach the related Atlas edges (:meth:`Atlas.edges_for`).
    """
    a = measure.annotation
    concept = _concept_of_measure(measure)
    node_ids = {
        "scale": a.atlas_scale_id,
        "degree": a.atlas_degree_id,
        "triad": a.atlas_triad_id,
    }
    node_ids = {k: v for k, v in node_ids.items() if v}

    out = {
        "concept": concept,
        "conceptLabel": _CONCEPT_EXPLANATIONS[concept]["title"],
        "experimentTitle": experiment_title,
        "measureNumber": measure.index + 1,
        "key": measure.key_display,
        "mode": measure.mode,
        "modeWord": _mode_word_of(measure.mode),
        "scale": list(measure.scale_pitches),
        "roman": a.roman,
        "chordSymbol": a.chord_symbol,
        "tones": list(a.chord_tones),
        "function": a.function_label,
        "intervalLayer": a.interval_layer,
        "labNote": a.lab_note or a.explanation,
        "atlasNodeIds": node_ids,
        "atlasEdges": [],
        # concept-specific blocks (only the relevant one is non-null):
        "inversion": None,
        "cadence": None,
        "motive": None,
        "polyphony": None,
    }

    if a.inversion is not None:
        out["inversion"] = {
            "inversion": a.inversion,
            "label": a.inversion_label,
            "figuredBass": a.figured_bass,
            "bass": a.bass_note,
            "slash": _slash_label(a.chord_symbol, a.bass_note, a.inversion),
        }
    if a.bass_motion or a.common_tones or a.tendency_tones or a.cadence_type:
        out["cadence"] = {
            "bassMotion": a.bass_motion,
            "commonTones": list(a.common_tones),
            "tendencyTones": list(a.tendency_tones),
            "cadenceType": a.cadence_type,
            "voices": [list(v) for v in a.voices],
        }
    if a.motive_label:
        out["motive"] = {
            "label": a.motive_label,
            "degrees": list(a.degree_labels),
            "notes": _motive_notes_from_measure(measure),
        }
    if a.implied_roman:
        out["polyphony"] = {
            "impliedRoman": a.implied_roman,
            "impliedChord": a.implied_chord,
            "voices": [list(v) for v in a.voices],
        }

    if atlas is not None and node_ids:
        try:
            out["atlasEdges"] = atlas.edges_for(list(node_ids.values()))
        except Exception:
            out["atlasEdges"] = []
    return out


def mapping_from_target(target: Dict, atlas=None) -> Dict:
    """Build a Current-Mapping payload from a runtime trainer/lab *target* dict.

    Fallback used when no compiled :class:`LabMeasure` is on hand (e.g. a raw
    Atlas/Circle drill loaded into the middle trainer).  Reads only the documented
    trainer/lab payload keys, so it works for both shapes.
    """
    t = target or {}
    node_ids = {
        "scale": t.get("atlasScaleId"),
        "degree": t.get("atlasDegreeId"),
        "triad": t.get("atlasTriadId"),
    }
    node_ids = {k: v for k, v in node_ids.items() if v}

    concept_field = t.get("concept")
    out = {
        "concept": concept_field or "",
        "conceptLabel": "",
        "experimentTitle": t.get("title", ""),
        "measureNumber": (t.get("measureNumber")
                          or ((t.get("absMeasure") or 0) + 1)),
        "key": t.get("key", ""),
        "mode": t.get("mode", ""),
        "modeWord": _mode_word_of(t.get("mode", "major")),
        "scale": list(t.get("scale", []) or []),
        "roman": t.get("roman", ""),
        "chordSymbol": t.get("chordSymbol", ""),
        "tones": list(t.get("chordTones", []) or []),
        "function": t.get("functionLabel", ""),
        "intervalLayer": t.get("intervalLayer", ""),
        "labNote": t.get("labNote") or t.get("explanation", ""),
        "atlasNodeIds": node_ids,
        "atlasEdges": [],
        "inversion": None,
        "cadence": None,
        "motive": None,
        "polyphony": None,
    }
    if t.get("inversionLabel"):
        out["inversion"] = {
            "inversion": t.get("inversion"),
            "label": t.get("inversionLabel"),
            "figuredBass": t.get("figuredBass"),
            "bass": t.get("bassNote"),
            "slash": _slash_label(t.get("chordSymbol"), t.get("bassNote"),
                                  t.get("inversion")),
        }
    if t.get("bassMotion") or t.get("commonTones") or t.get("tendencyTones") \
            or t.get("cadenceType"):
        out["cadence"] = {
            "bassMotion": t.get("bassMotion"),
            "commonTones": list(t.get("commonTones", []) or []),
            "tendencyTones": list(t.get("tendencyTones", []) or []),
            "cadenceType": t.get("cadenceType"),
            "voices": [list(v) for v in (t.get("voices") or [])],
        }
    if t.get("motiveLabel"):
        out["motive"] = {
            "label": t.get("motiveLabel"),
            "degrees": list(t.get("degreeLabels", []) or []),
            "notes": [],
        }
    if t.get("impliedRoman"):
        out["polyphony"] = {
            "impliedRoman": t.get("impliedRoman"),
            "impliedChord": t.get("impliedChord"),
            "voices": [list(v) for v in (t.get("voices") or [])],
        }
    try:
        out["conceptLabel"] = _CONCEPT_EXPLANATIONS[canonical_concept(
            concept_field or "")]["title"] if concept_field else ""
    except ValueError:
        out["conceptLabel"] = ""
    if atlas is not None and node_ids:
        try:
            out["atlasEdges"] = atlas.edges_for(list(node_ids.values()))
        except Exception:
            out["atlasEdges"] = []
    return out
