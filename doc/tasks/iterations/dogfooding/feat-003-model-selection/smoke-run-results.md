# Результаты боевых прогонов model_smoke.py

Запуск: оркестратор, локально, ключ из `.env` (`LLM_API_KEY`), OpenRouter `https://openrouter.ai/api/v1`.

## Прогон 2 — финальный состав (после замены Muse Spark → Grok 4.5)

| Модель | Роль | Ответ | Рассуждения | prompt/compl/reason tok | Latency, ms |
|---|---|---|---|---|---|
| z-ai/glm-5.2 | whitelist (main) | да | полные | 24/133/0 | 3324 |
| google/gemini-3.6-flash | whitelist | да | полные | 12/120/113 | 1302 |
| deepseek/deepseek-v4-pro | whitelist | да | полные | 17/57/48 | 977 |
| x-ai/grok-4.5 | whitelist | да | **суммаризованные** | 218/54/47 | 2929 |
| qwen/qwen3.7-max | whitelist | да | полные | 22/203/191 | 4321 |
| deepseek/deepseek-v4-flash | summarization/subagents | да | полные | 95/197/190 | 9292 |
| **google/gemini-3.5-flash-lite** | **guard** | **да** | **полные** | 13/7/0 | **575** |

Итог: 7/7 ответили. Вопрос архитектора закрыт: **guard-модель отдаёт рассуждения** (effort minimal, латентность вердикта < 600 мс). Grok 4.5 отдаёт суммаризованные рассуждения (ожидаемо для проприетарного xAI) и считает существенный prompt-overhead (218 prompt-токенов на короткий запрос — вероятно, системная обвязка провайдера). GLM-5.2 в этом прогоне отдала reasoning-текст при reason.tok=0 — токены рассуждений вошли в completion (нюанс биллинга провайдера, для cost-учёта не критичен: output и output_reasoning тарифицируются одинаково).

## Прогон 1 — исходный состав (историческая справка)

7 моделей: 6/7 ответили; `meta/muse-spark-1.1` — HTTP 403 «This model is only available in the United States» (гео-блок единственного провайдера Meta) → эскалация → решение архитектора: замена на `x-ai/grok-4.5`. Остальные результаты эквивалентны прогону 2 (GLM-5.2: полные рассуждения, 156 reason tok, 5.9 c; guard: полные, 483 мс).
