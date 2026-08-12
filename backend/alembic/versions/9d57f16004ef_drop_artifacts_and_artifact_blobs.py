"""drop artifacts and artifact_blobs

Revision ID: 9d57f16004ef
Revises: 05b404b12f90
Create Date: 2026-08-11 23:43:38.647731

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9d57f16004ef'
down_revision: Union[str, Sequence[str], None] = '05b404b12f90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Manual reorder: autogenerate emitted `drop_table('artifacts')` before
    # `drop_table('artifact_blobs')`, which fails — `artifact_blobs.artifact_id`
    # FK's the `artifacts` table. Drop the dependent table first.
    op.drop_index(op.f('ix_artifact_blobs_artifact_id'), table_name='artifact_blobs')
    op.drop_table('artifact_blobs')
    op.drop_index(op.f('ix_artifacts_message_id'), table_name='artifacts')
    op.drop_index(op.f('ix_artifacts_project_id'), table_name='artifacts')
    op.drop_index(op.f('ix_artifacts_thread_id'), table_name='artifacts')
    op.drop_table('artifacts')


def downgrade() -> None:
    """Downgrade schema."""
    # Manual reorder (mirrors `upgrade`): `artifacts` must exist before
    # `artifact_blobs` can be created — its FK references `artifacts.id`.
    op.create_table('artifacts',
    sa.Column('id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('project_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('thread_id', sa.UUID(), autoincrement=False, nullable=True),
    sa.Column('title', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('type', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('content', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('message_id', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_artifacts_project_id_projects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['thread_id'], ['thread_views.thread_id'], name=op.f('fk_artifacts_thread_id_thread_views'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_artifacts'))
    )
    op.create_index(op.f('ix_artifacts_thread_id'), 'artifacts', ['thread_id'], unique=False)
    op.create_index(op.f('ix_artifacts_project_id'), 'artifacts', ['project_id'], unique=False)
    op.create_index(op.f('ix_artifacts_message_id'), 'artifacts', ['message_id'], unique=False)
    op.create_table('artifact_blobs',
    sa.Column('id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('artifact_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('mime_type', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('data', postgresql.BYTEA(), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['artifact_id'], ['artifacts.id'], name=op.f('fk_artifact_blobs_artifact_id_artifacts'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_artifact_blobs'))
    )
    op.create_index(op.f('ix_artifact_blobs_artifact_id'), 'artifact_blobs', ['artifact_id'], unique=True)
