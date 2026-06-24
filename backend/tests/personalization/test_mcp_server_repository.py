"""Integration tests for ``MCPServerRepository`` against real Postgres.

Covers the persistence surface that backs MCP CRUD: create + typed get,
``active_only`` filtering, per-scope counts, and the polymorphic disable rows
(set / list / remove / cleanup). Runs on the transactional session with rollback.
"""

from __future__ import annotations

import uuid

import pytest
from app.models.user import User
from app.repositories.mcp_server import MCPServerRepository
from learnflow_testing.factories import UserFactory
from sqlalchemy.ext.asyncio import AsyncSession


async def _make_user_server(
    repo: MCPServerRepository,
    user_id: uuid.UUID,
    *,
    name: str,
    is_active: bool = True,
) -> uuid.UUID:
    server = await repo.create_user_server(
        user_id=user_id,
        name=name,
        transport="http",
        url="https://mcp.example.com",
        is_active=is_active,
    )
    return server.id


@pytest.mark.integration
async def test_create_and_get_user_server(db_session: AsyncSession) -> None:
    user: User = await UserFactory.create()
    repo = MCPServerRepository(db_session)

    server_id = await _make_user_server(repo, user.id, name="weather")
    fetched = await repo.get_user_server(server_id)

    assert fetched is not None
    assert fetched.name == "weather"
    assert fetched.user_id == user.id


@pytest.mark.integration
async def test_get_user_server_missing_returns_none(
    db_session: AsyncSession,
) -> None:
    repo = MCPServerRepository(db_session)

    assert await repo.get_user_server(uuid.uuid4()) is None


@pytest.mark.integration
async def test_list_by_user_active_only_filters_inactive(
    db_session: AsyncSession,
) -> None:
    user: User = await UserFactory.create()
    repo = MCPServerRepository(db_session)
    await _make_user_server(repo, user.id, name="active-one", is_active=True)
    await _make_user_server(repo, user.id, name="inactive-one", is_active=False)

    active = await repo.list_by_user(user.id, active_only=True)
    all_servers = await repo.list_by_user(user.id, active_only=False)

    assert {s.name for s in active} == {"active-one"}
    assert {s.name for s in all_servers} == {"active-one", "inactive-one"}


@pytest.mark.integration
async def test_count_by_scope_counts_user_servers(
    db_session: AsyncSession,
) -> None:
    user: User = await UserFactory.create()
    repo = MCPServerRepository(db_session)
    await _make_user_server(repo, user.id, name="s1")
    await _make_user_server(repo, user.id, name="s2")

    assert await repo.count_by_scope("user", user.id) == 2


@pytest.mark.integration
async def test_set_disable_creates_and_lists_then_removes(
    db_session: AsyncSession,
) -> None:
    repo = MCPServerRepository(db_session)
    project_id = uuid.uuid4()
    server_id = uuid.uuid4()

    await repo.set_disable("project", project_id, server_id, disabled=True)
    assert await repo.list_disabled_ids("project", project_id) == {server_id}

    # Idempotent: disabling again keeps a single row.
    await repo.set_disable("project", project_id, server_id, disabled=True)
    assert await repo.list_disabled_ids("project", project_id) == {server_id}

    await repo.set_disable("project", project_id, server_id, disabled=False)
    assert await repo.list_disabled_ids("project", project_id) == set()


@pytest.mark.integration
async def test_cleanup_disables_for_server_removes_all_scopes(
    db_session: AsyncSession,
) -> None:
    repo = MCPServerRepository(db_session)
    server_id = uuid.uuid4()
    project_id = uuid.uuid4()
    thread_id = uuid.uuid4()
    await repo.set_disable("project", project_id, server_id, disabled=True)
    await repo.set_disable("thread", thread_id, server_id, disabled=True)

    await repo.cleanup_disables_for_server(server_id)

    assert await repo.list_disabled_ids("project", project_id) == set()
    assert await repo.list_disabled_ids("thread", thread_id) == set()
