"""Add starter_kits table

Revision ID: 001_add_starter_kits
Revises:
Create Date: 2026-03-13

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '001_add_starter_kits'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'starter_kits',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('class_id', sa.Integer(), sa.ForeignKey('classes.id_class'), unique=True, nullable=False),
        sa.Column('items', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('skills', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('currency_amount', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_table('starter_kits')
