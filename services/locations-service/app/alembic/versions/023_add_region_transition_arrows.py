"""Add region_transition_arrows and arrow_neighbors tables

Revision ID: 023_add_region_transition_arrows
Revises: 022_add_index_posts_character_id
Create Date: 2026-03-28

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '023_add_region_transition_arrows'
down_revision = '022_add_index_posts_character_id'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    existing_tables = insp.get_table_names()

    if 'region_transition_arrows' not in existing_tables:
        op.create_table(
            'region_transition_arrows',
            sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column('region_id', sa.BigInteger(), nullable=False),
            sa.Column('target_region_id', sa.BigInteger(), nullable=False),
            sa.Column('paired_arrow_id', sa.BigInteger(), nullable=True),
            sa.Column('x', sa.Float(), nullable=True),
            sa.Column('y', sa.Float(), nullable=True),
            sa.Column('label', sa.String(255), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['region_id'], ['Regions.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['target_region_id'], ['Regions.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['paired_arrow_id'], ['region_transition_arrows.id'], ondelete='SET NULL'),
        )
        op.create_index('idx_rta_region', 'region_transition_arrows', ['region_id'])
        op.create_index('idx_rta_target_region', 'region_transition_arrows', ['target_region_id'])

    if 'arrow_neighbors' not in existing_tables:
        op.create_table(
            'arrow_neighbors',
            sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column('location_id', sa.BigInteger(), nullable=False),
            sa.Column('arrow_id', sa.BigInteger(), nullable=False),
            sa.Column('energy_cost', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('path_data', sa.JSON(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['location_id'], ['Locations.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['arrow_id'], ['region_transition_arrows.id'], ondelete='CASCADE'),
        )
        op.create_index('idx_an_location', 'arrow_neighbors', ['location_id'])
        op.create_index('idx_an_arrow', 'arrow_neighbors', ['arrow_id'])


def downgrade() -> None:
    op.drop_table('arrow_neighbors')
    op.drop_table('region_transition_arrows')
