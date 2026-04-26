"""Scripted harvest entry point: python -m learnflow_eval_sec.harvest."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from langfuse import Langfuse

from learnflow_eval_sec import boundary_probes
from learnflow_eval_sec.decompose import decompose_session
from learnflow_eval_sec.langfuse_client import NormalizedTrace, pull_traces
from learnflow_eval_sec.models import Case

DEFAULT_USER_ID = "40f3ea08-aac9-422a-bf32-078b61565c5f"
DEFAULT_ENVIRONMENT = "production"
PKG_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES_PATH = PKG_ROOT / "datasets" / "cases.jsonl"
DEFAULT_BOUNDARY_BENIGN_PATH = PKG_ROOT / "datasets" / "boundary_benign.jsonl"


def _parse_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="learnflow_eval_sec.harvest",
        description="Pull red-team traces from Langfuse and build cases.jsonl.",
    )
    parser.add_argument(
        "--user-id",
        default=os.environ.get("EVAL_HARVEST_USER_ID", DEFAULT_USER_ID),
        help="Red-team user_id in Langfuse.",
    )
    parser.add_argument(
        "--environment",
        default=os.environ.get(
            "EVAL_HARVEST_ENVIRONMENT",
            os.environ.get("LANGFUSE_TRACING_ENVIRONMENT", DEFAULT_ENVIRONMENT),
        ),
        help="Langfuse environment filter.",
    )
    parser.add_argument("--from-timestamp", default=None, help="ISO 8601 lower bound.")
    parser.add_argument("--to-timestamp", default=None, help="ISO 8601 upper bound.")
    parser.add_argument("--trace-name", default="agent-run")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_CASES_PATH),
        help="Path to cases.jsonl.",
    )
    parser.add_argument(
        "--boundary-benign-output",
        default=str(DEFAULT_BOUNDARY_BENIGN_PATH),
        help="Path to boundary_benign.jsonl.",
    )
    parser.add_argument(
        "--include-boundary-probes",
        dest="include_boundary_probes",
        action="store_true",
        default=True,
    )
    parser.add_argument(
        "--no-boundary-probes",
        dest="include_boundary_probes",
        action="store_false",
    )
    return parser.parse_args(argv)


def _group_by_session(
    traces: list[NormalizedTrace],
) -> list[tuple[str | None, list[NormalizedTrace]]]:
    buckets: dict[str | None, list[NormalizedTrace]] = defaultdict(list)
    for t in traces:
        buckets[t.session_id].append(t)
    # Deterministic ordering of sessions: by the first trace_id (str) within each bucket.
    ordered: list[tuple[str | None, list[NormalizedTrace]]] = []
    for session_id, items in buckets.items():
        items.sort(key=lambda x: x.timestamp)
        ordered.append((session_id, items))
    ordered.sort(key=lambda pair: pair[1][0].trace_id)
    return ordered


def _sort_cases(cases: list[Case]) -> list[Case]:
    def key(c: Case) -> tuple[str, str, str]:
        first = c.source_trace_ids[0] if c.source_trace_ids else ""
        return (first, c.notes, c.case_id)

    return sorted(cases, key=key)


def _write_jsonl(path: Path, cases: list[Case]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [c.model_dump_json() for c in cases]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def run(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    lf = Langfuse()
    traces = pull_traces(
        lf,
        user_id=args.user_id,
        environment=args.environment,
        from_ts=_parse_iso(args.from_timestamp),
        to_ts=_parse_iso(args.to_timestamp),
        trace_name=args.trace_name,
    )

    sessions = _group_by_session(traces)

    attack_cases: list[Case] = []
    for session_id, items in sessions:
        attack_cases.extend(decompose_session(session_id, items))

    boundary_benign_cases: list[Case] = []
    if args.include_boundary_probes:
        attack_cases.extend(boundary_probes.attack_probes())
        boundary_benign_cases.extend(boundary_probes.benign_probes())

    attack_cases = _sort_cases(attack_cases)
    boundary_benign_cases = _sort_cases(boundary_benign_cases)

    cases_path = Path(args.output)
    boundary_path = Path(args.boundary_benign_output)
    _write_jsonl(cases_path, attack_cases)
    _write_jsonl(boundary_path, boundary_benign_cases)

    print(
        json.dumps(
            {
                "traces_pulled": len(traces),
                "sessions": len(sessions),
                "cases_written": len(attack_cases),
                "boundary_benign_written": len(boundary_benign_cases),
                "cases_path": str(cases_path),
                "boundary_benign_path": str(boundary_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(run())
