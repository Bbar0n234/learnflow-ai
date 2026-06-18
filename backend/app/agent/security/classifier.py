from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

import structlog
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.agent.security.history_formatter import format_for_classifier
from app.agent.security.types import (
    Checkpoint,
    CheckpointConfig,
    ClassifierResult,
    SecurityConfig,
    Verdict,
)
from app.infra.llm import extract_usage

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from app.agent.security.observer import ObservationHandle
    from app.infra.prompt_provider import PromptProvider

logger = structlog.get_logger()

_VALID = {"CLEAN", "SUSPICIOUS", "INJECTION"}


class LLMClassifier:
    """Composite classifier: single prompt with per-checkpoint slots."""

    def __init__(
        self,
        llm: BaseChatModel,
        prompt_provider: PromptProvider,
        security_config: SecurityConfig,
        checkpoint_configs: dict[Checkpoint, CheckpointConfig],
    ) -> None:
        self._llm = llm
        self._prompt_provider = prompt_provider
        self._config = security_config
        self._checkpoint_configs = checkpoint_configs

    async def classify(
        self,
        content: str,
        checkpoint: Checkpoint,
        history: Sequence[BaseMessage] | None = None,
        *,
        observation: ObservationHandle | None = None,
    ) -> ClassifierResult:
        cfg = self._checkpoint_configs.get(checkpoint) or CheckpointConfig()

        history_section = ""
        if history:
            history_section = format_for_classifier(history, "")

        specifics_section = cfg.specifics or ""

        system_text = self._prompt_provider.get_prompt(
            "security-classifier",
            checkpoint_description=cfg.description,
            checkpoint_specifics_section=specifics_section,
            history_section=history_section,
            content=content,
        )
        user_text = content

        messages: list[BaseMessage] = [
            SystemMessage(content=system_text),
            HumanMessage(content=user_text),
        ]
        classifier_input = [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ]

        classifier_cfg = self._config.llm_classifier

        if observation is not None:
            observation.record_classifier_generation(
                input_payload=classifier_input,
                model=classifier_cfg.model,
                params={"temperature": classifier_cfg.temperature},
            )

        last_raw: str | None = None
        # Detach from the parent runnable's callback chain: keeps guard
        # generations out of the agent node and prevents ``stream_mode="messages"``
        # from leaking verdicts into the user-facing response. Telemetry is
        # built independently via GuardObserver.
        guard_run_config: RunnableConfig = {
            "callbacks": [],
            "tags": ["security_guard"],
            "run_name": f"guard-classifier-{checkpoint.value}",
        }
        for attempt in range(classifier_cfg.max_retries):
            response = await self._llm.ainvoke(messages, config=guard_run_config)
            raw = str(response.content).strip().upper()
            last_raw = raw
            reasoning: str | None = None
            if isinstance(response.additional_kwargs, dict):
                reasoning = response.additional_kwargs.get("reasoning")

            if observation is not None:
                observation.update_generation(
                    raw_output=raw, token_usage=extract_usage(response)
                )

            if raw in _VALID:
                return ClassifierResult(
                    verdict=Verdict(raw),
                    reasoning=reasoning,
                    retries=attempt,
                )

            logger.warning(
                "invalid classifier response, retrying",
                attempt=attempt + 1,
                raw_response=raw[:100],
            )

        logger.warning(
            "classifier retries exhausted, degrading to CLEAN",
            checkpoint=checkpoint.value,
            last_raw=(last_raw or "")[:100],
        )
        return ClassifierResult(
            verdict=Verdict.CLEAN,
            reasoning=None,
            retries=classifier_cfg.max_retries,
            degraded=True,
        )
