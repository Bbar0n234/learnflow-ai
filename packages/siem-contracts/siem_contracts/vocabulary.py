"""Security event type vocabulary for SIEM.

Hierarchical naming convention: <domain>.<subject>.<outcome>
"""

from typing import Literal

# Authentication events
AUTH_LOGIN_FAILED = "auth.login.failed"
AUTH_LOGIN_SUCCESS = "auth.login.success"
AUTH_REFRESH_SUCCESS = "auth.refresh.success"
AUTH_REFRESH_REPLAY_DETECTED = "auth.refresh.replay_detected"
AUTH_REGISTER_SUCCESS = "auth.register.success"
AUTH_REGISTER_FAILED = "auth.register.failed"

# Rate limiter events
RATE_LIMIT_LOGIN_EXCEEDED = "rate_limit.login.exceeded"
RATE_LIMIT_REFRESH_EXCEEDED = "rate_limit.refresh.exceeded"
RATE_LIMIT_REGISTER_EXCEEDED = "rate_limit.register.exceeded"

# Agent security guard events - cross-checkpoint degradation
AGENT_GUARD_DEGRADED = "agent.guard.degraded"

# Agent security guard events - input checkpoint
AGENT_GUARD_INPUT_CLASSIFIER_INJECTION = "agent.guard.input.classifier_injection"
AGENT_GUARD_INPUT_CLASSIFIER_SUSPICIOUS = "agent.guard.input.classifier_suspicious"
AGENT_GUARD_INPUT_CLASSIFIER_CLEAN = "agent.guard.input.classifier_clean"
AGENT_GUARD_INPUT_DETERMINISTIC_HIT = "agent.guard.input.deterministic_hit"

# Agent security guard events - output checkpoint
AGENT_GUARD_OUTPUT_CLASSIFIER_INJECTION = "agent.guard.output.classifier_injection"
AGENT_GUARD_OUTPUT_CLASSIFIER_SUSPICIOUS = "agent.guard.output.classifier_suspicious"
AGENT_GUARD_OUTPUT_CLASSIFIER_CLEAN = "agent.guard.output.classifier_clean"
AGENT_GUARD_OUTPUT_CANARY_LEAK = "agent.guard.output.canary_leak"
AGENT_GUARD_OUTPUT_DETERMINISTIC_HIT = "agent.guard.output.deterministic_hit"

# Agent runtime events
AGENT_RUNTIME_CANARY_STREAM_ABORTED = "agent.runtime.canary.stream_aborted"

# SIEM administrative events
SIEM_ALERT_ACKNOWLEDGED = "siem.alert.acknowledged"
SIEM_ALERT_RESOLVED = "siem.alert.resolved"
SIEM_RULE_CREATED = "siem.rule.created"
SIEM_RULE_UPDATED = "siem.rule.updated"
SIEM_RULE_DELETED = "siem.rule.deleted"

# Unified Literal type for type checking
EventType = Literal[
    # Auth
    "auth.login.failed",
    "auth.login.success",
    "auth.refresh.success",
    "auth.refresh.replay_detected",
    "auth.register.success",
    "auth.register.failed",
    # Rate limit
    "rate_limit.login.exceeded",
    "rate_limit.refresh.exceeded",
    "rate_limit.register.exceeded",
    # Agent guard - cross-checkpoint degradation
    "agent.guard.degraded",
    # Agent guard - input
    "agent.guard.input.classifier_injection",
    "agent.guard.input.classifier_suspicious",
    "agent.guard.input.classifier_clean",
    "agent.guard.input.deterministic_hit",
    # Agent guard - output
    "agent.guard.output.classifier_injection",
    "agent.guard.output.classifier_suspicious",
    "agent.guard.output.classifier_clean",
    "agent.guard.output.canary_leak",
    "agent.guard.output.deterministic_hit",
    # Agent runtime
    "agent.runtime.canary.stream_aborted",
    # SIEM
    "siem.alert.acknowledged",
    "siem.alert.resolved",
    "siem.rule.created",
    "siem.rule.updated",
    "siem.rule.deleted",
]
