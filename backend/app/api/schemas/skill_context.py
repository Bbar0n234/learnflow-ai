from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# Business invariants (design-brief § Лимиты) — mirrored, not imported, from
# the agent-tool counterparts (`app/agent/tools/skill_context.py`): the REST
# and tool paths are two independent enforcement points by design (Pydantic
# here, plain checks there), same as `_MAX_SKILL_CONTEXT_DOCUMENTS` in
# `app/agent/tools/skills.py` mirrors `_MAX_DOCUMENTS_PER_SKILL` there.
_MAX_DESCRIPTION_LENGTH = 200
_MAX_CONTENT_LENGTH = 20_000


class SkillContextDocument(BaseModel):
    key: str
    description: str
    content: str
    created_at: datetime
    updated_at: datetime


class SkillContextGroup(BaseModel):
    skill_name: str
    in_library: bool
    documents: list[SkillContextDocument]


class SkillContextListResponse(BaseModel):
    skills: list[SkillContextGroup]


class SkillContextUpdate(BaseModel):
    description: str = Field(max_length=_MAX_DESCRIPTION_LENGTH)
    content: str = Field(max_length=_MAX_CONTENT_LENGTH)
