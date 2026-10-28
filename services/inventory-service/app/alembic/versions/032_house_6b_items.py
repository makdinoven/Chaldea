"""Player houses (FEAT-180), stage 6b: elite trophies and the home teleport scroll.

* `items.is_elite_trophy` BOOLEAN NOT NULL DEFAULT 0 — a trophy (resource,
  subcategory 'trophy') that hangs in a house trophy hall (+1 % battle experience);
* `items.is_home_teleport` BOOLEAN NOT NULL DEFAULT 0 — a scroll that carries its
  reader to a house with a return circle.

Downgrade drops both columns (trophies hanging in halls stay as plain items).

Revision ID: 032_house_6b_items
Revises: 031_house_seeds
Create Date: 2026-10-28

"""
from alembic import op
import sqlalchemy as sa

revision = '032_house_6b_items'
down_revision = '031_house_seeds'
branch_labels = None
depends_on = None

COLUMNS = ('is_elite_trophy', 'is_home_teleport')


def upgrade():
    for name in COLUMNS:
        op.add_column('items', sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text('0')))


def downgrade():
    for name in reversed(COLUMNS):
        op.drop_column('items', name)
