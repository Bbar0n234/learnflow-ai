"""Thin httpx client for the executor service (ADR-031, T1.4).

The only HTTP contract this module speaks: ``POST {executor_base_url}/jobs``
with ``{project_id, cmd, timeout}``, returning ``{stdout, stderr, exit_code}``
(``services/executor``'s ``JobRequest``/``JobResponse`` — cross-track
contract 2, `tracks/T3/plan.md` § EXECUTOR_-knobs). `execute_code` always
sends its scratch file's run command through the ``cmd`` branch — the
``code`` branch documented in the executor's own contract is T3's reserved
fallback, not something this client uses (T3 plan, OQ-1 resolution).

No retries: a job is not idempotent (it may have already run partway when a
timeout hits), so a failed/timed-out call is surfaced once, not retried
(conventions.md § Таймауты и retry).
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import structlog

from app.config import Settings

logger = structlog.get_logger()


class ExecutorUnavailableError(Exception):
    """The executor service could not be reached at all.

    Internal exception of this infra client (conventions.md § Обработка
    ошибок, категория 2: internal exception of a subsystem, not a member of
    the `AppError` hierarchy — this client backs no REST endpoint, so
    nothing here can reach an HTTP barrier). Raised only for transport-layer
    failures — connect refused, DNS failure, the client-side timeout
    elapsing before the executor could respond — never for a job that ran
    and produced a result (non-zero exit, in-job timeout are both a normal
    `JobResult`, decided by the executor, not this client). Callers
    (`agent/tools/execution.py`) catch it narrowly and turn it into in-band
    tool text ("execution runtime unavailable") instead of raising to the
    generic `ToolNode` error handler — the point being that the agent should
    not try to "fix" its code in response to an infrastructure outage.

    A non-2xx HTTP response (`httpx.HTTPStatusError`, raised by
    `raise_for_status()`) is deliberately *not* covered here: that signals a
    request our own code built wrong (e.g. a malformed `project_id`), which
    is a bug to surface through the ordinary `handle_tool_error` path, not
    an infra outage to mask behind an "unavailable" message.
    """


@dataclass(frozen=True)
class JobResult:
    """Result of a job the executor actually ran, whatever its outcome."""

    stdout: str
    stderr: str
    exit_code: int


async def run_job(
    settings: Settings, *, project_id: str, cmd: str, timeout: float
) -> JobResult:
    """``POST /jobs``: run ``cmd`` in ``project_id``'s workspace under ``timeout``.

    The client-side httpx timeout is ``timeout`` plus
    ``executor_client_timeout_grace_seconds`` — the executor's own kill
    contract only resolves a timed-out job after its deadline plus
    ``EXECUTOR_KILL_GRACE_SECONDS`` (design-brief § Executor), so the client
    must wait at least that long before treating a slow response as a
    transport failure rather than a job that is still being killed.

    Raises:
        ExecutorUnavailableError: transport-layer failure only (see class
            docstring). A non-2xx response or a malformed response body
            raises the underlying `httpx`/`KeyError` as-is.
    """
    client_timeout = timeout + settings.executor_client_timeout_grace_seconds
    body = {"project_id": project_id, "cmd": cmd, "timeout": timeout}
    try:
        async with httpx.AsyncClient(timeout=client_timeout) as client:
            response = await client.post(
                f"{settings.executor_base_url}/jobs", json=body
            )
        response.raise_for_status()
    except httpx.RequestError as exc:
        logger.warning(
            "executor unreachable",
            project_id=project_id,
            error_type=type(exc).__name__,
            exc_info=True,
        )
        raise ExecutorUnavailableError("execution runtime unavailable") from exc

    data = response.json()
    return JobResult(
        stdout=data["stdout"], stderr=data["stderr"], exit_code=data["exit_code"]
    )
