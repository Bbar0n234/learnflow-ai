from __future__ import annotations

from collections.abc import Callable
from typing import Any


def format_index(
    items: list[Any],
    title: str,
    key_fn: Callable[[Any], str] | None = None,
) -> str:
    """Format store items as an index for system message.

    Generic helper used by both Knowledge Sphere and User Memory.
    """
    if not items:
        return f"{title}: empty"

    sorted_items = sorted(items, key=lambda i: i.created_at)
    lines = []
    for item in sorted_items:
        key = key_fn(item) if key_fn else item.key
        description = item.value.get("description", "")
        lines.append(f"- {key}: {description}")

    return f"{title}:\n" + "\n".join(lines)
