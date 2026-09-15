"""Add equipment_rules: which armor classes and weapon kinds a class/subclass may wear.

One row per scope: "class:<id>" (character without a chosen subclass) or a
subclass key. No row = no restrictions, so the game behaves as before until an
admin configures rules. See equipment_rules.py for the semantics.

Revision ID: 020_add_equipment_rules
Revises: 019_rework_item_weapon_types
Create Date: 2026-09-15

"""
from alembic import op
import sqlalchemy as sa

revision = '020_add_equipment_rules'
down_revision = '019_rework_item_weapon_types'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'equipment_rules',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('scope_key', sa.String(60), nullable=False),
        sa.Column('class_id', sa.Integer(), nullable=False),
        sa.Column('subclass_key', sa.String(50), nullable=True),
        sa.Column('armor_classes', sa.Text(), nullable=False),
        sa.Column('main_hand', sa.Text(), nullable=False),
        sa.Column('off_hand', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('scope_key', name='uq_equipment_rules_scope_key'),
    )
    op.create_index('ix_equipment_rules_class_id', 'equipment_rules', ['class_id'])


def downgrade() -> None:
    op.drop_index('ix_equipment_rules_class_id', table_name='equipment_rules')
    op.drop_table('equipment_rules')
