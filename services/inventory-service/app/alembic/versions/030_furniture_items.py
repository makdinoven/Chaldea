"""House furniture (FEAT-180, stage 3): the `furniture` item type and its fields.

* `items.item_type` ENUM gains 'furniture' (the table is small; the ALTER is quick);
* `items.furniture_room_type` VARCHAR(20) NULL — hall/bedroom/storage/workshop;
* `items.furniture_sleep_bonus` / `furniture_storage_stacks` / `furniture_xp_bonus_pct` /
  `furniture_refine_bonus_pct` — the bonus it adds in a room of that type.

Downgrade: furniture items become 'misc' (nothing is deleted), then the
columns go and the ENUM shrinks back.

Revision ID: 030_furniture_items
Revises: 029_house_storage
Create Date: 2026-10-27

"""
from alembic import op
import sqlalchemy as sa

revision = '030_furniture_items'
down_revision = '029_house_storage'
branch_labels = None
depends_on = None

_TYPES = ("'head','body','cloak','belt','ring','necklace','bracelet','weapon','consumable','resource',"
          "'scroll','misc','recipe','gem','rune','gathering_tool'")


def upgrade():
    op.execute(f"ALTER TABLE items MODIFY COLUMN item_type ENUM({_TYPES},'furniture') NOT NULL")
    op.add_column('items', sa.Column('furniture_room_type', sa.String(20), nullable=True))
    op.add_column('items', sa.Column('furniture_sleep_bonus', sa.Float(), nullable=False, server_default=sa.text('0')))
    op.add_column('items', sa.Column('furniture_storage_stacks', sa.Integer(), nullable=False,
                                     server_default=sa.text('0')))
    op.add_column('items', sa.Column('furniture_xp_bonus_pct', sa.Float(), nullable=False, server_default=sa.text('0')))
    op.add_column('items', sa.Column('furniture_refine_bonus_pct', sa.Float(), nullable=False,
                                     server_default=sa.text('0')))


def downgrade():
    op.execute("UPDATE items SET item_type = 'misc' WHERE item_type = 'furniture'")
    for col in ('furniture_refine_bonus_pct', 'furniture_xp_bonus_pct', 'furniture_storage_stacks',
                'furniture_sleep_bonus', 'furniture_room_type'):
        op.drop_column('items', col)
    op.execute(f"ALTER TABLE items MODIFY COLUMN item_type ENUM({_TYPES}) NOT NULL")
