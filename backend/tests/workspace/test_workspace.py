"""Solitary-unit: the workspace file layer (``app/storage/workspace.py``).

This module is the security barrier of the whole iteration (design-brief §
Безопасность, layer 2): every path an agent or a REST caller names is
canonicalized and checked against exactly two roots before anything touches
the disk. So the bulk of this suite is about *refusal* — traversal, absolute
escapes, a symlink pointing out of the tree, a write aimed at the read-only
skills mount — and about the fact that each refusal leaves an
``agent.runtime.path_denied`` security log behind, which is the only trace an
attempted escape ever produces.

The rest covers the plain filesystem contracts the tools and REST endpoints
build on: reading with a cap, atomic writes that report created-vs-updated
with line counters, listings that hide the layer's own temp files, and the
before/after snapshot of ``artifacts/`` that turns a code-execution job into
artifact events. No doubles anywhere — a real directory tree under
``tmp_path`` *is* the collaborator under test.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from app.storage.workspace import (
    TMP_FILE_PREFIX,
    Workspace,
    WorkspacePathError,
    artifact_type,
    extension_from_mime,
    read_text_bounded,
    resolve_under_root,
    sanitize_filename,
    to_artifact_path,
    unique_path,
)
from learnflow_testing.workspace import OTHER_PROJECT_ID, PROJECT_ID, write_file
from siem_contracts import AGENT_RUNTIME_PATH_DENIED
from structlog.testing import capture_logs

pytestmark = pytest.mark.unit


# --- path resolution: the two allowed roots ---------------------------------


def test_resolve_path_relative_path_stays_inside_the_project_workspace(
    workspace: Workspace, project_dir: Path
) -> None:
    resolved = workspace.resolve_path(PROJECT_ID, "artifacts/lecture-1/slides.md")

    assert resolved == project_dir / "artifacts" / "lecture-1" / "slides.md"


def test_resolve_path_normalizes_dot_segments_that_stay_inside(
    workspace: Workspace, project_dir: Path
) -> None:
    # Canonicalization is not the same as rejection: `..` that lands back
    # inside the root is an ordinary path, not an escape attempt.
    resolved = workspace.resolve_path(PROJECT_ID, "artifacts/../notes.md")

    assert resolved == project_dir / "notes.md"


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("../../etc/passwd", id="relative-traversal"),
        pytest.param("/etc/passwd", id="absolute-outside"),
        pytest.param(f"../{OTHER_PROJECT_ID}/artifacts/secret.md", id="other-project"),
        pytest.param("artifacts/../../../../etc/shadow", id="deep-traversal"),
    ],
)
def test_resolve_path_escaping_both_roots_is_denied(
    workspace: Workspace, project_dir: Path, path: str
) -> None:
    with pytest.raises(WorkspacePathError):
        workspace.resolve_path(PROJECT_ID, path)


def test_resolve_path_denial_writes_a_path_denied_security_log(
    workspace: Workspace, project_dir: Path
) -> None:
    with capture_logs() as logs, pytest.raises(WorkspacePathError):
        workspace.resolve_path(PROJECT_ID, "../../etc/passwd")

    assert [
        (entry["event_type"], entry["security_event"], entry["metadata"]["path"])
        for entry in logs
    ] == [(AGENT_RUNTIME_PATH_DENIED, True, "../../etc/passwd")]


def test_read_text_through_a_symlink_out_of_the_workspace_never_returns_that_file(
    workspace: Workspace, project_dir: Path, tmp_path: Path
) -> None:
    # Resolution is canonicalized, so a symlink cannot smuggle a component
    # past the root check (design-brief § Границы путей). Either refusal is
    # acceptable at this layer — what must never happen is the outside file's
    # content coming back through an innocent-looking relative path.
    outside = write_file(tmp_path / "outside" / "secret.txt", "s3cret")
    (project_dir / "link.txt").symlink_to(outside)

    with pytest.raises((WorkspacePathError, FileNotFoundError)):
        workspace.read_text(PROJECT_ID, "link.txt")


def test_read_text_through_a_symlink_into_another_project_never_returns_that_file(
    workspace: Workspace, workspaces_root: Path, project_dir: Path
) -> None:
    write_file(workspaces_root / OTHER_PROJECT_ID / "artifacts/secret.md", "их данные")
    (project_dir / "peek").symlink_to(workspaces_root / OTHER_PROJECT_ID)

    with pytest.raises((WorkspacePathError, FileNotFoundError)):
        workspace.read_text(PROJECT_ID, "peek/artifacts/secret.md")


def test_write_text_through_a_symlink_out_of_the_workspace_is_denied(
    workspace: Workspace, project_dir: Path, tmp_path: Path
) -> None:
    outside = write_file(tmp_path / "outside" / "secret.txt", "s3cret")
    (project_dir / "link.txt").symlink_to(outside)

    with pytest.raises(WorkspacePathError):
        workspace.write_text(PROJECT_ID, "link.txt", "overwritten")

    assert outside.read_text() == "s3cret"


def test_resolve_path_absolute_skills_path_resolves_for_reading(
    workspace: Workspace, skills_root: Path
) -> None:
    # The skills mount is addressed by its absolute path (`/skills/...` in
    # prod): pathlib's join drops the workspace root when the right-hand side
    # is absolute, which is what lets one `path` parameter reach both roots.
    write_file(skills_root / "alpha" / "SKILL.md", "# Alpha")

    resolved = workspace.resolve_path(PROJECT_ID, f"{skills_root}/alpha/SKILL.md")

    assert resolved == skills_root / "alpha" / "SKILL.md"


def test_resolve_path_write_into_the_skills_root_is_denied(
    workspace: Workspace, skills_root: Path
) -> None:
    write_file(skills_root / "alpha" / "SKILL.md", "# Alpha")

    with capture_logs() as logs, pytest.raises(WorkspacePathError) as exc_info:
        workspace.resolve_path(PROJECT_ID, f"{skills_root}/alpha/SKILL.md", write=True)

    assert exc_info.value.reason == "write_to_readonly_root"
    assert [entry["event_type"] for entry in logs] == [AGENT_RUNTIME_PATH_DENIED]


def test_resolve_skill_path_escaping_the_skills_root_is_denied(
    workspace: Workspace, skills_root: Path
) -> None:
    with pytest.raises(WorkspacePathError):
        workspace.resolve_skill_path("../workspaces/project-1/artifacts/x.md")


def test_resolve_under_root_returns_the_path_when_it_stays_inside(
    tmp_path: Path,
) -> None:
    assert resolve_under_root(tmp_path, "a/b.md") == tmp_path / "a" / "b.md"


def test_resolve_under_root_returns_none_when_the_path_escapes(tmp_path: Path) -> None:
    assert resolve_under_root(tmp_path / "root", "../elsewhere/b.md") is None


# --- read -------------------------------------------------------------------


def test_read_text_returns_the_whole_file_when_it_fits_the_limit(
    workspace: Workspace, project_dir: Path
) -> None:
    write_file(project_dir / "notes.md", "hello\nworld")

    result = workspace.read_text(PROJECT_ID, "notes.md")

    assert (result.content, result.truncated) == ("hello\nworld", False)


def test_read_text_over_the_limit_is_truncated_and_flagged(
    make_workspace: Callable[..., Workspace], project_dir: Path
) -> None:
    workspace = make_workspace(read_limit_chars=5)
    write_file(project_dir / "notes.md", "0123456789")

    result = workspace.read_text(PROJECT_ID, "notes.md")

    assert (result.content, result.truncated) == ("01234", True)


def test_read_text_of_a_file_exactly_at_the_limit_is_not_flagged(
    make_workspace: Callable[..., Workspace], project_dir: Path
) -> None:
    # The bounded read asks for one character more than the ceiling precisely to
    # tell "exactly at the limit" from "more follows" — off by one here and
    # every file of exactly N characters would come back marked truncated.
    workspace = make_workspace(read_limit_chars=5)
    write_file(project_dir / "notes.md", "01234")

    result = workspace.read_text(PROJECT_ID, "notes.md")

    assert (result.content, result.truncated) == ("01234", False)


def test_read_text_returns_a_multibyte_file_whole_when_its_characters_fit(
    make_workspace: Callable[..., Workspace], project_dir: Path
) -> None:
    """A ceiling counted in characters must not be enforced in bytes.

    Bounding the read means deciding *before* reading, and the only thing
    available before reading is the byte size. Cyrillic is two bytes per
    character in UTF-8, so this file is over the ceiling by bytes and under it
    by characters — refusing it, or cutting it at the byte count, would silently
    truncate ordinary Russian notes.
    """
    workspace = make_workspace(read_limit_chars=10)
    write_file(project_dir / "notes.md", "конспект")

    result = workspace.read_text(PROJECT_ID, "notes.md")

    assert (result.content, result.truncated) == ("конспект", False)


def test_read_text_far_over_the_limit_yields_exactly_the_limit(
    make_workspace: Callable[..., Workspace], project_dir: Path
) -> None:
    # The failure this closes is a job writing a huge file into `artifacts/`
    # and the backend materializing all of it before truncating. The observable
    # contract is the same either way — the result is capped — so the assertion
    # is on the size of what comes back, whatever the file behind it weighs.
    workspace = make_workspace(read_limit_chars=64)
    write_file(project_dir / "notes.md", "a" * 500_000)

    result = workspace.read_text(PROJECT_ID, "notes.md")

    assert result.content is not None
    assert (len(result.content), result.truncated) == (64, True)


def test_read_text_of_a_binary_file_over_the_limit_returns_no_content(
    make_workspace: Callable[..., Workspace], project_dir: Path
) -> None:
    # Binary detection lives on both read paths now (whole-file and bounded),
    # and the oversized one is the path a real PNG takes: callers still get
    # `content is None` -> "use the media endpoint", not a raised decode error.
    workspace = make_workspace(read_limit_chars=8)
    (project_dir / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe" * 20)

    result = workspace.read_text(PROJECT_ID, "image.png")

    assert (result.content, result.truncated) == (None, False)


def test_read_text_bounded_reads_a_path_the_rest_endpoint_already_resolved(
    project_dir: Path,
) -> None:
    # The REST detail endpoint has no lower entry point than the raw `Path`, so
    # the bound is a module-level primitive both callers share rather than a
    # `Workspace` method. Same ceiling, same truncation flag, no project id.
    write_file(project_dir / "artifacts/notes.md", "0123456789")

    result = read_text_bounded(project_dir / "artifacts" / "notes.md", 4)

    assert (result.content, result.truncated) == ("0123", True)


def test_read_text_of_a_binary_file_returns_no_content(
    workspace: Workspace, project_dir: Path
) -> None:
    # Callers surface "binary file, use media endpoint" instead of raw bytes;
    # the layer signals that with `content is None`, not an exception.
    (project_dir / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe")

    result = workspace.read_text(PROJECT_ID, "image.png")

    assert result.content is None


def test_read_text_of_a_missing_file_raises_file_not_found(
    workspace: Workspace, project_dir: Path
) -> None:
    with pytest.raises(FileNotFoundError):
        workspace.read_text(PROJECT_ID, "nope.md")


# --- write ------------------------------------------------------------------


def test_write_text_creates_parent_directories_and_reports_created(
    workspace: Workspace, project_dir: Path
) -> None:
    result = workspace.write_text(PROJECT_ID, "artifacts/lecture-1/slides.md", "# One")

    assert (result.kind, result.diff) == ("created", None)
    assert (project_dir / "artifacts/lecture-1/slides.md").read_text() == "# One"


def test_write_text_creates_the_project_workspace_lazily(
    workspace: Workspace, workspaces_root: Path
) -> None:
    # A project nobody has written to yet has no directory (ADR-032 §
    # Lifecycle) — the first write is what brings it into existence.
    assert not (workspaces_root / "fresh-project").exists()

    workspace.write_text("fresh-project", "artifacts/a.md", "x")

    assert (workspaces_root / "fresh-project" / "artifacts" / "a.md").exists()


def test_write_text_over_an_existing_file_reports_updated_with_line_counts(
    workspace: Workspace, project_dir: Path
) -> None:
    write_file(project_dir / "artifacts/notes.md", "one\ntwo\nthree\n")

    result = workspace.write_text(PROJECT_ID, "artifacts/notes.md", "one\nTWO\n")

    assert result.kind == "updated"
    assert result.diff is not None
    assert (result.diff.added, result.diff.removed) == (1, 2)


def test_write_text_over_a_binary_file_reports_updated_without_counters(
    workspace: Workspace, project_dir: Path
) -> None:
    (project_dir / "artifacts").mkdir()
    (project_dir / "artifacts/blob.bin").write_bytes(b"\xff\xfe\x00")

    result = workspace.write_text(PROJECT_ID, "artifacts/blob.bin", "now text")

    assert (result.kind, result.diff) == ("updated", None)


def test_write_text_leaves_no_temp_file_behind(
    workspace: Workspace, project_dir: Path
) -> None:
    # tmp + rename in the target directory: the temp half must not survive the
    # write, or every listing and artifacts snapshot would grow debris.
    workspace.write_text(PROJECT_ID, "artifacts/notes.md", "text")

    leftovers = [
        p.name
        for p in (project_dir / "artifacts").iterdir()
        if p.name.startswith(TMP_FILE_PREFIX)
    ]
    assert leftovers == []


def test_write_text_into_the_skills_root_is_denied(
    workspace: Workspace, skills_root: Path
) -> None:
    write_file(skills_root / "alpha" / "SKILL.md", "# Alpha")

    with pytest.raises(WorkspacePathError):
        workspace.write_text(PROJECT_ID, f"{skills_root}/alpha/SKILL.md", "hacked")

    assert (skills_root / "alpha" / "SKILL.md").read_text() == "# Alpha"


def test_write_bytes_writes_the_exact_payload(
    workspace: Workspace, project_dir: Path
) -> None:
    payload = b"\x89PNG\r\n\x1a\n"

    workspace.write_bytes(PROJECT_ID, "artifacts/cover.png", payload)

    assert (project_dir / "artifacts/cover.png").read_bytes() == payload


# --- list -------------------------------------------------------------------


def test_list_dir_lists_immediate_children_with_a_directory_flag(
    workspace: Workspace, project_dir: Path
) -> None:
    write_file(project_dir / "artifacts/notes.md", "x")
    write_file(project_dir / "artifacts/lecture-1/slides.md", "y")

    entries = workspace.list_dir(PROJECT_ID, "artifacts")

    assert [(e.path, e.is_dir) for e in entries] == [
        ("lecture-1", True),
        ("notes.md", False),
    ]


def test_list_dir_recursive_includes_nested_paths(
    workspace: Workspace, project_dir: Path
) -> None:
    write_file(project_dir / "artifacts/lecture-1/slides.md", "y")

    entries = workspace.list_dir(PROJECT_ID, "artifacts", recursive=True)

    assert [(e.path, e.is_dir) for e in entries] == [
        ("lecture-1", True),
        ("lecture-1/slides.md", False),
    ]


def test_list_dir_hides_the_layers_own_temp_files(
    workspace: Workspace, project_dir: Path
) -> None:
    # The scratch file `execute_code` writes shares this prefix — the agent
    # must never see its own plumbing in a listing.
    write_file(project_dir / "notes.md", "x")
    write_file(project_dir / f"{TMP_FILE_PREFIX}abc.py", "print(1)")

    entries = workspace.list_dir(PROJECT_ID, ".")

    assert [e.path for e in entries] == ["notes.md"]


def test_list_dir_skips_a_symlink_and_keeps_the_rest_of_the_listing(
    workspace: Workspace, project_dir: Path, tmp_path: Path
) -> None:
    """One stray link must cost itself, not the whole listing.

    A job can leave a symlink in `artifacts/` (`ln -s /etc/passwd x`) either
    deliberately or as a toolchain side effect, and the product has no way to
    remove it — the agent has no delete tool. Before the skip, `list_dir`
    handed the link out as an ordinary entry and the caller's re-resolve
    refused it, taking the entire project's artifact panel down with it.
    """
    outside = write_file(tmp_path / "outside" / "secret.txt", "s3cret")
    write_file(project_dir / "artifacts/notes.md", "x")
    write_file(project_dir / "artifacts/chart.png", "y")
    (project_dir / "artifacts/leak.txt").symlink_to(outside)

    entries = workspace.list_dir(PROJECT_ID, "artifacts")

    assert [e.path for e in entries] == ["chart.png", "notes.md"]


def test_list_dir_skips_a_dangling_symlink(
    workspace: Workspace, project_dir: Path
) -> None:
    # A link to nothing is the cheaper half of the same bug: it isn't a path
    # escape at all, it just makes `stat()` raise on a caller that assumed
    # every listed entry exists.
    write_file(project_dir / "artifacts/notes.md", "x")
    (project_dir / "artifacts/dangling.txt").symlink_to(project_dir / "nope.txt")

    assert [e.path for e in workspace.list_dir(PROJECT_ID, "artifacts")] == ["notes.md"]


def test_list_dir_records_a_warning_for_every_skipped_symlink(
    workspace: Workspace, project_dir: Path, tmp_path: Path
) -> None:
    # Routine filtering, not a security verdict (the resolve barrier owns that
    # log) — but a file the agent wrote and cannot see must not vanish in
    # silence either.
    outside = write_file(tmp_path / "outside" / "secret.txt", "s3cret")
    (project_dir / "artifacts").mkdir()
    (project_dir / "artifacts/leak.txt").symlink_to(outside)

    with capture_logs() as logs:
        workspace.list_dir(PROJECT_ID, "artifacts")

    assert [
        entry["log_level"]
        for entry in logs
        if entry["event"] == "workspace listing skipped symlink"
    ] == ["warning"]


def test_list_dir_of_a_missing_directory_returns_empty(
    workspace: Workspace, project_dir: Path
) -> None:
    assert workspace.list_dir(PROJECT_ID, "artifacts") == []


def test_list_dir_of_a_file_raises_not_a_directory(
    workspace: Workspace, project_dir: Path
) -> None:
    write_file(project_dir / "notes.md", "x")

    with pytest.raises(NotADirectoryError):
        workspace.list_dir(PROJECT_ID, "notes.md")


def test_list_dir_escaping_the_roots_is_denied(
    workspace: Workspace, project_dir: Path
) -> None:
    with pytest.raises(WorkspacePathError):
        workspace.list_dir(PROJECT_ID, "../..")


# --- artifacts/ snapshot + diff ---------------------------------------------


def test_diff_artifacts_reports_a_new_file_as_created_without_counters(
    workspace: Workspace, project_dir: Path
) -> None:
    before = workspace.snapshot_artifacts(PROJECT_ID)
    write_file(project_dir / "artifacts/chart.png", "fake-png")
    after = workspace.snapshot_artifacts(PROJECT_ID)

    entries = workspace.diff_artifacts(before, after)

    assert [(e.path, e.kind, e.diff) for e in entries] == [
        ("chart.png", "created", None)
    ]


def test_diff_artifacts_reports_a_rewritten_text_file_with_line_counts(
    workspace: Workspace, project_dir: Path
) -> None:
    write_file(project_dir / "artifacts/notes.md", "one\ntwo\n")
    before = workspace.snapshot_artifacts(PROJECT_ID)
    write_file(project_dir / "artifacts/notes.md", "one\ntwo\nthree\nfour\n")
    after = workspace.snapshot_artifacts(PROJECT_ID)

    entries = workspace.diff_artifacts(before, after)

    assert [(e.path, e.kind) for e in entries] == [("notes.md", "updated")]
    assert entries[0].diff is not None
    assert (entries[0].diff.added, entries[0].diff.removed) == (2, 0)


def test_diff_artifacts_skips_a_file_nothing_touched(
    workspace: Workspace, project_dir: Path
) -> None:
    write_file(project_dir / "artifacts/notes.md", "one\n")
    before = workspace.snapshot_artifacts(PROJECT_ID)
    after = workspace.snapshot_artifacts(PROJECT_ID)

    assert workspace.diff_artifacts(before, after) == []


def test_diff_artifacts_reports_a_rewritten_binary_file_without_counters(
    workspace: Workspace, project_dir: Path
) -> None:
    (project_dir / "artifacts").mkdir()
    (project_dir / "artifacts/chart.png").write_bytes(b"\xff\xd8old")
    before = workspace.snapshot_artifacts(PROJECT_ID)
    (project_dir / "artifacts/chart.png").write_bytes(b"\xff\xd8new-and-longer")
    after = workspace.snapshot_artifacts(PROJECT_ID)

    entries = workspace.diff_artifacts(before, after)

    assert [(e.path, e.kind, e.diff) for e in entries] == [
        ("chart.png", "updated", None)
    ]


def test_diff_artifacts_drops_counters_for_a_file_over_the_per_file_limit(
    make_workspace: Callable[..., Workspace], project_dir: Path
) -> None:
    workspace = make_workspace(diff_file_limit_bytes=8)
    write_file(project_dir / "artifacts/big.md", "a" * 100)
    before = workspace.snapshot_artifacts(PROJECT_ID)
    write_file(project_dir / "artifacts/big.md", "b" * 200)
    after = workspace.snapshot_artifacts(PROJECT_ID)

    entries = workspace.diff_artifacts(before, after)

    assert [(e.path, e.kind, e.diff) for e in entries] == [("big.md", "updated", None)]


def test_diff_artifacts_drops_counters_once_the_per_job_total_is_exceeded(
    make_workspace: Callable[..., Workspace], project_dir: Path
) -> None:
    # The copy budget is per snapshot, not per file: the first file fits, the
    # second one crosses the total and therefore loses its counters.
    workspace = make_workspace(diff_total_limit_bytes=12)
    write_file(project_dir / "artifacts/a.md", "a\n" * 5)
    write_file(project_dir / "artifacts/b.md", "b\n" * 5)
    before = workspace.snapshot_artifacts(PROJECT_ID)
    write_file(project_dir / "artifacts/a.md", "a\n" * 6)
    write_file(project_dir / "artifacts/b.md", "b\n" * 6)
    after = workspace.snapshot_artifacts(PROJECT_ID)

    diffs = {e.path: e.diff for e in workspace.diff_artifacts(before, after)}

    assert diffs["a.md"] is not None
    assert diffs["b.md"] is None


def test_snapshot_artifacts_ignores_the_layers_temp_files(
    workspace: Workspace, project_dir: Path
) -> None:
    before = workspace.snapshot_artifacts(PROJECT_ID)
    write_file(project_dir / f"artifacts/{TMP_FILE_PREFIX}xyz", "scratch")
    after = workspace.snapshot_artifacts(PROJECT_ID)

    assert workspace.diff_artifacts(before, after) == []


def test_snapshot_artifacts_never_reads_through_a_symlink_out_of_the_workspace(
    workspace: Workspace, project_dir: Path, tmp_path: Path
) -> None:
    """The snapshot walk is the one loop that bypasses the resolve barrier.

    `rglob` + `is_file()` + `read_text()` follow a link out of the zone without
    `resolve_path` ever running, so the outside file's *content* landed in the
    backend's memory and its *line counts* went out in the artifact envelope's
    diff. The link is invisible to the snapshot instead: appearing changes
    nothing, and rewriting the target changes nothing either.
    """
    outside = write_file(tmp_path / "outside" / "secret.txt", "line one\n")
    (project_dir / "artifacts").mkdir()

    before = workspace.snapshot_artifacts(PROJECT_ID)
    (project_dir / "artifacts/leak.txt").symlink_to(outside)
    after_link = workspace.snapshot_artifacts(PROJECT_ID)
    outside.write_text("line one\nline two\nline three\n", encoding="utf-8")
    after_rewrite = workspace.snapshot_artifacts(PROJECT_ID)

    assert after_link == {}
    assert workspace.diff_artifacts(before, after_link) == []
    assert workspace.diff_artifacts(after_link, after_rewrite) == []


def test_snapshot_artifacts_keeps_the_real_files_beside_a_skipped_symlink(
    workspace: Workspace, project_dir: Path, tmp_path: Path
) -> None:
    # The skip is per entry: the job's own output still has to be reported.
    outside = write_file(tmp_path / "outside" / "secret.txt", "s3cret\n")
    write_file(project_dir / "artifacts/notes.md", "one\n")
    (project_dir / "artifacts/leak.txt").symlink_to(outside)
    before = workspace.snapshot_artifacts(PROJECT_ID)
    write_file(project_dir / "artifacts/notes.md", "one\ntwo\n")
    after = workspace.snapshot_artifacts(PROJECT_ID)

    entries = workspace.diff_artifacts(before, after)

    assert [(e.path, e.kind) for e in entries] == [("notes.md", "updated")]


def test_snapshot_artifacts_records_a_warning_for_a_skipped_symlink(
    workspace: Workspace, project_dir: Path, tmp_path: Path
) -> None:
    outside = write_file(tmp_path / "outside" / "secret.txt", "s3cret\n")
    (project_dir / "artifacts").mkdir()
    (project_dir / "artifacts/leak.txt").symlink_to(outside)

    with capture_logs() as logs:
        workspace.snapshot_artifacts(PROJECT_ID)

    assert [
        entry["log_level"]
        for entry in logs
        if entry["event"] == "artifact snapshot skipped symlink"
    ] == ["warning"]


def test_snapshot_artifacts_survives_a_dangling_symlink(
    workspace: Workspace, project_dir: Path
) -> None:
    # `entry.is_file()` is already False for a broken link, so the pre-fix code
    # skipped it — but only because the check ran before `stat()`. Pinning it
    # keeps the ordering of the two guards from regressing into a crash.
    write_file(project_dir / "artifacts/notes.md", "one\n")
    (project_dir / "artifacts/dangling.txt").symlink_to(project_dir / "nope.txt")

    assert list(workspace.snapshot_artifacts(PROJECT_ID)) == ["notes.md"]


def test_snapshot_artifacts_of_a_project_without_artifacts_is_empty(
    workspace: Workspace, project_dir: Path
) -> None:
    assert workspace.snapshot_artifacts(PROJECT_ID) == {}


# --- lifecycle --------------------------------------------------------------


def test_delete_project_removes_the_whole_workspace_tree(
    workspace: Workspace, project_dir: Path
) -> None:
    write_file(project_dir / "artifacts/notes.md", "x")

    workspace.delete_project(PROJECT_ID)

    assert not project_dir.exists()


def test_delete_project_of_an_untouched_project_is_a_no_op(
    workspace: Workspace, workspaces_root: Path
) -> None:
    # Workspace creation is lazy, so "no directory" is the normal state of a
    # project the agent never wrote to — deleting it must not raise.
    workspace.delete_project("never-touched")

    assert list(workspaces_root.iterdir()) == []


# --- helpers shared by every artifact-producing call site --------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("artifacts/slides.md", "slides.md"),
        ("artifacts/lecture-1/slides.md", "lecture-1/slides.md"),
        ("uploads/lecture.pdf", None),
        ("notes.md", None),
    ],
)
def test_to_artifact_path_keeps_only_paths_inside_the_artifacts_zone(
    path: str, expected: str | None
) -> None:
    assert to_artifact_path(path) == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("slides.md", "md"),
        ("lecture-1/chart.PNG", "PNG"),
        ("archive.tar.gz", "gz"),
        ("Makefile", ""),
    ],
)
def test_artifact_type_is_the_extension_without_the_dot(
    path: str, expected: str
) -> None:
    assert artifact_type(path) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("lecture.pdf", "lecture.pdf", id="plain"),
        pytest.param("../../etc/passwd", "passwd", id="posix-traversal"),
        pytest.param("C:\\Users\\me\\notes.txt", "notes.txt", id="windows-path"),
        pytest.param("Лекция №1.md", "Лекция №1.md", id="cyrillic-preserved"),
        pytest.param("na\x00me.txt", "name.txt", id="control-chars-stripped"),
    ],
)
def test_sanitize_filename_reduces_a_name_to_a_safe_basename(
    raw: str, expected: str
) -> None:
    assert sanitize_filename(raw) == expected


@pytest.mark.parametrize("raw", ["", "..", ".", "\x00\x01"])
def test_sanitize_filename_falls_back_when_nothing_usable_is_left(raw: str) -> None:
    assert sanitize_filename(raw, fallback_stem="image").startswith("image-")


def test_unique_path_appends_a_numeric_suffix_on_collision(tmp_path: Path) -> None:
    # A repeated name must never overwrite the file an older message still
    # points at (design-brief § Вложения / generate_image).
    (tmp_path / "cover.png").write_bytes(b"first")
    (tmp_path / "cover-1.png").write_bytes(b"second")

    assert unique_path(tmp_path, "cover.png") == tmp_path / "cover-2.png"


def test_unique_path_returns_the_plain_name_when_free(tmp_path: Path) -> None:
    assert unique_path(tmp_path, "cover.png") == tmp_path / "cover.png"


@pytest.mark.parametrize(
    ("mime", "expected"),
    [
        ("image/png", "png"),
        ("image/jpeg", "jpg"),
        ("image/webp", "webp"),
        ("application/x-unknown-thing", "bin"),
    ],
)
def test_extension_from_mime_maps_the_image_mimes_the_tool_returns(
    mime: str, expected: str
) -> None:
    assert extension_from_mime(mime) == expected
