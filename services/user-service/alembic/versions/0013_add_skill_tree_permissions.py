"""Add skill_trees RBAC permissions (read, create, update, delete)

Revision ID: 0013
Revises: 0012
Create Date: 2026-03-20

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0013'
down_revision = '0012'
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
        {'id': 34, 'module': 'skill_trees', 'action': 'read', 'description': 'Просмотр деревьев навыков классов'},
        {'id': 35, 'module': 'skill_trees', 'action': 'create', 'description': 'Создание деревьев навыков классов'},
        {'id': 36, 'module': 'skill_trees', 'action': 'update', 'description': 'Редактирование деревьев навыков классов'},
        {'id': 37, 'module': 'skill_trees', 'action': 'delete', 'description': 'Удаление деревьев навыков классов'},
    ])

    role_permissions_table = sa.table(
        'role_permissions',
        sa.column('role_id', sa.Integer),
        sa.column('permission_id', sa.Integer),
    )
    op.bulk_insert(role_permissions_table, [
        # Admin (role_id=4) gets all 4 permissions
        {'role_id': 4, 'permission_id': 34},
        {'role_id': 4, 'permission_id': 35},
        {'role_id': 4, 'permission_id': 36},
        {'role_id': 4, 'permission_id': 37},
        # Moderator (role_id=3) gets all 4 permissions
        {'role_id': 3, 'permission_id': 34},
        {'role_id': 3, 'permission_id': 35},
        {'role_id': 3, 'permission_id': 36},
        {'role_id': 3, 'permission_id': 37},
        # Editor (role_id=2) gets read only
        {'role_id': 2, 'permission_id': 34},
    ])


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission_id IN (34, 35, 36, 37)")
    op.execute("DELETE FROM permissions WHERE id IN (34, 35, 36, 37)")
