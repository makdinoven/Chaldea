"""Add battles.dungeon_session_id (FEAT-175)

Battles created by dungeon-service carry the dungeon session id, so the
battle-service knows to report the outcome back to dungeon-service and to
exempt the run's members from the dungeon activity lock. NULL for every
other battle (and for all historical rows).

Revision ID: 008_dungeon_session_id
Revises: 007_participant_joined_at
Create Date: 2026-10-22

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '008_dungeon_session_id'
down_revision = '007_participant_joined_at'
branch_labels = None
depends_on = None

INDEX = 'ix_battles_dungeon_session_id'


def _battle_columns() -> list:
    inspector = sa.inspect(op.get_bind())
    return [c['name'] for c in inspector.get_columns('battles')]


def upgrade() -> None:
    if 'dungeon_session_id' not in _battle_columns():
        op.add_column(
            'battles',
            sa.Column('dungeon_session_id', sa.BigInteger(), nullable=True),
        )
        op.create_index(INDEX, 'battles', ['dungeon_session_id'])


def downgrade() -> None:
    if 'dungeon_session_id' in _battle_columns():
        # Not FK-backing, safe to drop before the column.
        op.drop_index(INDEX, table_name='battles')
        op.drop_column('battles', 'dungeon_session_id')
