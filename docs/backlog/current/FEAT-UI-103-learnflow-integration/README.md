# FEAT‑UI‑103 — Интеграция LearnFlow с локальными артефактами

Статус: Active  
Инициатива: `../INIT-UI-001-react-spa-platform/README.md`

## Контекст
Ранее артефакты сохранялись через GitHub. Требуется полностью перейти на локальный Artifacts Service и файловую структуру `data/artifacts/`.

## Цель
Заменить GitHub‑интеграцию на локальный менеджер артефактов и обеспечить сохранение/чтение всех артефактов из `data/artifacts/` так, чтобы Web UI отображал живой сквозной поток.

## План (см. IP)
- IP‑01 — Ввести `learnflow/artifacts_manager.py` вместо `github.py` — `impl/IP-01-artifacts-manager.md`
- IP‑02 — Обновить `ExamState` (заменить `github_*` на `artifacts_*`) — `impl/IP-02-exam-state-migration.md`
- IP‑03 — Обновить workflow‑узлы для сохранения артефактов: generated, recognized, synthesized, gap_q, answers — `impl/IP-03-workflow-nodes-io.md`
- IP‑04 — (при необходимости) Расширить Artifacts Service для метаданных треда — `impl/IP-04-artifacts-service-thread-metadata.md`

## DoD
- Все узлы workflow сохраняют артефакты в локальное хранилище.
- Web UI отображает реальные файлы от живого workflow.
- Метаданные треда доступны через API (если требуются).

## Ссылки
- Инициатива: `../INIT-UI-001-react-spa-platform/README.md`
- Обзор: `../../overview.md`

