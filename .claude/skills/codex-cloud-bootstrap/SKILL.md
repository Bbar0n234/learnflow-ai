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

## HTTP smoke в Codex Cloud

Codex Cloud command invocations могут не разделять localhost/network namespace для долгоживущих background-процессов. Dev-server, запущенный в одной команде, может оставаться видимым через `ps`, но `curl localhost:<port>` из следующей команды может не видеть его socket.

Не трактуй failed cross-invocation `curl` как доказательство, что backend/frontend сломан.

Надёжный паттерн для HTTP smoke: запусти server, дождись HTTP-ответа и останови server **внутри одной shell invocation**. Обязательно используй cleanup через `trap`.

Пример для backend:

```bash
set -euo pipefail

make dev >/tmp/learnflow-backend.log 2>&1 &
pid=$!
cleanup() { kill "$pid" 2>/dev/null || true; }
trap cleanup EXIT

for _ in $(seq 1 60); do
  curl -fsS http://127.0.0.1:8000/health && exit 0
  sleep 1
done

tail -120 /tmp/learnflow-backend.log
exit 1
```

Для frontend используй тот же паттерн с `make dev-fe` и `http://127.0.0.1:5173/`.

Если TCP-path не принципиален, backend endpoints можно проверять in-process через FastAPI app + `httpx.ASGITransport` / `TestClient`.

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
