---
name: codex-cloud-bootstrap
description: >
  Runtime policy и cloud merge-policy для агента в OpenAI Codex Cloud
  sandbox на LearnFlow AI. Python 3.12, docker-less путь, Postgres и
  Redis как localhost-процессы.
  Используй когда: ты агент в Codex Cloud (codex-universal sandbox),
  AGENTS.md, async workflow, Python 3.14 vs 3.12, docker not found,
  codex-universal.
---

# Codex Cloud runtime policy

## Старт сессии

1. Прочитай `CLAUDE.md` (на него же указывает корневой `AGENTS.md` — это symlink). Там единые правила проекта: конвенции, hard rules, AIDD, Makefile interface.
2. Прочитай `doc/tech/conventions.md` § Cloud sessions — там зафиксирована cloud merge-policy.
3. Если окружение не соответствует policy ниже, проверь `doc/tech/setup/codex-cloud.md` и сообщи, какой шаг setup / maintenance / env vars выглядит сломанным.

## Runtime policy

В codex-universal base image системный Python — `3.14`. Проектный dev-loop фиксирован на `Python 3.12` (см. `backend/pyproject.toml`). Под 3.14 нестабилен uvicorn reloader и Pydantic V1 совместимость, поэтому **всегда работай под 3.12**:

```bash
uv python install 3.12
uv sync --all-packages --python 3.12
```

Если окружение уже подготовлено Codex Environment setup script, не переустанавливай зависимости без причины. Все `make`-таргеты используют активную venv.

## Docker-less путь

Docker внутри codex-universal sandbox **архитектурно отсутствует** (`docker: command not found`). Все `make docker-*` таргеты непригодны.

Backend и frontend запускаются процессами:

```bash
make dev
make dev-fe
```

Postgres и Redis ожидаются уже запущенными локальными процессами внутри Codex container.

`DATABASE_URL` и `REDIS_URL` в env должны указывать на `host=localhost`, а не `host=db` / `host=redis` как в локальном `.env` — потому что backend в Codex запускается процессом, не контейнером в docker-сети.

Setup / maintenance scripts для Codex Environment UI живут в `doc/tech/setup/codex-cloud.md`. Это human-facing инструкция, а не регулярный agent context.

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
