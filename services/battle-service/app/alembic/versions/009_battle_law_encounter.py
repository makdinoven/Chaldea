"""Add battles.law_encounter_id (FEAT-198)

Guard battles are created by character-service for a law encounter
(POST /battles/internal/guard). The tag lets battle-service report the
outcome back (POST /characters/internal/law/battle-result) and is returned by
GET /battles/internal/{id}/result for the polling fallback. NULL for every
other battle (and for all historical rows). No FK: the encounter row belongs
to character-service.

Revision ID: 009_battle_law_encounter
Revises: 008_dungeon_session_id
Create Date: 2026-11-04

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '009_battle_law_encounter'
down_revision = '008_dungeon_session_id'
branch_labels = None
depends_on = None

COLUMN = 'law_encounter_id'
INDEX = 'ix_battles_law_encounter_id'


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
