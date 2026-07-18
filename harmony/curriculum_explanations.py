"""Generated lesson / exercise *pages* for the curriculum + the full UI payload.

This is the **pure** prose-assembly layer for :mod:`harmony.curriculum` (the
sibling of :mod:`harmony.lab_explanations`).  It turns a structural
:class:`~harmony.curriculum.CurriculumNode` into the rich page the workspace
shows *before* launching:

* :func:`lesson_page` -- definition, goal, skills acquired, common mistakes,
  Atlas / Circle links, recommended order, related lessons, practice time, and
  audio / visual objectives.
* :func:`exercise_page` -- the full generated explanation, music theory, harmonic
  analysis, practice advice, voice-leading notes, Atlas mapping, Circle mapping,
  the current-mapping hook, the trainer preview (the actual compiled chords), and
  the launch spec.

Data-source rule (shared with the rest of the project): general framing prose may
be templated, but **every specific musical fact is derived** from the exercise's
``LabExperimentSpec`` -> ``HarmonyExerciseSpec`` -> compiled chords (and the
Atlas / Circle id schemes), never hand-written per chord.

It is pure (standard library + :mod:`theory.diatonic_harmony` +
:mod:`harmony.exercise_spec` + :mod:`harmony.lab_explanations`), so it
unit-tests headlessly and serialises to JSON for the web UI.  No Qt / Verovio /
MIDI.  :func:`build_curriculum_payload` assembles the whole ``window.CURRICULUM``
payload the left panel consumes.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from theory.diatonic_harmony import _mode_word
from harmony.exercise_spec import HarmonyExerciseSpec, compile_exercise
from harmony.lab import _CARET
from harmony.lab_explanations import get_concept_explanation, canonical_concept
from harmony.curriculum import (
    CurriculumNode, get_curriculum, to_json, SCHEMA_VERSION,
    function_families_prose, function_flow_short,
)


# ---------------------------------------------------------------------------
# Atlas / Circle id parsing (for human labels in the page)
# ---------------------------------------------------------------------------

def _atlas_label(node_id: str) -> Dict:
    """Parse an Atlas node id (``triad:C:major:0``) into ``{id, kind, label}``."""
    parts = str(node_id).split(":")
    kind = parts[0] if parts else ""
    rest = " ".join(parts[1:])
    return {"id": node_id, "kind": kind, "label": rest}


def _circle_label(ref: str) -> Dict:
    """Parse a circle ref (``key:C:major`` / ``degree:major:V``) for display."""
    parts = str(ref).split(":")
    kind = parts[0] if parts else ""
    if kind == "key" and len(parts) >= 3:
        return {"ref": ref, "kind": "key",
                "label": f"{parts[1]} {_mode_word(parts[2])}"}
    if kind == "degree" and len(parts) >= 3:
        return {"ref": ref, "kind": "degree", "label": parts[2]}
    return {"ref": ref, "kind": kind, "label": " ".join(parts[1:])}


def _atlas_links(node: CurriculumNode, limit: int = 24) -> List[Dict]:
    return [_atlas_label(i) for i in node.atlas_nodes[:limit]]


def _circle_links(node: CurriculumNode, limit: int = 24) -> List[Dict]:
    return [_circle_label(i) for i in node.circle_nodes[:limit]]


# ---------------------------------------------------------------------------
# Trainer preview + harmonic analysis (derived from the compiled chords)
# ---------------------------------------------------------------------------

def _preview_from_spec(hs: HarmonyExerciseSpec) -> List[Dict]:
    """The actual chord stream the trainer will play (derived, capped to one page)."""
    out = []
    for c in compile_exercise(hs).chords:
        t = c.triad
        out.append({
            "roman": t.roman,
            "chordSymbol": t.chord_symbol,
            "tones": list(t.pitches),
            "quality": t.chord_quality,
            "function": t.function_label,
            "intervalLayer": t.interval_layer,
            "key": t.key,
            "group": c.group,
        })
    return out


def _trainer_preview(node: CurriculumNode) -> Dict:
    """Preview for an exercise leaf: the compiled chords (or motive notes)."""
    spec = node.lab_spec
    es = spec.to_exercise_specs()
    if es:
        chords = _preview_from_spec(es[0])
        return {"render": es[0].render, "count": len(chords), "chords": chords,
                "kind": "chords"}
    # No chord-drill representation (a monophonic motive): preview its degrees.
    if spec.concept == "motive":
        degs = spec.parameters.get("degrees", [])
        return {
            "render": "melody", "kind": "motive",
            "count": len(spec.parameters.get("keys", [])) or 12,
            "degrees": [_CARET.get(d, f"^{d}") for d in degs],
        }
    return {"render": spec.render, "count": 0, "chords": [], "kind": "none"}


def _harmonic_analysis(node: CurriculumNode) -> List[str]:
    """One derived analytical line per distinct chord in the preview."""
    preview = _trainer_preview(node)
    if preview["kind"] != "chords":
        return []
    seen, lines = set(), []
    for ch in preview["chords"]:
        key = (ch["roman"], ch["chordSymbol"])
        if key in seen:
            continue
        seen.add(key)
        lines.append(
            f"{ch['roman']} = {ch['chordSymbol']} "
            f"({'-'.join(ch['tones'])}; {ch['quality']}, {ch['function']}, "
            f"{ch['intervalLayer']})")
    return lines


# ---------------------------------------------------------------------------
# Voice-leading notes (derived for progressions)
# ---------------------------------------------------------------------------

def _voice_leading_notes(node: CurriculumNode) -> List[str]:
    preview = _trainer_preview(node)
    if preview["kind"] != "chords" or preview["count"] < 2:
        return []
    chords = preview["chords"]
    notes = []
    for prev, cur in zip(chords, chords[1:]):
        common = [p for p in cur["tones"] if p in prev["tones"]]
        line = f"{prev['roman']} → {cur['roman']}: bass {prev['tones'][0]} → {cur['tones'][0]}"
        if common:
            line += f"; common tone(s) {'-'.join(common)}"
        notes.append(line)
    return notes


# ---------------------------------------------------------------------------
# Practice advice + common mistakes (templated per concept / drill family)
# ---------------------------------------------------------------------------

_DRILL_PRACTICE = {
    "full_key": [
        "Play each triad as written, naming its Roman numeral.",
        "Then play them as a scale of chords, top to bottom.",
        "Sing the root of each triad before you play it.",
    ],
    "horizontal_degree": [
        "Play the degree in one key, then jump to the next without hesitating.",
        "Name the key and the chord symbol aloud each time.",
        "Notice the spelling change while the Roman numeral stays put.",
    ],
    "quality": [
        "Listen for the quality before you read the key.",
        "Compare the bright major against the darker minor and tense diminished.",
        "Spell the stacked thirds (M3+m3, m3+M3, m3+m3).",
    ],
    "function": [
        "Play the whole progression, then each chord in isolation.",
        "Feel the pull from predominant through dominant back to tonic.",
        "Hum the bass line on its own.",
    ],
}

_CONCEPT_PRACTICE = {
    "inversion": [
        "Play all the chord tones in any octave to fix the harmony.",
        "Then play the required bass note first, then the rest.",
        "Compare the three bass positions back to back.",
    ],
    "voice_leading": [
        "Play each chord as a block, then connect them in time.",
        "Hold the common tone(s); move only the other voices.",
        "Resolve the leading / tendency tone by step into the chord of arrival.",
    ],
    "motive": [
        "Play the motive in one key, then the same degrees in the next.",
        "Sing the scale-degree numbers to feel the invariant shape.",
        "Follow the transposition around the circle of fifths.",
    ],
    "polyphonic_harmony": [
        "Play the bass and upper voice together; name the implied chord.",
        "Play each line alone, then together, and hear the harmony appear.",
        "Compare each implied chord with its full block triad.",
    ],
}

_CONCEPT_MISTAKES = {
    "inversion": [
        "Thinking C/E is a new chord — it is still C major, E in the bass.",
        "Assuming the lowest note is always the root (only in root position).",
    ],
    "voice_leading": [
        "Treating a cadence as just the last two chord names, not voice motion.",
        "Resolving the leading tone to the next chord's root instead of the tonic.",
    ],
    "motive": [
        "Believing transposition changes the melody (it changes pitches, not shape).",
        "Reading the motive as a chord rather than a degree pattern.",
    ],
    "polyphonic_harmony": [
        "Hearing 'just two melodies' and missing the implied chord per slice.",
        "Assuming you need three notes for a chord (two voices can imply a triad).",
    ],
    "full_key": [
        "Mislabelling vii° as a major chord (it is diminished).",
        "Losing the key signature when the spelling gets accidental-heavy.",
    ],
    "horizontal_degree": [
        "Re-spelling the chord instead of transposing the same degree.",
        "Forgetting the quality stays fixed while the pitches move.",
    ],
    "quality": [
        "Confusing minor and diminished (the fifth is the tell).",
        "Reading quality off the key signature instead of the stacked thirds.",
    ],
    "function": [
        "Calling every non-tonic chord 'dominant'.",
        "Missing that vi can substitute for I (a deceptive resolution).",
    ],
}


def _concept_key(node: CurriculumNode) -> str:
    """The drill family or canonical lab concept driving the page templates."""
    spec = node.lab_spec
    if spec is None:
        return ""
    if spec.concept == "drill":
        es = spec.to_exercise_specs()
        return es[0].drill if es else "full_key"
    return canonical_concept(spec.concept)


#: Per-drill-family music-theory prose for native exercise pages (the ``drill``
#: passthrough concept has no lab-concept theory, so the page draws on this).
_DRILL_THEORY = {
    "full_key": (
        "A key's seven diatonic triads, in order, spell the harmonic palette of "
        "that key: I ii iii IV V vi vii° in major, i ii° III iv v VI VII in minor. "
        "Playing them in a row fixes the sound of each scale degree's chord. Each chord "
        "has a SPECIFIC role (I the tonic, iii the mediant, IV the subdominant, vi the "
        "submediant, vii° the leading-tone diminished) AND belongs to a BROAD family — "
        "tonic-related (I, iii, vi), predominant (ii, IV) or dominant (V, vii°). The "
        "family is a grouping, not the chord's complete identity."),
    "horizontal_degree": (
        "A degree drill fixes one Roman numeral and transposes it through all 12 "
        "keys. The spelling and absolute pitches change, but the chord's quality "
        "and harmonic function stay put — that invariance is the point."),
    "quality": (
        "Triad quality is the order of two stacked thirds: major = M3+m3, "
        "minor = m3+M3, diminished = m3+m3. A quality drill collects every triad "
        "of one quality so the ear learns the colour independent of key."),
    # Generated from the shared two-level vocabulary (ticket 01 / plan F1).
    "function": function_families_prose("major"),
}


def _ancestor_theory(node: CurriculumNode) -> str:
    """The nearest ancestor's theory text (so an exercise inherits its lesson's)."""
    root = get_curriculum()
    parents = {c.id: n for n in root.walk() for c in n.children}
    cur = parents.get(node.id)
    while cur is not None:
        if cur.theory:
            return cur.theory
        cur = parents.get(cur.id)
    return ""


# ---------------------------------------------------------------------------
# Exercise page
# ---------------------------------------------------------------------------

def exercise_page(node: CurriculumNode) -> Dict:
    """Assemble the full pre-launch page for one exercise leaf (derived facts)."""
    if node.kind != "exercise" or node.lab_spec is None:
        raise ValueError(f"exercise_page expects an exercise leaf, got {node.kind}")
    spec = node.lab_spec
    ckey = _concept_key(node)
    preview = _trainer_preview(node)

    # Music-theory framing prose: the node's own theory, else the drill-family
    # blurb (native drills), else the lab concept's core idea, else the lesson's.
    theory = node.theory
    if not theory and spec.concept == "drill":
        theory = _DRILL_THEORY.get(ckey, "")
    if not theory:
        try:
            theory = get_concept_explanation(spec.concept)["core_idea"]
        except ValueError:
            theory = ""
    if not theory:
        theory = _ancestor_theory(node)

    practice = (_CONCEPT_PRACTICE.get(ckey)
                or _DRILL_PRACTICE.get(ckey)
                or ["Play the exercise slowly and name each chord."])
    mistakes = _CONCEPT_MISTAKES.get(ckey, [])

    return {
        "id": node.id,
        "kind": "exercise",
        "title": node.title,
        "subtitle": node.subtitle,
        "definition": node.description or node.learning_objective,
        "learningObjective": node.learning_objective,
        "difficulty": node.difficulty,
        "estimatedMinutes": node.estimated_minutes,
        "musicTheory": theory,
        "harmonicAnalysis": _harmonic_analysis(node),
        "practiceAdvice": list(practice),
        "voiceLeadingNotes": _voice_leading_notes(node),
        "commonMistakes": list(mistakes),
        "atlasMapping": _atlas_links(node),
        "circleMapping": _circle_links(node),
        "currentMapping": ("The live chord-by-chord mapping appears here once you "
                           "launch and start playing."),
        "trainerPreview": preview,
        "prerequisites": list(node.prerequisites),
        "recommendedNext": node.recommended_next,
        "related": list(node.related),
        "launch": spec.to_dict(),
    }


# ---------------------------------------------------------------------------
# Lesson / category page
# ---------------------------------------------------------------------------

_CATEGORY_OBJECTIVES = {
    "cat:scales": {"audio": "Recognise each scale and its triads by ear.",
                   "visual": "Read the seven triads on the grand staff."},
    "cat:chords": {"audio": "Tell major, minor and diminished triads apart by sound.",
                   "visual": "See the stacked-thirds shape of each quality."},
    "cat:degrees": {"audio": "Hear the same degree colour in any key.",
                    "visual": "Track one Roman numeral across the staff and circle."},
    "cat:functions": {"audio": f"Feel the {function_flow_short()} pull of a progression.",
                      "visual": "Follow the function colours through the chords."},
    "cat:cadences": {"audio": "Identify a cadence by its closing sound.",
                     "visual": "Spot the cadential bass motion."},
    "cat:intervals": {"audio": "Hear the two thirds inside a triad.",
                      "visual": "See M3 vs m3 on the staff."},
    "cat:inversions": {"audio": "Hear the chord identity survive a moving bass.",
                       "visual": "Read figured bass (5/3, 6, 6/4)."},
    # The SATB cadence variants live under cat:cadences now (F7); the lookup
    # walks up from a leaf to the nearest id present here, so a lesson id works.
    "lesson:voice_leading_cadences": {
        "audio": "Hear voices resolve into the cadence.",
        "visual": "See common tones held and tendency tones move."},
    "cat:motives": {"audio": "Recognise a motive transposed to a new key.",
                    "visual": "See the same contour re-spelled."},
    "cat:polyphony": {"audio": "Hear two lines imply a chord progression.",
                      "visual": "Read the vertical slice of two voices."},
}


def _objectives_for(node: CurriculumNode, root: CurriculumNode) -> Dict:
    # walk up to the owning category for the audio/visual objective template
    cur = node
    by_id = {n.id: n for n in root.walk()}
    parents = {c.id: n.id for n in root.walk() for c in n.children}
    while cur is not None and cur.id not in _CATEGORY_OBJECTIVES:
        pid = parents.get(cur.id)
        cur = by_id.get(pid) if pid else None
    if cur is not None and cur.id in _CATEGORY_OBJECTIVES:
        return _CATEGORY_OBJECTIVES[cur.id]
    return {"audio": "Listen for the concept while you play.",
            "visual": "Watch the staff and the highlighted Atlas / Circle nodes."}


def _skills_acquired(node: CurriculumNode) -> List[str]:
    """Skills = the distinct learning objectives of the lesson's exercises."""
    out, seen = [], set()
    for lf in node.leaves():
        obj = lf.learning_objective
        if obj and obj not in seen:
            seen.add(obj)
            out.append(obj)
    return out[:8]


def lesson_page(node: CurriculumNode, root: Optional[CurriculumNode] = None) -> Dict:
    """Assemble the page for a lesson / group / category (shown before its leaves)."""
    root = root or get_curriculum()
    by_id = {n.id: n for n in root.walk()}

    practice_time = node.estimated_minutes or sum(
        lf.estimated_minutes for lf in node.leaves())

    common = []
    for cmkey in (_concept_key_for_container(node),):
        common = _CONCEPT_MISTAKES.get(cmkey, [])

    objectives = _objectives_for(node, root)
    related = [{"id": r, "title": by_id[r].title}
               for r in node.related if r in by_id]
    recommended_order = [{"id": c.id, "title": c.title} for c in node.children]

    return {
        "id": node.id,
        "kind": node.kind,
        "title": node.title,
        "subtitle": node.subtitle,
        "definition": node.subtitle or node.description or node.learning_objective,
        "goal": node.learning_objective,
        "difficulty": node.difficulty,
        "reserved": node.reserved,
        "theory": node.theory,
        "skillsAcquired": _skills_acquired(node),
        "commonMistakes": list(common),
        "atlasLinks": _atlas_links(node) or _aggregate_atlas(node),
        "circleLinks": _circle_links(node) or _aggregate_circle(node),
        "recommendedOrder": recommended_order,
        "relatedLessons": related,
        "estimatedPracticeTime": practice_time,
        "exerciseCount": node.exercise_count,
        "audioObjective": objectives["audio"],
        "visualObjective": objectives["visual"],
        "prerequisites": list(node.prerequisites),
        "recommendedNext": node.recommended_next,
    }


def _concept_key_for_container(node: CurriculumNode) -> str:
    leaves = node.leaves()
    if not leaves:
        return ""
    spec = leaves[0].lab_spec
    if spec is None:
        return ""
    if spec.concept == "drill":
        es = spec.to_exercise_specs()
        return es[0].drill if es else ""
    try:
        return canonical_concept(spec.concept)
    except ValueError:
        return ""


def _aggregate_atlas(node: CurriculumNode, limit: int = 16) -> List[Dict]:
    seen, out = set(), []
    for lf in node.leaves():
        for nid in lf.atlas_nodes:
            if nid not in seen:
                seen.add(nid)
                out.append(_atlas_label(nid))
            if len(out) >= limit:
                return out
    return out


def _aggregate_circle(node: CurriculumNode, limit: int = 16) -> List[Dict]:
    seen, out = set(), []
    for lf in node.leaves():
        for ref in lf.circle_nodes:
            if ref not in seen:
                seen.add(ref)
                out.append(_circle_label(ref))
            if len(out) >= limit:
                return out
    return out


def page_for(node: CurriculumNode, root: Optional[CurriculumNode] = None) -> Dict:
    """Dispatch: an exercise leaf -> exercise_page; anything else -> lesson_page."""
    if node.kind == "exercise":
        return exercise_page(node)
    return lesson_page(node, root)


# ---------------------------------------------------------------------------
# Full UI payload
# ---------------------------------------------------------------------------

def build_curriculum_payload(root: Optional[CurriculumNode] = None) -> Dict:
    """The complete ``window.CURRICULUM`` payload: structure + per-node pages.

    ``pages`` maps every node id to its generated lesson/exercise page, so the
    web UI can show the lesson page on selection and the exercise page on an
    exercise click without a host round-trip.
    """
    root = root or get_curriculum()
    payload = to_json(root)
    payload["schema"] = SCHEMA_VERSION
    payload["pages"] = {n.id: page_for(n, root) for n in root.walk()}
    return payload
