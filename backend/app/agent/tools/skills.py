from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from langchain_core.tools import BaseTool, tool

_SKILL_NAME_RE = re.compile(r"^[a-z0-9_-]+$")


def make_load_skill_tool(skills_dir: Path) -> BaseTool:
    """Create a load_skill tool bound to the given skills directory."""

    @tool
    async def load_skill(skill_name: str) -> str:
        """Load a skill module into context by name.

        Returns the full skill content (instructions, patterns, approaches)
        so you can use it to help the user.
        """
        if not _SKILL_NAME_RE.match(skill_name):
            available = _list_available(skills_dir)
            return (
                f"Error: invalid skill name '{skill_name}'. "
                f"Available skills: {available}"
            )

        skill_path = (skills_dir / skill_name / "SKILL.md").resolve()
        if not skill_path.is_relative_to(skills_dir.resolve()):
            return f"Error: invalid skill path for '{skill_name}'."

        if not skill_path.is_file():
            available = _list_available(skills_dir)
            return (
                f"Error: skill '{skill_name}' not found. Available skills: {available}"
            )

        return skill_path.read_text(encoding="utf-8")

    return load_skill


def _list_available(skills_dir: Path) -> str:
    """List available skill names by scanning subdirectories."""
    if not skills_dir.is_dir():
        return "(none)"
    names = sorted(
        d.name
        for d in skills_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").is_file()
    )
    return ", ".join(names) if names else "(none)"


def scan_skills_index(skills_dir: Path) -> str:
    """Build skills index from SKILL.md frontmatter (name + description).

    Scanned once at startup. Returns a string for injection into system message.
    """
    if not skills_dir.is_dir():
        return ""

    entries: list[tuple[str, str]] = []
    for skill_dir in sorted(skills_dir.iterdir()):
        skill_file = skill_dir / "SKILL.md"
        if not skill_dir.is_dir() or not skill_file.is_file():
            continue

        text = skill_file.read_text(encoding="utf-8")
        meta = _parse_frontmatter(text)
        if meta is None:
            continue

        name = meta.get("name", skill_dir.name)
        description = meta.get("description", "")
        if isinstance(description, str):
            description = " ".join(description.split())  # normalize whitespace
        entries.append((name, description))

    if not entries:
        return ""

    lines = [f"- {name}: {desc}" for name, desc in entries]
    return "Available Skills:\n" + "\n".join(lines)


def _parse_frontmatter(text: str) -> dict[str, Any] | None:
    """Parse YAML frontmatter delimited by --- lines."""
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        result = yaml.safe_load(parts[1])
        return result if isinstance(result, dict) else None
    except yaml.YAMLError:
        return None
