"""Quest faction fields + house vouchers (FEAT-205 §3.3).

* quests.faction_id INT NULL — faction quest (members only); character-service `factions.id`, no FK
  (cross-service, validated at write time).
* quests.min_faction_rank_id INT NULL — rank of that faction needed to take the quest.
* quests.faction_points_rewards JSON NULL — [{faction_id, points}] paid after completion by character-service.
* house_vouchers — a right to a free house (kind ready) / free empty plot (kind empty) in a location,
  granted by character-service as a faction rank reward; idempotent by `source_key`.

Downgrade drops the table, the index and the three columns. Idempotent (inspects before each step).

Revision ID: 058_quest_faction_vouchers
Revises: 057_country_prison_district
Create Date: 2026-11-05

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '058_quest_faction_vouchers'
down_revision = '057_country_prison_district'
branch_labels = None
depends_on = None

QUESTS = 'quests'
QUEST_INDEX = 'ix_quests_faction'
VOUCHERS = 'house_vouchers'


def _columns(bind, table) -> set:
    return {c['name'] for c in inspect(bind).get_columns(table)}


def _indexes(bind, table) -> set:
    return {i['name'] for i in inspect(bind).get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    cols = _columns(bind, QUESTS)
    if 'faction_id' not in cols:
        op.add_column(QUESTS, sa.Column('faction_id', sa.Integer(), nullable=True))
    if 'min_faction_rank_id' not in cols:
        op.add_column(QUESTS, sa.Column('min_faction_rank_id', sa.Integer(), nullable=True))
    if 'faction_points_rewards' not in cols:
        op.add_column(QUESTS, sa.Column('faction_points_rewards', sa.JSON(), nullable=True))
    if QUEST_INDEX not in _indexes(bind, QUESTS):
        op.create_index(QUEST_INDEX, QUESTS, ['faction_id'])

    if VOUCHERS not in inspect(bind).get_table_names():
        op.create_table(
            VOUCHERS,
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('character_id', sa.Integer(), nullable=False),
            sa.Column('location_id', sa.BigInteger(), nullable=False),
            sa.Column('kind', sa.String(10), nullable=False),
            sa.Column('source_key', sa.String(120), nullable=False),
            sa.Column('source_text', sa.String(255), nullable=True),
            sa.Column('status', sa.String(10), nullable=False, server_default='unclaimed'),
            sa.Column('claimed_house_id', sa.BigInteger(), nullable=True),
            sa.Column('claimed_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint('source_key', name='uq_house_vouchers_source_key'),
        )
        op.create_index('ix_house_vouchers_character', VOUCHERS, ['character_id'])
        # the FK's own index first (MySQL would otherwise auto-create a second one)
        op.create_index('ix_house_vouchers_location', VOUCHERS, ['location_id'])
        op.create_foreign_key('fk_house_vouchers_location', VOUCHERS, 'Locations', ['location_id'], ['id'],
                              ondelete='CASCADE')


def downgrade() -> None:
    bind = op.get_bind()
    if VOUCHERS in inspect(bind).get_table_names():
        op.drop_table(VOUCHERS)
    if QUEST_INDEX in _indexes(bind, QUESTS):
        op.drop_index(QUEST_INDEX, table_name=QUESTS)
    cols = _columns(bind, QUESTS)
    for col in ('faction_points_rewards', 'min_faction_rank_id', 'faction_id'):
        if col in cols:
            op.drop_column(QUESTS, col)
