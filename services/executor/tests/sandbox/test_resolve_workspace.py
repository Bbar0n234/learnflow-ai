"""Turning a `project_id` into a workspace path — the executor's only guard.

The executor is deliberately dumb: it does not know users or projects and
authorises nothing. What it must not do is *amplify* a bad request — a
`project_id` is one safe path segment or it is rejected, and the resolved path
is verified to still sit under the workspaces root after canonicalisation, so a
symlink cannot walk out of it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from executor.config import Settings
from executor.exceptions import InvalidProjectIdError, WorkspaceMissingError
from executor.sandbox import resolve_workspace


@pytest.mark.unit
def test_resolve_workspace_existing_project_returns_directory(
    workspace: Path, settings: Settings
) -> None:
    assert resolve_workspace("p1", settings) == workspace


@pytest.mark.unit
@pytest.mark.parametrize(
    "project_id",
    [
        "letters",
        "with-dash",
        "with_underscore",
        "with.dot",
        "MiXeD123",
        "a" * 128,
    ],
)
def test_resolve_workspace_safe_segment_is_accepted(
    workspaces_root: Path, settings: Settings, project_id: str
) -> None:
    (workspaces_root / project_id).mkdir()

    assert resolve_workspace(project_id, settings) == workspaces_root / project_id


@pytest.mark.unit
@pytest.mark.parametrize(
    ("project_id", "reason"),
    [
        ("", "empty"),
        (".", "current directory"),
        ("..", "parent directory"),
        ("../etc", "traversal"),
        ("../../etc/passwd", "deep traversal"),
        ("a/b", "nested segment"),
        ("/absolute", "absolute path"),
        ("p1/../p2", "traversal through a valid segment"),
        ("..%2fetc", "encoded traversal"),
        ("with space", "space"),
        ("semi;colon", "shell metacharacter"),
        ("dollar$sign", "shell metacharacter"),
        ("a" * 129, "over length limit"),
    ],
)
def test_resolve_workspace_unsafe_project_id_is_rejected(
    settings: Settings, project_id: str, reason: str
) -> None:
    with pytest.raises(InvalidProjectIdError):
        resolve_workspace(project_id, settings)


@pytest.mark.unit
def test_resolve_workspace_symlink_escaping_root_is_rejected(
    workspaces_root: Path, tmp_path: Path, settings: Settings
) -> None:
    """Canonicalisation happens before the containment check.

    A syntactically innocent `project_id` pointing at a symlink out of the root
    would otherwise hand a job somebody else's directory — the check runs on the
    resolved path, not the requested one.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspaces_root / "escape").symlink_to(outside)

    with pytest.raises(InvalidProjectIdError):
        resolve_workspace("escape", settings)


@pytest.mark.unit
def test_resolve_workspace_symlink_inside_root_is_accepted(
    workspaces_root: Path, settings: Settings
) -> None:
    target = workspaces_root / "real"
    target.mkdir()
    (workspaces_root / "alias").symlink_to(target)

    assert resolve_workspace("alias", settings) == target


@pytest.mark.unit
def test_resolve_workspace_missing_directory_is_rejected_without_creating_it(
    workspaces_root: Path, settings: Settings
) -> None:
    """A missing workspace is an error, not something to mkdir over.

    Every directory on the shared volume is created by the backend so that its
    owner matches the job's uid (a gVisor requirement) — an executor-side mkdir
    would quietly produce a directory the job then cannot write to.
    """
    with pytest.raises(WorkspaceMissingError):
        resolve_workspace("never-created", settings)

    assert not (workspaces_root / "never-created").exists()


@pytest.mark.unit
def test_resolve_workspace_file_instead_of_directory_is_rejected(
    workspaces_root: Path, settings: Settings
) -> None:
    (workspaces_root / "not-a-dir").write_text("regular file")

    with pytest.raises(WorkspaceMissingError):
        resolve_workspace("not-a-dir", settings)
