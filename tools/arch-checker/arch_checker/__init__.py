"""Deterministic architecture checks for LearnFlow AI (arch-checker, feat-008).

Self-contained AST assertions that catch conventions which neither ruff nor
import-linter express. Each check returns a list of ``Violation``; the package
entry point (``python -m arch_checker``) runs them all and exits non-zero on any
violation. See ``doc/tech/arch-checker.md`` for the full invariant registry.
"""
