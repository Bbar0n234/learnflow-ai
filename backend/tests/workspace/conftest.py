"""Local fixtures for the workspace scope (feat-011 / T1).

Everything here is real filesystem under ``tmp_path``: the file layer's whole
job is to decide what a path is allowed to touch, so faking the filesystem
would fake the thing under test. Two roots are built per test — a workspaces
root (``<tmp>/workspaces``, one directory per project) and a skills root
(``<tmp>/skills``) — mirroring the two mounts the container gets.

``make_workspace`` is a fixture-factory rather than a plain fixture because
several suites need the limits (read cap, the two diff-copy caps) dialled down
to a few bytes to reach the truncation/oversized branches without writing
megabytes.

The plain builders these fixtures are made of (``build_workspace``,
``runtime``, ``write_file``, the project ids) live in
``learnflow_testing.workspace``: the subagent and image-generation scopes drive
the same file layer, and shared test utilities belong to ``packages/testing``
rather than to one scope's conftest.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from app.storage.workspace import Workspace
from learnflow_testing.workspace import PROJECT_ID


@pytest.fixture
def workspaces_root(tmp_path: Path) -> Path:
    root = tmp_path / "workspaces"
    root.mkdir()
    return root


@pytest.fixture
def skills_root(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    root.mkdir()
    return root


@pytest.fixture
def make_workspace(
    workspaces_root: Path, skills_root: Path
) -> Callable[..., Workspace]:
    """Build a ``Workspace`` on the two test roots, limits overridable per test."""

    def factory(
        *,
        read_limit_chars: int = 50_000,
        diff_file_limit_bytes: int = 1_000_000,
        diff_total_limit_bytes: int = 10_000_000,
    ) -> Workspace:
        return Workspace(
            workspaces_root=workspaces_root,
            skills_root=skills_root,
            read_limit_chars=read_limit_chars,
            diff_file_limit_bytes=diff_file_limit_bytes,
            diff_total_limit_bytes=diff_total_limit_bytes,
        )

    return factory


@pytest.fixture
def workspace(make_workspace: Callable[..., Workspace]) -> Workspace:
    return make_workspace()


@pytest.fixture
def project_dir(workspaces_root: Path) -> Path:
    """The project's workspace directory, pre-created (lazy creation tested apart)."""
    path = workspaces_root / PROJECT_ID
    path.mkdir()
    return path
