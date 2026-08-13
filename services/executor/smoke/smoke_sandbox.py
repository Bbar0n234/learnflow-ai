"""Smoke test: the full `unshare … bwrap …` prefix from `executor.sandbox`,
run inside the built image via `executor.runner.run_job` end to end.

Mirrors the isolation matrix from
`spikes/spike-bwrap-gvisor.md` (C1/C2): own-workspace read/write succeeds,
a path outside the single workspace bind is ENOENT (`/workspaces` itself
isn't mounted into the job's mount namespace — only the one `/workspace`
bind is), `/skills` is read-only (EROFS), and no outbound socket connects
(empty netns via the outer `unshare -n`).

Under `--runtime=runsc` this script *is* the production verification of
bwrap under gVisor that design-brief § Executor and the spike's "Первая
проверка на проде" call for.

Imports `executor.*` via `PYTHONPATH` set by `run_all.sh` — the package
isn't pip-installed into the shared venv (same convention as the rest of
the repo's standalone scripts, e.g. `backend/scripts/*` run with
`PYTHONPATH=.`).
"""

from _common import report
from executor.config import Settings
from executor.runner import run_job
from executor.sandbox import resolve_workspace

NAME = "sandbox"

# Provisioned by `make smoke-executor` (chowned to uid 10001 before the
# container starts — gVisor requires the workspace dir to be owned by the
# job's uid, spike finding 4).
_PROJECT_ID = "smoke"

# Executed *inside* the sandbox by a fresh `python3 -c`, isolated in its own
# process — not linted as part of this file (plain string content), and
# intentionally free of anything beyond stdlib so it works regardless of
# which interpreter the sandbox's PATH resolves.
_INNER_SCRIPT = """
import socket

results = {}

try:
    with open("/workspace/smoke_marker.txt", "w") as f:
        f.write("ok")
    with open("/workspace/smoke_marker.txt") as f:
        results["own_workspace"] = f.read() == "ok"
except OSError:
    results["own_workspace"] = False

try:
    open("/workspaces/other-project/secret.txt")
    results["foreign_enoent"] = False
except FileNotFoundError:
    results["foreign_enoent"] = True
except OSError:
    results["foreign_enoent"] = False

try:
    with open("/skills/__smoke_write_test__", "w") as f:
        f.write("x")
    results["skills_erofs"] = False
except OSError:
    results["skills_erofs"] = True

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    s.connect(("1.1.1.1", 443))
    s.close()
    results["no_network"] = False
except OSError:
    results["no_network"] = True

print("SMOKE_SANDBOX " + " ".join(f"{k}={v}" for k, v in sorted(results.items())))
"""


def main() -> None:
    settings = Settings()
    if not settings.sandbox_enabled:
        raise AssertionError(
            "EXECUTOR_SANDBOX_ENABLED=false — this scenario verifies the bwrap "
            "prefix itself, a disabled sandbox can't exercise it"
        )

    workspace = resolve_workspace(_PROJECT_ID, settings)
    result = run_job(
        workspace, ["python3", "-c", _INNER_SCRIPT], timeout=30, settings=settings
    )

    if result.timed_out:
        raise AssertionError(f"job timed out: stderr={result.stderr!r}")
    if result.exit_code != 0:
        raise AssertionError(
            f"job exited {result.exit_code}: stdout={result.stdout!r} stderr={result.stderr!r}"
        )

    result_line = next(
        (
            candidate
            for candidate in result.stdout.splitlines()
            if candidate.startswith("SMOKE_SANDBOX ")
        ),
        None,
    )
    if result_line is None:
        raise AssertionError(
            f"no SMOKE_SANDBOX result line in stdout: {result.stdout!r}"
        )

    checks = dict(
        item.split("=", 1)
        for item in result_line.removeprefix("SMOKE_SANDBOX ").split()
    )
    failed = {k: v for k, v in checks.items() if v != "True"}
    if failed:
        raise AssertionError(
            f"sandbox checks failed: {failed} (full stdout: {result.stdout!r})"
        )


if __name__ == "__main__":
    report(NAME, main)
