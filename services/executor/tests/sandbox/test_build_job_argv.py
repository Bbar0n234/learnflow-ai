"""The argv a job is launched with — the isolation contract in list form.

`build_job_argv` is where every sandbox guarantee is decided: the job's network
namespace, the three kill-contract flags, the scrubbed environment, and the set
of paths that exist at all inside the job's mount namespace. Running the result
needs unprivileged user namespaces (unavailable here — see `tests/conftest.py`),
so these tests assert the command itself: what bwrap is told is exactly what the
job gets.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from executor.config import Settings
from executor.sandbox import build_job_argv
from structlog.testing import capture_logs

COMMAND = ["bash", "-c", "echo hi"]

# `--setenv NAME VALUE` — the complete environment a sandboxed job may see
# (design-brief § Executor: "Env джобы — чистый").
EXPECTED_JOB_ENV_KEYS = {"PATH", "HOME", "LANG", "MPLCONFIGDIR", "XDG_CACHE_HOME"}


def _flag_triples(argv: list[str], flag: str) -> list[tuple[str, str]]:
    """Collect `(arg1, arg2)` pairs following every occurrence of a 2-arg flag."""
    return [(argv[i + 1], argv[i + 2]) for i, item in enumerate(argv) if item == flag]


def _bwrap_flags(argv: list[str]) -> list[str]:
    """The slice bwrap itself parses: everything between `bwrap` and `--`.

    Position is part of the contract, not decoration. A flag that drifts past
    the `--` separator stops configuring the sandbox and becomes an argument of
    the job's own command — isolation silently gone, argv still containing the
    word. Asserting membership in this slice is what tells the two apart.
    """
    return argv[argv.index("bwrap") + 1 : argv.index("--")]


@pytest.fixture
def sandboxed_settings(make_settings: Callable[..., Settings]) -> Settings:
    return make_settings(sandbox_enabled=True)


@pytest.mark.unit
def test_build_job_argv_sandboxed_passes_command_through_after_separator(
    workspace: Path, sandboxed_settings: Settings
) -> None:
    argv = build_job_argv(workspace, COMMAND, sandboxed_settings)

    assert argv[argv.index("--") + 1 :] == COMMAND


@pytest.mark.unit
def test_build_job_argv_sandboxed_strips_network_via_outer_unshare(
    workspace: Path, sandboxed_settings: Settings
) -> None:
    """Network isolation comes from the outer `unshare -n`, never from bwrap.

    bwrap's own `--unshare-net` leaves the job without a loopback device and is
    fatal under gVisor (spike finding 3) — the wrapper must stay outside.
    """
    argv = build_job_argv(workspace, COMMAND, sandboxed_settings)

    assert argv[:5] == ["unshare", "-U", "--map-current-user", "-n", "bwrap"]
    assert "--unshare-net" not in argv


@pytest.mark.unit
@pytest.mark.parametrize(
    "flag", ["--unshare-pid", "--die-with-parent", "--new-session"]
)
def test_build_job_argv_sandboxed_carries_kill_contract_flag(
    workspace: Path, sandboxed_settings: Settings, flag: str
) -> None:
    """All three links of the kill chain are mandatory, not tuning knobs.

    Without `--new-session` the deadline's `killpg` reaches the wrapper only;
    `--die-with-parent` passes the kill on to the job, and `--unshare-pid` makes
    the job pid 1 so its death collapses the namespace and takes grandchildren
    (pandoc, shell pipelines) with it.
    """
    argv = build_job_argv(workspace, COMMAND, sandboxed_settings)

    assert flag in _bwrap_flags(argv)


@pytest.mark.unit
def test_build_job_argv_sandboxed_mounts_only_workspace_rw(
    workspace: Path, sandboxed_settings: Settings, workspaces_root: Path
) -> None:
    """The single writable mount is this project's own workspace.

    Sibling workspaces are absent from the job's mount namespace entirely —
    which is what makes a cross-project path fail with ENOENT rather than a
    permission check somebody could bargain with.
    """
    (workspaces_root / "other-project").mkdir()

    argv = build_job_argv(workspace, COMMAND, sandboxed_settings)

    assert _flag_triples(argv, "--bind") == [(str(workspace), "/workspace")]
    assert argv[argv.index("--chdir") + 1] == "/workspace"
    assert str(workspaces_root / "other-project") not in argv


@pytest.mark.unit
def test_build_job_argv_sandboxed_mounts_skills_read_only(
    workspace: Path, sandboxed_settings: Settings, skills_root: Path
) -> None:
    argv = build_job_argv(workspace, COMMAND, sandboxed_settings)

    assert (str(skills_root), "/skills") in _flag_triples(argv, "--ro-bind")


@pytest.mark.unit
def test_build_job_argv_sandboxed_mounts_toolchain_read_only(
    workspace: Path, sandboxed_settings: Settings
) -> None:
    """The job gets the image toolchain and the service venv — read-only.

    Plus the pseudo-filesystems it cannot run without: its own `/proc` (pid
    namespace) and a writable `/tmp` that is a tmpfs, not the host's.
    """
    argv = build_job_argv(workspace, COMMAND, sandboxed_settings)
    ro_binds = _flag_triples(argv, "--ro-bind")

    assert ("/usr", "/usr") in ro_binds
    assert (sys.prefix, sys.prefix) in ro_binds
    assert argv[argv.index("--proc") + 1] == "/proc"
    assert argv[argv.index("--tmpfs") + 1] == "/tmp"


@pytest.mark.unit
def test_build_job_argv_sandboxed_binds_only_existing_paths(
    workspace: Path, sandboxed_settings: Settings
) -> None:
    """Every bind source exists on this host.

    bwrap aborts on a missing bind source, so an unconditional bind of a path
    that a given base image happens not to ship (the `/etc` set differs between
    distributions) would turn every job into a launch failure.
    """
    argv = build_job_argv(workspace, COMMAND, sandboxed_settings)
    sources = [
        src
        for flag in ("--bind", "--ro-bind")
        for src, _dest in _flag_triples(argv, flag)
    ]

    assert sources, "expected the sandbox to bind at least the workspace"
    assert [src for src in sources if not Path(src).exists()] == []


@pytest.mark.unit
def test_build_job_argv_sandboxed_scrubs_environment_to_minimal_set(
    workspace: Path, sandboxed_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The job's environment is built from nothing, not inherited and filtered."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://secret@db/learnflow")

    argv = build_job_argv(workspace, COMMAND, sandboxed_settings)
    set_env = dict(_flag_triples(argv, "--setenv"))

    assert "--clearenv" in _bwrap_flags(argv)
    assert set(set_env) == EXPECTED_JOB_ENV_KEYS
    assert set_env["PATH"].startswith(f"{sys.prefix}/bin:")
    assert set_env["HOME"] == "/workspace"
    assert "postgresql://secret@db/learnflow" not in argv


@pytest.mark.unit
def test_build_job_argv_sandboxed_applies_extra_ro_binds_after_tmpfs(
    workspace: Path, sandboxed_settings: Settings
) -> None:
    """A file bound into `/tmp` must be bound after the tmpfs that covers it.

    bwrap applies mount operations in argv order — the `code` branch's
    `/tmp/job.py` bound before `--tmpfs /tmp` would be masked and the job would
    fail to find its own source file.
    """
    argv = build_job_argv(
        workspace,
        COMMAND,
        sandboxed_settings,
        extra_ro_binds=[("/etc/hostname", "/tmp/job.py")],
    )

    tmpfs_at = argv.index("--tmpfs")
    bind_at = argv.index("/tmp/job.py") - 2

    assert argv[bind_at : bind_at + 3] == ["--ro-bind", "/etc/hostname", "/tmp/job.py"]
    assert tmpfs_at < bind_at


@pytest.mark.unit
def test_build_job_argv_unsandboxed_returns_bare_command(
    workspace: Path, settings: Settings
) -> None:
    """The dev escape hatch runs the command as-is, with no wrapper at all."""
    argv = build_job_argv(workspace, COMMAND, settings)

    assert argv == COMMAND
    assert argv is not COMMAND


@pytest.mark.unit
def test_build_job_argv_unsandboxed_warns_on_every_call(
    workspace: Path, settings: Settings
) -> None:
    """Degradation is observable per job, not once per process start.

    A single warning at configuration time would scroll away; the contract is
    that no job ever runs unsandboxed without saying so (conventions.md
    § Восстановление — no silent fallback).
    """
    with capture_logs() as logs:
        build_job_argv(workspace, COMMAND, settings)
        build_job_argv(workspace, COMMAND, settings)

    warnings = [entry for entry in logs if entry["log_level"] == "warning"]
    assert len(warnings) == 2
    assert all(entry["sandbox_enabled"] is False for entry in warnings)


@pytest.mark.unit
def test_build_job_argv_sandboxed_does_not_warn(
    workspace: Path, sandboxed_settings: Settings
) -> None:
    with capture_logs() as logs:
        build_job_argv(workspace, COMMAND, sandboxed_settings)

    assert [entry for entry in logs if entry["log_level"] == "warning"] == []
