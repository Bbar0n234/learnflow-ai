from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from langfuse import Langfuse


@dataclass(frozen=True)
class NormalizedTrace:
    """Minimal projection of a Langfuse trace needed for case decomposition."""

    trace_id: str
    session_id: str | None
    timestamp: datetime
    input: str
    verdict: str  # CLEAN | SUSPICIOUS | INJECTION | UNKNOWN


def _extract_input(trace: Any) -> str:
    raw = getattr(trace, "input", None)
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    # Some trace objects wrap input as dict/list — keep conservative, str-ify.
    return str(raw)


def _pull_verdict(lf: Langfuse, trace_id: str) -> str:
    response = lf.api.scores.get_many(
        trace_id=trace_id,
        name="security_verdict",
        data_type="CATEGORICAL",
        limit=1,
    )
    data = getattr(response, "data", None) or []
    if not data:
        return "UNKNOWN"
    score = data[0]
    value = getattr(score, "string_value", None) or getattr(score, "value", None)
    if value is None:
        return "UNKNOWN"
    return str(value)


def pull_traces(
    lf: Langfuse,
    user_id: str,
    environment: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    trace_name: str = "agent-run",
    page_size: int = 100,
    progress: bool = True,
) -> list[NormalizedTrace]:
    """Fetch red-team traces + their security_verdict score.

    Returns traces sorted by timestamp ASC, deduplicated by id.
    Traces with empty input or missing session_id are kept — caller decides filtering.
    """

    seen: dict[str, NormalizedTrace] = {}
    page = 1
    processed = 0
    while True:
        kwargs: dict[str, Any] = {
            "user_id": user_id,
            "name": trace_name,
            "page": page,
            "limit": page_size,
        }
        if environment is not None:
            kwargs["environment"] = environment
        if from_ts is not None:
            kwargs["from_timestamp"] = from_ts
        if to_ts is not None:
            kwargs["to_timestamp"] = to_ts

        response = lf.api.trace.list(**kwargs)
        traces = getattr(response, "data", None) or []
        meta = getattr(response, "meta", None)
        total_pages = getattr(meta, "total_pages", None) if meta is not None else None
        total_items = getattr(meta, "total_items", None) if meta is not None else None
        if progress and page == 1:
            print(
                f"[harvest] page 1/{total_pages}, total_items={total_items}",
                file=sys.stderr,
                flush=True,
            )
        if not traces:
            break

        for trace in traces:
            trace_id = trace.id
            if trace_id in seen:
                continue
            verdict = _pull_verdict(lf, trace_id)
            seen[trace_id] = NormalizedTrace(
                trace_id=trace_id,
                session_id=getattr(trace, "session_id", None),
                timestamp=trace.timestamp,
                input=_extract_input(trace),
                verdict=verdict,
            )
            processed += 1
            if progress and processed % 25 == 0:
                print(
                    f"[harvest] processed {processed}/{total_items or '?'} traces",
                    file=sys.stderr,
                    flush=True,
                )

        if total_pages is None or page >= total_pages:
            break
        page += 1

    if progress:
        print(
            f"[harvest] done: processed {processed} traces", file=sys.stderr, flush=True
        )
    return sorted(seen.values(), key=lambda t: t.timestamp)
