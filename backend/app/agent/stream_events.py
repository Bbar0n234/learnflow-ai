"""Maps LangGraph ``stream_mode="updates"`` payloads to domain ``StreamEvent``s.

Translates node outputs (agent tool calls, tool results, created artifacts)
into the SSE-facing event vocabulary; the runner stays free of graph payload
shape knowledge.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from app.services.agent_runner import StreamEvent


class StreamEventMapper:
    def updates(self, data: dict[str, Any]) -> list[StreamEvent]:
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
                    if (
                        msg.name in {"create_artifact", "generate_image"}
                        and msg.artifact is not None
                    ):
                        artifact = dict(msg.artifact)
                        artifact["artifact_type"] = artifact.pop("type", "")
                        events.append(
                            StreamEvent(type="artifact_created", data=artifact)
                        )

        return events
