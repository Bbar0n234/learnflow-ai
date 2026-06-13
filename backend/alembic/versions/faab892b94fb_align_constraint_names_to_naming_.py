# Manual migration: переименование существующих constraints под naming convention —
# ALTER ... RENAME CONSTRAINT не покрывается autogenerate.
"""align constraint names to naming convention

Revision ID: faab892b94fb
Revises: add_is_admin_to_users
Create Date: 2026-06-12 21:49:32.549368

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "faab892b94fb"
down_revision: Union[str, Sequence[str], None] = "add_is_admin_to_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, [возможные старые имена], new_name).
# Renames условные: на свежей БД naming convention из target_metadata действует
# уже в ранних миграциях (op.create_table декорирует имена), поэтому старых имён
# там нет — constraints сразу создаются с целевыми именами и rename пропускается.
# Rename PK/UNIQUE переименовывает и их индексы.
_CONSTRAINT_RENAMES = [
    # primary keys
    ("artifacts", ["artifacts_pkey"], "pk_artifacts"),
    ("mcp_server_disables", ["mcp_server_disables_pkey"], "pk_mcp_server_disables"),
    ("project_mcp_servers", ["project_mcp_servers_pkey"], "pk_project_mcp_servers"),
    ("project_settings", ["project_settings_pkey"], "pk_project_settings"),
    ("projects", ["projects_pkey"], "pk_projects"),
    ("refresh_tokens", ["refresh_tokens_pkey"], "pk_refresh_tokens"),
    ("thread_mcp_servers", ["thread_mcp_servers_pkey"], "pk_thread_mcp_servers"),
    ("thread_settings", ["thread_settings_pkey"], "pk_thread_settings"),
    ("thread_views", ["thread_views_pkey"], "pk_thread_views"),
    ("user_mcp_servers", ["user_mcp_servers_pkey"], "pk_user_mcp_servers"),
    ("user_settings", ["user_settings_pkey"], "pk_user_settings"),
    ("users", ["users_pkey"], "pk_users"),
    # foreign keys
    ("artifacts", ["artifacts_project_id_fkey"], "fk_artifacts_project_id_projects"),
    ("artifacts", ["artifacts_thread_id_fkey"], "fk_artifacts_thread_id_thread_views"),
    (
        "project_mcp_servers",
        ["project_mcp_servers_project_id_fkey"],
        "fk_project_mcp_servers_project_id_projects",
    ),
    (
        "project_settings",
        ["project_settings_project_id_fkey"],
        "fk_project_settings_project_id_projects",
    ),
    ("projects", ["projects_user_id_fkey"], "fk_projects_user_id_users"),
    ("refresh_tokens", ["refresh_tokens_user_id_fkey"], "fk_refresh_tokens_user_id_users"),
    (
        "thread_mcp_servers",
        ["thread_mcp_servers_thread_id_fkey"],
        "fk_thread_mcp_servers_thread_id_thread_views",
    ),
    (
        "thread_settings",
        ["thread_settings_thread_id_fkey"],
        "fk_thread_settings_thread_id_thread_views",
    ),
    (
        "thread_views",
        ["thread_views_project_id_fkey"],
        "fk_thread_views_project_id_projects",
    ),
    (
        "user_mcp_servers",
        ["user_mcp_servers_user_id_fkey"],
        "fk_user_mcp_servers_user_id_users",
    ),
    ("user_settings", ["user_settings_user_id_fkey"], "fk_user_settings_user_id_users"),
    # unique constraints
    (
        "project_mcp_servers",
        ["project_mcp_servers_project_id_name_key"],
        "uq_project_mcp_servers_project_id",
    ),
    (
        "thread_mcp_servers",
        ["thread_mcp_servers_thread_id_name_key"],
        "uq_thread_mcp_servers_thread_id",
    ),
    (
        "user_mcp_servers",
        ["user_mcp_servers_user_id_name_key"],
        "uq_user_mcp_servers_user_id",
    ),
    ("users", ["users_name_key"], "uq_users_name"),
    # check constraints: второй вариант — имя, которое convention даёт явному
    # `name="ck_scope_type"` из миграции 2902408bdfd5 на свежей БД.
    (
        "mcp_server_disables",
        ["ck_scope_type", "ck_mcp_server_disables_ck_scope_type"],
        "ck_mcp_server_disables_scope_type",
    ),
]


def _constraint_exists(table: str, name: str) -> bool:
    return bool(
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM pg_constraint"
                " WHERE conname = :name AND conrelid = CAST(:table AS regclass)"
            ),
            {"name": name, "table": table},
        )
        .scalar()
    )


def upgrade() -> None:
    """Upgrade schema."""
    for table, old_names, new in _CONSTRAINT_RENAMES:
        for old in old_names:
            if _constraint_exists(table, old):
                op.execute(f'ALTER TABLE {table} RENAME CONSTRAINT "{old}" TO "{new}"')
                break


def downgrade() -> None:
    """Downgrade schema."""
    for table, old_names, new in reversed(_CONSTRAINT_RENAMES):
        if _constraint_exists(table, new):
            op.execute(f'ALTER TABLE {table} RENAME CONSTRAINT "{new}" TO "{old_names[0]}"')
