# INIT‑UI‑001 — React SPA Platform & Artifacts

Статус: Active  
Milestone: Pre‑OSS Release → UI V1

## Цели
- Локальный Artifacts Service как единственный источник артефактов.
- Базовый React SPA для просмотра материалов и статусов.
- Интеграция LearnFlow с локальными артефактами вместо GitHub.

## Скоуп
- Artifacts Service (локальное хранилище, базовые метаданные треда).
- Web UI (просмотр Markdown/списков, навигация по сессиям/тредам).
- Интеграция LearnFlow → сохранение всех артефактов в `data/artifacts/`.

## Не‑цели (в этой инициативе)
- Полноценный редактор и аннотации (FEAT‑UI‑105).
- Telegram‑first UX и deep‑links (после OSS: TG‑UX‑001).
- Продвинутые экспортёры (EXP‑NOTE‑001).

## Метрики успеха
- Сквозной поток от распознавания до синтеза виден в Web UI из локальных артефактов.
- Отсутствие зависимости от GitHub в рабочем сценарии.

## Состав / Статус
- FEAT‑UI‑101 — база Artifacts Service (Done, см. архив)
- FEAT‑UI‑102 — базовый просмотр Markdown (Done, см. архив)
- FEAT‑UI‑103 — Интеграция LearnFlow с локальными артефактами (Active) — см. `../FEAT-UI-103-learnflow-integration/README.md`
- FEAT‑UI‑104 — Real‑time обновления (Planned)
- FEAT‑UI‑105 — Продвинутый UI (Planned)

## DoD инициативы
- Артефакты из всех ключевых узлов графа сохраняются локально и доступны через Artifacts Service.
- Web UI показывает актуальные артефакты активного треда/сессии.
- (Базово) реализация совместима с будущими real‑time обновлениями.

## Риски и зависимости
- Большие файлы (OCR/рендер) — мониторить производительность.
- Simple и стабильный формат событий для WS (`/ws/{thread_id}`) — зависит от FEAT‑UI‑104.

## Ссылки
- Roadmap: `../../planning/roadmap.md`
- Обзор: `../../overview.md`
- FEAT‑UI‑103: `../FEAT-UI-103-learnflow-integration/README.md`

