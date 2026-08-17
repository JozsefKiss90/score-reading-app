"""Wiki vault validator (theory-wiki ticket 02).

Mechanises the lint checklist in ``wiki/CLAUDE.md``: frontmatter schema,
wikilink resolution, orphan detection, index sync, template completeness,
and reference validity -- ``lab_refs`` against the live curriculum tree,
``atlas_refs`` against the documented Atlas-surface vocabulary below.

The validator only *reads* the app (one-directional reference invariant):
it imports ``harmony.curriculum`` to enumerate valid node ids and never
touches Lab / Atlas / trainer / curriculum code.

Run from the repo root::

    python -m tools.validate_wiki            # validates wiki/
    python -m tools.validate_wiki --vault P  # validates another vault

Exit code 0 when clean, 1 when any violation is found.
"""

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml

# ---------------------------------------------------------------------------
# Schema vocabulary (mirrors wiki/CLAUDE.md; enums are append-only there)
# ---------------------------------------------------------------------------

DOMAINS = [
    "fundamentals", "intervals", "scales-keys", "chords", "harmony",
    "cadences", "minor-modes", "sevenths", "chromaticism", "musicianship",
    "glossary",
]

TYPES = ["concept", "lesson-support", "glossary", "hub"]
LEVELS = ["foundation", "core", "advanced"]
STATUSES = ["active", "stub", "draft"]

REQUIRED_KEYS = ["type", "domain", "level", "status", "created", "updated",
                 "lab_refs", "atlas_refs"]
OPTIONAL_KEYS = ["aliases"]

#: Structural files: not pages, exempt from per-page checks.
STRUCTURAL = {"index.md", "log.md", "CLAUDE.md"}

#: Template sections required on ``status: active`` canonical pages
#: (types ``concept`` / ``lesson-support``), in order.  "In the Atlas" is the
#: one section the template itself marks omittable ("omit if none").
TEMPLATE_SECTIONS = [
    "Definition", "Why it matters", "Prerequisites", "Explanation",
    "In the Lab", "In the Atlas", "Common confusions", "Related Concepts",
]
OMITTABLE_SECTIONS = {"In the Atlas"}

#: The documented Atlas-surface vocabulary: every id a page may cite in
#: ``atlas_refs``.  Surfaces, not fine-grained Atlas node ids -- a page sends
#: the student to a *place in the app*, not to one node of its ontology.
ATLAS_SURFACES: Dict[str, str] = {
    # Harmony Atlas parts (harmony/atlas.py Atlas view methods).
    "atlas:global-map": "Atlas Part I -- Global Diatonic Map",
    "atlas:transposition-matrix": "Atlas Part II -- Transposition Matrix",
    "atlas:quality-matrix": "Atlas Part III -- Quality Matrix",
    "atlas:function-map": "Atlas Part IV -- Function Map (T/PD/D)",
    "atlas:interval-layer-map": "Atlas Part V -- Interval-Layer Map",
    "atlas:cadence-map": "Atlas Part VI -- Cadence Map",
    "atlas:progress-map": "Atlas Part IX -- Progress Map",
    "atlas:graph": "Atlas Part X -- Graph view",
    "atlas:learning-path": "Atlas Part XI -- Learning Path",
    # Circle of Fifths (harmony/circle_payload.py + beat_selector view).
    "circle:fifths": "Circle of Fifths view",
    # Network / graph launchers.
    "network:harmonic": "Tonal Graph launcher (run_harmonic_network_demo.py)",
    "network:functional":
        "Functional Journey launcher (run_functional_network_demo.py)",
    "network:score-soul":
        "Score Soul Graph launcher (run_score_harmonic_network_demo.py)",
}

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class Violation:
    check: str      # frontmatter | wikilink | orphan | index | template | lab_ref | atlas_ref
    page: str       # vault-relative path (or "index.md")
    message: str

    def __str__(self) -> str:
        return f"[{self.check}] {self.page}: {self.message}"


@dataclass
class _Page:
    rel: str                     # vault-relative path, forward slashes
    name: str                    # file stem ("Circle of Fifths")
    directory: str               # first path component ("scales-keys")
    frontmatter: Optional[dict]  # None when missing/unparseable
    body: str                    # content after the frontmatter block
    links: List[str]             # wikilink targets (display text stripped)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _split_frontmatter(text: str):
    """Return (frontmatter dict or None, body)."""
    if not text.startswith("---"):
        return None, text
    match = re.match(r"^---\n(.*?)\n---\n?", text, flags=re.S)
    if not match:
        return None, text
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None, text[match.end():]
    if not isinstance(data, dict):
        return None, text[match.end():]
    return data, text[match.end():]


def _extract_links(body: str) -> List[str]:
    """Wikilink targets in ``body``, code fences and inline code ignored."""
    prose = re.sub(r"```.*?```", "", body, flags=re.S)
    prose = re.sub(r"`[^`\n]*`", "", prose)
    targets = []
    for raw in _WIKILINK_RE.findall(prose):
        target = raw.split("|")[0].split("#")[0].split("^")[0].strip()
        if target:
            targets.append(target)
    return targets


def _load_pages(vault: Path) -> List[_Page]:
    pages = []
    for path in sorted(vault.rglob("*.md")):
        rel = path.relative_to(vault).as_posix()
        if rel.split("/")[0] == ".obsidian" or rel in STRUCTURAL:
            continue
        text = path.read_text(encoding="utf-8")
        front, body = _split_frontmatter(text)
        parts = rel.split("/")
        pages.append(_Page(
            rel=rel,
            name=path.stem,
            directory=parts[0] if len(parts) > 1 else "",
            frontmatter=front,
            body=body,
            links=_extract_links(body),
        ))
    return pages


# ---------------------------------------------------------------------------
# Per-check validators
# ---------------------------------------------------------------------------

def _is_flat_string_list(value) -> bool:
    return (isinstance(value, list)
            and all(isinstance(item, str) for item in value))


def _is_date(value) -> bool:
    return isinstance(value, date) or (
        isinstance(value, str) and bool(_DATE_RE.match(value)))


def _check_frontmatter(pages: List[_Page]) -> List[Violation]:
    out = []
    for p in pages:
        if p.frontmatter is None:
            out.append(Violation("frontmatter", p.rel,
                                 "missing or unparseable frontmatter block"))
            continue
        front = p.frontmatter
        allowed = set(REQUIRED_KEYS) | set(OPTIONAL_KEYS)
        for key in sorted(set(front) - allowed):
            out.append(Violation("frontmatter", p.rel, f"unknown key '{key}'"))
        for key in REQUIRED_KEYS:
            if key not in front:
                out.append(Violation("frontmatter", p.rel,
                                     f"missing required key '{key}'"))
        for key, enum in (("type", TYPES), ("domain", DOMAINS),
                          ("level", LEVELS), ("status", STATUSES)):
            value = front.get(key)
            if key in front and value not in enum:
                out.append(Violation(
                    "frontmatter", p.rel,
                    f"invalid {key} '{value}' (allowed: {', '.join(enum)})"))
        domain = front.get("domain")
        if domain in DOMAINS and domain != p.directory:
            out.append(Violation(
                "frontmatter", p.rel,
                f"domain '{domain}' does not match directory "
                f"'{p.directory or '(vault root)'}'"))
        elif p.directory not in DOMAINS:
            out.append(Violation(
                "frontmatter", p.rel,
                f"page is not inside a domain folder "
                f"(found '{p.directory or '(vault root)'}')"))
        for key in ("created", "updated"):
            if key in front and not _is_date(front[key]):
                out.append(Violation(
                    "frontmatter", p.rel,
                    f"'{key}' must be a YYYY-MM-DD date, got "
                    f"{front[key]!r}"))
        for key in ("aliases", "lab_refs", "atlas_refs"):
            if key in front and not _is_flat_string_list(front[key]):
                out.append(Violation(
                    "frontmatter", p.rel,
                    f"'{key}' must be a flat list of strings"))
    return out


def _link_index(pages: List[_Page]) -> Dict[str, _Page]:
    """Lower-cased name/alias -> page, for case-insensitive resolution."""
    index: Dict[str, _Page] = {}
    for p in pages:
        index[p.name.lower()] = p
        aliases = (p.frontmatter or {}).get("aliases")
        if _is_flat_string_list(aliases):
            for alias in aliases:
                index[alias.lower()] = p
    return index


def _resolve(target: str, links: Dict[str, _Page]) -> Optional[_Page]:
    # Accept both "Page Name" and Obsidian's "folder/Page Name" forms.
    return links.get(target.lower()) or links.get(
        target.rsplit("/", 1)[-1].lower())


def _check_wikilinks(pages, links) -> List[Violation]:
    out = []
    for p in pages:
        for target in p.links:
            if _resolve(target, links) is None:
                out.append(Violation(
                    "wikilink", p.rel,
                    f"[[{target}]] does not resolve to any page or alias"))
    return out


def _check_orphans(pages, links) -> List[Violation]:
    inbound: Set[str] = set()
    for p in pages:
        for target in p.links:
            resolved = _resolve(target, links)
            if resolved is not None and resolved.rel != p.rel:
                inbound.add(resolved.rel)
    out = []
    for p in pages:
        front = p.frontmatter or {}
        if front.get("status") != "active" or front.get("type") == "hub":
            continue
        if p.rel not in inbound:
            out.append(Violation(
                "orphan", p.rel,
                "active page has no inbound wikilinks (hub pages excepted)"))
    return out


def _check_template(pages) -> List[Violation]:
    out = []
    for p in pages:
        front = p.frontmatter or {}
        if front.get("status") != "active":
            continue
        if front.get("type") not in ("concept", "lesson-support"):
            continue
        headings = re.findall(r"^##\s+(.+?)\s*$", p.body, flags=re.M)
        positions = {h: i for i, h in enumerate(headings)}
        last = -1
        for section in TEMPLATE_SECTIONS:
            if section not in positions:
                if section in OMITTABLE_SECTIONS:
                    continue
                out.append(Violation(
                    "template", p.rel,
                    f"active page is missing section '## {section}'"))
                continue
            if positions[section] < last:
                out.append(Violation(
                    "template", p.rel,
                    f"section '## {section}' is out of template order"))
            last = positions[section]
    return out


def _check_index(vault: Path, pages, links) -> List[Violation]:
    index_path = vault / "index.md"
    if not index_path.exists():
        return [Violation("index", "index.md", "index.md is missing")]
    text = index_path.read_text(encoding="utf-8")
    targets = _extract_links(text)
    listed: Set[str] = set()
    out = []
    for target in targets:
        resolved = _resolve(target, links)
        if resolved is None:
            out.append(Violation(
                "index", "index.md",
                f"lists [[{target}]] which is not an existing page (ghost)"))
        else:
            listed.add(resolved.rel)
    for p in pages:
        if p.rel not in listed:
            out.append(Violation(
                "index", "index.md", f"does not list page {p.rel}"))
    return out


def _check_lab_refs(pages, curriculum_ids: Set[str]) -> List[Violation]:
    out = []
    for p in pages:
        refs = (p.frontmatter or {}).get("lab_refs")
        if not _is_flat_string_list(refs):
            continue  # shape already reported by the frontmatter check
        for ref in refs:
            if ref not in curriculum_ids:
                out.append(Violation(
                    "lab_ref", p.rel,
                    f"'{ref}' is not a node id in the live curriculum tree"))
    return out


def _check_atlas_refs(pages, surfaces: Dict[str, str]) -> List[Violation]:
    out = []
    for p in pages:
        refs = (p.frontmatter or {}).get("atlas_refs")
        if not _is_flat_string_list(refs):
            continue
        for ref in refs:
            if ref not in surfaces:
                out.append(Violation(
                    "atlas_ref", p.rel,
                    f"'{ref}' is not in the Atlas-surface vocabulary "
                    f"(see tools/validate_wiki.py ATLAS_SURFACES)"))
    return out


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def _load_curriculum_ids() -> Set[str]:
    """Every node id in the live curriculum tree (read-only import)."""
    from harmony.curriculum import get_curriculum
    return {node.id for node in get_curriculum().walk()}


def validate_vault(vault: Path,
                   curriculum_ids: Optional[Set[str]] = None,
                   atlas_surfaces: Optional[Dict[str, str]] = None,
                   ) -> List[Violation]:
    """Run every lint check against ``vault`` and return the violations.

    ``curriculum_ids`` is injectable for tests; when ``None`` the live tree
    is built lazily, and only if some page actually cites a ``lab_refs`` id.
    """
    vault = Path(vault)
    pages = _load_pages(vault)
    links = _link_index(pages)
    surfaces = ATLAS_SURFACES if atlas_surfaces is None else atlas_surfaces

    violations = _check_frontmatter(pages)
    violations += _check_wikilinks(pages, links)
    violations += _check_orphans(pages, links)
    violations += _check_template(pages)
    violations += _check_index(vault, pages, links)
    if curriculum_ids is None:
        if any(_is_flat_string_list((p.frontmatter or {}).get("lab_refs"))
               and (p.frontmatter or {})["lab_refs"] for p in pages):
            curriculum_ids = _load_curriculum_ids()
        else:
            curriculum_ids = set()
    violations += _check_lab_refs(pages, curriculum_ids)
    violations += _check_atlas_refs(pages, surfaces)
    violations.sort(key=lambda v: (v.check, v.page, v.message))
    return violations


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the music-theory wiki vault.")
    parser.add_argument(
        "--vault",
        default=str(Path(__file__).resolve().parents[1] / "wiki"),
        help="vault directory (default: <repo>/wiki)")
    parser.add_argument(
        "--list-refs", action="store_true",
        help="print every valid atlas_refs surface id and lab_refs "
             "curriculum node id, then exit")
    ns = parser.parse_args(argv)
    if ns.list_refs:
        print("# atlas_refs vocabulary")
        for ref, blurb in ATLAS_SURFACES.items():
            print(f"  {ref:28} {blurb}")
        print("# lab_refs vocabulary (live curriculum node ids)")
        for node_id in sorted(_load_curriculum_ids()):
            print(f"  {node_id}")
        return 0
    vault = Path(ns.vault)
    if not vault.is_dir():
        print(f"wiki validator: vault not found: {vault}")
        return 1
    violations = validate_vault(vault)
    page_count = len(_load_pages(vault))
    if not violations:
        print(f"wiki validator: OK ({page_count} page(s) checked)")
        return 0
    print(f"wiki validator: {len(violations)} violation(s) "
          f"across {page_count} page(s)")
    for v in violations:
        print(f"  {v}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
