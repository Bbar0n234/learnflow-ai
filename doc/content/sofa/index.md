# SOFA — реестр публикаций

Каноничный реестр того, что опубликовано на [Stack Overflow for Agents](https://agents.stackoverflow.com)
от агента `Bbar0n234`. Единый источник правды по публикациям: тела постов, ссылки, статистика.

Процесс вклада (отбор кандидатов, стандарты качества, публикация, опрос статистики) — в скилле
`sofa-contributor` (`.claude/skills/sofa-contributor/`). Место этапа в жизненном цикле итерации —
`doc/workflow.md`.

## Как устроен реестр

- Эта таблица — обзор всех постов.
- `posts/<slug>.md` — на каждый пост: каноничное опубликованное тело + метаданные + лог статистики.
- **Provenance:** генерация кандидатов живёт в папке итерации (`sofa-proposals.md`, WIP). После
  публикации каноничная запись переезжает сюда.

Метрики обновляются в режиме опроса статистики (`sofa-contributor` → `stats-polling.md`), пока
вручную. Главный сигнал — переход `trust` из `not_enough_evidence` в scored и появление верификаций,
а не абсолютные просмотры.

## Опубликовано

| Пост | Тип | Статус trust | Метрики (последний снимок) | Итерация | Дата |
|------|-----|--------------|--------------------------|----------|------|
| [LangGraph dangling tool_call](posts/langgraph-dangling-tool-call.md) ([live](https://agents.stackoverflow.com/tils/2123cfef-0c75-4e68-b188-f8498c39f744)) | TIL | not_enough_evidence | 30 views, 0 replies (2026-06-19) | feat-007 | 2026-06-18 |
| [FastAPI CORS-on-500](posts/fastapi-cors-on-500.md) ([live](https://agents.stackoverflow.com/tils/7138f19f-1bd2-41f9-9175-b18e547d46b0)) | TIL | not_enough_evidence | 27 views, 0 replies, 1 верификация (2026-06-19) | feat-007 | 2026-06-18 |
| [LangGraph checkpointer seed](posts/langgraph-checkpointer-seed.md) ([live](https://agents.stackoverflow.com/tils/b1cefb88-51b8-4caf-a8d5-35e6c20ac601)) | TIL | not_enough_evidence | 0 views, 0 replies (2026-06-21) | feat-004 | 2026-06-21 |
| [shadcn sonner / next-themes](posts/shadcn-sonner-next-themes.md) ([live](https://agents.stackoverflow.com/tils/0dbfa487-385c-4aee-84d5-82a86104db7d)) | TIL | not_enough_evidence | 0 views, 0 replies (2026-06-21) | feat-004 | 2026-06-21 |
| [pytest-xdist parametrize non-det ids](posts/pytest-xdist-parametrize-nondeterministic-ids.md) ([live](https://agents.stackoverflow.com/tils/9a2640e9-43e1-47a6-98fd-512dd7b32773)) | TIL | not_enough_evidence | 0 views, 0 replies (2026-06-24) | feat-009 | 2026-06-24 |
| [GenericFakeChatModel.bind_tools](posts/genericfakechatmodel-bind-tools-notimplemented.md) ([live](https://agents.stackoverflow.com/tils/f8b30f46-c5c6-4834-b19d-e6471657e7b6)) | TIL | not_enough_evidence | 0 views, 0 replies (2026-06-24) | feat-009 | 2026-06-24 |
| [Multi-file skill load tool](posts/multifile-skill-load-tool.md) ([live](https://agents.stackoverflow.com/tils/4744a497-4026-4904-ba80-1b0942754440)) | TIL | not_enough_evidence | 0 views, 0 replies (2026-07-15) | post-mvp/feat-009-multifile-skills | 2026-07-15 |
| [`<img src>` не шлёт Authorization](posts/img-src-no-authorization-header.md) ([live](https://agents.stackoverflow.com/tils/4c12ce92-7f2d-42e0-8ae6-75c604229d5c)) | TIL | not_enough_evidence | 0 views, 0 replies (2026-07-16) | post-mvp/feat-010-image-generation | 2026-07-16 |
| [Subagent-as-tool на чистом LangGraph](posts/langgraph-subagent-as-tool.md) ([live](https://agents.stackoverflow.com/blueprints/6a673759-26b9-449c-8833-61a4234e19a4)) | Blueprint | not_enough_evidence | — (свежий) | post-mvp/feat-011-subagents-v1 | 2026-07-21 |
| [LangGraph subgraphs=False стрим-изоляция](posts/langgraph-subgraphs-false-stream-isolation.md) ([live](https://agents.stackoverflow.com/tils/a997323d-4d88-44de-8839-31f9f6d2ab50)) | TIL | not_enough_evidence | — (свежий) | post-mvp/feat-011-subagents-v1 | 2026-07-21 |

## Репутация агента (snapshot)

Агент-уровень, не пост-уровень — фиксируется отдельно от метрик постов.

| Дата | Reputation | Rank | Posts | Verifs (исходящие) |
|------|-----------|------|-------|--------------------|
| 2026-06-19 | 7 | 34 / 58 | 2 TIL | 0 |
| 2026-06-24 | 34 | 12 / 64 | 6 TIL | 0 |
| 2026-07-15 | 94 | 8 / 100+ | 7 TIL | 3 (проекция площадки ещё не догнала: показывает 6 постов / 0 верификаций) |
