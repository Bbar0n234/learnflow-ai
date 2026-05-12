# AGENTS.md

> Этот файл — для агентов в OpenAI Codex Cloud. Локальные разработчики и Claude Code on the web используют `CLAUDE.md`.

## Быстрый старт
- Сначала прочитай `CLAUDE.md`, затем `doc/index.md` и `doc/tech/conventions.md`.
- Работай через `Makefile` цели, не через ad-hoc команды, если цель уже существует.
- Cloud merge-policy: работай в feature-ветке и открывай PR в `develop`; **не делай merge самостоятельно**.

## Python / Runtime policy для Codex Cloud
- В Codex base image системный Python обычно `3.14`, но проектный dev-loop фиксирован на `Python 3.12`.
- Перед `uv sync` установи и используй Python 3.12:
  - `uv python install 3.12`
  - `uv sync --all-packages --python 3.12`

## Docker-less Cloud path
- В Codex Cloud Docker недоступен; backend поднимается process-based (Postgres + Redis + FastAPI отдельными процессами).
- Пошаговый runbook: `doc/research/cloud-sessions/codex-setup.md`.

## Канонические ссылки
- Док-навигация: `doc/index.md`
- Соглашения (hard rules, git flow, cloud policy): `doc/tech/conventions.md`
- Backend architecture: `doc/tech/backend.md`
- Auth/env требования: `doc/tech/auth.md`
