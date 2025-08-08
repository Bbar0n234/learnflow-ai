# UV Dependency Management — LearnFlow AI

Этот документ описывает рабочие практики управления зависимостями через UV для монорепозитория LearnFlow AI.

## Архитектура workspace

В проекте используется UV workspace с несколькими Python‑пакетами:

```
learnflow-ai/
├── pyproject.toml            # Root UV workspace
├── uv.lock                   # Единый lockfile для всего workspace
├── learnflow/                # API/Workflow сервис (FastAPI, LangGraph)
│   └── pyproject.toml        # Зависимости сервиса learnflow
├── bot/                      # Telegram бот (aiogram)
│   └── pyproject.toml        # Зависимости сервиса bot
├── web-ui/                   # React SPA (Node/npm, вне UV)
└── ...
```

Root `pyproject.toml` (workspace):

```toml
[tool.uv.workspace]
members = [
  "learnflow",
  "bot"
]
```

Ключевые особенности:
- Единый `uv.lock` для воспроизводимых сборок.
- Изоляция зависимостей по пакетам (`--package`).
- Группы зависимостей по окружениям: `prod`, `dev`, `test`.

## Группы зависимостей

- prod: минимально необходимые зависимости для запуска сервиса.
- dev: инструменты разработки (ruff, mypy, black и т. п.).
- test: pytest и утилиты тестирования.

Примеры:
```bash
# Установка всех зависимостей по умолчанию
uv sync

# Только dev‑инструменты (в дополнение к базовым для пакетов)
uv sync --group dev

# Комбинирование групп
uv sync --group dev --group test
```

## Операции по пакетам

```bash
# Синхронизация конкретного пакета
uv sync --package learnflow
uv sync --package bot

# Запуск команд в контексте пакета
uv run --package learnflow python -m learnflow.main
uv run --package bot python -m bot.main

# Добавление зависимости в конкретный пакет/группу
uv add fastapi --package learnflow --group prod
uv add ruff --package learnflow --group dev
uv add pytest --package bot --group test

# Удаление зависимости
uv remove fastapi --package learnflow --group prod
```

## Практики и правила

1) Не редактировать `pyproject.toml` вручную — использовать только UV‑команды.
2) Держать зависимости минимальными на пакет и на группу.
3) Регулярно обновлять и проверять `uv.lock` в PR.
4) Для фронтенда `web-ui/` зависимости управляются npm/pnpm — вне UV.

## Диагностика и аудит

```bash
# Дерево зависимостей
uv tree
uv tree --package learnflow

# Апдейты
uv sync --upgrade

# Прогон тестов пакета
uv run --package learnflow pytest
uv run --package bot pytest
```

## CI/CD и прод

В Docker‑образах использовать `uv sync --group prod` для установки только production‑зависимостей соответствующего пакета, а запуск через `uv run --package <pkg> ...`.

Пример (псевдо‑шаги):
```bash
uv sync --package learnflow --group prod --no-dev
uv run --package learnflow uvicorn learnflow.main:app --host 0.0.0.0 --port 8000
```

## Краткая памятка

```bash
uv sync                          # установить зависимости всего workspace
uv sync --package learnflow      # установить зависимости только для learnflow
uv add <pkg> --package bot       # добавить зависимость в bot
uv run --package bot pytest      # запустить тесты бота
uv tree --package learnflow      # посмотреть дерево зависимостей
```

