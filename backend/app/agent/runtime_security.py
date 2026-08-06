"""Runtime security enforcement for the agent stream.

Owns the four runtime checkpoints (user input, mid-stream tail, end-of-stream
final output, post-stream in-graph redaction inspection) together with their
side effects: redacting messages in the checkpointer and marking the thread
blocked. Each ``check_*`` performs its side effects internally and returns a
``SecurityOutcome`` when the turn must be blocked, or ``None`` to proceed — the
runner stays responsible only for emitting SSE events and trace scoring.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.checkpoint_history import CheckpointHistory
from app.agent.security.guard import SecurityGuard
from app.agent.security.types import (
    Checkpoint,
    DetectionLayer,
    GuardResult,
    SecurityMessages,
    Verdict,
    direction_of,
)
from app.repositories.thread_view import ThreadViewRepository

logger = structlog.get_logger()


@dataclass(frozen=True)
class SecurityOutcome:
    """A blocked turn: ``reason`` is the SSE ``security_block`` payload, ``result``
    feeds trace finalization."""

    reason: str
    result: GuardResult


class RuntimeSecurityEnforcer:
    def __init__(
        self,
        *,
        guard: SecurityGuard | None,
        security_messages: SecurityMessages,
        history: CheckpointHistory,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._guard = guard
        self._messages = security_messages
        self._history = history
        self._session_factory = session_factory

    @property
    def active(self) -> bool:
        """Whether inline LLM defense is active (a guard was built).

        The sole public signal callers may use to decide on observability
        (e.g. whether to emit review SSE events) — ``check_*`` methods stay
        safe no-ops on their own when defense is inactive, so callers never
        need to inspect the guard directly.
        """
        return self._guard is not None

    @staticmethod
    def tail_window_len(canary_token: str) -> int:
        return max(len(canary_token) if canary_token else 0, 64)

    @staticmethod
    def block_reason(result: GuardResult, fallback: str = "prompt_injection") -> str:
        """SSE ``security_block`` reason: detection layer name, else a fallback."""
        return result.detection_layer.value if result.detection_layer else fallback

    async def check_user_input(
        self,
        *,
        thread_id: uuid.UUID,
        content: str,
        canary_token: str,
        graph: Any,
        session: AsyncSession | None = None,
    ) -> GuardResult | None:
        """Pre-graph USER_INPUT check. Returns the verdict (``None`` if guard off).

        On INJECTION: persists the blocked turn + marks the thread blocked before
        returning (the caller inspects ``verdict`` to block); SUSPICIOUS is logged
        and allowed through.
        """
        if self._guard is None:
            return None
        history = await self._history.raw_messages(thread_id)
        result = await self._guard.check(
            content,
            Checkpoint.USER_INPUT,
            history=history,
            canary_token=canary_token,
        )
        if result.verdict == Verdict.INJECTION:
            await self._persist_user_input_block(graph, thread_id, content, result)
            await self._mark_blocked(thread_id, session=session)
        elif result.verdict == Verdict.SUSPICIOUS:
            logger.warning(
                "suspicious input detected, proceeding",
                thread_id=str(thread_id),
                detection_layer=(
                    result.detection_layer.value if result.detection_layer else None
                ),
            )
        return result

    async def check_mid_stream(
        self,
        *,
        thread_id: uuid.UUID,
        full_response: str,
        tail: str,
        canary_token: str,
        graph: Any,
        config: dict[str, Any],
        last_message_id: str | None,
        session: AsyncSession | None = None,
    ) -> SecurityOutcome | None:
        """Mid-stream tail-only deterministic check (skip_classifier=True)."""
        if self._guard is None:
            return None
        result = await self._guard.check(
            tail,
            Checkpoint.FINAL_OUTPUT,
            canary_token=canary_token,
            skip_classifier=True,
            observe=False,
        )
        if result.verdict != Verdict.INJECTION:
            return None
        await self._redact_final_output(
            graph, config, thread_id, full_response, result, last_message_id, session
        )
        return SecurityOutcome(
            reason=self.block_reason(result, "final_output"), result=result
        )

    async def check_final_output(
        self,
        *,
        thread_id: uuid.UUID,
        full_response: str,
        canary_token: str,
        graph: Any,
        config: dict[str, Any],
        last_message_id: str | None,
        session: AsyncSession | None = None,
    ) -> SecurityOutcome | None:
        """End-of-stream FINAL_OUTPUT classifier check."""
        if self._guard is None:
            return None
        result = await self._guard.check(
            full_response,
            Checkpoint.FINAL_OUTPUT,
            canary_token=canary_token,
        )
        if result.verdict != Verdict.INJECTION:
            return None
        await self._redact_final_output(
            graph, config, thread_id, full_response, result, last_message_id, session
        )
        return SecurityOutcome(
            reason=self.block_reason(result, "final_output"), result=result
        )

    async def inspect_in_graph(
        self,
        *,
        thread_id: uuid.UUID,
        session: AsyncSession | None = None,
    ) -> SecurityOutcome | None:
        """Post-stream inspection of TOOL_CALL_ARG / TOOL_RESULT redactions."""
        hit = await self._history.latest_redaction(thread_id)
        if hit is None:
            return None
        await self._mark_blocked(thread_id, session=session)
        result = GuardResult(
            verdict=Verdict.INJECTION,
            checkpoint=hit.checkpoint,
            direction=direction_of(hit.checkpoint),
            detection_layer=hit.detection_layer,
            details={"reason": "in_graph_security_redaction"},
        )
        return SecurityOutcome(reason=hit.reason, result=result)

    async def _redact_final_output(
        self,
        graph: Any,
        config: dict[str, Any],
        thread_id: uuid.UUID,
        full_response: str,
        result: GuardResult,
        last_message_id: str | None,
        session: AsyncSession | None = None,
    ) -> None:
        """Replace the assistant message by id with the redaction placeholder."""
        try:
            redacted = AIMessage(
                id=last_message_id,
                content=self._messages.redacted_user_facing,
                additional_kwargs={
                    "security_redacted": True,
                    "original_detection_layer": (
                        result.detection_layer.value
                        if result.detection_layer
                        else DetectionLayer.LLM_CLASSIFIER.value
                    ),
                    "created_at": datetime.now(UTC).isoformat(),
                },
            )
            await graph.aupdate_state(config, {"messages": [redacted]}, as_node="agent")
        except Exception:
            logger.warning(
                "final_output aupdate_state failed",
                thread_id=str(thread_id),
                exc_info=True,
            )
        await self._mark_blocked(thread_id, session=session)
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
        """Replay the blocked HumanMessage + redacted placeholder into the checkpointer.

        The graph never runs for USER_INPUT injections, so the user would
        otherwise see neither their prompt nor a response when reopening the chat.
        """
        config: dict[str, Any] = {"configurable": {"thread_id": str(thread_id)}}
        now_iso = datetime.now(UTC).isoformat()
        try:
            human = HumanMessage(
                content=content,
                additional_kwargs={"created_at": now_iso},
            )
            placeholder = AIMessage(
                content=self._messages.redacted_user_facing,
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

    async def _mark_blocked(
        self,
        thread_id: uuid.UUID,
        *,
        session: AsyncSession | None = None,
    ) -> None:
        """Mark the thread blocked.

        When a request-scoped ``session`` is provided, reuse it directly: the
        request transaction already holds the ``thread_views`` row lock (via
        ``touch``), so opening a second session here would deadlock — the second
        UPDATE would wait on a lock that only releases when the request commits,
        which only happens after the stream (and thus this call) finishes.
        ``mark_security_blocked`` flushes; the request transaction commits at the
        end of the request. The standalone fallback (own session + ``begin()``)
        covers non-request callers such as tests.
        """
        if session is not None:
            try:
                await ThreadViewRepository(session).mark_security_blocked(thread_id)
            except Exception:
                logger.warning(
                    "mark_security_blocked failed",
                    thread_id=str(thread_id),
                    exc_info=True,
                )
            return
        if self._session_factory is None:
            return
        try:
            async with self._session_factory() as own_session, own_session.begin():
                repo = ThreadViewRepository(own_session)
                await repo.mark_security_blocked(thread_id)
        except Exception:
            logger.warning(
                "mark_security_blocked failed",
                thread_id=str(thread_id),
                exc_info=True,
            )
