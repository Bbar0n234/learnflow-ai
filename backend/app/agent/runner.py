from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

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
            async for msg_chunk, _metadata in self._graph.astream(
                input_msg,
                config,
                stream_mode="messages",
                context=context,
            ):
                if (
                    hasattr(msg_chunk, "content")
                    and isinstance(msg_chunk.content, str)
                    and msg_chunk.content
                ):
                    yield StreamEvent(
                        type="text_chunk",
                        data={"content": msg_chunk.content},
                    )
            yield StreamEvent(type="done", data={})
        except Exception as e:
            yield StreamEvent(type="error", data={"detail": str(e)})

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
