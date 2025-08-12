# FEAT‑UI‑103 — Интеграция LearnFlow с локальными артефактами

Статус: Active  
Инициатива: `../INIT-UI-001-react-spa-platform/README.md`

## Контекст
Ранее артефакты сохранялись через GitHub. Требуется полностью перейти на локальный Artifacts Service и файловую структуру `data/artifacts/`.

## Цель
Заменить GitHub‑интеграцию на локальный менеджер артефактов и обеспечить сохранение/чтение всех артефактов из `data/artifacts/` так, чтобы Web UI отображал живой сквозной поток.

## Реализованные компоненты
- ✅ IP‑01 — Локальный менеджер артефактов (`learnflow/artifacts_manager.py`) — [Завершено](impl/IP-01-post-implementation-summary.md)
  - Полная замена GitHub integration
  - Миграция состояния ExamState  
  - Интеграция с GraphManager
  - Метаданные тредов и сессий

## Текущая работа
- IP‑05 — Интеграция Web UI с артефактами — `impl/IP-05-web-ui-artifacts-integration.md`

## DoD
- ✅ Все узлы workflow сохраняют артефакты в локальное хранилище
- ✅ Метаданные треда доступны через локальные JSON файлы
- ⏳ Web UI отображает реальные файлы от живого workflow

## Ссылки
- Инициатива: `../INIT-UI-001-react-spa-platform/README.md`
- Обзор: `../../overview.md`

