"""Add Areas table, ClickableZones table, area_id/x/y to Countries, marker_type to Locations

Revision ID: 003_areas_zones_marker
Revises: 002_game_rules
Create Date: 2026-03-19

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003_areas_zones_marker'
down_revision = '002_game_rules'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # 1. Create Areas table
    if 'Areas' not in existing_tables:
        op.create_table(
            'Areas',
            sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('map_image_url', sa.String(255), nullable=True),
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
            sa.PrimaryKeyConstraint('id'),
        )

    # 2. Create ClickableZones table
    if 'ClickableZones' not in existing_tables:
        op.create_table(
            'ClickableZones',
            sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column('parent_type', sa.Enum('area', 'country', name='clickable_zone_parent_type'), nullable=False),
            sa.Column('parent_id', sa.BigInteger(), nullable=False),
            sa.Column('target_type', sa.Enum('country', 'region', name='clickable_zone_target_type'), nullable=False),
            sa.Column('target_id', sa.BigInteger(), nullable=False),
            sa.Column('zone_data', sa.JSON(), nullable=False),
            sa.Column('label', sa.String(255), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('idx_parent', 'ClickableZones', ['parent_type', 'parent_id'])

    # 3. Add area_id, x, y columns to Countries
    existing_columns = [col['name'] for col in inspector.get_columns('Countries')]

    if 'area_id' not in existing_columns:
        op.add_column('Countries', sa.Column('area_id', sa.BigInteger(), nullable=True))
        op.create_index('idx_countries_area', 'Countries', ['area_id'])
        op.create_foreign_key(
            'fk_countries_area',
            'Countries', 'Areas',
            ['area_id'], ['id'],
            ondelete='SET NULL',
        )

    if 'x' not in existing_columns:
        op.add_column('Countries', sa.Column('x', sa.Float(), nullable=True))

    if 'y' not in existing_columns:
        op.add_column('Countries', sa.Column('y', sa.Float(), nullable=True))

    # 4. Add marker_type column to Locations
    location_columns = [col['name'] for col in inspector.get_columns('Locations')]
    if 'marker_type' not in location_columns:
        op.add_column(
            'Locations',
            sa.Column(
                'marker_type',
                sa.Enum('safe', 'dangerous', 'dungeon', name='location_marker_type'),
                nullable=False,
                server_default='safe',
            ),
        )


def downgrade() -> None:
    # 4. Remove marker_type from Locations
    op.drop_column('Locations', 'marker_type')

    # 3. Remove area_id, x, y from Countries
    op.drop_constraint('fk_countries_area', 'Countries', type_='foreignkey')
    op.drop_index('idx_countries_area', table_name='Countries')
    op.drop_column('Countries', 'y')
    op.drop_column('Countries', 'x')
    op.drop_column('Countries', 'area_id')

    # 2. Drop ClickableZones table
    op.drop_index('idx_parent', table_name='ClickableZones')
    op.drop_table('ClickableZones')

    # 1. Drop Areas table
    op.drop_table('Areas')
