"""Fire-and-forget chat auto-title generation (design-brief § Auto-title модуль).

``ChatTitleGenerator`` is built once in ``main.py``'s lifespan and lives on
``app.state`` — its in-flight task registry must survive across requests (a
second message arriving while the first title generation is still running
must not spawn a duplicate), and a request-scoped ``ChatService`` is the
wrong place to hold that state (conventions.md § Module-level state: no
module-level singletons, state lives in ``app.state`` or closures).

Each generation runs in its own DB session from ``session_factory`` — the
request that triggered it may finish (and its session close) long before the
title LLM call returns; the pattern mirrors
``app/agent/tools/image_generation.py``.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from typing import Any

import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langfuse import get_client
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.config import PromptFragmentsConfig, TitleConfig
from app.agent.prompt_builder import wrap_user_message
from app.config import Settings
from app.infra.llm import create_title_llm
from app.infra.prompt_provider import PromptProvider
from app.models.thread_view import ThreadView
from app.repositories.thread_view import ThreadViewRepository
from app.services.constants import DEFAULT_CHAT_TITLE, MAX_TITLE_LENGTH

logger = structlog.get_logger()


def _title_write_blocked(thread_view: ThreadView) -> bool:
    """Whether this chat already cannot take an auto-title — cheap early exit.

    A blocked chat never gets an auto-title, and a chat whose title is no
    longer the placeholder was either renamed by the user or already titled —
    both cases mean a generated title would be stale and must not overwrite it.

    This is a *snapshot* read taken before the LLM call, so it only saves the
    call; it decides nothing. The decision is the conditional UPDATE at write
    time (``ThreadViewRepository.apply_generated_title``), which restates the
    same predicate in SQL.
    """
    return thread_view.security_blocked or thread_view.title != DEFAULT_CHAT_TITLE


def _postprocess_title(raw: str) -> str:
    """strip -> keep the first line only -> truncate to the shared length limit.

    The prompt already instructs the model to output a single line with no
    quotes/trailing punctuation; this is a defensive net against models that
    ignore instructions (extra lines, wrapping quotes left in place, etc.).
    """
    first_line = raw.strip().splitlines()[0].strip() if raw.strip() else ""
    return first_line[:MAX_TITLE_LENGTH]


class ChatTitleGenerator:
    """Generates a short chat title from the first user message.

    Holds a registry of in-flight tasks keyed by ``thread_id`` — this is
    both the durable reference that keeps a task alive after the triggering
    request's own generator (``ChatService.send_message``) has returned, and
    the in-flight guard that prevents a second trigger for the same chat from
    spawning a duplicate task.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        title_config: TitleConfig,
        prompt_provider: PromptProvider,
        prompt_fragments: PromptFragmentsConfig,
        langfuse_enabled: bool = False,
    ) -> None:
        self._session_factory = session_factory
        self._title_config = title_config
        self._prompt_provider = prompt_provider
        self._prompt_fragments = prompt_fragments
        self._langfuse_enabled = langfuse_enabled
        self._llm: BaseChatModel = create_title_llm(settings, title_config)
        self._tasks: dict[uuid.UUID, asyncio.Task[str | None]] = {}

    async def shutdown(self) -> None:
        """Cancel every in-flight generation and wait for it to unwind.

        Called from the lifespan after ``yield`` and **before**
        ``engine.dispose()`` (conventions/api.md § Владение состоянием:
        background tasks are torn down where they were created). A running
        task holds a session from the same ``session_factory`` and can sit in
        ``ainvoke`` for up to ``LLM_TITLE_TIMEOUT_SECONDS`` — disposing the
        engine under it would pull the pool out from beneath a live
        connection, and leaving it unawaited turns every restart into a
        "Task was destroyed but it is pending".

        Iterates a snapshot of the registry: the done-callback mutates it as
        the cancellations land.
        """
        tasks = list(self._tasks.values())
        if not tasks:
            return
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def generate_title(
        self, thread_id: uuid.UUID, content: str
    ) -> asyncio.Task[str | None] | None:
        """Start title generation for ``thread_id`` unless one is already running.

        Returns the task handle (for the caller to poll ``task.done()`` /
        ``task.result()`` later) or ``None`` when a generation for this
        thread is already in flight.
        """
        if thread_id in self._tasks:
            return None
        task = asyncio.create_task(self._run(thread_id, content))
        self._tasks[thread_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(thread_id, None))
        return task

    async def _run(self, thread_id: uuid.UUID, content: str) -> str | None:
        try:
            async with self._session_factory() as session:
                repo = ThreadViewRepository(session)
                thread_view = await repo.get_by_id(thread_id)
                # Early exit — cheap: don't spend an LLM call on a chat that
                # already cannot take a generated title.
                if thread_view is None or _title_write_blocked(thread_view):
                    return None

                title = await self._invoke_llm(content)
                if not title:
                    logger.warning(
                        "chat title generation produced empty title",
                        thread_id=str(thread_id),
                    )
                    return None

                # Decisive guard (design-brief § Auto-title модуль: the task
                # must not write a title into a chat that was deleted, blocked
                # or renamed). The LLM call above is that window, so the state
                # read before it is stale by now — and re-reading here would
                # not help either: a mid-stream ``security_blocked`` is flushed
                # in the *request's* session and stays uncommitted (invisible
                # under READ COMMITTED) until the request ends. So the write is
                # conditional in SQL: the database checks the predicate against
                # the committed row at the moment it writes, and a no-match
                # (deleted / blocked / renamed) simply writes nothing.
                written = await repo.apply_generated_title(
                    thread_id, title=title, placeholder=DEFAULT_CHAT_TITLE
                )
                if not written:
                    return None
                await session.commit()
        except Exception:
            logger.warning(
                "chat title generation failed",
                thread_id=str(thread_id),
                exc_info=True,
            )
            return None

        logger.info("chat title generated", thread_id=str(thread_id), title=title)
        return title

    async def _invoke_llm(self, content: str) -> str:
        system_prompt = self._prompt_provider.get_prompt("title")
        user_message = wrap_user_message(self._prompt_fragments, content)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ]

        response = await self._llm.ainvoke(messages)
        raw = (
            response.content
            if isinstance(response.content, str)
            else str(response.content)
        )
        title = _postprocess_title(raw)

        if self._langfuse_enabled:
            with contextlib.suppress(Exception):
                gen_kwargs: dict[str, Any] = {
                    "as_type": "generation",
                    "name": "chat-title",
                    "model": self._title_config.model,
                    "input": content,
                    "output": title,
                }
                with get_client().start_as_current_observation(**gen_kwargs):
                    pass

        return title
