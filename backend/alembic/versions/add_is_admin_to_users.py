"""add is_admin field to users table

Revision ID: add_is_admin_to_users
Revises: a1e5c2d07f2b
Create Date: 2026-05-04

"""

# TODO: Есть ощущение, что сейчас вот эта миграция сгенерирована руками, а не самостоятельно. И это на самом деле минус. Я вот, кажется, видел краем глаза, что агент иногда не генерирует не генерирует миграцию через автогенерацию, он генерирует её руками. Опять же, хотелось бы понимать, насколько это паттерн, антипаттерн, насколько это хорошо, плохо, какие у этого плюсы, минусы. Но вот знаю такую лазейку. Не знаю даже, есть ли у нас конвенция или нет по тому, что генерировать нужно непосредственно миграции автоматически. Но если даже эти конвенции есть, агент по идее берет, смотрит: ага, у нас база данных не запущена, всё, херня, сгенерируй руками. Я не знаю, насколько это правильное поведение, но вот согласно моему видению, это не решение проблемы. Нужно взять, поднять базу данных, накатить туда предыдущие миграции и сделать автогенерацию новой миграции, и никак иначе. И, соответственно, это хотелось бы зафиксировать, наверное, куда-нибудь. Но опять же, если я нигде не ошибаюсь. То есть надо разобраться, если так действительно всё есть, то зафиксировать.

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_is_admin_to_users"
down_revision: Union[str, Sequence[str], None] = "a1e5c2d07f2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column(
            "is_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Whether user is an admin",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "is_admin")
