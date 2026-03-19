"""Add races module permissions (create, update, delete)

Revision ID: 0009
Revises: 0008
Create Date: 2026-03-19

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0009'
down_revision = '0008'
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
        {'id': 29, 'module': 'races', 'action': 'create', 'description': 'Создание рас и подрас'},
        {'id': 30, 'module': 'races', 'action': 'update', 'description': 'Редактирование рас и подрас'},
        {'id': 31, 'module': 'races', 'action': 'delete', 'description': 'Удаление рас и подрас'},
    ])

    role_permissions_table = sa.table(
        'role_permissions',
        sa.column('role_id', sa.Integer),
        sa.column('permission_id', sa.Integer),
    )
    op.bulk_insert(role_permissions_table, [
        {'role_id': 4, 'permission_id': 29},  # Admin
        {'role_id': 4, 'permission_id': 30},  # Admin
        {'role_id': 4, 'permission_id': 31},  # Admin
        {'role_id': 3, 'permission_id': 29},  # Moderator
        {'role_id': 3, 'permission_id': 30},  # Moderator
        {'role_id': 3, 'permission_id': 31},  # Moderator
    ])


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission_id IN (29, 30, 31)")
    op.execute("DELETE FROM permissions WHERE id IN (29, 30, 31)")
