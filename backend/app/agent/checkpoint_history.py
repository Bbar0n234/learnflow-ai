"""Read-side adapter over the LangGraph checkpointer.

Single place that knows the ``checkpoint.checkpoint["channel_values"]["messages"]``
shape: raw message extraction, history mapping for the API, last-AI-id lookup,
and post-stream redaction inspection. Keeps that knowledge out of the runner.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import structlog
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.security.types import Checkpoint, DetectionLayer, SecurityMessages
from app.agent.text_limits import truncate
from app.services.agent_runner import (
    Message,
    Part,
    ReasoningPart,
    TextPart,
    ToolCallPart,
)

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
        """Map stored messages to domain ``Message``s, one per turn.

        A turn spans from a ``HumanMessage`` up to (excluding) the next one;
        everything an assistant turn produced in between (tool-calling
        ``AIMessage``s, their ``ToolMessage`` results, the final ``AIMessage``)
        collapses into a single assistant ``Message`` with ordered ``parts``
        (design-brief § «Модель typed parts») — mirroring how one live turn
        renders as one activity-feed row, not one row per checkpoint message.

        Messages before the first ``HumanMessage`` of the thread are dropped:
        after compaction, ``graph.py`` prepends an id-less summary ``AIMessage``
        there (``_reduce_context``) — a context digest, not a turn the user
        took part in, so it has no place in the feed.
        """
        messages = await self.raw_messages(thread_id)
        first_human = next(
            (i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), None
        )
        if first_human is None:
            return []
        messages = messages[first_human:]

        result: list[Message] = []
        segment: list[Any] = []

        def flush_segment() -> None:
            turn = self._build_turn_message(segment)
            if turn is not None:
                result.append(turn)

        for m in messages:
            if isinstance(m, HumanMessage):
                flush_segment()
                segment = []
                redacted = bool(m.additional_kwargs.get("security_redacted"))
                content = (
                    self._messages.redacted_user_facing
                    if redacted
                    else (m.content if isinstance(m.content, str) else "")
                )
                result.append(
                    Message(
                        id=str(m.id),
                        role="user",
                        content=content,
                        created_at=_parse_created_at(
                            m.additional_kwargs.get("created_at")
                        ),
                        redacted=redacted,
                    )
                )
            else:
                segment.append(m)
        flush_segment()
        return result

    def _build_turn_message(self, segment: list[Any]) -> Message | None:
        """Collapse one assistant turn's messages into a single ``Message``.

        Returns ``None`` when the segment carries no ``AIMessage`` at all (a
        human turn with no reply yet).
        """
        ai_messages = [m for m in segment if isinstance(m, AIMessage)]
        if not ai_messages:
            return None

        tool_messages_by_call_id: dict[str, ToolMessage] = {
            m.tool_call_id: m for m in segment if isinstance(m, ToolMessage)
        }

        parts: list[Part] = []
        final_ai: AIMessage | None = None
        for ai in ai_messages:
            if getattr(ai, "tool_calls", None):
                parts.extend(self._tool_call_turn_parts(ai, tool_messages_by_call_id))
                continue
            # No tool_calls: the turn's final message (graph semantics — the
            # loop only exits "agent" -> END on a tool-call-free response, and
            # a security-redacted response has its tool_calls stripped to
            # empty, which is exactly why it lands here too). Reasoning tied
            # to a redacted message is not surfaced — same swap-to-stub policy
            # as ``content`` below, not a partial leak of it.
            final_ai = ai
            redacted = bool(ai.additional_kwargs.get("security_redacted"))
            if redacted:
                parts.append(TextPart(content=self._messages.redacted_user_facing))
            else:
                reasoning = ai.additional_kwargs.get("reasoning")
                if isinstance(reasoning, str) and reasoning:
                    parts.append(ReasoningPart(content=reasoning))
                parts.append(
                    TextPart(content=ai.content if isinstance(ai.content, str) else "")
                )

        anchor = final_ai if final_ai is not None else ai_messages[-1]
        redacted = bool(anchor.additional_kwargs.get("security_redacted"))
        content = (
            self._messages.redacted_user_facing
            if redacted
            else (anchor.content if isinstance(anchor.content, str) else "")
        )
        return Message(
            id=str(anchor.id),
            role="assistant",
            content=content,
            created_at=_parse_created_at(anchor.additional_kwargs.get("created_at")),
            redacted=redacted,
            parts=parts,
        )

    @staticmethod
    def _tool_call_turn_parts(
        ai: AIMessage, tool_messages_by_call_id: dict[str, ToolMessage]
    ) -> list[Part]:
        """``reasoning``(optional) + one ``tool_call`` part per ``ai.tool_calls`` entry."""
        parts: list[Part] = []
        reasoning = ai.additional_kwargs.get("reasoning")
        if isinstance(reasoning, str) and reasoning:
            parts.append(ReasoningPart(content=reasoning))

        for tc in ai.tool_calls:
            call_id = tc.get("id") or ""
            args_text, args_truncated = truncate(
                json.dumps(tc.get("args", {}), ensure_ascii=False)
            )
            tool_message = tool_messages_by_call_id.get(call_id)
            status: Literal["success", "error", "pending"]
            if tool_message is None:
                # Turn was cut short before the tool call resolved (checkpoint
                # snapshot mid-execution) — no result to show yet.
                status = "pending"
                result_text, result_truncated = "", False
            else:
                status = tool_message.status
                raw_result = (
                    tool_message.content
                    if isinstance(tool_message.content, str)
                    else str(tool_message.content)
                )
                result_text, result_truncated = truncate(raw_result)
            parts.append(
                ToolCallPart(
                    call_id=call_id,
                    tool=tc.get("name", ""),
                    args=args_text,
                    status=status,
                    result_preview=result_text,
                    truncated=args_truncated or result_truncated,
                )
            )
        return parts

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
