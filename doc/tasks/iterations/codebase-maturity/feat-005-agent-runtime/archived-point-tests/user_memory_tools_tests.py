"""feat-005: user_memory tools aligned with KS pattern (finding E).

Contract change: missing Store / AgentContext now raises RuntimeError (was an
error string) — matching the Knowledge Sphere tools.
"""

import asyncio
from types import SimpleNamespace

import pytest
from app.agent.tools.user_memory import (
    _store,
    _user_id,
    delete_user_memory,
    save_user_memory,
)


class _FakeStore:
    def __init__(self) -> None:
        self.puts: list = []
        self.deletes: list = []

    async def aput(self, ns, key, value) -> None:
        self.puts.append((ns, key, value))

    async def adelete(self, ns, key) -> None:
        self.deletes.append((ns, key))


def _runtime(store, user_id: str = "u1"):
    context = None if user_id is None else SimpleNamespace(user_id=user_id)
    return SimpleNamespace(store=store, context=context)


def test_store_raises_when_missing() -> None:
    with pytest.raises(RuntimeError):
        _store(_runtime(None))


def test_user_id_raises_when_context_missing() -> None:
    with pytest.raises(RuntimeError):
        _user_id(_runtime(_FakeStore(), user_id=None))


def test_save_user_memory_writes_to_store() -> None:
    store = _FakeStore()
    runtime = _runtime(store)
    result = asyncio.run(
        save_user_memory.coroutine(
            key="prefers-bullets",
            description="likes bullets",
            content="The user prefers bullet points.",
            runtime=runtime,
        )
    )
    assert result == "Memory saved: prefers-bullets"
    assert store.puts == [
        (
            ("user", "u1", "memory"),
            "prefers-bullets",
            {
                "description": "likes bullets",
                "content": "The user prefers bullet points.",
            },
        )
    ]


def test_delete_user_memory_deletes_from_store() -> None:
    store = _FakeStore()
    result = asyncio.run(
        delete_user_memory.coroutine(key="prefers-bullets", runtime=_runtime(store))
    )
    assert result == "Memory deleted: prefers-bullets"
    assert store.deletes == [(("user", "u1", "memory"), "prefers-bullets")]


def test_save_raises_without_store() -> None:
    with pytest.raises(RuntimeError):
        asyncio.run(
            save_user_memory.coroutine(
                key="k", description="d", content="c", runtime=_runtime(None)
            )
        )


def test_delete_raises_without_store() -> None:
    with pytest.raises(RuntimeError):
        asyncio.run(delete_user_memory.coroutine(key="k", runtime=_runtime(None)))
