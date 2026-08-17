"""Tests for the wiki vault validator (theory-wiki ticket 02).

Seam under test: ``tools.validate_wiki.validate_vault`` -- a pure function
from a vault directory to a list of violations -- plus the CLI ``main``.
Temp vaults are built per test; the real curriculum is only loaded by the
lab_refs tests (injected everywhere else to keep the suite fast).
"""

import textwrap
from pathlib import Path

from tools.validate_wiki import ATLAS_SURFACES, Violation, main, validate_vault


# ---------------------------------------------------------------------------
# Temp-vault helpers
# ---------------------------------------------------------------------------

def fm(**over):
    """A valid frontmatter block, with per-test overrides.

    An override value of ``None`` drops the key entirely; a raw string is
    emitted verbatim after ``key: ``.
    """
    fields = {
        "type": "concept",
        "domain": "chords",
        "level": "core",
        "status": "active",
        "created": "2026-08-17",
        "updated": "2026-08-17",
        "aliases": "[]",
        "lab_refs": "[]",
        "atlas_refs": "[]",
    }
    fields.update(over)
    lines = ["---"]
    for key, value in fields.items():
        if value is None:
            continue
        lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n"


ALL_SECTIONS = textwrap.dedent("""\
    ## Definition
    x
    ## Why it matters
    x
    ## Prerequisites
    x
    ## Explanation
    x
    ## In the Lab
    x
    ## In the Atlas
    x
    ## Common confusions
    x
    ## Related Concepts
    x
    """)


def page(front, title="Page", body=""):
    return front + f"# {title}\n\n" + body + "\n" + ALL_SECTIONS


def make_vault(tmp_path, pages, index=None):
    """Write ``pages`` ({relpath: content}) plus an index listing them all."""
    vault = tmp_path / "wiki"
    vault.mkdir(parents=True, exist_ok=True)
    for rel, content in pages.items():
        target = vault / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    if index is None:
        links = "\n".join(f"| [[{p.rsplit('/', 1)[-1][:-3]}]] | x |"
                          for p in pages)
        index = "# Index\n\n| Page | Summary |\n|---|---|\n" + links + "\n"
    (vault / "index.md").write_text(index, encoding="utf-8")
    (vault / "log.md").write_text("# Log\n", encoding="utf-8")
    return vault


def run(vault, **kw):
    kw.setdefault("curriculum_ids", set())
    return validate_vault(vault, **kw)


def checks_of(violations):
    return {v.check for v in violations}


# Two active pages that link each other: clean under every check.
def two_linked_pages():
    return {
        "chords/Triad.md": page(fm(), "Triad", "See [[Chord Quality]].\n"),
        "chords/Chord Quality.md": page(
            fm(), "Chord Quality", "A [[Triad]] has a quality.\n"),
    }


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------

def test_clean_vault_has_no_violations(tmp_path):
    vault = make_vault(tmp_path, two_linked_pages())
    assert run(vault) == []


# ---------------------------------------------------------------------------
# Frontmatter checks
# ---------------------------------------------------------------------------

def test_missing_frontmatter_fails(tmp_path):
    pages = two_linked_pages()
    pages["chords/Triad.md"] = "# Triad\n\nSee [[Chord Quality]].\n"
    vault = make_vault(tmp_path, pages)
    violations = [v for v in run(vault) if v.check == "frontmatter"]
    assert violations and "chords/Triad.md" in violations[0].page


def test_invalid_enum_value_fails(tmp_path):
    pages = two_linked_pages()
    pages["chords/Triad.md"] = page(
        fm(level="bogus"), "Triad", "See [[Chord Quality]].\n")
    vault = make_vault(tmp_path, pages)
    assert any(v.check == "frontmatter" and "level" in v.message
               for v in run(vault))


def test_domain_directory_mismatch_fails(tmp_path):
    pages = two_linked_pages()
    pages["chords/Triad.md"] = page(
        fm(domain="harmony"), "Triad", "See [[Chord Quality]].\n")
    vault = make_vault(tmp_path, pages)
    assert any(v.check == "frontmatter" and "domain" in v.message
               for v in run(vault))


def test_unknown_frontmatter_key_fails(tmp_path):
    pages = two_linked_pages()
    pages["chords/Triad.md"] = page(
        fm(extra_key="nope"), "Triad", "See [[Chord Quality]].\n")
    vault = make_vault(tmp_path, pages)
    assert any(v.check == "frontmatter" and "extra_key" in v.message
               for v in run(vault))


def test_missing_required_key_fails(tmp_path):
    pages = two_linked_pages()
    pages["chords/Triad.md"] = page(
        fm(lab_refs=None), "Triad", "See [[Chord Quality]].\n")
    vault = make_vault(tmp_path, pages)
    assert any(v.check == "frontmatter" and "lab_refs" in v.message
               for v in run(vault))


def test_page_outside_domain_folder_fails(tmp_path):
    pages = two_linked_pages()
    pages["Stray.md"] = page(fm(), "Stray", "See [[Triad]].\n")
    vault = make_vault(tmp_path, pages)
    assert any(v.check == "frontmatter" and "Stray.md" in v.page
               for v in run(vault))


# ---------------------------------------------------------------------------
# Wikilink checks
# ---------------------------------------------------------------------------

def test_broken_wikilink_fails(tmp_path):
    pages = two_linked_pages()
    pages["chords/Triad.md"] = page(
        fm(), "Triad", "See [[Chord Quality]] and [[Nonexistent Page]].\n")
    vault = make_vault(tmp_path, pages)
    violations = [v for v in run(vault) if v.check == "wikilink"]
    assert violations and "Nonexistent Page" in violations[0].message


def test_wikilink_resolves_via_alias_and_display_text(tmp_path):
    pages = two_linked_pages()
    pages["chords/Chord Quality.md"] = page(
        fm(aliases='["Quality of a Chord"]'), "Chord Quality",
        "A [[Triad]] has a quality.\n")
    pages["chords/Triad.md"] = page(
        fm(), "Triad", "See [[Quality of a Chord|qualities]].\n")
    vault = make_vault(tmp_path, pages)
    assert not [v for v in run(vault) if v.check == "wikilink"]


def test_wikilinks_inside_code_fences_ignored(tmp_path):
    pages = two_linked_pages()
    pages["chords/Triad.md"] = page(
        fm(), "Triad",
        "See [[Chord Quality]].\n\n```\n[[Not A Link]]\n```\n")
    vault = make_vault(tmp_path, pages)
    assert not [v for v in run(vault) if v.check == "wikilink"]


def test_folder_qualified_wikilink_is_rejected(tmp_path):
    pages = two_linked_pages()
    pages["chords/Triad.md"] = page(
        fm(), "Triad", "See [[Chord Quality]] and [[chords/Chord Quality]].\n")
    vault = make_vault(tmp_path, pages)
    violations = [v for v in run(vault) if v.check == "wikilink"]
    assert [("chords/Chord Quality" in v.message) for v in violations] == [True]


def test_duplicate_page_name_across_domains_fails(tmp_path):
    pages = two_linked_pages()
    pages["harmony/Triad.md"] = page(
        fm(domain="harmony"), "Triad", "See [[Chord Quality]].\n")
    vault = make_vault(tmp_path, pages)
    assert any(v.check == "duplicate" for v in run(vault))


def test_alias_colliding_with_page_name_fails(tmp_path):
    pages = two_linked_pages()
    pages["chords/Triad.md"] = page(
        fm(aliases='["Chord Quality"]'), "Triad", "See [[Chord Quality]].\n")
    vault = make_vault(tmp_path, pages)
    assert any(v.check == "duplicate" and "Chord Quality" in v.message
               for v in run(vault))


def test_page_nested_below_domain_folder_fails(tmp_path):
    pages = two_linked_pages()
    pages["chords/deep/Nested.md"] = page(
        fm(), "Nested", "See [[Triad]].\n")
    vault = make_vault(tmp_path, pages)
    assert any(v.check == "frontmatter" and "chords/deep/Nested.md" == v.page
               for v in run(vault))


# ---------------------------------------------------------------------------
# Orphan checks
# ---------------------------------------------------------------------------

def test_active_page_with_no_inbound_links_is_orphan(tmp_path):
    pages = two_linked_pages()
    pages["harmony/Lonely.md"] = page(
        fm(domain="harmony"), "Lonely", "See [[Triad]].\n")
    vault = make_vault(tmp_path, pages)
    violations = [v for v in run(vault) if v.check == "orphan"]
    assert [v.page for v in violations] == ["harmony/Lonely.md"]


def test_hub_and_stub_pages_are_exempt_from_orphan_check(tmp_path):
    pages = two_linked_pages()
    pages["harmony/Hub Page.md"] = page(
        fm(domain="harmony", type="hub"), "Hub Page", "See [[Triad]].\n")
    pages["harmony/Stubby.md"] = (
        fm(domain="harmony", status="stub") + "# Stubby\n\nOne line.\n")
    vault = make_vault(tmp_path, pages)
    assert not [v for v in run(vault) if v.check == "orphan"]


def test_self_link_does_not_rescue_orphan(tmp_path):
    pages = two_linked_pages()
    pages["harmony/Lonely.md"] = page(
        fm(domain="harmony"), "Lonely", "See [[Lonely]] and [[Triad]].\n")
    vault = make_vault(tmp_path, pages)
    assert [v.page for v in run(vault) if v.check == "orphan"] == [
        "harmony/Lonely.md"]


# ---------------------------------------------------------------------------
# Template checks
# ---------------------------------------------------------------------------

def test_active_concept_page_missing_section_fails(tmp_path):
    pages = two_linked_pages()
    body = ALL_SECTIONS.replace("## Common confusions\nx\n", "")
    pages["chords/Triad.md"] = (
        fm() + "# Triad\n\nSee [[Chord Quality]].\n" + body)
    vault = make_vault(tmp_path, pages)
    violations = [v for v in run(vault) if v.check == "template"]
    assert violations and "Common confusions" in violations[0].message


def test_in_the_atlas_section_is_omittable(tmp_path):
    pages = two_linked_pages()
    body = ALL_SECTIONS.replace("## In the Atlas\nx\n", "")
    pages["chords/Triad.md"] = (
        fm() + "# Triad\n\nSee [[Chord Quality]].\n" + body)
    vault = make_vault(tmp_path, pages)
    assert not [v for v in run(vault) if v.check == "template"]


def test_template_heading_inside_code_fence_does_not_count(tmp_path):
    pages = two_linked_pages()
    body = ALL_SECTIONS.replace(
        "## Common confusions\nx\n",
        "```\n## Common confusions\n```\n")
    pages["chords/Triad.md"] = (
        fm() + "# Triad\n\nSee [[Chord Quality]].\n" + body)
    vault = make_vault(tmp_path, pages)
    violations = [v for v in run(vault) if v.check == "template"]
    assert violations and "Common confusions" in violations[0].message


def test_stub_glossary_and_hub_pages_skip_template_check(tmp_path):
    pages = two_linked_pages()
    pages["glossary/Glossary.md"] = (
        fm(domain="glossary", type="glossary")
        + "# Glossary\n\n[[Triad]] entries.\n")
    pages["chords/Stub Concept.md"] = (
        fm(status="stub") + "# Stub Concept\n\nOne line.\n")
    pages["chords/Triad.md"] = page(
        fm(), "Triad",
        "See [[Chord Quality]], [[Glossary]], [[Stub Concept]].\n")
    vault = make_vault(tmp_path, pages)
    assert not [v for v in run(vault) if v.check == "template"]


# ---------------------------------------------------------------------------
# Index sync checks
# ---------------------------------------------------------------------------

def test_page_missing_from_index_fails(tmp_path):
    pages = two_linked_pages()
    index = ("# Index\n\n| Page | Summary |\n|---|---|\n"
             "| [[Triad]] | x |\n")
    vault = make_vault(tmp_path, pages, index=index)
    violations = [v for v in run(vault) if v.check == "index"]
    assert violations and "Chord Quality" in violations[0].message


def test_index_ghost_entry_fails(tmp_path):
    pages = two_linked_pages()
    index = ("# Index\n\n| Page | Summary |\n|---|---|\n"
             "| [[Triad]] | x |\n| [[Chord Quality]] | x |\n"
             "| [[Deleted Page]] | x |\n")
    vault = make_vault(tmp_path, pages, index=index)
    violations = [v for v in run(vault) if v.check == "index"]
    assert violations and "Deleted Page" in violations[0].message


def test_missing_index_file_fails(tmp_path):
    vault = make_vault(tmp_path, two_linked_pages())
    (vault / "index.md").unlink()
    assert any(v.check == "index" and "missing" in v.message
               for v in run(vault))


# ---------------------------------------------------------------------------
# lab_refs / atlas_refs checks
# ---------------------------------------------------------------------------

def test_lab_refs_validated_against_supplied_ids(tmp_path):
    pages = two_linked_pages()
    pages["chords/Triad.md"] = page(
        fm(lab_refs='["cat:chords", "ex:bogus_id"]'), "Triad",
        "See [[Chord Quality]].\n")
    vault = make_vault(tmp_path, pages)
    violations = [v for v in run(vault, curriculum_ids={"cat:chords"})
                  if v.check == "lab_ref"]
    assert [("ex:bogus_id" in v.message) for v in violations] == [True]


def test_atlas_refs_validated_against_surface_vocabulary(tmp_path):
    pages = two_linked_pages()
    pages["chords/Triad.md"] = page(
        fm(atlas_refs='["atlas:global-map", "atlas:not-a-surface"]'),
        "Triad", "See [[Chord Quality]].\n")
    vault = make_vault(tmp_path, pages)
    violations = [v for v in run(vault) if v.check == "atlas_ref"]
    assert [("atlas:not-a-surface" in v.message) for v in violations] == [True]


def test_lab_refs_checked_against_live_curriculum_when_not_injected(tmp_path):
    pages = two_linked_pages()
    pages["chords/Triad.md"] = page(
        fm(lab_refs='["cat:chords", "cat:no_such_category"]'), "Triad",
        "See [[Chord Quality]].\n")
    vault = make_vault(tmp_path, pages)
    violations = [v for v in validate_vault(vault) if v.check == "lab_ref"]
    assert len(violations) == 1 and "cat:no_such_category" in violations[0].message


# ---------------------------------------------------------------------------
# CLI + real vault
# ---------------------------------------------------------------------------

def test_main_exit_codes(tmp_path, capsys):
    vault = make_vault(tmp_path, two_linked_pages())
    assert main(["--vault", str(vault)]) == 0
    assert "OK" in capsys.readouterr().out

    broken = two_linked_pages()
    broken["chords/Triad.md"] = page(
        fm(), "Triad", "See [[Chord Quality]] and [[Nowhere]].\n")
    vault2 = make_vault(tmp_path / "second", broken)
    assert main(["--vault", str(vault2)]) == 1
    out = capsys.readouterr().out
    assert "violation" in out and "Nowhere" in out


def test_real_vault_is_clean():
    repo = Path(__file__).resolve().parents[1]
    violations = validate_vault(repo / "wiki")
    assert violations == [], "\n".join(str(v) for v in violations)


def test_list_refs_prints_vocabularies(capsys):
    assert main(["--list-refs"]) == 0
    out = capsys.readouterr().out
    assert "atlas:global-map" in out
    assert "circle:fifths" in out
    assert "cat:chords" in out and "ex:" in out


def test_atlas_surface_vocabulary_is_nonempty_and_prefixed():
    assert ATLAS_SURFACES
    assert all(ref.split(":")[0] in ("atlas", "circle", "network")
               for ref in ATLAS_SURFACES)
