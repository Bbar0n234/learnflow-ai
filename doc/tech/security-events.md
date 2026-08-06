# Security Events Vocabulary

## Overview

Security events are structured, typed messages emitted from various components of the LearnFlowAI platform. They serve as the contract between **producers** (main app) and **consumer** (SIEM service) for the feat-005 security event pipeline.

## Event Type Hierarchy

Event types follow the naming convention: `<domain>.<subject>.<outcome>`

### Domains

| Domain | Purpose | Components |
|--------|---------|-----------|
| `auth` | Authentication and session events | Login, registration, refresh token flows |
| `rate_limit` | Rate limiting triggers | Request throttling per scope |
| `agent.guard` | Security guard (input/output/tool) | Injection detection, canary checks |
| `agent.runtime` | Agent runtime events | Stream abortion, canary leaks |
| `siem` | SIEM administrative events | Alert state transitions, rule CRUD |

### Complete Event Type Catalog

#### Authentication Events

| Event Type | Severity | Occurs When | Identifiers |
|------------|----------|-------------|-------------|
| `auth.login.success` | `info` | User successfully authenticates | `ip`, `request_id`, `user_id` |
| `auth.login.failed` | `warning` | Login attempt fails (invalid credentials) | `ip`, `request_id` |
| `auth.register.success` | `info` | New user account created | `ip`, `request_id`, `user_id` |
| `auth.register.failed` | `warning` | Registration fails (username exists, etc) | `ip`, `request_id` |
| `auth.refresh.success` | `info` | Refresh token successfully exchanged | `request_id`, `user_id`, `session_id` |
| `auth.refresh.replay_detected` | `critical` | Token replay attack detected | `request_id`, `user_id` |

#### Rate Limit Events

| Event Type | Severity | Occurs When | Identifiers |
|------------|----------|-------------|-------------|
| `rate_limit.login.exceeded` | `warning` | Login rate limit exceeded | `ip`, `request_id` |
| `rate_limit.register.exceeded` | `warning` | Registration rate limit exceeded | `ip`, `request_id` |
| `rate_limit.refresh.exceeded` | `warning` | Refresh rate limit exceeded | `ip`, `request_id` |

#### Security Guard Events - Degradation (cross-checkpoint)

| Event Type | Severity | Occurs When | Identifiers |
|------------|----------|-------------|-------------|
| `agent.guard.degraded` | `critical` | LLM guard degraded to CLEAN (LLM exception or classifier retries exhausted) | `request_id`, `thread_id`, `user_id` |

#### Security Guard Events - Input Checkpoint

| Event Type | Severity | Occurs When | Identifiers |
|------------|----------|-------------|-------------|
| `agent.guard.input.deterministic_hit` | `critical` | Deterministic detector (Unicode, Fragment, Paired Tool) matches | `request_id`, `thread_id`, `user_id` |
| `agent.guard.input.classifier_injection` | `critical` | LLM classifier detects injection | `request_id`, `thread_id`, `user_id` |
| `agent.guard.input.classifier_suspicious` | `warning` | LLM classifier detects suspicious input | `request_id`, `thread_id`, `user_id` |
| `agent.guard.input.classifier_clean` | `info` | LLM classifier passes all checks | (optional) |

#### Security Guard Events - Output Checkpoint

| Event Type | Severity | Occurs When | Identifiers |
|------------|----------|-------------|-------------|
| `agent.guard.output.deterministic_hit` | `critical` | Deterministic detector matches output | `request_id`, `thread_id`, `user_id` |
| `agent.guard.output.classifier_injection` | `critical` | LLM classifier detects injection in output | `request_id`, `thread_id`, `user_id` |
| `agent.guard.output.classifier_suspicious` | `warning` | LLM classifier detects suspicious output | `request_id`, `thread_id`, `user_id` |
| `agent.guard.output.classifier_clean` | `info` | LLM classifier passes all checks | (optional) |
| `agent.guard.output.canary_leak` | `critical` | Canary token leaked in output | `request_id`, `thread_id`, `user_id` |

#### Agent Runtime Events

| Event Type | Severity | Occurs When | Identifiers |
|------------|----------|-------------|-------------|
| `agent.runtime.canary.stream_aborted` | `critical` | Streaming aborted due to canary detection | `request_id`, `thread_id`, `user_id` |

#### SIEM Administrative Events

| Event Type | Severity | Occurs When | Identifiers |
|------------|----------|-------------|-------------|
| `siem.alert.acknowledged` | `info` | Admin acknowledges security alert | `user_id` (admin) |
| `siem.alert.resolved` | `info` | Admin resolves security alert | `user_id` (admin) |
| `siem.rule.created` | `info` | New correlation rule created | `user_id` (admin) |
| `siem.rule.updated` | `info` | Correlation rule modified | `user_id` (admin) |
| `siem.rule.deleted` | `info` | Correlation rule deleted | `user_id` (admin) |

## Identifiers

Identifiers are extracted from request/session context and injected into events via `structlog.contextvars`.

| Identifier | Meaning | Binding Point | Optional |
|------------|---------|---------------|----------|
| `ip` | Client IP address | HTTP middleware, via `get_client_ip` (source selected by `CLIENT_IP_SOURCE`) | Yes (never bound on the health-check path) |
| `request_id` | Unique HTTP request ID | HTTP middleware (UUID) | No |
| `user_id` | Authenticated user ID | Auth dependency (from JWT) | Yes (absent for unauthenticated requests) |
| `session_id` | Refresh token session ID | Auth dependency (from token JTI) | Yes (only for authenticated requests) |
| `thread_id` | Chat thread/conversation ID | Chat route handler | Yes (only in /chat/... routes) |
| `project_id` | Project scope ID | Chat route handler | Yes (only in /chat/... routes) |
| `user_agent_hash` | SHA256 hash of User-Agent header | HTTP middleware | Yes |

### Rules for Identifiers

- **Binding is automatic**: Call sites never manually construct identifiers; they're extracted from contextvars by `SecurityEventProcessor`.
- **NULL handling**: If a correlation rule requires `group_key=user_id` but the event has no `user_id`, the event is skipped in that rule's window.
- **Always present**: `request_id` is always present (generated in HTTP middleware); others are conditional.

## Metadata

Metadata is event-specific contextual information beyond identifiers. It is unstructured (`dict[str, Any]`) per event.

### Common Metadata Fields

Certain fields appear across multiple event types for consistency and filtering:

| Field | Type | Present For | Purpose |
|-------|------|-------------|---------|
| `checkpoint` | `str` | `agent.guard.*` events | Which checkpoint (input, output, tool_call, etc) |
| `detection_layer` | `str` | `agent.guard.*` events | Layer that triggered: `deterministic`, `llm_classifier`, `canary` |
| `verdict` | `str` | `agent.guard.*` events | Result: `injection`, `suspicious`, `clean` |
| `domain` | `str` | All events | Duplicate of event_type domain for convenience |
| `reason` | `str` | Failure events | Human-readable explanation (e.g., "invalid_credentials", "username_exists") |

### Event-Specific Metadata

Additional metadata per event:

| Event Type | Metadata Fields |
|------------|-----------------|
| `auth.login.failed` | `username` (attempted login) |
| `auth.register.failed` | `username` (attempted registration), `reason` |
| `agent.guard.input.deterministic_hit` | `detector` (detector name), `details` (match specifics) |
| `agent.guard.*.classifier_*` | `reasoning` (LLM reasoning), `retries` (classifier retries) |
| `agent.guard.output.canary_leak` | `leaked_value` (indicator of leak) |
| `rate_limit.*` | `key` (rate limit key), `limit` (threshold), `window` (seconds) |

## Binding Sequence

Events are enriched with identifiers through the request lifecycle:

```
HTTP Request → HTTP Middleware (bind ip, request_id, user_agent_hash)
            → Auth Dependency (bind user_id, session_id)
            → Chat Route Handler (bind thread_id, project_id)
            → Business Logic → SecurityGuard or AuthService (log with security_event=True)
            → structlog processor (extract identifiers from contextvars)
            → Transport Publisher (enqueue for Redis)
```

## Contract Stability

- **Producer side**: `event_type` is `Literal[...]` (mypy-checked). Opaque field values (e.g., `metadata`) are flexible.
- **Consumer side**: Pydantic validates schema strictly; `event_type` is `Literal[...]` from the same shared package, so unknown values are rejected (counted in `siem_events_invalid`). Drift невозможен в monorepo: producer и consumer импортируют контракт из одного источника. Полная мотивация — [ADR-020 §5](adr/ADR-020-security-event-contract.md).
- **Adding new types**: New `event_type` values are added to `packages/siem-contracts/siem_contracts/vocabulary.py` и подхватываются producer'ом и consumer'ом одновременно.

## Example Events

### Auth Success
```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "event_type": "auth.login.success",
  "severity": "info",
  "timestamp": "2024-05-04T12:00:00Z",
  "identifiers": {
    "ip": "192.168.1.1",
    "request_id": "req-abc123",
    "user_id": "user-456"
  },
  "metadata": {
    "username": "john_doe",
    "domain": "auth"
  }
}
```

### Injection Detected
```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440001",
  "event_type": "agent.guard.input.classifier_injection",
  "severity": "critical",
  "timestamp": "2024-05-04T12:00:05Z",
  "identifiers": {
    "request_id": "req-abc123",
    "thread_id": "thread-789",
    "user_id": "user-456",
    "ip": "192.168.1.1"
  },
  "metadata": {
    "checkpoint": "input",
    "detection_layer": "llm_classifier",
    "verdict": "injection",
    "reasoning": "Attempted to override system prompt",
    "retries": 0,
    "domain": "agent.guard"
  }
}
```

### Rate Limit Exceeded
```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440002",
  "event_type": "rate_limit.login.exceeded",
  "severity": "warning",
  "timestamp": "2024-05-04T12:00:10Z",
  "identifiers": {
    "ip": "192.168.2.50",
    "request_id": "req-def456"
  },
  "metadata": {
    "key": "login:attacker:192.168.2.50",
    "limit": 5,
    "window": 60,
    "domain": "rate_limit"
  }
}
```
