"""Read-side adapter over the LangGraph checkpointer.

Single place that knows the ``checkpoint.checkpoint["channel_values"]["messages"]``
shape: raw message extraction, history mapping for the API, last-AI-id lookup,
and post-stream redaction inspection. Keeps that knowledge out of the runner.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.security.types import Checkpoint, DetectionLayer, SecurityMessages
from app.services.agent_runner import Message

logger = structlog.get_logger()


@dataclass(frozen=True)
class InGraphSecurityHit:
    checkpoint: Checkpoint
    detection_layer: DetectionLayer | None
    reason: str


def _parse_created_at(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


class CheckpointHistory:
    def __init__(self, checkpointer: Any, security_messages: SecurityMessages) -> None:
        self._checkpointer = checkpointer
        self._messages = security_messages

    async def raw_messages(self, thread_id: uuid.UUID) -> list[Any]:
        """Return the raw message list for a thread, or ``[]`` on miss / error."""
        try:
            config = {"configurable": {"thread_id": str(thread_id)}}
            checkpoint = await self._checkpointer.aget_tuple(config)
            if checkpoint is None:
                return []
            return checkpoint.checkpoint.get("channel_values", {}).get("messages", [])
        except Exception:
            logger.warning(
                "checkpoint read failed",
                thread_id=str(thread_id),
                exc_info=True,
            )
            return []

    async def history(self, thread_id: uuid.UUID) -> list[Message]:
        """Map stored messages to domain ``Message`` (excludes tool-call turns)."""
        messages = await self.raw_messages(thread_id)
        result: list[Message] = []
        for m in messages:
            if not isinstance(m, (HumanMessage, AIMessage)):
                continue
            if getattr(m, "tool_calls", None):
                continue
            redacted = bool(m.additional_kwargs.get("security_redacted"))
            content = (
                self._messages.redacted_user_facing
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

    async def last_ai_message_id(self, thread_id: uuid.UUID) -> str | None:
        messages = await self.raw_messages(thread_id)
        for m in reversed(messages):
            if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
                return str(m.id)
        return None

    async def latest_redaction(self, thread_id: uuid.UUID) -> InGraphSecurityHit | None:
        """Scan the latest turn for an in-graph redaction flag (bounded by user msg)."""
        messages = await self.raw_messages(thread_id)
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
                    detection_layer: DetectionLayer | None = DetectionLayer(layer)
                except ValueError:
                    detection_layer = None
                checkpoint = (
                    Checkpoint.TOOL_RESULT
                    if isinstance(m, ToolMessage)
                    else Checkpoint.TOOL_CALL_ARG
                )
                return InGraphSecurityHit(
                    checkpoint=checkpoint,
                    detection_layer=detection_layer,
                    reason=layer,
                )
            # Stop at the previous user message to bound the scan.
            if isinstance(m, HumanMessage):
                break
        return None
