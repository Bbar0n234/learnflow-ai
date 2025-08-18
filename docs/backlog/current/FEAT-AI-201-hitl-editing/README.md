# FEAT-AI-201: HITL Editing - Правки с подтверждением

## Статус
✅ **COMPLETED** (August 2025)

## Milestone
Pre-OSS Release

## Цель
Внедрить возможность интерактивного редактирования синтезированного образовательного материала с использованием LLM-агента и подтверждением пользователя.

## Обоснование
- Пользователи хотят корректировать и дополнять сгенерированный материал
- Необходимость точечных правок без полной регенерации
- Улучшение качества финального материала через итеративный процесс
- Сохранение контроля пользователя над контентом

## Архитектура

### Компоненты
1. **EditMaterialNode** - новый узел в LangGraph workflow
2. **Fuzzy matching** - для поиска и замены текста с учетом небольших отличий
3. **HITL интеграция** - использование существующего паттерна для взаимодействия
4. **Auto-save** - автоматическое сохранение версий через LocalArtifactsManager

### Интеграция в workflow
```
synthesis_material -> edit_material (optional) -> generating_questions
```

## План реализации

### Основной план
~~Детальный план реализации:~~ [IP-01-edit-agent-integration.md](../../archive/IP-01-edit-agent-integration.md) *(archived)*

**Post-Implementation Summary**: [impl/POST-IMPLEMENTATION-SUMMARY.md](impl/POST-IMPLEMENTATION-SUMMARY.md)

### Краткая сводка (4-6 дней)
1. **День 1-2**: Портирование fuzzy matcher из Jupyter notebook
2. **День 3-4**: Создание EditMaterialNode с HITL логикой
3. **День 5**: Интеграция в workflow и тестирование с ботом
4. **День 6**: Доработка и опциональные REST endpoints

## Definition of Done

- [x] EditMaterialNode успешно интегрирован в workflow
- [x] Fuzzy matching работает с точностью >85%
- [x] HITL взаимодействие через Telegram бот функционирует
- [x] Каждая правка автоматически сохраняется в artifacts
- [x] Feature flag позволяет включать/выключать функционал
- [x] Базовое тестирование покрывает основные сценарии
- [x] Документация обновлена

## Зависимости
- Существующая HITL инфраструктура (из recognition/questions nodes)
- LocalArtifactsManager для сохранения версий
- fuzzysearch библиотека для нечеткого поиска

## Риски
- Fuzzy matching может не найти текст при значительных отличиях
- Возможны конфликты при одновременном редактировании
- Производительность при больших документах

## Метрики успеха
- Количество успешных правок на сессию
- Процент найденных фрагментов через fuzzy matching
- Время на одну правку
- Удовлетворенность пользователей итоговым материалом

## Связанные документы
- [ADR-001: Architecture Overview](../../../ADR/001-architecture-overview.md)
- [~~План реализации IP-01~~](../../archive/IP-01-edit-agent-integration.md) *(archived)*
- [Post-Implementation Summary](impl/POST-IMPLEMENTATION-SUMMARY.md)
- [Roadmap](../../../planning/roadmap.md)