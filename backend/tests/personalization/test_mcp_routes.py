"""HTTP integration tests for the MCP server routes.

Behind ``api_client`` the handlers hit real Postgres via the shared session. The
create path also touches the network seam (remote ``tools/list`` fetch + SSRF
validation) — we monkeypatch those in ``app.services.mcp_server`` so the test
stays offline and deterministic. Covered: empty list, ownership 404s, the
per-scope cap (409), and a successful create that invalidates the tool cache.
"""

from __future__ import annotations

import socket
import uuid
from typing import Any

import pytest
from app.models.user import User
from app.repositories.mcp_server import MCPServerRepository
from app.services import mcp_server as mcp_module
from fastapi import FastAPI
from httpx import AsyncClient
from learnflow_testing.factories import ProjectFactory
from sqlalchemy.ext.asyncio import AsyncSession

_VALID_CREATE = {
    "name": "weather",
    "transport": "http",
    "url": "https://mcp.example.com",
    "allowed_tools": [],
}


@pytest.fixture
def _offline_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the network seam: URL passes SSRF, remote returns no tools."""
    monkeypatch.setattr(mcp_module, "validate_url", lambda url: None)

    async def _fetch(*a: Any, **k: Any) -> list[dict]:
        return []

    monkeypatch.setattr(mcp_module, "fetch_remote_metadata", _fetch)


@pytest.mark.integration
async def test_list_user_servers_empty_by_default(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/users/me/mcp-servers")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


@pytest.mark.integration
async def test_update_unknown_user_server_returns_404(
    api_client: AsyncClient,
) -> None:
    resp = await api_client.put(
        f"/api/users/me/mcp-servers/{uuid.uuid4()}", json={"name": "x"}
    )

    assert resp.status_code == 404


@pytest.mark.integration
async def test_delete_unknown_user_server_returns_404(
    api_client: AsyncClient,
) -> None:
    resp = await api_client.delete(f"/api/users/me/mcp-servers/{uuid.uuid4()}")

    assert resp.status_code == 404


@pytest.mark.integration
async def test_create_user_server_rejects_when_scope_full(
    api_client: AsyncClient,
    db_session: AsyncSession,
    current_user: User,
) -> None:
    repo = MCPServerRepository(db_session)
    for i in range(5):  # MAX_SERVERS_PER_SCOPE
        await repo.create_user_server(
            user_id=current_user.id,
            name=f"srv-{i}",
            transport="http",
            url="https://mcp.example.com",
        )

    resp = await api_client.post("/api/users/me/mcp-servers", json=_VALID_CREATE)

    assert resp.status_code == 409


@pytest.mark.integration
async def test_create_user_server_persists_and_invalidates_cache(
    api_client: AsyncClient,
    configured_app: FastAPI,
    current_user: User,
    _offline_mcp: None,
) -> None:
    resp = await api_client.post("/api/users/me/mcp-servers", json=_VALID_CREATE)

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "weather"
    assert body["has_api_key"] is False
    # The route fired the targeted cache invalidation for the user scope.
    assert ("user", current_user.id) in configured_app.state.tool_resolver.invalidations

    listed = await api_client.get("/api/users/me/mcp-servers")
    assert listed.json()["total"] == 1


@pytest.mark.integration
async def test_test_user_server_private_url_returns_success_false(
    api_client: AsyncClient,
    db_session: AsyncSession,
    current_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``/test`` on a server whose URL resolves to a private IP returns the
    contract body ``{success: False, error: ...}`` — not a 4xx.

    ``validate_url`` raises ``SecurityPolicyViolationError`` (an ``AppError``,
    not ``ValueError``); the endpoint must translate that SSRF rejection into a
    failed connection result instead of letting it bubble into a 422.
    """
    repo = MCPServerRepository(db_session)
    server = await repo.create_user_server(
        user_id=current_user.id,
        name="ssrf-probe",
        transport="http",
        url="http://internal.example.com",
    )

    # Hostname resolves to a private IP → real validate_url raises the SSRF error.
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 0))
        ],
    )

    resp = await api_client.post(f"/api/users/me/mcp-servers/{server.id}/test")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert body["error"]


@pytest.mark.integration
async def test_list_project_servers_empty_by_default(
    api_client: AsyncClient,
    current_user: User,
) -> None:
    project = await ProjectFactory.create(user=current_user)

    resp = await api_client.get(f"/api/projects/{project.id}/mcp-servers")

    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.integration
async def test_project_servers_ownership_enforced(
    api_client: AsyncClient,
) -> None:
    # A project owned by a different user must 404 (ownership dep).
    other_project = await ProjectFactory.create()

    resp = await api_client.get(f"/api/projects/{other_project.id}/mcp-servers")

    assert resp.status_code == 404
