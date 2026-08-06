"""Harmonic role profiles -- the explicit two-level model the scene UI needs.

This module makes a distinction the rest of the app kept implicit and, in the graph scene,
lossy: a chord has a **specific scale-degree role** (mediant, subdominant, leading-tone
diminished, ...) *and* it belongs to a **broad function family** (tonic-related, predominant,
dominant).  The old code carried only the collapsed family label (see
:data:`harmony.harmonic_network.BROAD_FUNCTION`), so ``iii`` was shown simply as "tonic" -- erasing
that it is specifically the mediant.  This module keeps both levels distinct (plan sections 1-3).

Single source of truth is preserved: :mod:`theory.diatonic_harmony` still owns spelling, quality,
Roman numerals and the raw ``scale_degree_name`` / ``function_label``.  This module adds only the
pedagogical overlay -- how to *name and explain* the role and family -- and never re-encodes theory
tables (the degree-name tables are *imported* from the theory engine, not copied).

Backward-compatibility (plan section 3.2): the INTERNAL 3-family key
(``"tonic"``/``"predominant"``/``"dominant"``, the values of
:data:`harmony.harmonic_network.BROAD_FUNCTION`) is left untouched -- it is baked into node ids
(``hn:function:{mode}:{fam}``) and layout bands.  The presentation family introduced here
(``"tonic_related"`` etc.) is a *second* layer mapped from it, not a rename of it.

Mode awareness (plan section 2.4): major-mode family strength is NOT generalised blindly to natural
minor.  The natural-minor ``v`` (minor, no leading tone) and ``VII`` (modal subtonic) are marked
``contextual`` and given honest, weaker family memberships rather than being asserted as strong
dominants.  Harmonic minor (ticket 13 / plan G2a) flips exactly those two: its raised leading tone
makes ``V`` a strong primary dominant and ``vii°`` a strong leading-tone chord, while its ``III+``
(augmented) loses natural minor's relative-major tonic grouping and becomes a contextual mediant.

Pure / headless: no Qt, JS, MusicXML or file I/O; deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

# Reuse the theory engine's degree-name tables rather than duplicating them (plan section 10 "Do
# not duplicate chord spellings or scale tables. Reuse theory.diatonic_harmony.").
from theory.diatonic_harmony import (
    _canon_mode,
    _DEGREE_NAMES_HARMONIC_MINOR,
    _DEGREE_NAMES_MAJOR,
    _DEGREE_NAMES_MINOR,
    _FUNCTION_LABELS_HARMONIC_MINOR,
    _FUNCTION_LABELS_MAJOR,
    _FUNCTION_LABELS_MINOR,
)


# --------------------------------------------------------------------------------------------- #
# Controlled vocabularies (plan section 3)
# --------------------------------------------------------------------------------------------- #

#: The broad function families a chord can belong to (the presentation layer).  ``tonic_related``
#: replaces the bare ``tonic`` so I/iii/vi are never presented as identical "tonic" material;
#: ``modal_or_contextual`` is the honest bucket for degrees whose function is mode-dependent.
BROAD_FUNCTION_FAMILIES = frozenset({
    "tonic_related", "predominant", "dominant", "modal_or_contextual",
})

#: How a chord participates in its family.
FAMILY_MEMBERSHIP_TYPES = frozenset({
    "primary", "related", "substitute", "preparatory", "leading_tone", "contextual",
})

#: How strong that participation is.
FAMILY_MEMBERSHIP_STRENGTH = frozenset({
    "strong", "medium", "weak", "context_dependent",
})

#: Human labels for the broad families (shown in the scene header / detail panel).
BROAD_FAMILY_LABELS: Dict[str, str] = {
    "tonic_related": "Tonic-related family",
    "predominant": "Predominant family",
    "dominant": "Dominant family",
    "modal_or_contextual": "Modal / contextual family",
}

#: The INTERNAL 3-family key (``BROAD_FUNCTION`` values / node-id suffix / layout band) -> the
#: presentation broad family.  Keep in sync with :data:`harmony.harmonic_network.BROAD_FUNCTION`'s
#: *values* (never its keys): ``tonic`` -> ``tonic_related``.
INTERNAL_FAMILY_TO_BROAD: Dict[str, str] = {
    "tonic": "tonic_related",
    "predominant": "predominant",
    "dominant": "dominant",
}

#: A label (fine engine ``function_label`` OR a curated score-annotation scale-degree name) ->
#: presentation broad family.  Mirrors :data:`harmony.harmonic_network.BROAD_FUNCTION` but renames
#: ``tonic`` -> ``tonic_related`` and, unlike the old ``.get(..., "tonic")``, handles the fine
#: scale-degree names that leak into ``function_label`` via curated score annotations (bwv846/999)
#: instead of silently defaulting them to tonic.  Unknown labels fail *honest*, to
#: ``modal_or_contextual`` (see :func:`broad_function_family`), never to a false "tonic".
_LABEL_TO_BROAD: Dict[str, str] = {
    # engine function_label values
    "tonic": "tonic_related",
    "mediant": "tonic_related",
    "predominant": "predominant",
    "subdominant": "predominant",
    "dominant": "dominant",
    # fine scale-degree names (curated score annotations)
    "supertonic": "predominant",
    "submediant": "tonic_related",
    "leading-tone": "dominant",
    "subtonic": "dominant",
}


def broad_function_family(label: str) -> str:
    """Map an engine ``function_label`` (or a curated fine scale-degree name) to a broad family.

    Honest fallback: an unrecognised label yields ``"modal_or_contextual"`` -- never a false
    ``"tonic"`` (the old ``BROAD_FUNCTION.get(..., "tonic")`` mis-bucketed ``supertonic`` /
    ``subtonic`` as tonic; this does not).
    """
    return _LABEL_TO_BROAD.get((label or "").strip().lower(), "modal_or_contextual")


def internal_family_to_broad(internal_family: str) -> str:
    """Map the internal 3-family key (``tonic``/``predominant``/``dominant``) to a broad family."""
    return INTERNAL_FAMILY_TO_BROAD.get((internal_family or "").strip().lower(), "modal_or_contextual")


def broad_family_label(broad_family: str) -> str:
    return BROAD_FAMILY_LABELS.get(broad_family, "Contextual")


# --------------------------------------------------------------------------------------------- #
# Derived vocabulary (ticket 01 / plan F1, section 9.5): the single source everyone else maps from
# --------------------------------------------------------------------------------------------- #

#: The theory engine's fine ``function_label`` vocabulary (all mode tables).  Derived from the
#: engine so this module can never disagree with it.
ENGINE_FUNCTION_LABELS = (frozenset(_FUNCTION_LABELS_MAJOR)
                          | frozenset(_FUNCTION_LABELS_MINOR)
                          | frozenset(_FUNCTION_LABELS_HARMONIC_MINOR))

#: Presentation broad family -> INTERNAL 3-family key (the inverse of
#: :data:`INTERNAL_FAMILY_TO_BROAD`; ``modal_or_contextual`` has no internal key by design).
BROAD_TO_INTERNAL_FAMILY: Dict[str, str] = {
    broad: internal for internal, broad in INTERNAL_FAMILY_TO_BROAD.items()
}

#: THE collapse map: engine fine ``function_label`` -> INTERNAL 3-family key.  Derived from
#: :data:`_LABEL_TO_BROAD`, never hand-maintained.  ``harmony.harmonic_network.BROAD_FUNCTION``,
#: ``harmony.functional_network.ENGINE_FUNCTION_TO_GROUP`` and the circle payload's colour
#: classes are all copies of this dict (drift-tested in tests/test_function_vocabulary.py).
ENGINE_FUNCTION_TO_INTERNAL_FAMILY: Dict[str, str] = {
    label: BROAD_TO_INTERNAL_FAMILY[_LABEL_TO_BROAD[label]]
    for label in sorted(ENGINE_FUNCTION_LABELS)
}

#: Canonical short badge per INTERNAL family (legend chips, group badges).  ``PD/S`` names both
#: the predominant family and its subdominant member -- the one abbreviation that does not take
#: sides in the old predominant-vs-subdominant synonym conflict (plan F1).
INTERNAL_FAMILY_SHORT: Dict[str, str] = {
    "tonic": "T",
    "predominant": "PD/S",
    "dominant": "D",
}


def internal_family_label(internal_family: str) -> str:
    """The presentation label for an INTERNAL family key (e.g. ``"tonic"`` ->
    ``"Tonic-related family"``).  The two strings are different by design: the internal key is
    baked into node ids and layout bands; this label is what a learner reads."""
    return broad_family_label(internal_family_to_broad(internal_family))


def function_flow_short() -> str:
    """The canonical short form of the functional loop, e.g. ``"T → PD/S → D → T"``."""
    fams = ("tonic", "predominant", "dominant", "tonic")
    return " → ".join(INTERNAL_FAMILY_SHORT[f] for f in fams)


#: Shorthand tokens accepted inside functional drill patterns, per function name.  The trainer's
#: token table (``harmony.exercise_spec._FUNCTION_TOKEN_TO_ROMAN``) is derived from this pair of
#: tables, so the drill vocabulary and the prose vocabulary can never diverge.
FUNCTION_TOKEN_ALIASES: Dict[str, tuple] = {
    "tonic": ("T", "TONIC"),
    "subdominant": ("S", "SD", "SUBDOMINANT"),
    "predominant": ("PD", "PREDOMINANT"),
    "dominant": ("D", "DOMINANT"),
}

#: The exemplar diatonic degree (major mode, 0-based) each function name resolves to when used
#: as a drill token: T -> I, PD -> ii (the primary predominant), S -> IV (the subdominant),
#: D -> V.  Each degree's :func:`role_profile` specific role bears the function's name
#: (drift-tested).
FUNCTION_EXEMPLAR_DEGREE: Dict[str, int] = {
    "tonic": 0,
    "predominant": 1,
    "subdominant": 3,
    "dominant": 4,
}


#: Canonical cadence/progression-type vocabulary (ticket 02 / plan F2+F7), shared by the
#: curriculum catalogue, the Atlas cadence nodes, the harmonic network's cadence catalogue,
#: lab cadence parameters and score-analysis cadence spans.  ``subtonic`` is the modal
#: flat-VII -> i close; ``aeolian`` and ``axis`` tag loop *progressions* (i-VI-VII-i and
#: I-V-vi-IV) rather than two-chord closures -- the axis loop contains deceptive motion but is
#: never itself labelled "deceptive".
CADENCE_TYPES = frozenset({
    "authentic", "plagal", "half", "deceptive", "subtonic", "aeolian", "axis",
})


# --------------------------------------------------------------------------------------------- #
# HarmonicRoleProfile (plan section 3 contract)
# --------------------------------------------------------------------------------------------- #

@dataclass(frozen=True)
class HarmonicRoleProfile:
    """The two-level harmonic identity of one diatonic degree in a mode.

    ``scale_degree_name`` + ``specific_role`` are the *specific* level; ``broad_family`` is the
    *broad* level.  They are deliberately separate fields: the UI must never present the broad
    family as though it were the chord's complete, context-free identity (plan section 1)."""

    mode: str
    roman: str
    degree_index: int

    scale_degree_name: str            # tonic / supertonic / mediant / ... (from theory engine)
    specific_role: str                # e.g. "mediant", "subdominant", "leading-tone diminished"
    specific_role_label: str          # display form of specific_role

    broad_family: str                 # BROAD_FUNCTION_FAMILIES
    broad_family_label: str           # BROAD_FAMILY_LABELS[broad_family]

    family_membership_type: str       # FAMILY_MEMBERSHIP_TYPES
    family_membership_strength: str   # FAMILY_MEMBERSHIP_STRENGTH
    family_membership_explanation: str

    contextual: bool = False

    def to_dict(self) -> Dict:
        return {
            "mode": self.mode,
            "roman": self.roman,
            "degreeIndex": self.degree_index,
            "scaleDegreeName": self.scale_degree_name,
            "specificRole": self.specific_role,
            "specificRoleLabel": self.specific_role_label,
            "broadFamily": self.broad_family,
            "broadFamilyLabel": self.broad_family_label,
            "familyMembershipType": self.family_membership_type,
            "familyMembershipStrength": self.family_membership_strength,
            "familyMembershipExplanation": self.family_membership_explanation,
            "contextual": self.contextual,
        }


# --------------------------------------------------------------------------------------------- #
# Per-degree role tables (the pedagogical overlay)
# --------------------------------------------------------------------------------------------- #
#
# Each entry: (specific_role, specific_role_label, broad_family, membership_type,
#              membership_strength, membership_explanation, contextual)
# scale_degree_name is taken from theory.diatonic_harmony (not repeated here).
#
# MAJOR mode -- the pedagogical defaults of plan section 3.1 (I..vii deg).

_MAJOR_ROLES = {
    0: ("tonic proper", "Tonic proper", "tonic_related", "primary", "strong",
        "I is the tonic proper -- the harmonic home the whole key resolves to.", False),
    1: ("predominant", "Supertonic (predominant)", "predominant", "primary", "strong",
        "ii is a predominant chord: it prepares the dominant, falling a fifth onto V (ii -> V).",
        False),
    2: ("mediant", "Mediant", "tonic_related", "related", "context_dependent",
        "iii is the mediant. It shares two tones with the tonic triad but is not the tonic proper; "
        "it may prolong or relate to tonic depending on context, and can also lean dominant.",
        True),
    3: ("subdominant", "Subdominant", "predominant", "preparatory", "strong",
        "IV is the subdominant chord. In progressions such as IV-V-I it acts as a predominant by "
        "preparing the dominant; it can also move straight home (plagal IV-I).", False),
    4: ("dominant", "Dominant", "dominant", "primary", "strong",
        "V is the primary dominant triad -- the engine of tonal tension, resolving to I.", False),
    5: ("submediant", "Submediant / tonic substitute", "tonic_related", "substitute", "medium",
        "vi is the submediant and often acts as a tonic substitute (it shares two tones with I; it "
        "is the goal of the deceptive resolution V -> vi).", False),
    6: ("leading-tone diminished", "Leading-tone diminished", "dominant", "leading_tone", "strong",
        "vii deg is the leading-tone diminished chord -- a rootless dominant sharing the dominant's "
        "pull: its leading tone resolves up a semitone to the tonic (vii deg -> I).", False),
}

# NATURAL MINOR mode -- mode-aware (plan section 2.4).  v and VII are NOT asserted as strong
# dominants: the diatonic v is minor (no leading tone) and VII is the modal subtonic.
_MINOR_ROLES = {
    0: ("tonic proper", "Tonic proper", "tonic_related", "primary", "strong",
        "i is the tonic proper -- the harmonic home in the minor key.", False),
    1: ("predominant", "Supertonic diminished (predominant)", "predominant", "primary", "medium",
        "ii deg is the diminished supertonic; it acts as a predominant preparing the dominant.",
        False),
    2: ("mediant", "Mediant (relative major)", "tonic_related", "related", "context_dependent",
        "III is the mediant -- the relative major. Its tonic-related grouping is contextual, not a "
        "strong tonic identity.", True),
    3: ("subdominant", "Subdominant", "predominant", "preparatory", "strong",
        "iv is the subdominant and commonly prepares the dominant.", False),
    4: ("dominant", "Dominant (weak in natural minor)", "dominant", "contextual", "context_dependent",
        "In natural minor the diatonic v is minor and lacks a leading tone, so its dominant "
        "function is weak/contextual; harmonic minor raises it to a true V.", True),
    5: ("submediant", "Submediant", "tonic_related", "substitute", "medium",
        "VI is the submediant, a common tonic substitute and the goal of the deceptive cadence in "
        "minor.", False),
    6: ("subtonic", "Subtonic (modal flat-VII)", "modal_or_contextual", "contextual",
        "context_dependent",
        "VII is the subtonic (flat-7). In natural minor it is a modal chord that typically leads to "
        "III rather than functioning as a dominant of i; its family is contextual.", True),
}

# HARMONIC MINOR mode (ticket 13 / plan G2a) -- the raised leading tone makes the dominant
# machinery real: V is a strong primary dominant and vii° a strong leading-tone chord, exactly
# what natural minor's contextual v / subtonic VII honestly could not claim.  III+ (augmented)
# is a contextual mediant, not the relative-major tonic substitute natural minor's III is.
_HARMONIC_MINOR_ROLES = {
    0: _MINOR_ROLES[0],
    1: _MINOR_ROLES[1],
    2: ("mediant", "Mediant (augmented)", "tonic_related", "related", "context_dependent",
        "III+ is the augmented mediant of harmonic minor -- a colour chord whose raised 7th "
        "denies it natural minor's relative-major identity; its grouping is contextual.", True),
    3: _MINOR_ROLES[3],
    4: ("dominant", "Dominant", "dominant", "primary", "strong",
        "V is a true major dominant: harmonic minor's raised 7th is a leading tone, so V-i "
        "resolves with the same pull as in major.", False),
    5: _MINOR_ROLES[5],
    6: ("leading-tone diminished", "Leading-tone diminished", "dominant", "leading_tone",
        "strong",
        "vii° is the leading-tone diminished chord on harmonic minor's raised 7th -- a rootless "
        "dominant resolving up a semitone to i (vii° -> i).", False),
}

#: Per-mode role tables, keyed by the canonical mode (same keys as
#: :data:`_DEGREE_NAME_TABLES`).
_ROLE_TABLES = {
    "major": _MAJOR_ROLES,
    "natural_minor": _MINOR_ROLES,
    "harmonic_minor": _HARMONIC_MINOR_ROLES,
}


def _canon(mode: str) -> str:
    """Canonical mode key, via the theory engine's own canonicaliser (never a
    second normalisation).  An unrecognised mode string falls back by its
    minor-ness, preserving this module's historical tolerance."""
    try:
        return _canon_mode(mode or "major")
    except ValueError:
        # historical tolerance: anything not recognisably major reads as minor
        return "natural_minor"


#: Per-mode degree-name and role tables, keyed by the canonical mode.
_DEGREE_NAME_TABLES = {
    "major": _DEGREE_NAMES_MAJOR,
    "natural_minor": _DEGREE_NAMES_MINOR,
    "harmonic_minor": _DEGREE_NAMES_HARMONIC_MINOR,
}


def _degree_name(mode: str, degree_index: int) -> str:
    table = _DEGREE_NAME_TABLES[_canon(mode)]
    if 0 <= degree_index < len(table):
        return table[degree_index]
    return ""


def _is_major(mode: str) -> bool:
    return _canon(mode) == "major"


def role_profile(mode: str, degree_index: int, roman: str = "",
                 scale_degree_name: Optional[str] = None) -> HarmonicRoleProfile:
    """Build the :class:`HarmonicRoleProfile` for a diatonic degree.

    ``scale_degree_name`` may be passed (the caller usually has a :class:`DiatonicTriad`); if
    omitted it is looked up from the theory engine's degree tables so the two levels stay
    consistent with the rest of the app.
    """
    canon_mode = _canon(mode)
    table = _ROLE_TABLES[canon_mode]
    sdn = scale_degree_name or _degree_name(mode, degree_index)
    entry = table.get(degree_index)
    if entry is None:
        # Out-of-range / non-diatonic degree: honest contextual profile, never a false tonic.
        return HarmonicRoleProfile(
            mode=canon_mode, roman=roman, degree_index=degree_index,
            scale_degree_name=sdn, specific_role=(sdn or "contextual"),
            specific_role_label=(sdn.title() if sdn else "Contextual"),
            broad_family="modal_or_contextual",
            broad_family_label=broad_family_label("modal_or_contextual"),
            family_membership_type="contextual", family_membership_strength="context_dependent",
            family_membership_explanation="A degree with no fixed diatonic function in this mode.",
            contextual=True)
    role, role_label, broad, mtype, strength, expl, contextual = entry
    return HarmonicRoleProfile(
        mode=canon_mode, roman=roman, degree_index=degree_index,
        scale_degree_name=sdn, specific_role=role, specific_role_label=role_label,
        broad_family=broad, broad_family_label=broad_family_label(broad),
        family_membership_type=mtype, family_membership_strength=strength,
        family_membership_explanation=expl, contextual=contextual)


def role_profile_for_triad(triad) -> HarmonicRoleProfile:
    """Convenience: build a role profile straight from a :class:`DiatonicTriad`."""
    return role_profile(
        mode=triad.mode, degree_index=triad.degree_index, roman=triad.roman,
        scale_degree_name=getattr(triad, "scale_degree_name", None))


__all__ = [
    "BROAD_FUNCTION_FAMILIES",
    "FAMILY_MEMBERSHIP_TYPES",
    "FAMILY_MEMBERSHIP_STRENGTH",
    "BROAD_FAMILY_LABELS",
    "INTERNAL_FAMILY_TO_BROAD",
    "BROAD_TO_INTERNAL_FAMILY",
    "ENGINE_FUNCTION_LABELS",
    "ENGINE_FUNCTION_TO_INTERNAL_FAMILY",
    "INTERNAL_FAMILY_SHORT",
    "FUNCTION_TOKEN_ALIASES",
    "FUNCTION_EXEMPLAR_DEGREE",
    "CADENCE_TYPES",
    "broad_function_family",
    "internal_family_to_broad",
    "broad_family_label",
    "internal_family_label",
    "function_flow_short",
    "HarmonicRoleProfile",
    "role_profile",
    "role_profile_for_triad",
]
