from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from typing import Any

import structlog
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.config import ResolvedModelConfig
from app.agent.graph import AgentContext
from app.agent.graph_factory import GraphFactory
from app.agent.security.canary import generate_canary_token
from app.agent.security.detectors import check_canary_in_text
from app.agent.security.guard import SecurityGuard
from app.agent.security.types import SecurityVerdict
from app.repositories.settings import SettingsRepository
from app.services.agent_runner import Message, StreamEvent
from app.services.model_config_resolver import ModelConfigResolver

logger = structlog.get_logger()

BLOCKED_USER_MESSAGE = "Запрос заблокирован из соображений безопасности."
CANARY_BLOCKED_USER_MESSAGE = (
    "Ответ заблокирован: обнаружена потенциальная утечка системной информации."
)

_VERDICT_TO_LEVEL = {
    SecurityVerdict.CLEAN: "DEFAULT",
    SecurityVerdict.SUSPICIOUS: "WARNING",
    SecurityVerdict.INJECTION: "ERROR",
}


class _NoOpSpan:
    """No-op span when Langfuse is unavailable."""

    trace_id = None
    id = None

    def update(self, **kwargs: Any) -> None:
        pass


@contextmanager
def _langfuse_observation(
    content: str,
    user_id: uuid.UUID,
    thread_id: uuid.UUID,
    project_id: uuid.UUID,
) -> Any:
    """Fail-safe Langfuse instrumentation. Yields (span, handler).

    ExitStack keeps CM references alive so OTel context stays active during
    the async generator stream. OTel detach errors on cleanup are expected
    (token created in a different async context) and suppressed.
    """
    from langfuse import get_client, propagate_attributes
    from langfuse.langchain import CallbackHandler

    from app.infra.langfuse import langfuse_enabled

    span: Any = _NoOpSpan()
    handler = None
    stack = ExitStack()

    if not langfuse_enabled:
        yield span, handler
        return

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
        yield span, handler
    finally:
        try:
            stack.close()
        except Exception:
            logger.warning("langfuse cleanup failed", exc_info=True)


def _parse_created_at(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


class LangGraphAgentRunner:
    def __init__(
        self,
        graph_factory: GraphFactory,
        model_resolver: ModelConfigResolver,
        checkpointer: Any,
        tool_resolver: Any | None = None,
        security_guard: SecurityGuard | None = None,
        canary_secret: str = "",
    ) -> None:
        self._graph_factory = graph_factory
        self._model_resolver = model_resolver
        self._checkpointer = checkpointer
        self._tool_resolver = tool_resolver
        self._security_guard = security_guard
        self._canary_secret = canary_secret
        self._cancel_events: dict[uuid.UUID, asyncio.Event] = {}
        self._pending_cancels: set[uuid.UUID] = set()

    async def stream(
        self,
        *,
        thread_id: uuid.UUID,
        content: str,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        session: AsyncSession | None = None,
        model_config: ResolvedModelConfig | None = None,
    ) -> AsyncIterator[StreamEvent]:
        cancel_event = asyncio.Event()
        self._cancel_events[thread_id] = cancel_event
        if thread_id in self._pending_cancels:
            self._pending_cancels.discard(thread_id)
            cancel_event.set()

        # Resolve model if not provided
        if model_config is None and session is not None:
            settings_repo = SettingsRepository(session)
            model_config = await self._model_resolver.resolve(
                settings_repo, user_id, project_id, thread_id
            )

        # Fallback to config default if no session available
        if model_config is None:
            model_config = self._model_resolver._from_llm_config(
                self._model_resolver._llm_config
            )

        # Resolve user MCP tools
        extra_tools: list[Any] = []
        if self._tool_resolver is not None:
            try:
                extra_tools = await self._tool_resolver.resolve(
                    user_id, project_id, thread_id
                )
            except Exception:
                logger.warning(
                    "user mcp tools resolution failed, using global tools only",
                    exc_info=True,
                )

        # Build graph per-request
        graph = self._graph_factory.build(model_config, extra_tools=extra_tools)

        # Generate canary token
        canary_token = ""
        if self._canary_secret:
            canary_token = generate_canary_token(str(thread_id), self._canary_secret)

        logger.info(
            "agent invoked",
            thread_id=str(thread_id),
            project_id=str(project_id),
            model=model_config.model,
            model_source=model_config.source,
        )
        stream_start = time.monotonic()
        stream_error = False
        full_response = ""

        with _langfuse_observation(content, user_id, thread_id, project_id) as (
            span,
            lf_handler,
        ):
            # --- Pre-graph security check ---
            guard_result = None
            if self._security_guard is not None:
                history = await self._get_checkpoint_messages(thread_id)
                guard_result = await self._run_guard_with_observability(
                    span, content, history, canary_token
                )

                if guard_result.verdict == SecurityVerdict.INJECTION:
                    self._finalize_blocked_trace(span, guard_result, "input_guard")
                    yield StreamEvent(
                        type="security_block",
                        data={"reason": guard_result.reason or "prompt_injection"},
                    )
                    if span.trace_id:
                        yield StreamEvent(
                            type="trace_id",
                            data={"trace_id": span.trace_id},
                        )
                    return

                if guard_result.verdict == SecurityVerdict.SUSPICIOUS:
                    logger.warning(
                        "suspicious input detected, proceeding",
                        thread_id=str(thread_id),
                        reason=guard_result.reason,
                    )

            # --- Score CLEAN/SUSPICIOUS on trace ---
            if guard_result is not None:
                self._score_trace(span, guard_result.verdict, guard_result.reason)

            config: dict[str, Any] = {"configurable": {"thread_id": str(thread_id)}}
            if lf_handler:
                config["callbacks"] = [lf_handler]

            context = AgentContext(
                project_id=str(project_id),
                user_id=str(user_id),
                canary_token=canary_token,
            )
            input_msg = {
                "messages": [
                    HumanMessage(
                        content=content,
                        additional_kwargs={
                            "created_at": datetime.now(timezone.utc).isoformat()
                        },
                    )
                ]
            }

            try:
                async for mode, data in graph.astream(  # type: ignore[call-overload]
                    input_msg,
                    config,
                    stream_mode=["messages", "updates"],
                    context=context,
                ):
                    if cancel_event.is_set():
                        yield StreamEvent(type="error", data={"detail": "Cancelled"})
                        return

                    if mode == "messages":
                        msg_chunk, _metadata = data
                        if (
                            isinstance(msg_chunk, AIMessageChunk)
                            and isinstance(msg_chunk.content, str)
                            and msg_chunk.content
                        ):
                            full_response += msg_chunk.content

                            # Canary output check
                            if canary_token and check_canary_in_text(
                                full_response, canary_token
                            ):
                                logger.error(
                                    "canary token leaked in output",
                                    thread_id=str(thread_id),
                                )
                                self._record_canary_leak(
                                    span, full_response, canary_token
                                )
                                yield StreamEvent(
                                    type="security_block",
                                    data={"reason": "canary_leak"},
                                )
                                if span.trace_id:
                                    yield StreamEvent(
                                        type="trace_id",
                                        data={"trace_id": span.trace_id},
                                    )
                                return

                            yield StreamEvent(
                                type="text_chunk",
                                data={"content": msg_chunk.content},
                            )

                    elif mode == "updates":
                        for event in self._process_updates(data):
                            yield event

            except Exception as e:
                stream_error = True
                logger.warning(
                    "agent stream error",
                    thread_id=str(thread_id),
                    error=str(e),
                )
                yield StreamEvent(type="error", data={"detail": str(e)})
            finally:
                duration_ms = int((time.monotonic() - stream_start) * 1000)
                logger.info(
                    "agent completed",
                    thread_id=str(thread_id),
                    duration_ms=duration_ms,
                    status="error" if stream_error else "ok",
                )
                self._cancel_events.pop(thread_id, None)
                self._pending_cancels.discard(thread_id)

            span.update(output=full_response)

        if span.trace_id:
            yield StreamEvent(type="trace_id", data={"trace_id": span.trace_id})

    async def _get_checkpoint_messages(self, thread_id: uuid.UUID) -> list[Any]:
        """Get messages from checkpoint for guard context."""
        try:
            config = {"configurable": {"thread_id": str(thread_id)}}
            checkpoint = await self._checkpointer.aget_tuple(config)
            if checkpoint is None:
                return []
            return checkpoint.checkpoint.get("channel_values", {}).get("messages", [])
        except Exception:
            logger.warning(
                "checkpoint read for guard failed",
                thread_id=str(thread_id),
                exc_info=True,
            )
            return []

    async def _run_guard_with_observability(
        self,
        span: Any,
        content: str,
        history: list[Any],
        canary_token: str,
    ) -> Any:
        """Run SecurityGuard.check within a Langfuse guardrail observation."""
        assert self._security_guard is not None

        guard_cm = None
        guard_obs = None
        try:
            guard_cm = span.start_as_current_observation(
                as_type="guardrail", name="input-guard", input=content
            )
            guard_obs = guard_cm.__enter__()
        except Exception:
            guard_cm = None

        try:
            result = await self._security_guard.check(
                content,
                history=history,
                checkpoint="user_input",
                canary_token=canary_token,
            )

            if guard_obs is not None:
                try:
                    metadata: dict[str, Any] = {}
                    if result.reason:
                        metadata["block_reason"] = result.reason
                    if result.details and "degradation" in result.details.lower():
                        metadata["degraded"] = True

                    level = _VERDICT_TO_LEVEL.get(result.verdict, "DEFAULT")
                    if result.details and "degradation" in result.details.lower():
                        level = "WARNING"

                    guard_obs.update(
                        output={
                            "verdict": result.verdict.value,
                            "reason": result.reason,
                        },
                        metadata=metadata,
                        level=level,
                    )
                except Exception:
                    logger.warning("guard langfuse update failed", exc_info=True)

            return result
        finally:
            if guard_cm is not None:
                try:
                    guard_cm.__exit__(None, None, None)
                except Exception:
                    logger.warning("guard langfuse cleanup failed", exc_info=True)

    @staticmethod
    def _score_trace(span: Any, verdict: SecurityVerdict, reason: str | None) -> None:
        """Score trace with security verdict."""
        try:
            span.score_trace(
                name="security_verdict",
                value=verdict.value,
                data_type="CATEGORICAL",
                comment=reason,
            )
        except Exception:
            logger.warning("security score failed", exc_info=True)

    @staticmethod
    def _finalize_blocked_trace(
        span: Any, guard_result: Any, detection_layer: str
    ) -> None:
        """Update trace for a blocked request."""
        try:
            span.score_trace(
                name="security_verdict",
                value=SecurityVerdict.INJECTION.value,
                data_type="CATEGORICAL",
                comment=guard_result.reason,
            )
            span.update(
                output=BLOCKED_USER_MESSAGE,
                metadata={
                    "blocked": True,
                    "detection_layer": detection_layer,
                    "block_reason": guard_result.reason,
                },
                level="ERROR",
            )
        except Exception:
            logger.warning("blocked trace finalization failed", exc_info=True)

    @staticmethod
    def _record_canary_leak(span: Any, output: str, canary_token: str) -> None:
        """Record canary leak event + update trace."""
        try:
            span.create_event(
                name="canary-detected",
                input={"output_length": len(output)},
                output={"canary_token": canary_token},
                level="ERROR",
            )
            span.score_trace(
                name="security_verdict",
                value=SecurityVerdict.INJECTION.value,
                data_type="CATEGORICAL",
                comment="canary_leak",
            )
            span.update(
                output=CANARY_BLOCKED_USER_MESSAGE,
                metadata={
                    "blocked": True,
                    "detection_layer": "output_check",
                    "block_reason": "canary_leak",
                },
                level="ERROR",
            )
        except Exception:
            logger.warning("canary leak recording failed", exc_info=True)

    @staticmethod
    def _process_updates(data: dict[str, Any]) -> list[StreamEvent]:
        """Extract tool_start / tool_end / artifact_created events from updates."""
        events: list[StreamEvent] = []

        if "agent" in data:
            for msg in data["agent"].get("messages", []):
                if isinstance(msg, AIMessage) and msg.tool_calls:
                    for tc in msg.tool_calls:
                        events.append(
                            StreamEvent(
                                type="tool_start",
                                data={
                                    "tool": tc["name"],
                                    "call_id": tc["id"],
                                },
                            )
                        )

        if "tools" in data:
            for msg in data["tools"].get("messages", []):
                if isinstance(msg, ToolMessage):
                    events.append(
                        StreamEvent(
                            type="tool_end",
                            data={
                                "tool": msg.name or "",
                                "call_id": msg.tool_call_id,
                            },
                        )
                    )
                    if msg.name == "create_artifact" and msg.artifact is not None:
                        artifact = dict(msg.artifact)
                        artifact["artifact_type"] = artifact.pop("type", "")
                        events.append(
                            StreamEvent(
                                type="artifact_created",
                                data=artifact,
                            )
                        )

        return events

    async def get_last_ai_message_id(
        self,
        *,
        thread_id: uuid.UUID,
    ) -> str | None:
        """Get ID of the last AIMessage without tool_calls (final user-facing message)."""
        config = {"configurable": {"thread_id": str(thread_id)}}
        checkpoint = await self._checkpointer.aget_tuple(config)
        if checkpoint is None:
            return None
        messages = checkpoint.checkpoint.get("channel_values", {}).get("messages", [])
        for m in reversed(messages):
            if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
                return str(m.id)
        return None

    async def get_history(
        self,
        *,
        thread_id: uuid.UUID,
    ) -> list[Message]:
        config = {"configurable": {"thread_id": str(thread_id)}}
        checkpoint = await self._checkpointer.aget_tuple(config)
        if checkpoint is None:
            return []
        messages = checkpoint.checkpoint.get("channel_values", {}).get("messages", [])
        return [
            Message(
                id=str(m.id),
                role="user" if isinstance(m, HumanMessage) else "assistant",
                content=m.content if isinstance(m.content, str) else "",
                created_at=_parse_created_at(m.additional_kwargs.get("created_at")),
            )
            for m in messages
            if isinstance(m, (HumanMessage, AIMessage))
            and not getattr(m, "tool_calls", None)
        ]

    async def cancel(self, *, thread_id: uuid.UUID) -> bool:
        event = self._cancel_events.get(thread_id)
        if event is None:
            self._pending_cancels.add(thread_id)
            return True
        event.set()
        return True
