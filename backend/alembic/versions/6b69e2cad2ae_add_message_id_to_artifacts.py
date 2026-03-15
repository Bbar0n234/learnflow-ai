"""add message_id to artifacts

Revision ID: 6b69e2cad2ae
Revises: 4512c02eeb05
Create Date: 2026-03-15 14:15:08.897256

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6b69e2cad2ae"
down_revision: Union[str, Sequence[str], None] = "4512c02eeb05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "artifacts", sa.Column("message_id", sa.String(length=100), nullable=True)
    )
    op.create_index(
        op.f("ix_artifacts_message_id"), "artifacts", ["message_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_artifacts_message_id"), table_name="artifacts")
    op.drop_column("artifacts", "message_id")
