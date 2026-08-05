"""Curriculum coverage audit — a pure introspection report over the live tree.

This is the machine-readable side of the corrective-maintenance "incomplete
lesson" audit (Bug 4).  It walks the **built** curriculum
(:func:`harmony.curriculum.build_curriculum`), the Atlas
(:func:`harmony.atlas.build_atlas`) and the Circle payload
(:func:`harmony.circle_payload.build_circle_payload`) and reports, per audit
category:

* expected vs actual coverage,
* missing required nodes (the cadence patterns + inversion grid this maintenance
  pass mandates),
* duplicate exercise / experiment ids,
* invalid ``LabExperimentSpec`` / broken ``HarmonyExerciseSpec`` bridge,
* empty lesson/exercise explanations,
* missing Atlas / Circle mappings,
* which test files cover the category.

It is **pure** (standard library + the pure curriculum / atlas / circle layers;
no Qt / Verovio / MIDI), so it serialises to JSON and unit-tests headlessly.
:func:`build_audit` returns the report dict; :func:`render_markdown` renders the
human-readable page; running the module writes both artifacts under ``docs/``.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

from harmony.exercise_spec import (
    compile_exercise, MAX_CHORDS_PER_SPEC, DEFAULT_MAJOR_KEYS, DEFAULT_MINOR_KEYS,
)
from harmony.curriculum import (
    CurriculumNode, build_curriculum, _CADENCE_CATALOG,
    _MAJOR_INV_DEGREES, _MINOR_INV_DEGREES,
)
from harmony.curriculum_explanations import exercise_page, lesson_page
from harmony.atlas import build_atlas
from harmony.circle_payload import build_circle_payload


SCHEMA_VERSION = "harmony-curriculum-audit/v1"


# ---------------------------------------------------------------------------
# Category definitions: (key, title, category node id(s), test files, expected)
# ---------------------------------------------------------------------------

_CATEGORIES = [
    ("scales", "Scales", ["cat:scales"],
     ["tests/test_curriculum.py", "tests/test_diatonic_harmony.py",
      "tests/test_harmony_musicxml.py"],
     "48 full-key drills (12 major + 12 minor, block + arpeggio)."),
    ("chords", "Chords / Triad quality", ["cat:chords"],
     ["tests/test_curriculum.py", "tests/test_harmony_atlas.py"],
     "Major / minor / diminished quality drills (augmented reserved)."),
    ("degrees", "Degrees & Transposition", ["cat:degrees"],
     ["tests/test_curriculum.py", "tests/test_harmony_exercise.py"],
     "Each degree across all 12 keys, both modes, block + arpeggio (28)."),
    ("functions", "Functions", ["cat:functions"],
     ["tests/test_curriculum.py", "tests/test_harmony_exercise.py"],
     "Major + minor functional progressions (19)."),
    ("cadences", "Cadences", ["cat:cadences"],
     ["tests/test_curriculum.py", "tests/test_curriculum_cadences.py",
      "tests/test_content_truth.py", "tests/test_harmony_atlas.py"],
     "13 cadences (6 two-chord types + 7 functional progressions), each as a "
     "block drill AND an SATB voice-leading variant (26 leaves)."),
    ("sevenths", "Seventh Chords", ["cat:sevenths"],
     ["tests/test_seventh_chords.py", "tests/test_curriculum.py"],
     "The V7 tracer (plan G1a): add-the-7th + V7→I chunked across the 12 major "
     "keys, and the two-voice tritone-resolution frame per key (16 leaves; the "
     "remaining seventh qualities and V7 inversions are reserved)."),
    ("intervals", "Intervals & Interval Layers", ["cat:intervals"],
     ["tests/test_harmony_atlas.py"],
     "Theory + cross-links to quality groups (owns no exercise by design)."),
    ("inversions", "Inversions", ["cat:inversions"],
     ["tests/test_curriculum.py", "tests/test_curriculum_inversions.py",
      "tests/test_harmony_lab.py"],
     "96-key grid (I/ii/IV/V x 12 major + i/iv/v/VII x 12 minor) + worked example."),
    ("motives", "Motives", ["cat:motives"],
     ["tests/test_harmony_lab.py"],
     "Scale-degree motive cells transposed across keys."),
    ("polyphony", "Polyphonic Harmony", ["cat:polyphony"],
     ["tests/test_harmony_lab.py"],
     "Two-voice implied-harmony examples."),
    ("integration", "Atlas / Circle integration", ["cat:atlas", "cat:circle"],
     ["tests/atlas_node_test.js", "tests/circle_node_test.js",
      "tests/test_circle_payload.py"],
     "Bridge categories opening the Atlas / Circle (reserved leaves)."),
    ("reserved", "Reserved topics", ["cat:advanced", "cat:reserved"],
     ["tests/test_curriculum.py"],
     "Harmonic/melodic minor, modal, jazz, secondary dominants, real-score "
     "analysis, reduction (all reserved; seventh chords went live with G1a)."),
]


def _category_nodes(root: CurriculumNode, cat_ids: List[str]) -> List[CurriculumNode]:
    out: List[CurriculumNode] = []
    for cid in cat_ids:
        node = root.find(cid)
        if node is not None:
            out.append(node)
    return out


def _leaves(nodes: List[CurriculumNode]) -> List[CurriculumNode]:
    out: List[CurriculumNode] = []
    for n in nodes:
        out.extend(n.leaves())
    return out


# ---------------------------------------------------------------------------
# Required-coverage checks (the items this maintenance pass mandates)
# ---------------------------------------------------------------------------

def _required_cadences(root: CurriculumNode) -> Dict:
    """Every catalogue cadence must appear (by tokens+mode) under Cadences."""
    cad = root.find("cat:cadences")
    present = set()
    families = {"type": set(), "progression": set()}
    for lf in (cad.leaves() if cad else []):
        es = lf.lab_spec.to_exercise_specs()
        if not es:
            continue
        pat = tuple(es[0].pattern or [])
        present.add((es[0].mode, pat))
    missing = []
    for tokens, label, mode, ctype, family in _CADENCE_CATALOG:
        key = (mode, tuple(tokens))
        ok = key in present
        if not ok:
            missing.append({"label": label, "mode": mode, "family": family})
        else:
            families[family].add(key)
    return {
        "expected": len(_CADENCE_CATALOG),
        "present": len(_CADENCE_CATALOG) - len(missing),
        "twoChordTypes": len(families["type"]),
        "progressions": len(families["progression"]),
        "missing": missing,
    }


def _required_inversions(root: CurriculumNode) -> Dict:
    """The full I/ii/IV/V x 12 major + i/iv/v/VII x 12 minor block grid must exist."""
    inv = root.find("cat:inversions")
    present = set()
    for lf in (inv.leaves() if inv else []):
        s = lf.lab_spec
        if s.concept != "inversion" or s.render != "block":
            continue
        tonic = s.key.split()[0]
        present.add((s.mode, tonic, str(s.parameters.get("degree"))))
    required = []
    for deg in _MAJOR_INV_DEGREES:
        for k in DEFAULT_MAJOR_KEYS:
            required.append(("major", k, deg))
    for deg in _MINOR_INV_DEGREES:
        for k in DEFAULT_MINOR_KEYS:
            required.append(("natural_minor", k, deg))
    missing = [{"mode": m, "key": k, "degree": d}
               for (m, k, d) in required if (m, k, d) not in present]
    return {
        "expected": len(required),
        "present": len(required) - len(missing),
        "missing": missing,
    }


# ---------------------------------------------------------------------------
# Per-category metrics
# ---------------------------------------------------------------------------

def _audit_category(root: CurriculumNode, atlas, circle_keys, key, title,
                    cat_ids, tests, expected) -> Dict:
    nodes = _category_nodes(root, cat_ids)
    leaves = _leaves(nodes)

    exercise_ids: List[str] = []
    experiment_ids: List[str] = []
    invalid_lab: List[str] = []
    invalid_bridge: List[str] = []
    empty_expl: List[str] = []
    missing_atlas: List[str] = []
    missing_circle: List[str] = []
    unresolved_atlas: List[str] = []
    unresolved_circle: List[str] = []

    for lf in leaves:
        spec = lf.lab_spec
        experiment_ids.append(spec.experiment_id)
        # lab spec validity
        try:
            spec.validate()
        except Exception as exc:  # pragma: no cover - guarded elsewhere
            invalid_lab.append(f"{lf.id}: {exc}")
        # bridge validity (compiles within the cap)
        try:
            for es in spec.to_exercise_specs():
                exercise_ids.append(es.exercise_id)
                n = len(compile_exercise(es))
                if n > MAX_CHORDS_PER_SPEC:
                    invalid_bridge.append(f"{lf.id}: {es.exercise_id} -> {n} chords")
        except Exception as exc:  # pragma: no cover
            invalid_bridge.append(f"{lf.id}: {exc}")
        # explanation completeness
        page = exercise_page(lf)
        if not (page.get("definition") or "").strip() or \
           not (page.get("musicTheory") or "").strip():
            empty_expl.append(lf.id)
        # mappings
        if not lf.atlas_nodes:
            missing_atlas.append(lf.id)
        else:
            for nid in lf.atlas_nodes:
                if atlas.node(nid) is None:
                    unresolved_atlas.append(f"{lf.id}: {nid}")
        if not lf.circle_nodes and not lf.reserved:
            missing_circle.append(lf.id)
        else:
            for ref in lf.circle_nodes:
                if ref.startswith("key:") and ref not in circle_keys:
                    unresolved_circle.append(f"{lf.id}: {ref}")

    dup_exercise = [i for i, c in Counter(exercise_ids).items() if c > 1]
    dup_experiment = [i for i, c in Counter(experiment_ids).items() if c > 1]

    # reserved categories legitimately own no exercises / mappings.
    reserved_cat = all(n.reserved for n in nodes) and bool(nodes)

    return {
        "key": key,
        "title": title,
        "categoryIds": cat_ids,
        "expected": expected,
        "actualLeaves": len(leaves),
        "reserved": reserved_cat,
        "duplicateExerciseIds": dup_exercise,
        "duplicateExperimentIds": dup_experiment,
        "invalidLabSpec": invalid_lab,
        "invalidBridge": invalid_bridge,
        "emptyExplanations": empty_expl,
        "missingAtlasMapping": missing_atlas,
        "unresolvedAtlasMapping": unresolved_atlas,
        "missingCircleMapping": missing_circle,
        "unresolvedCircleMapping": unresolved_circle,
        "tests": tests,
    }


# ---------------------------------------------------------------------------
# Audit assembly
# ---------------------------------------------------------------------------

def build_audit(root: Optional[CurriculumNode] = None) -> Dict:
    """Build the full coverage-audit report (pure, JSON-serialisable)."""
    root = root or build_curriculum()
    atlas = build_atlas()
    circle = build_circle_payload()
    circle_keys = {f"key:{e['key']}:{e['mode']}"
                   for e in (circle["majorKeys"] + circle["minorKeys"])}

    categories = [
        _audit_category(root, atlas, circle_keys, *cat) for cat in _CATEGORIES
    ]

    # Whole-tree integrity (cross-category).
    leaf_ids = [lf.id for lf in root.leaves()]
    experiment_ids = [lf.lab_spec.experiment_id for lf in root.leaves()]
    dup_leaf = [i for i, c in Counter(leaf_ids).items() if c > 1]
    dup_experiment = [i for i, c in Counter(experiment_ids).items() if c > 1]

    required = {
        "cadences": _required_cadences(root),
        "inversions": _required_inversions(root),
    }
    missing_required = (
        required["cadences"]["missing"] + required["inversions"]["missing"])

    incomplete = [c for c in categories if (
        c["duplicateExerciseIds"] or c["duplicateExperimentIds"]
        or c["invalidLabSpec"] or c["invalidBridge"]
        or (c["emptyExplanations"] and not c["reserved"])
        or (c["missingAtlasMapping"] and not c["reserved"])
        or c["unresolvedAtlasMapping"]
        or (c["missingCircleMapping"] and not c["reserved"])
        or c["unresolvedCircleMapping"])]

    return {
        "schema": SCHEMA_VERSION,
        "summary": {
            "totalLeaves": len(leaf_ids),
            "categories": len(categories),
            "duplicateLeafIds": dup_leaf,
            "duplicateExperimentIds": dup_experiment,
            "missingRequiredCount": len(missing_required),
            "incompleteCategories": [c["key"] for c in incomplete],
            "clean": not (dup_leaf or dup_experiment or missing_required or incomplete),
        },
        "required": required,
        "categories": categories,
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _yn(items) -> str:
    return "—" if not items else f"⚠ {len(items)}"


def render_markdown(audit: Dict) -> str:
    s = audit["summary"]
    lines: List[str] = []
    lines.append("# Harmony curriculum — coverage audit")
    lines.append("")
    lines.append("Auto-generated by `harmony/curriculum_audit.py` from the built "
                 "curriculum + Atlas + Circle. Re-run with "
                 "`python -m harmony.curriculum_audit`.")
    lines.append("")
    lines.append(f"- **Total exercise leaves:** {s['totalLeaves']}")
    lines.append(f"- **Audit categories:** {s['categories']}")
    lines.append(f"- **Duplicate leaf ids:** {_yn(s['duplicateLeafIds'])}")
    lines.append(f"- **Duplicate experiment ids:** {_yn(s['duplicateExperimentIds'])}")
    lines.append(f"- **Missing required nodes:** {s['missingRequiredCount']}")
    lines.append(f"- **Incomplete categories:** "
                 f"{', '.join(s['incompleteCategories']) or '—'}")
    lines.append(f"- **Overall:** {'✅ clean' if s['clean'] else '⚠ see below'}")
    lines.append("")

    # Required-coverage tables.
    rc = audit["required"]["cadences"]
    ri = audit["required"]["inversions"]
    lines.append("## Required coverage")
    lines.append("")
    lines.append(f"- **Cadences:** {rc['present']}/{rc['expected']} present "
                 f"({rc['twoChordTypes']} two-chord types, {rc['progressions']} "
                 f"progressions)."
                 + (f" Missing: {rc['missing']}" if rc['missing'] else " None missing."))
    lines.append(f"- **Inversions:** {ri['present']}/{ri['expected']} grid cells "
                 f"present." + (f" Missing: {ri['missing'][:10]}"
                               if ri['missing'] else " None missing."))
    lines.append("")

    # Per-category table.
    lines.append("## Per-category coverage")
    lines.append("")
    lines.append("| Category | Leaves | Dup ids | Invalid | Empty expl. | "
                 "Missing Atlas | Missing Circle | Tests |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for c in audit["categories"]:
        dup = _yn(c["duplicateExerciseIds"] + c["duplicateExperimentIds"])
        invalid = _yn(c["invalidLabSpec"] + c["invalidBridge"]
                      + c["unresolvedAtlasMapping"] + c["unresolvedCircleMapping"])
        empty = "—" if c["reserved"] else _yn(c["emptyExplanations"])
        m_atlas = "n/a" if c["reserved"] else _yn(c["missingAtlasMapping"])
        m_circle = "n/a" if c["reserved"] else _yn(c["missingCircleMapping"])
        lines.append(
            f"| {c['title']} | {c['actualLeaves']} | {dup} | {invalid} | "
            f"{empty} | {m_atlas} | {m_circle} | {len(c['tests'])} |")
    lines.append("")

    # Per-category detail.
    lines.append("## Per-category detail")
    for c in audit["categories"]:
        lines.append("")
        lines.append(f"### {c['title']}")
        lines.append(f"- Expected: {c['expected']}")
        lines.append(f"- Actual exercise leaves: {c['actualLeaves']}"
                     + (" (reserved — owns no exercises by design)"
                        if c["reserved"] else ""))
        for field, label in (
            ("duplicateExerciseIds", "Duplicate exercise ids"),
            ("duplicateExperimentIds", "Duplicate experiment ids"),
            ("invalidLabSpec", "Invalid LabExperimentSpec"),
            ("invalidBridge", "Invalid HarmonyExerciseSpec bridge"),
            ("emptyExplanations", "Empty explanations"),
            ("missingAtlasMapping", "Missing Atlas mapping"),
            ("unresolvedAtlasMapping", "Unresolved Atlas mapping"),
            ("missingCircleMapping", "Missing Circle mapping"),
            ("unresolvedCircleMapping", "Unresolved Circle mapping"),
        ):
            vals = c[field]
            if vals and not (c["reserved"] and field in
                             ("emptyExplanations", "missingAtlasMapping",
                              "missingCircleMapping")):
                lines.append(f"- {label}: {vals[:8]}"
                             + (" …" if len(vals) > 8 else ""))
        lines.append(f"- Tests: {', '.join(c['tests'])}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Artifact writers
# ---------------------------------------------------------------------------

_DOCS = Path(__file__).resolve().parent.parent / "docs"
_JSON_PATH = _DOCS / "harmony_curriculum_coverage_audit.json"
_MD_PATH = _DOCS / "harmony_curriculum_coverage_audit.md"


def write_artifacts(audit: Optional[Dict] = None) -> "tuple[Path, Path]":
    """Write the JSON + Markdown audit artifacts under ``docs/`` and return paths."""
    audit = audit or build_audit()
    _DOCS.mkdir(exist_ok=True)
    _JSON_PATH.write_text(json.dumps(audit, indent=2, ensure_ascii=False),
                          encoding="utf-8")
    _MD_PATH.write_text(render_markdown(audit), encoding="utf-8")
    return _JSON_PATH, _MD_PATH


if __name__ == "__main__":
    j, m = write_artifacts()
    print(f"wrote {j}")
    print(f"wrote {m}")
