from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from langchain_core.tools import BaseTool, tool

_SKILL_NAME_RE = re.compile(r"^[a-z0-9_-]+$")
_SAFE_PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def make_load_skill_tool(skills_dir: Path) -> BaseTool:
    """Create a load_skill tool bound to the given skills directory."""

    @tool
    async def load_skill(skill_name: str, file: str | None = None) -> str:
        """Load a skill into context, or load one of its files.

        Two forms:
        - load_skill(skill_name): loads SKILL.md (instructions, patterns,
          approaches), followed by a list of the skill's other files, if any.
        - load_skill(skill_name, file): loads the content of `file`, a path
          relative to the skill's directory (subdirectories allowed, any
          extension). Use this after load_skill(skill_name) to pull in one
          of the files listed in its footer.
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

        skill_dir = skill_path.parent

        if file is None:
            content = skill_path.read_text(encoding="utf-8")
            skill_files = _list_skill_files(skill_dir)
            if not skill_files:
                return content

            footer_lines = "\n".join(f"- {name}" for name in skill_files)
            footer = (
                "\n\n---\nSkill files (load with load_skill(skill_name, file)):\n"
                f"{footer_lines}"
            )
            return content + footer

        if not _is_safe_relative_path(file):
            skill_files = _list_skill_files(skill_dir)
            available_files = ", ".join(skill_files) if skill_files else "(none)"
            return (
                f"Error: invalid file path '{file}'. Available files: {available_files}"
            )

        file_path = (skill_dir / file).resolve()
        if not file_path.is_relative_to(skill_dir):
            skill_files = _list_skill_files(skill_dir)
            available_files = ", ".join(skill_files) if skill_files else "(none)"
            return (
                f"Error: invalid file path '{file}'. Available files: {available_files}"
            )

        if not file_path.is_file():
            skill_files = _list_skill_files(skill_dir)
            available_files = ", ".join(skill_files) if skill_files else "(none)"
            return (
                f"Error: file '{file}' not found in skill '{skill_name}'. "
                f"Available files: {available_files}"
            )

        try:
            return file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return f"Error: file '{file}' is a binary file, cannot load as text."

    return load_skill


def _is_safe_relative_path(file: str) -> bool:
    """First-layer validation for `load_skill`'s `file` parameter.

    Rejects absolute paths and `..` traversal by checking each `/`-separated
    segment against a safe pattern, mirroring `_SKILL_NAME_RE` for skill
    names. This is layer one of the two-layer defense; layer two is
    `resolve()` + `is_relative_to()` against the skill's directory.
    """
    if not file or file.startswith("/"):
        return False
    segments = file.split("/")
    return all(
        segment not in ("", ".", "..") and _SAFE_PATH_SEGMENT_RE.match(segment)
        for segment in segments
    )


def _list_skill_files(skill_dir: Path) -> list[str]:
    """Recursively list a skill's files, relative to its directory.

    Excludes SKILL.md itself and dotfiles. Used to build the progressive-
    disclosure footer appended to `load_skill` responses without `file`.
    """
    if not skill_dir.is_dir():
        return []
    files: list[str] = []
    for path in skill_dir.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(skill_dir)
        if relative == Path("SKILL.md"):
            continue
        if any(part.startswith(".") for part in relative.parts):
            continue
        files.append(relative.as_posix())
    return sorted(files)


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
