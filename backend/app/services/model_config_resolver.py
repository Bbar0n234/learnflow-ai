from __future__ import annotations

import uuid

import structlog

from app.agent.config import AgentConfig, LLMConfig, ResolvedModelConfig
from app.infra.prompt_provider import PromptProvider
from app.repositories.settings import SettingsRepository

logger = structlog.get_logger()


class ModelConfigResolver:
    """Resolves effective model config via cascade: thread → project → user → Langfuse → agent.yaml."""

    def __init__(
        self,
        prompt_provider: PromptProvider,
        agent_config: AgentConfig,
    ) -> None:
        self._prompt_provider = prompt_provider
        self._llm_config = agent_config.llm

    async def resolve(
        self,
        settings_repo: SettingsRepository,
        user_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
        thread_id: uuid.UUID | None = None,
    ) -> ResolvedModelConfig:
        # Thread level
        if thread_id is not None:
            thread_settings = await settings_repo.get_thread_settings(thread_id)
            if thread_settings and thread_settings.model_name:
                return ResolvedModelConfig(
                    model=thread_settings.model_name,
                    extra_body=thread_settings.extra_body,
                    source="thread",
                )

        # Project level
        if project_id is not None:
            project_settings = await settings_repo.get_project_settings(project_id)
            if project_settings and project_settings.model_name:
                return ResolvedModelConfig(
                    model=project_settings.model_name,
                    extra_body=project_settings.extra_body,
                    source="project",
                )

        # User level
        user_settings = await settings_repo.get_user_settings(user_id)
        if user_settings and user_settings.model_name:
            return ResolvedModelConfig(
                model=user_settings.model_name,
                extra_body=user_settings.extra_body,
                source="user",
            )

        # Langfuse prompt config
        config = self._prompt_provider.get_config("system")
        if config and config.get("model"):
            return ResolvedModelConfig(
                model=config["model"],
                extra_body=config.get("extra_body"),
                source="langfuse",
            )

        # agent.yaml fallback
        return self.default()

    def default(self) -> ResolvedModelConfig:
        """Resolve the agent.yaml base model config (no per-scope overrides)."""
        return self._from_llm_config(self._llm_config)

    @staticmethod
    def _from_llm_config(llm: LLMConfig) -> ResolvedModelConfig:
        return ResolvedModelConfig(
            model=llm.model,
            extra_body=llm.extra_body or None,
            source="config",
        )
