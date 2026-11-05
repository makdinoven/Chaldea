"""Add character_attributes.stealth (FEAT-201)

Stealth is the 11th primary stat. Like charisma it is stored as a TOTAL
(points + gear + perks + food) and has no stored derived field: it only lowers
the chance a crime is witnessed (computed in character-service).

Existing rows get 0. Plain ADD COLUMN, instant in MySQL 8. Idempotent.

Revision ID: 009_add_stealth
Revises: 008_add_regen_and_satiety
Create Date: 2026-11-04

"""
from alembic import op
import sqlalchemy as sa

revision = '009_add_stealth'
down_revision = '008_add_regen_and_satiety'
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column in {c['name'] for c in inspector.get_columns(table)}


def upgrade() -> None:
    if not _has_column('character_attributes', 'stealth'):
        op.add_column(
            'character_attributes',
            sa.Column('stealth', sa.Integer(), nullable=False, server_default='0'),
        )


def downgrade() -> None:
    if _has_column('character_attributes', 'stealth'):
        op.drop_column('character_attributes', 'stealth')
