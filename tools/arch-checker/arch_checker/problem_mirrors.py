"""Check (b): the two RFC 9457 problem modules must stay mirrors.

``backend/app/api/problem.py`` and ``siem_service/api/problem.py`` are hand-kept
mirrors (no shared package). Their handler functions must be structurally
identical once docstrings and the ``AppError`` import source are normalized away.
The base exceptions (``AppError`` / ``NotFoundError`` / ``ConflictError``) must
also match — siem is a legitimate subset, so only these three are compared, not
the full file. Rationale: conventions.md § Обработка ошибок.
"""

from __future__ import annotations

from pathlib import Path

from arch_checker._common import (
    Violation,
    normalized_dump,
    parse_module,
    top_level_defs,
)

CHECK = "problem-mirrors"

_BACKEND_PROBLEM = Path("backend/app/api/problem.py")
_SIEM_PROBLEM = Path("services/siem-service/siem_service/api/problem.py")
_BACKEND_EXC = Path("backend/app/services/exceptions.py")
_SIEM_EXC = Path("services/siem-service/siem_service/exceptions.py")

_HANDLER_DEFS = (
    "problem_response",
    "_app_error_handler",
    "_infra_exception_handler",
    "_timeout_exception_handler",
    "_http_exception_handler",
    "_validation_exception_handler",
    "register_problem_handlers",
)

# siem exceptions is a subset; only the shared base hierarchy is compared.
_BASE_EXCEPTIONS = ("AppError", "NotFoundError", "ConflictError")


def _compare_defs(
    *,
    names: tuple[str, ...],
    backend_path: Path,
    siem_path: Path,
    repo_root: Path,
    kind: str,
) -> list[Violation]:
    backend_defs = top_level_defs(parse_module(repo_root / backend_path))
    siem_defs = top_level_defs(parse_module(repo_root / siem_path))

    violations: list[Violation] = []
    for name in names:
        if name not in backend_defs:
            violations.append(
                Violation(CHECK, f"{kind} '{name}' missing in {backend_path}.")
            )
            continue
        if name not in siem_defs:
            violations.append(
                Violation(CHECK, f"{kind} '{name}' missing in {siem_path}.")
            )
            continue
        if normalized_dump(backend_defs[name]) != normalized_dump(siem_defs[name]):
            violations.append(
                Violation(
                    CHECK,
                    f"{kind} '{name}' diverges between {backend_path} and "
                    f"{siem_path} (compare ignoring docstrings/comments).",
                )
            )
    return violations


def check(repo_root: Path) -> list[Violation]:
    violations = _compare_defs(
        names=_HANDLER_DEFS,
        backend_path=_BACKEND_PROBLEM,
        siem_path=_SIEM_PROBLEM,
        repo_root=repo_root,
        kind="problem handler",
    )
    violations += _compare_defs(
        names=_BASE_EXCEPTIONS,
        backend_path=_BACKEND_EXC,
        siem_path=_SIEM_EXC,
        repo_root=repo_root,
        kind="base exception",
    )
    return violations
