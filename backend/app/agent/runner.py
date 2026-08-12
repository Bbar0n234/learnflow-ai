from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any

import structlog
from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.agent_events import DOMAIN_AGENT_EVENT_KINDS
from app.agent.checkpoint_history import CheckpointHistory
from app.agent.config import (
    ErrorMessagesConfig,
    PromptFragmentsConfig,
    ResolvedModelConfig,
)
from app.agent.error_mapper import normalize_error_message
from app.agent.graph import AgentContext
from app.agent.graph_factory import GraphFactory
from app.agent.heartbeat import HeartbeatPacer
from app.agent.prompt_builder import render_attachment_note
from app.agent.runtime_security import RuntimeSecurityEnforcer
from app.agent.security.canary import generate_canary_token
from app.agent.stream_events import StreamEventMapper, TokenChunkMapper
from app.agent.subagents import SUBAGENT_TAG
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
    (graph updates → SSE events, one fresh instance per run — see
    ``_event_mapper_factory``), ``TokenChunkMapper`` (messages-channel
    chunks → SSE events, one fresh instance per run — see
    ``_token_mapper_factory``), ``HeartbeatPacer`` (silence heartbeats +
    responsive cancellation).
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
        event_mapper_factory: Callable[[], StreamEventMapper] | None = None,
        heartbeat_pacer: HeartbeatPacer | None = None,
        token_mapper_factory: Callable[[], TokenChunkMapper] | None = None,
        tool_resolver: Any | None = None,
        canary_secret: str = "",
        checkpointer: AsyncPostgresSaver | None = None,
        prompt_fragments: PromptFragmentsConfig | None = None,
    ) -> None:
        self._graph_factory = graph_factory
        self._model_resolver = model_resolver
        self._tracer = tracer
        self._enforcer = enforcer
        self._history = history
        self._error_messages = error_messages
        # Only `headers.attachment_note` is read off this — an empty default
        # config still renders a note (`render_attachment_note`'s own
        # built-in fallback text), so a caller that doesn't pass one (tests
        # constructing this class directly) degrades instead of breaking.
        self._prompt_fragments = prompt_fragments or PromptFragmentsConfig()
        self._heartbeat_pacer = heartbeat_pacer or HeartbeatPacer()
        # Factories, not shared instances: both mappers accumulate per-run
        # state (``TokenChunkMapper`` — tool-call chunk assembly;
        # ``StreamEventMapper`` — announced-but-unresolved call ids for
        # ``tool_call_cancelled``), so each ``stream()`` call must get its own
        # (conventions.md § module state — no shared/module-level mutable
        # state across concurrent runs).
        self._event_mapper_factory = event_mapper_factory or StreamEventMapper
        self._token_mapper_factory = token_mapper_factory or TokenChunkMapper
        self._tool_resolver = tool_resolver
        self._canary_secret = canary_secret
        self._checkpointer = checkpointer
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
        attachments: list[str] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        cancel_event = asyncio.Event()
        self._cancel_events[thread_id] = cancel_event
        if thread_id in self._pending_cancels:
            self._pending_cancels.discard(thread_id)
            cancel_event.set()

        async def _run_turn() -> AsyncGenerator[StreamEvent, None]:
            """One full agent turn: setup, graph run, security reviews.

            Runs *inside* the heartbeat pacer (see below) — the pacer emits
            ``heartbeat`` for any silence here (setup included) and detects
            cancellation on its own timer, so this generator does not need to
            poll ``cancel_event`` itself except at the one point (the astream
            loop) where a per-iteration check is cheap and catches a
            cancellation faster than the heartbeat interval would.
            """
            nonlocal model_config
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
                canary_token = generate_canary_token(
                    str(thread_id), self._canary_secret
                )

            logger.info(
                "agent invoked",
                thread_id=str(thread_id),
                project_id=str(project_id),
                model=model_config.model,
                model_source=model_config.source,
            )
            logger.debug(
                "user message",
                thread_id=str(thread_id),
                preview=content[:500],
                length=len(content),
            )
            stream_start = time.monotonic()
            stream_error = False
            client_disconnected = False
            full_response = ""
            token_mapper = self._token_mapper_factory()
            event_mapper = self._event_mapper_factory()
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
                if (
                    guard_result is not None
                    and guard_result.verdict.value == "INJECTION"
                ):
                    span.finalize_blocked(guard_result)
                    yield StreamEvent(type="security_block", data={})
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
                # Attachment paths turn into an in-model note appended to the
                # stored `HumanMessage.content` (the backend is the only side
                # that knows the canonical `uploads/…` path, design-brief §
                # «Вложения пользователя») — `additional_kwargs` keeps the
                # clean text and the {path, title} list separately so the
                # history endpoint can serve both without re-parsing the
                # note back out of `content`.
                attachment_refs = [
                    {"path": path, "title": PurePosixPath(path).name}
                    for path in (attachments or [])
                ]
                model_text = content
                human_kwargs: dict[str, Any] = {
                    "created_at": datetime.now(UTC).isoformat()
                }
                if attachment_refs:
                    note = render_attachment_note(
                        self._prompt_fragments, attachment_refs
                    )
                    model_text = f"{content}\n\n{note}" if content else note
                    human_kwargs["text"] = content
                    human_kwargs["attachments"] = attachment_refs

                input_msg = {
                    "messages": [
                        HumanMessage(
                            content=model_text,
                            additional_kwargs=human_kwargs,
                        )
                    ]
                }

                try:
                    async for mode, data in graph.astream(  # type: ignore[call-overload]
                        input_msg,
                        config,
                        stream_mode=["messages", "updates", "custom"],
                        context=context,
                    ):
                        if cancel_event.is_set():
                            yield StreamEvent(type="cancelled", data={})
                            return

                        if mode == "messages":
                            msg_chunk, chunk_metadata = data
                            if chunk_metadata and SUBAGENT_TAG in (
                                chunk_metadata.get("tags") or ()
                            ):
                                # Subagent LLM tokens: dropped before full_response
                                # accumulation and canary/mid-stream checks (design-brief
                                # § "Стриминг: изоляция токенов субагента"). cancel_event
                                # is still checked every iteration at the top of this
                                # loop, so cancellation stays responsive during a
                                # subagent run; Langfuse callbacks are untouched — only
                                # this stream-loop projection is filtered.
                                continue
                            if not isinstance(msg_chunk, AIMessageChunk):
                                continue
                            if msg_chunk.id is not None:
                                last_message_id = str(msg_chunk.id)

                            # ``token_mapper`` splits the raw chunk into its
                            # text/reasoning/tool-call-assembly events. Only
                            # ``text_chunk`` feeds full_response and the
                            # canary/mid-stream guard — reasoning and
                            # tool_call_* stream live without guard
                            # involvement (design-brief § "Контракт SSE v2":
                            # a conscious boundary, not an oversight).
                            blocked = False
                            for token_event in token_mapper.map_chunk(msg_chunk):
                                if token_event.type == "text_chunk":
                                    token_text = token_event.data["content"]
                                    full_response += token_text
                                    chunks_processed += 1

                                    tail_len = RuntimeSecurityEnforcer.tail_window_len(
                                        canary_token
                                    )
                                    tail = full_response[
                                        -(tail_len + len(token_text)) :
                                    ]
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
                                            type="security_block", data={}
                                        )
                                        for _ev in self._trace_id_event(span):
                                            yield _ev
                                        blocked = True
                                        break

                                if token_event.type == "tool_call_started":
                                    # Recorded so the updates-channel mapper can
                                    # later tell a guard cut (empty tool_calls,
                                    # ``security_redacted``) apart from a plain
                                    # no-tool-calls turn, and knows which
                                    # ``call_id``s to report as
                                    # ``tool_call_cancelled`` — the redacted
                                    # payload itself no longer carries them.
                                    event_mapper.note_call_announced(
                                        token_event.data["call_id"]
                                    )

                                yield token_event

                            if blocked:
                                return

                        elif mode == "updates":
                            for event in event_mapper.updates(data):
                                yield event

                        elif mode == "custom" and isinstance(data, dict):
                            custom_type = data.get("type")
                            if custom_type in DOMAIN_AGENT_EVENT_KINDS:
                                # Our own tools' domain writes
                                # (`agent_events.emit_agent_event`) — wrapped
                                # into the wire's `agent_event {kind, payload,
                                # parent_call_id?}` (design-brief § "Контракт
                                # SSE v2").
                                agent_event_data: dict[str, Any] = {
                                    "kind": custom_type,
                                    "payload": data.get("payload", {}),
                                }
                                parent_call_id = data.get("parent_call_id")
                                if parent_call_id is not None:
                                    agent_event_data["parent_call_id"] = parent_call_id
                                yield StreamEvent(
                                    type="agent_event", data=agent_event_data
                                )
                            elif custom_type is not None:
                                # Lifecycle types written straight to the custom
                                # channel — already shaped like the final wire
                                # event's data, passed through unchanged rather
                                # than wrapped in agent_event. Two sources: the
                                # tools node's own per-call reporter
                                # (`stream_events.make_tool_result_reporter`,
                                # `tool_result` + `artifact_created`/
                                # `artifact_updated`), and lifecycle types
                                # (tool_call_started / tool_call_args /
                                # tool_result) the subagent-step wrapper writes
                                # for a nested call — on the wire these must be
                                # "те же типы, что у основного агента"
                                # (design-brief § "Вложенность субагента").
                                yield StreamEvent(
                                    type=custom_type, data=data.get("data", {})
                                )

                except (asyncio.CancelledError, GeneratorExit):
                    # Two distinct causes land here: a real client disconnect
                    # (cancel_event unset) and the heartbeat pacer interrupting
                    # a blocked tool call after detecting our own cancel_event
                    # (event-map.md попутная находка №3) — the flag picked for
                    # the completion log below distinguishes them.
                    client_disconnected = not cancel_event.is_set()
                    raise
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
                        data={
                            "detail": normalize_error_message(e, self._error_messages)
                        },
                    )
                finally:
                    duration_ms = int((time.monotonic() - stream_start) * 1000)
                    if client_disconnected:
                        status = "client_disconnected"
                    elif stream_error:
                        status = "error"
                    elif cancel_event.is_set():
                        status = "cancelled"
                    else:
                        status = "ok"
                    logger.info(
                        "agent completed",
                        thread_id=str(thread_id),
                        duration_ms=duration_ms,
                        status=status,
                    )

                # --- End-of-stream FINAL_OUTPUT classifier ---
                if not stream_error and not injection_emitted and full_response:
                    # review_events: при выключенной LLM-защите (enforcer без
                    # guard) проверка — no-op, и пара review-событий не эмитится
                    # вовсе — индикатор «проверяю ответ» не врёт пользователю.
                    review_events = self._enforcer.active
                    if review_events:
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
                        yield StreamEvent(type="security_block", data={})
                        for _ev in self._trace_id_event(span):
                            yield _ev
                        return
                    if review_events:
                        yield StreamEvent(type="final_output_review_complete", data={})

                # --- Post-stream in-graph INJECTION inspection ---
                if not injection_emitted and not stream_error:
                    in_graph = await self._enforcer.inspect_in_graph(
                        thread_id=thread_id, session=session
                    )
                    if in_graph is not None:
                        injection_emitted = True
                        span.finalize_blocked(in_graph.result)
                        yield StreamEvent(type="security_block", data={})

                if not injection_emitted:
                    logger.debug(
                        "agent reply",
                        thread_id=str(thread_id),
                        preview=full_response[:500],
                        length=len(full_response),
                    )
                    span.set_output(full_response)

            for _ev in self._trace_id_event(span):
                yield _ev

        try:
            yield StreamEvent(type="stream_started", data={})
            async with contextlib.aclosing(
                self._heartbeat_pacer.pace(_run_turn(), cancel_event)
            ) as paced:
                async for event in paced:
                    yield event
        finally:
            self._cancel_events.pop(thread_id, None)
            self._pending_cancels.discard(thread_id)

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

    async def delete_thread(self, *, thread_id: uuid.UUID) -> None:
        """Delete LangGraph checkpoints for a thread. Best-effort — the
        caller (``ChatService.delete_chat``) treats failures as a barrier: the
        DB-side chat row is already committed by then, and orphaned
        checkpoints degrade the same way pre-existing garbage does."""
        if self._checkpointer is None:
            logger.warning(
                "checkpointer not configured, skipping thread deletion",
                thread_id=str(thread_id),
            )
            return
        await self._checkpointer.adelete_thread(str(thread_id))
