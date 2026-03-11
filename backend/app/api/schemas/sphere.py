from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class SphereUpdate(BaseModel):
    content: str


class SphereResponse(BaseModel):
    project_id: uuid.UUID
    content: str
    updated_at: datetime
