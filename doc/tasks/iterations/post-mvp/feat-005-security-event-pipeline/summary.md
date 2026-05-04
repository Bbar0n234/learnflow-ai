# Summary: feat-005 — Security Event Pipeline

## T1 — Vocabulary + Contracts + Producer

**Status:** ✅ Complete (T2 ingestion follows)

## Fix-Cycle 2

### {T1.7} contextvars binding: chat route

**Status:** ✅ Fixed

**Issue**: `thread_id` and `project_id` were not bound to structlog contextvars when entering chat stream processing. This caused security events emitted within the stream (e.g., from SecurityGuard) to be missing `thread_id` and `project_id` in their `identifiers`.

**Resolution**: Added `bind_security_context(thread_id=str(chat_id), project_id=str(project.id))` in `backend/app/api/routes/messages.py::send_message` (lines 61-65) immediately after thread ownership validation and before calling the chat service. This ensures the context is bound for the entire request lifecycle including all downstream stream operations.

**Location**: `backend/app/api/routes/messages.py:61-65`

**Changes**:
- Added import: `from app.security_pipeline.context import bind_security_context`
- Added binding call in `send_message` endpoint with thread_id and project_id (lines 61-65)

**Verification**:
- ✅ `make check` passes (ruff + mypy)
- ✅ Code path verified: request → send_message → bind_security_context → service.send_message → stream → SecurityGuard → logger.warning(security_event=True) → merge_contextvars → security_event_processor (thread_id and project_id from contextvars)

## Implementation Summary

### T1 Phase Overview

The first implementation pass (T1 Implementer) established the foundational infrastructure for security event collection and transport:

1. **Vocabulary & Contracts** (packages/siem-contracts/)
   - Centralized event vocabulary with canonical event types across authentication, rate limiting, agent guard, and SIEM subsystems
   - Pydantic models: `SecurityEvent`, `SecurityEventIdentifiers`, `EventType` enum
   - Shared types: `SecurityEventDTO`, rule configurations (`ThresholdRuleConfig`, `SequenceRuleConfig`, `AggregateRuleConfig`)
   - Rules and alerting data structures ready for T2 SIEM service

2. **Producer-Side Pipeline** (backend/app/security_pipeline/)
   - `processor.py`: structlog processor that normalizes events into SecurityEvent and enqueues for transport
   - `context.py`: contextvars binding (user_id, ip, request_id, project_id, etc.) via structlog.contextvars
   - `transport.py`: RedisEventTransport for Redis Streams publishing with graceful shutdown, metrics, and bounded queue (drops on overflow)

3. **Integration Points**
   - `backend/app/agent/security/guard.py`: Refactored to emit canonical event_type (AGENT_GUARD_INPUT_* / OUTPUT_*) based on checkpoint direction (INBOUND vs OUTBOUND)
   - `backend/app/api/routes/auth.py`: Auth operations (LOGIN_SUCCESS, LOGIN_FAILED, REGISTER_SUCCESS, REGISTER_FAILED, REFRESH_REPLAY_DETECTED) emitted with canonical event types
   - `backend/app/infra/rate_limit.py`: Rate limit violations (RATE_LIMIT_LOGIN_EXCEEDED, etc.) emitted through security pipeline
   - `backend/app/main.py`: Lifespan integration for publisher task startup/graceful shutdown
   - `backend/app/api/deps.py`: Context binding (CurrentUser, DBSession) with structured logging context

4. **Documentation**
   - `doc/tech/security-events.md`: Vocabulary reference, event catalog by system, usage patterns, examples

### Files Created

#### New Packages
- `packages/siem-contracts/pyproject.toml`
- `packages/siem-contracts/siem_contracts/__init__.py` (public API)
- `packages/siem-contracts/siem_contracts/py.typed` (PEP 561 marker)
- `packages/siem-contracts/siem_contracts/vocabulary.py` (EventType enum, canonical constants)
- `packages/siem-contracts/siem_contracts/events.py` (SecurityEvent, SecurityEventIdentifiers)
- `packages/siem-contracts/siem_contracts/alerts.py` (AlertDTO, AlertStatus for T2)
- `packages/siem-contracts/siem_contracts/rules.py` (Rule configurations for T2)

#### Backend Security Pipeline
- `backend/app/security_pipeline/__init__.py` (public API exports)
- `backend/app/security_pipeline/processor.py` (structlog processor)
- `backend/app/security_pipeline/context.py` (contextvars binding utilities)
- `backend/app/security_pipeline/transport.py` (RedisEventTransport)

#### Documentation
- `doc/tech/security-events.md` (Vocabulary reference + integration guide)

### Files Modified

- `backend/app/agent/security/guard.py`: Switched from hardcoded event IDs to canonical event_type from vocabulary; direction-aware event selection (INBOUND vs OUTBOUND)
- `backend/app/api/routes/auth.py`: Added security event logging for auth events (login, register, refresh, replay detection)
- `backend/app/infra/rate_limit.py`: Added security event logging for rate limit violations
- `backend/app/infra/logging.py`: Integrated security_event_processor into structlog chain; added merge_contextvars for identifier collection
- `backend/app/api/deps.py`: Added context binding in CurrentUser and DBSession dependencies for request context propagation
- `backend/app/main.py`: Added lifespan startup/shutdown for security event publisher task
- `backend/pyproject.toml`: Added siem-contracts dependency via workspace path
- `pyproject.toml` (root): Added packages/siem-contracts as workspace member

## Deviations from Plan

None — all T1 deliverables implemented as specified in design-brief.

## Key Decisions

### 1. Redis Streams with Bounded Queue
- **Decision**: In-process bounded queue (asyncio.Queue) upstream of Redis transport, drops newest on overflow rather than backpressure
- **Rationale**: Security events are high-volume and non-critical; dropping silently with metrics is preferable to blocking request handling
- **Source**: design-brief T1 context § Event Transport

### 2. JSON Serialization in Single Field
- **Decision**: Entire SecurityEvent serialized via `model_dump_json()` into single `data` field in Redis Stream; metadata_dict stored separately
- **Rationale**: Simple, self-contained, avoids schema versioning for individual fields; T2 consumer will deserialize and apply rules
- **Source**: ADR-019 (implied by producer-consumer contract)

### 3. Checkpoint → Direction Logic
- **Decision**: Used existing Direction enum (INBOUND/OUTBOUND) map from Checkpoint to determine event_type (INPUT vs OUTPUT guard events)
- **Rationale**: Avoids adding non-existent `Checkpoint.OUTPUT`; reuses established guard architecture mapping
- **Source**: backend/app/agent/security/types.py::_DIRECTION_MAP

### 4. structlog Processor Chain Integration
- **Decision**: security_event_processor runs as late-stage processor (after merge_contextvars, after TimeStamper) in chain; returns event_dict unchanged
- **Rationale**: Processor acts as side-effect sink (publishes to transport); downstream processors (renderers) see full context; doesn't mutate the event
- **Source**: conventions.md § Logging Conventions + structlog documentation

### 5. contextvars for Identifier Binding
- **Decision**: Used structlog.contextvars.bind_contextvars() rather than custom ContextVar wrappers
- **Rationale**: Reuses standard structlog mechanism; merge_contextvars processor automatically extracts bound context into event_dict
- **Source**: conventions.md § Logging Conventions + structlog best practices

### 6. Workspace Structure for siem-contracts
- **Decision**: Placed siem-contracts as separate workspace package (packages/siem-contracts/) with its own pyproject.toml
- **Rationale**: Allows reuse in future SIEM service (T2); maintains dependency clarity (backend depends on shared contracts); enables version isolation
- **Source**: design-brief § Shared Contracts

## Code Quality

### Type Safety
- Added `py.typed` marker to siem-contracts for PEP 561 compliance
- Fixed mypy errors: proper typing for Redis xadd payload via cast, correct event_type handling via direction logic
- All security_event=True log calls now have explicit event_type from vocabulary

### Linting & Formatting
- All ruff checks pass (I001 import sorting, F401 unused imports, SIM105/SIM102 simplifications)
- All files formatted with ruff formatter
- No blind type: ignore comments — only one remaining for redis-py typing limitation (upstream issue)

### Test Coverage
- Smoke imports verified: siem_contracts module loads cleanly
- Smoke imports verified: app.security_pipeline submodules (processor, transport, context) load cleanly

## Known Issues / Tech Debt

1. **redis-py Type Stubs**: redis-py's StreamCommands.xadd signature is overly strict in type stubs (requires bytes values); actual implementation accepts str. Using cast() to work around.
   - **Future**: Monitor redis-py for type stub improvements or consider runtime validation wrapper.

2. **Event Type Validation at Runtime**: event_type_str passed to SecurityEvent comes as unchecked str from event_dict; mypy only validates at producer call sites. Could add runtime validation in processor if non-producer code paths emit security_event=True.
   - **Future**: Consider Pydantic validator or check_type() if producer boundary becomes hard to enforce.

## Next Steps (T2 SIEM Service)

- **Ingestion Service**: Consume Redis Stream; parse SecurityEvent; write to cold storage (S3/GCS)
- **Rules Engine**: Apply threshold, sequence, aggregate rules to event stream
- **Alert Generation**: Create alerts, write to AlertDTO queue
- **Dashboard**: Consume alerts, render SIEM dashboard with real-time event feed
- **Tracing Integration**: Link Langfuse traces to security events by request_id

## Test Verification

✅ `make check` passes (ruff + mypy)
✅ Smoke import: siem_contracts module
✅ Smoke import: app.security_pipeline submodules
