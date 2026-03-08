# Зависимости между итерациями

Сводная таблица межсписочных зависимостей. "Blocked by" указывает итерации, которые должны быть завершены до начала данной.

## Граф зависимостей

```
infra/chore-001 ──→ infra/chore-002 ──→ infra/chore-003
       │
       ├──→ backend-core/feat-001 ──→ feat-002 ──→ feat-003 ──→ feat-004 ──→ feat-005
       │           │                                   │
       │           │                                   │
       │           └──→ agent/feat-001 ──┬──→ feat-002 ─┤
       │                                 ├──→ feat-003 ←┘ (ArtifactRepository)
       │                                 └──→ feat-004
       │                                        │
       │                   agent/feat-002 ───────┤
       │                   agent/feat-003 ───────┤
       │                   agent/feat-004 ───────┘
       │                                         │
       │                                   agent/feat-005
       │
       └──→ frontend/feat-001 ──→ feat-002 ──┬──→ feat-003 ──→ feat-004 ──→ feat-005
                                              └──→ feat-006
```

```
backend-core/feat-005 ──┐
agent/feat-002 ─────────┼──→ integration/feat-001
                        │
frontend/feat-006 ──────┼──→ integration/feat-002
                        │
frontend/feat-005 ──────┼──→ integration/feat-003 ──→ feat-004 ──→ feat-005
```

## Полная таблица

| Итерация | Blocked by |
|----------|-----------|
| **Infrastructure Setup** | |
| infra/chore-001 | — |
| infra/chore-002 | infra/chore-001 |
| infra/chore-003 | infra/chore-002 |
| **Backend Core** | |
| backend-core/feat-001 | infra/chore-001 |
| backend-core/feat-002 | backend-core/feat-001 |
| backend-core/feat-003 | backend-core/feat-002 |
| backend-core/feat-004 | backend-core/feat-003 |
| backend-core/feat-005 | backend-core/feat-004 |
| **Frontend** | |
| frontend/feat-001 | infra/chore-001 |
| frontend/feat-002 | frontend/feat-001 |
| frontend/feat-003 | frontend/feat-002 |
| frontend/feat-004 | frontend/feat-003 |
| frontend/feat-005 | frontend/feat-004 |
| frontend/feat-006 | frontend/feat-002 |
| **Agent Runtime** | |
| agent/feat-001 | backend-core/feat-001 |
| agent/feat-002 | agent/feat-001 |
| agent/feat-003 | agent/feat-001, backend-core/feat-003 |
| agent/feat-004 | agent/feat-001 |
| agent/feat-005 | agent/feat-002, agent/feat-003, agent/feat-004 |
| **Integration & Polish** | |
| integration/feat-001 | backend-core/feat-005, agent/feat-002 |
| integration/feat-002 | integration/feat-001, frontend/feat-006 |
| integration/feat-003 | integration/feat-002, frontend/feat-005 |
| integration/feat-004 | integration/feat-003 |
| integration/feat-005 | integration/feat-004 |

## Параллелизация

После завершения `infra/chore-001` можно параллельно вести:
- **Backend Core** (feat-001 →...)
- **Frontend** (feat-001 →...)

**Agent Runtime** стартует после `backend-core/feat-001`. Agent feat-003 дополнительно ждёт `backend-core/feat-003`.

**Integration** начинается после завершения всех трёх треков (backend-core, agent, frontend).
