"""Sandbox argv/env construction for the executor job runtime.

Pure, side-effect-free helpers: `build_job_argv` assembles the full
`unshare … bwrap … -- <command>` prefix (spike variant A —
doc/tasks/iterations/dogfooding/feat-011-execution-runtime/spikes/spike-bwrap-gvisor.md)
and `resolve_workspace` validates a `project_id` into a workspace path.
Neither spawns a process — that is the job runner's concern (T3.4).

Mount set is a security invariant and therefore lives in this module's code,
not in `Settings`/env (conventions.md § Что попадает в env, design-brief
§ Executor).
"""

import re
import sys
from collections.abc import Sequence
from pathlib import Path

import structlog

from executor.config import Settings
from executor.exceptions import InvalidProjectIdError, WorkspaceMissingError

logger = structlog.get_logger()

# Single safe path segment: no `/`, no leading `.`/`..` traversal tricks.
# `.` and `..` match this charset and are rejected explicitly below.
_PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_RESERVED_PROJECT_IDS = frozenset({".", ".."})

# merged-usr symlinks (Debian/Ubuntu/Fedora layout) — mirrors spike variant A.
# Each pair is (bwrap SRC, bwrap DEST): `--symlink SRC DEST` creates a
# symlink at DEST pointing to SRC.
_MERGED_USR_SYMLINKS: tuple[tuple[str, str], ...] = (
    ("usr/bin", "/bin"),
    ("usr/lib", "/lib"),
    ("usr/lib64", "/lib64"),
    ("usr/sbin", "/sbin"),
)

# Narrowed `/etc` ro-binds (spike note: "в боевом образе сузить до
# необходимого"). `resolv.conf` is deliberately absent — the job has no
# network (empty netns, § kill-контракт). Exact set is confirmed by the
# T3.7 image smoke run; entries missing on a given host are skipped rather
# than failing the whole prefix.
_ETC_RO_BINDS: tuple[str, ...] = (
    "/etc/ld.so.cache",
    "/etc/passwd",
    "/etc/group",
    "/etc/ssl/certs",
    "/etc/fonts",
)


def resolve_workspace(project_id: str, settings: Settings) -> Path:
    """Resolve `project_id` into an existing workspace directory.

    `project_id` must be a single safe path segment; the resolved path must
    stay inside `settings.workspaces_root`. The executor never creates
    workspace directories (backend's job) — a missing one is an error.
    """
    if project_id in _RESERVED_PROJECT_IDS or not _PROJECT_ID_PATTERN.match(project_id):
        raise InvalidProjectIdError(project_id)

    workspaces_root = Path(settings.workspaces_root).resolve()
    workspace = (workspaces_root / project_id).resolve()

    if not workspace.is_relative_to(workspaces_root):
        raise InvalidProjectIdError(project_id)

    if not workspace.is_dir():
        raise WorkspaceMissingError(project_id, workspace)

    return workspace


def build_job_argv(
    workspace: Path,
    command: list[str],
    settings: Settings,
    *,
    extra_ro_binds: Sequence[tuple[str, str]] = (),
) -> list[str]:
    """Build the full argv a job is executed with.

    `sandbox_enabled=False` is a dev escape hatch for environments without
    userns support — it returns the bare command and logs a WARNING on
    every call (observable degradation, conventions.md § Восстановление;
    no silent fallback). `extra_ro_binds` is ignored on this path — there is
    no mount namespace to remap anything onto.

    Otherwise returns spike variant A: an outer `unshare -U
    --map-current-user -n` (bwrap's own `--unshare-net` is fatal under
    gVisor — spike finding 3) wrapping a `bwrap` invocation carrying the
    kill-contract flags (`--unshare-pid --die-with-parent --new-session`)
    plus the rest of the isolation and mount set.

    `extra_ro_binds` — additional `(src, dest)` ro-binds (e.g. the `POST
    /jobs` `code` branch's temp-file-as-`/tmp/job.py`, api/routes.py). Must
    be applied *after* `--tmpfs /tmp` in argv order: bwrap applies mount
    operations sequentially, so a bind placed before `--tmpfs /tmp` would be
    masked by the tmpfs mounted on top of it.
    """
    if not settings.sandbox_enabled:
        logger.warning("running job unsandboxed", sandbox_enabled=False)
        return list(command)

    venv_prefix = sys.prefix
    job_path = f"{venv_prefix}/bin:/usr/local/bin:/usr/bin:/bin"

    argv: list[str] = [
        "unshare",
        "-U",
        "--map-current-user",
        "-n",
        "bwrap",
        # Kill-contract flags (all three required — design-brief § Executor).
        "--unshare-pid",
        "--die-with-parent",
        "--new-session",
        # Remaining isolation.
        "--unshare-user",
        "--unshare-ipc",
        "--unshare-uts",
        "--clearenv",
        "--setenv",
        "PATH",
        job_path,
        "--setenv",
        "HOME",
        "/workspace",
        "--setenv",
        "LANG",
        "C.UTF-8",
        "--setenv",
        "MPLCONFIGDIR",
        "/tmp/mpl",
        "--setenv",
        "XDG_CACHE_HOME",
        "/tmp/cache",
        "--ro-bind",
        "/usr",
        "/usr",
    ]
    for src, dest in _MERGED_USR_SYMLINKS:
        argv += ["--symlink", src, dest]
    for etc_path in _ETC_RO_BINDS:
        if Path(etc_path).exists():
            argv += ["--ro-bind", etc_path, etc_path]
    argv += [
        "--ro-bind",
        venv_prefix,
        venv_prefix,
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
    ]
    # Must come after `--tmpfs /tmp` above — see docstring.
    for src, dest in extra_ro_binds:
        argv += ["--ro-bind", src, dest]
    argv += [
        "--bind",
        str(workspace),
        "/workspace",
        "--ro-bind",
        settings.skills_root,
        "/skills",
        "--chdir",
        "/workspace",
        "--",
        *command,
    ]
    return argv
