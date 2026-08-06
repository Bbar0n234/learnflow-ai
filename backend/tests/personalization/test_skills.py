"""Solitary-unit tests for the skills loader (``agent/tools/skills.py``).

These are pure filesystem functions over a skills directory: a ``load_skill``
tool that fetches one ``SKILL.md`` by name (with name-validation and path-escape
defense), an index scanner over frontmatter, and a frontmatter parser. We build a
throwaway skills tree under ``tmp_path`` and assert returned strings — no mocks,
no network.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.agent.tools.skills import (
    make_load_skill_tool,
    scan_skills_index,
)

_SKILL_BODY = """---
name: alpha-skill
description: |
  Helps  with    alpha   things.
---

# Alpha

Do alpha work.
"""


def _write_skill(root: Path, name: str, body: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")


def _write_skill_file(
    root: Path,
    skill: str,
    relpath: str,
    content: str | None = None,
    *,
    binary: bytes | None = None,
) -> None:
    path = root / skill / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    if binary is not None:
        path.write_bytes(binary)
    else:
        assert content is not None
        path.write_text(content, encoding="utf-8")


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    root.mkdir()
    _write_skill(root, "alpha-skill", _SKILL_BODY)
    return root


_MULTI_BODY = """---
name: multi-skill
description: Multi-file skill.
---

# Multi

multi body content.
"""


@pytest.fixture
def multifile_skills_dir(skills_dir: Path) -> Path:
    """A skills tree with one multi-file skill plus a neighbor to escape into.

    ``multi-skill`` carries markdown modules (top-level and nested), a
    non-markdown module, a binary blob, and a dotfile. ``neighbor`` sits
    beside it under the same skills root and holds a marker string; a path
    that escapes ``multi-skill``'s directory would reach it, so tests assert
    the marker never leaks.
    """
    _write_skill(skills_dir, "multi-skill", _MULTI_BODY)
    _write_skill_file(skills_dir, "multi-skill", "b-module.md", "B module content.")
    _write_skill_file(skills_dir, "multi-skill", "a-module.md", "A module content.")
    _write_skill_file(skills_dir, "multi-skill", "helper.py", "print('helper')\n")
    _write_skill_file(
        skills_dir, "multi-skill", "sub/c-module.md", "C nested module content."
    )
    _write_skill_file(skills_dir, "multi-skill", ".hidden", "secret dotfile body")
    _write_skill_file(
        skills_dir, "multi-skill", "data.bin", binary=b"\xff\xfe\x00\x01BINARY"
    )
    _write_skill(
        skills_dir,
        "neighbor",
        _MULTI_BODY.replace("multi body content.", "NEIGHBOR-SECRET"),
    )
    return skills_dir


_FOOTER_HINT = "Skill files (load with load_skill(skill_name, file)):"


def _footer_entries(content: str) -> list[str]:
    """Extract the bullet-listed file paths from a load_skill footer."""
    _, _, footer = content.partition(_FOOTER_HINT)
    return [line[2:] for line in footer.splitlines() if line.startswith("- ")]


@pytest.mark.unit
async def test_load_skill_returns_full_content(skills_dir: Path) -> None:
    tool = make_load_skill_tool(skills_dir)

    content = await tool.ainvoke({"skill_name": "alpha-skill"})

    assert "Do alpha work." in content


@pytest.mark.unit
async def test_load_skill_unknown_name_reports_available(skills_dir: Path) -> None:
    tool = make_load_skill_tool(skills_dir)

    content = await tool.ainvoke({"skill_name": "missing-skill"})

    assert "not found" in content
    assert "alpha-skill" in content  # lists what is available


@pytest.mark.unit
@pytest.mark.parametrize("bad_name", ["../etc", "Alpha Skill", "a/b", "UPPER", "x.y"])
async def test_load_skill_rejects_invalid_names(
    skills_dir: Path, bad_name: str
) -> None:
    tool = make_load_skill_tool(skills_dir)

    content = await tool.ainvoke({"skill_name": bad_name})

    # Rejected before any read; never returns skill content.
    assert content.startswith("Error: invalid skill name")
    assert "Do alpha work." not in content


@pytest.mark.unit
async def test_scan_skills_index_lists_name_and_normalized_description(
    skills_dir: Path,
) -> None:
    index = scan_skills_index(skills_dir)

    assert "Available Skills:" in index
    # Frontmatter whitespace collapsed to single spaces.
    assert "- alpha-skill: Helps with alpha things." in index


@pytest.mark.unit
async def test_scan_skills_index_skips_dirs_without_frontmatter(
    skills_dir: Path,
) -> None:
    _write_skill(skills_dir, "no-front", "# Plain\n\nNo frontmatter here.")

    index = scan_skills_index(skills_dir)

    assert "alpha-skill" in index
    assert "no-front" not in index


@pytest.mark.unit
async def test_scan_skills_index_empty_for_missing_dir(tmp_path: Path) -> None:
    assert scan_skills_index(tmp_path / "does-not-exist") == ""


# --- Autolist footer (load_skill without `file`) -----------------------------


@pytest.mark.unit
async def test_load_skill_footer_lists_files_recursive_sorted(
    multifile_skills_dir: Path,
) -> None:
    tool = make_load_skill_tool(multifile_skills_dir)

    content = await tool.ainvoke({"skill_name": "multi-skill"})

    # SKILL.md content still returned in full, footer appended after it.
    assert "multi body content." in content
    # Recursive (sub/c-module.md), sorted, any extension (helper.py, data.bin),
    # excludes SKILL.md and the dotfile.
    assert _footer_entries(content) == [
        "a-module.md",
        "b-module.md",
        "data.bin",
        "helper.py",
        "sub/c-module.md",
    ]


@pytest.mark.unit
async def test_load_skill_footer_excludes_skill_md_and_dotfiles(
    multifile_skills_dir: Path,
) -> None:
    tool = make_load_skill_tool(multifile_skills_dir)

    content = await tool.ainvoke({"skill_name": "multi-skill"})

    entries = _footer_entries(content)
    # Positive anchor: the footer is present and non-empty, so the exclusion
    # asserts below run against a real list rather than passing vacuously.
    assert _FOOTER_HINT in content
    assert "a-module.md" in entries
    assert "SKILL.md" not in entries
    assert ".hidden" not in entries
    # dotfile body is never disclosed anywhere in the response.
    assert "secret dotfile body" not in content


@pytest.mark.unit
async def test_load_skill_binary_module_still_visible_in_footer(
    multifile_skills_dir: Path,
) -> None:
    tool = make_load_skill_tool(multifile_skills_dir)

    content = await tool.ainvoke({"skill_name": "multi-skill"})

    # Agent must know the binary module exists even though it can't be read.
    assert "data.bin" in _footer_entries(content)


@pytest.mark.unit
async def test_load_skill_footer_excludes_symlink_escaping_dir(
    multifile_skills_dir: Path,
) -> None:
    """Autolist counterpart to ``test_load_skill_file_rejects_symlink_escape``.

    That test asserts the *load* path refuses a symlink resolving outside the
    skill dir; this one asserts the *listing* path never advertises it. A
    symlink whose ``resolve()`` leaves the skill directory is dropped from the
    footer — the autolist only offers what ``load_skill(skill_name, file)``
    could actually load — while genuine in-dir modules stay listed.
    """
    skill_dir = multifile_skills_dir / "multi-skill"
    escape_target = multifile_skills_dir / "neighbor" / "SKILL.md"
    link = skill_dir / "link.md"
    try:
        link.symlink_to(escape_target)
    except OSError as exc:  # pragma: no cover - platform/filesystem dependent
        pytest.skip(f"symlinks unavailable in this environment: {exc}")

    tool = make_load_skill_tool(multifile_skills_dir)

    content = await tool.ainvoke({"skill_name": "multi-skill"})

    entries = _footer_entries(content)
    # Positive anchor: real modules are still advertised, so the exclusion
    # below runs against a populated footer rather than passing vacuously.
    assert "a-module.md" in entries
    # The escaping symlink is filtered out, and its target's secret never leaks.
    assert "link.md" not in entries
    assert "NEIGHBOR-SECRET" not in content


@pytest.mark.unit
async def test_load_skill_single_file_skill_omits_footer(skills_dir: Path) -> None:
    tool = make_load_skill_tool(skills_dir)

    content = await tool.ainvoke({"skill_name": "alpha-skill"})

    # Regression: response for a module-less skill is unchanged (no footer).
    assert "Do alpha work." in content
    assert _FOOTER_HINT not in content


# --- Module loading (load_skill with `file`) ---------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("file", "expected"),
    [
        ("a-module.md", "A module content."),
        ("sub/c-module.md", "C nested module content."),  # subdirectory
        ("helper.py", "print('helper')"),  # non-markdown extension
    ],
)
async def test_load_skill_file_returns_module_content(
    multifile_skills_dir: Path, file: str, expected: str
) -> None:
    tool = make_load_skill_tool(multifile_skills_dir)

    content = await tool.ainvoke({"skill_name": "multi-skill", "file": file})

    assert expected in content
    assert not content.startswith("Error:")


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad_file",
    [
        "../neighbor/SKILL.md",  # parent-dir traversal
        "/etc/passwd",  # absolute path
        "sub/../../neighbor/SKILL.md",  # traversal through a subdirectory
        "",  # empty string is not a valid relative module path
    ],
)
async def test_load_skill_file_rejects_path_traversal(
    multifile_skills_dir: Path, bad_file: str
) -> None:
    tool = make_load_skill_tool(multifile_skills_dir)

    content = await tool.ainvoke({"skill_name": "multi-skill", "file": bad_file})

    # Rejected as an error, and the escape target's content never leaks.
    assert content.startswith("Error:")
    assert "NEIGHBOR-SECRET" not in content


@pytest.mark.unit
async def test_load_skill_file_rejects_symlink_escape(
    multifile_skills_dir: Path,
) -> None:
    """Second-layer defense: a symlink whose name passes the segment allowlist
    but resolves outside the skill directory is rejected.

    A symlink is the only input that reaches layer two (``resolve()`` +
    ``is_relative_to``): every string-level traversal (``..``, absolute paths)
    is already cut by layer one, so ``link.md`` clears the allowlist yet
    ``resolve()`` follows it out of the skill dir into the neighbor's secret.
    """
    skill_dir = multifile_skills_dir / "multi-skill"
    escape_target = multifile_skills_dir / "neighbor" / "SKILL.md"
    link = skill_dir / "link.md"
    try:
        link.symlink_to(escape_target)
    except OSError as exc:  # pragma: no cover - platform/filesystem dependent
        pytest.skip(f"symlinks unavailable in this environment: {exc}")

    tool = make_load_skill_tool(multifile_skills_dir)

    content = await tool.ainvoke({"skill_name": "multi-skill", "file": "link.md"})

    # Name clears layer one; resolve() escapes the skill dir → layer two rejects.
    assert content.startswith("Error:")
    # The escape target's secret never leaks. (Post-A3 the error carries an
    # "Available files:" list — that lists file *names*, not bodies, so the
    # secret content still cannot appear here.)
    assert "NEIGHBOR-SECRET" not in content


@pytest.mark.unit
async def test_load_skill_file_missing_reports_available_files(
    multifile_skills_dir: Path,
) -> None:
    tool = make_load_skill_tool(multifile_skills_dir)

    content = await tool.ainvoke({"skill_name": "multi-skill", "file": "nope.md"})

    assert "not found" in content
    # Error lists the skill's real files (same pattern as skill-not-found).
    assert "a-module.md" in content
    assert "sub/c-module.md" in content


@pytest.mark.unit
async def test_load_skill_file_binary_reports_clear_error(
    multifile_skills_dir: Path,
) -> None:
    tool = make_load_skill_tool(multifile_skills_dir)

    content = await tool.ainvoke({"skill_name": "multi-skill", "file": "data.bin"})

    assert content.startswith("Error:")
    assert "binary file" in content


@pytest.mark.unit
async def test_load_skill_non_ascii_module_listed_and_loadable(
    skills_dir: Path,
) -> None:
    """Unicode-named modules pass the segment allowlist (``^[\\w.-]+$``).

    A Cyrillic-named module nested in a Cyrillic-named subdirectory (so *both*
    path segments are non-ASCII) both surfaces in the autolist footer and
    loads by its ``file`` path with the exact body. Guards the widening of
    ``_SAFE_PATH_SEGMENT_RE`` from ASCII to Unicode word characters.
    """
    _write_skill(skills_dir, "cyrillic-skill", _MULTI_BODY)
    _write_skill_file(
        skills_dir,
        "cyrillic-skill",
        "раздел/методология.md",
        "Кириллический модуль.",
    )
    tool = make_load_skill_tool(skills_dir)

    # Listed in the progressive-disclosure footer (form without `file`).
    listing = await tool.ainvoke({"skill_name": "cyrillic-skill"})
    assert "раздел/методология.md" in _footer_entries(listing)

    # Loadable by its relative path with correct content (form with `file`).
    module = await tool.ainvoke(
        {"skill_name": "cyrillic-skill", "file": "раздел/методология.md"}
    )
    assert "Кириллический модуль." in module
    assert not module.startswith("Error:")
