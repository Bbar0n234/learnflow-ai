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

import asyncio
import operator
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from app.agent.config import TitleConfig, load_prompt_fragments
from app.api.deps import get_chat_service
from app.config import Settings
from app.infra.prompt_provider import PromptProvider
from app.models.thread_view import ThreadView
from app.repositories.artifact import ArtifactRepository
from app.repositories.thread_view import ThreadViewRepository
from app.services import chat_title as chat_title_module
from app.services.agent_runner import Message, StreamEvent
from app.services.chat import ChatService
from app.services.chat_title import ChatTitleGenerator
from app.services.constants import DEFAULT_CHAT_TITLE
from async_factory_boy.factory.sqlalchemy import AsyncSQLAlchemyFactory
from fastapi import FastAPI
from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from learnflow_testing.factories import bind_session
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import operators as sa_operators
from sqlalchemy.sql.dml import Update
from sqlalchemy.sql.elements import (
    BinaryExpression,
    BindParameter,
    BooleanClauseList,
    ColumnClause,
    ColumnElement,
    False_,
    Null,
    True_,
)
from sqlalchemy.sql.expression import Executable, TableClause

# Repo root -> configs/, so tests can build the *real* PromptProvider (file
# fallback, no Langfuse) and prompt fragments the title generator uses.
_CONFIGS_DIR = Path(__file__).resolve().parents[3] / "configs"

# ---------------------------------------------------------------------------
# Production wire vocabulary
# ---------------------------------------------------------------------------
#
# The real ``AgentRunner`` (``app.agent.runner`` + ``app.agent.heartbeat`` +
# ``StreamEventMapper``/``TokenChunkMapper``) only ever emits the event types
# below; ``ChatService`` forwards them verbatim and the frontend
# (``pages/chat/model/useAgentStream.ts``) switches on exactly this set plus the
# service-synthesised ones (``done``, ``title_updated`` — see
# SERVICE_SYNTHESISED_TYPES below). Tests MUST program the fake with these
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

# The wire types the runner produces and ChatService forwards verbatim
# (trace_id is emitted by the runner but consumed internally and never
# forwarded).
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

# The wire types ChatService puts on the stream *itself* — no runner event
# carries them: the terminal ``done`` it synthesises after the post-hoc step,
# and the non-terminal ``title_updated`` it slips in when the auto-title task
# has finished (services/chat.py). Together with RUNNER_FORWARDED_TYPES this is
# the full union the frontend's SSEEvent must know; the AST guards in
# test_chat_service.py pin both sides.
SERVICE_SYNTHESISED_TYPES = frozenset({"done", "title_updated"})


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
        self.deleted_threads: list[uuid.UUID] = []
        # Models a checkpointer outage during chat deletion: the DB-side delete
        # is already committed, the checkpoint cleanup is best-effort only.
        self.raise_on_delete_thread: bool = False
        # Called with the index of an event right before it is handed to the
        # consumer. The seam a test uses to land an *external* completion — the
        # auto-title task finishing — in one exact window of ChatService's relay
        # loop: firing it at index N puts the completion after the poll that
        # followed event N-1 and before event N is yielded.
        self.on_event: Callable[[int], None] | None = None

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
                if self.on_event is not None:
                    self.on_event(index)
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

    async def delete_thread(self, *, thread_id: uuid.UUID) -> None:
        self.deleted_threads.append(thread_id)
        if self.raise_on_delete_thread:
            raise RuntimeError("checkpointer unavailable")


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

    async def update(self, thread_view: ThreadView, *, title: str) -> ThreadView:
        thread_view.title = title
        return thread_view

    async def delete(self, thread_view: ThreadView) -> None:
        self.threads.pop(thread_view.thread_id, None)


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
# Auto-title fakes (design-brief § Auto-title модуль)
# ---------------------------------------------------------------------------


@dataclass
class ModelCallGate:
    """Parks the fake title model inside its call until the test lets it out.

    The seam for anything that happens *while a generation is running* and has
    to be observed at a known point: shutdown cancelling a task that sits in
    ``ainvoke``. ``on_call`` covers the same window for changes to the chat, but
    it returns immediately — this one keeps the call open across await points.
    """

    entered: asyncio.Event = field(default_factory=asyncio.Event)
    released: asyncio.Event = field(default_factory=asyncio.Event)

    async def wait_until_in_the_call(self) -> None:
        await self.entered.wait()

    def release(self) -> None:
        self.released.set()


class FakeTitleModel(GenericFakeChatModel):
    """Fake title LLM that records its prompts and can fail on demand.

    Recording the messages is what lets a test assert *what reached the model*:
    the user text must arrive wrapped as data (prompt-injection framing), and on
    the guard paths (deleted / blocked / already-renamed chat) nothing must reach
    it at all. ``failure`` models an outage or timeout of the title model.

    ``on_call`` fires while the call is "in flight" — the window in which the
    chat can be deleted, blocked or renamed by someone else. It is the seam for
    the mid-call race the conditional title write exists for. ``gate`` holds the
    call open instead of just interleaving with it.

    ``_agenerate`` is overridden so the call runs on the test's own event loop:
    the inherited default hands ``_generate`` to a thread executor, where a
    ``gate`` could not be awaited and a cancellation could not land.
    """

    recorded: list[list[BaseMessage]] = []
    failure: Exception | None = None
    on_call: Callable[[], None] | None = None
    gate: ModelCallGate | None = None

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.recorded.append(list(messages))
        if self.on_call is not None:
            self.on_call()
        if self.failure is not None:
            raise self.failure
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        if self.gate is not None:
            self.gate.entered.set()
            await self.gate.released.wait()
        return self._generate(messages, stop=stop, **kwargs)


# Columns the fake session copies from the store into a session snapshot;
# ``thread_id`` is the key and is set when the snapshot is built.
_THREAD_VIEW_STATE = ("project_id", "title", "security_blocked")


def _copy_thread_view_state(source: ThreadView, target: ThreadView) -> None:
    for name in _THREAD_VIEW_STATE:
        setattr(target, name, getattr(source, name))


# How the fake evaluates a WHERE criterion. ``eq``/``ne`` come from Python's
# ``==``/``!=`` on a column, ``is_``/``is_not`` from ``Column.is_(...)`` — the
# form ``ThreadView.security_blocked.is_(False)`` compiles to. Anything else is
# a comparison the fake would have to guess at, so it raises instead (see
# ``_criterion_holds``): a predicate the fake silently mis-evaluates is worse
# than one it refuses to run.
_COMPARISONS: dict[Any, Callable[[Any, Any], bool]] = {
    operator.eq: lambda stored, wanted: bool(stored == wanted),
    operator.ne: lambda stored, wanted: bool(stored != wanted),
    sa_operators.is_: lambda stored, wanted: stored is wanted,
    sa_operators.is_not: lambda stored, wanted: stored is not wanted,
}


def _column_key(column: object) -> str:
    """The model attribute a statement's column stands for."""
    if isinstance(column, str):
        return column
    if isinstance(column, ColumnClause) and isinstance(column.key, str):
        return column.key
    raise NotImplementedError(f"fake session cannot address column {column!r}")


def _literal(clause: object) -> Any:
    """The Python value a right-hand side of a criterion compares against."""
    if isinstance(clause, BindParameter):
        return clause.value
    if isinstance(clause, False_):
        return False
    if isinstance(clause, True_):
        return True
    if isinstance(clause, Null):
        return None
    raise NotImplementedError(f"fake session cannot read literal {clause!r}")


def _criterion_holds(criterion: ColumnElement[Any], row: ThreadView) -> bool:
    """Evaluate one ``column <op> literal`` criterion against a stored row."""
    if not isinstance(criterion, BinaryExpression):
        raise NotImplementedError(f"fake session cannot evaluate {criterion!r}")
    compare = _COMPARISONS.get(criterion.operator)
    if compare is None:
        raise NotImplementedError(
            f"fake session cannot evaluate operator {criterion.operator!r}"
        )
    stored = getattr(row, _column_key(criterion.left))
    return compare(stored, _literal(criterion.right))


def _where_holds(whereclause: ColumnElement[Any] | None, row: ThreadView) -> bool:
    if whereclause is None:
        return True
    if isinstance(whereclause, BooleanClauseList):
        if whereclause.operator is not sa_operators.and_:
            raise NotImplementedError(f"fake session cannot evaluate {whereclause!r}")
        return all(_criterion_holds(clause, row) for clause in whereclause.clauses)
    return _criterion_holds(whereclause, row)


@dataclass
class FakeResult:
    """What ``FakeAsyncSession.execute`` hands back — the RETURNING rows."""

    rows: list[tuple[Any, ...]]

    def scalar_one_or_none(self) -> Any:
        if not self.rows:
            return None
        if len(self.rows) > 1:
            raise MultipleResultsFound(f"{len(self.rows)} rows returned")
        return self.rows[0][0]


@dataclass
class FakeAsyncSession:
    """Async-session stand-in backed by an in-memory ``ThreadView`` store.

    The title task builds a *real* ``ThreadViewRepository`` over whatever the
    session factory hands it, so the fake implements exactly the operations that
    repository uses — ``get`` and ``execute`` — plus ``flush`` / ``commit`` and
    the async-context protocol callers of ``async_sessionmaker`` rely on.

    Two things make it a fake with teeth rather than a dictionary:

    * ``threads`` is *the database*: committed state, shared by every session
      the factory hands out. ``get`` returns a per-session **snapshot** taken
      once and never re-read, which is what a session's row really is — an
      in-flight change made elsewhere (worse: made and not yet committed, as a
      mid-stream ``security_blocked`` is) is invisible in it. So a title write
      decided from the snapshot cannot pass the mid-call tests; only one
      decided at write time can.
    * ``execute`` genuinely *interprets* the conditional UPDATE — it evaluates
      the statement's WHERE against the store and reports the RETURNING rows.
      Weaken the predicate in production and the fake writes the row, which is
      exactly when the mid-call tests must go red.

    There is deliberately no ``refresh``: re-reading the row before the write is
    the approach that could not work (an uncommitted change from another session
    stays invisible under READ COMMITTED), so an implementation that tries it
    fails here loudly instead of finding a fake that pretends it works.
    """

    threads: dict[uuid.UUID, ThreadView]
    commits: int = 0
    snapshots: dict[uuid.UUID, ThreadView] = field(default_factory=dict)

    async def __aenter__(self) -> FakeAsyncSession:
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False

    async def get(self, entity: type[ThreadView], pk: uuid.UUID) -> ThreadView | None:
        if pk in self.snapshots:
            return self.snapshots[pk]  # identity map: same object within a session
        stored = self.threads.get(pk)
        if stored is None:
            return None
        snapshot = ThreadView(thread_id=stored.thread_id)
        _copy_thread_view_state(stored, snapshot)
        self.snapshots[pk] = snapshot
        return snapshot

    async def execute(self, statement: Executable) -> FakeResult:
        """Run a conditional UPDATE against the store, honouring its WHERE.

        Only ``UPDATE thread_views`` is supported; anything else raises, so a
        production statement the fake does not model surfaces as a failure
        rather than as a quietly wrong result. ``_values`` / ``_returning`` are
        SQLAlchemy internals — there is no public accessor for the SET clause of
        a Core statement, and this fake is pinned to the project's SQLAlchemy.
        """
        if not isinstance(statement, Update):
            raise NotImplementedError(f"fake session cannot run {statement!r}")
        table = statement.table
        if not isinstance(table, TableClause) or table.name != ThreadView.__tablename__:
            raise NotImplementedError(f"fake session cannot run {statement!r}")

        assignments = {
            _column_key(column): _literal(value)
            for column, value in (statement._values or {}).items()
        }
        matched = [
            row
            for row in self.threads.values()
            if _where_holds(statement.whereclause, row)
        ]
        for row in matched:
            for name, value in assignments.items():
                setattr(row, name, value)
        returning = [_column_key(column) for column in statement._returning]
        return FakeResult(
            [tuple(getattr(row, key) for key in returning) for row in matched]
        )

    async def flush(self) -> None:
        """No-op: ``execute`` already wrote through to the store.

        Nothing in the title path mutates the snapshot, so there is no pending
        ORM state to push — an implementation that writes by assigning to the
        snapshot leaves the store untouched and fails on the stored title.
        """

    async def commit(self) -> None:
        self.commits += 1


@dataclass
class FakeSessionFactory:
    """``async_sessionmaker`` stand-in: each call opens a fresh fake session.

    All sessions share one ``threads`` map, so a test observes what the task
    wrote through its *own* session — the point of the fire-and-forget design.
    """

    threads: dict[uuid.UUID, ThreadView] = field(default_factory=dict)
    sessions: list[FakeAsyncSession] = field(default_factory=list)

    def __call__(self) -> FakeAsyncSession:
        session = FakeAsyncSession(threads=self.threads)
        self.sessions.append(session)
        return session

    def add(self, thread: ThreadView) -> ThreadView:
        self.threads[thread.thread_id] = thread
        return thread


@dataclass
class FakeTitleGenerator:
    """``ChatTitleGenerator`` stand-in for ``ChatService`` relay tests.

    ``mode`` programs the handle the relay gets back:

    * ``ready`` — generation already finished, handle carries ``title``;
    * ``pending`` — generation still running (handle never resolves);
    * ``deferred`` — generation still running when the handle is handed back,
      and the test completes it later via ``resolve()``. Paired with
      ``FakeAgentRunner.on_event`` this pins *when* the title became ready
      relative to the agent's events — the only way to express "the generation
      finished in the window right before a terminal event";
    * ``in_flight`` — a generation for this chat is already running, so the
      real generator returns ``None`` instead of a new handle.

    The handle is a plain ``asyncio.Future``: the relay only ever calls
    ``done()`` / ``result()`` on it, and a Future is resolvable synchronously,
    which keeps "title is ready at this exact point of the stream"
    deterministic (a real Task would need loop turns to complete).
    """

    title: str | None = "Квадратные уравнения"
    mode: str = "ready"
    calls: list[tuple[uuid.UUID, str]] = field(default_factory=list)
    handles: list[asyncio.Future[str | None]] = field(default_factory=list)

    def generate_title(
        self, thread_id: uuid.UUID, content: str
    ) -> asyncio.Future[str | None] | None:
        self.calls.append((thread_id, content))
        if self.mode == "in_flight":
            return None
        handle: asyncio.Future[str | None] = asyncio.get_running_loop().create_future()
        if self.mode == "ready":
            handle.set_result(self.title)
        self.handles.append(handle)
        return handle

    def resolve(self) -> None:
        """Complete every handle still in flight — "the LLM answered *now*"."""
        for handle in self.handles:
            if not handle.done():
                handle.set_result(self.title)

    def cancel(self) -> None:
        """Cancel every handle still in flight — "shutdown got there first".

        The real generator cancels its whole registry on application shutdown,
        which lands on a handle a running stream is still holding: the handle is
        ``done()`` but carries a ``CancelledError`` instead of a title.
        """
        for handle in self.handles:
            if not handle.done():
                handle.cancel()


class ThreadViewFactory(AsyncSQLAlchemyFactory):
    """Persisted ``ThreadView`` rows for chat-scope integration tests.

    Deliberately a scope-local copy rather than a promotion into
    ``packages/testing`` (design-brief § Партиция треков, scope constraint б).
    Bind it with the ``thread_factory`` fixture, which points it at the test's
    transactional session, and pass the owning ``project=`` explicitly — chat
    ownership always runs through a project the test already created.
    """

    class Meta:
        model = ThreadView
        sqlalchemy_session_persistence = "flush"

    title = DEFAULT_CHAT_TITLE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def thread_factory(db_session: AsyncSession) -> type[ThreadViewFactory]:
    """``ThreadViewFactory`` bound to the test's transactional session."""
    bind_session(db_session, ThreadViewFactory)
    return ThreadViewFactory


TitleGeneratorBuilder = Callable[
    ["FakeTitleModel", "FakeSessionFactory"], "ChatTitleGenerator"
]


@pytest.fixture
def build_title_generator(
    monkeypatch: pytest.MonkeyPatch,
) -> TitleGeneratorBuilder:
    """Build a real ``ChatTitleGenerator`` wired to a fake model and sessions.

    ``ChatTitleGenerator`` builds its model inline through the
    ``create_title_llm`` factory, so the test seam is that factory (conventions/
    testing.md § Фейки LLM: "инъектируемая model-factory, которую переопределяют
    тесты"). Everything else stays real — the prompt provider reads the actual
    ``configs/prompts/title.txt`` and the actual wrapper fragments, so the
    prompt wiring is under test rather than stubbed away.
    """

    def _build(
        model: FakeTitleModel, session_factory: FakeSessionFactory
    ) -> ChatTitleGenerator:
        monkeypatch.setattr(
            chat_title_module,
            "create_title_llm",
            lambda settings, config: model,
        )
        return ChatTitleGenerator(
            session_factory=session_factory,  # type: ignore[arg-type]
            settings=Settings(),
            title_config=TitleConfig(model="fake/title-model"),
            prompt_provider=PromptProvider(
                langfuse=None,
                label="development",
                cache_ttl=0,
                prompts_dir=_CONFIGS_DIR / "prompts",
            ),
            prompt_fragments=load_prompt_fragments(),
        )

    return _build


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


@dataclass
class TitleWiring:
    """Handles for the auto-title HTTP wiring: program both, assert on both."""

    runner: FakeAgentRunner
    title_generator: FakeTitleGenerator


@pytest.fixture
def wired_title_runner(
    app: FastAPI, db_session: AsyncSession, fake_runner: FakeAgentRunner
) -> TitleWiring:
    """Like ``wired_runner``, but the service also gets a fake title generator.

    In production the generator is built in the lifespan and read off
    ``app.state`` by ``get_chat_service``; ``ASGITransport`` runs no lifespan, so
    the scope-local override is the only way to exercise the title path through
    the real route (design-brief § Партиция треков, scope constraint в).
    """
    title_generator = FakeTitleGenerator()

    def _override() -> ChatService:
        return ChatService(
            thread_view_repo=ThreadViewRepository(db_session),
            agent_runner=fake_runner,
            artifact_repo=ArtifactRepository(db_session),
            trace_store=None,
            session=db_session,
            title_generator=title_generator,  # type: ignore[arg-type]
        )

    app.dependency_overrides[get_chat_service] = _override
    return TitleWiring(runner=fake_runner, title_generator=title_generator)
