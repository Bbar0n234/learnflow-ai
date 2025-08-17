# Roadmap

| Milestone | Период | Цели | Ключевые инициативы | Статус |
| --- | --- | --- | --- | --- |
| Pre‑OSS Release | Q1 2025 | Docker Compose деплой; поддержка локальных LLM; Guardrails для безопасности; английский README с демо; минимальные тесты | INIT‑UI‑001, FEAT‑AI‑201, SEC‑LLM‑001, FEAT‑LLM‑301, REL‑OSS‑001 | Active |
| OSS Launch | Q1 2025 | Публичный релиз; статическая библиотека промптов; issue templates; демо-видео | REL‑OSS‑001, FEAT‑PROMPT‑401, COMM‑OSS‑501 | Planned |
| UI V1 | Q2 2025 | Real‑time обновления; продвинутый UI; экспорт PDF/DOCX | FEAT‑UI‑104, FEAT‑UI‑105, EXP‑DOC‑001 | Planned |
| Community Growth | Q2-Q3 2025 | YouTube контент; Jupyter демо; динамические промпты; активное сообщество | COMM‑OSS‑502, FEAT‑PROMPT‑402, DEV‑JUPYTER‑001 | Future |
| Post‑OSS: Telegram‑first | Q3 2025 | Основной UX в Telegram; экспорт в заметки | TG‑UX‑001, EXP‑NOTE‑001 | Future |

См. инициативы в `docs/backlog/` и ADR для детальной декомпозиции.

## Как читать названия инициатив (INIT‑UI‑001)

- Тип:
  - INIT — большая инициатива (несколько фич под одной целью)
  - FEAT — отдельная фича/итерация внутри инициативы
  - REL — задачи релиза (документация, лицензия и пр.)
- Область: UI, AI, OSS, TG (Telegram), EXP (экспорт) — помогает быстро понять, о чём задача
- Номер: просто порядковый, чтобы ссылаться (001, 103 и т. д.)

Примеры:
- INIT‑UI‑001 — базовая платформа UI + артефакты
- FEAT‑UI‑103 — интеграция LearnFlow с локальными артефактами (часть INIT‑UI‑001)
- REL‑OSS‑001 — подготовка к публикации исходников

Как пользоваться:
- При добавлении работы создавай файл в `docs/backlog/current/` с таким же названием.
- Внутри укажи: цель, план, DoD (критерии готовности), статус.
- После завершения перемести файл в `docs/backlog/archive/` и добавь краткое резюме в `docs/changelog.md`.

## Активные инициативы

### 📌 Текущий порядок реализации (август 2025)
1. **FEAT‑AI‑201** — Edit Agent (в работе, 4-6 дней)
2. **SEC‑LLM‑001** — Security Guardrails (следующий, 3-5 дней)
3. Продолжение остальных инициатив Pre-OSS Release

### INIT‑UI‑001 — React SPA Platform & Artifacts
- Статус: Active; Milestone: Pre‑OSS Release → UI V1
- Объём: локальный Artifacts Service, React SPA, интеграция LearnFlow
- Выполнено: FEAT‑UI‑101 (база Artifacts Service), FEAT‑UI‑102 (базовый просмотр Markdown) — см. архив
- Чартер: `docs/backlog/current/INIT-UI-001-react-spa-platform/README.md`
- В работе/запланировано:
  - FEAT‑UI‑103 — Интеграция LearnFlow: замена GitHub → локальные артефакты (`docs/backlog/current/FEAT-UI-103-learnflow-integration/README.md`)
  - FEAT‑UI‑104 — Real‑time обновления (WebSocket) (`docs/backlog/current/FEAT-UI-104-realtime-updates.md`)
  - FEAT‑UI‑105 — Продвинутый UI (редактор, dnd, аннотации) (`docs/backlog/current/FEAT-UI-105-advanced-ui.md`)

### SEC‑LLM‑001 — Guardrails для защиты LLM
- Статус: Active; Milestone: Pre‑OSS Release
- Цель: Защита от prompt injection и jailbreak атак
- **План реализации**: `docs/backlog/current/SEC-LLM-001-guardrails/impl/IP-01-security-guard-implementation.md`
- План:
  - Детекция injection через выделенную LLM
  - Fuzzy matching для удаления вредоносного контента
  - Валидация входных запросов на подозрительные паттерны
  - Логирование и мониторинг подозрительных промптов
  - Интеграция с LangFuse для трекинга
- DoD: система блокирует > 95% известных injection паттернов

### FEAT‑LLM‑301 — Поддержка локальных LLM
- Статус: Active; Milestone: Pre‑OSS Release
- Цель: Работа с любыми OpenAI-совместимыми API
- Поддержка:
  - Ollama (с автоопределением моделей)
  - LM Studio
  - Dockerized models (llama.cpp, vLLM)
  - Настройка через переменные окружения
- DoD: успешная работа с минимум 3 локальными провайдерами

### FEAT‑AI‑201 — Правки с подтверждением (HITL)
- Статус: Active; Milestone: Pre‑OSS Release
- Когда: после этапа синтеза (готов `synthesized_material`, собранный из конспектов и сгенерированного текста).
- Что делает пользователь: даёт обратную связь — где дополнить, сократить, переписать или уточнить. Может выделить место (строка/абзац/пара абзацев) или описать его.
- Что делает агент: вносит точечные правки в указанном фрагменте, предлагает дифф; пользователь подтверждает или отклоняет.
- Главная сложность: спроектировать инструмент так, чтобы LLM надёжно попадал в нужный фрагмент и давал качественный дифф.
- **План реализации**: `docs/backlog/current/FEAT-AI-201-hitl-editing/impl/IP-01-edit-agent-integration.md`

План:
- Инструмент `EditTool` (для агента):
  - Вход: `{thread_id, file_path, locator (span|anchor+instruction), intent (add|reduce|rewrite|clarify), style_guidelines?}`
  - Выход: `diff` (unified), `suggestion` (чистый текст правки), `rationale` (кратко зачем изменено)
  - Требования: идемпотентность, строгие границы правки, отказ от «тихих» переписываний вне span
- Контракт правки (упрощённо): `RewriteSegment {path, locator, intent, suggestion, diff}`
- Узел HITL после синтеза: принимает обратную связь, запрашивает `EditTool`, показывает дифф в UI, применяет только после «Принять» и обновляет артефакты
- Web UI: минимальный review — подсветка изменений и кнопки «Принять/Отклонить», поле для короткого комментария; полноценный редактор — в FEAT‑UI‑105

Готово, если:
- подтверждённые правки записываются в `data/artifacts/{thread_id}/...` и видны в UI;
- последующие шаги графа учитывают обновления;
- некорректные локаторы/диффы корректно обрабатываются (ошибка/повторное уточнение).

### REL‑OSS‑001 — Подготовка к публикации кода и лицензирование
- Задача: привести репозиторий к публичному релизу (лицензия + доки)
- План:
  - Лицензия Apache 2.0 + Commons Clause (зафиксировать в ADR‑003)
  - README на английском с архитектурной диаграммой и демо
  - Базовые файлы: `CONTRIBUTING`, `CODE_OF_CONDUCT`, `SECURITY`
  - GitHub: topics, badges, issue templates, good first issues
  - Docker Compose с опцией локальной LLM по умолчанию
  - Минимальные pytest для критических компонентов
- Готово, если: проект запускается через `docker compose up`, README впечатляет

### FEAT‑PROMPT‑401 — Статическая библиотека промптов
- Статус: Planned; Milestone: OSS Launch
- Цель: Поддержка разных дисциплин из коробки
- План:
  - Промпты для: криптографии, математики, физики, программирования
  - YAML конфигурация с переключением через ENV
  - Документация по добавлению новых дисциплин
- DoD: минимум 5 дисциплин с примерами

### COMM‑OSS‑501 — Community Engagement (запуск)
- Статус: Planned; Milestone: OSS Launch
- План:
  - Демо-видео/GIF в README
  - Посты: LinkedIn, Reddit (r/MachineLearning, r/opensource), HackerNews
  - Telegram-каналы: AI/ML сообщества
  - Подготовка к YouTube серии
- DoD: 100+ stars в первую неделю

## Запланированные инициативы (Community Growth)

### COMM‑OSS‑502 — YouTube контент
- Статус: Future; Milestone: Community Growth
- План серии видео:
  1. Обзор проекта для пользователей (5-10 мин)
  2. Архитектура на LangGraph для инженеров (15-20 мин)
  3. AI-driven development процесс (10-15 мин)
  4. Настройка с локальными LLM (туториал)
- DoD: 1000+ просмотров, 50+ подписчиков

### FEAT‑PROMPT‑402 — Динамическое формирование промптов
- Статус: Future; Milestone: Community Growth
- Цель: Автоматическая адаптация под дисциплину
- План: RAG система для выбора оптимальных промптов
- DoD: точность определения дисциплины > 90%

### DEV‑JUPYTER‑001 — Jupyter демо notebook
- Статус: Future; Milestone: Community Growth
- Цель: Интерактивная демонстрация возможностей
- План: Google Colab совместимый notebook с примерами
- DoD: запускается в Colab без установки

### EXP‑DOC‑001 — Экспорт в PDF/DOCX
- Статус: Planned; Milestone: UI V1
- Цель: Профессиональное оформление материалов
- План: Pandoc интеграция, шаблоны оформления
- DoD: экспорт с сохранением форматирования и формул

## Запланированные инициативы (после OSS)

### TG‑UX‑001 — Telegram‑first UX
- Цель: перенести основной пользовательский сценарий в Telegram; Web UI оставить как просмотр/редактор
- План: deep link из бота в thread, управление сессиями, HITL‑подтверждения внутри чата, предпросмотр Markdown
- Метрики: MAU/DAU бота, % завершённых сессий без веба

### EXP‑NOTE‑001 — Экспорт в заметки/сервисы
- Цель: удобный экспорт материалов
- Варианты: Obsidian (локальная папка/зеркало), Notion API, Markdown zip, WebDAV; модуль экспортёров в Artifacts Service
- DoD: хотя бы два экспортёра, настройка из UI/бота

## Риски и зависимости
- Большие файлы (OCR/рендер) могут замедлять обработку — следить и оптимизировать
- Real‑time: нужен простой и стабильный формат событий WS (`/ws/{thread_id}`)
- Лицензия Apache 2.0 + Commons Clause — явно описать как source-available
- Guardrails могут влиять на производительность — профилирование и оптимизация
- Поддержка разных LLM — тестирование совместимости и fallback стратегии
- Community engagement требует постоянных усилий — планировать контент заранее

## Ссылки
- Обзор: `docs/overview.md`
- Vision: `docs/planning/vision.md`
- Инициативы: `docs/backlog/current/`


