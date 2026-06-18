from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import structlog
from langchain_core.messages import AIMessageChunk, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.checkpoint_history import CheckpointHistory
from app.agent.config import ErrorMessagesConfig, ResolvedModelConfig
from app.agent.error_mapper import normalize_error_message
from app.agent.graph import AgentContext
from app.agent.graph_factory import GraphFactory
from app.agent.runtime_security import RuntimeSecurityEnforcer
from app.agent.security.canary import generate_canary_token
from app.agent.stream_events import StreamEventMapper
from app.agent.tracing import AgentRunTracer
from app.repositories.settings import SettingsRepository
from app.services.agent_runner import Message, StreamEvent
from app.services.model_config_resolver import ModelConfigResolver

logger = structlog.get_logger()


class LangGraphAgentRunner:
    """Orchestrates the agent stream and implements the AgentRunner contract.

    Side concerns are delegated to collaborators: ``RuntimeSecurityEnforcer``
    (guard checkpoints + redaction), ``AgentRunTracer`` (Langfuse spans),
    ``CheckpointHistory`` (checkpointer reads/mapping), ``StreamEventMapper``
    (graph updates → SSE events).
    """

    def __init__(
        self,
        graph_factory: GraphFactory,
        model_resolver: ModelConfigResolver,
        tracer: AgentRunTracer,
        enforcer: RuntimeSecurityEnforcer,
        history: CheckpointHistory,
        error_messages: ErrorMessagesConfig,
        *,
        event_mapper: StreamEventMapper | None = None,
        tool_resolver: Any | None = None,
        canary_secret: str = "",
    ) -> None:
        self._graph_factory = graph_factory
        self._model_resolver = model_resolver
        self._tracer = tracer
        self._enforcer = enforcer
        self._history = history
        self._error_messages = error_messages
        self._event_mapper = event_mapper or StreamEventMapper()
        self._tool_resolver = tool_resolver
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

        if model_config is None and session is not None:
            settings_repo = SettingsRepository(session)
            model_config = await self._model_resolver.resolve(
                settings_repo, user_id, project_id, thread_id
            )
        if model_config is None:
            model_config = self._model_resolver.default()

        extra_tools = await self._resolve_user_tools(user_id, project_id, thread_id)
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

        with self._tracer.run(
            content=content,
            user_id=user_id,
            thread_id=thread_id,
            project_id=project_id,
        ) as span:
            # --- Pre-graph security check (USER_INPUT) ---
            guard_result = await self._enforcer.check_user_input(
                thread_id=thread_id,
                content=content,
                canary_token=canary_token,
                graph=graph,
                session=session,
            )
            if guard_result is not None and guard_result.verdict.value == "INJECTION":
                span.finalize_blocked(guard_result)
                yield StreamEvent(
                    type="security_block",
                    data={"reason": RuntimeSecurityEnforcer.block_reason(guard_result)},
                )
                for _ev in self._trace_id_event(span):
                    yield _ev
                return
            if guard_result is not None:
                span.score(guard_result.verdict, guard_result.detection_layer)

            config: dict[str, Any] = {"configurable": {"thread_id": str(thread_id)}}
            if span.callback_handler:
                config["callbacks"] = [span.callback_handler]

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
                        additional_kwargs={"created_at": datetime.now(UTC).isoformat()},
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
                        if not (
                            isinstance(msg_chunk, AIMessageChunk)
                            and isinstance(msg_chunk.content, str)
                            and msg_chunk.content
                        ):
                            continue
                        if msg_chunk.id is not None:
                            last_message_id = str(msg_chunk.id)
                        full_response += msg_chunk.content
                        chunks_processed += 1

                        tail_len = RuntimeSecurityEnforcer.tail_window_len(canary_token)
                        tail = full_response[-(tail_len + len(msg_chunk.content)) :]
                        mid_outcome = await self._enforcer.check_mid_stream(
                            thread_id=thread_id,
                            full_response=full_response,
                            tail=tail,
                            canary_token=canary_token,
                            graph=graph,
                            config=config,
                            last_message_id=last_message_id,
                            session=session,
                        )
                        if mid_outcome is not None:
                            injection_emitted = True
                            span.record_mid_stream_hit(
                                thread_id=thread_id,
                                full_response=full_response,
                                tail=tail,
                                result=mid_outcome.result,
                                chunks_processed=chunks_processed,
                            )
                            span.finalize_blocked(mid_outcome.result)
                            yield StreamEvent(
                                type="security_block",
                                data={"reason": mid_outcome.reason},
                            )
                            for _ev in self._trace_id_event(span):
                                yield _ev
                            return

                        yield StreamEvent(
                            type="text_chunk", data={"content": msg_chunk.content}
                        )

                    elif mode == "updates":
                        for event in self._event_mapper.updates(data):
                            yield event

            except Exception as e:
                stream_error = True
                logger.error(
                    "agent stream error",
                    thread_id=str(thread_id),
                    error_type=type(e).__name__,
                    exc_info=e,
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
            if not stream_error and not injection_emitted and full_response:
                yield StreamEvent(type="final_output_review_started", data={})
                final_outcome = await self._enforcer.check_final_output(
                    thread_id=thread_id,
                    full_response=full_response,
                    canary_token=canary_token,
                    graph=graph,
                    config=config,
                    last_message_id=last_message_id,
                    session=session,
                )
                if final_outcome is not None:
                    injection_emitted = True
                    span.finalize_blocked(final_outcome.result)
                    yield StreamEvent(
                        type="security_block",
                        data={"reason": final_outcome.reason},
                    )
                    for _ev in self._trace_id_event(span):
                        yield _ev
                    return
                yield StreamEvent(type="final_output_review_complete", data={})

            # --- Post-stream in-graph INJECTION inspection ---
            if not injection_emitted and not stream_error:
                in_graph = await self._enforcer.inspect_in_graph(
                    thread_id=thread_id, session=session
                )
                if in_graph is not None:
                    injection_emitted = True
                    span.finalize_blocked(in_graph.result)
                    yield StreamEvent(
                        type="security_block", data={"reason": in_graph.reason}
                    )

            if not injection_emitted:
                span.set_output(full_response)

        for _ev in self._trace_id_event(span):
            yield _ev

    async def _resolve_user_tools(
        self, user_id: uuid.UUID, project_id: uuid.UUID, thread_id: uuid.UUID
    ) -> list[Any]:
        if self._tool_resolver is None:
            return []
        try:
            return await self._tool_resolver.resolve(user_id, project_id, thread_id)
        except Exception:
            logger.warning(
                "user mcp tools resolution failed, using global tools only",
                exc_info=True,
            )
            return []

    @staticmethod
    def _trace_id_event(span: Any) -> list[StreamEvent]:
        if span.trace_id:
            return [StreamEvent(type="trace_id", data={"trace_id": span.trace_id})]
        return []

    async def get_last_ai_message_id(self, *, thread_id: uuid.UUID) -> str | None:
        return await self._history.last_ai_message_id(thread_id)

    async def get_history(self, *, thread_id: uuid.UUID) -> list[Message]:
        return await self._history.history(thread_id)

    async def cancel(self, *, thread_id: uuid.UUID) -> bool:
        event = self._cancel_events.get(thread_id)
        if event is None:
            self._pending_cancels.add(thread_id)
            return True
        event.set()
        return True
