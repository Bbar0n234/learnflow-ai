from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING, Any

import structlog
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.agent.security.detectors import check_canary_in_text, detect_invisible_chars
from app.agent.security.history_formatter import format_for_classifier
from app.agent.security.types import GuardResult, SecurityConfig, SecurityVerdict

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from app.infra.prompt_provider import PromptProvider

logger = structlog.get_logger()

# Checkpoint ID → human-readable description for the classifier prompt.
# These are part of the contract with guard-classifier.txt ({{ checkpoint }} variable).
# Changing values here requires updating the prompt to maintain calibration.
_CHECKPOINT_LABELS = {
    "user_input": "Analyzing a user's chat message in conversation context",
    "knowledge_sphere_write": "Analyzing content being written to persistent project memory",
    "mcp_tool_result": "Analyzing output returned by an external tool",
}


class SecurityGuard:
    def __init__(
        self,
        guard_llm: BaseChatModel,
        prompt_provider: PromptProvider,
        config: SecurityConfig,
    ) -> None:
        self._llm = guard_llm
        self._prompt_provider = prompt_provider
        self._config = config

    async def check(
        self,
        content: str,
        *,
        history: list[BaseMessage] | None = None,
        checkpoint: str = "user_input",
        canary_token: str | None = None,
    ) -> GuardResult:
        start = time.monotonic()

        # 1. Canary in input (fast path)
        canary_found = canary_token and check_canary_in_text(content, canary_token)
        if canary_found:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.warning("canary token found in input", checkpoint=checkpoint)
            self._emit_event(
                "canary-detector", {"has_canary": bool(canary_token)}, {"found": True}
            )
            return GuardResult(
                verdict=SecurityVerdict.INJECTION,
                reason="canary_in_input",
                duration_ms=duration_ms,
                details="Canary token detected in user input",
            )

        # 2. Invisible Unicode characters (fast path)
        has_invisible = detect_invisible_chars(content)
        self._emit_event(
            "unicode-detector",
            {"message_length": len(content)},
            {"safe": not has_invisible},
        )
        if has_invisible:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.warning("invisible chars detected", checkpoint=checkpoint)
            return GuardResult(
                verdict=SecurityVerdict.INJECTION,
                reason="invisible_chars",
                duration_ms=duration_ms,
                details="Invisible Unicode characters detected in input",
            )

        # 3. LLM classifier (with retry + graceful degradation)
        try:
            verdict = await self._classify(
                content, history=history or [], checkpoint=checkpoint
            )
        except Exception:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.warning(
                "guard llm failed, degrading to CLEAN",
                checkpoint=checkpoint,
                exc_info=True,
            )
            return GuardResult(
                verdict=SecurityVerdict.CLEAN,
                reason="llm_classifier",
                duration_ms=duration_ms,
                details="Guard LLM failed, graceful degradation to CLEAN",
            )

        duration_ms = int((time.monotonic() - start) * 1000)
        reason = "llm_classifier" if verdict != SecurityVerdict.CLEAN else None
        return GuardResult(
            verdict=verdict,
            reason=reason,
            duration_ms=duration_ms,
        )

    async def _classify(
        self,
        content: str,
        *,
        history: list[BaseMessage],
        checkpoint: str,
    ) -> SecurityVerdict:
        checkpoint_label = _CHECKPOINT_LABELS.get(checkpoint, checkpoint)
        system_text = self._prompt_provider.get_prompt(
            "guard-classifier", checkpoint=checkpoint_label
        )
        user_text = format_for_classifier(history, content)

        messages = [SystemMessage(content=system_text), HumanMessage(content=user_text)]
        classifier_input = [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ]

        gen_cm, gen_obs = self._start_generation(classifier_input)

        try:
            for attempt in range(self._config.max_retries):
                response = await self._llm.ainvoke(messages)
                raw = str(response.content).strip().upper()

                if raw in ("CLEAN", "SUSPICIOUS", "INJECTION"):
                    self._end_generation(gen_cm, gen_obs, raw)
                    return SecurityVerdict(raw)

                logger.warning(
                    "invalid classifier response, retrying",
                    attempt=attempt + 1,
                    raw_response=raw[:100],
                )

            logger.warning("classifier retries exhausted, degrading to CLEAN")
            self._end_generation(gen_cm, gen_obs, "CLEAN (retries exhausted)")
            return SecurityVerdict.CLEAN
        except Exception:
            self._end_generation(gen_cm, gen_obs, None, error=True)
            raise

    @staticmethod
    def _emit_event(
        name: str, input_data: dict[str, Any], output_data: dict[str, Any]
    ) -> None:
        """Create a Langfuse event under the current observation (fail-safe)."""
        with contextlib.suppress(Exception):
            from langfuse import get_client

            get_client().create_event(name=name, input=input_data, output=output_data)

    def _start_generation(
        self, classifier_input: list[dict[str, str]]
    ) -> tuple[Any, Any]:
        """Start a Langfuse generation observation (fail-safe)."""
        try:
            from langfuse import get_client

            cm = get_client().start_as_current_observation(
                as_type="generation",
                name="llm-classifier",
                model=self._config.guard_model,
                input=classifier_input,
                model_parameters={
                    "temperature": self._config.temperature,
                },
            )
            obs = cm.__enter__()
            return cm, obs
        except Exception:
            return None, None

    @staticmethod
    def _end_generation(
        cm: Any,
        obs: Any,
        output: str | None,
        *,
        error: bool = False,
    ) -> None:
        """Finalize and close Langfuse generation (fail-safe)."""
        if obs is not None:
            with contextlib.suppress(Exception):
                update_kwargs: dict[str, Any] = {"output": output}
                if error:
                    update_kwargs["level"] = "ERROR"
                    update_kwargs["status_message"] = "LLM classifier failed"
                obs.update(**update_kwargs)
        if cm is not None:
            with contextlib.suppress(Exception):
                cm.__exit__(None, None, None)
