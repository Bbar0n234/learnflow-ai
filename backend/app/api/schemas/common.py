from __future__ import annotations

from pydantic import BaseModel


class Page[T](BaseModel):
    """Канонический envelope списочных ответов: items + pagination metadata."""

    items: list[T]
    total: int
    limit: int
    offset: int
