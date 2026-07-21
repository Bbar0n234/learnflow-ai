"""Warning-only size checks: oversized modules and overcrowded packages.

Unlike the other checks in this package, these do not fail the build:
``__main__`` prints them with a ``WARN`` prefix and keeps the exit code at 0.
A threshold breach marks a refactoring candidate, not a violation — the check
is meant to flip to failing once the current offenders are refactored.

Scanned wider than ``_common.SOURCE_ROOTS`` on purpose: size hygiene applies
to every first-party Python tree (shared packages and tooling included), not
just the runtime source roots the AST asserts guard.
"""

from __future__ import annotations

from pathlib import Path

from arch_checker._common import Violation

FILE_CHECK = "file-size"
DIR_CHECK = "dir-size"

MAX_FILE_LINES = 500
MAX_DIR_PY_FILES = 10

# First-party Python trees to scan (repo-root-relative).
SCAN_ROOTS = (
    Path("backend/app"),
    Path("packages"),
    Path("services"),
    Path("tools"),
)

# Any path containing one of these segments is skipped: caches and virtual
# envs are not source; tests grow long tables/fixtures by design.
EXCLUDED_SEGMENTS = frozenset({"__pycache__", ".venv", "node_modules", "tests"})


def _is_excluded(rel: Path) -> bool:
    parts = rel.parts
    if EXCLUDED_SEGMENTS & set(parts):
        return True
    # Generated Alembic migrations: alembic/versions/*.py
    for first, second in zip(parts, parts[1:], strict=False):
        if first == "alembic" and second == "versions":
            return True
    return False


def _iter_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        base = repo_root / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if _is_excluded(path.relative_to(repo_root)):
                continue
            files.append(path)
    return files


def check(repo_root: Path) -> list[Violation]:
    warnings: list[Violation] = []
    files = _iter_files(repo_root)

    for path in files:
        lines = len(path.read_text(encoding="utf-8").splitlines())
        if lines > MAX_FILE_LINES:
            rel = path.relative_to(repo_root)
            warnings.append(
                Violation(
                    FILE_CHECK,
                    f"{rel}: {lines} lines (> {MAX_FILE_LINES}) — consider "
                    "splitting the module.",
                )
            )

    # __init__.py is re-export glue, not a semantic module — it does not count
    # toward how crowded a package is.
    counts: dict[Path, int] = {}
    for path in files:
        if path.name == "__init__.py":
            continue
        counts[path.parent] = counts.get(path.parent, 0) + 1
    for directory in sorted(counts):
        count = counts[directory]
        if count > MAX_DIR_PY_FILES:
            rel = directory.relative_to(repo_root)
            warnings.append(
                Violation(
                    DIR_CHECK,
                    f"{rel}: {count} modules (> {MAX_DIR_PY_FILES}, excluding "
                    "__init__.py) — consider grouping into subpackages.",
                )
            )

    return warnings
