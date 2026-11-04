"""Quest fame (FEAT-199): `quests.min_fame_tier` and `quests.fame_reward`.

`min_fame_tier` — one of the 5 fixed fame tier codes of character-service
(`nameless|familiar|known|famous|legend`), NULL = no gate. `fame_reward` —
fame for completing, NULL = character-service default, 0 = none. Plain
VARCHAR / INT, no ENUM.

Upgrade: add both columns. Downgrade: drop them.

Revision ID: 056_quest_fame
Revises: 055_region_jail_location
Create Date: 2026-11-04

"""
from alembic import op
import sqlalchemy as sa

revision = '056_quest_fame'
down_revision = '055_region_jail_location'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('quests', sa.Column('min_fame_tier', sa.String(20), nullable=True))
    op.add_column('quests', sa.Column('fame_reward', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('quests', 'fame_reward')
    op.drop_column('quests', 'min_fame_tier')
