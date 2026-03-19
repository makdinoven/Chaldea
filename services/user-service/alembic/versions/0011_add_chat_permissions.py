"""Add chat:delete and chat:ban permissions for chat moderation

Revision ID: 0011
Revises: 0010
Create Date: 2026-03-19

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    permissions_table = sa.table(
        'permissions',
        sa.column('id', sa.Integer),
        sa.column('module', sa.String),
        sa.column('action', sa.String),
        sa.column('description', sa.String),
    )
    op.bulk_insert(permissions_table, [
        {'id': 32, 'module': 'chat', 'action': 'delete', 'description': 'Удаление сообщений в чате'},
        {'id': 33, 'module': 'chat', 'action': 'ban', 'description': 'Бан/разбан пользователей в чате'},
    ])

    role_permissions_table = sa.table(
        'role_permissions',
        sa.column('role_id', sa.Integer),
        sa.column('permission_id', sa.Integer),
    )
    op.bulk_insert(role_permissions_table, [
        {'role_id': 4, 'permission_id': 32},  # Admin
        {'role_id': 4, 'permission_id': 33},  # Admin
        {'role_id': 3, 'permission_id': 32},  # Moderator
        {'role_id': 3, 'permission_id': 33},  # Moderator
    ])


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission_id IN (32, 33)")
    op.execute("DELETE FROM permissions WHERE id IN (32, 33)")
