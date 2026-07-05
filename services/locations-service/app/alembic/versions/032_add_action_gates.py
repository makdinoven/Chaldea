"""Post intent (post_type) + action_gates for RP-gated actions (FEAT-145)."""
from alembic import op
import sqlalchemy as sa

revision = '032_add_action_gates'
down_revision = '031_add_gathering_nodes'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'posts',
        sa.Column('post_type', sa.String(length=20), server_default='regular', nullable=False),
    )
    op.create_table(
        'action_gates',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('character_id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.BigInteger(), nullable=False),
        sa.Column('post_id', sa.Integer(), nullable=True),
        sa.Column('action_type', sa.String(length=20), nullable=False),
        sa.Column('target_ref', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=12), server_default='open', nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Column('consumed_at', sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(['location_id'], ['Locations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['post_id'], ['posts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'idx_action_gates_lookup', 'action_gates',
        ['character_id', 'location_id', 'action_type', 'status'],
    )


def downgrade():
    op.drop_index('idx_action_gates_lookup', table_name='action_gates')
    op.drop_table('action_gates')
    op.drop_column('posts', 'post_type')
