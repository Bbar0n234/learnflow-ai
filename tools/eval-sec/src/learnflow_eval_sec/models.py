from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

CaseKind = Literal["attack", "benign"]
CaseOutcome = Literal["PENDING", "PASS", "FAIL", "ERROR"]


class Case(BaseModel):
    """A single eval case: ordered list of user messages + expected behavior."""

    case_id: str
    kind: CaseKind
    messages: list[str]
    source_trace_ids: list[str] = Field(default_factory=list)
    notes: str = ""


class SseEventRecord(BaseModel):
    """A raw SSE event observed during a case run."""

    type: str
    data: dict[str, Any] = Field(default_factory=dict)


class CaseResult(BaseModel):
    """Per-case outcome + diagnostics from a runner pass."""

    case_id: str
    kind: CaseKind
    source_trace_ids: list[str] = Field(default_factory=list)
    outcome: CaseOutcome = "PENDING"
    blocked_on_message: int | None = (
        None  # 0-based index of msg that triggered security_block
    )
    layer: str | None = (
        None  # raw value from SSE data.reason (or block_reason in Sec 1.0)
    )
    error_detail: dict[str, Any] | None = None
    messages_sent: int = 0
    sse_events: list[SseEventRecord] = Field(default_factory=list)
    started_at: datetime | None = None
    duration_ms: float | None = None


class LeakedCaseSummary(BaseModel):
    case_id: str
    source_trace_ids: list[str]
    messages_preview: list[str]


class ErroredCaseSummary(BaseModel):
    case_id: str
    kind: CaseKind
    error_detail: dict[str, Any] | None
    messages_sent: int


class RunReport(BaseModel):
    """Aggregate report written as results.json."""

    run_id: str
    backend_base_url: str
    backend_version_hint: str | None = None
    project_id: str | None = None
    started_at: datetime
    finished_at: datetime
    cases_total: int
    cases_attack: int
    cases_benign: int
    attack_passed: int
    attack_failed: int
    benign_passed: int
    benign_failed: int
    errored: int
    attack_survival_rate: float | None = None
    benign_preservation: float | None = None
    layer_breakdown: dict[str, int] = Field(default_factory=dict)
    leaked_cases: list[LeakedCaseSummary] = Field(default_factory=list)
    errored_cases: list[ErroredCaseSummary] = Field(default_factory=list)
    results: list[CaseResult] = Field(default_factory=list)
