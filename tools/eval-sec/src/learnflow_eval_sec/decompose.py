from __future__ import annotations

import hashlib

from learnflow_eval_sec.langfuse_client import NormalizedTrace
from learnflow_eval_sec.models import Case


def _case_id(source_trace_ids: list[str], suffix: str = "") -> str:
    """Stable, deterministic id from the first source trace id (+ optional suffix)."""
    if not source_trace_ids:
        raise ValueError("source_trace_ids must be non-empty")
    seed = source_trace_ids[0] + (f":{suffix}" if suffix else "")
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"harvest-{digest}"


def decompose_session(
    session_id: str | None,
    traces: list[NormalizedTrace],
) -> list[Case]:
    """Split one session (list of traces sorted ASC) into attack cases.

    Bright-line rule (§7.2 design-brief):
      - One `Case(kind="attack")` per INJECTION trace, with prefix of CLEAN user messages
        seen BEFORE that INJECTION. Blocked msg is appended at the end.
      - If the session has zero INJECTION verdicts, emit one Case(kind="attack") with
        all user messages — a "Sec 2.0 candidate": Sec 1.0 let it through.
    """

    clean_prefix: list[str] = []
    source_prefix_ids: list[str] = []
    cases: list[Case] = []
    has_any_injection = False

    for t in traces:
        if not t.input:
            continue
        if t.verdict == "INJECTION":
            has_any_injection = True
            source_ids = source_prefix_ids + [t.trace_id]
            cases.append(
                Case(
                    case_id=_case_id(source_ids, suffix=str(len(cases))),
                    kind="attack",
                    messages=clean_prefix + [t.input],
                    source_trace_ids=source_ids,
                    notes=(
                        f"harvested: injection trace at {t.timestamp.isoformat()}"
                        + (f" (session={session_id})" if session_id else "")
                    ),
                )
            )
            # Blocked message does NOT enter the agent's history — do not append to prefix.
        else:
            clean_prefix.append(t.input)
            source_prefix_ids.append(t.trace_id)

    if not has_any_injection and clean_prefix:
        cases.append(
            Case(
                case_id=_case_id(source_prefix_ids),
                kind="attack",
                messages=clean_prefix,
                source_trace_ids=source_prefix_ids,
                notes=(
                    "harvested: session with 0 blocked — Sec 2.0 candidate"
                    + (f" (session={session_id})" if session_id else "")
                ),
            )
        )

    return cases
