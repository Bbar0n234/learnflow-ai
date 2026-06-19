"""Check (a): framework error-handling ordering in ``create_app``.

The generic ``Exception`` catch must be registered as an ``@app.middleware`` and
must sit *inside* ``CORSMiddleware`` (registered earlier in source → inner in the
Starlette stack), so a last-resort 500 carries CORS headers. A bare
``add_exception_handler(Exception, ...)`` would run outside CORS and is therefore
forbidden. Rationale: conventions.md § Обработка ошибок → Барьерный стек.
"""

from __future__ import annotations

import ast
from pathlib import Path

from arch_checker._common import Violation, parse_module

CHECK = "middleware-order"

# (module path relative to repo root, human label)
_APPS = (
    (Path("backend/app/main.py"), "backend"),
    (Path("services/siem-service/siem_service/main.py"), "siem-service"),
)


def _is_http_middleware_decorator(node: ast.expr) -> bool:
    # Matches @app.middleware("http")
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "middleware"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "http"
    )


def _catches_exception(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for handler in ast.walk(func):
        if not isinstance(handler, ast.ExceptHandler):
            continue
        exc_type = handler.type
        names: list[ast.expr] = []
        if isinstance(exc_type, ast.Tuple):
            names = list(exc_type.elts)
        elif exc_type is not None:
            names = [exc_type]
        if any(isinstance(n, ast.Name) and n.id == "Exception" for n in names):
            return True
    return False


def _generic_middleware_line(create_app: ast.FunctionDef) -> int | None:
    """Line of the @app.middleware('http') function that catches Exception."""
    lines: list[int] = []
    for node in ast.walk(create_app):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not any(_is_http_middleware_decorator(d) for d in node.decorator_list):
            continue
        if _catches_exception(node):
            lines.append(node.lineno)
    return min(lines) if lines else None


def _cors_add_middleware_line(create_app: ast.FunctionDef) -> int | None:
    for node in ast.walk(create_app):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_middleware"
            and node.args
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "CORSMiddleware"
        ):
            return node.lineno
    return None


def _exception_handler_violations(module: ast.Module, label: str) -> list[Violation]:
    violations: list[Violation] = []
    for node in ast.walk(module):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_exception_handler"
            and node.args
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "Exception"
        ):
            violations.append(
                Violation(
                    CHECK,
                    f"{label}: add_exception_handler(Exception, ...) at line "
                    f"{node.lineno} runs outside CORS — use an @app.middleware "
                    f'("http") catch instead.',
                )
            )
    return violations


def _find_create_app(module: ast.Module) -> ast.FunctionDef | None:
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == "create_app":
            return node
    return None


def check(repo_root: Path) -> list[Violation]:
    violations: list[Violation] = []
    for rel_path, label in _APPS:
        module = parse_module(repo_root / rel_path)
        violations.extend(_exception_handler_violations(module, label))

        create_app = _find_create_app(module)
        if create_app is None:
            violations.append(Violation(CHECK, f"{label}: create_app() not found."))
            continue

        mw_line = _generic_middleware_line(create_app)
        cors_line = _cors_add_middleware_line(create_app)

        if mw_line is None:
            violations.append(
                Violation(
                    CHECK,
                    f"{label}: no @app.middleware('http') catching Exception found "
                    f"in create_app().",
                )
            )
        if cors_line is None:
            violations.append(
                Violation(CHECK, f"{label}: no add_middleware(CORSMiddleware) found.")
            )
        if mw_line is not None and cors_line is not None and mw_line >= cors_line:
            violations.append(
                Violation(
                    CHECK,
                    f"{label}: generic-Exception middleware (line {mw_line}) must be "
                    f"registered BEFORE CORSMiddleware (line {cors_line}) so it sits "
                    f"inside CORS in the stack.",
                )
            )
    return violations
