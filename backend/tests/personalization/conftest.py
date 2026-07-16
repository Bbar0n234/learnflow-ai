"""Local fixtures for the personalization scope (S7).

The frozen backend ``app`` fixture builds a real ``create_app()`` but never runs
lifespan, so ``app.state`` is empty. The settings / models / mcp / user-memory
routes read collaborators off ``app.state`` (model resolver, agent config,
encryption, tool resolver, LangGraph store). Here we populate that state with
real-but-lightweight collaborators (real ``ModelConfigResolver`` over a stub
prompt provider, real ``EncryptionService`` with a throwaway key, an in-memory
LangGraph store) plus small stubs for the network-touching seams, and expose an
``api_client`` bound to the enriched app.

Nothing here touches the frozen harness; ``configured_app`` *depends on* the
root ``app`` fixture and mutates its ``state`` in place.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any, cast

import pytest
import pytest_asyncio
from app.agent.config import (
    AgentConfig,
    AvailableModel,
    ContextConfig,
    ImageConfig,
    LLMConfig,
)
from app.infra.prompt_provider import PromptProvider
from app.services.encryption import EncryptionService
from app.services.model_config_resolver import ModelConfigResolver
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from langgraph.store.memory import InMemoryStore


class StubPromptProvider:
    """Prompt provider stub: returns a fixed config (or ``None``) for any name."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config

    def get_config(self, name: str) -> dict[str, Any] | None:
        return self._config


class SpyToolResolver:
    """Records ``invalidate`` calls; the routes fire it after MCP mutations."""

    def __init__(self) -> None:
        self.invalidations: list[tuple[str, Any]] = []

    def invalidate(self, scope_type: str, scope_id: Any) -> None:
        self.invalidations.append((scope_type, scope_id))


def make_agent_config(
    *,
    model: str = "default-model",
    available: list[tuple[str, str]] | None = None,
) -> AgentConfig:
    """Minimal agent config: a base ``llm`` model + an allowed-models list."""
    if available is None:
        available = [("gpt-4o", "GPT-4o"), ("claude-3", "Claude 3")]
    return AgentConfig(
        llm=LLMConfig(model=model),
        context=ContextConfig(max_tokens=1000),
        image=ImageConfig(model="google/gemini-3.1-flash-image"),
        available_models=[AvailableModel(name=n, display_name=d) for n, d in available],
    )


def fernet_key() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture
def agent_config() -> AgentConfig:
    return make_agent_config()


@pytest.fixture
def configured_app(app: FastAPI, agent_config: AgentConfig) -> FastAPI:
    """Root ``app`` with ``state`` populated for the personalization routes.

    Tests may further override individual ``app.state`` slots before issuing a
    request (e.g. set ``security_guard`` to a ``StubGuard(INJECTION)``).
    """
    resolver = ModelConfigResolver(
        prompt_provider=cast(PromptProvider, StubPromptProvider(None)),
        agent_config=agent_config,
    )
    app.state.store = InMemoryStore()
    app.state.security_guard = None
    app.state.agent_config = agent_config
    app.state.settings = SimpleNamespace(mcp_timeout_seconds=30)
    app.state.encryption_service = EncryptionService(fernet_key())
    app.state.tool_resolver = SpyToolResolver()
    app.state.agent_runner = SimpleNamespace(_model_resolver=resolver)
    return app


@pytest_asyncio.fixture
async def api_client(configured_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Authenticated async client over the state-enriched app."""
    transport = ASGITransport(app=configured_app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
