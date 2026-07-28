"""Local fixtures for the S5 chat & streaming scope.

Two test styles live here:

* **Service sociable-unit** — drive ``ChatService`` directly with in-memory fake
  collaborators (runner, repos, trace store). Fast, deterministic, exercises the
  orchestration branches (trace-id filtering, artifact linking, error-vs-done,
  graceful degradation) without DB or network.
* **HTTP / SSE integration** — go through the authenticated ASGI ``client`` with
  *real* repositories on the transactional ``db_session``, replacing only the
  agent runner (the LangGraph seam, out of this scope) via a ``get_chat_service``
  override. ``app.state.agent_runner`` is never populated under ``ASGITransport``
  (no lifespan), so the override is mandatory for any route that builds a
  ``ChatService``.

Nothing here touches the frozen harness (``packages/testing`` or the parent
``conftest``); these are additive, scope-local fixtures.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import pytest
from app.api.deps import get_chat_service
from app.models.thread_view import ThreadView
from app.repositories.artifact import ArtifactRepository
from app.repositories.thread_view import ThreadViewRepository
from app.services.agent_runner import Message, StreamEvent
from app.services.chat import ChatService
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Production wire vocabulary
# ---------------------------------------------------------------------------
#
# The real ``AgentRunner`` (``app.agent.runner`` + ``app.agent.heartbeat`` +
# ``StreamEventMapper``/``TokenChunkMapper``) only ever emits the event types
# below; ``ChatService`` forwards them verbatim and the frontend
# (``pages/chat/model/useAgentStream.ts``) switches on exactly this set (plus
# the service-synthesised ``done``). Tests MUST program the fake with these
# builders rather than ad-hoc dicts, otherwise a green test can pin a type that
# prod never produces (the M1 finding: the fake used ``type="token"`` while
# prod emits ``text_chunk``). Payload shapes mirror prod exactly:
#   stream_started      -> {}                      (runner.py)
#   heartbeat           -> {}                       (heartbeat.py)
#   text_chunk          -> {"content": str}        (runner.py, stream_events.py)
#   reasoning_chunk     -> {"content": str}        (stream_events.py — token
#                           channel, ``additional_kwargs["reasoning"]``)
#   tool_call_started   -> {"call_id": str, "tool": str} (stream_events.py —
#                           token channel, first ``tool_call_chunk`` of a call)
#   tool_call_args      -> {"call_id": str, "args": str, "truncated": bool}
#                           (stream_events.py — token channel, args JSON
#                           complete, before execution)
#   tool_call_cancelled -> {"call_id": str}         (stream_events.py — updates
#                           channel, guard cut a turn's tool calls after
#                           generation, before execution)
#   tool_result         -> {"call_id": str, "tool": str, "status": str,
#                           "content": str, "truncated": bool} (stream_events.py
#                           — updates channel, ``ToolMessage`` after execution)
#   agent_event         -> {"kind": str, "payload": dict, "parent_call_id"?: str}
#                           (runner.py — custom channel, our own tools'
#                           ``agent_events.emit_agent_event`` domain writes:
#                           sphere_write / memory_write / skill_context_write /
#                           compaction)
#   cancelled           -> {}                       (runner.py)
#   error               -> {"detail": str}         (runner.py, streaming.md)
#   security_block      -> {}                       (runner.py — generic, no
#                           reason/checkpoint/detection_layer: design-brief §
#                           "Контракт SSE v2")
#   trace_id            -> {"trace_id": str}       (consumed by ChatService)
#   artifact_created    -> {"id": str, ...}        (stream_events.py)

# The wire types ChatService forwards to the frontend (trace_id is consumed
# internally and never forwarded; done is synthesised by the service).
RUNNER_FORWARDED_TYPES = frozenset(
    {
        "stream_started",
        "heartbeat",
        "text_chunk",
        "reasoning_chunk",
        "tool_call_started",
        "tool_call_args",
        "tool_call_cancelled",
        "tool_result",
        "agent_event",
        "artifact_created",
        "final_output_review_started",
        "final_output_review_complete",
        "security_block",
        "cancelled",
        "error",
    }
)


def stream_started_event() -> StreamEvent:
    return StreamEvent(type="stream_started", data={})


def heartbeat_event() -> StreamEvent:
    return StreamEvent(type="heartbeat", data={})


def text_chunk_event(content: str) -> StreamEvent:
    return StreamEvent(type="text_chunk", data={"content": content})


def reasoning_chunk_event(content: str) -> StreamEvent:
    return StreamEvent(type="reasoning_chunk", data={"content": content})


def tool_call_started_event(call_id: str, tool: str) -> StreamEvent:
    return StreamEvent(
        type="tool_call_started", data={"call_id": call_id, "tool": tool}
    )


def tool_call_args_event(
    call_id: str, args: str, *, truncated: bool = False
) -> StreamEvent:
    return StreamEvent(
        type="tool_call_args",
        data={"call_id": call_id, "args": args, "truncated": truncated},
    )


def tool_call_cancelled_event(call_id: str) -> StreamEvent:
    return StreamEvent(type="tool_call_cancelled", data={"call_id": call_id})


def tool_result_event(
    call_id: str,
    tool: str,
    *,
    status: str = "success",
    content: str = "",
    truncated: bool = False,
) -> StreamEvent:
    return StreamEvent(
        type="tool_result",
        data={
            "call_id": call_id,
            "tool": tool,
            "status": status,
            "content": content,
            "truncated": truncated,
        },
    )


def agent_event_event(
    kind: str, payload: dict[str, object], *, parent_call_id: str | None = None
) -> StreamEvent:
    data: dict[str, object] = {"kind": kind, "payload": payload}
    if parent_call_id is not None:
        data["parent_call_id"] = parent_call_id
    return StreamEvent(type="agent_event", data=data)


def error_event(detail: str = "Stream failed") -> StreamEvent:
    return StreamEvent(type="error", data={"detail": detail})


def security_block_event() -> StreamEvent:
    return StreamEvent(type="security_block", data={})


def cancelled_event() -> StreamEvent:
    return StreamEvent(type="cancelled", data={})


def trace_id_event(trace_id: str) -> StreamEvent:
    return StreamEvent(type="trace_id", data={"trace_id": trace_id})


def artifact_created_event(artifact_id: uuid.UUID) -> StreamEvent:
    return StreamEvent(type="artifact_created", data={"id": str(artifact_id)})


# ---------------------------------------------------------------------------
# Fakes for service sociable-unit tests
# ---------------------------------------------------------------------------


class FakeAgentRunner:
    """In-memory ``AgentRunner`` replaying a programmed event sequence.

    Records the args ``stream`` was called with, optionally raises mid-stream
    (``raise_after`` = index after which to raise, modelling an in-graph crash
    that the API generator must turn into a terminal error event).
    """

    def __init__(self) -> None:
        self.events: list[StreamEvent] = []
        self.history: list[Message] = []
        self.last_ai_message_id: str | None = None
        self.cancel_result: bool = True
        self.raise_after: int | None = None
        self.raise_on_last_id: bool = False
        self.stream_calls: list[tuple[uuid.UUID, str, uuid.UUID, uuid.UUID]] = []

    def stream(
        self,
        *,
        thread_id: uuid.UUID,
        content: str,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        session: AsyncSession | None = None,
        model_config: object | None = None,
    ) -> AsyncIterator[StreamEvent]:
        self.stream_calls.append((thread_id, content, project_id, user_id))

        async def _gen() -> AsyncIterator[StreamEvent]:
            for index, event in enumerate(self.events):
                if self.raise_after is not None and index == self.raise_after:
                    raise RuntimeError("simulated in-stream failure")
                yield event
            if self.raise_after is not None and self.raise_after >= len(self.events):
                raise RuntimeError("simulated in-stream failure")

        return _gen()

    async def get_history(self, *, thread_id: uuid.UUID) -> list[Message]:
        return self.history

    async def get_last_ai_message_id(self, *, thread_id: uuid.UUID) -> str | None:
        if self.raise_on_last_id:
            raise RuntimeError("simulated post-hoc failure")
        return self.last_ai_message_id

    async def cancel(self, *, thread_id: uuid.UUID) -> bool:
        return self.cancel_result


@dataclass
class FakeThreadViewRepo:
    """In-memory ``ThreadViewRepository`` for service-unit tests."""

    threads: dict[uuid.UUID, ThreadView] = field(default_factory=dict)
    touched: list[uuid.UUID] = field(default_factory=list)
    recent: list[ThreadView] = field(default_factory=list)

    def add(self, thread: ThreadView) -> ThreadView:
        self.threads[thread.thread_id] = thread
        return thread

    async def create(self, *, project_id: uuid.UUID, title: str) -> ThreadView:
        thread = ThreadView(thread_id=uuid.uuid4(), project_id=project_id, title=title)
        return self.add(thread)

    async def get_by_id(self, thread_id: uuid.UUID) -> ThreadView | None:
        return self.threads.get(thread_id)

    async def list_by_project(
        self, project_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> list[ThreadView]:
        rows = [t for t in self.threads.values() if t.project_id == project_id]
        return rows[offset : offset + limit]

    async def count_by_project(self, project_id: uuid.UUID) -> int:
        return len([t for t in self.threads.values() if t.project_id == project_id])

    async def list_recent(
        self, user_id: uuid.UUID, *, limit: int = 10, offset: int = 0
    ) -> list[ThreadView]:
        return self.recent[offset : offset + limit]

    async def count_by_user(self, user_id: uuid.UUID) -> int:
        return len(self.recent)

    async def touch(self, thread_view: ThreadView) -> None:
        self.touched.append(thread_view.thread_id)


@dataclass
class FakeArtifactRepo:
    """In-memory artifact repo holding the message_id linkage as state.

    ``set_message_id`` mutates ``linked`` (artifact_id -> message_id) so tests
    assert the *effect* — which artifacts ended up bound to which message — not
    merely that the method was called. ``set_message_id_calls`` is kept for tests
    that need to observe call multiplicity/ordering.
    """

    linked: dict[uuid.UUID, str] = field(default_factory=dict)
    set_message_id_calls: list[tuple[list[uuid.UUID], str]] = field(
        default_factory=list
    )

    async def set_message_id(
        self, artifact_ids: list[uuid.UUID], message_id: str
    ) -> None:
        self.set_message_id_calls.append((artifact_ids, message_id))
        for artifact_id in artifact_ids:
            self.linked[artifact_id] = message_id

    async def list_by_thread(self, thread_id: uuid.UUID) -> list[object]:
        return []


@dataclass
class FakeTraceStore:
    """In-memory trace store; flags let a read/write raise to test degradation."""

    by_thread: dict[uuid.UUID, dict[str, str]] = field(default_factory=dict)
    feedback: dict[str, bool] = field(default_factory=dict)
    saved: list[tuple[uuid.UUID, str, str]] = field(default_factory=list)
    raise_on_get_by_thread: bool = False
    raise_on_feedback_batch: bool = False

    async def get_by_thread(self, thread_id: uuid.UUID) -> dict[str, str]:
        if self.raise_on_get_by_thread:
            raise RuntimeError("redis down")
        return self.by_thread.get(thread_id, {})

    async def get_feedback_batch(self, trace_ids: list[str]) -> dict[str, bool]:
        if self.raise_on_feedback_batch:
            raise RuntimeError("redis down")
        return {tid: self.feedback[tid] for tid in trace_ids if tid in self.feedback}

    async def save(self, thread_id: uuid.UUID, message_id: str, trace_id: str) -> None:
        self.saved.append((thread_id, message_id, trace_id))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_runner() -> FakeAgentRunner:
    """A programmable agent runner shared by service- and HTTP-level tests."""
    return FakeAgentRunner()


@pytest.fixture
def wired_runner(
    app: FastAPI, db_session: AsyncSession, fake_runner: FakeAgentRunner
) -> FakeAgentRunner:
    """Override ``get_chat_service`` to use real repos + the fake runner.

    Returned so a test can program ``.events`` / ``.history`` before calling the
    client. Real ``ThreadViewRepository`` / ``ArtifactRepository`` on the shared
    transactional session keep the route's SQL path under test; only the graph
    seam is faked.
    """

    def _override() -> ChatService:
        return ChatService(
            thread_view_repo=ThreadViewRepository(db_session),
            agent_runner=fake_runner,
            artifact_repo=ArtifactRepository(db_session),
            trace_store=None,
            session=db_session,
        )

    app.dependency_overrides[get_chat_service] = _override
    return fake_runner
