"""Tests for ``MCPToolResolver`` — the user-tool resolution + cache layer.

The resolver owns three behaviors worth pinning: an in-memory TTL cache with
targeted invalidation, graceful degradation to ``[]`` when resolution fails, and
the additive merge (thread ∪ project ∪ user) with dedup, global-tool exclusion,
disabled-server skipping and a hard tool cap. Cache/degradation tests drive the
public ``resolve`` / ``invalidate`` against a stubbed ``_resolve_uncached``; the
merge tests fake the DB repository and the per-server tool fetch (the network
boundary) and assert the resolved tool names.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from app.services import mcp_tool_resolver as resolver_module
from app.services.encryption import EncryptionService
from app.services.mcp_tool_resolver import MAX_USER_TOOLS, MCPToolResolver

_UID = uuid.uuid4()
_PID = uuid.uuid4()
_TID = uuid.uuid4()


class _Tool:
    def __init__(self, name: str) -> None:
        self.name = name


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
) -> None:
    """Fake the DB repo + session_factory + per-server tool fetch for merge tests."""
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

    async def _fetch(server: Any) -> list[_Tool]:
        return server.tools

    monkeypatch.setattr(res, "_fetch_tools", _fetch)


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
