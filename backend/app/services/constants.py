"""Shared chat/project naming constants.

Lives in the service layer (not ``api/schemas``) so schemas import a plain
constant instead of the full chat-service module and its dependencies —
``api -> services`` is a permitted import direction under the layered
architecture contract (backend.md § Правила вызовов); the reverse is not.
"""

from __future__ import annotations

DEFAULT_CHAT_TITLE = "Новый чат"
"""Placeholder title the server sets on chat creation.

The auto-title trigger is an exact match against this value — nothing keeps a
user or the title model from choosing the same string, and renaming a chat to
it re-arms generation for the next message (design-brief § Триггер accepts that
edge case as harmless)."""

MAX_TITLE_LENGTH = 100
"""Shared length limit for chat/project titles: ``ChatUpdate.title``,
auto-title truncation, and the ``ProjectUpdate.name`` drift-fix (design-brief
Open Questions §1)."""
