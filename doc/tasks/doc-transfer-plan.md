# План переноса документации

## Цель

Перенос и адаптация проектной документации из Obsidian в `doc/` репозитория. Формирование контекста для реализации по методологии AIDD (documentation first).

**Текущая фаза проекта:**

```
Фаза A: Documentation Transfer    ✅ done
  Перенос + адаптация Obsidian → doc/
     ↓
Фаза B: Detailed Architecture
  Модули, интерфейсы, классы, контракты
  (doc/tech/backend/, agent/, frontend/)
     ↓
Фаза C: Infrastructure Setup
  uv, ruff, mypy, pre-commit, Docker, Makefile
     ↓
Фаза D: Implementation (Итерации 1-4)
```

## Источник

Symlink на директорию проекта в Obsidian vault:

```
doc/.obsidian-source → /home/bbaron/my_obsidian/projects/active/LearnFlowAI/
```

### Ключевые файлы-источники

| Файл | Что содержит |
|------|-------------|
| `Product_Vision.md` | ICP, JTBD, конкурентное преимущество, scope по версиям, unit economics, боли из опыта, дистрибуция |
| `Architecture_v2.md` | Принципы, системная архитектура, General Agent, Memory System (Knowledge Sphere), Context Engineering, Skills, мультиагентность, persistence, стек, MVP scope, feedback loop, distribution & integration |
| `_INDEX.md` | Навигационная карта, текущий статус, ближайшие шаги |

## Принципы переноса

- **Адаптация, не копирование.** Структура `doc/` ≠ структура Obsidian. Один источник может разбиваться на несколько документов репо (и наоборот). Документы репо могут содержать дополнительные детали или опускать то, что здесь не нужно.
- **Outline-first.** Для каждого документа: outline → ревью архитектора → апрув → полный документ.
- **Single Source of Truth.** Не дублировать информацию между документами репо. Подробно — в одном месте, в связанных — ссылка и краткий тезис.
- **Язык:** русский для содержания, английский для кода и технических терминов.

## Маппинг и статус

| # | Документ | Источник(и) | Что берём | Статус |
|---|----------|-------------|-----------|--------|
| 1 | `doc/idea.md` | `Product_Vision.md` | Проблема, ICP, JTBD, конкурентное преимущество, границы продукта | ✅ done |
| 2 | `doc/vision.md` | `Architecture_v2.md` | Принципы, системная архитектура, стек, MVP criteria | ✅ done |
| 3 | `doc/product/use-cases.md` | `Product_Vision.md` | Сценарии из JTBD, user journey, боли из опыта → конкретные use cases | ✅ done |
| 4 | `doc/product/roadmap.md` | `Product_Vision.md` + `Architecture_v2.md` | Scope v1/v1.5/v2+ | ✅ done |
| 5 | `doc/tech/adr/ADR-001..004` | `Architecture_v2.md` | Архитектурные решения: General Agent, Skills System, Knowledge Sphere, Progressive Disclosure | ✅ done |

## Что НЕ переносим

| Файл Obsidian | Причина |
|---------------|---------|
| `Project_Context.md` | Личные цели и горизонты — стратегический документ, не нужен в репо |
| `Core.md` | Медиа-стратегия — не техническая документация |
| `Competitors/` | Анализ конкурентов — справочный материал, остаётся в Obsidian |

Эти документы доступны через symlink при необходимости.

## Порядок работы

Последовательность: от фундамента к деталям (1 → 7).

Для каждого документа:
1. Outline → ревью архитектора → апрув
2. Написание полного документа
3. Отметка статуса в таблице выше
