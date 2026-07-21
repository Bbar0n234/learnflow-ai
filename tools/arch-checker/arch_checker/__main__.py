"""Entry point: run every AST architecture check, exit non-zero on violations.

Usage: ``python -m arch_checker`` (wired into ``make check`` and pre-commit).
import-linter contracts run separately (``lint-imports``); this module owns the
checks that need source-level AST analysis.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import structlog

from arch_checker import (
    middleware_order,
    module_singletons,
    problem_mirrors,
    size_limits,
)
from arch_checker._common import Violation, find_repo_root

logger = structlog.get_logger()

Check = Callable[[Path], list[Violation]]

CHECKS: tuple[Check, ...] = (
    middleware_order.check,
    problem_mirrors.check,
    module_singletons.check,
)

# Warning-only checks: printed with a WARN prefix, never affect the exit code.
WARNING_CHECKS: tuple[Check, ...] = (size_limits.check,)


def run() -> int:
    repo_root = find_repo_root()

    warnings: list[Violation] = []
    for check in WARNING_CHECKS:
        warnings.extend(check(repo_root))
    for warning in warnings:
        print(f"WARN {warning.render()}", file=sys.stderr)
    if warnings:
        logger.warning("arch-checker warnings", warnings=len(warnings))

    violations: list[Violation] = []
    for check in CHECKS:
        violations.extend(check(repo_root))

    if violations:
        for violation in violations:
            print(violation.render(), file=sys.stderr)
        logger.error("arch-checker failed", violations=len(violations))
        return 1

    print("arch-checker: all AST checks passed.")
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
