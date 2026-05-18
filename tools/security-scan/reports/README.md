# Red Team Scan Reports

Per-run артефакты от Promptfoo + provider'а. В отличие от типичной
`reports/` directory, raw отчёты **коммитятся** — учебный проект выигрывает
от воспроизводимых audit-evidence артефактов.

## Структура

```
reports/
├── README.md            # этот файл
└── <run-id>/
    ├── report.html               # Promptfoo HTML report
    ├── results.json              # Promptfoo machine-readable export
    ├── provider-events.jsonl     # provider-side bridge log
    └── summary.md                # ручной summary по template из design-brief §8.2
```

`<run-id>` — рекомендуется ISO-like формат: `YYYY-MM-DD-<purpose>`,
например `2026-05-10-promptfoo-baseline`.

## Commit Policy

Raw отчёт коммитится **только если** все условия выполнены:

- [ ] Run выполнен на dedicated eval user (`LEARNFLOW_SCAN_USERNAME`),
      не на реальном пользователе.
- [ ] `.env` / access tokens / refresh cookies в директории отсутствуют.
- [ ] В prompt/output **нет реальных секретов** — `grep -E "(password|token|sk-|api_key|Bearer)" reports/<run-id>/*` пусто.
- [ ] В prompt/output нет пользовательских данных вне synthetic/eval контекста.
- [ ] Отчёт полезен как evidence для преподавателя или regression baseline.

Если raw отчёт содержит чувствительные данные:

1. Не коммитим raw артефакты.
2. Коммитим только sanitized `summary.md` с описанием findings без leaked content.
3. В summary указываем причину sanitization.

## Sanitize Mode

При запуске можно установить `LEARNFLOW_SCAN_SANITIZE_LOGS=true` —
provider будет сокращать prompt/output в `provider-events.jsonl` до preview,
сохраняя при этом structural metadata (chat_id, block_reason, latency).
Baseline learning runs обычно работают с `false` для богатых артефактов.

## Не коммитить

- `tools/security-scan/.env`
- access tokens, refresh cookies, API keys
- Promptfoo local cache (`.promptfoo/`)
- временные scratch files
- отчёты с обнаруженными реальными секретами
