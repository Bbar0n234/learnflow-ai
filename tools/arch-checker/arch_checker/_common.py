"""Shared helpers for the AST-based architecture checks."""

from __future__ import annotations

import ast
import copy
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

# Package source roots scanned by file-walking checks. Kept narrow on purpose:
# only first-party application code, never tests / migrations / generated files.
SOURCE_ROOTS = (
    Path("backend/app"),
    Path("services/siem-service/siem_service"),
)


@dataclass(frozen=True)
class Violation:
    """A single architecture-rule breach, addressed to a human reader."""

    check: str
    message: str

    def render(self) -> str:
        return f"[{self.check}] {self.message}"


def find_repo_root() -> Path:
    """Walk upward from this file until the repository root is found.

    The root is identified structurally (it contains ``backend/app/main.py``)
    so the checker works both from an editable install and from a source
    checkout, regardless of the current working directory.
    """
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "backend" / "app" / "main.py").is_file():
            return candidate
    raise RuntimeError(
        "arch-checker: repository root not found (no backend/app/main.py)"
    )


def parse_module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def iter_source_files(repo_root: Path) -> Iterator[Path]:
    """Yield every ``*.py`` under the first-party source roots."""
    for root in SOURCE_ROOTS:
        base = repo_root / root
        if not base.is_dir():
            continue
        yield from sorted(base.rglob("*.py"))


FuncDef = ast.FunctionDef | ast.AsyncFunctionDef
Definition = FuncDef | ast.ClassDef


def _strip_docstring(node: Definition) -> None:
    """Drop the leading docstring statement, if present (in place)."""
    body = node.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        del body[0]


def normalized_dump(node: Definition) -> str:
    """Structural fingerprint of a def: docstring removed, positions ignored.

    ``ast.dump`` without ``include_attributes`` already discards line/column
    info; stripping the docstring makes two definitions that differ only in
    prose compare equal.
    """
    clone = copy.deepcopy(node)
    _strip_docstring(clone)
    return ast.dump(clone)


def top_level_defs(module: ast.Module) -> dict[str, Definition]:
    """Map name -> node for top-level functions and classes."""
    defs: dict[str, Definition] = {}
    for node in module.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            defs[node.name] = node
    return defs
