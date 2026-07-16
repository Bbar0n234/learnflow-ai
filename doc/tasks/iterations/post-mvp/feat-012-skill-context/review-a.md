## Code Review Report — режим A (качество кода)

### Summary
- blocker: 0
- nit: 2
- pre-existing: 0
- (question: 1)

Общая оценка: код высокого качества. Точно следует прецедентам (`user_memory.py`,
`knowledge_sphere.py`, `store_helpers.format_index`, `CustomInstructionsSection`),
изоляция по `user_id` из runtime-контекста корректна, границы функций аккуратные,
тесты поведенческие и ловят реальные регрессии (граничные значения 20 000/200/cap-20,
изоляция per-user/per-skill, порядок 404→guard, отсутствие утечки тела документа в
индекс). Ни одного blocker'а. Разобранные осознанные решения (`_NO_RUNTIME`-sentinel,
дублирование констант вместо cross-module импорта, идемпотентный tool-delete vs
404-REST-delete) — обоснованы верно, поведение соответствует обоснованиям.

### Замечания

| Severity | Намерение | Файл:строка | Замечание (со свидетельством поведения) | Предложение |
|---|---|---|---|---|
| nit | suggestion | backend/app/agent/tools/skill_context.py:134 | `get_skill_context` читает `item.value["content"]` прямым ключом, тогда как сервисный слой (`services/skill_context.py:670` `_to_document_data`) и `format_index` используют `.get("content", "")` / `.get("description", "")`. Расхождение в defensive-стиле. Реального бага нет: оба пишущих пути (`save_skill_context` и REST `update_document`) всегда кладут оба ключа, документа без `content` не возникает. Но при гипотетическом дрейфе схемы значения именно tool упадёт с `KeyError` вместо мягкой деградации. | Для симметрии с сервисом — `item.value.get("content", "")`; либо оставить как есть (инвариант «оба ключа всегда записаны» держится обоими путями). |
| nit | question | backend/app/agent/tools/skill_context.py:174-184 | Проверка cap-20 (`asearch` → `if len(...) >= 20` → `aput`) не атомарна: два конкурентных `save_skill_context` с *новыми* ключами, каждый увидевший 19 существующих документов, оба пройдут проверку и создадут 21-й. Тот же неатомарный read-then-write присущ прецеденту (`knowledge_sphere`), Store транзакции не даёт; для персонального namespace одного юзера окно узкое и урон (21 вместо 20 документов) незначителен. | Приемлемо оставить; при желании ужесточить — только через Store-level constraint, что вне скоупа фичи. Фиксирую как известное свойство, не дефект. |
| — (question) | question | backend/app/agent/tools/skill_context.py:136-185 ↔ configs/security.yaml:777 | Агентский `save_skill_context` НЕ прогоняет контент через checkpoint `SKILL_CONTEXT_WRITE` — классификатор применяется только на REST-пути (`services/skill_context.py:717`). Тред-модель checkpoint'а («контент записан → сюрфейсится при `load_skill` как доверенный») формально покрывает и агентскую запись; summary/design-brief явно относят агентский путь к runtime-checkpoint `tool_call_arg`. Это документированное дизайн-решение (не мой мандат судить архитектуру), отмечаю лишь для явной верификации архитектором, что `tool_call_arg` действительно инспектирует аргументы `save_skill_context` симметрично REST-классификатору. | Подтвердить у архитектора покрытие агентского write-пути; если да — ничего не менять. |

Ничего блокирующего. Замечания уровня nit/question — на усмотрение.
