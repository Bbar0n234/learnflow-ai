# Implementation Plan: chore-002 — Code Quality Tooling

## Context

Итерация chore-002 из `doc/tasks/tasklist-infra.md`. Настройка трёхуровневой защиты качества кода для backend (ruff format → ruff check → mypy) и ESLint + Prettier для frontend. MVP-каркас с базовыми правилами.

**Blocked by:** chore-001 (Done)
**Ветка:** `chore/002-code-quality`

## Актуальные версии инструментов

| Tool | Version | Source |
|------|---------|--------|
| ruff | 0.15.5 | PyPI (2026-03-05) |
| mypy | 1.19.1 | PyPI (2025-12-15) |
| pre-commit | 4.5.1 | PyPI (2025-12-16) |
| ESLint | 10.0.3 | npm (2026-03-06) |
| typescript-eslint | latest (supports ESLint ^10) | npm |
| Prettier | 3.8.1 | npm (2026-01-21) |
| eslint-config-prettier | latest | npm |

**ESLint 10:** вышел 2026-02-06, flat config only (eslintrc полностью удалён). Node >=20.19.0 — наш Node 22.22.0 подходит. typescript-eslint поддерживает ^10.0.0. Для нового проекта — правильный выбор (v9 в maintenance mode).

## Файлы

### Создать
| Файл | Назначение |
|------|-----------|
| `ruff.toml` | Конфиг ruff (lint + format) |
| `.pre-commit-config.yaml` | Pre-commit hooks |
| `frontend/eslint.config.mjs` | ESLint flat config |
| `.mcp.json` | ESLint MCP для Claude Code |

### Изменить
| Файл | Изменение |
|------|----------|
| `pyproject.toml` | Добавить `[dependency-groups]` dev (ruff, mypy, pre-commit) |
| `backend/pyproject.toml` | Добавить pydantic dep + `[tool.mypy]` + `[tool.pydantic-mypy]` |
| `frontend/package.json` | Добавить devDependencies (eslint, prettier, typescript-eslint, eslint-config-prettier, typescript) |

## Шаги реализации

### Шаг 1: Python dev-зависимости

**`pyproject.toml`** — добавить dependency group:
```toml
[dependency-groups]
dev = ["ruff>=0.15", "mypy>=1.19", "pre-commit>=4.5"]
```

**`backend/pyproject.toml`** — добавить pydantic (нужен для mypy pydantic plugin, входит в стек проекта — FastAPI):
```toml
dependencies = ["pydantic>=2.0"]
```

Выполнить `uv sync` для установки.

### Шаг 2: ruff.toml

Отдельный файл в корне (не в pyproject.toml — чище, ruff сканирует только .py файлы).

```toml
target-version = "py312"
line-length = 88

[lint]
select = ["E", "W", "F", "B", "I", "SIM"]
ignore = ["E501"]
fixable = ["ALL"]

[lint.per-file-ignores]
"__init__.py" = ["F401"]

[format]
quote-style = "double"
indent-style = "space"
```

Правила по таклисту: E (pycodestyle errors), W (warnings), F (Pyflakes), B (flake8-bugbear), I (isort), SIM (flake8-simplify). E501 (line too long) — ignore, контролируется форматером.

### Шаг 3: mypy в backend/pyproject.toml

```toml
[tool.mypy]
python_version = "3.12"
plugins = ["pydantic.mypy"]
disallow_untyped_defs = true
warn_redundant_casts = true
warn_unused_ignores = true
check_untyped_defs = true
no_implicit_reexport = true

[tool.pydantic-mypy]
init_forbid_extra = true
init_typed = true
warn_required_dynamic_aliases = true
```

### Шаг 4: .pre-commit-config.yaml

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.15.5
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: local
    hooks:
      - id: mypy
        name: mypy
        entry: uv run mypy
        language: system
        types: [python]
        pass_filenames: false
        args: [backend/]
```

**Почему local hook для mypy:** `mirrors-mypy` запускает mypy в изолированном virtualenv без доступа к зависимостям проекта (pydantic и пр.). Local hook через `uv run mypy` использует проектный .venv — видит все зависимости.

Выполнить `uv run pre-commit install` для активации хуков.

### Шаг 5: Frontend — npm dependencies

```bash
cd frontend && npm install --save-dev \
  eslint \
  @eslint/js \
  typescript \
  typescript-eslint \
  eslint-config-prettier \
  prettier
```

**eslint-config-prettier** (не eslint-plugin-prettier): отключает конфликтующие ESLint-правила. Prettier запускается отдельно — стандартный подход, рекомендованный Prettier.

`package-lock.json` генерируется автоматически — коммитится в репозиторий (стандартная практика).

### Шаг 6: frontend/eslint.config.mjs

```mjs
import eslint from "@eslint/js";
import tseslint from "typescript-eslint";
import eslintConfigPrettier from "eslint-config-prettier";

export default tseslint.config(
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  eslintConfigPrettier,
  {
    ignores: ["dist/", "build/", "node_modules/"],
  },
);
```

`tseslint.configs.recommended` — как указано в таклисте (`@typescript-eslint/recommended`). Без type-checked — не требует tsconfig.json.

### Шаг 7: .mcp.json (ESLint MCP)

```json
{
  "mcpServers": {
    "eslint": {
      "command": "npx",
      "args": ["@eslint/mcp@latest"],
      "env": {}
    }
  }
}
```

Файл в корне проекта. Не попадает под `.claude/*.json` в .gitignore (строка 202) — паттерн матчит только `.claude/` подкаталог. `.mcp.json` в корне коммитится в репозиторий.

## Верификация (критерии приёмки)

```bash
# Backend
uv run ruff check .              # должен пройти без ошибок
uv run ruff format --check .     # должен пройти без ошибок
uv run mypy backend/             # должен пройти без ошибок

# Pre-commit
git commit --allow-empty -m "test"  # должен триггерить хуки (ruff + mypy)

# Frontend
cd frontend && npx eslint .         # должен пройти
cd frontend && npx prettier --check .  # должен пройти
```

## Edge cases

**mypy на пустом backend/:** сейчас в `backend/` нет `.py` файлов. `mypy backend/` и pre-commit хук отработают мгновенно с `Success: no issues found`. Хук запускается при каждом коммите (включая frontend-only коммиты) с `pass_filenames: false` — overhead нулевой на пустой директории, станет релевантным при появлении Python-кода.

## Решения, принятые в плане

1. **ESLint 10** (не 9) — v10 released 2026-02, v9 в maintenance mode, новый проект, Node 22 совместим
2. **Local hook для mypy** — mirrors-mypy не видит зависимости проекта, `uv run mypy` решает
3. **eslint-config-prettier** (не eslint-plugin-prettier) — стандартная рекомендация Prettier, разделение concerns
4. **pydantic в backend deps** — нужен для mypy pydantic plugin из таклиста, входит в стек (FastAPI)
5. **Нет .prettierrc** — базовый конфиг = Prettier defaults (как указано: "базовый конфиг")
6. **ruff.toml отдельным файлом** — чище чем в pyproject.toml, стандартная практика
