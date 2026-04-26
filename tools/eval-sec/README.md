# learnflow-eval-sec

> **Status: archived (parked) 2026-04-26.** Track B harness feat-006 Security 2.0. Полный single-run проведён, репрезентативные кейсы разобраны вручную через Langfuse UI; регулярного использования не предполагается. Пакет **отключён от uv-workspace и Makefile/CI**, код оставлен на месте на случай возврата. См. [summary.md §Track B archived](../../doc/tasks/iterations/post-mvp/feat-006-security-2.0/summary.md).

Security 2.0 eval harness: двухфазный harvest из Langfuse → HTTP runner против публичного API → отчёт.

## Reactivate (если понадобится)

1. В корневом `pyproject.toml` вернуть `tools/eval-sec` в `[tool.uv.workspace] members`.
2. В `Makefile` вернуть macro `LOAD_ENV_EVAL`, target'ы `eval-sec-harvest` / `eval-sec-run` / `eval-sec-report`, строку `uv run --package learnflow-eval-sec mypy tools/eval-sec/src/` в `check`, а также `.PHONY`-записи.
3. `uv sync` подтянет deps пакета обратно в lockfile.
4. Заполнить `.env.eval` в корне на основе `tools/eval-sec/.env.example`. Langfuse creds читаются из `.env`/`.env.local`.

## Workflow (после reactivate)

```bash
# 1. Recon (Phase 4.1) — один раз, результат в recon-notes.md

# 2. Harvest — собрать cases.jsonl из Langfuse
make eval-sec-harvest

# 3. Run — прогнать атаки против dev-backend'а (make dev должен быть запущен)
make eval-sec-run

# 4. Report — human-readable summary.md
make eval-sec-report
```

## Rate-limit safety

`POST /api/auth/login` ограничен 5/60с на `name:ip` (backend `auth.py:101`).
Runner при 409 на register (т.е. user существует, но пароль не совпал) падает fail-fast —
никаких retry-циклов на 401 нет. Перед запуском проверь `EVAL_RUNNER_PASSWORD`
в `.env.eval`.

## Артефакты

- `datasets/cases.jsonl` (versioned) — harvest attack cases + attack boundary probes.
- `datasets/boundary_benign.jsonl` (versioned) — benign boundary probes (auto, из `boundary_probes.py`).
- `datasets/benign_smoke.jsonl` (versioned) — ручные benign smoke cases.
- `reports/<timestamp>/{results.json,summary.md}` — per-run (gitignored).

## Hermetic boundary

Пакет **не** импортирует из `backend/`. Общение с системой — только HTTP + Langfuse API.
Tripwire — TC-6.5.1: `! grep -rE "^from (app|agent|services|backend)\." tools/eval-sec/src/`.

## Контекст

- [recon-notes.md](recon-notes.md) — результаты Phase 4.1 recon: объём trace'ов red-team user'а, verdict-распределение, edge-cases.
- [../../doc/tasks/iterations/post-mvp/feat-006-security-2.0/plan-phase-4.md](../../doc/tasks/iterations/post-mvp/feat-006-security-2.0/plan-phase-4.md) — implementation plan Track B (этот пакет).
- [../../doc/tasks/iterations/post-mvp/feat-006-security-2.0/test-cases.md](../../doc/tasks/iterations/post-mvp/feat-006-security-2.0/test-cases.md) §6 — test cases покрытия.
