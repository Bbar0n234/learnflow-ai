from enum import Enum
from typing import Any

from pydantic import BaseModel


class SecurityVerdict(str, Enum):
    CLEAN = "CLEAN"
    SUSPICIOUS = "SUSPICIOUS"
    INJECTION = "INJECTION"


class GuardResult(BaseModel):
    verdict: SecurityVerdict
    reason: str | None = None
    duration_ms: int
    details: str | None = None


class SecurityConfig(BaseModel):
    guard_model: str
    guard_extra_body: dict[str, Any] = {}
    max_retries: int = 3
    temperature: float = 0.0
