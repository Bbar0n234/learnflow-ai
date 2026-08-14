"""Read-side adapter over the LangGraph checkpointer.

Single place that knows the ``checkpoint.checkpoint["channel_values"]["messages"]``
shape: raw message extraction, history mapping for the API, last-AI-id lookup,
and post-stream redaction inspection. Keeps that knowledge out of the runner.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal

import structlog
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.security.types import Checkpoint, DetectionLayer, SecurityMessages
from app.agent.text_limits import truncate
from app.services.agent_runner import (
    ArtifactPart,
    AttachmentRef,
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


def _attachment_refs(raw: Any) -> list[AttachmentRef]:
    """``AttachmentRef`` per element of ``HumanMessage.additional_kwargs["attachments"]``.

    Mirrors ``_artifact_parts`` on the input side — reads the ``{path,
    title}`` list `agent/runner.py` stores verbatim, doesn't touch
    ``content``/the in-model note (design-brief § «Вложения пользователя»:
    the UI chip renders from this metadata, never by re-parsing the note).
    """
    if not raw:
        return []
    return [
        AttachmentRef(path=item.get("path", ""), title=item.get("title", ""))
        for item in raw
    ]


def _artifact_parts(tool_message: ToolMessage) -> list[ArtifactPart]:
    """``ArtifactPart`` per element of ``tool_message.artifact`` (may be several).

    Mirrors ``stream_events.artifact_envelopes``' reading of the same list —
    this is the checkpoint-replay half, this module's one job (module
    docstring: the single place that knows the ``channel_values["messages"]``
    shape). Every artifact-producing tool keys its element as ``"path"``.

    Older checkpoints (written before this iteration) carry ``artifact`` as a
    single ``dict``, not a list of dicts — ADR-032 does not design history
    back-compat for that shape, so it is a defensive guard, not a migration:
    a non-list value is skipped entirely (zero parts), the turn still renders,
    just without artifact cards.
    """
    artifact = tool_message.artifact
    if not artifact:
        return []
    if not isinstance(artifact, list):
        logger.warning(
            "legacy non-list ToolMessage.artifact skipped",
            tool_call_id=tool_message.tool_call_id,
        )
        return []
    return [
        ArtifactPart(
            path=item.get("path", ""),
            title=item.get("title", ""),
            type=item.get("type", ""),
            kind=item.get("kind", "created"),
            diff=item.get("diff"),
        )
        for item in artifact
    ]


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

        Two kinds of stored messages never become a turn. Compaction summaries
        (``additional_kwargs["context_summary"]``, set by ``_reduce_context``)
        are a context digest the model reads, not a turn the user took part in;
        they are dropped wherever they sit — and they sit at the *end* of the
        state, next to the answer of the turn that triggered compaction, since
        the id-less summary is appended by ``add_messages``. Messages before the
        first ``HumanMessage`` of the thread are dropped as well: a feed row
        without the user turn it answers is meaningless.
        """
        messages = await self.raw_messages(thread_id)
        messages = [
            m
            for m in messages
            if not (
                isinstance(m, AIMessage) and m.additional_kwargs.get("context_summary")
            )
        ]
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
                # `additional_kwargs["text"]` is the clean text `agent/runner.py`
                # stored alongside the model-facing note it appended to
                # `content` — only present when the turn carried attachments;
                # otherwise `content` itself already is the clean text.
                raw_content = m.content if isinstance(m.content, str) else ""
                clean_text = m.additional_kwargs.get("text", raw_content)
                content = (
                    self._messages.redacted_user_facing if redacted else clean_text
                )
                attachments = (
                    []
                    if redacted
                    else _attachment_refs(m.additional_kwargs.get("attachments"))
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
                        attachments=attachments,
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

        parts.extend(self._turn_artifact_parts(segment))

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
                    args_truncated=args_truncated,
                    status=status,
                    result_preview=result_text,
                    result_truncated=result_truncated,
                )
            )
        return parts

    @staticmethod
    def _turn_artifact_parts(segment: list[Any]) -> list[Part]:
        """Every artifact the turn produced, as one trailing group of cards.

        Placement is a product call, not a data one: a card reads as an outcome
        of the turn, so it follows the final text instead of sitting inline
        after the tool call that happened to write the file.

        One card per path — a path written twice in the same turn (a job
        rewriting what an earlier call created) collapses into a single entry:
        order comes from its first appearance, data from the last event, except
        that ``created`` never degrades to ``updated`` — for the reader the file
        is new in this turn.
        """
        by_path: dict[str, ArtifactPart] = {}
        for m in segment:
            if not isinstance(m, ToolMessage):
                continue
            for part in _artifact_parts(m):
                previous = by_path.get(part.path)
                if previous is not None and previous.kind == "created":
                    part = replace(part, kind="created")
                by_path[part.path] = part
        return list(by_path.values())

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
