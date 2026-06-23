"""Tests for ``MCPToolResolver`` — the user-tool resolution + cache layer.

The resolver owns three behaviors worth pinning: an in-memory TTL cache with
targeted invalidation, graceful degradation to ``[]`` when resolution fails, and
the additive merge (thread ∪ project ∪ user) with dedup, global-tool exclusion,
disabled-server skipping and a hard tool cap. Cache/degradation tests drive the
public ``resolve`` / ``invalidate`` against a stubbed ``_resolve_uncached``; the
merge tests fake the DB repository and the per-server tool fetch (the network
boundary) and assert the resolved tool names.

The TTL boundary and negative-caching are exercised through an injected clock
(``resolver_module.time`` swapped for a manual ``_Clock``) so expiry is asserted
deterministically rather than by wall-clock sleeps. The per-server ``_fetch_tools``
path — allowed-tools filtering and decrypted-API-key header injection — is driven
against a fake ``MultiServerMCPClient`` instead of being stubbed wholesale.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, cast

import pytest
from app.models.mcp_server import UserMCPServer
from app.services import mcp_tool_resolver as resolver_module
from app.services.encryption import EncryptionService
from app.services.mcp_tool_resolver import (
    CACHE_TTL_SECONDS,
    MAX_USER_TOOLS,
    MCPToolResolver,
)
from cryptography.fernet import Fernet

_UID = uuid.uuid4()
_PID = uuid.uuid4()
_TID = uuid.uuid4()


class _Tool:
    def __init__(self, name: str) -> None:
        self.name = name


class _Clock:
    """Manual monotonic clock injected in place of ``resolver_module.time``.

    The resolver reads ``time.monotonic()`` for TTL bookkeeping; swapping the
    module reference lets a test advance time across the 5-minute boundary
    without sleeping and without patching the global ``time`` module.
    """

    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def monotonic(self) -> float:
        return self.now


def _resolver(global_names: set[str] | None = None) -> MCPToolResolver:
    return MCPToolResolver(
        session_factory=lambda: None,  # type: ignore[arg-type]
        encryption_service=EncryptionService(""),
        global_tool_names=global_names or set(),
    )


# ------------------------------------------------------------------ caching


@pytest.mark.unit
async def test_resolve_caches_within_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = _resolver()
    calls = {"n": 0}

    async def _uncached(u: Any, p: Any, t: Any) -> list[_Tool]:
        calls["n"] += 1
        return [_Tool(f"tool-{calls['n']}")]

    monkeypatch.setattr(resolver, "_resolve_uncached", _uncached)

    first = await resolver.resolve(_UID, _PID, _TID)
    second = await resolver.resolve(_UID, _PID, _TID)

    assert calls["n"] == 1  # second call served from cache
    assert [t.name for t in second] == ["tool-1"]
    assert first == second


@pytest.mark.unit
async def test_invalidate_forces_recompute_for_matching_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = _resolver()
    calls = {"n": 0}

    async def _uncached(u: Any, p: Any, t: Any) -> list[_Tool]:
        calls["n"] += 1
        return [_Tool(f"tool-{calls['n']}")]

    monkeypatch.setattr(resolver, "_resolve_uncached", _uncached)

    await resolver.resolve(_UID, _PID, _TID)
    resolver.invalidate("project", _PID)
    after = await resolver.resolve(_UID, _PID, _TID)

    assert calls["n"] == 2
    assert [t.name for t in after] == ["tool-2"]


@pytest.mark.unit
async def test_invalidate_unknown_scope_is_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = _resolver()
    calls = {"n": 0}

    async def _uncached(u: Any, p: Any, t: Any) -> list[_Tool]:
        calls["n"] += 1
        return [_Tool("x")]

    monkeypatch.setattr(resolver, "_resolve_uncached", _uncached)

    await resolver.resolve(_UID, _PID, _TID)
    resolver.invalidate("nonsense", _PID)
    await resolver.resolve(_UID, _PID, _TID)

    assert calls["n"] == 1  # cache untouched


@pytest.mark.unit
async def test_resolve_degrades_to_empty_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = _resolver()

    async def _boom(u: Any, p: Any, t: Any) -> list[_Tool]:
        raise RuntimeError("db down")

    monkeypatch.setattr(resolver, "_resolve_uncached", _boom)

    assert await resolver.resolve(_UID, _PID, _TID) == []


@pytest.mark.unit
async def test_cache_expires_after_ttl_and_recomputes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cached entry is served until the TTL elapses, then recomputed.

    Without the injected clock this boundary is invisible — the existing
    within-TTL test alone would pass even if the freshness check were dropped
    (entries would just be cached forever). Advancing past the boundary proves
    the timestamp comparison is load-bearing.
    """
    clock = _Clock()
    monkeypatch.setattr(resolver_module, "time", clock)
    resolver = _resolver()
    calls = {"n": 0}

    async def _uncached(u: Any, p: Any, t: Any) -> list[_Tool]:
        calls["n"] += 1
        return [_Tool(f"tool-{calls['n']}")]

    monkeypatch.setattr(resolver, "_resolve_uncached", _uncached)

    first = await resolver.resolve(_UID, _PID, _TID)
    # Still inside the TTL window — served from cache, no recompute.
    clock.now += CACHE_TTL_SECONDS - 1
    mid = await resolver.resolve(_UID, _PID, _TID)
    assert calls["n"] == 1
    assert [t.name for t in mid] == [t.name for t in first] == ["tool-1"]

    # Cross the boundary — the stale entry is discarded and recomputed.
    clock.now += 2
    after = await resolver.resolve(_UID, _PID, _TID)
    assert calls["n"] == 2
    assert [t.name for t in after] == ["tool-2"]


@pytest.mark.unit
async def test_failure_is_negatively_cached_until_ttl_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A degraded ``[]`` poisons the cache for the full TTL, then re-resolves.

    This pins the resolver's negative-caching contract: a transient resolution
    failure is remembered (the empty result is cached, not retried) until the
    TTL elapses — at which point a now-healthy backend is picked up. The clock
    injection makes both halves — the poisoning and the eventual recovery —
    observable.
    """
    clock = _Clock()
    monkeypatch.setattr(resolver_module, "time", clock)
    resolver = _resolver()
    calls = {"n": 0}

    async def _flaky(u: Any, p: Any, t: Any) -> list[_Tool]:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("db down")
        return [_Tool("recovered")]

    monkeypatch.setattr(resolver, "_resolve_uncached", _flaky)

    # First resolve fails → degrades to [] and caches that empty result.
    assert await resolver.resolve(_UID, _PID, _TID) == []
    assert calls["n"] == 1

    # Within the TTL the empty result is served from cache — no retry, even
    # though the backend may have recovered (the documented negative-cache cost).
    assert await resolver.resolve(_UID, _PID, _TID) == []
    assert calls["n"] == 1

    # After the TTL the entry is recomputed and the healthy backend is seen.
    clock.now += CACHE_TTL_SECONDS + 1
    after = await resolver.resolve(_UID, _PID, _TID)
    assert [t.name for t in after] == ["recovered"]
    assert calls["n"] == 2


# ------------------------------------------------------------------ merge


def _server(name: str, tools: list[str]) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), name=name, tools=[_Tool(t) for t in tools])


def _wire_merge(
    res: MCPToolResolver,
    monkeypatch: pytest.MonkeyPatch,
    *,
    thread: list[Any] | None = None,
    project: list[Any] | None = None,
    user: list[Any] | None = None,
    disabled: set[uuid.UUID] | None = None,
    fetch: Any | None = None,
) -> None:
    """Fake the DB repo + session_factory + per-server tool fetch for merge tests.

    ``fetch`` overrides the default per-server tool fetch (which just returns
    ``server.tools``); pass a custom coroutine to model an unreachable server.
    """
    t_list, p_list, u_list = thread or [], project or [], user or []
    disabled_set = disabled or set()

    class _Repo:
        def __init__(self, session: Any) -> None:
            pass

        async def list_by_thread(self, tid: Any, active_only: bool = True) -> list:
            return t_list

        async def list_by_project(self, pid: Any, active_only: bool = True) -> list:
            return p_list

        async def list_by_user(self, uid: Any, active_only: bool = True) -> list:
            return u_list

        async def list_disabled_ids(self, scope: str, sid: Any) -> set:
            return disabled_set

    monkeypatch.setattr(resolver_module, "MCPServerRepository", _Repo)

    class _Sess:
        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *exc: Any) -> bool:
            return False

    monkeypatch.setattr(res, "_session_factory", lambda: _Sess(), raising=False)

    async def _default_fetch(server: Any) -> list[_Tool]:
        return server.tools

    monkeypatch.setattr(res, "_fetch_tools", fetch or _default_fetch)


@pytest.mark.unit
async def test_resolve_dedups_by_name_with_thread_priority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    res = _resolver()
    _wire_merge(
        res,
        monkeypatch,
        thread=[_server("t", ["shared", "t_only"])],
        user=[_server("u", ["shared", "u_only"])],
    )

    tools = await res.resolve(_UID, _PID, _TID)

    assert [t.name for t in tools] == ["shared", "t_only", "u_only"]


@pytest.mark.unit
async def test_resolve_excludes_global_tool_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    res = _resolver(global_names={"banned"})
    _wire_merge(res, monkeypatch, user=[_server("u", ["banned", "allowed"])])

    tools = await res.resolve(_UID, _PID, _TID)

    assert [t.name for t in tools] == ["allowed"]


@pytest.mark.unit
async def test_resolve_skips_disabled_servers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    res = _resolver()
    disabled_srv = _server("off", ["drop"])
    _wire_merge(
        res,
        monkeypatch,
        thread=[disabled_srv],
        project=[_server("on", ["keep"])],
        disabled={disabled_srv.id},
    )

    tools = await res.resolve(_UID, _PID, _TID)

    assert [t.name for t in tools] == ["keep"]


@pytest.mark.unit
async def test_resolve_truncates_to_max_user_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    res = _resolver()
    _wire_merge(
        res,
        monkeypatch,
        user=[_server("u", [f"t{i}" for i in range(MAX_USER_TOOLS + 5)])],
    )

    tools = await res.resolve(_UID, _PID, _TID)

    assert len(tools) == MAX_USER_TOOLS


@pytest.mark.unit
async def test_resolve_isolates_one_unreachable_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One server whose fetch raises is skipped; the rest still merge.

    The per-server ``try/except`` in ``_resolve_uncached`` is the resilience
    contract: a single dead MCP server must degrade to *its own* absence, not
    sink the whole merge. The other merge tests always succeed for every
    server, so a regression that moved the ``try`` to wrap the whole loop would
    pass them while silently dropping every user's tools on one bad endpoint.
    """
    res = _resolver()
    bad = _server("bad", ["never"])
    good_thread = _server("good-thread", ["kept_t"])
    good_user = _server("good-user", ["kept_u"])

    async def _fetch(server: Any) -> list[_Tool]:
        if server is bad:
            raise RuntimeError("connection refused")
        return server.tools

    _wire_merge(
        res,
        monkeypatch,
        thread=[good_thread, bad],
        user=[good_user],
        fetch=_fetch,
    )

    tools = await res.resolve(_UID, _PID, _TID)

    # The broken server contributes nothing; both healthy servers survive.
    assert [t.name for t in tools] == ["kept_t", "kept_u"]


# ----------------------------------------------------------- _fetch_tools


def _fetch_server(
    *,
    allowed_tools: list[str],
    api_key_encrypted: bytes | None = None,
    transport: str = "http",
) -> UserMCPServer:
    # Duck-typed server double: ``_fetch_tools`` reads only these attributes.
    # cast keeps the typed call site honest (same pattern as the other doubles).
    return cast(
        UserMCPServer,
        SimpleNamespace(
            name="srv",
            url="https://mcp.example.com",
            transport=transport,
            api_key_encrypted=api_key_encrypted,
            allowed_tools=allowed_tools,
        ),
    )


def _fake_mcp_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tools: list[str],
    captured: dict[str, Any] | None = None,
) -> None:
    """Replace ``MultiServerMCPClient`` + neutralise the connection-time SSRF check.

    Drives the real ``_fetch_tools`` body (header assembly, allowed-tools
    filtering) instead of stubbing it wholesale. ``captured`` receives the
    single connection dict so header injection can be asserted.
    """
    monkeypatch.setattr(resolver_module, "validate_url", lambda url: None)

    class _Client:
        def __init__(self, connections: dict[str, Any]) -> None:
            if captured is not None:
                captured["conn"] = next(iter(connections.values()))

        async def get_tools(self, server_name: str) -> list[_Tool]:
            return [_Tool(name) for name in tools]

    monkeypatch.setattr(resolver_module, "MultiServerMCPClient", _Client)


@pytest.mark.unit
async def test_fetch_tools_filters_by_allowed_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``allowed_tools`` whitelists the remote tool set; others are dropped."""
    res = _resolver()
    _fake_mcp_client(monkeypatch, tools=["a", "b", "c"])

    tools = await res._fetch_tools(_fetch_server(allowed_tools=["a", "c"]))

    assert [t.name for t in tools] == ["a", "c"]


@pytest.mark.unit
async def test_fetch_tools_empty_allowlist_returns_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty ``allowed_tools`` means no filtering — every remote tool passes."""
    res = _resolver()
    _fake_mcp_client(monkeypatch, tools=["a", "b"])

    tools = await res._fetch_tools(_fetch_server(allowed_tools=[]))

    assert [t.name for t in tools] == ["a", "b"]


@pytest.mark.unit
async def test_fetch_tools_injects_decrypted_api_key_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stored API key is decrypted and forwarded as a Bearer auth header.

    The merge tests stub ``_fetch_tools`` whole, so the auth path never ran.
    Here a real ``EncryptionService`` round-trips the key and the captured
    connection proves the ``Authorization`` header reaches the MCP client.
    """
    encryption = EncryptionService(Fernet.generate_key().decode())
    res = MCPToolResolver(
        session_factory=lambda: None,  # type: ignore[arg-type]
        encryption_service=encryption,
        global_tool_names=set(),
    )
    captured: dict[str, Any] = {}
    _fake_mcp_client(monkeypatch, tools=["a"], captured=captured)

    server = _fetch_server(
        allowed_tools=[],
        api_key_encrypted=encryption.encrypt("super-secret"),
    )
    await res._fetch_tools(server)

    assert captured["conn"]["headers"]["Authorization"] == "Bearer super-secret"


@pytest.mark.unit
async def test_fetch_tools_omits_header_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No stored key → no ``headers`` slot on the connection (no empty auth)."""
    res = _resolver()
    captured: dict[str, Any] = {}
    _fake_mcp_client(monkeypatch, tools=["a"], captured=captured)

    await res._fetch_tools(_fetch_server(allowed_tools=[], api_key_encrypted=None))

    assert "headers" not in captured["conn"]
