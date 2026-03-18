"""Add RBAC tables (roles, permissions, role_permissions, user_permissions)

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-18

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Create roles table ---
    op.create_table(
        'roles',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('description', sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_roles_name'),
    )
    op.create_index('ix_roles_id', 'roles', ['id'])

    # --- Create permissions table ---
    op.create_table(
        'permissions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('module', sa.String(50), nullable=False),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('description', sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('module', 'action', name='uq_permission_module_action'),
    )
    op.create_index('ix_permissions_id', 'permissions', ['id'])

    # --- Create role_permissions table ---
    op.create_table(
        'role_permissions',
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.Column('permission_id', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('role_id', 'permission_id'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE'),
    )

    # --- Create user_permissions table ---
    op.create_table(
        'user_permissions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('permission_id', sa.Integer(), nullable=False),
        sa.Column('granted', sa.Boolean(), nullable=False, server_default='1'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'permission_id', name='uq_user_permission'),
    )
    op.create_index('ix_user_permissions_id', 'user_permissions', ['id'])

    # --- Add role_id and role_display_name columns to users ---
    op.add_column('users', sa.Column('role_id', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('role_display_name', sa.String(100), nullable=True))

    # --- Seed roles ---
    roles_table = sa.table(
        'roles',
        sa.column('id', sa.Integer),
        sa.column('name', sa.String),
        sa.column('level', sa.Integer),
        sa.column('description', sa.String),
    )
    op.bulk_insert(roles_table, [
        {'id': 1, 'name': 'user', 'level': 0, 'description': 'Regular user'},
        {'id': 2, 'name': 'editor', 'level': 20, 'description': 'Editor — read access to admin panels'},
        {'id': 3, 'name': 'moderator', 'level': 50, 'description': 'Moderator — content management'},
        {'id': 4, 'name': 'admin', 'level': 100, 'description': 'Administrator — full access'},
    ])

    # --- Seed permissions ---
    permissions_table = sa.table(
        'permissions',
        sa.column('id', sa.Integer),
        sa.column('module', sa.String),
        sa.column('action', sa.String),
        sa.column('description', sa.String),
    )
    op.bulk_insert(permissions_table, [
        {'id': 1, 'module': 'users', 'action': 'read', 'description': 'View user list and details'},
        {'id': 2, 'module': 'users', 'action': 'update', 'description': 'Edit user profiles'},
        {'id': 3, 'module': 'users', 'action': 'delete', 'description': 'Delete users'},
        {'id': 4, 'module': 'users', 'action': 'manage', 'description': 'Manage user roles and permissions'},
        {'id': 5, 'module': 'items', 'action': 'create', 'description': 'Create new items'},
        {'id': 6, 'module': 'items', 'action': 'read', 'description': 'View items'},
        {'id': 7, 'module': 'items', 'action': 'update', 'description': 'Edit items'},
        {'id': 8, 'module': 'items', 'action': 'delete', 'description': 'Delete items'},
    ])

    # --- Seed role_permissions ---
    role_permissions_table = sa.table(
        'role_permissions',
        sa.column('role_id', sa.Integer),
        sa.column('permission_id', sa.Integer),
    )
    # Admin (role_id=4) gets ALL permissions (1-8)
    admin_perms = [{'role_id': 4, 'permission_id': pid} for pid in range(1, 9)]
    # Moderator (role_id=3) gets items:* (5-8)
    moderator_perms = [{'role_id': 3, 'permission_id': pid} for pid in range(5, 9)]
    # Editor (role_id=2) gets *:read (1=users:read, 6=items:read)
    editor_perms = [
        {'role_id': 2, 'permission_id': 1},
        {'role_id': 2, 'permission_id': 6},
    ]
    op.bulk_insert(role_permissions_table, admin_perms + moderator_perms + editor_perms)

    # --- Data migration: map existing users.role to role_id ---
    # admin -> role_id=4, all others -> role_id=1
    op.execute("UPDATE users SET role_id = 4 WHERE role = 'admin'")
    op.execute("UPDATE users SET role_id = 1 WHERE role != 'admin' OR role IS NULL")

    # --- Add FK constraint for role_id ---
    op.create_foreign_key(
        'fk_users_role_id',
        'users', 'roles',
        ['role_id'], ['id'],
    )


def downgrade() -> None:
    # Drop FK constraint
    op.drop_constraint('fk_users_role_id', 'users', type_='foreignkey')

    # Drop columns from users
    op.drop_column('users', 'role_display_name')
    op.drop_column('users', 'role_id')

    # Drop tables in reverse order
    op.drop_table('user_permissions')
    op.drop_table('role_permissions')
    op.drop_table('permissions')
    op.drop_table('roles')
