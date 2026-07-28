"""Heartbeat pacing for the agent SSE stream.

A new cross-cutting concern gets its own collaborator rather than another
method on the runner (conventions/agent.md § Agent Runtime): ``HeartbeatPacer``
wraps any ``StreamEvent`` source and interleaves two things on a single timer —

* a ``heartbeat`` event whenever the source has been silent for ``interval``
  seconds (design-brief § «Контракт SSE v2»: no silent stretch — setup, a
  slow tool call, the final-output review — should ever reach the client
  unexplained);
* a check of ``cancel_event`` on that *same* timer, so a run started via
  ``LangGraphAgentRunner.cancel`` gets interrupted within one interval even
  while blocked deep inside a tool call, not only between ``astream``
  iterations (event-map.md popутная находка №3).

The source is pulled via a background ``asyncio.Task`` raced against the
timer (``asyncio.wait(..., timeout=interval)``) precisely so the timer keeps
ticking independently of whether the source has anything ready — that
decoupling is what makes the cancel check "responsive" during a blocked tool
call instead of only firing between the source's own yields.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from typing import Final

from app.services.agent_runner import StreamEvent

HEARTBEAT_INTERVAL_SECONDS: Final = 5.0


class HeartbeatPacer:
    """Interleaves ``heartbeat``/``cancelled`` events into a ``StreamEvent`` source."""

    def __init__(self, interval: float = HEARTBEAT_INTERVAL_SECONDS) -> None:
        self._interval = interval

    async def pace(
        self,
        source: AsyncGenerator[StreamEvent, None],
        cancel_event: asyncio.Event,
    ) -> AsyncGenerator[StreamEvent, None]:
        agen = source
        pending: asyncio.Task[StreamEvent] | None = None
        try:
            while True:
                if pending is None:
                    pending = asyncio.ensure_future(agen.__anext__())
                done, _ = await asyncio.wait({pending}, timeout=self._interval)
                if pending in done:
                    finished, pending = pending, None
                    try:
                        yield finished.result()
                    except StopAsyncIteration:
                        return
                    continue
                if cancel_event.is_set():
                    yield StreamEvent(type="cancelled", data={})
                    return
                yield StreamEvent(type="heartbeat", data={})
        finally:
            # Best-effort teardown, not a masking suppression: whichever path
            # got us here (cancellation detected above, the caller closing us
            # via GeneratorExit, or an exception from the source itself) has
            # already decided the outcome — a secondary failure while retiring
            # the still-open source must not override it.
            if pending is not None and not pending.done():
                pending.cancel()
                with contextlib.suppress(Exception, asyncio.CancelledError):
                    await pending
            else:
                with contextlib.suppress(Exception, asyncio.CancelledError):
                    await agen.aclose()
