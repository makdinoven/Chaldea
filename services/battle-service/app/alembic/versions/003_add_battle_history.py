"""Add battle_history table

Revision ID: 003_battle_history
Revises: 002_add_pvp
Create Date: 2026-03-23

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003_battle_history'
down_revision = '002_add_pvp'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'battle_history' not in existing_tables:
        op.create_table(
            'battle_history',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('battle_id', sa.Integer(), nullable=False),
            sa.Column('character_id', sa.Integer(), nullable=False),
            sa.Column('character_name', sa.String(100), nullable=False),
            sa.Column('opponent_names', sa.JSON(), nullable=False),
            sa.Column('opponent_character_ids', sa.JSON(), nullable=False),
            sa.Column('battle_type',
                      sa.Enum('pve', 'pvp_training', 'pvp_death', 'pvp_attack',
                              name='battletype', create_type=False),
                      nullable=False),
            sa.Column('result',
                      sa.Enum('victory', 'defeat', name='battleresult'),
                      nullable=False),
            sa.Column('finished_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('idx_bh_character_id', 'battle_history', ['character_id'])
        op.create_index('idx_bh_character_finished', 'battle_history',
                        ['character_id', sa.text('finished_at DESC')])


def downgrade() -> None:
    op.drop_index('idx_bh_character_finished', table_name='battle_history')
    op.drop_index('idx_bh_character_id', table_name='battle_history')
    op.drop_table('battle_history')
