"""Add game_time_config table and RBAC permissions for gametime module

Revision ID: 004_game_time_config
Revises: 003_areas_zones_marker
Create Date: 2026-03-19

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '004_game_time_config'
down_revision = '003_areas_zones_marker'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # 1. Create game_time_config table
    if 'game_time_config' not in existing_tables:
        op.create_table(
            'game_time_config',
            sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column('epoch', sa.TIMESTAMP(), nullable=False, server_default="2026-03-19 00:00:00"),
            sa.Column('offset_days', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('updated_at', sa.TIMESTAMP(), nullable=False,
                       server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
            sa.PrimaryKeyConstraint('id'),
        )

    # 2. Insert default row
    op.execute(
        "INSERT INTO game_time_config (epoch, offset_days) "
        "VALUES ('2026-03-19 00:00:00', 0)"
    )

    # 3. Insert RBAC permissions
    op.execute(
        "INSERT INTO permissions (module, action, description) VALUES "
        "('gametime', 'read', 'View game time admin page'), "
        "('gametime', 'update', 'Modify game time settings')"
    )

    # 4. Assign permissions to admin role
    op.execute(
        "INSERT INTO role_permissions (role_id, permission_id) "
        "SELECT r.id, p.id FROM roles r "
        "CROSS JOIN permissions p "
        "WHERE r.name = 'admin' AND p.module = 'gametime' "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM role_permissions rp "
        "  WHERE rp.role_id = r.id AND rp.permission_id = p.id"
        ")"
    )


def downgrade() -> None:
    # 1. Remove role_permissions for gametime permissions
    op.execute(
        "DELETE rp FROM role_permissions rp "
        "INNER JOIN permissions p ON rp.permission_id = p.id "
        "WHERE p.module = 'gametime'"
    )

    # 2. Remove permissions
    op.execute("DELETE FROM permissions WHERE module = 'gametime'")

    # 3. Drop game_time_config table
    op.drop_table('game_time_config')
