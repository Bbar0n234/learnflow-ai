"""Job runner: synchronous execution of a prepared argv under a hard deadline.

Owns the parts of the kill-контракт that live outside `bwrap` itself
(design-brief § Executor): `start_new_session=True` puts the wrapper
(`unshare`+`bwrap`) in its own process group so a deadline can `killpg` it
without touching the caller's session; `--die-with-parent` and
`--unshare-pid` (both baked into the argv by `executor.sandbox`) take it
from there — `bwrap`'s death delivers PDEATHSIG to the sandboxed job, and
the job being pid 1 of its own pid namespace means its death collapses that
namespace, taking any grandchildren with it.

A job's own failure (non-zero exit, timeout) is a normal `JobResult`, not an
exception — the "job failed" vs "runner couldn't even start it" distinction
lives here per conventions.md § Logging (WARNING vs ERROR).
"""

import contextlib
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO

import structlog

from executor.config import Settings
from executor.sandbox import build_job_argv

logger = structlog.get_logger()

# Reader threads drain pipes in chunks rather than via `communicate()`, which
# buffers unboundedly — exactly the OOM scenario `max_output_bytes` guards
# against. Chunk size is an I/O tuning constant, not a security boundary.
_READ_CHUNK_BYTES = 65536


# Minimal job environment — identical values to the ones `executor.sandbox`
# bakes into the sandboxed job via `--setenv` (matplotlib/fontconfig need a
# writable cache dir even off the sandboxed path). This is also the env the
# outer `unshare`/`bwrap` wrapper processes run with when sandboxing is on:
# they only need enough `PATH` to find their own binaries, since `bwrap`
# clears and rebuilds the job's env internally regardless of what Popen
# passes it. When sandboxing is disabled (dev escape hatch, `sandbox.
# build_job_argv` returns the bare command), this *is* the job's env — kept
# scrubbed for the same reason `--clearenv` exists: the job must not see the
# executor service's own environment.
def _job_env() -> dict[str, str]:
    return {
        "PATH": f"{sys.prefix}/bin:/usr/local/bin:/usr/bin:/bin",
        "HOME": "/workspace",
        "LANG": "C.UTF-8",
        "MPLCONFIGDIR": "/tmp/mpl",
        "XDG_CACHE_HOME": "/tmp/cache",
    }


@dataclass(frozen=True, slots=True)
class JobResult:
    """Outcome of a job run — always a result, never an exception.

    `exit_code` follows `subprocess` convention: negative when the process
    was killed by a signal (e.g. -9 after the SIGTERM→SIGKILL escalation on
    deadline). `timed_out` is the explicit signal for "this negative
    exit_code is the deadline, not the job's own choice to die by signal".
    """

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool


class _PipeReader:
    """Drains a subprocess pipe in a background thread, capped at `max_bytes`.

    Keeps reading until EOF even past the cap — an unread pipe fills its
    kernel buffer and blocks the writer, which would hang the job until the
    deadline instead of finishing on its own. Bytes past the cap are counted
    and dropped, never buffered.

    What has been read so far is readable at any moment, including while the
    reader thread is still running: `_drain` gives up on a pipe that never
    reaches EOF and `run_job` takes the partial output. The lock is what
    makes that safe — a `bytearray` cannot be decoded and appended to at the
    same time.
    """

    def __init__(self, pipe: IO[bytes], max_bytes: int) -> None:
        self._pipe = pipe
        self._max_bytes = max(max_bytes, 0)
        self._buffer = bytearray()
        self._total_bytes = 0
        self._lock = threading.Lock()

    def run(self) -> None:
        # `os.read` on the raw descriptor rather than the buffered `read()`:
        # the latter blocks until it has a full chunk, so anything shorter
        # sits invisible in Python's buffer instead of in `self._buffer` —
        # which is exactly what a caller that gave up on this pipe would
        # lose. Both return empty only at EOF.
        fd = self._pipe.fileno()
        while True:
            chunk = os.read(fd, _READ_CHUNK_BYTES)
            if not chunk:
                return
            with self._lock:
                self._total_bytes += len(chunk)
                room = self._max_bytes - len(self._buffer)
                if room > 0:
                    self._buffer += chunk[:room]

    @property
    def truncated(self) -> bool:
        with self._lock:
            return self._total_bytes > self._max_bytes

    def text(self) -> str:
        with self._lock:
            decoded = self._buffer.decode("utf-8", errors="replace")
            dropped = self._total_bytes - self._max_bytes
        if dropped > 0:
            decoded += f"\n…[output truncated: {dropped} bytes dropped]"
        return decoded


def _kill_process_group(
    proc: "subprocess.Popen[bytes]", kill_grace_seconds: float
) -> None:
    """Escalate SIGTERM → (grace) → SIGKILL against the wrapper's process group.

    Targets the group, not the pid: `start_new_session=True` made the
    wrapper (`unshare`+`bwrap`) its own group leader, and the sandboxed job
    lives one `--die-with-parent` + pid-namespace-collapse hop further down
    — unreachable directly, reachable via this chain.
    """
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        # Already gone — still reap it, so `proc.returncode` is a number and
        # not `None` on the way into `JobResult.exit_code`.
        proc.wait()
        return

    try:
        proc.wait(timeout=kill_grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass

    with contextlib.suppress(ProcessLookupError):
        os.killpg(pgid, signal.SIGKILL)
    proc.wait()


def _drain(threads: tuple[threading.Thread, ...], grace_seconds: float) -> bool:
    """Wait out the pipe readers under a shared deadline; True if both finished.

    A reader returns when its pipe reaches EOF, which requires every copy of
    the write end to be closed. Under the sandbox that is guaranteed by the
    kill-контракт: the job is pid 1 of its own pid namespace, so its death
    collapses the namespace and no descendant can outlive it holding a pipe.

    On the dev escape hatch (`sandbox_enabled=False`) there is no pid
    namespace, so a process that detached itself from the job's process group
    (`setsid … &`) survives the killpg and keeps the write end open
    indefinitely. Waiting unconditionally would hang `run_job` — and with it
    the request — long past the deadline it exists to enforce. So the wait is
    bounded: past the grace, the job's outcome is reported with whatever
    output was captured, and the orphaned reader threads (daemon) are left to
    exit whenever that process finally does.
    """
    drain_until = time.monotonic() + grace_seconds
    for thread in threads:
        thread.join(timeout=max(drain_until - time.monotonic(), 0.0))
    return not any(thread.is_alive() for thread in threads)


def run_job(
    workspace: Path,
    command: list[str],
    timeout: float,
    settings: Settings,
    *,
    extra_ro_binds: Sequence[tuple[str, str]] = (),
) -> JobResult:
    """Run `command` inside `workspace` under `timeout`, honoring the deadline.

    `command` is the job's own argv (e.g. `["bash", "-c", cmd]`) —
    `executor.sandbox.build_job_argv` wraps it with the `unshare`/`bwrap`
    isolation prefix (or returns it bare when `settings.sandbox_enabled` is
    `False`). `extra_ro_binds` passes through to `build_job_argv` unchanged
    (the `POST /jobs` `code` branch's temp-file-as-`/tmp/job.py` ro-bind).
    """
    project_id = workspace.name
    argv = build_job_argv(workspace, command, settings, extra_ro_binds=extra_ro_binds)

    started_at = time.monotonic()
    try:
        proc: subprocess.Popen[bytes] = subprocess.Popen(
            argv,
            start_new_session=True,
            env=_job_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=workspace,
        )
    except OSError as exc:
        # Infrastructural failure to even start the job (e.g. `unshare`/
        # `bwrap` missing from PATH) — not a job outcome, so it does not
        # become a JobResult. § Logging: ERROR is reserved for exactly this.
        logger.error(
            "job launch failed",
            project_id=project_id,
            error=str(exc),
            error_type=type(exc).__name__,
            exc_info=True,
        )
        raise

    # `stdout=PIPE, stderr=PIPE` above guarantee these are open pipes, not
    # `None` — the `Popen` signature only allows `None` because callers can
    # opt out of capturing either stream.
    assert proc.stdout is not None
    assert proc.stderr is not None
    stdout_reader = _PipeReader(proc.stdout, settings.max_output_bytes)
    stderr_reader = _PipeReader(proc.stderr, settings.max_output_bytes)
    stdout_thread = threading.Thread(target=stdout_reader.run, daemon=True)
    stderr_thread = threading.Thread(target=stderr_reader.run, daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_process_group(proc, settings.kill_grace_seconds)

    # The wrapper process has exited either way — its stdout/stderr write
    # ends (and, once the kill-контракт chain above has run its course, any
    # grandchildren's copies of them) are closed, so these normally reach EOF
    # and return on their own. `_drain` bounds the wait anyway: see its
    # docstring for the one case that does not hold.
    output_incomplete = not _drain(
        (stdout_thread, stderr_thread), settings.kill_grace_seconds
    )

    duration_ms = round((time.monotonic() - started_at) * 1000)
    stdout_text = stdout_reader.text()
    stderr_text = stderr_reader.text()
    if timed_out:
        stderr_text += (
            f"\n[executor] job exceeded timeout of {timeout}s — killed "
            f"(SIGTERM, then SIGKILL after {settings.kill_grace_seconds}s grace)"
        )
    if output_incomplete:
        # Same channel as the truncation notice: `JobResponse` carries fixed
        # fields, so a degraded capture has to be visible in the output itself
        # or the agent silently reads a partial answer as a complete one.
        stderr_text += (
            "\n[executor] output capture incomplete: a process outlived the job "
            "holding its pipes open — output beyond this point was not captured"
        )

    result = JobResult(
        stdout=stdout_text,
        stderr=stderr_text,
        exit_code=proc.returncode,
        timed_out=timed_out,
    )

    # § Logging: WARNING is "the service coped, but something was off" — an
    # overrun and a degraded capture are both that.
    log = logger.warning if timed_out or output_incomplete else logger.info
    log(
        "job finished",
        project_id=project_id,
        exit_code=result.exit_code,
        duration_ms=duration_ms,
        timed_out=timed_out,
        stdout_truncated=stdout_reader.truncated,
        stderr_truncated=stderr_reader.truncated,
        output_incomplete=output_incomplete,
    )

    return result
