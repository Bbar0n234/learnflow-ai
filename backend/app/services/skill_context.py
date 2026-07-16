from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

import structlog

from app.agent.security.guard import SecurityGuard
from app.agent.security.types import Checkpoint, Verdict
from app.services.exceptions import NotFoundError, SecurityPolicyViolationError

if TYPE_CHECKING:
    from langgraph.store.base import BaseStore, Item

logger = structlog.get_logger()

# Upper bound for the full listing: business limit is <= 20 skills x <= 20
# documents/skill (design-brief § Лимиты); headroom above the theoretical max
# so a full inventory is never silently truncated by the search limit.
_MAX_LIST_ITEMS = 500


@dataclass(frozen=True)
class SkillContextDocumentData:
    """One skill-context document (namespace: user/uid/skill_context/skill)."""

    key: str
    description: str
    content: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SkillContextGroupData:
    """Documents for a single skill, grouped for the listing endpoint."""

    skill_name: str
    in_library: bool
    documents: list[SkillContextDocumentData]


class SkillContextService(Protocol):
    async def list_skill_contexts(
        self, user_id: str
    ) -> list[SkillContextGroupData]: ...

    async def get_document(
        self, user_id: str, skill_name: str, key: str
    ) -> SkillContextDocumentData: ...

    async def update_document(
        self,
        user_id: str,
        skill_name: str,
        key: str,
        *,
        description: str,
        content: str,
    ) -> SkillContextDocumentData: ...

    async def delete_document(
        self, user_id: str, skill_name: str, key: str
    ) -> None: ...


class LangGraphSkillContextService:
    """Skill-scoped user context over the LangGraph Store.

    Namespace: ``("user", uid, "skill_context", skill_name)``. ``skill_names``
    is the startup snapshot of the skill library (`scan_skill_names`), used
    only for the ``in_library`` badge on the listing — it never gates
    read/write/delete, so context for a skill later removed from the library
    stays fully reachable through REST (design-brief: storage and delivery
    are decoupled).
    """

    def __init__(
        self,
        store: BaseStore,
        guard: SecurityGuard | None,
        skill_names: frozenset[str],
    ) -> None:
        self._store = store
        self._guard = guard
        self._skill_names = skill_names

    def _ns(self, user_id: str, skill_name: str) -> tuple[str, ...]:
        return ("user", user_id, "skill_context", skill_name)

    @staticmethod
    def _to_document_data(item: Item) -> SkillContextDocumentData:
        return SkillContextDocumentData(
            key=item.key,
            description=item.value.get("description", ""),
            content=item.value.get("content", ""),
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    async def list_skill_contexts(self, user_id: str) -> list[SkillContextGroupData]:
        items = await self._store.asearch(
            ("user", user_id, "skill_context"), limit=_MAX_LIST_ITEMS
        )
        groups: dict[str, list[SkillContextDocumentData]] = {}
        for item in items:
            skill_name = item.namespace[3]
            groups.setdefault(skill_name, []).append(self._to_document_data(item))
        return [
            SkillContextGroupData(
                skill_name=skill_name,
                in_library=skill_name in self._skill_names,
                documents=sorted(documents, key=lambda d: d.created_at),
            )
            for skill_name, documents in sorted(groups.items())
        ]

    async def get_document(
        self, user_id: str, skill_name: str, key: str
    ) -> SkillContextDocumentData:
        item = await self._store.aget(self._ns(user_id, skill_name), key)
        if item is None:
            raise NotFoundError(
                f"Skill context '{key}' not found for skill '{skill_name}'"
            )
        return self._to_document_data(item)

    async def update_document(
        self,
        user_id: str,
        skill_name: str,
        key: str,
        *,
        description: str,
        content: str,
    ) -> SkillContextDocumentData:
        ns = self._ns(user_id, skill_name)
        existing = await self._store.aget(ns, key)
        if existing is None:
            raise NotFoundError(
                f"Skill context '{key}' not found for skill '{skill_name}'"
            )

        if self._guard is not None:
            result = await self._guard.check(
                f"{description}\n\n{content}",
                Checkpoint.SKILL_CONTEXT_WRITE,
                trace_ctx={
                    "top_level": True,
                    "user_id": user_id,
                    "skill_name": skill_name,
                    "key": key,
                    "scope": "skill_context",
                },
            )
            if result.verdict == Verdict.INJECTION:
                logger.warning(
                    "skill context write injection blocked",
                    security_event=True,
                    checkpoint=Checkpoint.SKILL_CONTEXT_WRITE.value,
                    verdict=Verdict.INJECTION.value,
                    identifiers={
                        "user_id": user_id,
                        "skill_name": skill_name,
                        "key": key,
                    },
                    metadata={
                        "detection_layer": (
                            result.detection_layer.value
                            if result.detection_layer
                            else None
                        )
                    },
                )
                raise SecurityPolicyViolationError(
                    reason=(
                        result.detection_layer.value
                        if result.detection_layer
                        else "skill_context_write"
                    )
                )

        await self._store.aput(
            ns, key, {"description": description, "content": content}
        )
        return await self.get_document(user_id, skill_name, key)

    async def delete_document(self, user_id: str, skill_name: str, key: str) -> None:
        ns = self._ns(user_id, skill_name)
        existing = await self._store.aget(ns, key)
        if existing is None:
            raise NotFoundError(
                f"Skill context '{key}' not found for skill '{skill_name}'"
            )
        await self._store.adelete(ns, key)
