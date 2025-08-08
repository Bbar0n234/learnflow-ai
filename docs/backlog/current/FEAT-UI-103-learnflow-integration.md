# FEAT-UI-103 — Интеграция LearnFlow с локальными артефактами

Статус: Planned
Инициатива: INIT-UI-001

## Цель
Заменить GitHub-интеграцию на локальный Artifacts Manager и обеспечить сохранение всех артефактов в `data/artifacts/`.

## План
- Ввести `learnflow/artifacts_manager.py` вместо `github.py`.
- Обновить `ExamState` (заменить `github_*` на `artifacts_*`).
- Обновить workflow nodes для сохранения файлов: generated, recognized, synthesized, gap_q, answers.
- Расширить Artifacts Service для метаданных thread'а (если требуется).

## DoD
- Все узлы workflow сохраняют артефакты в локальное хранилище.
- Web UI отображает реальные файлы от живого workflow.
- Метаданные доступны через API.

## Ссылки
- Инициатива: `./INIT-UI-001-react-spa-platform.md`