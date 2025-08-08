# FEAT-UI-104 — Real-time обновления (WebSocket)

Статус: Planned
Инициатива: INIT-UI-001

## Цель
Обеспечить live updates файлов и прогресса workflow в Web UI.

## План
- WebSocket endpoint в Artifacts Service: `/ws/{thread_id}`.
- Интеграция в `artifacts_manager.py`: отправка событий при сохранении.
- Frontend: `useWebSocket` hook, обновление списка/контента файлов, `WorkflowProgress`.

## DoD
- Подключение WS при открытии thread.
- Новые файлы/изменения появляются без перезагрузки.
- Отображается прогресс workflow.

## Ссылки
- Инициатива: `./INIT-UI-001-react-spa-platform.md`