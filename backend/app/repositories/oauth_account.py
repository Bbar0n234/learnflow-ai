from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.oauth_account import OAuthAccount


class OAuthAccountRepository:
    """ORM-CRUD для ``oauth_accounts`` — без бизнес-логики (find-or-create
    и retry на unique violation живут в ``app.services.oauth.OAuthService``).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_provider_account(
        self, provider: str, provider_account_id: str
    ) -> OAuthAccount | None:
        result = await self._session.execute(
            select(OAuthAccount).where(
                OAuthAccount.provider == provider,
                OAuthAccount.provider_account_id == provider_account_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, account: OAuthAccount) -> OAuthAccount:
        self._session.add(account)
        await self._session.flush()
        return account
