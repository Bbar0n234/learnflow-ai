from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from contextlib import ExitStack, asynccontextmanager
from typing import Any

import structlog

from app.agent.security.types import VERDICT_TO_LEVEL, Checkpoint, GuardResult

logger = structlog.get_logger()


class ObservationHandle:
    """Handle exposed inside ``GuardObserver.observe(...)`` context.

    Each method is fail-safe — Langfuse errors are suppressed and logged.
    """

    def __init__(self, guard_obs: Any | None, root_obs: Any | None = None) -> None:
        self._guard_obs = guard_obs
        self._root_obs = root_obs
        self._gen_cm: Any = None
        self._gen_obs: Any = None

    def record_classifier_generation(
        self,
        *,
        input_payload: list[dict[str, str]],
        model: str,
        params: dict[str, Any],
    ) -> None:
        try:
            from langfuse import get_client

            self._gen_cm = get_client().start_as_current_observation(
                as_type="generation",
                name="llm-classifier",
                model=model,
                input=input_payload,
                model_parameters=params,
            )
            self._gen_obs = self._gen_cm.__enter__()
        except Exception:
            self._gen_cm = None
            self._gen_obs = None

    def update_generation(
        self,
        *,
        raw_output: str | None,
        token_usage: dict[str, Any] | None,
    ) -> None:
        if self._gen_obs is None:
            return
        from app.infra.llm import normalize_usage_for_langfuse

        with contextlib.suppress(Exception):
            kwargs: dict[str, Any] = {"output": raw_output}
            usage_details = normalize_usage_for_langfuse(token_usage)
            if usage_details:
                kwargs["usage_details"] = usage_details
            self._gen_obs.update(**kwargs)

    def _close_generation(self, *, error: bool = False) -> None:
        if self._gen_obs is not None and error:
            with contextlib.suppress(Exception):
                self._gen_obs.update(level="ERROR", status_message="classifier failed")
        if self._gen_cm is not None:
            with contextlib.suppress(Exception):
                self._gen_cm.__exit__(None, None, None)
        self._gen_cm = None
        self._gen_obs = None

    def finalize(self, result: GuardResult) -> None:
        metadata: dict[str, Any] = {}
        if result.detection_layer is not None:
            metadata["detection_layer"] = result.detection_layer.value
        if result.details:
            metadata["details"] = result.details
        level = VERDICT_TO_LEVEL.get(result.verdict, "DEFAULT")
        output = {
            "verdict": result.verdict.value,
            "detection_layer": (
                result.detection_layer.value
                if result.detection_layer is not None
                else None
            ),
        }

        if self._guard_obs is not None:
            with contextlib.suppress(Exception):
                self._guard_obs.update(
                    output=output,
                    metadata=metadata,
                    level=level,
                )

        if self._root_obs is not None:
            with contextlib.suppress(Exception):
                blocked = result.verdict.value == "INJECTION"
                self._root_obs.score_trace(
                    name="security_verdict",
                    value=result.verdict.value,
                    data_type="CATEGORICAL",
                    comment=(
                        result.detection_layer.value
                        if result.detection_layer is not None
                        else None
                    ),
                )
                self._root_obs.update(
                    output={**output, "blocked": blocked},
                    metadata={
                        "blocked": blocked,
                        "checkpoint": result.checkpoint.value,
                        **metadata,
                    },
                    level=level,
                )


class GuardObserver:
    """Two-mode observer for SecurityGuard calls.

    Mode is selected by ``trace_ctx``:

    * agent runtime (nested): no ``top_level`` flag — opens a nested
      ``guardrail`` observation under the current (parent) span.
    * REST add-time (top-level): ``trace_ctx["top_level"] is True`` — opens a
      top-level trace ``security.<checkpoint>`` with attribute propagation.
    """

    @asynccontextmanager
    async def observe(
        self,
        checkpoint: Checkpoint,
        content: str,
        *,
        trace_ctx: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> AsyncIterator[ObservationHandle]:
        if not enabled:
            yield ObservationHandle(None)
            return

        trace_ctx = trace_ctx or {}
        top_level = bool(trace_ctx.get("top_level"))

        stack = ExitStack()
        root_obs: Any = None
        guard_obs: Any = None

        get_client: Any = None
        propagate_attributes: Any = None
        try:
            from langfuse import (
                get_client as _get_client,
            )
            from langfuse import (
                propagate_attributes as _propagate_attributes,
            )

            from app.infra.langfuse import langfuse_enabled

            get_client = _get_client
            propagate_attributes = _propagate_attributes
        except Exception:
            langfuse_enabled = False

        if langfuse_enabled and get_client is not None:
            try:
                client = get_client()
                if top_level:
                    root_obs = stack.enter_context(
                        client.start_as_current_observation(
                            as_type="span",
                            name=f"security.{checkpoint.value}",
                            input=content,
                        )
                    )
                    attrs: dict[str, Any] = {
                        "trace_name": f"security.{checkpoint.value}"
                    }
                    user_id = trace_ctx.get("user_id")
                    if user_id:
                        attrs["user_id"] = str(user_id)
                    metadata = {
                        k: v
                        for k, v in trace_ctx.items()
                        if k not in {"top_level", "user_id"}
                    }
                    if metadata:
                        attrs["metadata"] = metadata
                    stack.enter_context(propagate_attributes(**attrs))

                guard_obs = stack.enter_context(
                    client.start_as_current_observation(
                        as_type="guardrail",
                        name=f"guard-{checkpoint.value}",
                        input=content,
                    )
                )
            except Exception:
                logger.warning("guard observer setup failed", exc_info=True)
                guard_obs = None

        handle = ObservationHandle(guard_obs, root_obs=root_obs)
        try:
            yield handle
        finally:
            with contextlib.suppress(Exception):
                handle._close_generation()
            try:
                stack.close()
            except Exception:
                logger.warning("guard observer cleanup failed", exc_info=True)
