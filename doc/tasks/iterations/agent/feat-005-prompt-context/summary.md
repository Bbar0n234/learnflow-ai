# Post-implementation Summary: feat-005 — Based Prompt & Context Engineering

## Результат

Реализован полноценный системный промпт и стратегия управления контекстом. Агент использует tools автономно (без явных инструкций), обновляет Knowledge Sphere по ходу работы, gracefully обрабатывает ошибки и длинные сессии через compaction.

## Отклонения от плана

| Аспект | План | Факт | Причина |
|--------|------|------|---------|
| `build_graph` signature | Принимает `based_prompt: str` отдельно | Принимает весь `agent_config`, использует `agent_config.prompt.system_text` | Проще wiring, не нужно менять существующий контракт |
| `RemoveMessage(id=m.id)` | Без проверки | Добавлен guard `if m.id is not None` | mypy: `m.id` может быть `None` |
| Tool docstrings | Ревью skills.py и artifacts.py | Оставлены без изменений | Оценены как уже достаточно информативные (план это допускал) |
| E2E тестирование | Явные команды агенту (UC-1..UC-3) | Неявные сценарии — агент сам решает какие tools вызвать | Согласовано с архитектором: проверяем поведение Based Prompt, а не tool API |

## Принятые решения

- **Summary как AIMessage** — не HumanMessage, чтобы модель не "отвечала" на summary
- **Graceful degradation** — при сбое summarization (сеть, rate limit) — fallback на trim-only без ошибки для пользователя
- **Prompt в Goldilocks zone** — минимальный каркас, итеративная доработка по failure modes

## E2E результаты

| Сценарий | Результат | Детали |
|----------|-----------|--------|
| A1: Тон + автономное KS | PASS | `create_section` + `load_skill` без явной просьбы |
| A2: Structure + artifact | PASS | `update_section` + `create_artifact`, не переспрашивал известное |
| A3: Web research (MCP) | PASS | Два вызова `firecrawl_search`, ответ со ссылками |
| B1: Cross-session KS | PASS | Новый чат → `get_section` → полный контекст из KS |
| C1: Error resilience | PASS | Увидел из index что секции нет, объяснил корректно |
| D1-D4: Compaction | PASS | Summary `[Previous conversation summary]`, 6 msgs → 1 summary + 2 recent |

## Нюансы

- **Pydantic serialization warning** — при checkpointer-сериализации `AgentContext` выдаётся warning. Не влияет на работу, но стоит разобраться в будущем.
- **`count_tokens_approximately`** — приблизительный подсчёт токенов. Для production может потребоваться точный счётчик (tiktoken/модель-специфичный).

## Артефакты

- `configs/prompts/system.txt` — Based Prompt
- `backend/app/agent/prompt_builder.py` — Jinja2 template для system message
- `backend/app/agent/config.py` — `SummarizationConfig`, расширенные `ContextConfig` и `PromptConfig`
- `doc/tech/backend.md` — обновлены секции Based Prompt, Short-term Memory, Configuration
