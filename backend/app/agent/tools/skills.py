from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, cast

import yaml
from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import ToolRuntime

from app.agent.tools.store_helpers import format_index

_SKILL_NAME_RE = re.compile(r"^[a-z0-9_-]+$")
_SAFE_PATH_SEGMENT_RE = re.compile(r"^[\w.-]+$")

# Mirrors save_skill_context's per-skill document cap (skill_context.py) so the
# index fetched here is never truncated below what a skill can actually hold.
_MAX_SKILL_CONTEXT_DOCUMENTS = 20

# Sentinel default for `load_skill`'s injected `runtime` param — see the
# comment at its use site (`make_load_skill_tool`) for why this is needed
# instead of a plain required parameter or `ToolRuntime | None`.
_NO_RUNTIME: ToolRuntime = cast("ToolRuntime", None)


def make_load_skill_tool(skills_dir: Path) -> BaseTool:
    """Create a load_skill tool bound to the given skills directory."""

    @tool
    async def load_skill(
        skill_name: str,
        file: str | None = None,
        # Defaults to `_NO_RUNTIME`, not a plain required param: the LLM-facing
        # schema/injection machinery only excludes params whose annotation is
        # exactly `ToolRuntime` (see langchain_core.tools.base
        # `_is_directly_injected_arg_type`) — `ToolRuntime | None` breaks schema
        # generation. A real default is needed so direct invocation without a
        # full agent runtime (filesystem-only unit tests, no store/context)
        # still works; the sentinel keeps the annotation exact for mypy while
        # its runtime value is `None`, handled explicitly in
        # `_skill_context_index`.
        runtime: ToolRuntime = _NO_RUNTIME,
    ) -> str:
        """Load a skill into context, or load one of its files.

        Two forms:
        - load_skill(skill_name): loads SKILL.md (instructions, patterns,
          approaches), followed by a list of the skill's other files, if any,
          and — if you have saved context documents for this skill (style
          profiles, samples, preferences) — an index of them as
          `key: description`. Fetch a document's full content with
          get_skill_context(skill_name, key).
        - load_skill(skill_name, file): loads the content of `file`, a path
          relative to the skill's directory (subdirectories allowed, any
          extension). Use this after load_skill(skill_name) to pull in one
          of the files listed in its footer.
        """
        result = await asyncio.to_thread(_load_skill_sync, skills_dir, skill_name, file)
        if file is not None or result.startswith("Error:"):
            return result

        index = await _skill_context_index(runtime, skill_name)
        if index is None:
            return result
        return f"{result}\n\n---\n{index}"

    return load_skill


async def _skill_context_index(runtime: ToolRuntime, skill_name: str) -> str | None:
    """Fetch and format the caller's skill-context index for `skill_name`.

    Returns None — leaving `load_skill`'s output untouched — when no runtime is
    wired (direct invocation outside a tool-calling agent turn) or the
    namespace is empty. Two-level progressive disclosure (design-brief
    § Доставка в контекст агента): only `key: description` here; document
    content is fetched separately via `get_skill_context`.
    """
    if runtime is None or runtime.store is None or runtime.context is None:
        return None
    ns = ("user", runtime.context.user_id, "skill_context", skill_name)
    items = await runtime.store.asearch(ns, limit=_MAX_SKILL_CONTEXT_DOCUMENTS)
    if not items:
        return None
    return format_index(list(items), title="Skill Context")


def _load_skill_sync(skills_dir: Path, skill_name: str, file: str | None) -> str:
    """Synchronous body of `load_skill`, run off the event loop via `asyncio.to_thread`."""
    if not _SKILL_NAME_RE.match(skill_name):
        available = _list_available(skills_dir)
        return (
            f"Error: invalid skill name '{skill_name}'. Available skills: {available}"
        )

    skill_path = (skills_dir / skill_name / "SKILL.md").resolve()
    if not skill_path.is_relative_to(skills_dir.resolve()):
        return f"Error: invalid skill path for '{skill_name}'."

    if not skill_path.is_file():
        available = _list_available(skills_dir)
        return f"Error: skill '{skill_name}' not found. Available skills: {available}"

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
        return f"Error: invalid file path '{file}'. Available files: {available_files}"

    file_path = (skill_dir / file).resolve()
    if not file_path.is_relative_to(skill_dir):
        skill_files = _list_skill_files(skill_dir)
        available_files = ", ".join(skill_files) if skill_files else "(none)"
        return f"Error: invalid file path '{file}'. Available files: {available_files}"

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


def _is_safe_relative_path(file: str) -> bool:
    """First-layer validation for `load_skill`'s `file` parameter.

    Rejects absolute paths and `..` traversal by checking each `/`-separated
    segment against a safe pattern (word characters plus `.`/`-`, Unicode-aware
    so non-ASCII module names pass), mirroring `_SKILL_NAME_RE` for skill
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

    Excludes SKILL.md itself, dotfiles, and entries that resolve outside
    `skill_dir` (e.g. symlinks pointing elsewhere) — the footer only lists
    what `load_skill(skill_name, file)` can actually load, since layer two
    of that path's validation rejects the same entries. Used to build the
    progressive-disclosure footer appended to `load_skill` responses without
    `file`.
    """
    if not skill_dir.is_dir():
        return []
    resolved_skill_dir = skill_dir.resolve()
    files: list[str] = []
    for path in skill_dir.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(skill_dir)
        if relative == Path("SKILL.md"):
            continue
        if any(part.startswith(".") for part in relative.parts):
            continue
        if not path.resolve().is_relative_to(resolved_skill_dir):
            continue
        files.append(relative.as_posix())
    return sorted(files)


def _list_available(skills_dir: Path) -> str:
    """List available skill names by scanning subdirectories."""
    names = sorted(scan_skill_names(skills_dir))
    return ", ".join(names) if names else "(none)"


def scan_skill_names(skills_dir: Path) -> frozenset[str]:
    """Return the set of skill names available in the library.

    Startup snapshot, same directory scan as `_list_available` (subdirectory
    with a `SKILL.md`), but as a set for programmatic existence checks: used
    by `save_skill_context` (reject writes for unknown/misspelled skills) and
    the REST `in_library` flag. `load_skill` itself keeps checking the
    filesystem live, independently of this snapshot.
    """
    if not skills_dir.is_dir():
        return frozenset()
    return frozenset(
        d.name
        for d in skills_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").is_file()
    )


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
