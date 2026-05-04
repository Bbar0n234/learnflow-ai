"""Correlation engine for alert generation."""

import asyncio

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from siem_service.correlation.deduper import AlertDeduper
from siem_service.correlation.strategies import get_strategy
from siem_service.db import get_async_session_maker
from siem_service.models import CorrelationRule

logger = structlog.get_logger()


class CorrelationEngine:
    """Main correlation engine: loads rules, evaluates them, creates alerts."""

    def __init__(self, poll_interval_seconds: float = 10.0) -> None:
        """Initialize engine."""
        self.poll_interval = poll_interval_seconds
        self._running = False

    async def start(self) -> None:
        """Start the correlation engine polling loop."""
        self._running = True
        logger.info("correlation_engine_started", poll_interval=self.poll_interval)

        while self._running:
            try:
                await self.evaluate_rules()
            except Exception as e:
                logger.error(
                    "correlation_engine_error",
                    error=str(e),
                    exc_info=True,
                )

            # Sleep before next poll
            await asyncio.sleep(self.poll_interval)

    async def stop(self) -> None:
        """Stop the correlation engine."""
        self._running = False
        logger.info("correlation_engine_stopped")

    async def evaluate_rules(self) -> None:
        """Load active rules and evaluate each one."""
        session_maker = get_async_session_maker()
        async with session_maker() as session:
            # Load all enabled rules
            query = select(CorrelationRule).where(CorrelationRule.enabled.is_(True))
            result = await session.execute(query)
            rules = result.scalars().all()

            for rule in rules:
                try:
                    await self._evaluate_single_rule(rule, session)
                except Exception as e:
                    logger.error(
                        "rule_evaluation_error",
                        rule_id=rule.id,
                        rule_name=rule.name,
                        error=str(e),
                        exc_info=True,
                    )

            # Commit all alert changes
            await session.commit()

    async def _evaluate_single_rule(
        self,
        rule: CorrelationRule,
        session: AsyncSession,
    ) -> None:
        """Evaluate a single rule."""
        strategy = get_strategy(rule.rule_type)  # type: ignore[arg-type]  # rule_type is SQLAlchemy Column[str], not literal str

        # Get alert candidates from strategy
        candidates = await strategy.evaluate(rule, session)

        # Process each candidate through deduper
        for candidate in candidates:
            alert = await AlertDeduper.dedupe(candidate, session)
            if alert:
                logger.info(
                    "alert_processed",
                    rule_id=rule.id,
                    alert_id=alert.id,
                    rule_type=rule.rule_type,
                )


# Global engine instance
_engine: CorrelationEngine | None = None


def get_correlation_engine(poll_interval_seconds: float = 10.0) -> CorrelationEngine:
    """Get or create correlation engine."""
    global _engine
    if _engine is None:
        _engine = CorrelationEngine(poll_interval_seconds)
    return _engine
