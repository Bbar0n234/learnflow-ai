"""Sociable-unit tests for the model-config cascade resolver.

``ModelConfigResolver.resolve`` walks thread -> project -> user -> Langfuse ->
agent.yaml and returns the first level that carries a ``model_name``. We drive it
with a fake settings repository (in-memory rows) and a stub prompt provider, and
assert the *resolved* model + source — the observable contract — rather than
which lookups fired.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, cast

import pytest
from app.agent.config import (
    AgentConfig,
    ContextConfig,
    ImageConfig,
    LLMConfig,
    TitleConfig,
)
from app.infra.prompt_provider import PromptProvider
from app.repositories.settings import SettingsRepository
from app.services.model_config_resolver import ModelConfigResolver


class FakeSettingsRepo:
    """In-memory stand-in for ``SettingsRepository`` scope lookups."""

    def __init__(
        self,
        *,
        user: Any | None = None,
        project: Any | None = None,
        thread: Any | None = None,
    ) -> None:
        self._user = user
        self._project = project
        self._thread = thread

    async def get_user_settings(self, user_id: uuid.UUID) -> Any | None:
        return self._user

    async def get_project_settings(self, project_id: uuid.UUID) -> Any | None:
        return self._project

    async def get_thread_settings(self, thread_id: uuid.UUID) -> Any | None:
        return self._thread


class StubPromptProvider:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config

    def get_config(self, name: str) -> dict[str, Any] | None:
        return self._config


def _settings_row(model_name: str | None, extra_body: dict | None = None) -> Any:
    return SimpleNamespace(model_name=model_name, extra_body=extra_body)


def _fake_repo(**kwargs: Any) -> SettingsRepository:
    # Duck-typed in-memory stand-in; cast to satisfy the concrete-class signature.
    return cast(SettingsRepository, FakeSettingsRepo(**kwargs))


def _resolver(prompt_config: dict[str, Any] | None = None) -> ModelConfigResolver:
    agent_config = AgentConfig(
        llm=LLMConfig(model="agent-yaml-model", extra_body={"foo": "bar"}),
        context=ContextConfig(max_tokens=1000),
        image=ImageConfig(model="google/gemini-3.1-flash-image"),
        title=TitleConfig(model="deepseek/deepseek-v4-flash"),
    )
    return ModelConfigResolver(
        prompt_provider=cast(PromptProvider, StubPromptProvider(prompt_config)),
        agent_config=agent_config,
    )


_UID = uuid.uuid4()
_PID = uuid.uuid4()
_TID = uuid.uuid4()


@pytest.mark.unit
async def test_resolve_thread_override_wins() -> None:
    repo = _fake_repo(
        user=_settings_row("user-model"),
        project=_settings_row("project-model"),
        thread=_settings_row("thread-model", {"t": 1}),
    )
    resolver = _resolver()

    resolved = await resolver.resolve(repo, _UID, _PID, _TID)

    assert (resolved.model, resolved.source) == ("thread-model", "thread")
    assert resolved.extra_body == {"t": 1}


@pytest.mark.unit
async def test_resolve_falls_to_project_when_thread_absent() -> None:
    repo = _fake_repo(
        user=_settings_row("user-model"),
        project=_settings_row("project-model"),
        thread=None,
    )

    resolved = await _resolver().resolve(repo, _UID, _PID, _TID)

    assert (resolved.model, resolved.source) == ("project-model", "project")


@pytest.mark.unit
async def test_resolve_falls_to_user_when_higher_scopes_absent() -> None:
    repo = _fake_repo(user=_settings_row("user-model"))

    resolved = await _resolver().resolve(repo, _UID, _PID, _TID)

    assert (resolved.model, resolved.source) == ("user-model", "user")


@pytest.mark.unit
async def test_resolve_uses_langfuse_config_when_no_db_overrides() -> None:
    repo = _fake_repo()
    resolver = _resolver({"model": "langfuse-model", "extra_body": {"lf": True}})

    resolved = await resolver.resolve(repo, _UID, _PID, _TID)

    assert (resolved.model, resolved.source) == ("langfuse-model", "langfuse")
    assert resolved.extra_body == {"lf": True}


@pytest.mark.unit
async def test_resolve_falls_back_to_agent_yaml_default() -> None:
    repo = _fake_repo()

    resolved = await _resolver(prompt_config=None).resolve(repo, _UID, _PID, _TID)

    assert (resolved.model, resolved.source) == ("agent-yaml-model", "config")
    assert resolved.extra_body == {"foo": "bar"}


@pytest.mark.unit
async def test_resolve_ignores_row_without_model_name() -> None:
    # A settings row exists but model_name is None -> skip this scope.
    repo = _fake_repo(
        user=_settings_row("user-model"),
        project=_settings_row(None),
        thread=None,
    )

    resolved = await _resolver().resolve(repo, _UID, _PID, _TID)

    assert (resolved.model, resolved.source) == ("user-model", "user")


@pytest.mark.unit
async def test_resolve_without_project_or_thread_uses_user_scope() -> None:
    repo = _fake_repo(user=_settings_row("user-model"))

    resolved = await _resolver().resolve(repo, _UID)

    assert (resolved.model, resolved.source) == ("user-model", "user")


@pytest.mark.unit
def test_default_returns_agent_yaml_config() -> None:
    resolved = _resolver().default()

    assert (resolved.model, resolved.source) == ("agent-yaml-model", "config")


@pytest.mark.unit
async def test_resolve_override_with_none_extra_body_inherits_default() -> None:
    # Scope switched the model but the settings row never carried an
    # extra_body (None) -> the agent.yaml reasoning default must survive.
    repo = _fake_repo(user=_settings_row("user-model", extra_body=None))

    resolved = await _resolver().resolve(repo, _UID, _PID, _TID)

    assert (resolved.model, resolved.source) == ("user-model", "user")
    assert resolved.extra_body == {"foo": "bar"}


@pytest.mark.unit
async def test_resolve_override_with_empty_extra_body_inherits_default() -> None:
    # Settings rows store extra_body as JSON, so an explicit "no override" can
    # arrive as {} rather than None -> must inherit the default just the same.
    repo = _fake_repo(user=_settings_row("user-model", extra_body={}))

    resolved = await _resolver().resolve(repo, _UID, _PID, _TID)

    assert (resolved.model, resolved.source) == ("user-model", "user")
    assert resolved.extra_body == {"foo": "bar"}


@pytest.mark.unit
async def test_resolve_override_with_own_extra_body_keeps_priority() -> None:
    # A scope with its own non-empty extra_body must NOT be overwritten by the
    # agent.yaml default.
    repo = _fake_repo(user=_settings_row("user-model", extra_body={"own": True}))

    resolved = await _resolver().resolve(repo, _UID, _PID, _TID)

    assert (resolved.model, resolved.source) == ("user-model", "user")
    assert resolved.extra_body == {"own": True}
