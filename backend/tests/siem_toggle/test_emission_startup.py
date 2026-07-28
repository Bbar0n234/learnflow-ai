"""Startup wiring of the SIEM kill-switch: what ``lifespan`` builds, and what
it says while doing it.

The switch lives in a single ``if/elif`` inside ``app.main.lifespan``: with the
flag off no ``RedisEventTransport`` is created and no publisher loop is started,
so the holder stays empty and the structlog processor drops security events on
the floor. What makes it a kill-switch rather than a silent degradation is the
log line — "off by flag" and "Redis is down" must stay two distinguishable
states, because before this iteration both produced the same empty holder and
the same silence (design-brief § 1 «Принятые следствия»).

**Why the lifespan is cut short.** There is no seam around that block: it is
composition-root code, and everything after it needs Postgres (LangGraph store
and checkpointer), the network (built-in MCP validation) and an LLM. So the
suite stubs the boundary resources the block actually consumes — the SQLAlchemy
engine, Langfuse, ``create_redis`` — and replaces ``create_store`` (the next
piece of real infrastructure) with a sentinel that raises. Startup therefore
runs for real up to and including the block under test and stops right after it.
The cut is the honest cost of testing a monolithic lifespan; it is deliberately
placed at an infrastructure call, not at an arbitrary line, so that ordinary
refactoring of the block does not move it.

``setup_logging`` is stubbed too — it reconfigures global structlog and stdlib
logging for the whole process — but the stub keeps the processor the app built,
so the tests can exercise the real production processor against the holder the
app really published. Log assertions go through ``structlog.testing.capture_logs``
(conventions/testing.md § Async и pytest).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

import pytest
import pytest_asyncio
import structlog
from app import main as main_module
from app.config import Settings
from app.security_pipeline.transport import EventTransportHolder
from fastapi import FastAPI
from siem_contracts.vocabulary import AUTH_LOGIN_FAILED
from structlog.testing import capture_logs

DISABLED_BY_FLAG = "siem event emission disabled by flag"
PUBLISHER_STARTED = "security event publisher started"


class _StartupCut(Exception):
    """Raised in place of the LangGraph store — the end of the tested path."""


class _FakeConnection:
    """The one thing lifespan does with a connection: ``SELECT 1``."""

    async def execute(self, statement: Any) -> None:
        return None

    async def __aenter__(self) -> _FakeConnection:
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class _FakeEngine:
    """Stands in for the SQLAlchemy engine: no Postgres in this scope."""

    def connect(self) -> _FakeConnection:
        return _FakeConnection()


class _StubRedis:
    """An "available Redis" that records what the publisher loop writes.

    Only ``xadd`` is ever reached from this scope (the publisher loop blocks on
    an empty queue until an event shows up), so the stub implements that one
    method and signals arrivals through an event the tests can await.
    """

    def __init__(self) -> None:
        self.streamed: list[dict[str, Any]] = []
        self.arrival = asyncio.Event()

    # Signature mirrors redis.asyncio.Redis.xadd.
    async def xadd(self, name: str, fields: dict[Any, Any], **_kwargs: Any) -> str:
        self.streamed.append({"stream": name, "fields": fields})
        self.arrival.set()
        return "0-1"


@dataclass
class _Startup:
    """What one startup run left behind, for the assertions to look at."""

    app: FastAPI
    #: ``event`` keys of everything startup logged, in order.
    events: list[str] = field(default_factory=list)
    #: The processor instance the app passed to ``setup_logging``.
    processor: structlog.types.Processor | None = None


StartApp = Callable[..., Coroutine[Any, Any, _Startup]]


@pytest_asyncio.fixture
async def start_app(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[StartApp]:
    """Run ``lifespan`` up to the LangGraph store with infra stubbed out."""
    started: list[_Startup] = []

    async def _start(*, siem_enabled: str, redis: object | None = None) -> _Startup:
        monkeypatch.setenv("SIEM_ENABLED", siem_enabled)
        # The composition root reads several other knobs from the ambient
        # environment; only the ones that would reach the network or a real
        # database are neutralized here.
        monkeypatch.setattr(main_module, "init_langfuse", lambda **_: False)
        monkeypatch.setattr(
            main_module, "create_engine", lambda _settings: _FakeEngine()
        )
        monkeypatch.setattr(main_module, "create_session_factory", lambda _engine: None)

        async def _create_redis(_settings: Settings) -> object | None:
            return redis

        monkeypatch.setattr(main_module, "create_redis", _create_redis)

        result = _Startup(app=FastAPI())

        def _capture_setup_logging(**kwargs: Any) -> None:
            result.processor = kwargs["security_event_processor"]

        monkeypatch.setattr(main_module, "setup_logging", _capture_setup_logging)

        def _cut(*_args: Any, **_kwargs: Any) -> None:
            raise _StartupCut

        monkeypatch.setattr(main_module, "create_store", _cut)

        with capture_logs() as logs, pytest.raises(_StartupCut):
            await main_module.lifespan(result.app).__aenter__()

        result.events = [str(entry.get("event", "")) for entry in logs]
        started.append(result)
        return result

    yield _start

    for run in started:
        task = getattr(run.app.state, "security_publisher_task", None)
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


def _security_event() -> dict[str, Any]:
    """A log record shaped like the ones ``api/routes/auth.py`` emits."""
    return {
        "event": "login failed",
        "security_event": True,
        "event_type": AUTH_LOGIN_FAILED,
        "ip": "198.51.100.10",
    }


# --- flag off ---------------------------------------------------------------


@pytest.mark.unit
async def test_flag_off_skips_the_transport_even_when_redis_is_available(
    start_app: StartApp,
) -> None:
    # Redis is deliberately available: the flag alone must gate emission, not
    # the accident of an unreachable broker.
    run = await start_app(siem_enabled="false", redis=_StubRedis())

    assert run.app.state.security_transport_holder.get() is None
    assert not hasattr(run.app.state, "security_publisher_task")


@pytest.mark.unit
async def test_flag_off_announces_itself_exactly_once(start_app: StartApp) -> None:
    # Exactly once, and only this line: an operator reading startup logs must
    # be able to tell "SIEM is off on purpose" from "SIEM tried and failed".
    run = await start_app(siem_enabled="false", redis=_StubRedis())

    assert run.events.count(DISABLED_BY_FLAG) == 1
    assert PUBLISHER_STARTED not in run.events


@pytest.mark.unit
async def test_flag_off_keeps_redis_itself_alive(start_app: StartApp) -> None:
    # The scope boundary of the toggle: the same Redis instance backs the
    # feedback TraceStore, so switching SIEM off must not take it down
    # (design-brief § 2 «Границы и следствия»).
    redis = _StubRedis()

    run = await start_app(siem_enabled="false", redis=redis)

    assert run.app.state.redis is redis


@pytest.mark.unit
async def test_flag_off_leaves_the_processor_wired_and_dropping_silently(
    start_app: StartApp,
) -> None:
    # The production processor, bound to the holder the app published, still
    # sits in the logging chain: a security event passes through unchanged,
    # nothing blows up and nothing reaches Redis. "Disabled" means inert, not
    # broken — the producers in auth.py / guard.py keep logging as they always
    # did and never learn that the subsystem is off.
    redis = _StubRedis()
    run = await start_app(siem_enabled="false", redis=redis)
    assert run.processor is not None

    event_dict = _security_event()
    returned = run.processor(None, "warning", dict(event_dict))
    await asyncio.sleep(0)

    assert returned == event_dict
    assert redis.streamed == []


# --- flag on ----------------------------------------------------------------


@pytest.mark.unit
async def test_flag_on_with_redis_starts_the_publisher(start_app: StartApp) -> None:
    run = await start_app(siem_enabled="true", redis=_StubRedis())

    assert run.app.state.security_transport_holder.get() is not None
    assert run.app.state.security_publisher_task is not None
    assert run.events.count(PUBLISHER_STARTED) == 1
    assert DISABLED_BY_FLAG not in run.events


@pytest.mark.unit
async def test_flag_on_carries_a_security_event_into_the_redis_stream(
    start_app: StartApp,
) -> None:
    # The positive twin of the "drops silently" case above: the same processor
    # and the same log record now travel holder → transport → publisher loop →
    # Redis. Without this end of the contrast, a transport created but never
    # wired into the holder (or a loop that is never started) would keep every
    # other assertion in this file green.
    redis = _StubRedis()
    run = await start_app(siem_enabled="true", redis=redis)
    assert run.processor is not None

    run.processor(None, "warning", _security_event())

    await asyncio.wait_for(redis.arrival.wait(), timeout=5)
    assert [entry["stream"] for entry in redis.streamed] == ["security.events"]
    assert redis.streamed[0]["fields"]["event_type"] == AUTH_LOGIN_FAILED


@pytest.mark.unit
async def test_flag_on_without_redis_stays_silent_about_the_flag(
    start_app: StartApp,
) -> None:
    # The branch that must stay distinguishable: no broker, no transport — but
    # also no "disabled by flag" line, because nobody disabled anything. The
    # warning about Redis itself belongs to ``app.infra.redis.create_redis``,
    # which is stubbed out here and unchanged by this iteration.
    run = await start_app(siem_enabled="true", redis=None)

    assert run.app.state.security_transport_holder.get() is None
    assert not hasattr(run.app.state, "security_publisher_task")
    assert DISABLED_BY_FLAG not in run.events
    assert PUBLISHER_STARTED not in run.events


# --- invariant across modes -------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("siem_enabled", ["true", "false"])
async def test_the_holder_is_published_on_app_state_in_both_modes(
    start_app: StartApp, siem_enabled: str
) -> None:
    # The holder is created before the flag is read and handed to the logging
    # chain unconditionally; only its content depends on the toggle.
    run = await start_app(siem_enabled=siem_enabled, redis=_StubRedis())

    assert isinstance(run.app.state.security_transport_holder, EventTransportHolder)
    assert run.processor is not None
