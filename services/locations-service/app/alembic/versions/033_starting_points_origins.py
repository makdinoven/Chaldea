"""Starting locations flag/blurb + origin_countries registry (FEAT-154)."""
from alembic import op
import sqlalchemy as sa

revision = '033_start_pts_origins'
down_revision = '032_add_action_gates'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'Locations',
        sa.Column('is_starting', sa.Boolean(), server_default='0', nullable=False),
    )
    op.add_column('Locations', sa.Column('starting_blurb', sa.Text(), nullable=True))
    op.create_index('ix_locations_is_starting', 'Locations', ['is_starting'])

    op.create_table(
        'origin_countries',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('skitaltsy_attitude', sa.Text(), nullable=True),
        sa.Column('emblem_url', sa.String(length=255), nullable=True),
        sa.Column('map_image_url', sa.String(length=255), nullable=True),
        sa.Column('archive_slug', sa.String(length=255), nullable=True),
        sa.Column('country_id', sa.BigInteger(), nullable=True),
        sa.Column('is_playable', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_origin_countries_name'),
        sa.ForeignKeyConstraint(
            ['country_id'], ['Countries.id'],
            name='fk_origin_countries_country', ondelete='SET NULL',
        ),
    )
    op.create_index(
        'ix_origin_countries_active_sort', 'origin_countries',
        ['is_active', 'sort_order'],
    )


def downgrade():
    op.drop_index('ix_origin_countries_active_sort', table_name='origin_countries')
    op.drop_table('origin_countries')
    op.drop_index('ix_locations_is_starting', table_name='Locations')
    op.drop_column('Locations', 'starting_blurb')
    op.drop_column('Locations', 'is_starting')
