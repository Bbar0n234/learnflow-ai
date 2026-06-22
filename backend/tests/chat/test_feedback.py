"""HTTP integration for the feedback routes.

Feedback sends a score to Langfuse — an external system. Per the testing
conventions that single call **is** the contract, so the Langfuse client is the
one legitimate mock here and we assert on the payload it receives. Everything
else is real: ownership goes through the dependency chain, and the Redis-backed
``TraceStore`` runs against an in-memory fake redis.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock

import httpx
import langfuse
import pytest
from app.config import Settings
from app.models.project import Project
from app.models.thread_view import ThreadView
from app.models.user import User
from app.repositories.thread_view import ThreadViewRepository
from app.repositories.trace_store import TraceStore
from fastapi import FastAPI
from httpx import AsyncClient
from learnflow_testing.factories import ProjectFactory
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    import redis.asyncio as aioredis

pytestmark = pytest.mark.integration


class FakeRedis:
    """Minimal in-memory redis covering the surface ``TraceStore`` uses."""

    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.strings: dict[str, str] = {}

    async def hset(self, key: str, field: str, value: str) -> None:
        self.hashes.setdefault(key, {})[field] = value

    async def expire(self, key: str, ttl: int) -> None:
        pass

    async def hgetall(self, key: str) -> dict[bytes, bytes]:
        return {k.encode(): v.encode() for k, v in self.hashes.get(key, {}).items()}

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.strings[key] = value

    async def delete(self, key: str) -> None:
        self.strings.pop(key, None)

    async def mget(self, keys: list[str]) -> list[bytes | None]:
        return [self.strings[k].encode() if k in self.strings else None for k in keys]


@pytest.fixture
def fake_redis(app: FastAPI) -> FakeRedis:
    redis = FakeRedis()
    app.state.redis = redis
    return redis


@pytest.fixture
def langfuse_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch ``langfuse.get_client`` (imported lazily inside the route)."""
    client = MagicMock()
    monkeypatch.setattr(langfuse, "get_client", lambda: client)
    return client


async def _owned_thread_with_trace(
    db_session: AsyncSession, user: User, redis: FakeRedis, trace_id: str
) -> tuple[Project, ThreadView]:
    project = await ProjectFactory.create(user=user)
    thread = await ThreadViewRepository(db_session).create(
        project_id=project.id, title="Chat"
    )
    await TraceStore(cast("aioredis.Redis", redis)).save(
        thread.thread_id, "m1", trace_id
    )
    return project, thread


@pytest.mark.parametrize(("score", "expected_value"), [(True, 1), (False, 0)])
async def test_set_feedback_sends_score_to_langfuse(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    fake_redis: FakeRedis,
    langfuse_client: MagicMock,
    score: bool,
    expected_value: int,
) -> None:
    project, thread = await _owned_thread_with_trace(
        db_session, current_user, fake_redis, "tr-1"
    )

    response = await client.put(
        f"/api/projects/{project.id}/chats/{thread.thread_id}/feedback/tr-1",
        json={"score": score},
    )

    assert response.status_code == 200
    assert response.json() == {"trace_id": "tr-1", "score": score}
    langfuse_client.create_score.assert_called_once_with(
        trace_id="tr-1",
        name="user-feedback",
        value=expected_value,
        data_type="BOOLEAN",
        score_id="tr-1-user-feedback",
    )


async def test_set_feedback_unknown_trace_returns_404(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    fake_redis: FakeRedis,
    langfuse_client: MagicMock,
) -> None:
    project, thread = await _owned_thread_with_trace(
        db_session, current_user, fake_redis, "tr-1"
    )

    response = await client.put(
        f"/api/projects/{project.id}/chats/{thread.thread_id}/feedback/unknown-trace",
        json={"score": True},
    )

    assert response.status_code == 404
    langfuse_client.create_score.assert_not_called()


async def test_set_feedback_without_redis_returns_503(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    # No fake_redis fixture: app.state.redis is unset -> feedback store missing.
    project = await ProjectFactory.create(user=current_user)
    thread = await ThreadViewRepository(db_session).create(
        project_id=project.id, title="Chat"
    )

    response = await client.put(
        f"/api/projects/{project.id}/chats/{thread.thread_id}/feedback/tr-1",
        json={"score": True},
    )

    assert response.status_code == 503


async def test_set_feedback_langfuse_unreachable_returns_503(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    fake_redis: FakeRedis,
    langfuse_client: MagicMock,
) -> None:
    project, thread = await _owned_thread_with_trace(
        db_session, current_user, fake_redis, "tr-1"
    )
    langfuse_client.create_score.side_effect = httpx.ConnectError("down")

    response = await client.put(
        f"/api/projects/{project.id}/chats/{thread.thread_id}/feedback/tr-1",
        json={"score": True},
    )

    assert response.status_code == 503


async def test_delete_feedback_returns_204(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    fake_redis: FakeRedis,
    langfuse_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    app: FastAPI,
) -> None:
    app.state.settings = Settings()

    async def _noop_delete(**kwargs: object) -> None:
        return None

    monkeypatch.setattr("app.api.routes.feedback._delete_score_via_api", _noop_delete)
    project, thread = await _owned_thread_with_trace(
        db_session, current_user, fake_redis, "tr-1"
    )

    response = await client.delete(
        f"/api/projects/{project.id}/chats/{thread.thread_id}/feedback/tr-1"
    )

    assert response.status_code == 204


async def test_delete_feedback_idempotent_when_score_already_gone(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    fake_redis: FakeRedis,
    langfuse_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    app: FastAPI,
) -> None:
    app.state.settings = Settings()

    async def _raise_404(**kwargs: object) -> None:
        request = httpx.Request("DELETE", "http://langfuse/api")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    monkeypatch.setattr("app.api.routes.feedback._delete_score_via_api", _raise_404)
    project, thread = await _owned_thread_with_trace(
        db_session, current_user, fake_redis, "tr-1"
    )

    response = await client.delete(
        f"/api/projects/{project.id}/chats/{thread.thread_id}/feedback/tr-1"
    )

    # A missing score on Langfuse must not surface as an error — delete is idempotent.
    assert response.status_code == 204
