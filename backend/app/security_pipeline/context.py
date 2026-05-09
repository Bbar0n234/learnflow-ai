"""Security context management via structlog contextvars."""

from __future__ import annotations

import structlog


def bind_security_context(
    *,
    ip: str | None = None,
    request_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    thread_id: str | None = None,
    project_id: str | None = None,
    user_agent_hash: str | None = None,
) -> None:
    """Bind security context variables for current task.

    Args:
        ip: Client IP address
        request_id: HTTP request ID
        user_id: Authenticated user ID
        session_id: Session/refresh token ID
        thread_id: Chat thread ID
        project_id: Project ID
        user_agent_hash: User-Agent hash
    """
    context: dict[str, str] = {}
    if ip is not None:
        context["ip"] = ip
    if request_id is not None:
        context["request_id"] = request_id
    if user_id is not None:
        context["user_id"] = user_id
    if session_id is not None:
        context["session_id"] = session_id
    if thread_id is not None:
        context["thread_id"] = thread_id
    if project_id is not None:
        context["project_id"] = project_id
    if user_agent_hash is not None:
        context["user_agent_hash"] = user_agent_hash

    if context:
        structlog.contextvars.bind_contextvars(**context)


def clear_security_context() -> None:
    """Clear all security context variables."""
    structlog.contextvars.unbind_contextvars(
        "ip",
        "request_id",
        "user_id",
        "session_id",
        "thread_id",
        "project_id",
        "user_agent_hash",
    )
