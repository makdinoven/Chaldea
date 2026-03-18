"""Add battles:manage permission for autobattle-service admin endpoints

Revision ID: 0008
Revises: 0007
Create Date: 2026-03-18

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0008'
down_revision = '0007'
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
        {'id': 28, 'module': 'battles', 'action': 'manage', 'description': 'Управление автобоем (режим, регистрация участников)'},
    ])

    role_permissions_table = sa.table(
        'role_permissions',
        sa.column('role_id', sa.Integer),
        sa.column('permission_id', sa.Integer),
    )
    op.bulk_insert(role_permissions_table, [
        {'role_id': 4, 'permission_id': 28},  # Admin
        {'role_id': 3, 'permission_id': 28},  # Moderator
    ])


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission_id = 28")
    op.execute("DELETE FROM permissions WHERE id = 28")
