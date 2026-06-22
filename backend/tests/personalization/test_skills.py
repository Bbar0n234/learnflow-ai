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


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    root.mkdir()
    _write_skill(root, "alpha-skill", _SKILL_BODY)
    return root


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
