"""Add 'rune' to items.item_type ENUM.

Revision ID: 013_add_rune_type
Revises: 012_add_time_buffs
Create Date: 2026-03-26

"""
from alembic import op
import sqlalchemy as sa

revision = '013_add_rune_type'
down_revision = '012_add_time_buffs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT COLUMN_TYPE FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'items' AND COLUMN_NAME = 'item_type'"
    ))
    col_type = result.scalar()
    if col_type and "'rune'" not in col_type:
        op.execute(
            "ALTER TABLE items MODIFY COLUMN item_type "
            "ENUM('head','body','cloak','belt','ring','necklace','bracelet',"
            "'main_weapon','consumable','additional_weapons','resource','scroll','misc','shield',"
            "'blueprint','recipe','gem','rune') "
            "NOT NULL"
        )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE items MODIFY COLUMN item_type "
        "ENUM('head','body','cloak','belt','ring','necklace','bracelet',"
        "'main_weapon','consumable','additional_weapons','resource','scroll','misc','shield',"
        "'blueprint','recipe','gem') "
        "NOT NULL"
    )
