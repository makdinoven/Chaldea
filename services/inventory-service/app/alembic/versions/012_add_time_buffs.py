"""Add time buffs system: active_buffs table, buff fields on items.

Revision ID: 012_add_time_buffs
Revises: 011_add_identification_system
Create Date: 2026-03-26

"""
from alembic import op
import sqlalchemy as sa

revision = '012_add_time_buffs'
down_revision = '011_add_identification_system'
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    """Check if a column exists in a table (MySQL)."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table AND COLUMN_NAME = :column"
    ), {"table": table, "column": column})
    return result.scalar() > 0


def _table_exists(table: str) -> bool:
    """Check if a table exists (MySQL)."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table"
    ), {"table": table})
    return result.scalar() > 0


def upgrade() -> None:
    # 1. Create active_buffs table
    if not _table_exists('active_buffs'):
        op.create_table(
            'active_buffs',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('character_id', sa.Integer(), nullable=False),
            sa.Column('buff_type', sa.String(50), nullable=False),
            sa.Column('value', sa.Float(), nullable=False),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('source_item_name', sa.String(200), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('character_id', 'buff_type', name='uq_character_buff_type'),
        )

    # 2. Add buff fields to items table
    if not _column_exists('items', 'buff_type'):
        op.add_column('items', sa.Column('buff_type', sa.String(50), nullable=True))

    if not _column_exists('items', 'buff_value'):
        op.add_column('items', sa.Column('buff_value', sa.Float(), nullable=True))

    if not _column_exists('items', 'buff_duration_minutes'):
        op.add_column('items', sa.Column('buff_duration_minutes', sa.Integer(), nullable=True))


def downgrade() -> None:
    # Remove buff fields from items
    if _column_exists('items', 'buff_duration_minutes'):
        op.drop_column('items', 'buff_duration_minutes')

    if _column_exists('items', 'buff_value'):
        op.drop_column('items', 'buff_value')

    if _column_exists('items', 'buff_type'):
        op.drop_column('items', 'buff_type')

    # Drop active_buffs table
    if _table_exists('active_buffs'):
        op.drop_table('active_buffs')
