"""bind/clear security context — structlog contextvars round-trip.

These vars are picked up by the security-event processor downstream, so the
behavior under test is "what ends up in the contextvars", not any log output.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import structlog
from app.security_pipeline.context import (
    bind_security_context,
    clear_security_context,
)


@pytest.fixture(autouse=True)
def _clean_contextvars() -> Iterator[None]:
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()


@pytest.mark.unit
def test_bind_security_context_sets_provided_fields() -> None:
    bind_security_context(ip="10.0.0.1", user_id="u-1", thread_id="t-1")

    ctx = structlog.contextvars.get_contextvars()

    assert ctx["ip"] == "10.0.0.1"
    assert ctx["user_id"] == "u-1"
    assert ctx["thread_id"] == "t-1"


@pytest.mark.unit
def test_bind_security_context_omits_none_fields() -> None:
    bind_security_context(ip="10.0.0.1")

    ctx = structlog.contextvars.get_contextvars()

    assert ctx["ip"] == "10.0.0.1"
    assert "user_id" not in ctx
    assert "thread_id" not in ctx


@pytest.mark.unit
def test_bind_security_context_sets_all_fields() -> None:
    bind_security_context(
        ip="10.0.0.1",
        request_id="r-1",
        user_id="u-1",
        session_id="s-1",
        thread_id="t-1",
        project_id="p-1",
        user_agent_hash="ua-1",
    )

    ctx = structlog.contextvars.get_contextvars()

    assert ctx["request_id"] == "r-1"
    assert ctx["session_id"] == "s-1"
    assert ctx["project_id"] == "p-1"
    assert ctx["user_agent_hash"] == "ua-1"


@pytest.mark.unit
def test_bind_security_context_with_no_fields_binds_nothing() -> None:
    bind_security_context()

    ctx = structlog.contextvars.get_contextvars()

    assert ctx == {}


@pytest.mark.unit
def test_clear_security_context_removes_bound_fields() -> None:
    bind_security_context(ip="10.0.0.1", user_id="u-1")

    clear_security_context()

    ctx = structlog.contextvars.get_contextvars()
    assert "ip" not in ctx
    assert "user_id" not in ctx
