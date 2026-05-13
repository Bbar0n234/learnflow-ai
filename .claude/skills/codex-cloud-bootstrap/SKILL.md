---
name: codex-cloud-bootstrap
description: >
  Bootstrap, runtime policy и cloud merge-policy для агента в OpenAI
  Codex Cloud sandbox на LearnFlow AI. Python 3.12 setup, docker-less
  путь (Postgres + Redis процессами), Codex Environment UI (Setup
  script / Maintenance script / env vars).
  Используй когда: ты агент в Codex Cloud (codex-universal sandbox),
  AGENTS.md, async workflow, bootstrap в облаке, Python 3.14 vs 3.12,
  docker not found, Codex Environment, codex-universal.
---

# Codex Cloud bootstrap

## Старт сессии

1. Прочитай `CLAUDE.md` (на него же указывает корневой `AGENTS.md` — это symlink). Там единые правила проекта: конвенции, hard rules, AIDD, Makefile interface.
2. Прочитай `doc/tech/conventions.md` § Cloud sessions — там зафиксирована cloud merge-policy.
3. Если задача связана с настройкой Codex Environment UI (Setup script / Maintenance script / env vars) — открой `runbook.md` в этой же директории.

## Runtime policy

В codex-universal base image системный Python — `3.14`. Проектный dev-loop фиксирован на `Python 3.12` (см. `backend/pyproject.toml`). Под 3.14 нестабилен uvicorn reloader и Pydantic V1 совместимость, поэтому **всегда работай под 3.12**:

```bash
uv python install 3.12
uv sync --all-packages --python 3.12
```

Все `make`-таргеты используют активную venv, поэтому достаточно зафиксировать 3.12 в начале сессии.

## Docker-less путь

Docker внутри codex-universal sandbox **архитектурно отсутствует** (`docker: command not found`). Все `make docker-*` таргеты непригодны. Backend поднимается процессом (`make dev`), Postgres и Redis — через apt (детали bootstrap'а — в `runbook.md`).

`DATABASE_URL` и `REDIS_URL` в env должны указывать на `host=localhost`, а не `host=db` / `host=redis` как в локальном `.env` — потому что backend в Codex запускается процессом, не контейнером в docker-сети.

## Cloud merge-policy

Ты доводишь итерацию **только до feature-ветки**:

```
[ты в Codex]   feat-XXX → commit + push + PR (gh / GitHub MCP)
                                            │
                                            ▼
[архитектор]   pull → UI / интеграционная валидация → merge
   локально
```

**Merge в `develop` агент не выполняет.** Полный контекст и причина — `doc/tech/conventions.md` § Cloud sessions.

Push в feature-ветку: Codex обычно переименовывает её при push'е в `codex/<branch-name>` — это нормально, не блокер для последующего PR.
