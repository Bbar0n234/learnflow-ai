# Tech Debt: Improve Prerequisites Documentation

## Problem

При клонировании репозитория и попытке запуска через `make local-dev` возникают неочевидные проблемы для новых пользователей:

1. **UV не установлен** - скрипт требует UV, но в README нет инструкций по его установке
2. **Python 3.11 отсутствует** - проект требует Python 3.11+, но:
   - Не указано как установить если у пользователя другая версия (например, Python 3.13)
   - Нет инструкций по использованию `uv python install 3.11`
   - Отсутствуют ссылки на альтернативные способы установки (system package manager, pyenv)
3. **Нет troubleshooting секции** - при ошибках пользователь не знает что делать

## Current State

В README.md секция "Предварительные требования" (строки 56-60):
```markdown
### Предварительные требования

- Docker и Docker Compose
- Python 3.11+ (для локальной разработки)
- API-ключи для выбранного вами LLM-провайдера
```

**Недостатки:**
- ❌ Нет упоминания про UV
- ❌ Нет инструкций по установке Python 3.11
- ❌ Нет ссылок на официальную документацию инструментов
- ❌ Не понятно что делать при проблемах

## Actual Error Example

```bash
$ make local-dev
error: No interpreter found for Python 3.11 in managed installations or search path
hint: A managed Python download is available for Python 3.11, but Python downloads
are set to 'manual', use `uv python install 3.11` to install the required version
```

Пользователь с Python 3.13 получает эту ошибку без понимания как её решить.

## Proposed Solution

### 1. Расширить секцию Prerequisites в README.md

Добавить детальные инструкции по установке:

- **UV Package Manager**
  - Команды для установки (Linux/macOS/Windows)
  - Проверка версии
  - Ссылка на официальную документацию

- **Python 3.11+**
  - Команда для проверки текущей версии
  - 3 способа установки:
    - Через UV (рекомендуется): `uv python install 3.11`
    - Через system package manager (apt/dnf/brew)
    - Через pyenv
  - Объяснение что делать если уже установлена другая версия

- **Docker и Docker Compose**
  - Ссылки на официальную документацию
  - Команды для проверки установки

### 2. Добавить Troubleshooting секцию

Основные проблемы:
- "No interpreter found for Python 3.11"
- "Port already in use"
- "Docker not running"

### 3. Создать `docs/troubleshooting.md`

Детальный справочник по решению проблем.

## Impact

**Текущее состояние:**
- Новые пользователи застревают на этапе установки
- Требуется гуглить решения
- Негативное первое впечатление от проекта

**После улучшения:**
- Пользователи могут запустить проект с первой попытки
- Понятный путь решения проблем
- Профессиональный уровень документации → больше звезд на GitHub

## References

Best practices от популярных проектов:
- [LangChain Prerequisites](https://github.com/langchain-ai/langchain)
- [FastAPI Installation](https://github.com/tiangolo/fastapi)
- [UV Documentation](https://docs.astral.sh/uv/)

## Priority

**Medium** - не критично для работы, но важно для user experience и популярности проекта.

## Estimated Effort

~2-3 часа на:
- Переписать секцию Prerequisites в README.md
- Создать docs/troubleshooting.md
- Улучшить комментарии в .env.local.example
