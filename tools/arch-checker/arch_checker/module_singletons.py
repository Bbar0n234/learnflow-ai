"""Check (c): no module-level mutable singletons.

Flags the narrow forbidden pattern — a module-level ``_x = None`` (or
``_x: T | None = None``) that some function reassigns via ``global _x``. That is
the hidden ``get_x()/set_x()`` singleton banned by conventions.md
§ Module-level state. Stateless module constants such as
``_ph = PasswordHasher()`` are not matched: their value is not ``None`` and they
are never rebound through ``global``.
"""

from __future__ import annotations

import ast
from pathlib import Path

from arch_checker._common import Violation, iter_source_files, parse_module

CHECK = "module-singleton"


def _module_level_none_names(module: ast.Module) -> set[str]:
    """Underscore-prefixed names bound to ``None`` at module scope."""
    names: set[str] = set()
    for node in module.body:
        if isinstance(node, ast.AnnAssign):
            ann_target, value = node.target, node.value
            if (
                isinstance(ann_target, ast.Name)
                and ann_target.id.startswith("_")
                and isinstance(value, ast.Constant)
                and value.value is None
            ):
                names.add(ann_target.id)
        elif isinstance(node, ast.Assign):
            if not (isinstance(node.value, ast.Constant) and node.value.value is None):
                continue
            for assign_target in node.targets:
                if isinstance(assign_target, ast.Name) and assign_target.id.startswith(
                    "_"
                ):
                    names.add(assign_target.id)
    return names


def _global_declared_names(module: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.Global):
            names.update(node.names)
    return names


def check(repo_root: Path) -> list[Violation]:
    violations: list[Violation] = []
    for path in iter_source_files(repo_root):
        module = parse_module(path)
        singletons = _module_level_none_names(module) & _global_declared_names(module)
        rel = path.relative_to(repo_root)
        for name in sorted(singletons):
            violations.append(
                Violation(
                    CHECK,
                    f"{rel}: module-level singleton '{name}' (None + reassigned via "
                    f"`global {name}`) — move state to app.state / closure / DI.",
                )
            )
    return violations
