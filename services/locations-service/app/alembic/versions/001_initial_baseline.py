"""Initial baseline — existing tables in locations-service

Revision ID: 001_initial
Revises:
Create Date: 2026-03-17

This is a baseline migration reflecting the current state of all existing
tables managed by locations-service. It should NOT be run against an existing
database — use `alembic stamp head` to mark it as applied.

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # Countries
    if 'Countries' not in existing_tables:
        op.create_table(
            'Countries',
            sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('leader_id', sa.BigInteger(), nullable=True),
            sa.Column('map_image_url', sa.String(255), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )

    # Regions (entrance_location_id FK added later to avoid circular dependency)
    if 'Regions' not in existing_tables:
        op.create_table(
            'Regions',
            sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('country_id', sa.BigInteger(), nullable=False),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('map_image_url', sa.String(255), nullable=True),
            sa.Column('image_url', sa.String(255), nullable=True),
            sa.Column('entrance_location_id', sa.BigInteger(), nullable=True),
            sa.Column('leader_id', sa.BigInteger(), nullable=True),
            sa.Column('x', sa.Float(), nullable=True),
            sa.Column('y', sa.Float(), nullable=True),
            sa.ForeignKeyConstraint(['country_id'], ['Countries.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )

    # Districts (entrance_location_id FK added later to avoid circular dependency)
    if 'Districts' not in existing_tables:
        op.create_table(
            'Districts',
            sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('region_id', sa.BigInteger(), nullable=False),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('image_url', sa.String(255), nullable=True),
            sa.Column('entrance_location_id', sa.BigInteger(), nullable=True),
            sa.Column('recommended_level', sa.Integer(), nullable=True),
            sa.Column('x', sa.Float(), nullable=True),
            sa.Column('y', sa.Float(), nullable=True),
            sa.ForeignKeyConstraint(['region_id'], ['Regions.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )

    # Locations
    if 'Locations' not in existing_tables:
        op.create_table(
            'Locations',
            sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('district_id', sa.BigInteger(), nullable=False),
            sa.Column('type', sa.Enum('location', 'subdistrict', name='location_type'), nullable=False),
            sa.Column('image_url', sa.String(255), nullable=True),
            sa.Column('recommended_level', sa.Integer(), nullable=False),
            sa.Column('quick_travel_marker', sa.Boolean(), nullable=False),
            sa.Column('parent_id', sa.BigInteger(), nullable=True),
            sa.Column('description', sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(['district_id'], ['Districts.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['parent_id'], ['Locations.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )

    # LocationNeighbors
    if 'LocationNeighbors' not in existing_tables:
        op.create_table(
            'LocationNeighbors',
            sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column('location_id', sa.BigInteger(), nullable=False),
            sa.Column('neighbor_id', sa.BigInteger(), nullable=False),
            sa.Column('energy_cost', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['location_id'], ['Locations.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['neighbor_id'], ['Locations.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )

    # posts
    if 'posts' not in existing_tables:
        op.create_table(
            'posts',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('character_id', sa.Integer(), nullable=False),
            sa.Column('location_id', sa.BigInteger(), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.ForeignKeyConstraint(['location_id'], ['Locations.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_posts_id'), 'posts', ['id'], unique=False)

    # Deferred FKs (circular dependency: Regions/Districts → Locations)
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Add Regions.entrance_location_id → Locations.id
    existing_fks = [fk['name'] for fk in inspector.get_foreign_keys('Regions')]
    if 'fk_regions_entrance_location' not in existing_fks:
        op.create_foreign_key(
            'fk_regions_entrance_location',
            'Regions', 'Locations',
            ['entrance_location_id'], ['id'],
            ondelete='SET NULL',
        )

    # Add Districts.entrance_location_id → Locations.id
    existing_fks = [fk['name'] for fk in inspector.get_foreign_keys('Districts')]
    if 'fk_districts_entrance_location' not in existing_fks:
        op.create_foreign_key(
            'fk_districts_entrance_location',
            'Districts', 'Locations',
            ['entrance_location_id'], ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    op.drop_constraint('fk_districts_entrance_location', 'Districts', type_='foreignkey')
    op.drop_constraint('fk_regions_entrance_location', 'Regions', type_='foreignkey')
    op.drop_index(op.f('ix_posts_id'), table_name='posts')
    op.drop_table('posts')
    op.drop_table('LocationNeighbors')
    op.drop_table('Locations')
    op.drop_table('Districts')
    op.drop_table('Regions')
    op.drop_table('Countries')
