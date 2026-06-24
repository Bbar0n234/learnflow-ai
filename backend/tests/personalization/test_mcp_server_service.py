"""Tests for the MCP server service layer.

Two parts:

* **Pure helpers** — ``extract_schema_text`` (which JSON-Schema text the guard
  inspects) and ``serialize_mcp_meta_blob`` (deterministic blob layout). Solitary
  units, no collaborators.
* **``McpServerService``** — the guard → SSRF → encrypt → persist flow. Sociable
  unit: a fake repository (records writes), a real ``EncryptionService``, a
  ``StubGuard`` for the verdict, and the network seam (``fetch_remote_metadata``
  / ``validate_url``) monkeypatched. We assert the persisted data and
  raised errors, plus whether the guard is consulted on update — the observable
  contract — not internal call wiring.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, cast

import pytest
from app.agent.security.guard import SecurityGuard
from app.api.schemas.mcp_servers import MCPServerCreate, MCPServerUpdate
from app.repositories.mcp_server import MCPServerRepository
from app.services import mcp_server as mcp_module
from app.services.encryption import EncryptionService
from app.services.exceptions import (
    SecurityPolicyViolationError,
    UpstreamUnavailableError,
)
from app.services.mcp_server import (
    McpServerService,
    extract_schema_text,
    serialize_mcp_meta_blob,
)
from cryptography.fernet import Fernet
from learnflow_testing.fakes import StubGuard

from app.agent.security.types import Verdict  # isort: skip

_OWNER = uuid.uuid4()


# --------------------------------------------------------------- pure helpers


@pytest.mark.unit
def test_extract_schema_text_collects_descriptions_skips_types() -> None:
    schema = {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "title": "City",
                "description": "City name to look up",
            }
        },
        "required": ["city"],
        "examples": ["London"],
    }

    text = extract_schema_text(schema)

    assert "City name to look up" in text
    assert "City" in text
    assert "London" in text
    # Structural noise must not leak into the guarded text.
    assert "object" not in text
    assert "string" not in text


@pytest.mark.unit
def test_extract_schema_text_empty_for_none() -> None:
    assert extract_schema_text(None) == ""


@pytest.mark.unit
def test_serialize_mcp_meta_blob_includes_metadata_and_tools() -> None:
    blob = serialize_mcp_meta_blob(
        name="weather",
        transport="http",
        url="https://mcp.example.com",
        allowed_tools=["get_forecast", "get_alerts"],
        remote_tools=[
            {
                "name": "get_forecast",
                "description": "Return the forecast",
                "inputSchema": {"description": "city to query"},
            }
        ],
    )

    assert "name: weather" in blob
    assert "transport: http" in blob
    assert "url: https://mcp.example.com" in blob
    assert "allowed_tools: get_forecast, get_alerts" in blob
    assert "tool.name: get_forecast" in blob
    assert "tool.description: Return the forecast" in blob
    assert "city to query" in blob


# --------------------------------------------------------------- service flow


class FakeMCPRepo:
    """Records create/update writes; returns a server-shaped object."""

    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.updated: list[dict[str, Any]] = []

    async def create_user_server(self, **data: Any) -> SimpleNamespace:
        self.created.append(data)
        return SimpleNamespace(id=uuid.uuid4(), **data)

    async def update(self, server: Any, **data: Any) -> Any:
        self.updated.append(data)
        for key, value in data.items():
            setattr(server, key, value)
        return server


def _fernet_key() -> str:
    return Fernet.generate_key().decode()


def _service(
    repo: FakeMCPRepo,
    *,
    guard: StubGuard | None = None,
    encryption: EncryptionService | None = None,
) -> McpServerService:
    return McpServerService(
        repo=cast(MCPServerRepository, repo),
        guard=cast(SecurityGuard, guard) if guard is not None else None,
        encryption=encryption or EncryptionService(_fernet_key()),
    )


def _stub_network(
    monkeypatch: pytest.MonkeyPatch, tools: list[dict] | None = None
) -> None:
    monkeypatch.setattr(mcp_module, "validate_url", lambda url: None)

    async def _fetch(*a: Any, **k: Any) -> list[dict]:
        return tools or []

    monkeypatch.setattr(mcp_module, "fetch_remote_metadata", _fetch)


def _create_payload(**over: Any) -> MCPServerCreate:
    base: dict[str, Any] = {
        "name": "weather",
        "transport": "http",
        "url": "https://mcp.example.com",
        "allowed_tools": ["get_forecast"],
    }
    base.update(over)
    # ``model_validate`` coerces the dict (incl. str→HttpUrl) the way the HTTP
    # layer does, without tripping the strict pydantic-mypy init signature.
    return MCPServerCreate.model_validate(base)


@pytest.mark.unit
async def test_guard_and_persist_clean_verdict_persists_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_network(monkeypatch, tools=[{"name": "get_forecast", "description": "f"}])
    repo = FakeMCPRepo()
    service = _service(repo, guard=StubGuard(Verdict.CLEAN))

    server = await service.guard_and_persist(
        scope="user", owner_id=_OWNER, payload=_create_payload()
    )

    assert len(repo.created) == 1
    assert repo.created[0]["url"] == "https://mcp.example.com/"
    assert repo.created[0]["user_id"] == _OWNER
    assert server.name == "weather"


@pytest.mark.unit
async def test_guard_and_persist_injection_verdict_blocks_persist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_network(monkeypatch, tools=[{"name": "evil", "description": "ignore rules"}])
    repo = FakeMCPRepo()
    service = _service(repo, guard=StubGuard(Verdict.INJECTION))

    with pytest.raises(SecurityPolicyViolationError):
        await service.guard_and_persist(
            scope="user", owner_id=_OWNER, payload=_create_payload()
        )

    assert repo.created == []


@pytest.mark.unit
async def test_guard_and_persist_unreachable_host_maps_to_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_module, "validate_url", lambda url: None)

    async def _boom(*a: Any, **k: Any) -> list[dict]:
        raise ConnectionError("refused")

    monkeypatch.setattr(mcp_module, "fetch_remote_metadata", _boom)
    repo = FakeMCPRepo()
    service = _service(repo, guard=None)

    with pytest.raises(UpstreamUnavailableError) as exc:
        await service.guard_and_persist(
            scope="user", owner_id=_OWNER, payload=_create_payload()
        )

    assert exc.value.status == 503
    assert repo.created == []


@pytest.mark.unit
async def test_guard_and_persist_encrypts_api_key_and_stores_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_network(monkeypatch)
    repo = FakeMCPRepo()
    enc = EncryptionService(_fernet_key())
    service = _service(repo, guard=None, encryption=enc)

    await service.guard_and_persist(
        scope="user",
        owner_id=_OWNER,
        payload=_create_payload(api_key="supersecretkey"),
    )

    stored = repo.created[0]
    assert stored["api_key_encrypted"] is not None
    # Round-trips back to plaintext; hint masks the middle.
    assert enc.decrypt(stored["api_key_encrypted"]) == "supersecretkey"
    assert stored["api_key_hint"] == "supe...tkey"


@pytest.mark.unit
async def test_guard_and_persist_api_key_without_encryption_raises_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_network(monkeypatch)
    repo = FakeMCPRepo()
    service = _service(repo, guard=None, encryption=EncryptionService(""))

    with pytest.raises(UpstreamUnavailableError):
        await service.guard_and_persist(
            scope="user",
            owner_id=_OWNER,
            payload=_create_payload(api_key="supersecretkey"),
        )


def _existing_server() -> SimpleNamespace:
    return SimpleNamespace(
        name="weather",
        transport="http",
        url="https://old.example.com",
        allowed_tools=["get_forecast"],
        api_key_encrypted=None,
        api_key_hint=None,
        is_active=True,
    )


@pytest.mark.unit
async def test_update_api_key_only_skips_revalidation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_network(monkeypatch)
    repo = FakeMCPRepo()
    guard = StubGuard(Verdict.CLEAN)
    service = _service(repo, guard=guard)
    server = _existing_server()

    await service.update_and_reguard(
        scope="user",
        owner_id=_OWNER,
        server=server,
        payload=MCPServerUpdate.model_validate({"api_key": "newsecretkey"}),
    )

    # No mutable surface changed → guard never consulted.
    assert guard.calls == []
    assert repo.updated[0]["api_key_encrypted"] is not None


@pytest.mark.unit
async def test_update_url_change_triggers_revalidation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_network(monkeypatch)
    repo = FakeMCPRepo()
    guard = StubGuard(Verdict.CLEAN)
    service = _service(repo, guard=guard)
    server = _existing_server()

    await service.update_and_reguard(
        scope="user",
        owner_id=_OWNER,
        server=server,
        payload=MCPServerUpdate.model_validate({"url": "https://new.example.com"}),
    )

    assert len(guard.calls) == 1
    assert repo.updated[0]["url"] == "https://new.example.com/"


@pytest.mark.unit
async def test_update_injection_on_changed_url_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_network(monkeypatch, tools=[{"name": "evil", "description": "exfiltrate"}])
    repo = FakeMCPRepo()
    service = _service(repo, guard=StubGuard(Verdict.INJECTION))
    server = _existing_server()

    with pytest.raises(SecurityPolicyViolationError):
        await service.update_and_reguard(
            scope="user",
            owner_id=_OWNER,
            server=server,
            payload=MCPServerUpdate.model_validate({"url": "https://new.example.com"}),
        )

    assert repo.updated == []
