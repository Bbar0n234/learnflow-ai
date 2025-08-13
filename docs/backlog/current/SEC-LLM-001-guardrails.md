# SEC-LLM-001: Guardrails для защиты LLM

## Статус
Active

## Milestone
Pre-OSS Release

## Цель
Внедрить многоуровневую систему защиты от prompt injection, jailbreak атак и других уязвимостей LLM.

## Обоснование
- Пользовательский контент может содержать вредоносные промпты
- Необходима защита от утечки данных и системной информации
- Требование для production-ready системы
- Повышение доверия к проекту со стороны сообщества

## План реализации

### Этап 1: Базовая валидация (2 дня)
- [ ] Создать модуль `learnflow/security/validators.py`
- [ ] Реализовать проверку длины входных данных
- [ ] Добавить базовые regex паттерны для опасных конструкций
- [ ] Интегрировать валидацию в workflow nodes

### Этап 2: Система паттернов (3 дня)
- [ ] Создать YAML конфигурацию паттернов (`configs/security/patterns.yaml`)
- [ ] Реализовать загрузчик паттернов с hot-reload
- [ ] Добавить категоризацию угроз (injection, jailbreak, exfiltration)
- [ ] Реализовать scoring систему для подозрительности

### Этап 3: Изоляция и sandboxing (2 дня)
- [ ] Создать `SandboxedLLM` wrapper
- [ ] Реализовать безопасные промпт-шаблоны
- [ ] Добавить ограничения на выходные данные
- [ ] Тестирование с известными атаками

### Этап 4: Логирование и мониторинг (2 дня)
- [ ] Реализовать аудит лог для всех проверок безопасности
- [ ] Добавить метрики в LangFuse
- [ ] Создать дашборд для мониторинга угроз
- [ ] Настроить алерты для критических событий

### Этап 5: Тестирование (3 дня)
- [ ] Unit тесты для каждого компонента
- [ ] Интеграционные тесты с реальными атаками
- [ ] Fuzzing тестирование
- [ ] Документация по безопасности

## Технические требования

### Архитектура
```python
learnflow/security/
├── __init__.py
├── validators.py      # Основные валидаторы
├── patterns.py        # Работа с паттернами
├── sandbox.py         # Изолированное выполнение
├── audit.py          # Логирование безопасности
└── exceptions.py     # Security-specific исключения
```

### Конфигурация
```yaml
# configs/security/settings.yaml
guardrails:
  enabled: true
  max_input_length: 10000
  suspicion_threshold: 5
  sandbox_high_risk: true
  
patterns:
  update_interval: 3600  # seconds
  sources:
    - local: configs/security/patterns.yaml
    - remote: https://security-patterns.learnflow.ai/latest
```

### API
```python
from learnflow.security import SecurityGuard

guard = SecurityGuard()
result = await guard.validate(user_input)

if result.is_safe:
    # Process normally
    response = await llm.generate(user_input)
elif result.requires_sandbox:
    # Process in isolation
    response = await sandbox.process(user_input)
else:
    # Block and log
    raise SecurityException(result.reason)
```

## Definition of Done

- [ ] Все компоненты безопасности реализованы и протестированы
- [ ] Блокируется >95% известных injection паттернов
- [ ] False positive rate <0.1%
- [ ] Латентность валидации <100ms
- [ ] Документация по настройке и использованию
- [ ] ADR-002 полностью реализован
- [ ] Метрики интегрированы в мониторинг

## Риски
- Возможны false positives для легитимных образовательных запросов
- Дополнительная латентность может повлиять на UX
- Требует постоянного обновления паттернов

## Зависимости
- LangFuse для логирования
- YAML библиотеки для конфигурации
- Regex engine для паттерн-матчинга

## Метрики успеха
- Количество заблокированных атак
- Процент false positives
- Среднее время валидации
- Покрытие известных уязвимостей

## Ссылки
- [ADR-002: LLM Security Guardrails](../../ADR/002-llm-guardrails.md)
- [OWASP LLM Top 10](https://owasp.org/www-project-top-10-for-large-language-model-applications/)