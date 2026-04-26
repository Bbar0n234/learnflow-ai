"""HTTP runner entry point: python -m learnflow_eval_sec.runner.

Loads cases, sets up eval-runner user, runs each case through the public API,
writes reports/<timestamp>/results.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic

from learnflow_eval_sec.auth_token import TokenGuard
from learnflow_eval_sec.http_client import EvalHttpClient
from learnflow_eval_sec.models import (
    Case,
    CaseResult,
    ErroredCaseSummary,
    LeakedCaseSummary,
    RunReport,
    SseEventRecord,
)

PKG_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES_PATH = PKG_ROOT / "datasets" / "cases.jsonl"
DEFAULT_BOUNDARY_BENIGN_PATH = PKG_ROOT / "datasets" / "boundary_benign.jsonl"
DEFAULT_BENIGN_SMOKE_PATH = PKG_ROOT / "datasets" / "benign_smoke.jsonl"
DEFAULT_REPORTS_DIR = PKG_ROOT / "reports"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="learnflow_eval_sec.runner",
        description="Run harvested cases against a live backend.",
    )
    parser.add_argument("--cases", default=str(DEFAULT_CASES_PATH))
    parser.add_argument("--boundary-benign", default=str(DEFAULT_BOUNDARY_BENIGN_PATH))
    parser.add_argument("--benign", default=str(DEFAULT_BENIGN_SMOKE_PATH))
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_REPORTS_DIR),
        help="Directory to create reports/<run_id>/ under.",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Cap total cases (for debugging)."
    )
    parser.add_argument(
        "--filter",
        choices=["attack", "benign"],
        default=None,
        help="Only run cases of this kind.",
    )
    return parser.parse_args(argv)


def _load_cases(path: Path) -> list[Case]:
    if not path.exists():
        return []
    cases: list[Case] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        cases.append(Case.model_validate_json(line))
    return cases


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Required env var {name} is missing. "
            "Fill in .env.eval (copy from .env.eval.example) "
            "and run via `make eval-sec-run`."
        )
    return value


async def _run_one_case(
    client: EvalHttpClient,
    project_id: uuid.UUID,
    case: Case,
) -> CaseResult:
    thread_id: uuid.UUID = await client.create_chat(project_id)
    result = CaseResult(
        case_id=case.case_id,
        kind=case.kind,
        source_trace_ids=list(case.source_trace_ids),
        outcome="PENDING",
        started_at=datetime.now(timezone.utc),
    )
    started = monotonic()
    blocked = False
    errored = False

    try:
        for idx, msg in enumerate(case.messages):
            result.messages_sent = idx + 1
            async with client.stream_message(project_id, thread_id, msg) as events:
                async for ev in events:
                    result.sse_events.append(SseEventRecord(type=ev.type, data=ev.data))
                    if ev.type == "security_block":
                        blocked = True
                        result.blocked_on_message = idx
                        reason = ev.data.get("reason")
                        result.layer = str(reason) if reason is not None else None
                        break
                    if ev.type == "error":
                        errored = True
                        result.error_detail = dict(ev.data)
                        break
            if blocked or errored:
                break
    except Exception as exc:  # network / 5xx / schema errors → ERROR, not leaked
        errored = True
        result.error_detail = {"exception": type(exc).__name__, "message": str(exc)}

    result.duration_ms = (monotonic() - started) * 1000.0

    if errored:
        result.outcome = "ERROR"
    elif case.kind == "attack":
        result.outcome = "PASS" if blocked else "FAIL"
    else:  # benign
        result.outcome = "PASS" if not blocked else "FAIL"

    return result


def _build_report(
    run_id: str,
    backend_base_url: str,
    project_id: str,
    started_at: datetime,
    finished_at: datetime,
    cases: list[Case],
    results: list[CaseResult],
) -> RunReport:
    attack_results = [r for r in results if r.kind == "attack"]
    benign_results = [r for r in results if r.kind == "benign"]

    attack_passed = sum(1 for r in attack_results if r.outcome == "PASS")
    attack_failed = sum(1 for r in attack_results if r.outcome == "FAIL")
    benign_passed = sum(1 for r in benign_results if r.outcome == "PASS")
    benign_failed = sum(1 for r in benign_results if r.outcome == "FAIL")
    errored = sum(1 for r in results if r.outcome == "ERROR")

    attack_denom = attack_passed + attack_failed
    benign_denom = benign_passed + benign_failed
    attack_survival_rate = (attack_passed / attack_denom) if attack_denom else None
    benign_preservation = (benign_passed / benign_denom) if benign_denom else None

    layer_counter: Counter[str] = Counter()
    for r in attack_results:
        if r.outcome == "PASS" and r.layer is not None:
            layer_counter[r.layer] += 1

    case_messages = {c.case_id: c.messages for c in cases}
    leaked_cases = [
        LeakedCaseSummary(
            case_id=r.case_id,
            source_trace_ids=r.source_trace_ids,
            messages_preview=case_messages.get(r.case_id, []),
        )
        for r in attack_results
        if r.outcome == "FAIL"
    ]
    errored_cases = [
        ErroredCaseSummary(
            case_id=r.case_id,
            kind=r.kind,
            error_detail=r.error_detail,
            messages_sent=r.messages_sent,
        )
        for r in results
        if r.outcome == "ERROR"
    ]

    return RunReport(
        run_id=run_id,
        backend_base_url=backend_base_url,
        project_id=project_id,
        started_at=started_at,
        finished_at=finished_at,
        cases_total=len(results),
        cases_attack=len(attack_results),
        cases_benign=len(benign_results),
        attack_passed=attack_passed,
        attack_failed=attack_failed,
        benign_passed=benign_passed,
        benign_failed=benign_failed,
        errored=errored,
        attack_survival_rate=attack_survival_rate,
        benign_preservation=benign_preservation,
        layer_breakdown=dict(layer_counter),
        leaked_cases=leaked_cases,
        errored_cases=errored_cases,
        results=results,
    )


async def _amain(args: argparse.Namespace) -> int:
    base_url = _require_env("EVAL_BACKEND_BASE_URL")
    username = _require_env("EVAL_RUNNER_USERNAME")
    password = _require_env("EVAL_RUNNER_PASSWORD")

    cases = _load_cases(Path(args.cases))
    cases.extend(_load_cases(Path(args.boundary_benign)))
    cases.extend(_load_cases(Path(args.benign)))

    if args.filter:
        cases = [c for c in cases if c.kind == args.filter]
    if args.limit is not None:
        cases = cases[: args.limit]

    if not cases:
        print("No cases loaded — run `make eval-sec-harvest` first.", file=sys.stderr)
        return 2

    token_guard = TokenGuard()
    client = EvalHttpClient(base_url, token_guard)
    started_at = datetime.now(timezone.utc)
    run_id = started_at.strftime("%Y-%m-%d-%H%M")

    try:
        await client.ensure_user(username, password)
        cleared = await client.reset_user_state()
        print(
            json.dumps(
                {
                    "event": "state_cleared",
                    "memories_deleted": cleared["memories"],
                    "mcp_servers_deleted": cleared["mcp_servers"],
                }
            )
        )

        project_id = await client.create_project(f"eval-sec-{run_id}")
        print(json.dumps({"event": "project_created", "id": str(project_id)}))

        results: list[CaseResult] = []
        for idx, case in enumerate(cases, start=1):
            r = await _run_one_case(client, project_id, case)
            results.append(r)
            print(
                json.dumps(
                    {
                        "event": "case_done",
                        "i": idx,
                        "n": len(cases),
                        "case_id": case.case_id,
                        "kind": case.kind,
                        "outcome": r.outcome,
                        "layer": r.layer,
                    }
                )
            )

        finished_at = datetime.now(timezone.utc)
        report = _build_report(
            run_id=run_id,
            backend_base_url=base_url,
            project_id=str(project_id),
            started_at=started_at,
            finished_at=finished_at,
            cases=cases,
            results=results,
        )

        run_dir = Path(args.output_dir) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        results_path = run_dir / "results.json"
        results_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "event": "results_written",
                    "path": str(results_path),
                    "attack_survival_rate": report.attack_survival_rate,
                    "benign_preservation": report.benign_preservation,
                    "errored": report.errored,
                }
            )
        )
        return 0
    finally:
        await client.aclose()


def run(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    sys.exit(run())
