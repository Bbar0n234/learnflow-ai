from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol

import structlog
from fastapi import HTTPException

from app.agent.security.guard import SecurityGuard
from app.agent.security.types import Checkpoint, Verdict

if TYPE_CHECKING:
    from langgraph.store.base import BaseStore

logger = structlog.get_logger()


@dataclass(frozen=True)
class SphereData:
    """Knowledge Sphere of a project."""

    project_id: uuid.UUID
    content: str
    updated_at: datetime


class SphereService(Protocol):
    async def get(self, *, project_id: uuid.UUID) -> SphereData: ...
    async def update(self, *, project_id: uuid.UUID, content: str) -> SphereData: ...


def _slugify(text: str) -> str:
    """Convert header text to a slug for section_id."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug.strip("-")


def _format_full_sphere(items: list) -> str:
    """Concatenate all sections into a single Markdown document."""
    if not items:
        return ""
    sorted_items = sorted(items, key=lambda i: i.created_at)
    parts = []
    for item in sorted_items:
        section_id = item.key.removeprefix("section:")
        desc = item.value.get("description", "")
        content = item.value.get("content", "")
        parts.append(f"## {section_id}\n\n_{desc}_\n\n{content}")
    return "\n\n".join(parts)


def _parse_markdown_sections(
    content: str,
) -> list[tuple[str, str, str]]:
    """Parse markdown into sections: list of (section_id, description, content)."""
    sections: list[tuple[str, str, str]] = []
    # Split by H2 headers
    parts = re.split(r"^## (.+)$", content, flags=re.MULTILINE)
    # parts[0] is text before first H2 (ignored)
    # then alternating: header, body, header, body, ...
    for i in range(1, len(parts), 2):
        header = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        section_id = _slugify(header)

        # Extract description from italic line at start
        desc_match = re.match(r"^_(.+?)_\s*\n?", body)
        if desc_match:
            description = desc_match.group(1)
            section_content = body[desc_match.end() :].strip()
        else:
            # First line as description
            lines = body.split("\n", 1)
            description = lines[0][:100] if lines[0] else header
            section_content = lines[1].strip() if len(lines) > 1 else ""

        sections.append((section_id, description, section_content))
    return sections


class LangGraphSphereService:
    def __init__(
        self,
        store: BaseStore,
        guard: SecurityGuard | None = None,
    ) -> None:
        self._store = store
        self._guard = guard

    def _namespace(self, project_id: uuid.UUID) -> tuple[str, ...]:
        return ("project", str(project_id), "sphere")

    async def get(self, *, project_id: uuid.UUID) -> SphereData:
        ns = self._namespace(project_id)
        items = await self._store.asearch(ns, limit=100)
        content = _format_full_sphere(list(items))
        if items:
            updated_at = max(i.updated_at for i in items)
        else:
            updated_at = datetime.now(timezone.utc)
        return SphereData(project_id=project_id, content=content, updated_at=updated_at)

    async def update(self, *, project_id: uuid.UUID, content: str) -> SphereData:
        if self._guard is not None:
            result = await self._guard.check(
                content,
                Checkpoint.KS_WRITE_REST,
                trace_ctx={
                    "top_level": True,
                    "project_id": str(project_id),
                    "scope": "ks",
                },
            )
            if result.verdict == Verdict.INJECTION:
                logger.warning(
                    "ks write injection blocked",
                    security_event=True,
                    checkpoint=Checkpoint.KS_WRITE_REST.value,
                    verdict=Verdict.INJECTION.value,
                    identifiers={"project_id": str(project_id)},
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
                            else "ks_write_rest"
                        ),
                    },
                )

        ns = self._namespace(project_id)

        # Parse incoming markdown into sections
        new_sections = _parse_markdown_sections(content)
        new_ids = set()

        for section_id, description, section_content in new_sections:
            key = f"section:{section_id}"
            new_ids.add(key)
            await self._store.aput(
                ns, key, {"description": description, "content": section_content}
            )

        # Delete sections not in new content
        existing = await self._store.asearch(ns, limit=100)
        for item in existing:
            if item.key not in new_ids:
                await self._store.adelete(ns, item.key)

        return await self.get(project_id=project_id)
