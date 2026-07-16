# Harvest proposals — feat-010

## Anytime-кандидаты (оркестратор, по ходу итерации)

- **[конвенция] `conventions.md` § Env (правило «все четыре места») устарело относительно `env_file`-паттерна.** Сервис `app` в `docker-compose.yml` получает окружение через `env_file: [.env]` целиком — перечислять каждую app-переменную в compose не нужно и фактически не делается (ни один `LLM_*`-таймаут не перечислен). Формулировка «одновременное обновление `.env.example`, `.env.local.example`, `docker-compose.yml` и `Settings`» заставляет каждую новую переменную формально нарушать норму, следуя верному паттерну. Предложение: смягчить норму — «`Settings` + `.env.example` всегда; `docker-compose.yml` — только для сервисов с явным перечнем env (siem-service); `.env.local.example` — только если нужен local-dev override». Источник: review-b.md feat-010, суждение имплементера T1.4 подтверждено ревьюером B.

- **[конвенция/долг] `backend.md` «Правила вызовов»: `API → Repository ❌` расходится с практикой.** Media endpoint feat-010 инжектит `BlobStorageDep` (обёртка `PgBlobStorage` из `app/repositories/blob_storage.py`) прямо в route-handler мимо Service-слоя; тот же паттерн пре-существует для `MCPServerRepository` (`app/api/routes/mcp_servers.py`). Ни один ревьюер не флагнул. Нужно решение архитектора: ослабить документированное правило под сложившуюся практику (например, «инжект репозитория в route допустим для тонких read/CRUD-обвязок без бизнес-логики») либо признать оба места долгом и завести рефакторинг в backlog. Источник: эскалация docs-updater feat-010.

(Секция консолидируется harvester'ом на фазе HARVEST.)
