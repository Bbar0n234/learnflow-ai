from __future__ import annotations

import secrets

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.infra.oauth.base import OAuthProfile
from app.models.oauth_account import OAuthAccount
from app.models.user import User
from app.repositories.oauth_account import OAuthAccountRepository
from app.repositories.user import UserRepository
from app.services.auth import AuthService
from app.services.exceptions import OAuthAccountCreationError

logger = structlog.get_logger()

_NAME_MAX_LENGTH = 100  # RegisterRequest.name зеркалит тот же потолок
_MAX_NAME_ATTEMPTS = 5  # базовый кандидат + до 4 ретраев с суффиксом
_SUFFIX_HEX_BYTES = (
    2  # "_" + 4 hex-символа, по образцу alice_x7f3 из research-data-model.md
)

# Naming convention (app/models/base.py: "uq_%(table_name)s_%(column_0_name)s"):
# оба constraint'а различаются table_name, column_0 у обоих — первая колонка
# соответствующего UniqueConstraint.
_USERS_NAME_CONSTRAINT = "uq_users_name"
_OAUTH_ACCOUNT_CONSTRAINT = "uq_oauth_accounts_provider"


def _base_candidate_name(profile: OAuthProfile) -> str:
    """Кандидат для ``users.name``: нормализованный ``display_name`` профиля,
    либо фолбэк ``<provider>_<суффикс>`` (research-data-model.md § Генерация
    users.name). Провайдер-специфичный выбор поля (login/given_name/…) уже
    сделан внутри ``fetch_profile`` каждого провайдера — здесь только общая
    часть: нормализация и фолбэк для пустого/отсутствующего значения.
    """
    raw = (profile.display_name or "").strip()
    if raw:
        normalized = " ".join(raw.split())
        if normalized:
            return normalized[:_NAME_MAX_LENGTH]
    return f"{profile.provider}_{secrets.token_hex(_SUFFIX_HEX_BYTES)}"


def _suffixed_candidate_name(base: str) -> str:
    suffix = f"_{secrets.token_hex(_SUFFIX_HEX_BYTES)}"
    return f"{base[: _NAME_MAX_LENGTH - len(suffix)]}{suffix}"


def _constraint_name(exc: IntegrityError) -> str | None:
    """Имя нарушенного constraint'а из DBAPI-исключения.

    Драйвер — psycopg3 (``postgresql+psycopg``, backend/pyproject.toml), не
    asyncpg: ``psycopg.errors.UniqueViolation`` несёт имя constraint'а в
    ``.diag.constraint_name`` (``Diagnostic``), не как плоский атрибут на
    самом исключении — плоский ``getattr(exc.orig, "constraint_name", None)``
    молча вернул бы ``None`` и увёл обе ветки retry в ``raise``.
    """
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


class OAuthService:
    """Find-or-create по нормализованному ``OAuthProfile`` + выдача сессии.

    Одна транзакция на вызов: обе ветки (найден/не найден) укладываются в
    транзакцию, открытую ``get_db_session`` (app/api/deps.py) для текущего
    запроса — сервис не коммитит и не открывает свою верхнеуровневую
    транзакцию, только SAVEPOINT'ы (``session.begin_nested()``) для retry
    внутри неё (design-brief.md § Эндпоинты, research-data-model.md —
    «атомарно через constraint, не SELECT-then-INSERT»).
    """

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._oauth_repo = OAuthAccountRepository(session)
        self._user_repo = UserRepository(session)
        self._auth_service = AuthService(session, settings)

    async def login_with_provider(
        self, profile: OAuthProfile
    ) -> tuple[User, str, str, bool]:
        """Возвращает ``(user, access, refresh, new_user)``. ``new_user``
        различает создание аккаунта от логина уже существующей связки —
        нужно вызывающему (``routes/oauth.py``, T1.6) для поля ``new_user``
        события ``AUTH_OAUTH_SUCCESS`` (design-brief.md § Эндпоинты).
        """
        account = await self._oauth_repo.get_by_provider_account(
            profile.provider, profile.provider_account_id
        )
        if account is not None:
            return await self._login_existing(account, profile)
        return await self._create_and_login(profile)

    async def _login_existing(
        self, account: OAuthAccount, profile: OAuthProfile
    ) -> tuple[User, str, str, bool]:
        user = await self._user_repo.get_by_id(account.user_id)
        if user is None:
            # FK ondelete=CASCADE удаляет связку вместе с пользователем —
            # живая oauth_accounts-строка без users-строки не должна
            # существовать. Защитная ветка на случай рассинхрона, не
            # ожидаемый путь; не 500 наружу.
            logger.warning(
                "oauth account references missing user",
                provider=profile.provider,
                account_id=str(account.id),
            )
            raise OAuthAccountCreationError
        # Освежение email на каждом входе — источник истины «что сообщил
        # провайдер сейчас» (research-data-model.md § Таблица решений,
        # updated_at не декоративен).
        account.email = profile.email
        access_token, refresh_raw = await self._auth_service.issue_session(user)
        return user, access_token, refresh_raw, False

    async def _create_and_login(
        self, profile: OAuthProfile
    ) -> tuple[User, str, str, bool]:
        base_name = _base_candidate_name(profile)
        candidate = base_name
        for attempt in range(_MAX_NAME_ATTEMPTS):
            if attempt > 0:
                candidate = _suffixed_candidate_name(base_name)
            user = User(name=candidate, password_hash=None)
            account = OAuthAccount(
                user=user,
                provider=profile.provider,
                provider_account_id=profile.provider_account_id,
                email=profile.email,
            )
            try:
                # SAVEPOINT: на IntegrityError откатывает только эту попытку
                # (оба INSERT — users и oauth_accounts), не всю транзакцию
                # запроса — retry с новым именем продолжает ту же сессию.
                async with self._session.begin_nested():
                    self._session.add(user)
                    await self._oauth_repo.create(account)
            except IntegrityError as exc:
                constraint = _constraint_name(exc)
                if constraint == _USERS_NAME_CONSTRAINT:
                    logger.warning(
                        "oauth user name collision, retrying with suffix",
                        provider=profile.provider,
                        attempt=attempt,
                    )
                    continue
                if constraint == _OAUTH_ACCOUNT_CONSTRAINT:
                    logger.warning(
                        "oauth account race detected on create, degrading to lookup",
                        provider=profile.provider,
                    )
                    return await self._login_after_race(profile)
                raise
            else:
                access_token, refresh_raw = await self._auth_service.issue_session(user)
                return user, access_token, refresh_raw, True

        logger.warning(
            "oauth user name generation exhausted retry budget",
            provider=profile.provider,
            attempts=_MAX_NAME_ATTEMPTS,
        )
        raise OAuthAccountCreationError

    async def _login_after_race(
        self, profile: OAuthProfile
    ) -> tuple[User, str, str, bool]:
        """Повторный lookup после гонки двойного callback'а на unique
        ``(provider, provider_account_id)`` — login-путь, не 500."""
        account = await self._oauth_repo.get_by_provider_account(
            profile.provider, profile.provider_account_id
        )
        if account is None:
            # Unique violation срабатывает только против уже закоммиченной
            # конфликтующей строки (Postgres блокирует на индексной
            # блокировке до commit/rollback конкурента) — промах здесь
            # означает неожиданное состояние БД, не саму гонку.
            logger.warning(
                "oauth account race degraded to lookup but found nothing",
                provider=profile.provider,
            )
            raise OAuthAccountCreationError
        return await self._login_existing(account, profile)
