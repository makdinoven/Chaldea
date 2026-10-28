"""Player houses (FEAT-180), stage 3: furniture standing in rooms.

`house_furniture` (room, item). The furniture items themselves are rows of
inventory-service `items` with item_type 'furniture' (its migration 030).
Downgrade returns every placed piece to its house owner's bag, then drops the table.

Revision ID: 048_house_furniture
Revises: 047_house_building
Create Date: 2026-10-27

"""
from alembic import op
import sqlalchemy as sa

revision = '048_house_furniture'
down_revision = '047_house_building'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'house_furniture',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('room_id', sa.BigInteger(), sa.ForeignKey('house_rooms.id'), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('placed_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Index('ix_house_furniture_room', 'room_id'),
        mysql_engine='InnoDB',
    )


def downgrade() -> None:
    op.execute(
        "INSERT INTO character_inventory (character_id, item_id, quantity) "
        "SELECT h.owner_character_id, f.item_id, 1 FROM house_furniture f "
        "JOIN house_rooms r ON r.id = f.room_id JOIN houses h ON h.id = r.house_id"
    )
    op.drop_table('house_furniture')
