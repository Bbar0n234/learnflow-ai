from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

import structlog
from langchain_core.messages import BaseMessage
from siem_contracts import (
    AGENT_GUARD_INPUT_CLASSIFIER_INJECTION, # TODO: Здесь тоже вопрос, то есть я помню, у нас действительно есть SIEM контракты, и в действительности это общий такой shared package, правильно? Но, соответственно, мне не очень понятно, то есть у нас же событие складывается из какого-то source (источник), action (действие) и результат (исход). И я предполагаю, что сейчас это всё монолитно фигачится, правильно? То есть все эти события, они монолитные. Ты импортируешь эту константу, она записывает это правильно собранное событие. Насколько это правильно, насколько это чисто? Какие у этого плюсы и минусы? Я просто думал, что это будет следующим образом: у тебя есть модуль, у тебя есть source, у тебя есть action, у тебя есть исход. И ты их как-то по отдельности собираешь, через context vars или ещё что-то такое. В нужной точке определённый компонент guard, он не знает о том, что он guard, он только знает действие или исход. Как-то так. То есть, условно говоря, если объяснить другими словами, я это видел как: не ты импортируешь большие монолитные константы, а ты где-то задаёшь какую-то общую переменную выше, затем уже когда погружаешься, ты в моменте знаешь либо action, либо исход, ты уже её логируешь, а то сверху дописывается само. Надеюсь, понятно объяснил, хотелось бы понимать, как у нас с этой точки зрения работает, какие плюсы-минусы, какие есть варианты решения и так далее.
    AGENT_GUARD_INPUT_DETERMINISTIC_HIT,
    AGENT_GUARD_OUTPUT_CLASSIFIER_INJECTION,
    AGENT_GUARD_OUTPUT_DETERMINISTIC_HIT,
)

from app.agent.security.classifier import LLMClassifier
from app.agent.security.detectors.base import DeterministicDetector
from app.agent.security.observer import GuardObserver
from app.agent.security.types import (
    Checkpoint,
    DetectionLayer,
    Direction,
    GuardResult,
    SecurityConfig,
    Verdict,
    direction_of,
)

logger = structlog.get_logger()


# Intra-checkpoint execution order: cheapest first, strongest discriminator last.
_LAYER_ORDER = {
    DetectionLayer.CANARY: 0,
    DetectionLayer.UNICODE: 1,
    DetectionLayer.PAIRED: 2,
    DetectionLayer.FRAGMENT: 3,
}


class SecurityGuard:
    def __init__(
        self,
        *,
        detectors: list[DeterministicDetector],
        classifier: LLMClassifier,
        observer: GuardObserver,
        config: SecurityConfig,
    ) -> None:
        self._config = config
        self._classifier = classifier
        self._observer = observer
        self._detectors_by_checkpoint = self._build_registry(detectors)

    @staticmethod
    def _build_registry(
        detectors: list[DeterministicDetector],
    ) -> dict[Checkpoint, list[DeterministicDetector]]:
        registry: dict[Checkpoint, list[DeterministicDetector]] = {
            cp: [] for cp in Checkpoint
        }
        for d in detectors:
            for cp in d.applies_to:
                registry[cp].append(d)
        for cp in registry:
            registry[cp].sort(key=lambda det: _LAYER_ORDER.get(det.layer, 99))
        return registry

    def _is_classifier_enabled(self, checkpoint: Checkpoint) -> bool:
        cfg = self._config.checkpoints.get(checkpoint)
        if cfg is None:
            return True
        return cfg.classifier_enabled

    async def check(
        self,
        content: str,
        checkpoint: Checkpoint,
        *,
        history: Sequence[BaseMessage] | None = None,
        canary_token: str | None = None,
        skip_classifier: bool = False,
        observe: bool = True,
        trace_ctx: dict[str, Any] | None = None,
    ) -> GuardResult:
        direction = direction_of(checkpoint)
        start = time.monotonic()

        async with self._observer.observe(
            checkpoint, content, trace_ctx=trace_ctx, enabled=observe
        ) as obs:
            # 1. Deterministic detectors (short-circuit on first hit)
            ctx: dict[str, Any] = {"canary_token": canary_token or ""}
            for detector in self._detectors_by_checkpoint.get(checkpoint, []):
                hit = detector.inspect(content, ctx)
                if hit is not None:
                    duration_ms = int((time.monotonic() - start) * 1000)
                    # Select canonical event_type based on direction (output if OUTBOUND)
                    is_output = direction == Direction.OUTBOUND
                    event_type = (
                        AGENT_GUARD_OUTPUT_DETERMINISTIC_HIT
                        if is_output
                        else AGENT_GUARD_INPUT_DETERMINISTIC_HIT
                    )

                    logger.warning(
                        "security hit (deterministic)",
                        security_event=True,
                        event_type=event_type,
                        severity="critical",
                        metadata={
                            "checkpoint": checkpoint.value,
                            "detection_layer": hit.layer.value,
                            "detector": detector.name,
                            "verdict": "injection",
                            **hit.details,
                        },
                    )
                    result = GuardResult(
                        verdict=Verdict.INJECTION,
                        checkpoint=checkpoint,
                        direction=direction,
                        detection_layer=hit.layer,
                        details=hit.details,
                        duration_ms=duration_ms,
                    )
                    obs.finalize(result)
                    return result

            # 2. Skip classifier (mid-stream tail-only / disabled)
            if skip_classifier or not self._is_classifier_enabled(checkpoint):
                result = GuardResult(
                    verdict=Verdict.CLEAN,
                    checkpoint=checkpoint,
                    direction=direction,
                    detection_layer=None,
                    details=None,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
                obs.finalize(result)
                return result

            # 3. LLM classifier with retry + graceful degradation
            try:
                classifier_result = await self._classifier.classify(
                    content, checkpoint, history, observation=obs
                )
            except Exception:
                duration_ms = int((time.monotonic() - start) * 1000)
                logger.warning(
                    "guard llm failed, degrading to CLEAN",
                    security_event=True,
                    event_type=AGENT_GUARD_INPUT_CLASSIFIER_INJECTION,  # Classify as attempted injection for safety
                    severity="critical",
                    metadata={
                        "checkpoint": checkpoint.value,
                        "detection_layer": DetectionLayer.GRACEFUL_DEGRADATION.value,
                        "verdict": "clean",  # Actual verdict is clean due to degradation
                    },
                    exc_info=True,
                )
                result = GuardResult(
                    verdict=Verdict.CLEAN,
                    checkpoint=checkpoint,
                    direction=direction,
                    detection_layer=DetectionLayer.GRACEFUL_DEGRADATION,
                    details={"reason": "llm_failure"},
                    duration_ms=duration_ms,
                )
                obs.finalize(result)
                return result

            duration_ms = int((time.monotonic() - start) * 1000)
            details: dict[str, Any] = {
                "reasoning": classifier_result.reasoning,
                "retries": classifier_result.retries,
            }
            result = GuardResult(
                verdict=classifier_result.verdict,
                checkpoint=checkpoint,
                direction=direction,
                detection_layer=DetectionLayer.LLM_CLASSIFIER,
                details=details,
                duration_ms=duration_ms,
            )

            if classifier_result.verdict == Verdict.INJECTION:
                # Select canonical event_type based on direction (output if OUTBOUND)
                is_output = direction == Direction.OUTBOUND
                event_type = (
                    AGENT_GUARD_OUTPUT_CLASSIFIER_INJECTION
                    if is_output
                    else AGENT_GUARD_INPUT_CLASSIFIER_INJECTION
                )

                logger.warning(
                    "security hit (classifier)",
                    security_event=True,
                    event_type=event_type,
                    severity="critical",
                    metadata={
                        "checkpoint": checkpoint.value,
                        "detection_layer": DetectionLayer.LLM_CLASSIFIER.value,
                        "verdict": "injection",
                        "retries": classifier_result.retries,
                    },
                )
            obs.finalize(result)
            return result


__all__ = ["SecurityGuard", "Direction"]
