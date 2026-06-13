"""Correlation engine for alert generation."""

import asyncio
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from siem_service.correlation.deduper import AlertDeduper
from siem_service.correlation.strategies import get_strategy
from siem_service.domain.models import CorrelationRule, SiemAlert

logger = structlog.get_logger()


class CorrelationEngine:
    """Main correlation engine: loads rules, evaluates them, creates alerts."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        poll_interval_seconds: float = 10.0,
        alert_open_window_seconds: int = 86400,
    ) -> None:
        """Initialize engine."""
        self._session_factory = session_factory
        self.poll_interval = poll_interval_seconds
        self._alert_open_window_seconds = alert_open_window_seconds
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
        async with self._session_factory() as session:
            await self._expire_stale_alerts(session)

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

    async def _expire_stale_alerts(self, session: AsyncSession) -> None:
        """Перевести открытые алерты старше окна в `expired`.

        Открытый алерт перестаёт принимать дозаписи по истечении окна —
        следующее срабатывание правила поднимет свежий `new`-алерт (политика
        «застоявшееся должно перевсплыть»). Поддерживает инвариант частичного
        уникального индекса uq_siem_alerts_open_alert.
        """
        threshold = datetime.now(UTC) - timedelta(
            seconds=self._alert_open_window_seconds
        )
        result = await session.execute(
            update(SiemAlert)
            .where(SiemAlert.status == "new", SiemAlert.created_at < threshold)
            .values(status="expired")
            .returning(SiemAlert.id)
        )
        expired_ids = result.scalars().all()
        if expired_ids:
            logger.info("alerts_expired", count=len(expired_ids))

    async def _evaluate_single_rule(
        self,
        rule: CorrelationRule,
        session: AsyncSession,
    ) -> None:
        """Evaluate a single rule."""
        strategy = get_strategy(rule.rule_type)

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
