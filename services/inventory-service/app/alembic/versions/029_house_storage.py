"""House storage (FEAT-180): the `house_storage` table.

Stacks lying in a player's house; the house and its residents' rights are in
locations-service. A stored item keeps its sharpening, gems and wear.

Upgrade: create the table. Downgrade: every stored stack goes back to the bag
of the house's owner (nothing is lost), then the table is dropped.

Revision ID: 029_house_storage
Revises: 028_camp_backpack
Create Date: 2026-10-27

"""
from alembic import op
import sqlalchemy as sa

revision = '029_house_storage'
down_revision = '028_camp_backpack'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'house_storage',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('house_id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('is_identified', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('enhancement_points_spent', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('enhancement_bonuses', sa.Text(), nullable=True),
        sa.Column('socketed_gems', sa.Text(), nullable=True),
        sa.Column('current_durability', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['item_id'], ['items.id'], name='fk_house_storage_item', ondelete='CASCADE'),
    )
    op.create_index('ix_house_storage_house_id', 'house_storage', ['house_id'])
    op.create_index('ix_house_storage_item_id', 'house_storage', ['item_id'])


def downgrade():
    op.execute(
        "INSERT INTO character_inventory (character_id, item_id, quantity, is_identified, "
        "enhancement_points_spent, enhancement_bonuses, socketed_gems, current_durability) "
        "SELECT h.owner_character_id, s.item_id, s.quantity, s.is_identified, s.enhancement_points_spent, "
        "s.enhancement_bonuses, s.socketed_gems, s.current_durability "
        "FROM house_storage s JOIN houses h ON h.id = s.house_id"
    )
    op.drop_constraint('fk_house_storage_item', 'house_storage', type_='foreignkey')
    op.drop_index('ix_house_storage_item_id', table_name='house_storage')
    op.drop_index('ix_house_storage_house_id', table_name='house_storage')
    op.drop_table('house_storage')
