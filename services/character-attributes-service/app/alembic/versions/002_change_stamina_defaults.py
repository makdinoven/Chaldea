"""Change default stamina from 50 to 100

Revision ID: 002_change_stamina_defaults
Revises: 001_initial_baseline
Create Date: 2026-03-19

"""
from alembic import op
import sqlalchemy as sa

revision = '002_change_stamina_defaults'
down_revision = '001_initial_baseline'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'character_attributes',
        'max_stamina',
        server_default='100',
        existing_type=sa.Integer(),
        existing_nullable=True,
    )
    op.alter_column(
        'character_attributes',
        'current_stamina',
        server_default='100',
        existing_type=sa.Integer(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'character_attributes',
        'max_stamina',
        server_default='50',
        existing_type=sa.Integer(),
        existing_nullable=True,
    )
    op.alter_column(
        'character_attributes',
        'current_stamina',
        server_default='50',
        existing_type=sa.Integer(),
        existing_nullable=True,
    )
