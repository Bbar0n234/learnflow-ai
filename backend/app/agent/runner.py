from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.config import ErrorMessagesConfig, ResolvedModelConfig
from app.agent.error_mapper import normalize_error_message
from app.agent.graph import AgentContext
from app.agent.graph_factory import GraphFactory
from app.agent.security.canary import generate_canary_token
from app.agent.security.guard import SecurityGuard
from app.agent.security.types import (
    VERDICT_TO_LEVEL,  # noqa: F401  # re-export for tests/legacy imports
    Checkpoint,
    DetectionLayer,
    GuardResult,
    SecurityMessages,
    Verdict,
    direction_of,
)
from app.repositories.settings import SettingsRepository
from app.repositories.thread_view import ThreadViewRepository
from app.services.agent_runner import Message, StreamEvent
from app.services.model_config_resolver import ModelConfigResolver

logger = structlog.get_logger()


class _NoOpSpan:
    trace_id = None
    id = None

    def update(self, **kwargs: Any) -> None:
        pass

    def score_trace(self, **kwargs: Any) -> None:
        pass


@dataclass(frozen=True)
class _InGraphSecurityHit:
    checkpoint: Checkpoint
    detection_layer: DetectionLayer | None
    reason: str


@contextmanager
def _langfuse_observation(
    content: str,
    user_id: uuid.UUID,
    thread_id: uuid.UUID,
    project_id: uuid.UUID,
) -> Any:
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
        security_messages: SecurityMessages,
        error_messages: ErrorMessagesConfig,
        tool_resolver: Any | None = None,
        security_guard: SecurityGuard | None = None,
        canary_secret: str = "",
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._graph_factory = graph_factory
        self._model_resolver = model_resolver
        self._checkpointer = checkpointer
        self._security_messages = security_messages
        self._error_messages = error_messages
        self._tool_resolver = tool_resolver
        self._security_guard = security_guard
        self._canary_secret = canary_secret
        self._session_factory = session_factory
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

        user_installed_tool_names = frozenset(
            getattr(t, "name", "") for t in extra_tools if getattr(t, "name", None)
        )

        graph = self._graph_factory.build(model_config, extra_tools=extra_tools)

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
        last_message_id: str | None = None
        injection_emitted = False
        chunks_processed = 0

        with _langfuse_observation(content, user_id, thread_id, project_id) as (
            span,
            lf_handler,
        ):
            # --- Pre-graph security check (USER_INPUT) ---
            guard_result: GuardResult | None = None
            if self._security_guard is not None:
                history = await self._get_checkpoint_messages(thread_id)
                guard_result = await self._security_guard.check(
                    content,
                    Checkpoint.USER_INPUT,
                    history=history,
                    canary_token=canary_token,
                )

                if guard_result.verdict == Verdict.INJECTION:
                    self._finalize_blocked_trace(span, guard_result)
                    await self._persist_user_input_block(
                        graph,
                        thread_id,
                        content,
                        guard_result,
                    )
                    await self._mark_security_blocked(thread_id)
                    yield StreamEvent(
                        type="security_block",
                        data={
                            "reason": (
                                guard_result.detection_layer.value
                                if guard_result.detection_layer
                                else "prompt_injection"
                            )
                        },
                    )
                    if span.trace_id:
                        yield StreamEvent(
                            type="trace_id",
                            data={"trace_id": span.trace_id},
                        )
                    return

                if guard_result.verdict == Verdict.SUSPICIOUS:
                    logger.warning(
                        "suspicious input detected, proceeding",
                        thread_id=str(thread_id),
                        detection_layer=(
                            guard_result.detection_layer.value
                            if guard_result.detection_layer
                            else None
                        ),
                    )

            if guard_result is not None:
                self._score_trace(
                    span,
                    guard_result.verdict,
                    guard_result.detection_layer,
                )

            config: dict[str, Any] = {"configurable": {"thread_id": str(thread_id)}}
            if lf_handler:
                config["callbacks"] = [lf_handler]

            context = AgentContext(
                project_id=str(project_id),
                user_id=str(user_id),
                canary_token=canary_token,
                user_installed_tool_names=user_installed_tool_names,
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
                        yield StreamEvent(
                            type="error",
                            data={
                                "detail": normalize_error_message(
                                    asyncio.CancelledError(), self._error_messages
                                )
                            },
                        )
                        return

                    if mode == "messages":
                        msg_chunk, _metadata = data
                        if (
                            isinstance(msg_chunk, AIMessageChunk)
                            and isinstance(msg_chunk.content, str)
                            and msg_chunk.content
                        ):
                            if msg_chunk.id is not None:
                                last_message_id = str(msg_chunk.id)
                            full_response += msg_chunk.content
                            chunks_processed += 1

                            # Mid-stream tail-only deterministic guard (skip_classifier=True).
                            # observe=False: per-chunk observations flood traces; a single
                            # retrospective observation is emitted only on INJECTION below.
                            tail_len = self._tail_window_len(canary_token)
                            tail = full_response[-(tail_len + len(msg_chunk.content)) :]
                            mid_result = await self._maybe_guard(
                                tail,
                                Checkpoint.FINAL_OUTPUT,
                                canary_token=canary_token,
                                skip_classifier=True,
                                observe=False,
                            )
                            if (
                                mid_result is not None
                                and mid_result.verdict == Verdict.INJECTION
                            ):
                                injection_emitted = True
                                self._record_mid_stream_hit_observation(
                                    thread_id=thread_id,
                                    full_response=full_response,
                                    tail=tail,
                                    result=mid_result,
                                    chunks_processed=chunks_processed,
                                )
                                await self._handle_final_output_injection(
                                    graph,
                                    config,
                                    thread_id,
                                    full_response,
                                    mid_result,
                                    last_message_id,
                                )
                                self._finalize_blocked_trace(span, mid_result)
                                yield StreamEvent(
                                    type="security_block",
                                    data={
                                        "reason": (
                                            mid_result.detection_layer.value
                                            if mid_result.detection_layer
                                            else "final_output"
                                        )
                                    },
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
                yield StreamEvent(
                    type="error",
                    data={"detail": normalize_error_message(e, self._error_messages)},
                )
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

            # --- End-of-stream FINAL_OUTPUT classifier ---
            if (
                not stream_error
                and not injection_emitted
                and self._security_guard is not None
                and full_response
            ):
                yield StreamEvent(type="final_output_review_started", data={})
                final_result = await self._security_guard.check(
                    full_response,
                    Checkpoint.FINAL_OUTPUT,
                    canary_token=canary_token,
                )
                if final_result.verdict == Verdict.INJECTION:
                    injection_emitted = True
                    await self._handle_final_output_injection(
                        graph,
                        config,
                        thread_id,
                        full_response,
                        final_result,
                        last_message_id,
                    )
                    self._finalize_blocked_trace(span, final_result)
                    yield StreamEvent(
                        type="security_block",
                        data={
                            "reason": (
                                final_result.detection_layer.value
                                if final_result.detection_layer
                                else "final_output"
                            )
                        },
                    )
                    if span.trace_id:
                        yield StreamEvent(
                            type="trace_id", data={"trace_id": span.trace_id}
                        )
                    return

                yield StreamEvent(type="final_output_review_complete", data={})

            # --- Post-stream in-graph INJECTION inspection (TOOL_CALL_ARG / TOOL_RESULT) ---
            if not injection_emitted and not stream_error:
                hit = await self._inspect_in_graph_injection(thread_id, config)
                if hit is not None:
                    await self._mark_security_blocked(thread_id)
                    injection_emitted = True
                    result = GuardResult(
                        verdict=Verdict.INJECTION,
                        checkpoint=hit.checkpoint,
                        direction=direction_of(hit.checkpoint),
                        detection_layer=hit.detection_layer,
                        details={"reason": "in_graph_security_redaction"},
                    )
                    self._finalize_blocked_trace(span, result)
                    yield StreamEvent(
                        type="security_block", data={"reason": hit.reason}
                    )

            if not injection_emitted:
                span.update(output=full_response)

        if span.trace_id:
            yield StreamEvent(type="trace_id", data={"trace_id": span.trace_id})

    @staticmethod
    def _tail_window_len(canary_token: str) -> int:
        return max(len(canary_token) if canary_token else 0, 64)

    async def _maybe_guard(
        self,
        content: str,
        checkpoint: Checkpoint,
        *,
        canary_token: str,
        skip_classifier: bool,
        observe: bool = True,
    ) -> GuardResult | None:
        if self._security_guard is None:
            return None
        return await self._security_guard.check(
            content,
            checkpoint,
            canary_token=canary_token,
            skip_classifier=skip_classifier,
            observe=observe,
        )

    @staticmethod
    def _record_mid_stream_hit_observation(
        *,
        thread_id: uuid.UUID,
        full_response: str,
        tail: str,
        result: GuardResult,
        chunks_processed: int,
    ) -> None:
        """Emit a single retrospective guardrail observation for a mid-stream hit.

        Mid-stream checks run per-chunk with ``observe=False`` to keep traces
        readable; when a hit fires we record one ``guard-final_output`` observation
        with the full context (accumulated response, detected tail, detector
        layer/details, chunk counter).
        """
        try:
            from langfuse import get_client

            from app.infra.langfuse import langfuse_enabled

            if not langfuse_enabled:
                return
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

    async def _handle_final_output_injection(
        self,
        graph: Any,
        config: dict[str, Any],
        thread_id: uuid.UUID,
        full_response: str,
        result: GuardResult,
        last_message_id: str | None,
    ) -> None:
        """Redact the assistant message via replace-by-id + mark thread blocked."""
        try:
            redacted = AIMessage(
                id=last_message_id,
                content=self._security_messages.redacted_user_facing,
                additional_kwargs={
                    "security_redacted": True,
                    "original_detection_layer": (
                        result.detection_layer.value
                        if result.detection_layer
                        else DetectionLayer.LLM_CLASSIFIER.value
                    ),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            await graph.aupdate_state(config, {"messages": [redacted]}, as_node="agent")
        except Exception:
            logger.warning(
                "final_output aupdate_state failed",
                thread_id=str(thread_id),
                exc_info=True,
            )
        await self._mark_security_blocked(thread_id)
        logger.warning(
            "final output blocked",
            security_event=True,
            checkpoint=Checkpoint.FINAL_OUTPUT.value,
            verdict=Verdict.INJECTION.value,
            identifiers={"thread_id": str(thread_id)},
            metadata={
                "detection_layer": (
                    result.detection_layer.value if result.detection_layer else None
                ),
                "response_length": len(full_response),
            },
        )

    async def _persist_user_input_block(
        self,
        graph: Any,
        thread_id: uuid.UUID,
        content: str,
        result: GuardResult,
    ) -> None:
        """Write the blocked HumanMessage + redacted AIMessage placeholder to checkpointer.

        The graph never runs for USER_INPUT injections, so messages would otherwise
        not appear in history. We replay them as if `agent` had produced them:
        the user sees their original prompt and the placeholder when reopening the chat.
        """
        config: dict[str, Any] = {"configurable": {"thread_id": str(thread_id)}}
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            human = HumanMessage(
                content=content,
                additional_kwargs={"created_at": now_iso},
            )
            placeholder = AIMessage(
                content=self._security_messages.redacted_user_facing,
                additional_kwargs={
                    "security_redacted": True,
                    "original_detection_layer": (
                        result.detection_layer.value
                        if result.detection_layer
                        else Checkpoint.USER_INPUT.value
                    ),
                    "created_at": now_iso,
                },
            )
            await graph.aupdate_state(
                config, {"messages": [human, placeholder]}, as_node="agent"
            )
        except Exception:
            logger.warning(
                "user_input block persist failed",
                thread_id=str(thread_id),
                exc_info=True,
            )

    async def _mark_security_blocked(self, thread_id: uuid.UUID) -> None:
        if self._session_factory is None:
            return
        try:
            async with self._session_factory() as session, session.begin():
                repo = ThreadViewRepository(session)
                await repo.mark_security_blocked(thread_id)
        except Exception:
            logger.warning(
                "mark_security_blocked failed",
                thread_id=str(thread_id),
                exc_info=True,
            )

    async def _inspect_in_graph_injection(
        self, thread_id: uuid.UUID, config: dict[str, Any]
    ) -> _InGraphSecurityHit | None:
        """Check the latest turn for an in-graph redaction flag."""
        try:
            checkpoint = await self._checkpointer.aget_tuple(config)
            if checkpoint is None:
                return None
            messages = checkpoint.checkpoint.get("channel_values", {}).get(
                "messages", []
            )
            for m in reversed(messages):
                if isinstance(m, (AIMessage, ToolMessage)) and m.additional_kwargs.get(
                    "security_redacted"
                ):
                    layer = m.additional_kwargs.get("original_detection_layer")
                    if layer is None:
                        logger.warning(
                            "security_redacted set without original_detection_layer",
                            thread_id=str(thread_id),
                        )
                        layer = "unknown"
                    try:
                        detection_layer = DetectionLayer(layer)
                    except ValueError:
                        detection_layer = None
                    checkpoint = (
                        Checkpoint.TOOL_RESULT
                        if isinstance(m, ToolMessage)
                        else Checkpoint.TOOL_CALL_ARG
                    )
                    return _InGraphSecurityHit(
                        checkpoint=checkpoint,
                        detection_layer=detection_layer,
                        reason=layer,
                    )
                # Stop at the previous user message to bound scan.
                if isinstance(m, HumanMessage):
                    break
        except Exception:
            logger.warning(
                "post-stream state inspection failed",
                thread_id=str(thread_id),
                exc_info=True,
            )
        return None

    async def _get_checkpoint_messages(self, thread_id: uuid.UUID) -> list[Any]:
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

    @staticmethod
    def _score_trace(
        span: Any,
        verdict: Verdict,
        detection_layer: DetectionLayer | None,
    ) -> None:
        try:
            span.score_trace(
                name="security_verdict",
                value=verdict.value,
                data_type="CATEGORICAL",
                comment=detection_layer.value if detection_layer else None,
            )
        except Exception:
            logger.warning("security score failed", exc_info=True)

    def _finalize_blocked_trace(self, span: Any, guard_result: GuardResult) -> None:
        try:
            span.score_trace(
                name="security_verdict",
                value=Verdict.INJECTION.value,
                data_type="CATEGORICAL",
                comment=(
                    guard_result.detection_layer.value
                    if guard_result.detection_layer
                    else None
                ),
            )
            span.update(
                output=self._security_messages.redacted_user_facing,
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

    @staticmethod
    def _process_updates(data: dict[str, Any]) -> list[StreamEvent]:
        events: list[StreamEvent] = []

        if "agent" in data:
            for msg in data["agent"].get("messages", []):
                if isinstance(msg, AIMessage) and msg.tool_calls:
                    for tc in msg.tool_calls:
                        events.append(
                            StreamEvent(
                                type="tool_start",
                                data={"tool": tc["name"], "call_id": tc["id"]},
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
        result: list[Message] = []
        for m in messages:
            if not isinstance(m, (HumanMessage, AIMessage)):
                continue
            if getattr(m, "tool_calls", None):
                continue
            redacted = bool(m.additional_kwargs.get("security_redacted"))
            content = (
                self._security_messages.redacted_user_facing
                if redacted
                else (m.content if isinstance(m.content, str) else "")
            )
            result.append(
                Message(
                    id=str(m.id),
                    role="user" if isinstance(m, HumanMessage) else "assistant",
                    content=content,
                    created_at=_parse_created_at(m.additional_kwargs.get("created_at")),
                    redacted=redacted,
                )
            )
        return result

    async def cancel(self, *, thread_id: uuid.UUID) -> bool:
        event = self._cancel_events.get(thread_id)
        if event is None:
            self._pending_cancels.add(thread_id)
            return True
        event.set()
        return True
