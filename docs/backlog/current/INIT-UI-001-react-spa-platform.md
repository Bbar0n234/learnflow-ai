# INIT-UI-001 — React SPA Platform & Artifacts

Статус: Active
Milestone: MVP (Qx)

## Цель
Заменить GitHub-интеграцию локальным Artifacts Service и предоставить веб-интерфейс (React SPA) для просмотра/редактирования артефактов и наблюдения за прогрессом workflow.

## Метрики/DoD (для инициативы)
- Сквозной поток: LearnFlow → сохранение артефактов → Web UI отображает реальные данные.
- Время до отображения результата (TTR) ≤ 60 сек для среднего кейса.
- Стоимость запроса без регресса относительно исходного решения.

## Объём (Scope)
- Artifacts Service (FastAPI) с локальным хранением `data/artifacts/{thread_id}`.
- React SPA (Vite + React + TS, Tailwind, react-markdown + LaTeX).
- Интеграция LearnFlow с новым менеджером артефактов.
- (Поэтапно) WebSocket real-time обновления; редактор/структурирование — позже.

Не-цели (сейчас): совместное редактирование, полная версионность, PDF экспорт (в отдельные итерации).

## Риски
- Качество и производительность OCR/рендеринга больших файлов.
- Сложность синхронизации состояния в real-time.

## Зависимости
- Хранилище артефактов доступно и монтируется в LearnFlow и сервис артефактов.

## Итерации/фичи
- FEAT-UI-101 — Artifacts Service: базовая инфраструктура (Completed; см. архив).
- FEAT-UI-102 — React SPA: базовый просмотр файлов и Markdown (Completed; см. архив).
- FEAT-UI-103 — Интеграция LearnFlow: замена GitHub → локальные артефакты (Planned).
- FEAT-UI-104 — Real-time обновления (WebSocket, прогресс workflow) (Planned).
- FEAT-UI-105 — Продвинутые UI-фичи (редактирование, dnd, аннотации) (Planned).

## Связанные материалы
- Архитектурный high-level план (superseded): см. архив `../archive/react_spa/react_spa_high_level.md`.
- Детализация итераций (superseded): см. архив `../archive/react_spa/react_spa_iterations.md`.
- Ранний план Iteration 2 (архив): `../archive/feature-react-spa-iteration2-implementation-plan.md`.