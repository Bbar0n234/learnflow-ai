"""Alert deduplication logic with open-alert policy."""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from siem_service.models import SiemAlert

logger = structlog.get_logger()

# Maximum alert age before forced new alert creation (24 hours)
MAX_ALERT_AGE_SECONDS = 86400 # TODO: Вопрос, не должна ли эта константа жить в переменных окружения? Да, это, конечно, не супер частая штука, которая будет меняться, и тем не менее хотелось бы, наверное, её... хотелось бы иметь возможность её менять без пересборки контейнера, как я считаю.

# TODO: Также накидаю свои мысли в целом, уже скорее не относящиеся к этому файлу, но куда-то их всё равно нужно закинуть. Во-первых, по поводу этого CM (SIEM)-сервиса. Непонятно, почему он сейчас внутри непосредственно директории packages. То есть я, конечно, могу путать, я могу ошибаться, но, по-моему, packages — это у нас директория для так называемых shared packages, для общего кода, который нужно импортировать в различные сервисы, правильно? И, например, package CM-контракты действительно должен быть, потому что его импортирует и бэкенд, и CM-сервис. А CM-сервис никто не импортирует, и как бы, мне кажется, он должен быть на уровень выше, хотя опять же, возможно, я заблуждаюсь. Также я вот смотрю, тут довольно много всяких файлов в корне, то есть не вынесенных по поддиректориям. И, на мой взгляд, стоит рассмотреть вариант с какой-то, может быть, не знаю, детерминированной проверкой. Чтобы, знаешь, на уровне форматера или линтера, чтобы наш агент, когда запускал всё, все инструменты через make. То есть, не знаю, какой-нибудь триггер тоже, который бы срабатывал, там, если условно там в одном репозитории больше десяти файлов, значит, это уже какой-то флаг, и, скорее всего, стоит как бы пофиксить, разбить ещё на поддиректории. Но это у меня такие мысли, опять же, могу быть неправым. Вот. Но опять же стоит рассмотреть, прикинуть такие варианты, плюсы-минусы и только потом решить там, делать или не делать. 


class AlertCandidate:
    """Alert candidate from correlation engine."""

    def __init__(
        self,
        rule_id: int,
        severity: str,
        group_key: str | None,
        first_event_id: UUID,
        latest_event_id: UUID,
    ) -> None:
        """Initialize alert candidate."""
        self.rule_id = rule_id
        self.severity = severity
        self.group_key = group_key
        self.first_event_id = first_event_id
        self.latest_event_id = latest_event_id


class AlertDeduper:
    """Handles alert deduplication with open-alert policy."""

    @staticmethod
    async def dedupe(
        candidate: AlertCandidate,
        session: AsyncSession,
    ) -> Optional[SiemAlert]:
        """
        Apply open-alert policy: find existing new alert for (rule_id, group_key).

        Returns:
            SiemAlert instance if alert was found and updated, or newly created alert.
        """
        now = datetime.now(timezone.utc)
        age_threshold = now - timedelta(seconds=MAX_ALERT_AGE_SECONDS)

        # Find open alert (new status) for this rule and group_key, created within 24h
        query = select(SiemAlert).where(
            SiemAlert.rule_id == candidate.rule_id,
            SiemAlert.status == "new",
            SiemAlert.created_at >= age_threshold,
        )

        # If group_key is provided, match it exactly
        # If group_key is NULL (for Aggregate rules), match NULL
        if candidate.group_key is not None:
            query = query.where(SiemAlert.group_key == candidate.group_key)
        else:
            query = query.where(SiemAlert.group_key.is_(None))

        result = await session.execute(query)
        existing_alert = result.scalar_one_or_none()

        if existing_alert:
            # Append to existing alert
            existing_alert.matched_events_count += 1  # type: ignore[assignment] # SQLAlchemy Column type
            existing_alert.latest_event_id = candidate.latest_event_id  # type: ignore[assignment] # SQLAlchemy Column type
            existing_alert.updated_at = now  # type: ignore[assignment] # SQLAlchemy Column type
            session.add(existing_alert)
            logger.info(
                "alert_appended",
                rule_id=candidate.rule_id,
                alert_id=existing_alert.id,
                group_key=candidate.group_key,
            )
            return existing_alert

        # Create new alert
        new_alert = SiemAlert(
            rule_id=candidate.rule_id,
            severity=candidate.severity,
            status="new",
            group_key=candidate.group_key,
            matched_events_count=1,
            first_event_id=candidate.first_event_id,
            latest_event_id=candidate.latest_event_id,
        )
        session.add(new_alert)
        logger.info(
            "alert_created",
            rule_id=candidate.rule_id,
            group_key=candidate.group_key,
            severity=candidate.severity,
        )
        return new_alert
