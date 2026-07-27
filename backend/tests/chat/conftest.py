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
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

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
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from learnflow_testing.factories import bind_session
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import ObjectDeletedError

# Repo root -> configs/, so tests can build the *real* PromptProvider (file
# fallback, no Langfuse) and prompt fragments the title generator uses.
_CONFIGS_DIR = Path(__file__).resolve().parents[3] / "configs"

# ---------------------------------------------------------------------------
# Production wire vocabulary
# ---------------------------------------------------------------------------
#
# The real ``AgentRunner`` (``app.agent.runner`` + ``StreamEventMapper``) only
# ever emits the event types below; ``ChatService`` forwards them verbatim and
# the frontend (``pages/chat/model/useAgentStream.ts``) switches on exactly this
# set plus the service-synthesised ones (``done``, ``title_updated`` — see
# SERVICE_SYNTHESISED_TYPES below). Tests MUST program the fake with
# these builders rather than ad-hoc dicts, otherwise a green test can pin a type
# that prod never produces (the M1 finding: the fake used ``type="token"`` while
# prod emits ``text_chunk``). Payload shapes mirror prod exactly:
#   text_chunk        -> {"content": str}        (runner.py:218)
#   error             -> {"detail": str}         (runner.py:234, streaming.md:29)
#   security_block    -> {"reason": str}         (runner.py:128/210/264/281)
#   trace_id          -> {"trace_id": str}       (consumed by ChatService)
#   artifact_created  -> {"id": str, ...}        (stream_events.py:48)
#
# ``security_block`` carries ``reason`` (a detection-layer name or the
# ``"prompt_injection"`` fallback from ``RuntimeSecurityEnforcer.block_reason``),
# NOT ``{checkpoint, detection_layer}``. streaming.md still documents the latter
# — a doc/prod drift flagged for the architect (the frontend reads no field off
# ``security_block`` at all, so the wire payload is whatever prod sends).

# The wire types the runner produces and ChatService forwards verbatim
# (trace_id is emitted by the runner but consumed internally and never
# forwarded).
RUNNER_FORWARDED_TYPES = frozenset(
    {
        "text_chunk",
        "tool_start",
        "tool_end",
        "artifact_created",
        "final_output_review_started",
        "final_output_review_complete",
        "security_block",
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


def text_chunk_event(content: str) -> StreamEvent:
    return StreamEvent(type="text_chunk", data={"content": content})


def error_event(detail: str = "Stream failed") -> StreamEvent:
    return StreamEvent(type="error", data={"detail": detail})


def security_block_event(reason: str = "llm_classifier") -> StreamEvent:
    return StreamEvent(type="security_block", data={"reason": reason})


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


class FakeTitleModel(GenericFakeChatModel):
    """Fake title LLM that records its prompts and can fail on demand.

    Recording the messages is what lets a test assert *what reached the model*:
    the user text must arrive wrapped as data (prompt-injection framing), and on
    the guard paths (deleted / blocked / already-renamed chat) nothing must reach
    it at all. ``failure`` models an outage or timeout of the title model.

    ``on_call`` fires while the call is "in flight" — the window in which the
    chat can be deleted, blocked or renamed by someone else. It is the seam for
    the mid-call race the decisive pre-write guard exists for.
    """

    recorded: list[list[BaseMessage]] = []
    failure: Exception | None = None
    on_call: Callable[[], None] | None = None

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


# Columns the fake session copies between its snapshot and the shared store;
# ``thread_id`` is the key and is set when the snapshot is built.
_THREAD_VIEW_STATE = ("project_id", "title", "security_blocked")


def _copy_thread_view_state(source: ThreadView, target: ThreadView) -> None:
    for name in _THREAD_VIEW_STATE:
        setattr(target, name, getattr(source, name))


@dataclass
class FakeAsyncSession:
    """Async-session stand-in backed by an in-memory ``ThreadView`` store.

    The title task builds a *real* ``ThreadViewRepository`` over whatever the
    session factory hands it, so the fake implements exactly the operations that
    repository uses (``get`` / ``flush`` / ``refresh``) plus ``commit`` and the
    async-context protocol callers of ``async_sessionmaker`` rely on.

    Sessions are isolated from the store the way a real one is isolated from the
    database, and that isolation is the point: ``get`` hands out a per-session
    *snapshot* of the row, ``flush`` writes the snapshot's values back to the
    store, and ``refresh`` re-reads the store into the snapshot — raising
    ``ObjectDeletedError`` when the row is gone, exactly as SQLAlchemy does.
    Without it a "re-read before the write" would be indistinguishable from the
    read the task already did, and a chat blocked, renamed or deleted *during*
    the LLM call would be unobservable (fixer handoff on finding R3).
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

    async def flush(self) -> None:
        for pk, snapshot in self.snapshots.items():
            stored = self.threads.get(pk)
            if stored is None:
                continue  # row deleted meanwhile: the UPDATE matches nothing
            _copy_thread_view_state(snapshot, stored)

    async def refresh(self, instance: object) -> None:
        snapshot = cast(ThreadView, instance)
        stored = self.threads.get(snapshot.thread_id)
        if stored is None:
            raise ObjectDeletedError(inspect(snapshot))
        _copy_thread_view_state(stored, snapshot)

    async def commit(self) -> None:
        await self.flush()
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
