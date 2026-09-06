"""Origin -> recommended starting points link table (FEAT-155)."""
from alembic import op
import sqlalchemy as sa

revision = '034_origin_start_pts'
down_revision = '033_start_pts_origins'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'origin_starting_points',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('origin_id', sa.BigInteger(), nullable=False),
        sa.Column('location_id', sa.BigInteger(), nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'origin_id', 'location_id', name='uq_origin_starting_point'
        ),
        sa.ForeignKeyConstraint(
            ['origin_id'], ['origin_countries.id'],
            name='fk_origin_starting_points_origin', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['location_id'], ['Locations.id'],
            name='fk_origin_starting_points_location', ondelete='CASCADE',
        ),
        mysql_engine='InnoDB',
    )
    op.create_index(
        'ix_origin_starting_points_origin', 'origin_starting_points',
        ['origin_id', 'sort_order'],
    )
    op.create_index(
        'ix_origin_starting_points_location', 'origin_starting_points',
        ['location_id'],
    )


def downgrade():
    # No explicit drop_index here: InnoDB refuses to drop an index a foreign key
    # still depends on (error 1553), and both indexes back one of the two FKs.
    # Dropping the table removes its indexes and constraints together.
    op.drop_table('origin_starting_points')
