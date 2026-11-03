"""Region reputation gates (FEAT-197 §3.1).

* quests.reputation_reward   INT NULL         — reputation for completing the quest; NULL = the points of the
                                                character-service action 'quest_complete' (default +10)
* quests.min_reputation_tier VARCHAR(20) NULL — tier code needed to take the quest (region of the quest giver)
* house_plots.min_reputation_tier VARCHAR(20) NULL — tier code needed to buy / buy back a house on the plot

The reputation tables themselves belong to character-service (038_reputation); this service only reads them.
No backfill: NULL = no gate / default reward. Downgrade drops exactly the three columns.

Revision ID: 054_reputation_gates
Revises: 053_npc_shop_market
Create Date: 2026-11-03

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '054_reputation_gates'
down_revision = '053_npc_shop_market'
branch_labels = None
depends_on = None

TIER_CODE_LEN = 20       # reputation_tiers.code (character-service)

COLUMNS = (
    ('quests', 'reputation_reward', lambda: sa.Column('reputation_reward', sa.Integer(), nullable=True)),
    ('quests', 'min_reputation_tier',
     lambda: sa.Column('min_reputation_tier', sa.String(TIER_CODE_LEN), nullable=True)),
    ('house_plots', 'min_reputation_tier',
     lambda: sa.Column('min_reputation_tier', sa.String(TIER_CODE_LEN), nullable=True)),
)


def _columns(bind, table: str) -> set:
    return {c['name'] for c in inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    for table, name, column in COLUMNS:
        if name not in _columns(bind, table):
            op.add_column(table, column())


def downgrade() -> None:
    bind = op.get_bind()
    for table, name, _column in reversed(COLUMNS):
        if name in _columns(bind, table):
            op.drop_column(table, name)
