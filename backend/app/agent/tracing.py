"""Langfuse instrumentation for one agent run, isolated from the runner.

``AgentRunTracer`` owns the Langfuse span lifecycle; ``AgentRunSpan`` is the
per-run handle the runner talks to (score, finalize-on-block, set output,
record a mid-stream guardrail hit). Whether tracing is active is carried by the
injected ``enabled`` flag — no module-level state, no lazy import of a global
(see conventions.md § FastAPI / § Module-level state).

``observe_compaction`` stands apart: it instruments an LLM call that runs with
its callbacks detached, so it hangs the observation on the ambient Langfuse
context itself instead of going through the injected span.

Every method is fail-safe: Langfuse errors are suppressed and logged so a
tracing outage never breaks the agent stream.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any

import structlog
from langfuse import get_client, propagate_attributes
from langfuse.langchain import CallbackHandler

from app.agent.security.types import Checkpoint, GuardResult, SecurityMessages, Verdict
from app.infra.llm import normalize_usage_for_langfuse

logger = structlog.get_logger()


class _NoOpSpan:
    trace_id = None
    id = None

    def update(self, **kwargs: Any) -> None:
        pass

    def score_trace(self, **kwargs: Any) -> None:
        pass


class AgentRunSpan:
    """Handle over a Langfuse root span for a single agent run.

    Wraps either a real Langfuse observation or ``_NoOpSpan`` when tracing is
    disabled / failed to start, so callers never branch on enabled state.
    """

    def __init__(
        self,
        span: Any,
        callback_handler: Any,
        *,
        enabled: bool,
        security_messages: SecurityMessages,
    ) -> None:
        self._span = span
        self._callback_handler = callback_handler
        self._enabled = enabled
        self._messages = security_messages

    @property
    def trace_id(self) -> Any:
        return self._span.trace_id

    @property
    def callback_handler(self) -> Any:
        return self._callback_handler

    def score(self, verdict: Verdict, detection_layer: Any) -> None:
        try:
            self._span.score_trace(
                name="security_verdict",
                value=verdict.value,
                data_type="CATEGORICAL",
                comment=detection_layer.value if detection_layer else None,
            )
        except Exception:
            logger.warning("security score failed", exc_info=True)

    def finalize_blocked(self, guard_result: GuardResult) -> None:
        try:
            self._span.score_trace(
                name="security_verdict",
                value=Verdict.INJECTION.value,
                data_type="CATEGORICAL",
                comment=(
                    guard_result.detection_layer.value
                    if guard_result.detection_layer
                    else None
                ),
            )
            self._span.update(
                output=self._messages.redacted_user_facing,
                metadata={
                    "blocked": True,
                    "checkpoint": guard_result.checkpoint.value,
                    "detection_layer": (
                        guard_result.detection_layer.value
                        if guard_result.detection_layer
                        else None
                    ),
                },
                level="ERROR",
            )
        except Exception:
            logger.warning("blocked trace finalization failed", exc_info=True)

    def set_output(self, output: str) -> None:
        try:
            self._span.update(output=output)
        except Exception:
            logger.warning("span output update failed", exc_info=True)

    def record_mid_stream_hit(
        self,
        *,
        thread_id: uuid.UUID,
        full_response: str,
        tail: str,
        result: GuardResult,
        chunks_processed: int,
    ) -> None:
        """Emit a single retrospective guardrail observation for a mid-stream hit.

        Mid-stream checks run per-chunk silently; when a hit fires we record one
        ``guard-final_output`` observation with the full context (accumulated
        response, detected tail, detector layer/details, chunk counter).
        """
        if not self._enabled:
            return
        try:
            detection_layer = (
                result.detection_layer.value if result.detection_layer else None
            )
            with get_client().start_as_current_observation(
                as_type="guardrail",
                name=f"guard-{Checkpoint.FINAL_OUTPUT.value}",
                input=full_response,
            ) as obs:
                obs.update(
                    output={
                        "verdict": result.verdict.value,
                        "detection_layer": detection_layer,
                    },
                    metadata={
                        "mode": "mid_stream",
                        "detection_layer": detection_layer,
                        "details": result.details or {},
                        "chunks_processed": chunks_processed,
                        "response_length": len(full_response),
                        "tail_length": len(tail),
                        "tail_snapshot": tail,
                        "duration_ms": result.duration_ms,
                        "thread_id": str(thread_id),
                    },
                    level="ERROR",
                )
        except Exception:
            logger.warning(
                "mid-stream hit observation failed",
                thread_id=str(thread_id),
                exc_info=True,
            )


class AgentRunTracer:
    """Builds an ``AgentRunSpan`` per agent run.

    ``enabled`` is resolved once at startup (auth-checked Langfuse client) and
    injected here, so request-scope code never reads a module-level flag.
    """

    def __init__(self, *, enabled: bool, security_messages: SecurityMessages) -> None:
        self._enabled = enabled
        self._messages = security_messages

    @contextmanager
    def run(
        self,
        *,
        content: str,
        user_id: uuid.UUID,
        thread_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> Iterator[AgentRunSpan]:
        if not self._enabled:
            yield AgentRunSpan(
                _NoOpSpan(),
                None,
                enabled=False,
                security_messages=self._messages,
            )
            return

        span: Any = _NoOpSpan()
        handler = None
        stack = ExitStack()
        try:
            langfuse = get_client()
            actual_span = stack.enter_context(
                langfuse.start_as_current_observation(
                    as_type="span", name="agent-run", input=content
                )
            )
            stack.enter_context(
                propagate_attributes(
                    user_id=str(user_id),
                    session_id=str(thread_id),
                    trace_name="agent-run",
                    metadata={"project_id": str(project_id)},
                )
            )
            span = actual_span
            handler = CallbackHandler()
        except Exception:
            logger.warning(
                "langfuse setup failed, proceeding without tracing", exc_info=True
            )

        try:
            yield AgentRunSpan(
                span,
                handler,
                enabled=True,
                security_messages=self._messages,
            )
        finally:
            try:
                stack.close()
            except Exception:
                logger.warning("langfuse cleanup failed", exc_info=True)


class CompactionGeneration:
    """Handle over the Langfuse generation for one context-compaction call.

    Every method is fail-safe: a Langfuse error is suppressed and logged, the
    compaction it describes goes on regardless.
    """

    def __init__(self, obs: Any | None) -> None:
        self._obs = obs

    def record_summary(
        self, *, summary: str, token_usage: dict[str, Any] | None
    ) -> None:
        """Attach the produced summary and the call's token usage.

        ``usage_details`` is what makes the call show up in cost accounting:
        Langfuse prices it by the generation's ``model`` (``configs/pricing.yaml``).
        """
        if self._obs is None:
            return
        try:
            kwargs: dict[str, Any] = {"output": summary}
            usage_details = normalize_usage_for_langfuse(token_usage)
            if usage_details:
                kwargs["usage_details"] = usage_details
            self._obs.update(**kwargs)
        except Exception:
            logger.warning("compaction generation update failed", exc_info=True)

    def record_failure(self, message: str) -> None:
        if self._obs is None:
            return
        with contextlib.suppress(Exception):
            self._obs.update(level="ERROR", status_message=message)


@contextmanager
def observe_compaction(
    *,
    input_payload: list[dict[str, str]],
    model: str | None,
    model_parameters: dict[str, Any],
    metadata: dict[str, Any],
) -> Iterator[CompactionGeneration]:
    """Observe the summarization call that compacts the agent's context.

    Compaction invokes its model with the callback chain detached (see
    ``graph._reduce_context``), which also cuts it off from the Langfuse
    LangChain handler — this observation is the compensation, the same trade the
    guard classifier makes (``security/observer.py``). It opens on the ambient
    Langfuse context, so the generation nests under the current agent-run span
    when tracing is on and no-ops on a disabled client.

    Manual ``__enter__`` / ``__exit__`` over the sync Langfuse CM (as in
    ``ObservationHandle``) keeps the setup failure isolated from the caller.
    """
    gen_cm: Any = None
    obs: Any = None
    try:
        gen_cm = get_client().start_as_current_observation(
            as_type="generation",
            name="context-summarization",
            model=model,
            input=input_payload,
            model_parameters=model_parameters,
            metadata=metadata,
        )
        obs = gen_cm.__enter__()
    except Exception:
        logger.warning("compaction observation setup failed", exc_info=True)
        gen_cm = None
        obs = None

    handle = CompactionGeneration(obs)
    try:
        yield handle
    except Exception:
        handle.record_failure("summarization failed")
        raise
    finally:
        if gen_cm is not None:
            with contextlib.suppress(Exception):
                gen_cm.__exit__(None, None, None)
