"""Add battles.sea_raid_id (FEAT-214)

Sea raid battles (sea monsters boarding a ship deck) are created by
character-service (POST /battles/internal/sea-raid). The tag lets
battle-service report the outcome back (POST /characters/internal/sea/raid-result)
and is returned by GET /battles/internal/{id}/result for the polling fallback.
NULL for every other battle (and for all historical rows). No FK: the raid row
(`sea_raids`) belongs to character-service.

Revision ID: 011_battle_sea_raid
Revises: 010_battle_caravan_raid
Create Date: 2026-11-17

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '011_battle_sea_raid'
down_revision = '010_battle_caravan_raid'
branch_labels = None
depends_on = None

COLUMN = 'sea_raid_id'
INDEX = 'ix_battles_sea_raid_id'


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
