"""Camp backpack (FEAT-178): `items.is_backpack` and the `character_backpack` table.

A backpack is a cloak marked `is_backpack`; what is packed into it lives in
`character_backpack`, apart from the bag, so nothing else can spend it.

Upgrade: add the column and the table. Downgrade: every packed stack goes back
to the bag as a row of its own (nothing is lost), then the table and the column
are dropped.

Revision ID: 028_camp_backpack
Revises: 027_fast_slots_belt_only
Create Date: 2026-10-25

"""
from alembic import op
import sqlalchemy as sa

revision = '028_camp_backpack'
down_revision = '027_fast_slots_belt_only'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('items', sa.Column('is_backpack', sa.Boolean(), nullable=False, server_default=sa.text('0')))
    op.create_table(
        'character_backpack',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('character_id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.ForeignKeyConstraint(['item_id'], ['items.id'], name='fk_character_backpack_item', ondelete='CASCADE'),
    )
    op.create_index('ix_character_backpack_character_id', 'character_backpack', ['character_id'])
    op.create_index('ix_character_backpack_item_id', 'character_backpack', ['item_id'])


def downgrade():
    op.execute(
        "INSERT INTO character_inventory (character_id, item_id, quantity) "
        "SELECT character_id, item_id, quantity FROM character_backpack"
    )
    op.drop_constraint('fk_character_backpack_item', 'character_backpack', type_='foreignkey')
    op.drop_index('ix_character_backpack_item_id', table_name='character_backpack')
    op.drop_index('ix_character_backpack_character_id', table_name='character_backpack')
    op.drop_table('character_backpack')
    op.drop_column('items', 'is_backpack')
