"""Add cosmetic_slug column to bp_rewards

Revision ID: 0002_cosmetic_slug
Revises: 0001_initial
Create Date: 2026-03-29

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_cosmetic_slug'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'bp_rewards',
        sa.Column('cosmetic_slug', sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('bp_rewards', 'cosmetic_slug')
