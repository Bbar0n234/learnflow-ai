"""Shared chat/project naming constants.

Lives in the service layer (not ``api/schemas``) so schemas import a plain
constant instead of the full chat-service module and its dependencies —
``api -> services`` is a permitted import direction under the layered
architecture contract (backend.md § Правила вызовов); the reverse is not.
"""

from __future__ import annotations

DEFAULT_CHAT_TITLE = "Новый чат"
"""Placeholder title the server sets on chat creation. Auto-title generation
(T1.4) looks for chats whose title still equals this exact value before
overwriting it, so it must never collide with a user- or LLM-chosen title."""

MAX_TITLE_LENGTH = 100
"""Shared length limit for chat/project titles: ``ChatUpdate.title``,
auto-title truncation, and the ``ProjectUpdate.name`` drift-fix (design-brief
Open Questions §1)."""
