"""add security_blocked to thread_views

Revision ID: a1e5c2d07f2b
Revises: 2902408bdfd5
Create Date: 2026-04-21 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1e5c2d07f2b"
down_revision: Union[str, Sequence[str], None] = "2902408bdfd5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "thread_views",
        sa.Column(
            "security_blocked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("thread_views", "security_blocked")
