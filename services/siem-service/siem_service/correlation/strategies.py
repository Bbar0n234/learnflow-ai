"""Correlation rule evaluation strategies."""

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from siem_service.correlation.deduper import AlertCandidate
from siem_service.domain.models import CorrelationRule, SiemEvent

logger = structlog.get_logger()


class Strategy(Protocol):
    """Correlation rule evaluation contract.

    Implementations are stateless and selected via `get_strategy(rule_type)`.
    """

    async def evaluate(
        self,
        rule: CorrelationRule,
        session: AsyncSession,
    ) -> list[AlertCandidate]:
        """Evaluate rule against events in the window, return alert candidates."""
        ...


class ThresholdStrategy:
    """Threshold strategy: COUNT >= N events of type LIKE pattern in window."""

    async def evaluate(
        self,
        rule: CorrelationRule,
        session: AsyncSession,
    ) -> list[AlertCandidate]:
        """Evaluate threshold rule."""
        config: dict[str, Any] = rule.config or {}

        event_type_pattern = config.get("event_type_pattern")
        threshold = config.get("threshold", 1)
        window_seconds = config.get("window_seconds", 60)
        group_key = config.get("group_key")

        if not event_type_pattern:
            logger.warning("threshold_rule_missing_pattern", rule_id=rule.id)
            return []

        # Calculate window start time (use ingested_at for determinism)
        window_start = datetime.now(UTC) - timedelta(seconds=window_seconds)

        # Build query for events matching pattern in window
        query = select(SiemEvent).where(
            SiemEvent.event_type.ilike(event_type_pattern),
            SiemEvent.ingested_at >= window_start,
        )

        result = await session.execute(query)
        events = result.scalars().all()

        candidates: list[AlertCandidate] = []

        if not group_key and len(events) >= threshold:
            # No grouping: simple count
            # Use first and last event in window
            first_event = min(events, key=lambda e: e.ingested_at)
            latest_event = max(events, key=lambda e: e.ingested_at)
            candidates.append(
                AlertCandidate(
                    rule_id=rule.id,
                    severity=rule.severity,
                    group_key=None,
                    first_event_id=first_event.event_id,
                    latest_event_id=latest_event.event_id,
                )
            )
        else:
            # Group by identifier
            grouped: dict[str, list[SiemEvent]] = {}
            for event in events:
                # Extract group key from identifiers
                identifiers = event.identifiers or {}
                key_value = identifiers.get(group_key) if group_key else None

                # Skip events without required identifier (NULL group_key policy)
                if key_value is None:
                    continue

                key_str = str(key_value)
                if key_str not in grouped:
                    grouped[key_str] = []
                grouped[key_str].append(event)

            # Check each group
            for key_value, group_events in grouped.items():
                if len(group_events) >= threshold:
                    first_event = min(group_events, key=lambda e: e.ingested_at)
                    latest_event = max(group_events, key=lambda e: e.ingested_at)
                    candidates.append(
                        AlertCandidate(
                            rule_id=rule.id,
                            severity=rule.severity,
                            group_key=key_value,
                            first_event_id=first_event.event_id,
                            latest_event_id=latest_event.event_id,
                        )
                    )

        return candidates


class SequenceStrategy:
    """Sequence strategy: Event A followed by Event B within window."""

    async def evaluate(
        self,
        rule: CorrelationRule,
        session: AsyncSession,
    ) -> list[AlertCandidate]:
        """Evaluate sequence rule."""
        config: dict[str, Any] = rule.config or {}

        event_a_pattern = config.get("event_a_pattern")
        event_b_pattern = config.get("event_b_pattern")
        window_seconds = config.get("window_seconds", 600)
        group_key = config.get("group_key")

        if not event_a_pattern or not event_b_pattern:
            logger.warning("sequence_rule_missing_patterns", rule_id=rule.id)
            return []

        window_start = datetime.now(UTC) - timedelta(seconds=window_seconds)

        # Fetch events matching patterns in window
        query_a = select(SiemEvent).where(
            SiemEvent.event_type.ilike(event_a_pattern),
            SiemEvent.ingested_at >= window_start,
        )
        query_b = select(SiemEvent).where(
            SiemEvent.event_type.ilike(event_b_pattern),
            SiemEvent.ingested_at >= window_start,
        )

        result_a = await session.execute(query_a)
        result_b = await session.execute(query_b)

        events_a = result_a.scalars().all()
        events_b = result_b.scalars().all()

        candidates: list[AlertCandidate] = []

        # Find A followed by B pairs
        for event_a in events_a:
            for event_b in events_b:
                # B must occur after A within window
                if event_b.ingested_at <= event_a.ingested_at:
                    continue

                # Check group key match if specified
                if group_key:
                    id_a = (event_a.identifiers or {}).get(group_key)
                    id_b = (event_b.identifiers or {}).get(group_key)
                    if id_a != id_b or id_a is None:
                        continue
                    key_value = str(id_a)
                else:
                    key_value = None

                candidates.append(
                    AlertCandidate(
                        rule_id=rule.id,
                        severity=rule.severity,
                        group_key=key_value,
                        first_event_id=event_a.event_id,
                        latest_event_id=event_b.event_id,
                    )
                )

        return candidates


class AggregateStrategy:
    """Aggregate strategy: COUNT >= N events matching pattern, no grouping."""

    async def evaluate(
        self,
        rule: CorrelationRule,
        session: AsyncSession,
    ) -> list[AlertCandidate]:
        """Evaluate aggregate rule (equivalent to threshold without group_key)."""
        config: dict[str, Any] = rule.config or {}

        event_type_pattern = config.get("event_type_pattern")
        threshold = config.get("threshold", 1)
        window_seconds = config.get("window_seconds", 300)

        if not event_type_pattern:
            logger.warning("aggregate_rule_missing_pattern", rule_id=rule.id)
            return []

        window_start = datetime.now(UTC) - timedelta(seconds=window_seconds)

        # Count events matching pattern in window
        query = select(SiemEvent).where(
            SiemEvent.event_type.ilike(event_type_pattern),
            SiemEvent.ingested_at >= window_start,
        )

        result = await session.execute(query)
        events = result.scalars().all()

        if len(events) >= threshold:
            first_event = min(events, key=lambda e: e.ingested_at)
            latest_event = max(events, key=lambda e: e.ingested_at)
            return [
                AlertCandidate(
                    rule_id=rule.id,
                    severity=rule.severity,
                    group_key=None,
                    first_event_id=first_event.event_id,
                    latest_event_id=latest_event.event_id,
                )
            ]

        return []


def get_strategy(rule_type: str) -> Strategy:
    """Get strategy for rule type.

    Raises ValueError for unknown rule_type so the per-rule try/except in
    CorrelationEngine logs the error and skips the rule without crashing the
    engine (F-SIEM-G4: one failing rule must not stop the correlation cycle).
    Unknown values indicate a DB record created before schema tightening —
    silent fallback to ThresholdStrategy is intentionally avoided.
    """
    strategies: dict[str, Strategy] = {
        "threshold": ThresholdStrategy(),
        "sequence": SequenceStrategy(),
        "aggregate": AggregateStrategy(),
    }
    if rule_type not in strategies:
        logger.warning("unknown rule type in correlation engine", rule_type=rule_type)
        raise ValueError(f"Unknown rule_type: {rule_type!r}")
    return strategies[rule_type]
