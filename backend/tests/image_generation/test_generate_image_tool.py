"""Behavior tests for the ``generate_image`` agent tool (T1.5).

The tool orchestrates: call the OpenRouter helper -> write artifact + blob in one
transaction -> (optional) Langfuse generation-observation -> return a text
ToolMessage plus the artifact dict that drives ``artifact_created``.

The external OpenRouter call (``call_generate_image``, tested on its own in
``test_openrouter_image.py``) is replaced with a fake here; the transaction runs
against real Postgres through ``tool_session_factory`` (see the scope conftest),
so the atomic write is observed end to end. We drive the tool's ``.coroutine``
directly with a constructed ``ToolRuntime`` — the injected ``runtime`` arg is
excluded from the public tool schema, matching the KS/user-memory tool tests.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any, cast

import pytest
from app.agent.config import ImageConfig
from app.agent.graph import AgentContext
from app.agent.tools.image_generation import make_generate_image_tool
from app.infra.image_generation import ImageGenerationResult
from app.models.project import Project
from app.models.thread_view import ThreadView
from app.repositories.artifact import ArtifactRepository
from app.services.exceptions import UpstreamUnavailableError
from app.storage.blob_storage import PgBlobStorage
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import ToolRuntime
from sqlalchemy.ext.asyncio import AsyncSession

from tests.image_generation.conftest import ThreadViewFactory

pytestmark = pytest.mark.integration

_PNG = b"\x89PNG\r\n\x1a\n fake image bytes"


def _coro(tool: object) -> Callable[..., Awaitable[Any]]:
    return cast(Callable[..., Awaitable[Any]], cast(StructuredTool, tool).coroutine)


def _runtime(
    *, project_id: uuid.UUID, thread_id: uuid.UUID, with_context: bool = True
) -> ToolRuntime[AgentContext | None, dict[str, Any]]:
    context = (
        AgentContext(project_id=str(project_id), user_id="user-1")
        if with_context
        else None
    )
    return ToolRuntime(
        state={},
        context=context,
        config={"configurable": {"thread_id": str(thread_id)}},
        stream_writer=lambda _: None,
        tool_call_id="call-1",
        store=None,
    )


def _fake_helper(
    result: ImageGenerationResult | None = None,
    *,
    raises: Exception | None = None,
    calls: list[dict[str, Any]] | None = None,
) -> Callable[..., Awaitable[ImageGenerationResult]]:
    async def _call(
        settings: Any, image_config: Any, **kwargs: Any
    ) -> ImageGenerationResult:
        if calls is not None:
            calls.append(kwargs)
        if raises is not None:
            raise raises
        assert result is not None
        return result

    return _call


async def _seed_project_and_thread(session: AsyncSession) -> tuple[Project, ThreadView]:
    thread: ThreadView = await ThreadViewFactory.create()
    project = thread.project
    return project, thread


async def test_generate_image_writes_artifact_and_blob_atomically(
    seed_session: AsyncSession,
    tool_session_factory: Callable[[], AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, thread = await _seed_project_and_thread(seed_session)
    result = ImageGenerationResult(data=_PNG, media_type="image/png", cost=0.067)
    monkeypatch.setattr(
        "app.agent.tools.image_generation.call_generate_image",
        _fake_helper(result),
    )
    tool = make_generate_image_tool(
        cast(Any, tool_session_factory),
        cast(Any, SimpleNamespace()),
        ImageConfig(model="google/gemini-3.1-flash-image"),
    )

    text, artifact_payload = await _coro(tool)(
        prompt="a wide-angle cover of a neon city at golden hour",
        title="Neon City",
        aspect_ratio="16:9",
        resolution="2K",
        runtime=_runtime(project_id=project.id, thread_id=thread.thread_id),
    )

    # The artifact dict is what the SSE mapper turns into ``artifact_created``.
    assert artifact_payload["type"] == "image"
    assert artifact_payload["title"] == "Neon City"
    artifact_id = uuid.UUID(artifact_payload["id"])

    # Both rows are readable on the same connection -> the single transaction
    # committed the artifact and its blob together.
    artifact = await ArtifactRepository(seed_session).get_by_id(artifact_id)
    assert artifact is not None
    assert artifact.type == "image"
    assert artifact.content == "a wide-angle cover of a neon city at golden hour"
    assert artifact.project_id == project.id
    assert artifact.thread_id == thread.thread_id

    blob = await PgBlobStorage(seed_session).get(artifact_id)
    assert blob is not None
    data, mime_type = blob
    assert data == _PNG
    assert mime_type == "image/png"

    # ToolMessage text confirms title, id, resolution and cost to the agent.
    assert "Neon City" in text
    assert str(artifact_id) in text
    assert "2K" in text
    assert "0.0670" in text


async def test_generate_image_forwards_prompt_and_params_to_helper(
    seed_session: AsyncSession,
    tool_session_factory: Callable[[], AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, thread = await _seed_project_and_thread(seed_session)
    calls: list[dict[str, Any]] = []
    result = ImageGenerationResult(data=_PNG, media_type="image/png", cost=None)
    monkeypatch.setattr(
        "app.agent.tools.image_generation.call_generate_image",
        _fake_helper(result, calls=calls),
    )
    tool = make_generate_image_tool(
        cast(Any, tool_session_factory),
        cast(Any, SimpleNamespace()),
        ImageConfig(model="m"),
    )

    await _coro(tool)(
        prompt="an icon",
        title="Icon",
        aspect_ratio="1:1",
        resolution="512",
        runtime=_runtime(project_id=project.id, thread_id=thread.thread_id),
    )

    # The composition/creative args reach the OpenRouter helper unchanged.
    assert calls == [{"prompt": "an icon", "aspect_ratio": "1:1", "resolution": "512"}]


async def test_generate_image_omits_cost_label_when_cost_unknown(
    seed_session: AsyncSession,
    tool_session_factory: Callable[[], AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, thread = await _seed_project_and_thread(seed_session)
    result = ImageGenerationResult(data=_PNG, media_type="image/png", cost=None)
    monkeypatch.setattr(
        "app.agent.tools.image_generation.call_generate_image",
        _fake_helper(result),
    )
    tool = make_generate_image_tool(
        cast(Any, tool_session_factory),
        cast(Any, SimpleNamespace()),
        ImageConfig(model="m"),
    )

    text, _ = await _coro(tool)(
        prompt="p",
        title="T",
        runtime=_runtime(project_id=project.id, thread_id=thread.thread_id),
    )

    # No provider cost -> a literal "unknown", never a fabricated "$0.0000".
    assert "unknown" in text
    assert "provider default" in text  # resolution omitted by the agent


async def test_generate_image_provider_error_writes_nothing(
    seed_session: AsyncSession,
    tool_session_factory: Callable[[], AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, thread = await _seed_project_and_thread(seed_session)
    monkeypatch.setattr(
        "app.agent.tools.image_generation.call_generate_image",
        _fake_helper(
            raises=UpstreamUnavailableError(
                code="image-generation-failed", status=502, detail="boom"
            )
        ),
    )
    tool = make_generate_image_tool(
        cast(Any, tool_session_factory),
        cast(Any, SimpleNamespace()),
        ImageConfig(model="m"),
    )

    with pytest.raises(UpstreamUnavailableError):
        await _coro(tool)(
            prompt="p",
            title="T",
            runtime=_runtime(project_id=project.id, thread_id=thread.thread_id),
        )

    # Atomicity: the helper raised before the transaction opened, so no artifact
    # (and thus no blob) exists for this project.
    artifacts = await ArtifactRepository(seed_session).list_by_project(project.id)
    assert artifacts == []


async def test_generate_image_blob_write_failure_rolls_back_artifact(
    seed_session: AsyncSession,
    tool_session_factory: Callable[[], AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blob write failing *inside* ``session.begin()`` rolls the artifact back.

    The provider-error case above proves nothing survives when the helper fails
    *before* the transaction opens. This case pins the harder invariant the
    ``_atomically`` design leans on: the artifact row is created and flushed, then
    the blob write raises within the same ``session.begin()`` — the whole
    transaction must roll back, leaving neither the artifact nor its blob.
    """
    project, thread = await _seed_project_and_thread(seed_session)
    result = ImageGenerationResult(data=_PNG, media_type="image/png", cost=0.067)
    monkeypatch.setattr(
        "app.agent.tools.image_generation.call_generate_image",
        _fake_helper(result),
    )

    async def _boom_put(_self: Any, **_kwargs: Any) -> None:
        raise RuntimeError("blob storage exploded mid-transaction")

    # Fail the blob write after ``ArtifactRepository.create`` has flushed the
    # artifact row, i.e. strictly inside the tool's ``session.begin()``.
    monkeypatch.setattr(PgBlobStorage, "put", _boom_put)

    tool = make_generate_image_tool(
        cast(Any, tool_session_factory),
        cast(Any, SimpleNamespace()),
        ImageConfig(model="m"),
    )

    with pytest.raises(RuntimeError, match="blob storage exploded"):
        await _coro(tool)(
            prompt="p",
            title="T",
            runtime=_runtime(project_id=project.id, thread_id=thread.thread_id),
        )

    # All-or-nothing: the artifact flushed before the failing blob write is gone,
    # and no blob leaked either — the reader on the same connection sees neither.
    artifacts = await ArtifactRepository(seed_session).list_by_project(project.id)
    assert artifacts == []


async def test_generate_image_without_context_raises(
    tool_session_factory: Callable[[], AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.agent.tools.image_generation.call_generate_image",
        _fake_helper(
            ImageGenerationResult(data=_PNG, media_type="image/png", cost=1.0)
        ),
    )
    tool = make_generate_image_tool(
        cast(Any, tool_session_factory),
        cast(Any, SimpleNamespace()),
        ImageConfig(model="m"),
    )

    with pytest.raises(RuntimeError, match="AgentContext"):
        await _coro(tool)(
            prompt="p",
            title="T",
            runtime=_runtime(
                project_id=uuid.uuid4(), thread_id=uuid.uuid4(), with_context=False
            ),
        )


async def test_generate_image_emits_langfuse_observation_with_cost(
    seed_session: AsyncSession,
    tool_session_factory: Callable[[], AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, thread = await _seed_project_and_thread(seed_session)
    result = ImageGenerationResult(data=_PNG, media_type="image/png", cost=0.101)
    monkeypatch.setattr(
        "app.agent.tools.image_generation.call_generate_image",
        _fake_helper(result),
    )

    recorded: list[dict[str, Any]] = []

    class _Obs:
        def __enter__(self) -> _Obs:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    class _Client:
        def start_as_current_observation(self, **kwargs: Any) -> _Obs:
            recorded.append(kwargs)
            return _Obs()

    monkeypatch.setattr(
        "app.agent.tools.image_generation.get_client", lambda: _Client()
    )

    tool = make_generate_image_tool(
        cast(Any, tool_session_factory),
        cast(Any, SimpleNamespace()),
        ImageConfig(model="google/gemini-3.1-flash-image"),
        langfuse_enabled=True,
    )

    await _coro(tool)(
        prompt="p",
        title="T",
        runtime=_runtime(project_id=project.id, thread_id=thread.thread_id),
    )

    # The cost-carrying generation observation is the only accounting hook for an
    # image call (it bypasses the token-usage callback) — assert the payload.
    assert len(recorded) == 1
    obs = recorded[0]
    assert obs["as_type"] == "generation"
    assert obs["model"] == "google/gemini-3.1-flash-image"
    assert obs["cost_details"] == {"total": 0.101}


async def test_generate_image_langfuse_observation_omits_cost_when_unknown(
    seed_session: AsyncSession,
    tool_session_factory: Callable[[], AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, thread = await _seed_project_and_thread(seed_session)
    result = ImageGenerationResult(data=_PNG, media_type="image/png", cost=None)
    monkeypatch.setattr(
        "app.agent.tools.image_generation.call_generate_image",
        _fake_helper(result),
    )

    recorded: list[dict[str, Any]] = []

    class _Obs:
        def __enter__(self) -> _Obs:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    class _Client:
        def start_as_current_observation(self, **kwargs: Any) -> _Obs:
            recorded.append(kwargs)
            return _Obs()

    monkeypatch.setattr(
        "app.agent.tools.image_generation.get_client", lambda: _Client()
    )

    tool = make_generate_image_tool(
        cast(Any, tool_session_factory),
        cast(Any, SimpleNamespace()),
        ImageConfig(model="m"),
        langfuse_enabled=True,
    )

    await _coro(tool)(
        prompt="p",
        title="T",
        runtime=_runtime(project_id=project.id, thread_id=thread.thread_id),
    )

    # None cost -> the observation is still opened, but with no cost_details
    # (a fabricated 0 would read as "free" in Langfuse reports).
    assert len(recorded) == 1
    assert "cost_details" not in recorded[0]
