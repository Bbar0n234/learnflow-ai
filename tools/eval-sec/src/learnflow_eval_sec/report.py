"""Render results.json → summary.md (Phase 4.4).

Entry point: python -m learnflow_eval_sec.report
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from learnflow_eval_sec.models import RunReport

PKG_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORTS_DIR = PKG_ROOT / "reports"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="learnflow_eval_sec.report",
        description="Render summary.md from a results.json.",
    )
    parser.add_argument(
        "--results",
        default=None,
        help="Path to results.json (default: latest under tools/eval-sec/reports/).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path to summary.md (default: sibling of results.json).",
    )
    parser.add_argument(
        "--langfuse-base-url",
        default=os.environ.get("LANGFUSE_BASE_URL", ""),
        help="Used to build trace links for leaked cases.",
    )
    parser.add_argument(
        "--langfuse-project-id",
        default=os.environ.get("LANGFUSE_PROJECT_ID", ""),
        help="Optional — if set, trace links include project path.",
    )
    return parser.parse_args(argv)


def _latest_results(reports_dir: Path) -> Path:
    if not reports_dir.exists():
        raise FileNotFoundError(
            f"reports dir {reports_dir} does not exist — run `make eval-sec-run` first"
        )
    candidates = sorted(
        [p / "results.json" for p in reports_dir.iterdir() if p.is_dir()],
        key=lambda p: p.stat().st_mtime if p.exists() else 0.0,
        reverse=True,
    )
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(f"no results.json found under {reports_dir}")


def _trace_link(trace_id: str, base_url: str, project_id: str) -> str:
    base = base_url.rstrip("/")
    if not base:
        return trace_id
    if project_id:
        return f"[{trace_id[:8]}…]({base}/project/{project_id}/traces/{trace_id})"
    return f"[{trace_id[:8]}…]({base}/trace/{trace_id})"


def _preview(messages: list[str], max_chars: int = 200) -> str:
    if not messages:
        return "—"
    first = messages[0].replace("\n", " ").strip()
    if len(first) > max_chars:
        first = first[: max_chars - 1] + "…"
    return first


def _fmt_ratio(passed: int, denom: int, ratio: float | None) -> str:
    if ratio is None or denom == 0:
        return "— (no cases in denominator)"
    return f"{passed} / {denom} = {ratio * 100:.1f}%"


def render(report: RunReport, langfuse_base: str, langfuse_project: str) -> str:
    lines: list[str] = []
    lines.append("# Security 2.0 — Eval Report")
    lines.append("")
    lines.append(f"**Run ID:** `{report.run_id}`")
    lines.append(f"**Backend:** `{report.backend_base_url}`")
    if report.project_id:
        lines.append(f"**Project:** `{report.project_id}`")
    lines.append(
        f"**Started:** {report.started_at.isoformat()} — "
        f"**Finished:** {report.finished_at.isoformat()}"
    )
    lines.append(
        f"**Cases:** total={report.cases_total}, attack={report.cases_attack}, "
        f"benign={report.cases_benign}, errored={report.errored}"
    )
    lines.append("")
    lines.append("## Ключевые метрики")
    lines.append("")
    lines.append("> Знаменатель метрик считается без ERROR-кейсов (§R3 plan-phase-4).")
    lines.append("")
    lines.append("| Метрика | Значение |")
    lines.append("|---|---|")
    attack_denom = report.attack_passed + report.attack_failed
    benign_denom = report.benign_passed + report.benign_failed
    lines.append(
        f"| Attack survival rate | {_fmt_ratio(report.attack_passed, attack_denom, report.attack_survival_rate)} |"
    )
    lines.append(
        f"| Benign preservation | {_fmt_ratio(report.benign_passed, benign_denom, report.benign_preservation)} |"
    )
    lines.append("")

    lines.append("## Layer breakdown (blocked attacks)")
    lines.append("")
    lines.append(
        "Значения — raw SSE `data.reason`. В Sec 1.0 это `block_reason` "
        "(`prompt_injection`/`canary_leak`); в Sec 2.0 — `detection_layer.value` "
        "(`canary`/`unicode`/`paired`/`fragment`/`llm_classifier`)."
    )
    lines.append("")
    if report.layer_breakdown:
        lines.append("| layer (SSE `data.reason`) | N |")
        lines.append("|---|---|")
        for layer, count in sorted(
            report.layer_breakdown.items(), key=lambda kv: (-kv[1], kv[0])
        ):
            lines.append(f"| `{layer}` | {count} |")
    else:
        lines.append("_No blocks recorded._")
    lines.append("")

    lines.append("## Leaked cases (attack FAIL)")
    lines.append("")
    if report.leaked_cases:
        lines.append("| case_id | source_trace_ids | preview | Langfuse |")
        lines.append("|---|---|---|---|")
        for c in report.leaked_cases:
            traces = ", ".join(c.source_trace_ids) if c.source_trace_ids else "—"
            links = (
                ", ".join(
                    _trace_link(t, langfuse_base, langfuse_project)
                    for t in c.source_trace_ids
                )
                if c.source_trace_ids
                else "—"
            )
            lines.append(
                f"| `{c.case_id}` | `{traces}` | {_preview(c.messages_preview)} | {links} |"
            )
    else:
        lines.append("_Empty — all attack cases were blocked._")
    lines.append("")

    fp_cases = [r for r in report.results if r.kind == "benign" and r.outcome == "FAIL"]
    lines.append("## FP cases (benign FAIL)")
    lines.append("")
    if fp_cases:
        lines.append("| case_id | layer | duration_ms |")
        lines.append("|---|---|---|")
        for r in fp_cases:
            dur = f"{r.duration_ms:.0f}" if r.duration_ms is not None else "—"
            lines.append(f"| `{r.case_id}` | `{r.layer or '—'}` | {dur} |")
    else:
        lines.append("_Empty — no benign case was falsely blocked._")
    lines.append("")

    lines.append("## ERROR cases (backend failures, excluded from metrics)")
    lines.append("")
    if report.errored_cases:
        lines.append("| case_id | kind | messages_sent | error_detail |")
        lines.append("|---|---|---|---|")
        for ec in report.errored_cases:
            detail = (
                str(ec.error_detail).replace("|", "\\|")
                if ec.error_detail is not None
                else "—"
            )
            lines.append(
                f"| `{ec.case_id}` | `{ec.kind}` | {ec.messages_sent} | {detail[:200]} |"
            )
    else:
        lines.append("_Empty — no backend errors during the run._")
    lines.append("")

    return "\n".join(lines) + "\n"


def run(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    results_path = (
        Path(args.results) if args.results else _latest_results(DEFAULT_REPORTS_DIR)
    )
    report = RunReport.model_validate_json(results_path.read_text(encoding="utf-8"))
    output_path = (
        Path(args.output) if args.output else results_path.with_name("summary.md")
    )
    output_path.write_text(
        render(report, args.langfuse_base_url, args.langfuse_project_id),
        encoding="utf-8",
    )
    print(f"summary.md written: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
