from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

from app.agent.graph import AgentContext
from app.services.agent_runner import Message, StreamEvent


class LangGraphAgentRunner:
    def __init__(self, graph: Any) -> None:
        self._graph = graph

    async def stream(
        self,
        *,
        thread_id: uuid.UUID,
        content: str,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> AsyncIterator[StreamEvent]:
        config = {"configurable": {"thread_id": str(thread_id)}}
        context = AgentContext(
            project_id=str(project_id),
            user_id=str(user_id),
        )
        input_msg = {"messages": [{"role": "user", "content": content}]}

        try:
            async for mode, data in self._graph.astream(
                input_msg,
                config,
                stream_mode=["messages", "updates"],
                context=context,
            ):
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

            yield StreamEvent(type="done", data={})
        except Exception as e:
            yield StreamEvent(type="error", data={"detail": str(e)})

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
            )
            for m in messages
            if isinstance(m, (HumanMessage, AIMessage))
            and not getattr(m, "tool_calls", None)
        ]

    async def cancel(self, *, thread_id: uuid.UUID) -> bool:
        return True  # MVP stub
