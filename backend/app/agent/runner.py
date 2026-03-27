from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import structlog
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

from app.agent.graph import AgentContext
from app.services.agent_runner import Message, StreamEvent

logger = structlog.get_logger()


def _parse_created_at(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


class LangGraphAgentRunner:
    def __init__(self, graph: Any) -> None:
        self._graph = graph
        self._cancel_events: dict[uuid.UUID, asyncio.Event] = {}
        self._pending_cancels: set[uuid.UUID] = set()

    async def stream(
        self,
        *,
        thread_id: uuid.UUID,
        content: str,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> AsyncIterator[StreamEvent]:
        cancel_event = asyncio.Event()
        self._cancel_events[thread_id] = cancel_event
        if thread_id in self._pending_cancels:
            self._pending_cancels.discard(thread_id)
            cancel_event.set()

        logger.info(
            "agent invoked",
            thread_id=str(thread_id),
            project_id=str(project_id),
        )
        stream_start = time.monotonic()
        stream_error = False

        config = {"configurable": {"thread_id": str(thread_id)}}
        context = AgentContext(
            project_id=str(project_id),
            user_id=str(user_id),
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
            async for mode, data in self._graph.astream(
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

    @staticmethod
    def _process_updates(data: dict[str, Any]) -> list[StreamEvent]:
        """Extract tool_start / tool_end / artifact_created events from updates."""
        events: list[StreamEvent] = []

        # Agent node finished — check for tool_calls
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

        # Tools node finished — emit tool_end (+ artifact_created)
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
                    # artifact_created for create_artifact tool
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
        state = await self._graph.aget_state(config)
        if not state.values:
            return None
        for m in reversed(state.values.get("messages", [])):
            if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
                return str(m.id)
        return None

    async def get_history(
        self,
        *,
        thread_id: uuid.UUID,
    ) -> list[Message]:
        config = {"configurable": {"thread_id": str(thread_id)}}
        state = await self._graph.aget_state(config)
        if not state.values:
            return []
        messages = state.values.get("messages", [])
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
