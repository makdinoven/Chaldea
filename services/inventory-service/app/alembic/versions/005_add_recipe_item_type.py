"""Add 'recipe' to items.item_type ENUM.

Revision ID: 005_add_recipe_item_type
Revises: 004_add_professions_crafting
Create Date: 2026-03-26

"""
from alembic import op

revision = '005_add_recipe_item_type'
down_revision = '004_add_professions_crafting'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE items MODIFY COLUMN item_type "
        "ENUM('head','body','cloak','belt','ring','necklace','bracelet',"
        "'main_weapon','consumable','additional_weapons','resource','scroll','misc','shield',"
        "'blueprint','recipe') "
        "NOT NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE items MODIFY COLUMN item_type "
        "ENUM('head','body','cloak','belt','ring','necklace','bracelet',"
        "'main_weapon','consumable','additional_weapons','resource','scroll','misc','shield',"
        "'blueprint') "
        "NOT NULL"
    )
