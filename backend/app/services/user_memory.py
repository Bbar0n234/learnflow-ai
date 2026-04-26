from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import structlog
from fastapi import HTTPException

from app.agent.security.guard import SecurityGuard
from app.agent.security.types import Checkpoint, Verdict

logger = structlog.get_logger()


@dataclass
class MemoryItemData:
    key: str
    description: str
    content: str
    created_at: datetime


class UserMemoryService(Protocol):
    async def get_instructions(self, user_id: str) -> str: ...
    async def update_instructions(self, user_id: str, content: str) -> str: ...
    async def list_memories(self, user_id: str) -> list[MemoryItemData]: ...


class LangGraphUserMemoryService:
    def __init__(
        self,
        store: Any,
        guard: SecurityGuard | None = None,
    ) -> None:
        self._store = store
        self._guard = guard

    async def get_instructions(self, user_id: str) -> str:
        item = await self._store.aget(("user", user_id, "instructions"), "default")
        if item is None:
            return ""
        return item.value.get("content", "")

    async def update_instructions(self, user_id: str, content: str) -> str:
        if self._guard is not None:
            result = await self._guard.check(
                content,
                Checkpoint.CUSTOM_INSTRUCTIONS_WRITE,
                trace_ctx={
                    "top_level": True,
                    "user_id": user_id,
                    "scope": "custom_instructions",
                },
            )
            if result.verdict == Verdict.INJECTION:
                logger.warning(
                    "custom instructions injection blocked",
                    security_event=True,
                    checkpoint=Checkpoint.CUSTOM_INSTRUCTIONS_WRITE.value,
                    verdict=Verdict.INJECTION.value,
                    identifiers={"user_id": user_id},
                    metadata={
                        "detection_layer": (
                            result.detection_layer.value
                            if result.detection_layer
                            else None
                        )
                    },
                )
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "security_policy_violation",
                        "reason": (
                            result.detection_layer.value
                            if result.detection_layer
                            else "custom_instructions_write"
                        ),
                    },
                )
        await self._store.aput(
            ("user", user_id, "instructions"),
            "default",
            {"content": content},
        )
        return content

    async def list_memories(self, user_id: str) -> list[MemoryItemData]:
        items = await self._store.asearch(("user", user_id, "memory"), limit=50)
        result = []
        for item in items:
            result.append(
                MemoryItemData(
                    key=item.key,
                    description=item.value.get("description", ""),
                    content=item.value.get("content", ""),
                    created_at=item.created_at,
                )
            )
        return sorted(result, key=lambda x: x.created_at)

    async def delete_memory(self, user_id: str, key: str) -> None:
        await self._store.adelete(("user", user_id, "memory"), key)
