"""Add battles.caravan_raid_id (FEAT-211)

Caravan raid battles are created by character-service
(POST /battles/internal/caravan-raid). The tag lets battle-service report the
outcome back (POST /characters/internal/caravans/raid-result) and is returned
by GET /battles/internal/{id}/result for the polling fallback. NULL for every
other battle (and for all historical rows). No FK: the raid row
(`econ_caravan_raids`) belongs to character-service.

Revision ID: 010_battle_caravan_raid
Revises: 009_battle_law_encounter
Create Date: 2026-11-11

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '010_battle_caravan_raid'
down_revision = '009_battle_law_encounter'
branch_labels = None
depends_on = None

COLUMN = 'caravan_raid_id'
INDEX = 'ix_battles_caravan_raid_id'


def _battle_columns() -> list:
    inspector = sa.inspect(op.get_bind())
    return [c['name'] for c in inspector.get_columns('battles')]


def _battle_indexes() -> list:
    inspector = sa.inspect(op.get_bind())
    return [i['name'] for i in inspector.get_indexes('battles')]


def upgrade() -> None:
    if COLUMN not in _battle_columns():
        op.add_column('battles', sa.Column(COLUMN, sa.Integer(), nullable=True))
    if INDEX not in _battle_indexes():
        op.create_index(INDEX, 'battles', [COLUMN])


def downgrade() -> None:
    if INDEX in _battle_indexes():
        # Not FK-backing, safe to drop before the column.
        op.drop_index(INDEX, table_name='battles')
    if COLUMN in _battle_columns():
        op.drop_column('battles', COLUMN)
