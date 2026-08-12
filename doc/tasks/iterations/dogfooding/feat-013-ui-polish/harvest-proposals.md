# Harvest-кандидаты: feat-013 — UI/UX polish

> Кандидаты на перенос в `doc/backlog.md` / `doc/tech/conventions.md`. **Только предложения** —
> landing после апрува архитектора на pre-commit gate. Секции ниже пополняет `harvester` на
> финализации; записи «anytime» вносит оркестратор по ходу итерации.

## Anytime-кандидаты (от оркестратора, по ходу итерации)

- **Свежий worktree не готов к работе: нет цели bootstrap.** На старте конвейера `make check` и
  `make check-fe` упали не по вине кода — в worktree отсутствовали `.venv` и `frontend/node_modules`,
  потребовались ручные `uv sync --all-packages` и `npm ci`. Конвенция (`conventions.md` § Git →
  «Lifecycle итерации») описывает создание worktree, но не его подготовку, а `make check` при этом
  заявлен предусловием старта итерации. Кандидат: цель `make bootstrap` (или `worktree-init`),
  выполняющая обе установки, + строка в lifecycle-разделе конвенции. Тип: конвенция + Makefile.
  Приоритет: P3 (разовая ручная работа на каждый новый worktree, ловушка для автономного агента —
  падение выглядит как сломанный код).
