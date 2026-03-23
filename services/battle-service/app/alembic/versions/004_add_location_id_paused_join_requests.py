"""Add location_id, is_paused to battles and battle_join_requests table

Revision ID: 004_location_paused_join
Revises: 003_battle_history
Create Date: 2026-03-23

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '004_location_paused_join'
down_revision = '003_battle_history'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # -- Add columns to battles table --
    battles_columns = [c['name'] for c in inspector.get_columns('battles')]

    if 'location_id' not in battles_columns:
        op.add_column(
            'battles',
            sa.Column('location_id', sa.BigInteger(), nullable=True),
        )
        op.create_index('idx_battles_location_id', 'battles', ['location_id'])

    if 'is_paused' not in battles_columns:
        op.add_column(
            'battles',
            sa.Column(
                'is_paused',
                sa.Boolean(),
                nullable=False,
                server_default='0',
            ),
        )

    # -- Create battle_join_requests table --
    if 'battle_join_requests' not in existing_tables:
        op.create_table(
            'battle_join_requests',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('battle_id', sa.Integer(), nullable=False),
            sa.Column('character_id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('team', sa.Integer(), nullable=False),
            sa.Column(
                'status',
                sa.Enum('pending', 'approved', 'rejected',
                        name='joinrequeststatus'),
                nullable=False,
                server_default='pending',
            ),
            sa.Column(
                'created_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.text('CURRENT_TIMESTAMP'),
            ),
            sa.Column('reviewed_at', sa.DateTime(), nullable=True),
            sa.Column('reviewed_by', sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(
                ['battle_id'], ['battles.id'], name='fk_bjr_battle'
            ),
            sa.UniqueConstraint(
                'battle_id', 'character_id', name='uq_bjr_battle_character'
            ),
        )
        op.create_index(
            'idx_bjr_battle_id', 'battle_join_requests', ['battle_id']
        )
        op.create_index(
            'idx_bjr_character_id', 'battle_join_requests', ['character_id']
        )
        op.create_index(
            'idx_bjr_status', 'battle_join_requests', ['status']
        )


def downgrade() -> None:
    op.drop_index('idx_bjr_status', table_name='battle_join_requests')
    op.drop_index('idx_bjr_character_id', table_name='battle_join_requests')
    op.drop_index('idx_bjr_battle_id', table_name='battle_join_requests')
    op.drop_table('battle_join_requests')

    op.drop_column('battles', 'is_paused')
    op.drop_index('idx_battles_location_id', table_name='battles')
    op.drop_column('battles', 'location_id')
