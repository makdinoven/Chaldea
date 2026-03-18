"""Add remaining permissions for all modules (characters, skills, locations, rules, photos, notifications)

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-18

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Seed new permissions (IDs 9-27) ---
    permissions_table = sa.table(
        'permissions',
        sa.column('id', sa.Integer),
        sa.column('module', sa.String),
        sa.column('action', sa.String),
        sa.column('description', sa.String),
    )
    op.bulk_insert(permissions_table, [
        {'id': 9,  'module': 'characters', 'action': 'create', 'description': 'Создание персонажей и титулов'},
        {'id': 10, 'module': 'characters', 'action': 'read',   'description': 'Просмотр панели персонажей'},
        {'id': 11, 'module': 'characters', 'action': 'update', 'description': 'Редактирование персонажей, стартовых наборов'},
        {'id': 12, 'module': 'characters', 'action': 'delete', 'description': 'Удаление персонажей'},
        {'id': 13, 'module': 'characters', 'action': 'approve', 'description': 'Одобрение/отклонение заявок на персонажей'},
        {'id': 14, 'module': 'skills',     'action': 'create', 'description': 'Создание навыков, рангов, урона, эффектов'},
        {'id': 15, 'module': 'skills',     'action': 'read',   'description': 'Просмотр панели навыков'},
        {'id': 16, 'module': 'skills',     'action': 'update', 'description': 'Редактирование навыков и деревьев'},
        {'id': 17, 'module': 'skills',     'action': 'delete', 'description': 'Удаление навыков, рангов, урона, эффектов'},
        {'id': 18, 'module': 'locations',  'action': 'create', 'description': 'Создание стран, регионов, районов, локаций'},
        {'id': 19, 'module': 'locations',  'action': 'read',   'description': 'Просмотр панели локаций'},
        {'id': 20, 'module': 'locations',  'action': 'update', 'description': 'Редактирование локаций, соседей'},
        {'id': 21, 'module': 'locations',  'action': 'delete', 'description': 'Удаление локаций, соседей'},
        {'id': 22, 'module': 'rules',      'action': 'create', 'description': 'Создание правил'},
        {'id': 23, 'module': 'rules',      'action': 'read',   'description': 'Просмотр панели правил'},
        {'id': 24, 'module': 'rules',      'action': 'update', 'description': 'Редактирование и сортировка правил'},
        {'id': 25, 'module': 'rules',      'action': 'delete', 'description': 'Удаление правил'},
        {'id': 26, 'module': 'photos',     'action': 'upload', 'description': 'Загрузка изображений (карты, предметы, навыки)'},
        {'id': 27, 'module': 'notifications', 'action': 'create', 'description': 'Отправка уведомлений'},
    ])

    # --- Seed role_permissions for new permissions ---
    role_permissions_table = sa.table(
        'role_permissions',
        sa.column('role_id', sa.Integer),
        sa.column('permission_id', sa.Integer),
    )

    # Admin (role_id=4) gets ALL new permissions (9-27)
    admin_perms = [{'role_id': 4, 'permission_id': pid} for pid in range(9, 28)]

    # Moderator (role_id=3) gets ALL new permissions (9-27)
    moderator_perms = [{'role_id': 3, 'permission_id': pid} for pid in range(9, 28)]

    # Editor (role_id=2) gets only *:read permissions from new set
    editor_perms = [
        {'role_id': 2, 'permission_id': 10},  # characters:read
        {'role_id': 2, 'permission_id': 15},  # skills:read
        {'role_id': 2, 'permission_id': 19},  # locations:read
        {'role_id': 2, 'permission_id': 23},  # rules:read
    ]

    op.bulk_insert(role_permissions_table, admin_perms + moderator_perms + editor_perms)


def downgrade() -> None:
    # Remove role_permissions for new permissions first (FK constraint)
    op.execute("DELETE FROM role_permissions WHERE permission_id >= 9")
    # Remove the new permissions
    op.execute("DELETE FROM permissions WHERE id >= 9")
