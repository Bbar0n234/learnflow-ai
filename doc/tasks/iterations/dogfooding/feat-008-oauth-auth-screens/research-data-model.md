# Ресёрч: модель данных OAuth-входа

Выжимка ресёрча при взятии итерации в работу (август 2026). Спроектировано и проревьюировано по skill `postgresql`; эталоны сверены по Auth.js/NextAuth, Django allauth, better-auth, Rails omniauth. Вход для design-brief.

Вводные решения архитектора: провайдеры Яндекс ID / VK ID / Google / GitHub (вертикаль сначала на Яндексе); идентичность = `(provider, provider_account_id)`; авто-линковка по email в v1 запрещена (риск pre-account-takeover); ручная линковка — за скоупом v1, но схема не должна ей мешать; password-вход остаётся.

## Сводка ресёрча эталонов

| Система | Таблица | Ключевые поля | Уникальность | Токены провайдера | Сырой профиль |
|---|---|---|---|---|---|
| Auth.js/NextAuth (`accounts`) | отдельная | userId FK, provider, providerAccountId, type | unique(provider, providerAccountId) | хранит (access/refresh/id_token, expires_at, scope) — т.к. JS-экосистема дальше зовёт API провайдера | нет |
| Django allauth (`SocialAccount`) | отдельная | user FK, provider, uid, last_login, date_joined | unique_together(provider, uid) | **отдельная таблица SocialToken, `SOCIALACCOUNT_STORE_TOKENS` default `False`** | `extra_data` JSONField |
| better-auth (`account`) | отдельная | userId FK, providerId, accountId, createdAt, updatedAt | (providerId, accountId) | хранит опционально; password-кредо — тоже строка в `account` | нет |
| Rails omniauth-паттерн (`identities`) | отдельная | user FK, provider, uid | unique(provider, uid) | хранят, только если дальше зовут API провайдера | по вкусу |

Консенсус: **отдельная таблица identity-связок, ядро — (user_id, provider, provider_account_id) + unique(provider, provider_account_id)**. Тезис «токены провайдера не хранить» ресёрчем **подтверждён**: хранение нужно только для последующих вызовов API провайдера (кейс Auth.js); для чистой аутентификации эталон — allauth с дефолтом «не хранить». У нас OAuth используется одноразово на входе, свои сессии — свой `refresh_tokens`.

## Итоговый DDL-эскиз

Новая модель `backend/app/models/oauth_account.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User

OAUTH_PROVIDERS = ("yandex", "vk", "google", "github")


class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_account_id"),
        CheckConstraint(
            "provider IN ('yandex', 'vk', 'google', 'github')",
            name="provider_allowed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(Text)
    provider_account_id: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="oauth_accounts")
```

Изменение `User` (`backend/app/models/user.py`):

```python
password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
# + relationship:
oauth_accounts: Mapped[list[OAuthAccount]] = relationship(
    back_populates="user", cascade="all, delete-orphan"
)
```

**Миграция (словесно):** одна autogenerate-ревизия против запущенной БД (`make docker-up-db` → `make migrate` → правка моделей → `make migration msg="oauth accounts"`). Содержимое: `create_table oauth_accounts` (PK, FK с `ondelete=CASCADE`, `ix_oauth_accounts_user_id`, `uq_oauth_accounts_provider` на пару колонок, `ck_oauth_accounts_provider_allowed`) + `alter_column users.password_hash nullable=True`. Данные не трогаются, существующие пользователи с паролями не затронуты. Ручная миграция не нужна. Downgrade вернёт `NOT NULL` — упадёт при наличии OAuth-пользователей, это ожидаемо и приемлемо.

## Таблица решений

| Решение | Выбор | Обоснование |
|---|---|---|
| Таблица vs поля в users | Отдельная `oauth_accounts` | Единогласный эталон (все 4 системы). Поля в users ограничили бы одного провайдера на пользователя и заблокировали будущую ручную линковку; таблица 1:N ей не мешает, ничего не меняя в v1 |
| Идентичность | `unique(provider, provider_account_id)` | Требование архитектора = эталонный минимум. Гонка создания решается самим constraint'ом: `INSERT` + обработка unique violation, не SELECT-then-INSERT (db.md, «бизнес-инварианты — в БД») |
| `password_hash` | → nullable | OAuth-пользователь пароля не имеет. NULL = «пароль не установлен» — честная семантика; логин по паролю при NULL отклоняется. Инвариант «password_hash IS NOT NULL OR существует oauth_account» — кросс-табличный, в CHECK не выражается, контролируется сервисным слоем (создание OAuth-user и его oauth_account — одна транзакция) |
| Email в `users` | **Не вводить в v1**; email от провайдера — nullable-колонка в `oauth_accounts` | В v1 email не участвует ни в логине, ни в линковке. `users.email` осмыслен только с unique + verified-семантикой — а неверифицированный уникальный email как раз открывает pre-account-takeover. GitHub может скрывать email → NULL допустим по построению. Email фиксируется как факт «что сообщил провайдер на момент входа» — пригодится для будущей линковки/нотификаций. Будущее введение `users.email` (nullable + partial unique `WHERE email IS NOT NULL`) схемой не заблокировано |
| Провайдеры | `Text` + CHECK `provider IN (...)` | Конвенция db.md для enum-подобных строк, зашитых в код; pg-ENUM в проекте запрещён. Новый провайдер = код + миграция в одном PR — осознанная цена, уже принятая проектом |
| Генерация `users.name` | Сервисный слой: кандидат из провайдера (login у Яндекс/GitHub, given name у Google, имя у VK; фолбэк — `<provider>_<короткий суффикс>`) → нормализация → `INSERT`; на unique violation — суффикс (`alice` → `alice_x7f3`) и повтор, с ограничением попыток | Атомарно через constraint (без гонки SELECT-then-INSERT). `name` остаётся стабильным идентификатором для UI и не переименовывается вслед за профилем провайдера |
| `created_at`/`updated_at` | Оба, по конвенции (`server_default=func.now()`, `onupdate` для updated_at) | `updated_at` не декоративен: на каждом OAuth-входе допустимо освежать `email` — строка мутирует |
| Токены провайдера | **Не хранить** | Подтверждено эталоном (allauth default False). code→token→userinfo используется одноразово; хранение — лишняя секретная поверхность (шифрование, ротация, утечки) без потребителя: API провайдеров после входа не зовём |
| Сырой профиль (jsonb) | Не хранить в v1 | Единственное нужное поле (email) вынесено явной колонкой. `extra_data` — свалка PII без потребителя; добавить `raw_profile JSONB` позже — одна тривиальная миграция |
| `refresh_tokens` | Без изменений | Уже провайдер-агностична: сессия привязана к user_id, не к способу входа |

## Отвергнутые альтернативы

- **Поля `oauth_provider`/`oauth_uid` прямо в `users`** — блокирует несколько провайдеров на пользователя (заявленное будущее), NULL-пары для парольных пользователей, кривой unique по nullable-паре. Ни один эталон так не делает.
- **Sentinel вместо nullable `password_hash`** (невалидный хеш à la Django `!`-префикс) — магическое значение в данных вместо честного NULL; verify и так упадёт, но семантику «пароля нет» из схемы не видно. Django к этому привязан историческим NOT NULL, у нас такого багажа нет.
- **Password-кредо как строка в `oauth_accounts`** (паттерн better-auth: провайдер `credential`) — красивая унификация, но требует миграции текущих парольных пользователей и перестройки auth-сервиса; для v1 неоправданный объём. Схема v1 не мешает прийти к этому позже.
- **`users.email` NOT NULL / unique уже сейчас** — GitHub скрывает email (NULL по построению), а уникальный неверифицированный email — заготовка pre-account-takeover; вводить его без email-фичей незачем.
- **Отдельная таблица токенов провайдера** (SocialToken) — нет потребителя: провайдерские API после входа не вызываем.
- **pg-ENUM для provider** — запрещён конвенцией проекта (дорог в эволюции), CHECK дешевле.

## Что из эталонов сознательно не взяли

- **Токены провайдера** (Auth.js: access/refresh/id_token, expires_at, scope, token_type, session_state) — весь блок существует ради последующих вызовов API провайдера; наш сценарий — только вход.
- **`extra_data`/raw profile jsonb** (allauth) — нет потребителя, PII-балласт.
- **`last_login` на identity-строке** (allauth) — активность видна по `refresh_tokens` и структурным логам; при нужде добавляется миграцией.
- **`type` аккаунта** (Auth.js: oauth/oidc/email/webauthn) — у нас ровно один тип связки, парольный вход живёт в `users`, не в `oauth_accounts`.
- **unique(user_id, provider)** — «один аккаунт провайдера на пользователя» — продуктовое решение будущей ручной линковки; фиксировать его constraint'ом до проектирования линковки преждевременно, в v1 недостижимо (линковки нет).

## Ревью по skill postgresql — замечания и как учтены

1. **PK: skill предпочитает `BIGINT IDENTITY`, UUID — для opacity/федерации.** Оставлен UUID (app-side `uuid.uuid4`) — единообразие со *всеми* таблицами проекта; ломать паттерн ради одной таблицы хуже. Таблица маленькая, insert-нагрузки нет — минусов v4-UUID не почувствуем.
2. **Типы**: `TEXT` вместо varchar, `timestamptz` вместо timestamp, `server_default=func.now()` — по skill и db.md, замечаний нет.
3. **FK-индекс**: Postgres не индексирует referencing-колонки — `user_id` получает явный `index=True` (фактический путь доступа: «аккаунты пользователя», каскад при удалении user).
4. **Композитный unique**: обе колонки NOT NULL → нюанс «UNIQUE + NULLs» не применяется. Порядок `(provider, provider_account_id)`: login-запрос — equality по обеим, порядок безразличен; provider первым даёт prefix-scan «все аккаунты провайдера» для админ/миграционных нужд. Индекс от constraint обслуживает и login-lookup — отдельный не нужен.
5. **CHECK и NULL** (three-valued logic — NULL проходит CHECK): `provider` NOT NULL через `Mapped[str]`, дыры нет.
6. **Email не индексируем**: индексы по фактическим путям доступа; поиска по email в v1 нет. Когда появится линковка — expression-индекс `LOWER(email)` отдельной миграцией.
7. **Upsert-friendly**: unique constraint — точная цель для `ON CONFLICT (provider, provider_account_id)`, если login-flow захочет атомарный upsert «создать или освежить email».
8. **Naming**: имена constraints генерятся naming convention из `base.py` (`uq_oauth_accounts_provider`, `ix_oauth_accounts_user_id`, `pk_oauth_accounts`, `fk_oauth_accounts_user_id_users`); руками задано только имя CHECK (`provider_allowed` → `ck_oauth_accounts_provider_allowed`). Имена таблиц/колонок — snake_case, без кавычек.

## Открытый вопрос архитектору (вне схемы)

Где живёт OAuth `state`/PKCE между redirect'ами — БД-таблица не нужна, если класть в короткоживущую httpOnly-cookie или подписанный state; предложение — не заводить таблицу и решить это в design-brief самого flow.

## Источники

authjs.dev/concepts/database-models; django-allauth models.py + docs.allauth.org (configuration); better-auth.com/docs/concepts/database; omniauth wiki «Managing Multiple Providers».
